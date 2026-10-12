"""Phase-1 observations, not acceptance of native protocol correctness.

The controlled model uses the installed LangChain interface; no provider,
credentials, network, textbook index or user learning database is accessed.
Replace gap observations with positive acceptance assertions when integrated.
"""
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from backend.services.agent_runtime.contracts import RunCommand
from backend.services.agent_runtime.multi_step import BoundedAgentRunner
from backend.services.agent_runtime.progress_tool import register_recent_progress_runtime
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.decision.contracts import DecisionContext
from backend.services.decision.resolver import resolve_candidate_tools
from backend.services.decision.router import DecisionRouter
from backend.services.tool_orchestration import ToolOrchestrationRequest, select_tool_calls
from backend.tools.registry import ToolContext, ToolRegistry, get_tool_registry
from llm.agent_adapter import NativeToolAdapter
from llm.configuration import resolve_model_role
from memory.learning_events import LearningEventStore


class ControlledNativeModel(BaseChatModel):
    received: list[Any] = Field(default_factory=list)
    schemas: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "texa-offline-audit"

    def bind_tools(self, tools, **kwargs):
        self.schemas.append(tools)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.received.append(messages)
        round_number = len(self.received)
        response = AIMessage(content="查询完成。") if round_number == 3 else AIMessage(
            content="", tool_calls=[{"name": "get_recent_progress",
                "args": {"days": round_number}, "id": f"native-{round_number}",
                "type": "tool_call"}])
        return ChatResult(generations=[ChatGeneration(message=response)])


def test_real_langchain_interface_two_tools_same_run_exposes_protocol_gap(tmp_path):
    registry = ToolRegistry()
    register_recent_progress_runtime(registry, LearningEventStore(tmp_path / "events.db"))
    meta = registry.runtime_tool("get_recent_progress").runtime_metadata()
    model = ControlledNativeModel()
    resolved = resolve_model_role("reasoning", {
        "LLM_REASONING_PROVIDER": "openai_compatible",
        "LLM_REASONING_MODEL": "offline-audit",
        "LLM_REASONING_BASE_URL": "http://127.0.0.1:1/v1",
    })
    # Inject capability evidence only for this controlled, offline model.
    from backend.services.agent_runtime.contracts import ModelCapabilities
    adapter = NativeToolAdapter(resolved, registry, model_factory=lambda *a, **k: model)
    adapter.capabilities = lambda: ModelCapabilities(tool_calling="supported")
    store = RuntimeStore(tmp_path / "runtime.db")
    run_id = store.create(RunCommand("audit", "request", "task", "session", "turn",
        "最近学习进度如何", "owner", budget_calls=2, budget_model_calls=3))["run"]["id"]
    result = BoundedAgentRunner(store, registry, adapter, (
        {"id": meta["id"], "version": meta["version"], "schema_hash": meta["schema_hash"]},
    )).run_bounded(run_id, "owner", context=ToolContext())
    assert result["run"]["id"] == run_id
    assert result["consumed_model_calls"] == 3
    assert len(result["tool_calls"]) == 2
    assert all(call["status"] == "succeeded" for call in result["tool_calls"])
    assert all(event["run_id"] == run_id for event in store.events(run_id))
    # Tool data reached later rounds, but as quoted user text, not native ToolMessage.
    assert "range_days" in str(model.received[1])
    assert "range_days" in str(model.received[2])
    assert not any(isinstance(msg, ToolMessage) for batch in model.received for msg in batch)
    assert not any(isinstance(msg, AIMessage) and msg.tool_calls
                   for batch in model.received for msg in batch)
    assert "native-1" not in str(result["run"]["checkpoint"])
    assert "native-2" not in str(result["run"]["checkpoint"])


def test_math_exists_but_has_no_canonical_runtime_schema():
    registry = get_tool_registry()
    assert registry.call("symbolic_math", {"operation": "calculate", "expression": "2^10"},
                         ToolContext()).data["result"]["exact"] == "1024"
    with pytest.raises(ValueError, match="no canonical runtime schema"):
        registry.runtime_tool("symbolic_math")


def test_math_router_capability_has_no_runtime_candidate():
    decision = DecisionRouter(shadow=False).route(DecisionContext(
        request_id="audit", text="计算 2+3", resolved_query="计算 2+3",
        answer_mode="global_general"))
    assert decision.selected_capability == "math.verify"
    assert not resolve_candidate_tools(decision, get_tool_registry()).tool_refs


def test_concept_question_has_no_forced_math_call():
    assert select_tool_calls(ToolOrchestrationRequest(question="什么是导数？")) == []


def test_limit_is_not_an_existing_math_operation():
    result = get_tool_registry().call("symbolic_math", {
        "operation": "limit", "expression": "sin(x)/x", "variable": "x", "point": "0",
    }, ToolContext())
    assert not result.success
    assert "unsupported operation" in result.message
