from __future__ import annotations

from backend.services.agent_runtime.contracts import FixedAction, ModelCapabilities, RunCommand
from backend.services.agent_runtime.multi_step import BoundedAgentRunner
from backend.services.agent_runtime.progress_tool import register_recent_progress_runtime
from backend.services.agent_runtime.store import RuntimeStore
from backend.tools.registry import ToolContext, ToolRegistry
from memory.learning_events import LearningEvent, LearningEventStore


class FakeAdapter:
    def __init__(self, actions):
        self.actions = iter(actions)
    def capabilities(self):
        return ModelCapabilities(tool_calling="supported")
    def next_action(self, transcript, candidate_tools):
        return next(self.actions)


def test_two_read_steps_and_verified_finish(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    learning = LearningEventStore(tmp_path / "learning.db")
    learning.append(LearningEvent(event_type="chat_qa", book_name="default"))
    registry = ToolRegistry()
    register_recent_progress_runtime(registry, learning)
    metadata = registry.runtime_tool("get_recent_progress").runtime_metadata()
    command = RunCommand("key", "req", "task", "conv", "turn", "Inspect", "owner",
                         budget_calls=2, budget_model_calls=3,
                         required_outputs=[{"id": "answer", "kind": "content", "required": True}])
    run_id = store.create(command)["run"]["id"]
    adapter = FakeAdapter([
        FixedAction("call", tool_id="get_recent_progress", args={"limit": 5}, operation_key="one"),
        FixedAction("call", tool_id="get_recent_progress", args={"days": 2}, operation_key="two"),
        FixedAction("finish", answer="<think>private</think>已记录两次查询。"),
    ])
    runner = BoundedAgentRunner(store, registry, adapter,
                                ({"id": "get_recent_progress", "version": "1", "schema_hash": metadata["schema_hash"]},))
    result = runner.run_offline(run_id, "owner", context=ToolContext(book_name="default"))
    assert result["task"]["status"] == "completed"
    assert result["consumed_calls"] == 2
    assert result["consumed_model_calls"] == 3
    assert "private" not in result["task"]["artifacts"]["final_answer"]
    assert len(store.events(run_id)) == 14


def test_unknown_model_capability_rejected(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    registry = ToolRegistry()
    run_id = store.create(RunCommand("key", "req", "task", "conv", "turn", "Ask", "owner",
                                         budget_model_calls=1))["run"]["id"]
    adapter = FakeAdapter([FixedAction("finish", answer="hello")])
    adapter.capabilities = lambda: ModelCapabilities()
    from backend.services.agent_runtime.contracts import RuntimeDenied
    import pytest
    with pytest.raises(RuntimeDenied):
        BoundedAgentRunner(store, registry, adapter, ()).run_offline(run_id, "owner")


def test_budget_exhaustion_closes_run_and_initial_goal_reaches_adapter(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    learning = LearningEventStore(tmp_path / "learning.db")
    registry = ToolRegistry()
    register_recent_progress_runtime(registry, learning)
    metadata = registry.runtime_tool("get_recent_progress").runtime_metadata()
    run_id = store.create(RunCommand("key", "req", "task", "conv", "turn", "Inspect my progress", "owner",
                                    budget_model_calls=1))["run"]["id"]
    class Adapter(FakeAdapter):
        def next_action(self, transcript, candidates):
            assert transcript[0] == {"role": "user", "content": "Inspect my progress"}
            return FixedAction("call", tool_id="get_recent_progress", args={})
    result = BoundedAgentRunner(store, registry, Adapter([]),
        ({"id": "get_recent_progress", "version": "1", "schema_hash": metadata["schema_hash"]},)).run_offline(run_id, "owner")
    assert result["run"]["status"] == "failed"
    assert result["consumed_model_calls"] == 1


def test_shared_answer_boundary_uses_prompt_and_counts_final_model_call(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    run_id = store.create(RunCommand("key", "req", "task", "conv", "turn", "解释学习方法", "owner",
        budget_calls=0, budget_model_calls=2,
        required_outputs=[{"id": "answer", "kind": "content", "required": True}]))["run"]["id"]
    prompts = []
    def generate(messages):
        prompts.append(messages)
        return "<think>private</think>先理解概念，再回顾例题。"
    result = BoundedAgentRunner(store, ToolRegistry(), FakeAdapter([
        FixedAction("finish", answer="action response must not become the answer")]), ()).run_offline(
            run_id, "owner", answer_state={"user_input": "解释学习方法", "intent": "qa",
                "use_textbook_context": False, "answer_mode": "global_general"}, answer_generator=generate)
    assert result["task"]["status"] == "completed"
    assert result["consumed_model_calls"] == 2
    assert prompts
    assert result["task"]["artifacts"]["final_answer"] == "先理解概念，再回顾例题。"


def test_late_model_result_cannot_publish_after_timeout(tmp_path):
    import threading
    release, ended = threading.Event(), threading.Event()
    store = RuntimeStore(tmp_path / "runtime.db")
    run_id = store.create(RunCommand("key", "req", "task", "conv", "turn", "Ask", "owner",
                                    budget_model_calls=1))["run"]["id"]
    class SlowAdapter(FakeAdapter):
        def next_action(self, transcript, candidates):
            release.wait(2)
            ended.set()
            return FixedAction("finish", answer="late result")
    try:
        result = BoundedAgentRunner(store, ToolRegistry(), SlowAdapter([]), (),
                                    model_timeout_seconds=.01).run_offline(run_id, "owner")
        assert result["run"]["status"] == "failed"
        release.set()
        assert ended.wait(1)
        assert store.snapshot(run_id)["task"]["artifacts"].get("final_answer", "") != "late result"
    finally:
        release.set()
