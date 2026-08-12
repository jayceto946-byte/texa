"""Pure reducer for the rebuildable cross-session Learning State projection."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Iterable

from memory.learning_events import LearningEvent


LEARNING_STATE_SCHEMA_VERSION = 1


def empty_learning_state(
    learner_id: str,
    *,
    book_id: str = "",
    book_name: str = "",
    subject: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": LEARNING_STATE_SCHEMA_VERSION,
        "learner_id": learner_id,
        "book_id": book_id,
        "book_name": book_name,
        "subject": subject,
        "active_goal": {},
        "guided_progress": {
            "status": "not_started",
            "chapter_id": "",
            "chapter_name": "",
            "current_unit_id": "",
            "current_unit_name": "",
            "completed_unit_ids": [],
            "last_session_id": "",
        },
        "concept_states": {},
        "next_action": {"type": "none", "target_id": "", "reason_codes": []},
        "last_event_id": "",
        "last_activity_at": "",
        "event_count": 0,
    }


def reduce_learning_events(
    events: Iterable[LearningEvent],
    *,
    learner_id: str,
    book_id: str = "",
    book_name: str = "",
    subject: str = "",
) -> dict[str, Any]:
    state = empty_learning_state(
        learner_id, book_id=book_id, book_name=book_name, subject=subject,
    )
    for event in events:
        state = apply_learning_event(state, event)
    state["next_action"] = derive_next_action(state)
    return state


def apply_learning_event(state: dict[str, Any], event: LearningEvent) -> dict[str, Any]:
    result = deepcopy(state)
    payload = event.payload if isinstance(event.payload, dict) else {}
    result["book_id"] = event.book_id or result.get("book_id", "")
    result["book_name"] = event.book_name or result.get("book_name", "")
    result["subject"] = event.subject or result.get("subject", "")
    result["last_event_id"] = event.id
    result["last_activity_at"] = event.timestamp
    result["event_count"] = int(result.get("event_count", 0)) + 1

    event_type = event.event_type
    progress = result["guided_progress"]
    if event_type in {"goal_created", "learning_started"}:
        goal_id = str(payload.get("goal_id") or event.source_id or event.id)
        result["active_goal"] = {
            "goal_id": goal_id,
            "target_type": str(payload.get("target_type") or "chapter"),
            "target_id": str(payload.get("target_id") or event.chapter_id),
            "target_name": str(payload.get("target_name") or payload.get("chapter_name") or ""),
            "status": "active",
            "created_at": str(payload.get("created_at") or event.timestamp),
            "updated_at": event.timestamp,
        }
        progress["status"] = "in_progress"
        _apply_progress_location(progress, event, payload)
    elif event_type == "goal_paused":
        if result["active_goal"]:
            result["active_goal"]["status"] = "paused"
            result["active_goal"]["updated_at"] = event.timestamp
        progress["status"] = "paused"
        progress["last_session_id"] = event.conversation_id or progress["last_session_id"]
    elif event_type in {"goal_completed", "chapter_completed"}:
        if result["active_goal"]:
            result["active_goal"]["status"] = "completed"
            result["active_goal"]["updated_at"] = event.timestamp
        progress["status"] = "completed"
    elif event_type in {"guided_session_started", "guided_session_resumed", "unit_started"}:
        progress["status"] = "in_progress"
        _apply_progress_location(progress, event, payload)
        if result["active_goal"]:
            result["active_goal"]["status"] = "active"
            result["active_goal"]["updated_at"] = event.timestamp
    elif event_type == "unit_completed":
        unit_id = event.unit_id or str(payload.get("unit_id") or "")
        if unit_id and unit_id not in progress["completed_unit_ids"]:
            progress["completed_unit_ids"].append(unit_id)
        _apply_progress_location(progress, event, payload)

    for concept_name in event.concept_names:
        _apply_concept_evidence(result, concept_name, event)

    result["next_action"] = derive_next_action(result)
    return result


def _apply_progress_location(progress: dict[str, Any], event: LearningEvent, payload: dict) -> None:
    progress["chapter_id"] = event.chapter_id or str(payload.get("chapter_id") or progress["chapter_id"])
    progress["chapter_name"] = str(payload.get("chapter_name") or progress["chapter_name"])
    progress["current_unit_id"] = event.unit_id or str(payload.get("unit_id") or progress["current_unit_id"])
    progress["current_unit_name"] = str(payload.get("unit_name") or progress["current_unit_name"])
    progress["last_session_id"] = event.conversation_id or progress["last_session_id"]


def _concept_state(result: dict[str, Any], name: str, timestamp: str) -> dict[str, Any]:
    concepts = result["concept_states"]
    return concepts.setdefault(name, {
        "concept_id": "",
        "status": "unknown",
        "mastery_band": "unknown",
        "exposure_count": 0,
        "graded_attempt_count": 0,
        "correct_attempt_count": 0,
        "review_count": 0,
        "explicit_weak": False,
        "last_activity_at": timestamp,
        "next_review_at": "",
        "evidence_event_ids": [],
    })


def _apply_concept_evidence(result: dict[str, Any], name: str, event: LearningEvent) -> None:
    concept = _concept_state(result, name, event.timestamp)
    payload = event.payload if isinstance(event.payload, dict) else {}
    concept["concept_id"] = str(payload.get("concept_id") or concept["concept_id"])
    concept["last_activity_at"] = event.timestamp
    if event.id not in concept["evidence_event_ids"]:
        concept["evidence_event_ids"].append(event.id)
        concept["evidence_event_ids"] = concept["evidence_event_ids"][-50:]

    if event.event_type == "concept_exposure":
        concept["exposure_count"] += 1
        if concept["status"] == "unknown":
            concept["status"] = "exposed"
    if event.event_type in {"weakness_reported", "mistake_added", "exercise_to_mistake"}:
        concept["explicit_weak"] = True
        concept["status"] = "practicing"
        concept["mastery_band"] = "weak"
    if event.event_type in {"exercise_practiced", "graded_attempt"}:
        quality = _quality(payload)
        if quality is not None:
            concept["graded_attempt_count"] += 1
            concept["status"] = "practicing"
            if quality >= 3:
                concept["correct_attempt_count"] += 1
            if quality <= 2:
                concept["explicit_weak"] = True
                concept["mastery_band"] = "weak"
            elif quality >= 4 and concept["graded_attempt_count"] >= 2:
                concept["mastery_band"] = "stable"
                concept["status"] = "stable"
    if event.event_type in {"concept_reviewed", "mistake_reviewed", "review_completed"}:
        quality = _quality(payload)
        concept["review_count"] += 1
        concept["next_review_at"] = str(payload.get("next_review") or "")
        if quality is not None and quality <= 2:
            concept["explicit_weak"] = True
            concept["mastery_band"] = "weak"
            concept["status"] = "practicing"
        elif quality is not None and quality >= 5:
            concept["explicit_weak"] = False
            if concept["graded_attempt_count"] or concept["review_count"] >= 2:
                concept["mastery_band"] = "stable"
                concept["status"] = "stable"


def _quality(payload: dict[str, Any]) -> int | None:
    if "quality" not in payload:
        return None
    try:
        return max(0, min(5, int(payload["quality"])))
    except (TypeError, ValueError):
        return None


def derive_next_action(state: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    concepts = state.get("concept_states") or {}
    weak = [
        (name, value) for name, value in concepts.items()
        if isinstance(value, dict) and (value.get("explicit_weak") or value.get("mastery_band") == "weak")
    ]
    if weak:
        weak.sort(key=lambda item: str(item[1].get("last_activity_at") or ""), reverse=True)
        return {
            "type": "remediate_concept",
            "target_id": str(weak[0][1].get("concept_id") or weak[0][0]),
            "target_name": weak[0][0],
            "reason_codes": ["explicit_weakness_or_scored_failure"],
        }
    progress = state.get("guided_progress") or {}
    if progress.get("current_unit_id") or progress.get("current_unit_name"):
        return {
            "type": "resume_current_unit",
            "target_id": str(progress.get("current_unit_id") or ""),
            "target_name": str(progress.get("current_unit_name") or ""),
            "reason_codes": ["guided_progress_incomplete"],
        }
    goal = state.get("active_goal") or {}
    if goal and goal.get("status") in {"active", "paused"}:
        return {
            "type": "resume_goal",
            "target_id": str(goal.get("target_id") or ""),
            "target_name": str(goal.get("target_name") or ""),
            "reason_codes": ["active_goal"],
        }
    return {"type": "none", "target_id": "", "reason_codes": []}
