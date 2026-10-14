import json
import pytest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services.agent_runtime import chat_binding as binding
from backend.services.agent_runtime.contracts import FixedAction, ModelCapabilities
from backend.services.agent_runtime.progress_tool import register_recent_progress_runtime
from backend.services.agent_runtime.store import RuntimeStore
from backend.tools.registry import ToolRegistry
from memory.learning_events import LearningEventStore


def prepared():
    return {"rewritten_question": "最近学习进度如何", "book_name": "", "subject": "",
        "use_textbook_context": False, "answer_mode": "global_general", "scope_reason": "explicit",
        "resolution_trace": {}, "continuity_context": {}, "conversation_id": "conv", "turn_id": "turn"}


@pytest.mark.parametrize("baseline", [False, True])
def test_runtime_sse_sql_outcome_transport_delta_and_projection(tmp_path, monkeypatch, baseline):
    monkeypatch.setenv("TEXA_AGENT_RUNTIME_READ", "1")
    monkeypatch.setenv("TEXA_RUNTIME_POLICY_V0", "1" if baseline else "0")
    store = RuntimeStore(tmp_path / "runtime.db")
    registry = ToolRegistry()
    register_recent_progress_runtime(registry, LearningEventStore(tmp_path / "events.db"))
    class Adapter:
        def capabilities(self):
            return ModelCapabilities(tool_calling="supported")
        def next_action(self, transcript, candidates):
            if len(transcript) == 1:
                return FixedAction("call", tool_id="get_recent_progress", args={})
            return FixedAction("finish", answer="protocol text")
    monkeypatch.setattr(binding, "runtime_store", lambda **kw: store)
    monkeypatch.setattr(binding, "build_registry", lambda: registry)
    def adapter(_):
        assert not baseline, "baseline must not instantiate a model adapter"
        return Adapter()
    monkeypatch.setattr(binding, "build_adapter", adapter)
    monkeypatch.setattr(binding, "generate_answer", lambda _: "本次查询覆盖近期学习记录。")
    import backend.conversation_memory as conversations
    messages = {}
    def append(conversation_id, role, content, **kwargs):
        identity = kwargs.get("message_id") or f"{kwargs['turn_id']}:{role}"
        messages.setdefault(identity, {"id": identity, "content": content})
        return messages[identity]
    monkeypatch.setattr(conversations, "append_message", append)
    monkeypatch.setattr(conversations, "update_learning_task_projection", lambda *a, **kw: None)
    app = FastAPI()
    @app.post("/stream")
    def stream():
        return binding.try_chat_response(SimpleNamespace(question="最近学习进度如何"), prepared(), "req")
    response = TestClient(app).post("/stream")
    assert response.status_code == 200
    envelopes = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    events = [item["execution_event"] for item in envelopes]
    assert events[-1]["type"] == "final"
    assert events[-2]["type"] == "output_delta"
    assert events[-2]["payload"]["text"] == "本次查询覆盖近期学习记录。"
    assert [event["seq"] for event in events] == sorted(set(event["seq"] for event in events))
    task_id = events[-1]["task_id"]
    snapshot = store.task_snapshot(task_id)
    assert snapshot["task"]["status"] == "completed"
    assert snapshot["consumed_model_calls"] == (1 if baseline else 3)
    assert all(e["type"] != "output_delta" for e in store.events(events[-1]["run_id"]))
    binding.project_outcomes(store)
    assert len(messages) == 2
    assert store.pending_outbox() == []
    assert envelopes[-1]["learning_task"]["terminal"] is True


def test_runtime_does_not_claim_grounded_or_ambiguous_requests(monkeypatch):
    monkeypatch.setenv("TEXA_AGENT_RUNTIME_READ", "1")
    monkeypatch.setattr(binding, "build_registry", lambda: (_ for _ in ()).throw(AssertionError("must stay lazy")))
    for changes in ({"use_textbook_context": True}, {"resolution_trace": {"resolution_action": "clarify"}}):
        assert binding.try_chat_response(SimpleNamespace(question="最近学习进度如何"),
            {**prepared(), **changes}, "req") is None


def test_http_replay_fences_task_and_run(tmp_path, monkeypatch):
    from backend.api.chat import get_chat_runtime_events
    from backend.services.agent_runtime import locator
    from backend.services.agent_runtime.contracts import RunCommand
    from fastapi import HTTPException
    import pytest
    store = RuntimeStore(tmp_path / "runtime.db")
    run = store.create(RunCommand("key", "req", "rtask_one", "conv", "turn", "inspect", "owner"))["run"]["id"]
    monkeypatch.setattr(locator, "runtime_store", lambda: store)
    page = get_chat_runtime_events("rtask_one", run, limit=1)
    assert len(page["events"]) == 1
    assert page["next_seq"] == page["events"][0]["seq"]
    assert not get_chat_runtime_events("rtask_one", run, after_seq=page["next_seq"])["events"]
    with pytest.raises(HTTPException) as denied:
        get_chat_runtime_events("rtask_other", run)
    assert denied.value.status_code == 404
