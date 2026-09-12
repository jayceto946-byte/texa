"""Bounded model exploration independent of the producer's lifecycle state."""
from itertools import product

import pytest

from backend.services.execution_events import ExecutionEventEmitter, validate_execution_event_sequence


def event_for(action, seq):
    kind, status, payload = {
        "append": ("output_delta", "running", {"text": "a", "replace": False}),
        "replace": ("output_delta", "running", {"text": "b", "replace": True}),
        "progress": ("progress", "running", {}),
        "gate": ("state_transition", "completed", {"task_status_before": "running", "task_status_after": "waiting_for_input"}),
        "final": ("final", "completed", {"task_status": "degraded"}),
        "error": ("error", "failed", {"task_status": "failed"}),
    }[action]
    return {"schema": "texa.execution/v1", "request_id": "request", "task_id": "task", "run_id": "run",
            "conversation_id": "conversation", "turn_id": "turn", "seq": seq, "operation_id": "answer",
            "type": kind, "phase": "generation", "status": status, "summary": "summary", "label": "answer",
            "kind": "system", "elapsed_ms": 0, "payload": payload}


def test_runtime_and_sequence_validator_match_bounded_run_model():
    for actions in product(("append", "replace", "progress", "gate", "final", "error"), repeat=4):
        emitter = ExecutionEventEmitter(request_id="request", task_id="task", run_id="run", conversation_id="conversation", turn_id="turn")
        closed = False
        accepted = []
        for seq, action in enumerate(actions, 1):
            event = event_for(action, seq)
            kwargs = {key: event[key] for key in ("phase", "status", "summary", "label", "kind", "payload")}
            if closed:
                with pytest.raises(ValueError):
                    emitter.emit(event["type"], **kwargs)
                with pytest.raises(ValueError):
                    validate_execution_event_sequence([*accepted, event])
            else:
                emitter.emit(event["type"], **kwargs)
                accepted.append(event)
                validate_execution_event_sequence(accepted)
            closed |= action in {"gate", "final", "error"}


@pytest.mark.parametrize("field", ["request_id", "task_id", "run_id", "conversation_id", "turn_id"])
def test_identity_cannot_drift_even_in_sparse_milestones(field):
    first, second = event_for("progress", 2), event_for("final", 900)
    validate_execution_event_sequence([first, second])
    second[field] = "other"
    with pytest.raises(ValueError, match="identit|task runs"):
        validate_execution_event_sequence([first, second])


def test_failed_persistence_does_not_consume_sequence_or_close_emitter():
    attempts = []
    def persist(event):
        attempts.append(event)
        if len(attempts) == 1:
            raise OSError("atomic write failed")
    emitter = ExecutionEventEmitter(request_id="request", persist=persist)
    with pytest.raises(OSError):
        emitter.emit("final", phase="final", status="completed", summary="done")
    final = emitter.emit("final", phase="final", status="completed", summary="done")
    assert [e["seq"] for e in attempts] == [1, 1]
    assert final["seq"] == 1
