from __future__ import annotations

from backend.services.agent_runtime.contracts import FixedAction, RunCommand
from backend.services.agent_runtime.exercise_tool import register_search_exercises_runtime
from backend.services.agent_runtime.runner import FixedRunner
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.agent_runtime.write_service import RuntimeWriteService
from backend.services.agent_runtime.write_tools import register_receipt_backed_write_tools
from backend.services.pending_actions import PendingActionStore
from backend.tools.registry import ToolContext, ToolRegistry
from memory.exercise_bank import ExerciseRecord, get_exercise_bank


def test_search_existing_then_approved_practice_session(tmp_path):
    bank = get_exercise_bank("math", str(tmp_path))
    exercise_id = bank.add(ExerciseRecord(question_text="求极限 lim x→0 sin x/x", subject="数学"))
    registry = ToolRegistry()
    register_search_exercises_runtime(registry, bank)
    register_receipt_backed_write_tools(registry)
    runtime = RuntimeStore(tmp_path / "runtime.db")
    service = RuntimeWriteService(runtime, registry, PendingActionStore(tmp_path))
    context = ToolContext(book_name="math", subject="数学", conversation_id="conv")
    run_id = runtime.create(RunCommand("key", "req", "task", "conv", "turn",
                                       "Practice limit", "owner", budget_calls=2))["run"]["id"]
    read = FixedRunner(runtime, registry, allowlist=frozenset({"search_exercises"}))
    found = read.execute(run_id, "owner", FixedAction("call", tool_id="search_exercises",
        args={"book_name": "math", "query": "极限"}, operation_key="search"), context=context)
    exercises = found["tool_calls"][0]["result"]["data"]["exercises"]
    assert any(item["id"] == exercise_id for item in exercises)
    paused = service.propose(run_id, "owner", tool_id="create_exercise_set",
        args={"book_name": "math", "exercise_ids": [exercise_id]},
        operation_key="create", context=context)
    call = next(item for item in paused["tool_calls"] if item["tool_id"] == "create_exercise_set")
    result = service.confirm("task", call["id"], actor_id="user",
        args_hash=call["args_hash"], scope={"book_name": "math", "subject": "数学"},
        expected_revision=paused["task_revision"], resume_request_key="resume",
        request_id="req2", owner_token="owner2", turn_id="turn2")
    created = bank.get_practice_session(call["id"])
    assert created and created.exercise_ids == [exercise_id]
    assert next(item for item in result["tool_calls"] if item["id"] == call["id"])["status"] == "succeeded"
