from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from backend.services.agent_runtime.contracts import FixedAction, RunCommand, RuntimeConflict, RuntimeDenied
from backend.services.agent_runtime.progress_tool import register_recent_progress_runtime
from backend.services.agent_runtime.runner import FixedRunner
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.execution_events import execution_sse_payload, validate_execution_event_sequence
from backend.tools.registry import ToolContext, ToolRegistry, ToolResult, ToolSpec
from memory.learning_events import LearningEvent, LearningEventStore


def command(key: str = "request-1", owner: str = "owner-1") -> RunCommand:
    return RunCommand(key, key, "task-1", "conversation-1", "turn-1", "Inspect progress", owner)


def setup(tmp_path: Path):
    store = RuntimeStore(tmp_path / "runtime.db")
    events = LearningEventStore(tmp_path / "learning.db")
    registry = ToolRegistry()
    register_recent_progress_runtime(registry, events)
    return store, events, FixedRunner(store, registry)


def test_zero_tool_complete_and_reopen(tmp_path):
    store, _, runner = setup(tmp_path)
    run_id = runner.start(command())["run"]["id"]
    runner.execute(run_id, "owner-1", FixedAction("finish", answer="Done"))
    reopened = RuntimeStore(tmp_path / "runtime.db")
    assert reopened.snapshot(run_id)["task"]["status"] == "completed"
    events = reopened.events(run_id)
    assert [e["payload"]["lifecycle"] for e in events] == ["run.created", "run.completed"]
    validate_execution_event_sequence(events)
    assert "execution_event" in execution_sse_payload(events[-1], sidecar={"answer": "Done"})
    with pytest.raises(RuntimeConflict):
        reopened.close(run_id, "owner-1", outcome="completed")


def test_p0_cannot_publish_unverified_required_outputs(tmp_path):
    store, _, runner = setup(tmp_path)
    required = RunCommand("key", "req", "task-1", "conversation-1", "turn-1",
                          "Explain", "owner-1", required_outputs=[{"kind": "citation"}])
    run_id = runner.start(required)["run"]["id"]
    with pytest.raises(RuntimeConflict):
        runner.execute(run_id, "owner-1", FixedAction("finish", answer="Unverified"))
    assert store.snapshot(run_id)["task"]["status"] == "running"


def test_read_tool_and_bounded_coverage(tmp_path):
    store, learning, runner = setup(tmp_path)
    learning.append(LearningEvent(event_type="chat_qa", book_name="default", subject="math"))
    run_id = runner.start(command())["run"]["id"]
    result = runner.execute(run_id, "owner-1", FixedAction("call", tool_id="get_recent_progress",
                            args={"subject": "math", "days": 7, "limit": 5}, operation_key="activity-1"),
                            context=ToolContext(book_name="default", subject="math"))
    data = result["tool_calls"][0]["result"]["data"]
    assert data["summary"]["qa_count"] == 1
    assert data["queried_event_limit"] == 200
    assert data["window_complete"] is False
    assert data["coverage_note"]
    runner.execute(run_id, "owner-1", FixedAction("finish", answer="One event"))
    events = RuntimeStore(tmp_path / "runtime.db").events(run_id)
    assert [e["seq"] for e in events] == list(range(1, 6))
    assert [e["seq"] for e in store.events(run_id, after_seq=2, limit=2)] == [3, 4]
    validate_execution_event_sequence(events)


def test_request_key_claim_and_operation_hash(tmp_path):
    store, _, runner = setup(tmp_path)
    first = runner.start(command())
    assert runner.start(command())["run"]["id"] == first["run"]["id"]
    with pytest.raises(RuntimeConflict):
        runner.start(command("different"))
    meta = runner.registry.runtime_tool("get_recent_progress").runtime_metadata()
    run_id = first["run"]["id"]
    store.request_tool(run_id, "owner-1", tool_id="get_recent_progress", version="1",
                       schema_hash=meta["schema_hash"], args={"days": 7}, args_hash="a", operation_key="op")
    with pytest.raises(RuntimeConflict):
        store.request_tool(run_id, "owner-1", tool_id="get_recent_progress", version="1",
                           schema_hash=meta["schema_hash"], args={"days": 8}, args_hash="b", operation_key="op")


def test_concurrent_claim_has_one_active_run(tmp_path):
    store, _, _ = setup(tmp_path)
    barrier = threading.Barrier(2)
    results = []
    def claim(key):
        barrier.wait()
        try:
            results.append(store.create(command(key))["run"]["id"])
        except RuntimeConflict:
            results.append("conflict")
    threads = [threading.Thread(target=claim, args=(key,)) for key in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 2
    assert results.count("conflict") == 1


def test_pause_resume_fences_old_owner_and_budget(tmp_path):
    store, _, runner = setup(tmp_path)
    old = runner.start(command())["run"]["id"]
    paused = runner.pause(old, "owner-1")
    new = store.resume("task-1", expected_revision=paused["task_revision"],
                       request_key="resume-1", request_id="request-2",
                       owner_token="owner-2", turn_id="turn-2")
    assert new["run"]["resume_of_run_id"] == old
    with pytest.raises(RuntimeConflict):
        store.close(old, "owner-1", outcome="completed")
    with pytest.raises(RuntimeConflict):
        store.finish_tool(old, "owner-1", "stale-call", {"success": True})
    with pytest.raises(RuntimeConflict):
        store.close(new["run"]["id"], "owner-1", outcome="completed")
    assert new["budget_calls"] == 1
    assert [e["payload"]["lifecycle"] for e in store.events(new["run"]["id"])] == ["run.resumed"]


def test_recover_does_not_execute_and_closes_run(tmp_path):
    store, _, runner = setup(tmp_path)
    run_id = runner.start(command())["run"]["id"]
    reopened = RuntimeStore(tmp_path / "runtime.db")
    assert reopened.recover_unfinished() == 1
    assert reopened.recover_unfinished() == 0
    assert reopened.snapshot(run_id)["task"]["status"] == "interrupted"
    assert reopened.events(run_id)[-1]["payload"]["pause_reason"] == "recovery_required"


def test_transaction_rollback_at_create_tool_and_finish(tmp_path, monkeypatch):
    store, _, runner = setup(tmp_path)
    original = store._event
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("injected persistence failure")
    monkeypatch.setattr(store, "_event", fail)
    with pytest.raises(sqlite3.OperationalError):
        runner.start(command())
    with store._connect() as conn:
        assert conn.execute("SELECT count(*) FROM runtime_tasks").fetchone()[0] == 0
    monkeypatch.setattr(store, "_event", original)
    run_id = runner.start(command())["run"]["id"]
    monkeypatch.setattr(store, "_event", fail)
    with pytest.raises(sqlite3.OperationalError):
        store.request_tool(run_id, "owner-1", tool_id="get_recent_progress", version="1",
                           schema_hash="hash", args={}, args_hash="hash", operation_key="op")
    assert store.snapshot(run_id)["consumed_calls"] == 0
    with pytest.raises(sqlite3.OperationalError):
        store.close(run_id, "owner-1", outcome="completed", answer="no")
    assert store.snapshot(run_id)["task"]["status"] == "running"
    assert len(store.events(run_id)) == 1


def test_tool_result_rollback_keeps_running_call(tmp_path, monkeypatch):
    store, _, runner = setup(tmp_path)
    run_id = runner.start(command())["run"]["id"]
    requested = store.request_tool(run_id, "owner-1", tool_id="get_recent_progress",
        version="1", schema_hash="hash", args={}, args_hash="hash", operation_key="op")
    call_id = requested["tool_calls"][0]["id"]
    store.start_tool(run_id, "owner-1", call_id)
    before = store.events(run_id)
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("injected persistence failure")
    monkeypatch.setattr(store, "_event", fail)
    with pytest.raises(sqlite3.OperationalError):
        store.finish_tool(run_id, "owner-1", call_id, {"success": True})
    assert store.snapshot(run_id)["tool_calls"][0]["status"] == "running"
    assert store.events(run_id) == before


def test_denials_before_handler(tmp_path):
    store, _, runner = setup(tmp_path)
    run_id = runner.start(command())["run"]["id"]
    for args in ({"days": "7"}, {"days": 40}, {"extra": 1}):
        with pytest.raises(Exception):
            runner.execute(run_id, "owner-1", FixedAction("call", tool_id="get_recent_progress",
                           args=args, operation_key="bad"))
    with pytest.raises(RuntimeDenied):
        runner.execute(run_id, "owner-1", FixedAction("call", tool_id="unknown", operation_key="x"))
    for permission in ("LOCAL_WRITE", "EXTERNAL_WRITE", "DESTRUCTIVE"):
        called = []
        registry = ToolRegistry()
        spec = runner.registry.get("get_recent_progress")
        registry.register(ToolSpec(name="get_recent_progress", description="test", parameters={},
            read_only=True, handler=lambda *_: called.append(True) or ToolResult(True),
            runtime_input=spec.runtime_input, runtime_output=spec.runtime_output,
            permission=permission))
        denied = FixedRunner(store, registry)
        with pytest.raises(RuntimeDenied):
            denied.execute(run_id, "owner-1", FixedAction("call", tool_id="get_recent_progress",
                           operation_key="write"))
        assert not called
    assert store.snapshot(run_id)["consumed_calls"] == 0


def test_timeout_capacity_and_late_result(tmp_path):
    store, _, base = setup(tmp_path)
    runner = FixedRunner(store, base.registry, max_inflight=1)
    run_id = runner.start(command())["run"]["id"]
    entered = threading.Event()
    release = threading.Event()
    spec = runner.registry.get("get_recent_progress")
    def slow(*_):
        entered.set()
        release.wait(2)
        return ToolResult(True, data={})
    spec.handler = slow
    spec.timeout_seconds = 0.02
    runner.execute(run_id, "owner-1", FixedAction("call", tool_id="get_recent_progress",
                   operation_key="slow"))
    assert entered.is_set()
    assert store.snapshot(run_id)["tool_calls"][0]["status"] == "failed"
    # The timed-out daemon still occupies its bounded slot until it really exits.
    with pytest.raises(RuntimeDenied):
        runner.execute(run_id, "owner-1", FixedAction("call", tool_id="get_recent_progress",
                       operation_key="capacity"))
    assert store.snapshot(run_id)["consumed_calls"] == 1
    paused = runner.pause(run_id, "owner-1")
    resumed = store.resume("task-1", expected_revision=paused["task_revision"],
                           request_key="resume", request_id="req2", owner_token="owner2", turn_id="turn2")
    assert resumed["consumed_calls"] == 1
    release.set()
    time.sleep(0.03)
    with pytest.raises(RuntimeConflict):
        runner.execute(resumed["run"]["id"], "owner2", FixedAction("call", tool_id="get_recent_progress",
                       operation_key="another"))
    assert store.snapshot(run_id)["tool_calls"][0]["status"] == "failed"


def test_newer_schema_fails_closed(tmp_path):
    path = tmp_path / "future.db"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version=99")
    with pytest.raises(RuntimeError):
        RuntimeStore(path)
