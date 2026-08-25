"""Durable confirmation boundary for learner-state mutations proposed by tools."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from config import PROGRESS_PATH
from utils.json_io import atomic_write_json


_ACTION_LOCK = threading.RLock()
_ALLOWED_TYPES = {"add_mistake", "mark_concept_reviewed", "create_practice_session"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class PendingActionStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or PROGRESS_PATH) / "pending_actions"

    def _path(self, action_id: str) -> Path:
        if not action_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in action_id):
            raise ValueError("invalid pending action id")
        return self.root / f"{action_id}.json"

    def create(self, proposal: dict[str, Any], *, context: dict[str, str]) -> dict[str, Any]:
        action_type = str(proposal.get("type") or "")
        if action_type not in _ALLOWED_TYPES:
            raise ValueError(f"unsupported pending action type: {action_type}")
        action = {
            "action_id": f"action_{uuid.uuid4().hex}",
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

    def reject(self, action_id: str) -> dict[str, Any]:
        with _ACTION_LOCK:
            action = self.get(action_id)
            if action is None:
                raise KeyError(action_id)
            if action.get("status") == "confirmed":
                raise ValueError("confirmed action cannot be rejected")
            if action.get("status") == "rejected":
                return action
            action["status"] = "rejected"
            action["result"] = {"rejected": True}
            return self.save(action)

    def confirm(self, action_id: str) -> dict[str, Any]:
        with _ACTION_LOCK:
            action = self.get(action_id)
            if action is None:
                raise KeyError(action_id)
            if action.get("status") == "confirmed":
                return action
            if action.get("status") == "rejected":
                raise ValueError("rejected action cannot be confirmed")
            try:
                action["result"] = _execute(action)
                action["status"] = "confirmed"
                action["error"] = ""
            except Exception as exc:
                action["status"] = "failed"
                action["error"] = str(exc)[:500]
                self.save(action)
                raise
            return self.save(action)


def _execute(action: dict[str, Any]) -> dict[str, Any]:
    action_type = str(action.get("type") or "")
    payload = dict(action.get("payload") or {})
    context = dict(action.get("context") or {})
    book_name = str(payload.get("book_name") or context.get("book_name") or "default")

    if action_type == "add_mistake":
        from memory.mistake_book import MistakeRecord, get_mistake_book

        tags = payload.get("tags") or []
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.replace("，", ",").split(",") if item.strip()]
        record = MistakeRecord(
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
        record_id = get_mistake_book(book_name, str(PROGRESS_PATH)).add(record)
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
        )
        return {"concept": result}

    if action_type == "create_practice_session":
        from memory.exercise_bank import PracticeSession, get_exercise_bank

        bank = get_exercise_bank(book_name, str(PROGRESS_PATH))
        exercise_ids = [str(item) for item in payload.get("exercise_ids") or []]
        valid_ids = [exercise_id for exercise_id in exercise_ids if bank.get(exercise_id) is not None]
        if not valid_ids or len(valid_ids) != len(exercise_ids):
            raise ValueError("practice proposal is stale or contains missing exercises")
        previous = bank.get_active_practice_session()
        if previous:
            previous.status = "replaced"
            previous.completed_at = _now()
            bank.save_practice_session(previous)
        session = PracticeSession(
            exercise_ids=valid_ids,
            filters={key: str(payload.get(key) or "") for key in ("subject", "chapter", "tag", "status", "query")},
            shuffle=bool(payload.get("shuffle")),
        )
        bank.save_practice_session(session)
        return {"session_id": session.id, "exercise_ids": valid_ids}

    raise ValueError(f"unsupported pending action type: {action_type}")


_DEFAULT_STORE: PendingActionStore | None = None


def get_pending_action_store() -> PendingActionStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = PendingActionStore()
    return _DEFAULT_STORE
