"""Durable confirmation boundary for learner-state mutations proposed by tools."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from config import PROGRESS_PATH
from utils.json_io import atomic_write_json


from backend.services.goals.service import GOAL_CONTROL_LOCK

_ACTION_LOCK = GOAL_CONTROL_LOCK
_ALLOWED_TYPES = {"add_mistake", "mark_concept_reviewed", "create_practice_session", "record_practice_result", "update_mistake"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class PendingActionStore:
    def __init__(self, root: str | Path | None = None):
        self.data_root = Path(root or PROGRESS_PATH)
        self.root = self.data_root / "pending_actions"

    def _path(self, action_id: str) -> Path:
        if not action_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in action_id):
            raise ValueError("invalid pending action id")
        return self.root / f"{action_id}.json"

    def create(self, proposal: dict[str, Any], *, context: dict[str, str], action_id: str = "") -> dict[str, Any]:
        action_type = str(proposal.get("type") or "")
        if action_type not in _ALLOWED_TYPES:
            raise ValueError(f"unsupported pending action type: {action_type}")
        action = {
            "action_id": action_id or f"action_{uuid.uuid4().hex}",
            "type": action_type,
            "payload": dict(proposal.get("payload") or {}),
            "context": {
                "book_name": str(context.get("book_name") or "default"),
                "subject": str(context.get("subject") or ""),
                "conversation_id": str(context.get("conversation_id") or ""),
                "learning_task_id": str(context.get("learning_task_id") or ""),
            },
            "status": "pending",
            "result": None,
            "error": "",
            "created_at": _now(),
            "updated_at": _now(),
        }
        if action_id:
            existing = self.get(action_id)
            if existing:
                if existing.get("type") != action_type or existing.get("payload") != action["payload"] or existing.get("context") != action["context"]:
                    raise ValueError("stable pending action id reused with different proposal")
                return existing
        self.save(action)
        return action

    def get(self, action_id: str) -> dict[str, Any] | None:
        path = self._path(action_id)
        if not path.is_file():
            return None
        with _ACTION_LOCK:
            return json.loads(path.read_text(encoding="utf-8"))

    def save(self, action: dict[str, Any]) -> dict[str, Any]:
        action["updated_at"] = _now()
        path = self._path(str(action.get("action_id") or ""))
        with _ACTION_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(path, action)
        return action

    def domain_receipt(self, action_id: str) -> dict[str, Any] | None:
        action = self.get(action_id)
        if action is None:
            raise KeyError(action_id)
        receipt = _read_domain_receipt(action, self.data_root)
        if receipt is not None:
            _reconcile_domain_projection(action, self.data_root)
        return receipt

    def reject(self, action_id: str) -> dict[str, Any]:
        with _ACTION_LOCK:
            action = self.get(action_id)
            if action is None:
                raise KeyError(action_id)
            if action.get("status") == "confirmed":
                raise ValueError("confirmed action cannot be rejected")
            if action.get("status") == "rejected":
                return action
            receipt = _read_domain_receipt(action, self.data_root)
            if receipt is not None:
                action.update(status="confirmed", result=receipt, error="")
                self.save(action)
                raise ValueError("executed action cannot be rejected")
            action["status"] = "rejected"
            action["result"] = {"rejected": True}
            return self.save(action)

    def confirm(self, action_id: str) -> dict[str, Any]:
        with _ACTION_LOCK:
            action = self.get(action_id)
            if action is None:
                raise KeyError(action_id)
            if action.get("status") == "confirmed":
                _reconcile_domain_projection(action, self.data_root)
                return action
            if action.get("status") == "rejected":
                raise ValueError("rejected action cannot be confirmed")
            try:
                receipt = _read_domain_receipt(action, self.data_root)
                if receipt is None:
                    context = action.get("context") or {}
                    task_id = context.get("learning_task_id")
                    if task_id:
                        if task_id.startswith("rtask_"):
                            path = self.data_root / "agent_runtime.db"
                            if path.exists():
                                import sqlite3
                                with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
                                    row = conn.execute("SELECT status FROM runtime_tasks WHERE id=?", (task_id,)).fetchone()
                                if row and row[0] == "cancelled":
                                    raise ValueError("task was explicitly cancelled")
                        else:
                            from backend.services.learning_task import LearningTaskStore
                            task = LearningTaskStore(self.data_root).get(task_id)
                            if task and task.status == "cancelled":
                                raise ValueError("task was explicitly cancelled")
                action["result"] = receipt if receipt is not None else _execute(action, self.data_root)
                _reconcile_domain_projection(action, self.data_root)
                action["status"] = "confirmed"
                action["error"] = ""
            except Exception as exc:
                action["status"] = "failed"
                action["error"] = str(exc)[:500]
                self.save(action)
                raise
            return self.save(action)


def _read_domain_receipt(action: dict[str, Any], data_root: str | Path = PROGRESS_PATH) -> dict[str, Any] | None:
    """Read without constructing stores, migrations, or a domain write."""
    import sqlite3
    from utils.path_safety import safe_book_name, safe_child_path
    from utils.state_locks import get_state_lock
    payload, context = action.get("payload") or {}, action.get("context") or {}
    book = safe_book_name(payload.get("book_name") or context.get("book_name") or "default")
    operation_id, kind = action["action_id"], action["type"]
    if kind == "mark_concept_reviewed":
        path = safe_child_path(data_root, book, "concept_memory.json")
        with get_state_lock(path):
            if not path.is_file():
                return None
            value = json.loads(path.read_text(encoding="utf-8")).get("review_operations", {}).get(operation_id)
        return {"concept": value} if value is not None else None
    if kind in {"update_mistake", "record_practice_result"}:
        prefix = "mistake_book" if kind == "update_mistake" else "exercise_bank"
        path = safe_child_path(data_root, f"{prefix}_{book}.db")
        if not path.is_file():
            return None
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            if kind == "update_mistake":
                if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mistake_operations'").fetchone():
                    return None
                row = conn.execute("SELECT result_json FROM mistake_operations WHERE operation_id=?", (operation_id,)).fetchone()
                return json.loads(row[0]) if row else None
            row = conn.execute("SELECT data FROM exercise_practice_sessions WHERE id=?", (payload["session_id"],)).fetchone()
        result = json.loads(row[0]).get("results", {}).get(payload["exercise_id"]) if row else None
        if result is None:
            return None
        if any(result.get(key, "") != payload.get(key, "").strip() if key != "quality" else result[key] != payload[key]
               for key in ("user_answer", "quality", "note")):
            raise ValueError("practice answer arguments differ from the committed result")
        return {"session_id": payload["session_id"], "exercise_id": payload["exercise_id"], "answer_recorded": True}
    tables = {"add_mistake": ("mistake_book", "mistakes"),
              "create_practice_session": ("exercise_bank", "exercise_practice_sessions")}
    if kind not in tables:
        raise ValueError("unsupported pending action type")
    prefix, table = tables[kind]
    path = safe_child_path(data_root, f"{prefix}_{book}.db")
    if not path.is_file():
        return None
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = conn.execute(f"SELECT data FROM {table} WHERE id = ?", (operation_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    data = json.loads(row[0])
    return ({"mistake_id": operation_id} if kind == "add_mistake" else
            {"session_id": operation_id, "exercise_ids": data["exercise_ids"]})


def _execute(action: dict[str, Any], data_root: str | Path = PROGRESS_PATH) -> dict[str, Any]:
    action_type = str(action.get("type") or "")
    payload = dict(action.get("payload") or {})
    context = dict(action.get("context") or {})
    operation_id = str(action["action_id"])
    book_name = str(payload.get("book_name") or context.get("book_name") or "default")

    if action_type == "update_mistake":
        from memory.mistake_book import get_mistake_book
        return get_mistake_book(book_name, str(data_root)).update_once(payload["mistake_id"],
            operation_id=operation_id, expected_revision=payload["expected_revision"], changes={"notes": payload["notes"]})
    if action_type == "record_practice_result":
        from memory.exercise_bank import get_exercise_bank
        bank = get_exercise_bank(book_name, str(data_root))
        bank.record_session_answer_with_status(payload["session_id"], exercise_id=payload["exercise_id"],
            user_answer=payload["user_answer"], quality=payload["quality"], note=payload.get("note", ""))
        return _read_domain_receipt(action, data_root)

    if action_type == "add_mistake":
        from memory.mistake_book import MistakeRecord, get_mistake_book

        tags = payload.get("tags") or []
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.replace("，", ",").split(",") if item.strip()]
        record = MistakeRecord(
            id=operation_id,
            question_text=str(payload.get("question_text") or "").strip(),
            user_answer=str(payload.get("user_answer") or ""),
            correct_answer=str(payload.get("correct_answer") or ""),
            source=str(payload.get("source") or "agent_confirmation"),
            subject=str(payload.get("subject") or context.get("subject") or ""),
            chapter=str(payload.get("chapter") or "") or None,
            tags=list(tags)[:30],
            mistake_type=list(payload.get("mistake_type") or [])[:10],
            difficulty=max(1, min(5, int(payload.get("difficulty") or 3))),
            explanation=str(payload.get("explanation") or ""),
        )
        if not record.question_text:
            raise ValueError("question_text is required")
        record_id = get_mistake_book(book_name, str(data_root)).add_if_absent(record)
        return {"mistake_id": record_id}

    if action_type == "mark_concept_reviewed":
        from knowledge.concept_memory import ConceptMemory

        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("concept name is required")
        result = ConceptMemory(book_name).mark_reviewed(
            name,
            quality=max(0, min(5, int(payload.get("quality") or 4))),
            note=str(payload.get("note") or "agent_confirmation"),
            operation_id=operation_id,
        )
        return {"concept": result}

    if action_type == "create_practice_session":
        from memory.exercise_bank import PracticeSession, get_exercise_bank

        bank = get_exercise_bank(book_name, str(data_root))
        existing = bank.get_practice_session(operation_id)
        if existing:
            return {"session_id": existing.id, "exercise_ids": existing.exercise_ids}
        exercise_ids = [str(item) for item in payload.get("exercise_ids") or []]
        valid_ids = [exercise_id for exercise_id in exercise_ids if bank.get(exercise_id) is not None]
        if not valid_ids or len(valid_ids) != len(exercise_ids):
            raise ValueError("practice proposal is stale or contains missing exercises")
        session = PracticeSession(
            id=operation_id,
            exercise_ids=valid_ids,
            filters={key: str(payload.get(key) or "") for key in ("subject", "chapter", "tag", "status", "query")},
            shuffle=bool(payload.get("shuffle")),
        )
        bank.create_practice_session_once(session)
        return {"session_id": session.id, "exercise_ids": valid_ids}

    raise ValueError(f"unsupported pending action type: {action_type}")


def _reconcile_domain_projection(action: dict, data_root: str | Path) -> None:
    """Repair a stable learning event after a committed practice answer."""
    if action["type"] != "record_practice_result":
        return
    import hashlib
    from memory.exercise_bank import get_exercise_bank
    from memory.learning_events import LearningEvent, get_learning_event_store
    payload = action["payload"]
    book = payload["book_name"]
    bank = get_exercise_bank(book, str(data_root))
    session = bank.get_practice_session(payload["session_id"])
    record = bank.get(payload["exercise_id"])
    result = session.results[payload["exercise_id"]]
    stable = hashlib.sha256(f"{book}\0{session.id}\0{record.id}".encode()).hexdigest()
    get_learning_event_store(data_root).append(LearningEvent(id=f"evt_practice_{stable}",
        event_type="exercise_practiced", book_name=book, subject=record.subject,
        book_id=record.book_id, chapter_id=record.chapter or "", source_type="exercise", source_id=record.id,
        payload={"quality": result["quality"], "status": record.status, "session_id": session.id}))


_DEFAULT_STORE: PendingActionStore | None = None


def get_pending_action_store() -> PendingActionStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = PendingActionStore()
    return _DEFAULT_STORE
