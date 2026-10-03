"""SQLite-backed background job state manager."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from config import PROGRESS_PATH
from utils.sqlite_recovery import prepare_sqlite_retry_files
from utils.sqlite_migrations import apply_sqlite_migrations


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "interrupted"}
RUNNING_STATUSES = {"queued", "running", "cancelling"}


class JobCancelled(RuntimeError):
    """Raised inside a worker when cancellation has been requested."""


class JobManager:
    """Small durable job store for background work.

    The manager intentionally stores business-specific fields in ``input`` and
    ``result`` JSON. ``to_dict`` also flattens input keys for compatibility with
    the existing API responses used by the frontend.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or (Path(PROGRESS_PATH) / "jobs.sqlite3"))
        self._lock = threading.RLock()
        self._force_delete_journal = False
        self._init_db()

    def create_job(
        self,
        job_type: str,
        input_data: dict[str, Any] | None = None,
        *,
        status: str = "queued",
        stage: str = "queued",
        progress: int = 0,
        message: str = "",
        job_id: str | None = None,
    ) -> dict[str, Any]:
        now = _now()
        job_id = job_id or uuid.uuid4().hex
        with self._connect() as conn, self._lock:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, type, status, stage, progress, message, input_json,
                    result_json, error, created_at, updated_at, started_at,
                    completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, NULL)
                """,
                (
                    job_id,
                    job_type,
                    status,
                    stage,
                    _clamp_progress(progress),
                    message,
                    _json_dumps(input_data or {}),
                    now,
                    now,
                    now if status == "running" else None,
                ),
            )
            conn.commit()
        return self.get_job(job_id) or {"id": job_id, "type": job_type}

    def get_job(self, job_id: str, job_type: str | None = None) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        job = self._row_to_job(row)
        if job_type and job.get("type") != job_type:
            return None
        return job

    def list_jobs(self, job_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 100), 500))
        query = "SELECT * FROM jobs"
        params: tuple[Any, ...] = ()
        if job_type:
            query += " WHERE type = ?"
            params = (job_type,)
        query += " ORDER BY created_at DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(query, (*params, limit)).fetchall()
        return [self._row_to_job(row) for row in rows]

    def update_job(self, job_id: str, **updates: Any) -> dict[str, Any]:
        if not updates:
            job = self.get_job(job_id)
            if job is None:
                raise KeyError(f"job not found: {job_id}")
            return job

        allowed = {
            "status",
            "stage",
            "progress",
            "message",
            "result",
            "error",
            "started_at",
            "completed_at",
        }
        columns: dict[str, Any] = {}
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key == "result":
                columns["result_json"] = _json_dumps(value)
            elif key == "progress":
                columns[key] = _clamp_progress(value)
            else:
                columns[key] = value

        now = _now()
        status = columns.get("status")
        if status == "running" and "started_at" not in columns:
            columns["started_at"] = now
        if status in TERMINAL_STATUSES and "completed_at" not in columns:
            columns["completed_at"] = now
        columns["updated_at"] = now

        assignments = ", ".join(f"{column} = ?" for column in columns)
        values = list(columns.values()) + [job_id]
        with self._connect() as conn, self._lock:
            cur = conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", values)
            if cur.rowcount == 0:
                raise KeyError(f"job not found: {job_id}")
            conn.commit()
        return self.get_job(job_id) or {"id": job_id}

    def complete_job(self, job_id: str, **updates: Any) -> dict[str, Any]:
        """Atomically complete a job unless cancellation already won the race."""
        allowed = {"stage", "progress", "message", "result", "error"}
        columns: dict[str, Any] = {
            "status": "completed",
            "completed_at": _now(),
            "updated_at": _now(),
        }
        for key, value in updates.items():
            if key not in allowed:
                continue
            if key == "result":
                columns["result_json"] = _json_dumps(value)
            elif key == "progress":
                columns[key] = _clamp_progress(value)
            else:
                columns[key] = value
        columns.setdefault("stage", "completed")
        columns.setdefault("progress", 100)

        assignments = ", ".join(f"{column} = ?" for column in columns)
        values = list(columns.values()) + [job_id]
        with self._connect() as conn, self._lock:
            cur = conn.execute(
                f"UPDATE jobs SET {assignments} WHERE id = ? AND status IN ('queued', 'running')",
                values,
            )
            conn.commit()
        if cur.rowcount:
            return self.get_job(job_id) or {"id": job_id, "status": "completed"}

        job = self.get_job(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        if job.get("status") in {"cancelling", "cancelled"}:
            raise JobCancelled(job.get("message") or "job cancelled")
        if job.get("status") == "completed":
            return job
        raise RuntimeError(f"job cannot complete from status: {job.get('status')}")

    def claim_queued_job(self, job_id: str) -> bool:
        """Claim a worker without reviving cancelled/interrupted attempts."""
        stamp = _now()
        with self._connect() as conn, self._lock:
            cur = conn.execute(
                "UPDATE jobs SET status='running', started_at=?, updated_at=? "
                "WHERE id=? AND status='queued'", (stamp, stamp, job_id),
            )
            conn.commit()
        return bool(cur.rowcount)

    def fail_or_cancel_job(self, job_id: str, *, error: str, message: str) -> dict[str, Any]:
        """Failure respects cancellation and never changes a terminal receipt."""
        stamp = _now()
        with self._connect() as conn, self._lock:
            conn.execute(
                "UPDATE jobs SET status=CASE WHEN status='cancelling' THEN 'cancelled' ELSE 'failed' END, "
                "stage=CASE WHEN status='cancelling' THEN 'cancelled' ELSE 'failed' END, "
                "error=?, message=?, updated_at=?, completed_at=? "
                "WHERE id=? AND status IN ('queued','running','cancelling')",
                (error, message, stamp, stamp, job_id),
            )
            conn.commit()
        return self.get_job(job_id) or {"id": job_id}

    def request_cancel(self, job_id: str, message: str = "Cancellation requested") -> dict[str, Any]:
        now = _now()
        with self._connect() as conn, self._lock:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'cancelling', stage = 'cancelling', message = ?, updated_at = ?
                WHERE id = ? AND status IN ('queued', 'running')
                """,
                (message, now, job_id),
            )
            conn.commit()
        job = self.get_job(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        return job

    def raise_if_cancelled(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job and job.get("status") == "cancelling":
            raise JobCancelled(job.get("message") or "job cancelled")

    def mark_running_interrupted(self, message: str = "Server restarted before the job finished") -> int:
        now = _now()
        with self._connect() as conn, self._lock:
            cur = conn.execute(
                """
                UPDATE jobs
                SET status = 'interrupted', stage = 'interrupted', message = ?,
                    error = ?, updated_at = ?, completed_at = ?
                WHERE status IN ('queued', 'running', 'cancelling')
                """,
                (message, message, now, now),
            )
            conn.commit()
            return int(cur.rowcount or 0)

    def import_legacy_json_jobs(
        self,
        job_type: str,
        job_dir: str | Path,
        *,
        input_keys: Iterable[str] = (),
    ) -> int:
        directory = Path(job_dir)
        if not directory.exists():
            return 0
        imported = 0
        for path in directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            job_id = str(payload.get("id") or path.stem)
            if self.get_job(job_id):
                continue
            input_data = {key: payload.get(key) for key in input_keys if key in payload}
            status = str(payload.get("status") or "interrupted")
            stage = str(payload.get("stage") or status)
            message = str(payload.get("message") or "")
            created_at = str(payload.get("created_at") or payload.get("updated_at") or _now())
            updated_at = str(payload.get("updated_at") or created_at)
            result = payload.get("result")
            error = payload.get("error")
            completed_at = updated_at if status in TERMINAL_STATUSES else None
            with self._connect() as conn, self._lock:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO jobs (
                        id, type, status, stage, progress, message, input_json,
                        result_json, error, created_at, updated_at, started_at,
                        completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        job_type,
                        status,
                        stage,
                        _clamp_progress(payload.get("progress", 0)),
                        message,
                        _json_dumps(input_data),
                        _json_dumps(result) if result is not None else None,
                        error,
                        created_at,
                        updated_at,
                        created_at if status in RUNNING_STATUSES else None,
                        completed_at,
                    ),
                )
                conn.commit()
                imported += 1
        return imported

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._init_db_once()
        except sqlite3.OperationalError as exc:
            if not _is_sqlite_storage_error(exc):
                raise
            self._force_delete_journal = True
            self._prepare_retry_db_files()
            self._init_db_once()

    def _init_db_once(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT '',
                    progress INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    input_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_type_created ON jobs(type, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            apply_sqlite_migrations(conn, component="job_manager", current_version=1)
            conn.commit()

    def _prepare_retry_db_files(self) -> None:
        result = prepare_sqlite_retry_files(self.db_path)
        if result["preserved"]:
            print(
                f"[sqlite] preserved non-empty recovery files for {self.db_path}: "
                f"{', '.join(result['preserved'])}",
                flush=True,
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if self._force_delete_journal:
            conn.execute("PRAGMA journal_mode=DELETE")
        else:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError as exc:
                if not _is_sqlite_storage_error(exc):
                    raise
                self._force_delete_journal = True
                conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _row_to_job(self, row: sqlite3.Row) -> dict[str, Any]:
        input_data = _json_loads(row["input_json"], {})
        result = _json_loads(row["result_json"], None) if row["result_json"] else None
        job = {
            "id": row["id"],
            "type": row["type"],
            "status": row["status"],
            "stage": row["stage"],
            "progress": row["progress"],
            "message": row["message"],
            "input": input_data,
            "result": result,
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
        }
        if isinstance(input_data, dict):
            for key, value in input_data.items():
                job.setdefault(key, value)
        return job


_job_manager: JobManager | None = None
_manager_lock = threading.Lock()


def get_job_manager() -> JobManager:
    global _job_manager
    if _job_manager is None:
        with _manager_lock:
            if _job_manager is None:
                _job_manager = JobManager()
    return _job_manager


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _is_sqlite_storage_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return (
        "disk i/o" in message
        or "readonly" in message
        or "unable to open database file" in message
    )

def _clamp_progress(value: Any) -> int:
    try:
        return max(0, min(100, int(value)))
    except Exception:
        return 0
