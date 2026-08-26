import threading

from backend.services.execution_events import ExecutionEventEmitter
from backend.services.learning_task import LearningTaskStore
from backend.services.tool_orchestration import ToolOrchestrationRequest, execute_read_only_tools
from graph.main_graph import _iterate_stream_with_progress, _run_blocking_with_progress


def test_execution_emitter_sequences_events_and_persists_only_milestones(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="chat",
        goal="test progressive trace",
        artifacts={"active_run_id": "run-1"},
    )
    emitter = ExecutionEventEmitter(
        request_id="request-1",
        task_id=task.id,
        run_id="run-1",
        persist=lambda event: store.append_execution_event_for_run(task.id, "run-1", event),
    )

    emitted = [
        emitter.emit("progress", phase="planning", status="running", summary="waiting"),
        emitter.emit("tool_call", phase="tool", status="started", summary="calling"),
        emitter.emit("state_transition", phase="planning", status="completed", summary="planned"),
        emitter.emit("tool_result", phase="tool", status="completed", summary="returned"),
        emitter.emit("output_delta", phase="generation", status="running", summary="delta"),
        emitter.emit("final", phase="final", status="completed", summary="done"),
    ]

    assert [event["seq"] for event in emitted] == [1, 2, 3, 4, 5, 6]
    stored = store.get(task.id)
    assert stored is not None
    assert [event["type"] for event in stored.artifacts["execution_events"]] == [
        "state_transition", "tool_result", "final",
    ]


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
