"""Persistent bounded SQLite projection of conversation state used by Resolver v2."""
from __future__ import annotations

import threading
from dataclasses import asdict
from typing import Any

from backend.services.session_context import rebuild_session_state, session_state_from_dict


LEDGER_SCHEMA_VERSION = 2
_LEDGER_LOCKS = tuple(threading.RLock() for _ in range(64))


def _ledger_lock(conversation_id: str) -> threading.RLock:
    return _LEDGER_LOCKS[hash(conversation_id) % len(_LEDGER_LOCKS)]


def _conversation_memory():
    from backend import conversation_memory

    return conversation_memory


def _conversation_exists(conversation_id: str) -> bool:
    return _conversation_memory().conversation_exists(conversation_id)


def _read_ledger(conversation_id: str) -> dict[str, Any] | None:
    value = _conversation_memory().load_session_ledger_projection(conversation_id)
    if not isinstance(value, dict) or value.get("schema_version") != LEDGER_SCHEMA_VERSION:
        return None
    return value


def _bounded_state(value: dict[str, Any]) -> dict[str, Any]:
    state = asdict(session_state_from_dict(value))
    state["entities"] = list(state.get("entities") or [])[-100:]
    state["topic_stack"] = list(state.get("topic_stack") or [])[-100:]
    state["entity_records"] = list(state.get("entity_records") or [])[-100:]
    state["entity_groups"] = list(state.get("entity_groups") or [])[-50:]
    state["assistant_artifacts"] = list(state.get("assistant_artifacts") or [])[-48:]
    return state


def _write_ledger(conversation_id: str, value: dict[str, Any]) -> None:
    if not _conversation_exists(conversation_id):
        return
    payload = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "conversation_id": conversation_id,
        "state": _bounded_state(value.get("state") or {}),
        "active_evidence": value.get("active_evidence") or {},
        "last_message_id": str(value.get("last_message_id") or "")[:100],
    }
    _conversation_memory().save_session_ledger_projection(conversation_id, payload)


def _active_evidence_projection(message: dict[str, Any]) -> dict[str, Any]:
    sources = message.get("sources") if isinstance(message.get("sources"), list) else []
    bounded = [item for item in sources[:12] if isinstance(item, dict)]
    versions = message.get("context_versions") if isinstance(message.get("context_versions"), dict) else {}
    return {
        "sources": bounded,
        "ids": [
            str(item.get("chunk_id") or "") for item in bounded if item.get("chunk_id")
        ],
        "book_id": next((str(item.get("book_id") or "") for item in bounded if item.get("book_id")), ""),
        "book_name": str(message.get("book_name") or "")[:200],
        "corpus_version": str(versions.get("corpus_version") or "")[:100],
        "scope": {
            "book_name": str(message.get("book_name") or "")[:200],
            "subject": str(message.get("subject") or "")[:100],
            "chapters": list(dict.fromkeys(
                str(item.get("chapter") or "") for item in bounded if item.get("chapter")
            ))[:12],
        },
        "support": str(message.get("evidence_support_status") or "")[:40],
        "invalidation_reason": "",
    }


def get_or_rebuild_session_ledger(
    conversation_id: str,
    recent_history: list[dict] | None = None,
) -> dict[str, Any]:
    """Return a current ledger, rebuilding only from authoritative SQLite messages."""
    with _ledger_lock(conversation_id):
        recent = [item for item in (recent_history or []) if isinstance(item, dict)]
        if not _conversation_exists(conversation_id):
            return {
                "schema_version": LEDGER_SCHEMA_VERSION,
                "conversation_id": conversation_id,
                "state": asdict(rebuild_session_state(recent, limit=5000)),
                "active_evidence": {},
                "last_message_id": str((recent[-1] if recent else {}).get("id") or ""),
                "last_seq": 0,
            }

        latest_seq, latest_message_id = _conversation_memory().latest_message_marker(conversation_id)
        existing = _read_ledger(conversation_id)
        if existing and (
            existing.get("last_message_id") == latest_message_id
            and int(existing.get("last_seq") or 0) == latest_seq
        ):
            return existing

        history = _conversation_memory().load_full_history(conversation_id)
        state = rebuild_session_state(history, limit=5000)
        latest_assistant = next((
            item for item in reversed(history) if item.get("role") == "assistant"
        ), {})
        ledger = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "conversation_id": conversation_id,
            "state": asdict(state),
            "active_evidence": _active_evidence_projection(latest_assistant),
            "last_message_id": latest_message_id,
            "last_seq": latest_seq,
        }
        _write_ledger(conversation_id, ledger)
        return _read_ledger(conversation_id) or ledger


def save_resolution_to_ledger(
    conversation_id: str,
    resolution_trace: dict[str, Any],
    user_message: dict | None,
) -> None:
    with _ledger_lock(conversation_id):
        if not _conversation_exists(conversation_id):
            return
        existing = _read_ledger(conversation_id) or {}
        _write_ledger(conversation_id, {
            **existing,
            "state": resolution_trace.get("state_after") or {},
            "last_message_id": str((user_message or {}).get("id") or ""),
        })


def record_assistant_in_ledger(
    conversation_id: str,
    assistant_message: dict | None,
) -> None:
    with _ledger_lock(conversation_id):
        if not assistant_message or not _conversation_exists(conversation_id):
            return
        existing = _read_ledger(conversation_id) or get_or_rebuild_session_ledger(conversation_id)
        state = rebuild_session_state(
            [assistant_message], limit=1, initial_state=existing.get("state") or {},
        )
        _write_ledger(conversation_id, {
            **existing,
            "state": asdict(state),
            "active_evidence": _active_evidence_projection(assistant_message),
            "last_message_id": str(assistant_message.get("id") or ""),
        })


def update_ledger_evidence_support(conversation_id: str, status: str) -> None:
    with _ledger_lock(conversation_id):
        existing = _read_ledger(conversation_id)
        if not existing:
            return
        active = dict(existing.get("active_evidence") or {})
        active["support"] = str(status or "")[:40]
        _write_ledger(conversation_id, {**existing, "active_evidence": active})


def update_ledger_evidence_invalidation(conversation_id: str, reason: str) -> None:
    with _ledger_lock(conversation_id):
        existing = _read_ledger(conversation_id)
        if not existing:
            return
        active = dict(existing.get("active_evidence") or {})
        active["invalidation_reason"] = str(reason or "")[:80]
        _write_ledger(conversation_id, {**existing, "active_evidence": active})


def invalidate_session_ledger(conversation_id: str) -> None:
    """Remove a derived ledger projection; authoritative message events remain intact."""
    with _ledger_lock(conversation_id):
        _conversation_memory().delete_session_ledger_projection(conversation_id)
