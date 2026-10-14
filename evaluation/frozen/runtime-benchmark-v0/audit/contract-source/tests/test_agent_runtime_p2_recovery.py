from __future__ import annotations

import sqlite3

import pytest

from backend.services.agent_runtime.contracts import RunCommand
from backend.services.agent_runtime.outbox import RuntimeOutboxProjector
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.agent_runtime.write_service import RuntimeWriteService
from backend.services.agent_runtime.write_tools import register_receipt_backed_write_tools
from backend.services.pending_actions import PendingActionStore
from backend.tools.registry import ToolContext, ToolRegistry


def test_outbox_retries_same_message_id_after_projection_crash(tmp_path):
    runtime = RuntimeStore(tmp_path / "runtime.db")
    run_id = runtime.create(RunCommand("key", "req", "task", "conv", "turn", "Answer", "owner"))["run"]["id"]
    runtime.close(run_id, "owner", outcome="completed", answer="Answer")
    messages = {}
    first = True
    def append(conversation_id, role, content, **kwargs):
        nonlocal first
        messages.setdefault(kwargs["message_id"], {"id": kwargs["message_id"], "content": content})
        if first:
            first = False
            raise OSError("crash after message commit")
        return messages[kwargs["message_id"]]
    projector = RuntimeOutboxProjector(runtime, append)
    assert projector.drain_once() == 0
    assert runtime.pending_outbox()[0]["attempts"] == 1
    assert len(messages) == 1 and len(runtime.pending_outbox()) == 1
    assert projector.drain_once() == 1
    assert len(messages) == 1 and runtime.pending_outbox() == []


def test_domain_write_receipt_reconciles_after_runtime_commit_failure(tmp_path, monkeypatch):
    runtime = RuntimeStore(tmp_path / "runtime.db")
    pending = PendingActionStore(tmp_path)
    registry = ToolRegistry()
    register_receipt_backed_write_tools(registry)
    service = RuntimeWriteService(runtime, registry, pending)
    run_id = runtime.create(RunCommand("key", "req", "task", "conv", "turn", "Save", "owner"))["run"]["id"]
    paused = service.propose(run_id, "owner", tool_id="save_mistake",
        args={"book_name": "math", "question_text": "2+2?"}, operation_key="save",
        context=ToolContext(book_name="math", subject="数学", conversation_id="conv"))
    call = paused["tool_calls"][0]
    original = runtime.finish_tool
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("injected runtime commit failure")
    monkeypatch.setattr(runtime, "finish_tool", fail)
    with pytest.raises(sqlite3.OperationalError):
        service.confirm("task", call["id"], actor_id="user", args_hash=call["args_hash"],
            scope={"book_name": "math", "subject": "数学"},
            expected_revision=paused["task_revision"], resume_request_key="resume1",
            request_id="req2", owner_token="owner2", turn_id="turn2")
    assert pending.domain_receipt(call["id"])["mistake_id"] == call["id"]
    reopened = RuntimeStore(tmp_path / "runtime.db")
    assert reopened.recover_unfinished() == 1
    prior = reopened.snapshot(run_id)
    assert prior["tool_calls"][0]["status"] == "unknown"
    resumed = RuntimeWriteService(reopened, registry, pending).confirm(
        "task", call["id"], actor_id="user", args_hash=call["args_hash"],
        scope={"book_name": "math", "subject": "数学"},
        expected_revision=prior["task_revision"], resume_request_key="resume2",
        request_id="req3", owner_token="owner3", turn_id="turn3")
    assert resumed["tool_calls"][0]["status"] == "succeeded"
    assert resumed["tool_calls"][0]["result"]["reconciled"] is True
