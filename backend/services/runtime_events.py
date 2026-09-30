"""RuntimeEvent V1: bounded, content-free decision and execution audit trail.

Diagnostic logs remain in logging/RAG traces. These events are replay inputs, not
training examples; any later training export needs separate review and consent.
"""
from __future__ import annotations

import hashlib
import json
import logging
import queue
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import PROGRESS_PATH
from utils.version import APP_VERSION

SCHEMA = "texa.runtime_event/v1"
RUNTIME_VERSION = "1"
ROUTER_VERSION = "rules-v1"
DEFAULT_EVENT_DB_PATH = Path(PROGRESS_PATH) / "runtime_events.db"
EVENT_TYPES = frozenset({
    "user_input", "context", "active_goal", "state", "decision", "tool_call",
    "retrieval", "model_call", "state_transition", "execution_result",
    "error", "retry", "user_outcome", "feedback",
})
# No arbitrary payloads. In particular, question, prompt, answer, tool arguments,
# credentials, paths, textbook text, and model reasoning have no field here.
PAYLOAD_FIELDS = frozenset({
    "input_hash", "input_chars", "answer_mode", "subject", "route", "reason_code",
    "decision_mode", "capability", "shadow_only", "goal_ref", "goal_status",
    "task_status", "task_status_before", "task_status_after", "phase", "status",
    "tool_id", "tool_version", "operation_id", "result_status", "error_code",
    "retry_count", "model_role", "model_id", "provider_id", "duration_ms",
    "source_refs", "chunk_refs", "content_refs", "evidence_count", "verification_status",
    "rating", "feedback_reasons", "request_ref", "message_ref", "origin_kind",
    "required_output_count", "context_turn_count", "context_turn_refs", "ledger_revision",
    "resolved_hash", "topic_hash", "constraint_count", "resume", "run_id", "task_id", "call_ref",
    "prompt_version", "context_policy_version", "retrieval_policy_version", "corpus_version",
})
_REF = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_LIST_FIELDS = {"source_refs", "chunk_refs", "content_refs", "feedback_reasons", "context_turn_refs"}
_BOOL_FIELDS = {"shadow_only", "resume"}
_INT_FIELDS = {"input_chars", "retry_count", "evidence_count", "required_output_count", "context_turn_count", "ledger_revision", "constraint_count"}
_FLOAT_FIELDS = {"duration_ms"}
_MAX_ROWS = 100_000
logger = logging.getLogger(__name__)


def text_fingerprint(value: str) -> dict[str, Any]:
    return {"input_hash": hashlib.sha256(value.encode("utf-8")).hexdigest(), "input_chars": len(value)}


def safe_reference(value: Any) -> str:
    text = str(value or "")
    return text if _REF.fullmatch(text) else f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}" if text else ""


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) - PAYLOAD_FIELDS:
        raise ValueError("RuntimeEvent payload contains unapproved fields")
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if value is None or value == "":
            continue
        if key in _LIST_FIELDS:
            if not isinstance(value, (list, tuple)):
                raise ValueError(f"{key} must be a list of references")
            safe[key] = [item for item in value[:32] if isinstance(item, str) and _REF.fullmatch(item)]
        elif key in _BOOL_FIELDS and isinstance(value, bool):
            safe[key] = value
        elif key in _INT_FIELDS and type(value) is int and 0 <= value <= 1_000_000:
            safe[key] = value
        elif key in _FLOAT_FIELDS and type(value) in (int, float) and 0 <= value <= 1_000_000:
            safe[key] = round(float(value), 2)
        elif key not in _BOOL_FIELDS | _INT_FIELDS | _FLOAT_FIELDS and isinstance(value, str) and _REF.fullmatch(value):
            safe[key] = value
        else:
            raise ValueError(f"invalid RuntimeEvent payload value: {key}")
    return safe


def make_event(event_type: str, *, session_id: str, turn_id: str = "", request_id: str = "",
               task_id: str = "", run_id: str = "", parent_event_id: str = "",
               payload: dict[str, Any] | None = None, event_id: str = "") -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise ValueError("unknown RuntimeEvent type")
    for value in (session_id, turn_id, request_id, task_id, run_id, parent_event_id):
        if value and (not isinstance(value, str) or not _REF.fullmatch(value)):
            raise ValueError("invalid RuntimeEvent identity")
    if not session_id:
        raise ValueError("RuntimeEvent session_id is required")
    identity = event_id or f"rev_{uuid.uuid4().hex}"
    if not _REF.fullmatch(identity):
        raise ValueError("invalid RuntimeEvent event_id")
    return {
        "schema": SCHEMA, "event_id": identity, "parent_event_id": parent_event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(), "session_id": session_id,
        "turn_id": turn_id, "request_id": request_id, "task_id": task_id, "run_id": run_id,
        "app_version": APP_VERSION, "runtime_version": RUNTIME_VERSION,
        "router_version": ROUTER_VERSION, "type": event_type,
        "payload": _safe_payload(payload or {}),
    }


def validate_event(event: dict[str, Any]) -> None:
    expected = {"schema", "event_id", "parent_event_id", "timestamp", "session_id",
                "turn_id", "request_id", "task_id", "run_id", "app_version",
                "runtime_version", "router_version", "type", "payload"}
    if not isinstance(event, dict) or set(event) != expected or event["schema"] != SCHEMA or event["type"] not in EVENT_TYPES:
        raise ValueError("invalid RuntimeEvent V1 envelope")
    for key in ("event_id", "session_id", "turn_id", "request_id", "task_id", "run_id", "parent_event_id"):
        value = event[key]
        if not isinstance(value, str) or value and not _REF.fullmatch(value):
            raise ValueError(f"invalid RuntimeEvent {key}")
    if not event["event_id"] or not event["session_id"]:
        raise ValueError("RuntimeEvent identity is required")
    for key in ("app_version", "runtime_version", "router_version"):
        if not isinstance(event[key], str) or not _REF.fullmatch(event[key]):
            raise ValueError(f"invalid RuntimeEvent {key}")
    try:
        timestamp = datetime.fromisoformat(event["timestamp"])
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid RuntimeEvent timestamp") from exc
    if timestamp.tzinfo is None:
        raise ValueError("RuntimeEvent timestamp must have a timezone")
    if _safe_payload(event["payload"]) != event["payload"]:
        raise ValueError("RuntimeEvent payload is not canonical")


class RuntimeEventStore:
    def __init__(self, path: str | Path = DEFAULT_EVENT_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("RuntimeEvent database schema is newer than supported")
            conn.execute("CREATE TABLE IF NOT EXISTS runtime_events (event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, turn_id TEXT NOT NULL, request_id TEXT NOT NULL, timestamp TEXT NOT NULL, event_json TEXT NOT NULL)")
            conn.execute("CREATE INDEX IF NOT EXISTS runtime_events_turn ON runtime_events(session_id,turn_id,timestamp,event_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS runtime_events_request ON runtime_events(request_id,timestamp,event_id)")
            conn.execute("PRAGMA user_version=1")

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def append_many(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        for event in events:
            validate_event(event)
        with self._connect() as conn:
            conn.executemany("INSERT OR IGNORE INTO runtime_events VALUES (?,?,?,?,?,?)", [
                (e["event_id"], e["session_id"], e["turn_id"], e["request_id"], e["timestamp"],
                 json.dumps(e, ensure_ascii=False, separators=(",", ":"))) for e in events
            ])
            count = conn.execute("SELECT COUNT(*) FROM runtime_events").fetchone()[0]
            if count > _MAX_ROWS:
                # Rotate complete oldest turns together, preserving the newest turn.
                oldest = conn.execute("SELECT session_id,turn_id FROM runtime_events GROUP BY session_id,turn_id HAVING SUM(CASE WHEN json_extract(event_json,'$.type') IN ('execution_result','user_outcome','error') THEN 1 ELSE 0 END)>0 ORDER BY MIN(timestamp) LIMIT 1").fetchone()
                newest = conn.execute("SELECT session_id,turn_id FROM runtime_events ORDER BY timestamp DESC LIMIT 1").fetchone()
                if oldest and oldest != newest:
                    conn.execute("DELETE FROM runtime_events WHERE session_id=? AND turn_id=?", oldest)

    def list(self, *, session_id: str, turn_id: str = "", after_event_id: str = "",
             limit: int = 5000) -> list[dict[str, Any]]:
        if not session_id or not _REF.fullmatch(session_id) or turn_id and not _REF.fullmatch(turn_id) or after_event_id and not _REF.fullmatch(after_event_id) or not 1 <= limit <= 10000:
            raise ValueError("invalid RuntimeEvent replay query")
        with self._connect() as conn:
            cursor = 0
            if after_event_id:
                row = conn.execute("SELECT rowid FROM runtime_events WHERE event_id=? AND session_id=?", (after_event_id, session_id)).fetchone()
                if not row:
                    raise ValueError("RuntimeEvent replay cursor not found")
                cursor = row[0]
            rows = conn.execute("SELECT event_json FROM runtime_events WHERE rowid>? AND session_id=? AND (?='' OR turn_id=?) ORDER BY rowid LIMIT ?", (cursor, session_id, turn_id, turn_id, limit)).fetchall()
        return [json.loads(row[0]) for row in rows]


class RuntimeEventWriter:
    def __init__(self, store: RuntimeEventStore, *, max_queue: int = 4096):
        self.store = store
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue(max_queue)
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, name="texa-runtime-events", daemon=True)
        self._worker.start()

    def submit(self, event: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(event)
        except queue.Full:
            logger.error("RuntimeEvent queue full; event dropped id=%s", event["event_id"])

    def _run(self):
        while not self._stop.is_set() or not self.queue.empty():
            batch = []
            try:
                batch.append(self.queue.get(timeout=0.2))
            except queue.Empty:
                continue
            while len(batch) < 128:
                try:
                    batch.append(self.queue.get_nowait())
                except queue.Empty:
                    break
            for attempt in range(3):
                try:
                    self.store.append_many(batch)
                    break
                except Exception:
                    if attempt == 2:
                        logger.exception("RuntimeEvent batch persistence failed after retries")
                    else:
                        time.sleep(0.05 * (attempt + 1))
            for _ in batch:
                self.queue.task_done()

    def flush(self):
        self.queue.join()

    def stop(self):
        self._stop.set()
        self._worker.join(timeout=5)


_writer: RuntimeEventWriter | None = None
_writer_lock = threading.Lock()
_last_event: dict[tuple[str, str], str] = {}


def start_writer() -> None:
    global _writer
    with _writer_lock:
        if _writer is None:
            _writer = RuntimeEventWriter(RuntimeEventStore())


def emit(event_type: str, *, session_id: str, turn_id: str = "", request_id: str = "",
         task_id: str = "", run_id: str = "", payload: dict[str, Any] | None = None) -> str:
    global _writer
    key = (session_id, turn_id or run_id)
    with _writer_lock:
        parent = _last_event.get(key, "")
        event = make_event(event_type, session_id=session_id, turn_id=turn_id,
                           request_id=request_id, task_id=task_id, run_id=run_id,
                           parent_event_id=parent, payload=payload)
        if _writer is None:
            _writer = RuntimeEventWriter(RuntimeEventStore())
        _writer.submit(event)
        _last_event[key] = event["event_id"]
        if len(_last_event) > 8192:
            _last_event.pop(next(iter(_last_event)))
    return event["event_id"]


def emit_best_effort(event_type: str, **kwargs: Any) -> str:
    try:
        return emit(event_type, **kwargs)
    except Exception:
        logger.exception("RuntimeEvent emission failed type=%s", event_type)
        return ""


def observe_execution_event(event: dict[str, Any]) -> None:
    """Project the existing SSE protocol onto the unified audit contract."""
    phase = str(event.get("phase") or "")
    kind = str(event.get("kind") or "")
    event_type = str(event.get("type") or "")
    payload = event.get("payload") or {}
    if not event.get("conversation_id") and not event.get("task_id") and not event.get("origin"):
        return
    if event_type == "output_delta":
        return
    if event_type == "progress" and kind not in {"tool", "evidence"}:
        return
    lifecycle = str(payload.get("lifecycle") or "")
    if lifecycle == "run.created":
        category = "active_goal"
    elif lifecycle == "run.resumed":
        category = "retry"
    elif event_type == "error":
        category = "error"
    elif event_type == "final":
        category = "execution_result"
    elif kind == "tool":
        category = "tool_call"
    elif phase == "retrieval" or kind == "evidence":
        category = "retrieval"
    elif phase in {"generation", "model"}:
        category = "model_call"
    else:
        category = "state_transition"
    safe = {"phase": phase or "system", "status": str(event.get("status") or "running")}
    for key in ("task_status", "task_status_before", "task_status_after", "error_code", "tool_id", "evidence_count"):
        if key in payload:
            safe[key] = payload[key]
    if "tool" in payload and "tool_id" not in safe:
        safe["tool_id"] = payload["tool"]
    if "tool_call_id" in payload:
        safe["call_ref"] = payload["tool_call_id"]
    if category == "active_goal":
        safe["goal_ref"] = str(event.get("task_id") or "")
        safe["goal_status"] = "running"
    if "tool_status" in payload:
        safe["result_status"] = payload["tool_status"]
    if "lifecycle" in payload and payload["lifecycle"] == "run.created":
        safe["task_status"] = "running"
    if "lifecycle" in payload and payload["lifecycle"].startswith("model."):
        category = "model_call"
    if event.get("operation_id") and _REF.fullmatch(str(event["operation_id"])):
        safe["operation_id"] = event["operation_id"]
    session_id = event.get("conversation_id") or (f"origin:{event.get('origin', {}).get('kind', 'run')}:{event.get('origin', {}).get('id', event.get('task_id', ''))}")
    emit(category, session_id=session_id, turn_id=event.get("turn_id") or "",
         request_id=event.get("request_id") or "", task_id=event.get("task_id") or "",
         run_id=event.get("run_id") or "", payload=safe)
    if event_type == "final":
        emit("user_outcome", session_id=session_id, turn_id=event.get("turn_id") or "",
             request_id=event.get("request_id") or "", task_id=event.get("task_id") or "",
             run_id=event.get("run_id") or "",
             payload={"task_status": str(payload.get("task_status") or payload.get("task_status_after") or "completed")})


def replay(*, session_id: str, turn_id: str = "", after_event_id: str = "",
           limit: int = 5000, store: RuntimeEventStore | None = None) -> dict[str, Any]:
    if not 1 <= limit <= 5000:
        raise ValueError("invalid RuntimeEvent replay page size")
    if store is None:
        with _writer_lock:
            writer = _writer
        if writer:
            writer.flush()
        store = RuntimeEventStore()
    page = store.list(session_id=session_id, turn_id=turn_id,
                      after_event_id=after_event_id, limit=limit + 1)
    truncated = len(page) > limit
    events = page[:limit]
    ids = {event["event_id"] for event in events}
    state: dict[str, Any] = {}
    chain: list[dict[str, Any]] = []
    for event in events:
        payload = event["payload"]
        if event["type"] in {"user_input", "context", "state", "decision", "retrieval", "state_transition", "active_goal", "execution_result", "user_outcome", "error"}:
            for key in ("task_status", "goal_status", "answer_mode", "subject", "route", "decision_mode", "capability", "chunk_refs", "source_refs", "content_refs", "context_turn_refs", "ledger_revision", "resolved_hash", "topic_hash", "constraint_count", "model_id", "provider_id", "prompt_version", "context_policy_version", "retrieval_policy_version", "corpus_version"):
                if key in payload:
                    state[key] = payload[key]
            if "task_status_after" in payload:
                state["task_status"] = payload["task_status_after"]
        chain.append({"event_id": event["event_id"], "parent_event_id": event["parent_event_id"],
                      "type": event["type"], "parent_present": event["parent_event_id"] in ids if event["parent_event_id"] else True})
    return {"schema": SCHEMA, "session_id": session_id, "turn_id": turn_id,
            "state": state, "chain": chain, "events": events, "truncated": truncated,
            "next_cursor": events[-1]["event_id"] if truncated else ""}


def stop_writer() -> None:
    global _writer
    with _writer_lock:
        writer, _writer = _writer, None
        _last_event.clear()
    if writer:
        writer.stop()
