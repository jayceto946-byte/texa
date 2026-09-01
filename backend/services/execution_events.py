"""Versioned execution events for progressive learning-task traces.

Execution events describe observable orchestration work. They never contain
hidden model reasoning or chain-of-thought text.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


EXECUTION_EVENT_V1_CONTRACT = {
    "schema": "texa.execution/v1",
    "identity_fields": (
        "schema", "request_id", "task_id", "run_id", "conversation_id", "turn_id", "seq",
    ),
    "types": frozenset({
        "progress", "state_transition", "tool_result", "output_delta", "final", "error",
    }),
    "terminal_types": frozenset({"final", "error"}),
    "persisted_types": frozenset({"state_transition", "tool_result", "final", "error"}),
    "statuses": frozenset({"started", "running", "completed", "failed", "skipped", "cancelled"}),
    "activity_kinds": frozenset({
        "analysis", "tool", "evidence", "reasoning", "generation", "memory", "system",
    }),
    "output_delta_payload_fields": frozenset({"text", "replace"}),
    "reasoning_visibility": "public_summary_only",
}
EXECUTION_EVENT_SCHEMA = EXECUTION_EVENT_V1_CONTRACT["schema"]
EXECUTION_EVENT_IDENTITY_FIELDS = EXECUTION_EVENT_V1_CONTRACT["identity_fields"]
EXECUTION_EVENT_TYPES = EXECUTION_EVENT_V1_CONTRACT["types"]
EXECUTION_EVENT_TERMINAL_TYPES = EXECUTION_EVENT_V1_CONTRACT["terminal_types"]
PERSISTED_EVENT_TYPES = EXECUTION_EVENT_V1_CONTRACT["persisted_types"]
_EVENT_STATUSES = EXECUTION_EVENT_V1_CONTRACT["statuses"]
_ACTIVITY_KINDS = EXECUTION_EVENT_V1_CONTRACT["activity_kinds"]
_OUTPUT_DELTA_PAYLOAD_FIELDS = EXECUTION_EVENT_V1_CONTRACT["output_delta_payload_fields"]
_REQUIRED_EVENT_FIELDS = frozenset({
    *EXECUTION_EVENT_IDENTITY_FIELDS,
    "operation_id", "type", "phase", "status", "summary", "label", "kind",
    "elapsed_ms", "payload",
})
_OPTIONAL_EVENT_FIELDS = frozenset({"duration_ms"})
_PRIVATE_REASONING_KEYS = frozenset({
    "chain_of_thought", "chainofthought", "cot", "hidden_reasoning", "reasoning", "thinking",
})
EXECUTION_SSE_FORBIDDEN_LIFECYCLE_FIELDS = frozenset({
    *_REQUIRED_EVENT_FIELDS,
    *_OPTIONAL_EVENT_FIELDS,
    "activity",
    "chunk",
    "done",
    "error",
    "error_code",
    "http_status",
    "message",
    "replace",
    "stage",
    "terminal",
})


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


def _contains_private_reasoning(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_").replace(" ", "_")
            if normalized_key in _PRIVATE_REASONING_KEYS or _contains_private_reasoning(item):
                return True
    elif isinstance(value, list):
        return any(_contains_private_reasoning(item) for item in value)
    return False


def _validate_task_state_payload(event_type: str, payload: dict[str, Any]) -> None:
    before = payload.get("task_status_before")
    after = payload.get("task_status_after")
    snapshot = payload.get("task_status")
    if "task_status_before" in payload or "task_status_after" in payload:
        if event_type != "state_transition" or not isinstance(before, str) or not isinstance(after, str):
            raise ValueError(
                "task_status_before/task_status_after require a state_transition event and string values"
            )
        from backend.services.learning_task import validate_learning_task_transition

        validate_learning_task_transition(before, after)
    if "task_status" in payload:
        if not isinstance(snapshot, str):
            raise ValueError("task_status must be a string")
        from backend.services.learning_task import validate_learning_task_status

        validate_learning_task_status(snapshot)


def validate_execution_event(
    event: dict[str, Any],
    *,
    expected_task_id: str | None = None,
    expected_run_id: str | None = None,
    expected_conversation_id: str | None = None,
    expected_turn_id: str | None = None,
    previous_seq: int | None = None,
    require_persisted_identity: bool = False,
) -> dict[str, Any]:
    """Validate one canonical ``texa.execution/v1`` event without adapting it."""
    if not isinstance(event, dict):
        raise ValueError("execution event must be an object")
    missing = _REQUIRED_EVENT_FIELDS - event.keys()
    if missing:
        raise ValueError(f"execution event missing fields: {', '.join(sorted(missing))}")
    unexpected = event.keys() - _REQUIRED_EVENT_FIELDS - _OPTIONAL_EVENT_FIELDS
    if unexpected:
        raise ValueError(f"execution event has unexpected fields: {', '.join(sorted(unexpected))}")
    if event["schema"] != EXECUTION_EVENT_SCHEMA:
        raise ValueError(f"invalid execution event schema: {event['schema']}")

    for field in ("request_id", "task_id", "run_id", "conversation_id", "turn_id"):
        if not isinstance(event[field], str):
            raise ValueError(f"execution event {field} must be a string")
    if not event["request_id"]:
        raise ValueError("execution event request_id is required")
    if bool(event["task_id"]) != bool(event["run_id"]):
        raise ValueError("execution event task_id and run_id must both be present or both be empty")
    if expected_task_id is not None and event["task_id"] != expected_task_id:
        raise ValueError("execution event task_id does not match the active task")
    if expected_run_id is not None and event["run_id"] != expected_run_id:
        raise ValueError("execution event run_id does not match the active run")
    if expected_conversation_id is not None and event["conversation_id"] != expected_conversation_id:
        raise ValueError("execution event conversation_id does not match the active task")
    if expected_turn_id is not None and event["turn_id"] != expected_turn_id:
        raise ValueError("execution event turn_id does not match the active task")

    seq = event["seq"]
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        raise ValueError("execution event seq must be a positive integer")
    if previous_seq is not None and seq <= previous_seq:
        raise ValueError("execution event seq must increase within a task run")

    event_type = event["type"]
    if event_type not in EXECUTION_EVENT_TYPES:
        raise ValueError(f"invalid execution event type: {event_type}")
    if require_persisted_identity:
        if event_type not in PERSISTED_EVENT_TYPES:
            raise ValueError(f"execution event type is not a persisted milestone: {event_type}")
        missing_identity = [
            field for field in ("request_id", "task_id", "run_id", "conversation_id", "turn_id")
            if not event[field]
        ]
        if missing_identity:
            raise ValueError(
                f"persisted execution event missing identity: {', '.join(missing_identity)}"
            )
    if event["status"] not in _EVENT_STATUSES:
        raise ValueError(f"invalid execution event status: {event['status']}")
    for field in ("operation_id", "phase", "summary", "label", "kind"):
        if not isinstance(event[field], str):
            raise ValueError(f"execution event {field} must be a string")
    if event["kind"] not in _ACTIVITY_KINDS:
        raise ValueError(f"invalid execution event kind: {event['kind']}")
    if not isinstance(event["elapsed_ms"], (int, float)) or event["elapsed_ms"] < 0:
        raise ValueError("execution event elapsed_ms must be non-negative")
    if "duration_ms" in event and (
        not isinstance(event["duration_ms"], (int, float)) or event["duration_ms"] < 0
    ):
        raise ValueError("execution event duration_ms must be non-negative")

    payload = event["payload"]
    if not isinstance(payload, dict):
        raise ValueError("execution event payload must be an object")
    if event_type == "output_delta":
        if set(payload) != _OUTPUT_DELTA_PAYLOAD_FIELDS:
            raise ValueError("output_delta payload must contain exactly text and replace")
        if not isinstance(payload["text"], str) or not isinstance(payload["replace"], bool):
            raise ValueError("output_delta payload requires string text and boolean replace")
    if _contains_private_reasoning(payload):
        raise ValueError("execution event payload must not expose private reasoning")
    _validate_task_state_payload(event_type, payload)
    return event


def validate_execution_event_sequence(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate monotonic order and a single terminal event for one task/run."""
    identity: tuple[str, str] | None = None
    previous_seq: int | None = None
    terminal_seen = False
    for event in events:
        validate_execution_event(event, previous_seq=previous_seq)
        current_identity = (event["task_id"], event["run_id"])
        if not all(current_identity):
            raise ValueError("execution event sequence requires task_id and run_id")
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise ValueError("execution event sequence cannot mix task runs")
        if terminal_seen:
            raise ValueError("execution events cannot follow final or error")
        if event["type"] in EXECUTION_EVENT_TERMINAL_TYPES:
            terminal_seen = True
        previous_seq = event["seq"]
    return events


def should_persist_execution_event(event: dict[str, Any]) -> bool:
    """Persist milestones only; progress and output deltas remain transport-only."""
    return event.get("type") in PERSISTED_EVENT_TYPES


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
        self._terminal_emitted = False

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
        if self._terminal_emitted:
            raise ValueError("execution events cannot follow final or error")
        next_seq = self._seq + 1
        event = {
            "schema": EXECUTION_EVENT_SCHEMA,
            "seq": next_seq,
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
            "payload": dict(payload or {}) if event_type == "output_delta" else _compact_payload(payload),
        }
        if duration_ms is not None:
            event["duration_ms"] = round(float(duration_ms), 2)
        validate_execution_event(
            event,
            previous_seq=self._seq if self._seq else None,
        )
        self._seq = next_seq
        if self.persist and event_type in PERSISTED_EVENT_TYPES:
            self.persist(event)
        if event_type in EXECUTION_EVENT_TERMINAL_TYPES:
            self._terminal_emitted = True
        return event


def execution_sse_payload(
    event: dict[str, Any],
    *,
    sidecar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap one canonical event plus domain-only sidecar data."""
    validate_execution_event(event)
    domain_sidecar = dict(sidecar or {})
    forbidden = EXECUTION_SSE_FORBIDDEN_LIFECYCLE_FIELDS.intersection(domain_sidecar)
    if forbidden:
        raise ValueError(
            "execution SSE sidecar contains lifecycle fields: "
            + ", ".join(sorted(forbidden))
        )
    return {"execution_event": event, **domain_sidecar}
