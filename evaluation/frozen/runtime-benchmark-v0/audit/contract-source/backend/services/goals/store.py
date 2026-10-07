"""Conversation-independent, evidence-based Goal foundation (P3)."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import PROGRESS_PATH

DEFAULT_GOAL_DB_PATH = Path(PROGRESS_PATH) / "goals.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _validate_content(snapshot: dict) -> None:
    if not isinstance(snapshot.get("title"), str) or not snapshot["title"].strip() or len(snapshot["title"]) > 200:
        raise ValueError("invalid goal title")
    if not isinstance(snapshot.get("objective"), str) or len(snapshot["objective"]) > 2000:
        raise ValueError("invalid goal objective")
    criteria = snapshot.get("success_criteria")
    if not isinstance(criteria, list) or len(criteria) > 12 or len(_dump(criteria)) > 16000:
        raise ValueError("invalid goal criteria")
    ids = []
    for criterion in criteria:
        if not isinstance(criterion, dict) or not isinstance(criterion.get("id"), str) or not criterion["id"].strip():
            raise ValueError("goal criterion requires an id")
        ids.append(criterion["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate goal criterion ids")
    if not isinstance(snapshot.get("scope"), dict) or len(_dump(snapshot["scope"])) > 8000:
        raise ValueError("invalid goal scope")


class GoalConflict(RuntimeError):
    pass


class GoalStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("goal schema is newer than supported")
            if version == 0:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute("CREATE TABLE goals (id TEXT PRIMARY KEY, learner_id TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL, snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
                    conn.execute("CREATE TABLE goal_revisions (goal_id TEXT NOT NULL REFERENCES goals(id), revision INTEGER NOT NULL, snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(goal_id,revision))")
                    conn.execute("CREATE TABLE goal_run_links (goal_id TEXT NOT NULL REFERENCES goals(id), task_id TEXT NOT NULL, run_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, PRIMARY KEY(goal_id,task_id,run_id))")
                    conn.execute("PRAGMA user_version=1")
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def create(self, *, learner_id: str, title: str, objective: str,
               scope: dict[str, Any] | None = None,
               success_criteria: list[dict[str, Any]] | None = None,
               target_date: str = "", timezone_name: str = "", goal_id: str = "") -> dict:
        if not learner_id or not title.strip() or len(title) > 200 or len(objective) > 2000:
            raise ValueError("invalid goal identity or content")
        criteria = list(success_criteria or [])
        if len(criteria) > 12 or len(_dump(criteria)) > 16000:
            raise ValueError("goal criteria exceed size budget")
        if goal_id and (len(goal_id) > 200 or not goal_id.strip()):
            raise ValueError("invalid goal id")
        goal_id = goal_id or f"goal_{uuid.uuid4().hex}"
        now = _now()
        snapshot = {"id": goal_id, "learner_id": learner_id, "title": title.strip(),
            "objective": objective.strip(), "scope": scope or {},
            "success_criteria": criteria, "target_date": target_date or None,
            "timezone": timezone_name or None, "status": "draft",
            "progress": {"criterion_results": [], "evidence_refs": [],
                         "measured_at": None, "unknowns": [item.get("id") for item in criteria]},
            "plan": {"version": 0, "bounded_steps": [], "approved_revision": None},
            "next_action": None, "revision": 1, "created_at": now, "updated_at": now}
        _validate_content(snapshot)
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("INSERT INTO goals VALUES (?,?,?,?,?,?,?)",
                             (goal_id, learner_id, "draft", 1, _dump(snapshot), now, now))
                conn.execute("INSERT INTO goal_revisions VALUES (?,?,?,?)",
                             (goal_id, 1, _dump(snapshot), now))
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return snapshot

    def get(self, goal_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT snapshot_json FROM goals WHERE id=?", (goal_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def list(self, *, learner_id: str, limit: int = 50, before_id: str = "") -> list[dict]:
        if not learner_id or not 1 <= limit <= 100:
            raise ValueError("invalid goal list bounds")
        with closing(self._connect()) as conn:
            return [json.loads(row[0]) for row in conn.execute(
                "SELECT snapshot_json FROM goals WHERE learner_id=? AND (?='' OR id<?) ORDER BY id DESC LIMIT ?",
                (learner_id, before_id, before_id, limit))]

    def active_for_scope(self, *, learner_id: str, book_name: str) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT snapshot_json FROM goals WHERE learner_id=? AND status='active' AND json_extract(snapshot_json,'$.scope.book_name')=? ORDER BY updated_at DESC LIMIT 20", (learner_id, book_name))
            return [json.loads(row[0]) for row in rows]

    def update(self, goal_id: str, *, expected_revision: int,
               changes: dict[str, Any], projection_source_id: str = "") -> dict:
        allowed = {"title", "objective", "scope", "success_criteria", "target_date",
                   "timezone", "status", "progress", "plan", "next_action"}
        if set(changes) - allowed:
            raise ValueError("unknown goal fields")
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
                if not row or row["revision"] != expected_revision:
                    raise GoalConflict("goal revision changed")
                snapshot = json.loads(row["snapshot_json"])
                if snapshot["status"] in {"completed", "cancelled"} and changes.get("status") not in {None, snapshot["status"]}:
                    raise GoalConflict("terminal goal cannot be reopened")
                snapshot.update(changes)
                if set(changes) & {"objective", "scope", "success_criteria"}:
                    snapshot["plan"] = {"version": int(snapshot.get("plan", {}).get("version", 0)) + 1,
                                        "bounded_steps": [], "approved_revision": None}
                    snapshot["next_action"] = None
                _validate_content(snapshot)
                if snapshot["status"] not in {"draft", "active", "paused", "completed", "cancelled"}:
                    raise ValueError("invalid goal status")
                if len(_dump(snapshot)) > 64000:
                    raise ValueError("goal exceeds size budget")
                snapshot["revision"] = expected_revision + 1
                snapshot["updated_at"] = _now()
                cursor = conn.execute("UPDATE goals SET status=?,revision=?,snapshot_json=?,updated_at=? WHERE id=? AND revision=?",
                    (snapshot["status"], snapshot["revision"], _dump(snapshot), snapshot["updated_at"],
                     goal_id, expected_revision))
                if cursor.rowcount != 1:
                    raise GoalConflict("goal revision changed")
                # Bind preparation identity to the committed revision, even if
                # the event projector fails. Keep it out of the current Goal.
                revision_snapshot = dict(snapshot)
                if projection_source_id:
                    revision_snapshot["_projection_source_id"] = projection_source_id
                conn.execute("INSERT INTO goal_revisions VALUES (?,?,?,?)",
                             (goal_id, snapshot["revision"], _dump(revision_snapshot), snapshot["updated_at"]))
                conn.commit()
                return snapshot
            except BaseException:
                conn.rollback()
                raise

    def link(self, goal_id: str, *, task_id: str, run_id: str = "") -> None:
        if not task_id or not self.get(goal_id):
            raise ValueError("goal and task are required")
        with closing(self._connect()) as conn:
            conn.execute("INSERT OR IGNORE INTO goal_run_links VALUES (?,?,?,?)",
                         (goal_id, task_id, run_id, _now()))

    def links(self, goal_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            return [dict(row) for row in conn.execute(
                "SELECT task_id,run_id,created_at FROM goal_run_links WHERE goal_id=? ORDER BY created_at",
                (goal_id,))]

    def revisions(self, goal_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            return [json.loads(row[0]) for row in conn.execute(
                "SELECT snapshot_json FROM goal_revisions WHERE goal_id=? ORDER BY revision",
                (goal_id,))]

    def projected_operation(self, *, learner_id: str, source_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT r.snapshot_json FROM goal_revisions r JOIN goals g ON g.id=r.goal_id WHERE g.learner_id=? AND json_extract(r.snapshot_json,'$._projection_source_id')=? LIMIT 1",
                               (learner_id, source_id)).fetchone()
            return json.loads(row[0]) if row else None


def legacy_goal_id(event_id: str) -> str:
    """Stable mapping only; missing legacy objective and criteria remain unknown."""
    if not event_id:
        raise ValueError("legacy event id required")
    return f"legacy_goal_{uuid.uuid5(uuid.NAMESPACE_URL, 'texa-learning-event:' + event_id).hex}"


def legacy_goal_projection(event: Any) -> dict:
    payload = event.payload if isinstance(event.payload, dict) else {}
    return {"id": legacy_goal_id(event.id), "learner_id": event.learner_id,
            "title": str(payload.get("target_name") or "历史学习目标")[:200],
            "objective": None, "scope": {"book_name": event.book_name,
            "chapter_id": event.chapter_id}, "success_criteria": None,
            "status": "active", "legacy_event_id": event.id,
            "progress": {"criterion_results": [], "evidence_refs": [],
                         "measured_at": None, "unknowns": ["objective", "success_criteria"]}}
