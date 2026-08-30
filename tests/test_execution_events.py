import threading

import pytest

from backend.services.execution_events import (
    EXECUTION_EVENT_SCHEMA,
    EXECUTION_EVENT_V1_CONTRACT,
    ExecutionEventEmitter,
    validate_execution_event,
    validate_execution_event_sequence,
)
from backend.services.learning_task import LearningTaskStore
from backend.services.tool_orchestration import ToolOrchestrationRequest, execute_read_only_tools
from graph.main_graph import _iterate_stream_with_progress, _run_blocking_with_progress


def test_execution_emitter_sequences_events_and_persists_only_milestones(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="chat",
        goal="test progressive trace",
        conversation_id="conversation-1",
        turn_id="turn-1",
        artifacts={"active_run_id": "run-1"},
    )
    emitter = ExecutionEventEmitter(
        request_id="request-1",
        task_id=task.id,
        run_id="run-1",
        conversation_id="conversation-1",
        turn_id="turn-1",
        persist=lambda event: store.append_execution_event_for_run(task.id, "run-1", event),
    )

    emitted = [
        emitter.emit("progress", phase="planning", status="running", summary="waiting"),
        emitter.emit("state_transition", phase="planning", status="completed", summary="planned"),
        emitter.emit("tool_result", phase="tool", status="completed", summary="returned"),
        emitter.emit(
            "output_delta",
            phase="generation",
            status="running",
            summary="visible answer text",
            payload={"text": "answer", "replace": False},
        ),
    ]
    current = store.get(task.id)
    store.checkpoint(current, "verified", status="completed")
    emitted.append(emitter.emit(
        "final", phase="final", status="completed", summary="done",
        payload={"task_status": "completed"},
    ))

    assert [event["seq"] for event in emitted] == [1, 2, 3, 4, 5]
    validate_execution_event_sequence(emitted)
    stored = store.get(task.id)
    assert stored is not None
    assert [event["type"] for event in stored.artifacts["execution_events"]] == [
        "state_transition", "tool_result", "final",
    ]
    for event in stored.artifacts["execution_events"]:
        assert {
            key: event[key]
            for key in (
                "schema", "request_id", "task_id", "run_id", "conversation_id", "turn_id",
            )
        } == {
            "schema": EXECUTION_EVENT_SCHEMA,
            "request_id": "request-1",
            "task_id": task.id,
            "run_id": "run-1",
            "conversation_id": "conversation-1",
            "turn_id": "turn-1",
        }


def test_execution_event_v1_contract_is_frozen():
    assert EXECUTION_EVENT_V1_CONTRACT == {
        "schema": "texa.execution/v1",
        "identity_fields": (
            "schema", "request_id", "task_id", "run_id", "conversation_id", "turn_id", "seq",
        ),
        "types": frozenset({
            "progress", "state_transition", "tool_result", "output_delta", "final", "error",
        }),
        "terminal_types": frozenset({"final", "error"}),
        "persisted_types": frozenset({"state_transition", "tool_result", "final", "error"}),
        "statuses": frozenset({
            "started", "running", "completed", "failed", "skipped", "cancelled",
        }),
        "activity_kinds": frozenset({
            "analysis", "tool", "evidence", "reasoning", "generation", "memory", "system",
        }),
        "output_delta_payload_fields": frozenset({"text", "replace"}),
        "reasoning_visibility": "public_summary_only",
    }


def _event(*, event_type="progress", run_id="run-1", start_seq=0, payload=None):
    emitter = ExecutionEventEmitter(
        request_id="request-1",
        task_id="task-1",
        run_id=run_id,
        conversation_id="conversation-1",
        turn_id="turn-1",
        start_seq=start_seq,
    )
    return emitter.emit(
        event_type,
        phase="generation" if event_type == "output_delta" else "orchestration",
        status="failed" if event_type == "error" else "running",
        summary="public summary",
        kind="reasoning",
        payload=payload,
    )


def test_execution_event_v1_rejects_wrong_schema_and_noncanonical_type():
    wrong_schema = _event()
    wrong_schema["schema"] = "texa.execution/v0"
    with pytest.raises(ValueError, match="schema"):
        validate_execution_event(wrong_schema)

    tool_call = _event()
    tool_call["type"] = "tool_call"
    with pytest.raises(ValueError, match="event type"):
        validate_execution_event(tool_call)

    heartbeat = _event()
    heartbeat["type"] = "heartbeat"
    with pytest.raises(ValueError, match="event type"):
        validate_execution_event(heartbeat)


def test_emitter_validates_canonical_event_before_returning_or_persisting():
    persisted = []
    emitter = ExecutionEventEmitter(
        request_id="request-1",
        task_id="task-1",
        run_id="run-1",
        conversation_id="conversation-1",
        turn_id="turn-1",
        persist=persisted.append,
    )

    with pytest.raises(ValueError, match="event type"):
        emitter.emit(
            "tool_call", phase="tool", status="started", summary="internal call",
        )
    with pytest.raises(ValueError, match="output_delta payload"):
        emitter.emit(
            "output_delta", phase="generation", status="running", summary="invalid delta",
            payload={"activity": "generating"},
        )

    valid = emitter.emit(
        "state_transition", phase="planning", status="completed", summary="planned",
    )
    assert valid["seq"] == 1
    assert persisted == [valid]


@pytest.mark.parametrize("payload", [
    {},
    {"text": "answer"},
    {"text": "answer", "replace": 0},
    {"text": "answer", "replace": False, "extra": True},
])
def test_output_delta_requires_exact_text_replace_payload(payload):
    event = _event()
    event["type"] = "output_delta"
    event["payload"] = payload
    with pytest.raises(ValueError, match="output_delta payload"):
        validate_execution_event(event)

    valid = _event(
        event_type="output_delta",
        payload={"text": "visible answer", "replace": True},
    )
    assert validate_execution_event(valid) is valid


def test_sequence_is_monotonic_for_one_run_and_has_one_terminal_event():
    emitter = ExecutionEventEmitter(
        request_id="request-1",
        task_id="task-1",
        run_id="run-1",
        conversation_id="conversation-1",
        turn_id="turn-1",
    )
    events = [
        emitter.emit("progress", phase="planning", status="running", summary="planning"),
        emitter.emit("final", phase="final", status="completed", summary="done"),
    ]
    assert validate_execution_event_sequence(events) == events

    with pytest.raises(ValueError, match="cannot follow"):
        emitter.emit("error", phase="error", status="failed", summary="late error")

    out_of_order = [dict(events[0]), dict(events[1])]
    out_of_order[1]["seq"] = out_of_order[0]["seq"]
    with pytest.raises(ValueError, match="seq must increase"):
        validate_execution_event_sequence(out_of_order)

    mixed_run = [events[0], _event(run_id="run-2", start_seq=1)]
    with pytest.raises(ValueError, match="cannot mix task runs"):
        validate_execution_event_sequence(mixed_run)


def test_stale_or_mismatched_run_event_cannot_persist(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="chat",
        goal="test stale event",
        conversation_id="conversation-1",
        turn_id="turn-1",
        artifacts={"active_run_id": "run-current"},
    )
    stale_emitter = ExecutionEventEmitter(
        request_id="request-old",
        task_id=task.id,
        run_id="run-stale",
        conversation_id="conversation-1",
        turn_id="turn-1",
        persist=lambda event: store.append_execution_event_for_run(task.id, "run-stale", event),
    )
    stale_emitter.emit(
        "state_transition", phase="planning", status="completed", summary="stale",
    )
    assert "execution_events" not in store.get(task.id).artifacts

    mismatched_identity = stale_emitter.emit(
        "tool_result", phase="tool", status="completed", summary="wrong owner",
    )
    with pytest.raises(ValueError, match="run_id does not match"):
        store.append_execution_event_for_run(task.id, "run-current", mismatched_identity)
    assert "execution_events" not in store.get(task.id).artifacts


def test_interrupted_run_cannot_persist_late_event_with_same_run_id(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="chat",
        goal="test interrupted run",
        conversation_id="conversation-1",
        turn_id="turn-1",
        artifacts={"active_run_id": "run-1"},
    )
    store.checkpoint(task, "user_stopped", status="interrupted")
    late_event = ExecutionEventEmitter(
        request_id="request-1",
        task_id=task.id,
        run_id="run-1",
        conversation_id="conversation-1",
        turn_id="turn-1",
    ).emit(
        "state_transition", phase="planning", status="completed", summary="late planning",
    )

    store.append_execution_event_for_run(task.id, "run-1", late_event)

    interrupted = store.get(task.id)
    assert interrupted.status == "interrupted"
    assert "execution_events" not in interrupted.artifacts


def test_terminal_event_cannot_persist_before_task_state_matches(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="chat",
        goal="test premature terminal",
        conversation_id="conversation-1",
        turn_id="turn-1",
        artifacts={"active_run_id": "run-1"},
    )
    premature = ExecutionEventEmitter(
        request_id="request-1",
        task_id=task.id,
        run_id="run-1",
        conversation_id="conversation-1",
        turn_id="turn-1",
    ).emit(
        "final", phase="final", status="completed", summary="premature final",
        payload={"task_status": "completed"},
    )

    store.append_execution_event_for_run(task.id, "run-1", premature)

    current = store.get(task.id)
    assert current.status == "running"
    assert "execution_events" not in current.artifacts


def test_store_rejects_second_terminal_for_same_run(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="chat",
        goal="test terminal cardinality",
        conversation_id="conversation-1",
        turn_id="turn-1",
        artifacts={"active_run_id": "run-1"},
    )
    task = store.checkpoint(task, "verified", status="completed")
    first = ExecutionEventEmitter(
        request_id="request-1",
        task_id=task.id,
        run_id="run-1",
        conversation_id="conversation-1",
        turn_id="turn-1",
    ).emit(
        "final", phase="final", status="completed", summary="done",
        payload={"task_status": "completed"},
    )
    store.append_execution_event_for_run(task.id, "run-1", first)

    second = ExecutionEventEmitter(
        request_id="request-1",
        task_id=task.id,
        run_id="run-1",
        conversation_id="conversation-1",
        turn_id="turn-1",
        start_seq=first["seq"],
    ).emit(
        "error", phase="error", status="failed", summary="late error",
        payload={"task_status": "completed"},
    )
    with pytest.raises(ValueError, match="cannot follow"):
        store.append_execution_event_for_run(task.id, "run-1", second)


def test_persisted_milestone_requires_complete_identity(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="chat",
        goal="test persisted identity",
        artifacts={"active_run_id": "run-1"},
    )
    event = ExecutionEventEmitter(
        request_id="request-1",
        task_id=task.id,
        run_id="run-1",
    ).emit(
        "state_transition", phase="planning", status="completed", summary="planned",
    )

    with pytest.raises(ValueError, match="conversation_id, turn_id"):
        store.append_execution_event_for_run(task.id, "run-1", event)
    assert "execution_events" not in store.get(task.id).artifacts


def test_progress_and_output_delta_are_not_persisted(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="chat",
        goal="test transient events",
        conversation_id="conversation-1",
        turn_id="turn-1",
        artifacts={"active_run_id": "run-1"},
    )
    emitter = ExecutionEventEmitter(
        request_id="request-1",
        task_id=task.id,
        run_id="run-1",
        conversation_id="conversation-1",
        turn_id="turn-1",
    )
    progress = emitter.emit("progress", phase="planning", status="running", summary="waiting")
    delta = emitter.emit(
        "output_delta",
        phase="generation",
        status="running",
        summary="visible answer",
        payload={"text": "answer", "replace": False},
    )
    store.append_execution_event_for_run(task.id, "run-1", progress)
    store.append_execution_event_for_run(task.id, "run-1", delta)

    assert "execution_events" not in store.get(task.id).artifacts


def test_reasoning_events_allow_public_summary_but_reject_private_reasoning_payload():
    public = _event(payload={"evidence_count": 2})
    public["kind"] = "reasoning"
    public["summary"] = "正在综合两条教材证据"
    validate_execution_event(public)

    private = _event()
    private["payload"] = {"chain_of_thought": "hidden steps"}
    with pytest.raises(ValueError, match="private reasoning"):
        validate_execution_event(private)


def test_task_state_payload_uses_learning_task_transition_contract():
    valid = _event()
    valid["payload"] = {
        "task_status_before": "running",
        "task_status_after": "degraded",
    }
    valid["type"] = "state_transition"
    validate_execution_event(valid)

    invalid = _event()
    invalid["payload"] = {
        "task_status_before": "degraded",
        "task_status_after": "running",
    }
    invalid["type"] = "state_transition"
    with pytest.raises(ValueError, match="degraded -> running"):
        validate_execution_event(invalid)


def test_tool_orchestration_emits_call_then_result_for_dynamic_verifier():
    events = []

    execute_read_only_tools(
        ToolOrchestrationRequest(question="解方程 x^2-5*x+6=0"),
        on_event=events.append,
    )

    assert [(event["type"], event["tool"]) for event in events] == [
        ("tool_call", "symbolic_math"),
        ("tool_result", "symbolic_math"),
        ("tool_call", "verify_math_result"),
        ("tool_result", "verify_math_result"),
    ]
    assert events[-1]["status"] == "completed"


def test_blocking_worker_emits_neutral_progress_before_result():
    release = threading.Event()
    stream = _run_blocking_with_progress(
        lambda: release.wait(1) or "never",
        phase="planning",
        operation_id="understand",
        label="理解问题",
        summary="仍在分析问题范围",
        interval_seconds=0.01,
    )

    progress = next(stream)
    release.set()
    try:
        next(stream)
    except StopIteration as completed:
        result = completed.value

    assert progress == {
        "stage": "progress",
        "phase": "planning",
        "operation_id": "understand",
        "label": "理解问题",
        "kind": "analysis",
        "message": "仍在分析问题范围",
        "waited_ms": progress["waited_ms"],
    }
    assert progress["waited_ms"] >= 10
    assert result is True


def test_stream_worker_progress_contains_no_provider_reasoning():
    release = threading.Event()

    def provider_stream():
        release.wait(1)
        yield "visible-token"

    stream = _iterate_stream_with_progress(
        provider_stream,
        phase="generation",
        operation_id="reason",
        label="组织回答",
        summary="仍在等待可展示内容",
        interval_seconds=0.01,
    )

    event_type, progress = next(stream)
    release.set()
    item_type, item = next(stream)

    assert event_type == "progress"
    assert progress["message"] == "仍在等待可展示内容"
    assert progress["waited_ms"] >= 10
    assert "reasoning" not in progress
    assert (item_type, item) == ("item", "visible-token")
