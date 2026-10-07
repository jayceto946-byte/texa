from __future__ import annotations

from backend.services.agent_runtime.contracts import RunCommand, RuntimeConflict
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.agent_runtime.write_service import RuntimeWriteService
from backend.services.agent_runtime.write_tools import register_receipt_backed_write_tools
from backend.services.pending_actions import PendingActionStore
from backend.tools.registry import ToolContext, ToolRegistry


def test_save_mistake_confirm_is_idempotent(tmp_path):
    runtime = RuntimeStore(tmp_path / "runtime.db")
    pending = PendingActionStore(tmp_path)
    registry = ToolRegistry()
    register_receipt_backed_write_tools(registry)
    service = RuntimeWriteService(runtime, registry, pending)
    run_id = runtime.create(RunCommand("key", "req", "task", "conv", "turn",
                                       "Save mistake", "owner"))["run"]["id"]
    context = ToolContext(book_name="math", subject="数学", conversation_id="conv")
    paused = service.propose(run_id, "owner", tool_id="save_mistake",
        args={"book_name": "math", "question_text": "What is 2+2?"},
        operation_key="save-1", context=context)
    call = paused["tool_calls"][0]
    assert paused["task"]["status"] == "waiting_for_confirmation"
    assert pending.get(call["id"])["status"] == "pending"
    result = service.confirm("task", call["id"], actor_id="user",
        args_hash=call["args_hash"], scope={"book_name": "math", "subject": "数学"},
        expected_revision=paused["task_revision"], resume_request_key="resume",
        request_id="req2", owner_token="owner2", turn_id="turn2")
    assert result["tool_calls"][0]["status"] == "succeeded"
    again = service.confirm("task", call["id"], actor_id="user",
        args_hash=call["args_hash"], scope={"book_name": "math", "subject": "数学"},
        expected_revision=paused["task_revision"], resume_request_key="resume",
        request_id="req2", owner_token="owner2", turn_id="turn2")
    assert again["tool_calls"][0]["result"]["domain_receipt"]["mistake_id"] == call["id"]
    from memory.mistake_book import get_mistake_book
    records = get_mistake_book("math", str(tmp_path)).list_all()
    assert len([item for item in records if item.id == call["id"]]) == 1
