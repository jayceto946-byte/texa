from datetime import datetime, timedelta, timezone

import pytest

from backend.services.agent_runtime.contracts import RunCommand, RuntimeConflict
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.execution_events import validate_execution_event_sequence


def test_confirmed_write_call_is_bound_and_resumes_new_run(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    first = store.create(RunCommand("key", "req", "task", "conv", "turn", "Create practice", "owner"))
    old_id = first["run"]["id"]
    requested = store.request_tool(old_id, "owner", tool_id="create_practice_session",
        version="1", schema_hash="schema", args={"exercise_ids": ["ex1"]},
        args_hash="frozen", operation_key="create-1", permission="LOCAL_WRITE")
    call_id = requested["tool_calls"][0]["id"]
    with pytest.raises(RuntimeConflict):
        store.start_tool(old_id, "owner", call_id)
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    paused = store.await_approval(old_id, "owner", call_id,
                                  scope={"book": "math"}, expires_at=expires)
    assert paused["task"]["status"] == "waiting_for_confirmation"
    with pytest.raises(RuntimeConflict):
        store.resume("task", expected_revision=paused["task_revision"],
                     request_key="resume", request_id="req2", owner_token="owner2", turn_id="turn2")
    with pytest.raises(RuntimeConflict):
        store.confirm_approval(call_id, actor_id="user", args_hash="tampered", scope={"book": "math"})
    approved = store.confirm_approval(call_id, actor_id="user", args_hash="frozen", scope={"book": "math"})
    assert approved["status"] == "confirmed"
    assert store.confirm_approval(call_id, actor_id="user", args_hash="frozen", scope={"book": "math"})["status"] == "confirmed"
    current = store.resume("task", expected_revision=paused["task_revision"],
                           request_key="resume", request_id="req2", owner_token="owner2", turn_id="turn2")
    new_id = current["run"]["id"]
    store.start_approved_tool(new_id, "owner2", call_id)
    finished = store.finish_tool(new_id, "owner2", call_id,
                                  {"success": True, "domain_receipt": {"session_id": call_id}})
    assert finished["tool_calls"][0]["status"] == "succeeded"
    with store._connect() as conn:
        row = conn.execute("SELECT status,receipt_json,executed_run_id FROM tool_calls WHERE id=?", (call_id,)).fetchone()
        assert row["status"] == "succeeded" and row["executed_run_id"] == new_id
        assert "session_id" in row["receipt_json"]
    validate_execution_event_sequence(store.events(old_id))
    validate_execution_event_sequence(store.events(new_id))


def test_rejected_approval_cannot_execute(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    run_id = store.create(RunCommand("key", "req", "task", "conv", "turn", "Write", "owner"))["run"]["id"]
    call_id = store.request_tool(run_id, "owner", tool_id="save_mistake", version="1",
        schema_hash="schema", args={}, args_hash="hash", operation_key="op",
        permission="LOCAL_WRITE")["tool_calls"][0]["id"]
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    store.await_approval(run_id, "owner", call_id, scope={}, expires_at=expires)
    assert store.reject_approval(call_id, actor_id="user")["status"] == "rejected"
    with pytest.raises(RuntimeConflict):
        store.confirm_approval(call_id, actor_id="user", args_hash="hash", scope={})
