"""Versioned execution events for progressive learning-task traces.

Execution events describe observable orchestration work. They never contain
hidden model reasoning or chain-of-thought text.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


EXECUTION_EVENT_SCHEMA = "texa.execution/v1"
PERSISTED_EVENT_TYPES = {"state_transition", "tool_result", "final", "error"}
_ACTIVITY_KINDS = {"analysis", "tool", "evidence", "reasoning", "generation", "memory", "system"}


def _bounded(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _compact_payload(value: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in list((value or {}).items())[:24]:
        safe_key = _bounded(key, 80)
        if isinstance(item, str):
            result[safe_key] = item[:500]
        elif item is None or isinstance(item, (bool, int, float)):
            result[safe_key] = item
        elif isinstance(item, list):
            result[safe_key] = item[:20]
        elif isinstance(item, dict):
            result[safe_key] = dict(list(item.items())[:20])
        else:
            result[safe_key] = _bounded(item, 500)
    return result


class ExecutionEventEmitter:
    """Allocate monotonic sequence numbers and optionally persist milestones."""

    def __init__(
        self,
        *,
        request_id: str,
        task_id: str = "",
        run_id: str = "",
        conversation_id: str = "",
        turn_id: str = "",
        start_seq: int = 0,
        persist: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.request_id = request_id
        self.task_id = task_id
        self.run_id = run_id
        self.conversation_id = conversation_id
        self.turn_id = turn_id
        self.persist = persist
        self._seq = max(0, int(start_seq))
        self._started = time.perf_counter()

    def emit(
        self,
        event_type: str,
        *,
        phase: str,
        status: str,
        summary: str,
        operation_id: str = "",
        label: str = "",
        kind: str = "system",
        payload: dict[str, Any] | None = None,
        duration_ms: int | float | None = None,
    ) -> dict[str, Any]:
        self._seq += 1
        event = {
            "schema": EXECUTION_EVENT_SCHEMA,
            "seq": self._seq,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "operation_id": _bounded(operation_id or f"{phase}:{event_type}", 160),
            "type": _bounded(event_type, 40),
            "phase": _bounded(phase, 60),
            "status": _bounded(status, 30),
            "summary": _bounded(summary, 500),
            "label": _bounded(label or summary, 120),
            "kind": kind if kind in _ACTIVITY_KINDS else "system",
            "elapsed_ms": round((time.perf_counter() - self._started) * 1000, 2),
            "payload": _compact_payload(payload),
        }
        if duration_ms is not None:
            event["duration_ms"] = round(float(duration_ms), 2)
        if self.persist and event_type in PERSISTED_EVENT_TYPES:
            self.persist(event)
        return event


def legacy_activity_from_execution(event: dict[str, Any]) -> dict[str, Any]:
    """Compatibility projection for existing ChatActivity consumers."""
    raw_status = str(event.get("status") or "")
    status = {
        "started": "active",
        "running": "active",
        "completed": "completed",
        "failed": "failed",
        "skipped": "skipped",
        "cancelled": "skipped",
    }.get(raw_status, "pending")
    activity = {
        "id": str(event.get("operation_id") or f"{event.get('phase')}:{event.get('type')}"),
        "kind": str(event.get("kind") or "system"),
        "label": str(event.get("label") or event.get("summary") or "执行任务"),
        "status": status,
        "detail": str(event.get("summary") or ""),
        "seq": int(event.get("seq") or 0),
        "operation_id": str(event.get("operation_id") or ""),
        "event_type": str(event.get("type") or ""),
        "phase": str(event.get("phase") or ""),
    }
    if event.get("duration_ms") is not None:
        activity["duration_ms"] = event["duration_ms"]
    payload = event.get("payload")
    if isinstance(payload, dict) and payload:
        activity["meta"] = payload
    return activity


def execution_sse_payload(event: dict[str, Any], *, stage: str = "execution") -> dict[str, Any]:
    return {
        "stage": stage,
        "execution_event": event,
        "activity": legacy_activity_from_execution(event),
        "request_id": event.get("request_id"),
        "conversation_id": event.get("conversation_id"),
        "turn_id": event.get("turn_id"),
        "elapsed_ms": event.get("elapsed_ms"),
    }
