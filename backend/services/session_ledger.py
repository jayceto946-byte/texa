"""Persistent bounded projection of conversation state used by Resolver v2."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backend.services.session_context import rebuild_session_state, session_state_from_dict
from utils.json_io import atomic_write_json


LEDGER_SCHEMA_VERSION = 1
_LEDGER_LOCKS = tuple(threading.RLock() for _ in range(64))


def _ledger_lock(conversation_id: str) -> threading.RLock:
    return _LEDGER_LOCKS[hash(conversation_id) % len(_LEDGER_LOCKS)]


def _conversation_memory():
    from backend import conversation_memory

    return conversation_memory


def _ledger_dir() -> Path:
    path = Path(_conversation_memory().CONV_DIR) / "_session_ledgers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ledger_path(conversation_id: str) -> Path:
    return _ledger_dir() / f"{conversation_id}.json"


def _conversation_exists(conversation_id: str) -> bool:
    return _conversation_memory().conversation_exists(conversation_id)


def _read_ledger(conversation_id: str) -> dict[str, Any] | None:
    path = _ledger_path(conversation_id)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
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
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    atomic_write_json(_ledger_path(conversation_id), payload)


def get_or_rebuild_session_ledger(
    conversation_id: str,
    recent_history: list[dict] | None = None,
) -> dict[str, Any]:
    """Return a current ledger, rebuilding from the event projection only when stale."""
    with _ledger_lock(conversation_id):
        recent = [item for item in (recent_history or []) if isinstance(item, dict)]
        if not _conversation_exists(conversation_id):
            return {
                "schema_version": LEDGER_SCHEMA_VERSION,
                "conversation_id": conversation_id,
                "state": asdict(rebuild_session_state(recent, limit=5000)),
                "active_evidence": {},
                "last_message_id": str((recent[-1] if recent else {}).get("id") or ""),
            }
        latest_message_id = str((recent[-1] if recent else {}).get("id") or "")
        existing = _read_ledger(conversation_id)
        if existing and (
            not latest_message_id or existing.get("last_message_id") == latest_message_id
        ):
            return existing

        history = _conversation_memory().load_full_history(conversation_id)
        state = rebuild_session_state(history, limit=5000)
        latest = str((history[-1] if history else {}).get("id") or "")
        latest_assistant = next((
            item for item in reversed(history) if item.get("role") == "assistant"
        ), {})
        sources = latest_assistant.get("sources") if isinstance(latest_assistant.get("sources"), list) else []
        ledger = {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "conversation_id": conversation_id,
            "state": asdict(state),
            "active_evidence": {
                "sources": sources[:12],
                "ids": [
                    str(item.get("chunk_id") or "") for item in sources[:12]
                    if isinstance(item, dict) and item.get("chunk_id")
                ],
                "support": str(latest_assistant.get("evidence_support_status") or ""),
            },
            "last_message_id": latest,
        }
        _write_ledger(conversation_id, ledger)
        return ledger


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
        sources = assistant_message.get("sources") if isinstance(assistant_message.get("sources"), list) else []
        _write_ledger(conversation_id, {
            **existing,
            "state": asdict(state),
            "active_evidence": {
                "sources": sources[:12],
                "ids": [
                    str(item.get("chunk_id") or "") for item in sources[:12]
                    if isinstance(item, dict) and item.get("chunk_id")
                ],
                "support": str(assistant_message.get("evidence_support_status") or ""),
            },
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


def invalidate_session_ledger(conversation_id: str) -> None:
    """Remove a derived projection after split/reclassification; raw events remain intact."""
    with _ledger_lock(conversation_id):
        _ledger_path(conversation_id).unlink(missing_ok=True)
