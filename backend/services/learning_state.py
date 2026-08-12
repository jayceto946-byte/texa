"""Application service for validated Learning State events and projections."""
from __future__ import annotations

import re
import threading
import json
from pathlib import Path
from typing import Any

import config
from memory.learning_events import LearningEvent, LearningEventStore, get_learning_event_store
from utils.book_registry import BookRegistry
from utils.json_io import atomic_write_json
from utils.path_safety import safe_book_name, safe_child_path

from backend.services.learning_state_reducer import (
    LEARNING_STATE_SCHEMA_VERSION,
    reduce_learning_events,
)


DEFAULT_LEARNER_ID = "local_default"
_PROJECTION_LOCKS = tuple(threading.RLock() for _ in range(64))
_ALLOWED_OPERATIONS = {
    "create_goal": "goal_created",
    "start_learning": "learning_started",
    "pause_learning": "goal_paused",
    "resume_learning": "guided_session_resumed",
    "start_unit": "unit_started",
    "complete_unit": "unit_completed",
    "complete_goal": "goal_completed",
    "record_weakness": "weakness_reported",
    "record_attempt": "graded_attempt",
    "record_review": "review_completed",
}


def _clean_identifier(value: str, default: str = "") -> str:
    clean = " ".join(str(value or "").strip().split())[:160]
    return clean or default


def resolve_book_identity(book_name: str, *, progress_root: str | Path | None = None) -> dict[str, str]:
    name = _clean_identifier(book_name)
    if not name:
        return {"book_id": "", "book_name": ""}
    try:
        record = BookRegistry(progress_root or config.PROGRESS_PATH).resolve(name)
    except Exception:
        record = None
    return {
        "book_id": str((record or {}).get("book_id") or ""),
        "book_name": str((record or {}).get("storage_name") or safe_book_name(name)),
    }


def resolve_chapter_identity(
    book_name: str,
    chapter_reference: str,
    *,
    progress_root: str | Path | None = None,
) -> dict[str, str]:
    """Resolve a chapter name/number to the stable chapter_### identity used by textbook artifacts."""
    reference = _clean_identifier(chapter_reference)
    if not reference:
        return {"chapter_id": "", "chapter_name": ""}
    root = Path(progress_root or config.PROGRESS_PATH)
    path = safe_child_path(root, safe_book_name(book_name), "_chapters.json")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = []
    compact = re.sub(r"\s+", "", reference)
    for index, item in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        title = _clean_identifier(item.get("title", ""))
        if compact and (compact == re.sub(r"\s+", "", title) or compact in re.sub(r"\s+", "", title)):
            return {"chapter_id": f"chapter_{index + 1:03d}", "chapter_name": title}
    return {"chapter_id": "", "chapter_name": reference}


class LearningStateService:
    def __init__(
        self,
        *,
        progress_root: str | Path | None = None,
        event_store: LearningEventStore | None = None,
    ) -> None:
        self.progress_root = Path(progress_root or config.PROGRESS_PATH)
        self.event_store = event_store or get_learning_event_store(self.progress_root)

    def get_state(
        self,
        *,
        learner_id: str = DEFAULT_LEARNER_ID,
        book_id: str = "",
        book_name: str = "",
        subject: str = "",
    ) -> dict[str, Any]:
        learner = _clean_identifier(learner_id, DEFAULT_LEARNER_ID)
        identity = resolve_book_identity(book_name, progress_root=self.progress_root)
        resolved_book_id = _clean_identifier(book_id or identity["book_id"])
        resolved_book_name = identity["book_name"] or _clean_identifier(book_name)
        events = self.event_store.list_for_state(
            learner_id=learner,
            book_id=resolved_book_id,
            book_name=resolved_book_name,
        )
        state = reduce_learning_events(
            events,
            learner_id=learner,
            book_id=resolved_book_id,
            book_name=resolved_book_name,
            subject=subject,
        )
        self._write_projection(state)
        return state

    def list_resumable(
        self,
        *,
        learner_id: str = DEFAULT_LEARNER_ID,
        book_name: str = "",
        subject: str = "",
    ) -> list[dict[str, Any]]:
        if book_name:
            states = [self.get_state(learner_id=learner_id, book_name=book_name, subject=subject)]
        else:
            scopes: dict[str, str] = {}
            for event in self.event_store.list_recent(learner_id=learner_id, limit=5000):
                if event.book_id or event.book_name:
                    scopes[event.book_id or f"name:{event.book_name}"] = event.book_name
            states = [
                self.get_state(
                    learner_id=learner_id,
                    book_id="" if key.startswith("name:") else key,
                    book_name=name,
                    subject=subject,
                )
                for key, name in scopes.items()
            ]
        return sorted(
            [state for state in states if _is_resumable(state)],
            key=lambda state: str(state.get("last_activity_at") or ""),
            reverse=True,
        )

    def list_reviewable(
        self,
        *,
        learner_id: str = DEFAULT_LEARNER_ID,
        book_name: str = "",
        subject: str = "",
    ) -> list[dict[str, Any]]:
        states = self.list_resumable(
            learner_id=learner_id, book_name=book_name, subject=subject,
        )
        if book_name:
            current = self.get_state(learner_id=learner_id, book_name=book_name, subject=subject)
            if current not in states:
                states.append(current)
        else:
            scopes: dict[str, str] = {}
            for event in self.event_store.list_recent(learner_id=learner_id, limit=5000):
                if event.book_id or event.book_name:
                    scopes[event.book_id or f"name:{event.book_name}"] = event.book_name
            for key, name in scopes.items():
                current = self.get_state(
                    learner_id=learner_id,
                    book_id="" if key.startswith("name:") else key,
                    book_name=name,
                    subject=subject,
                )
                if current not in states:
                    states.append(current)
        return sorted(
            [
                state for state in states
                if str((state.get("next_action") or {}).get("type") or "") == "remediate_concept"
            ],
            key=lambda state: str(state.get("last_activity_at") or ""),
            reverse=True,
        )

    def apply_operation(
        self,
        operation: dict[str, Any],
        *,
        learner_id: str = DEFAULT_LEARNER_ID,
        book_name: str = "",
        subject: str = "",
        conversation_id: str = "",
        source_id: str = "",
    ) -> dict[str, Any]:
        op = str(operation.get("operation") or "")
        if op not in _ALLOWED_OPERATIONS:
            raise ValueError(f"unsupported learning operation: {op}")
        identity = resolve_book_identity(book_name, progress_root=self.progress_root)
        resolved_book_name = identity["book_name"] or _clean_identifier(book_name)
        if not resolved_book_name:
            raise ValueError("book_name is required for a learning operation")
        chapter_id = _clean_identifier(operation.get("chapter_id", ""))
        unit_id = _clean_identifier(operation.get("unit_id", ""))
        concepts = _validated_concepts(operation)
        if op == "record_weakness" and not concepts:
            raise ValueError("record_weakness requires validated concept_names")
        if op in {"record_attempt", "record_review"}:
            quality = operation.get("quality")
            if not isinstance(quality, int) or not 0 <= quality <= 5:
                raise ValueError(f"{op} requires quality 0-5")
        payload = {
            key: value for key, value in operation.items()
            if key not in {"operation", "concept_names"} and _safe_payload_value(value)
        }
        event = LearningEvent(
            event_type=_ALLOWED_OPERATIONS[op],
            learner_id=_clean_identifier(learner_id, DEFAULT_LEARNER_ID),
            book_id=identity["book_id"],
            book_name=resolved_book_name,
            chapter_id=chapter_id,
            unit_id=unit_id,
            subject=subject,
            conversation_id=_clean_identifier(conversation_id),
            source_type="conversation" if conversation_id else "learning_state",
            source_id=_clean_identifier(source_id or conversation_id),
            concept_names=concepts,
            payload=payload,
        )
        self.event_store.append(event)
        return self.get_state(
            learner_id=learner_id,
            book_id=identity["book_id"],
            book_name=resolved_book_name,
            subject=subject,
        )

    def learning_context_pack(self, state: dict[str, Any]) -> dict[str, Any]:
        progress = state.get("guided_progress") or {}
        next_action = state.get("next_action") or {}
        relevant_name = str(next_action.get("target_name") or progress.get("current_unit_name") or "")
        concept = (state.get("concept_states") or {}).get(relevant_name, {})
        return {
            "learner_id": str(state.get("learner_id") or ""),
            "book_id": str(state.get("book_id") or ""),
            "book_name": str(state.get("book_name") or ""),
            "subject": str(state.get("subject") or ""),
            "goal": dict(state.get("active_goal") or {}),
            "current_progress": dict(progress),
            "relevant_concept_states": (
                [{"name": relevant_name, **dict(concept)}] if relevant_name and concept else []
            ),
            "next_action": dict(next_action),
            "state_version": int(state.get("event_count") or 0),
        }

    def _write_projection(self, state: dict[str, Any]) -> None:
        learner = safe_book_name(str(state.get("learner_id") or DEFAULT_LEARNER_ID), DEFAULT_LEARNER_ID)
        scope = safe_book_name(str(state.get("book_id") or state.get("book_name") or "default"), "default")
        path = safe_child_path(self.progress_root, "learning_states", learner, f"{scope}.json")
        lock = _PROJECTION_LOCKS[hash(str(path)) % len(_PROJECTION_LOCKS)]
        with lock:
            atomic_write_json(path, state)


def _validated_concepts(operation: dict[str, Any]) -> list[str]:
    raw = operation.get("concept_names")
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for value in raw:
        name = _clean_identifier(value)
        if 2 <= len(name) <= 100 and re.search(r"[\w\u4e00-\u9fff]", name) and name not in result:
            result.append(name)
    return result[:20]


def _safe_payload_value(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, str):
        return len(value) <= 500
    return isinstance(value, list) and len(value) <= 20 and all(isinstance(item, str) for item in value)


def _is_resumable(state: dict[str, Any]) -> bool:
    goal_status = str((state.get("active_goal") or {}).get("status") or "")
    progress_status = str((state.get("guided_progress") or {}).get("status") or "")
    return goal_status in {"active", "paused"} or progress_status in {"in_progress", "paused"}
