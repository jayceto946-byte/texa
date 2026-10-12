from __future__ import annotations
import json
import multiprocessing
import threading
import time
from types import SimpleNamespace
import pytest
from pydantic import Field
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage, messages_from_dict
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from backend.services.agent_runtime.chat_binding import build_math_registry
from backend.services.agent_runtime.contracts import RunCommand, ModelCapabilities
from backend.services.agent_runtime.multi_step import BoundedAgentRunner
from backend.services.agent_runtime.store import RuntimeStore
from backend.tools.registry import ToolContext
from llm.agent_adapter import NativeToolAdapter
from llm.configuration import resolve_model_role


class ScriptedMathModel(BaseChatModel):
    responses: list[dict]
    received: list = Field(default_factory=list)
    delays: float = 0

    @property
    def _llm_type(self):
        return "controlled-math"

    def bind_tools(self, tools, **kwargs):
        return self

    def _response(self, messages):
        self.received.append(messages)
        return self.responses[min(len(self.received)-1, len(self.responses)-1)]

    def _generate(self, messages, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(**self._response(messages)))])

    def _stream(self, messages, **kwargs):
        response = self._response(messages)
        calls = response.get("tool_calls") or []
        if calls:
            call = calls[0]
            args = json.dumps(call["args"])
            for index, part in enumerate([args[:len(args)//2], args[len(args)//2:]]):
                yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[{
                    "name": call["name"] if index == 0 else None, "id": call["id"] if index == 0 else None,
                    "args": part, "index": 0}]))
        else:
            for part in [response["content"][:3], response["content"][3:]]:
                time.sleep(self.delays)
                yield ChatGenerationChunk(message=AIMessageChunk(content=part))


def call(name, args, identity):
    return {"content": "", "tool_calls": [{"name": name, "args": args, "id": identity, "type": "tool_call"}]}


def model_adapter(model, registry):
    resolved = resolve_model_role("reasoning", {"LLM_REASONING_PROVIDER": "openai_compatible",
        "LLM_REASONING_MODEL": "controlled", "LLM_REASONING_BASE_URL": "http://127.0.0.1:1/v1"})
    adapter = NativeToolAdapter(resolved, registry, model_factory=lambda *a, **k: model)
    adapter.capabilities = lambda: ModelCapabilities(tool_calling="supported")
    return adapter


def setup_run(tmp_path, responses, *, budget_calls=3, budget_model_calls=4, on_output=None):
    registry = build_math_registry()
    refs = tuple({key: spec.runtime_metadata()[key] for key in ("id", "version", "schema_hash")}
                 for spec in (registry.get("symbolic_math"), registry.get("verify_math_result")))
    store = RuntimeStore(tmp_path / "runtime.db")
    run = store.create(RunCommand("request", "request", "rtask_math", "session", "turn", "计算 2^10", "owner",
        budget_calls=budget_calls, budget_model_calls=budget_model_calls,
        required_outputs=[{"id": "answer", "kind": "content"}, {"id": "numeric", "kind": "numeric"}]))["run"]["id"]
    model = ScriptedMathModel(responses=responses)
    runner = BoundedAgentRunner(store, registry, model_adapter(model, registry), refs, on_output=on_output)
    state = {"user_input": "计算 2^10", "answer_mode": "textbook_grounded", "use_textbook_context": True,
        "support_type": "explicit_math_only", "evidence_support": {"status": "not_applicable"}}
    return store, run, model, runner, state


SUCCESS = [call("symbolic_math", {"operation": "calculate", "expression": "2^10"}, "calc-1"),
    call("verify_math_result", {"kind": "equivalence", "left": "2^10", "right": "1024"}, "verify-2"),
    {"content": "结果是 1024。"}]


def test_two_real_sympy_calls_three_model_rounds_and_streaming(tmp_path):
    deltas = []
    store, run, model, runner, state = setup_run(tmp_path, SUCCESS, on_output=lambda text, replace: deltas.append((text, replace)))
    result = runner.run_bounded(run, "owner", context=ToolContext(), answer_state=state, answer_generator=lambda _: pytest.fail("no second answer chain"))
    assert result["run"]["status"] == "completed", result["run"]["error_code"]
    assert result["consumed_model_calls"] == 3
    assert result["consumed_calls"] == 2
    assert result["task"]["verification"]["status"] == "passed"
    assert result["tool_calls"][0]["result"]["data"]["result"]["exact"] == "1024"
    for index, identity in [(1, "calc-1"), (2, "verify-2")]:
        tool = next(m for m in model.received[index] if isinstance(m, ToolMessage) and m.tool_call_id == identity)
        assert json.loads(tool.content)["success"] is True
    assert "结果是 1024。" == "".join(text for text, replace in deltas if not replace)
    assert len([text for text, replace in deltas if text]) >= 2
    saved = messages_from_dict(result["run"]["checkpoint"]["native_messages"])
    assert [m.tool_call_id for m in saved if isinstance(m, ToolMessage)] == ["calc-1", "verify-2"]
    assert not result["task"]["artifacts"].get("evidence_sources")


@pytest.mark.parametrize("args", [{"operation": "calculate", "expression": "__import__('os')"},
    {"operation": "invalid", "expression": "2"}])
def test_tool_error_is_native_result_and_never_verified(tmp_path, args):
    store, run, model, runner, state = setup_run(tmp_path, [call("symbolic_math", args, "bad"), {"content": "计算失败，不能提供精确结果。"}])
    result = runner.run_bounded(run, "owner", context=ToolContext(), answer_state=state, answer_generator=lambda _: "")
    assert result["task"]["status"] != "completed"
    receipt = next(m for m in model.received[1] if isinstance(m, ToolMessage))
    assert receipt.tool_call_id == "bad" and json.loads(receipt.content)["success"] is False


@pytest.mark.parametrize("budgets,code", [((0, 3), "tool_budget_exhausted"), ((3, 1), "model_budget_exhausted")])
def test_budgets_fail_same_run(tmp_path, budgets, code):
    store, run, model, runner, state = setup_run(tmp_path, SUCCESS, budget_calls=budgets[0], budget_model_calls=budgets[1])
    result = runner.run_bounded(run, "owner", context=ToolContext())
    assert result["run"]["status"] == "failed"
    assert result["run"]["error_code"] == code


def sleeping_worker(connection, tool, args):
    time.sleep(30)


@pytest.mark.parametrize("cancel", [False, True])
def test_math_worker_timeout_and_cancel_reap_process(cancel):
    from backend.tools.math_worker import execute_math
    before = {p.pid for p in multiprocessing.active_children()}
    stop = threading.Event()
    if cancel:
        timer = threading.Timer(.2, stop.set)
        timer.start()
    result = execute_math("symbolic_math", {}, ToolContext(cancelled=stop.is_set, timeout_seconds=.4), worker_target=sleeping_worker)
    assert not result.success
    assert result.data["error_code"] == ("cancelled" if cancel else "timeout")
    assert {p.pid for p in multiprocessing.active_children()} == before


def test_no_tool_answer_has_no_tool_execution(tmp_path):
    store, run, model, runner, state = setup_run(tmp_path, [{"content": "先理解导数的含义。"}])
    result = runner.run_bounded(run, "owner", context=ToolContext())
    assert result["consumed_model_calls"] == 1 and result["consumed_calls"] == 0


def test_gate_exception_requires_whole_original_and_resolved_question():
    from backend.services.agent_runtime.math_support import explicit_math_only
    assert explicit_math_only("计算 2^10", "计算 2^10")
    for q in ["按教材定义解释导数，再计算 2^10", "计算 2^10 并解释本书例3", "按第3章公式计算", "什么是导数？"]:
        assert not explicit_math_only(q, "计算 2^10")
    assert not explicit_math_only("计算 2^10", "计算 2^10", attachments=True)
    assert not explicit_math_only("计算 2^10", "计算 2^10", scope_reason="requested_textbook_grounded")


def test_native_messages_resume_after_interrupted_tool(tmp_path):
    store, run, model, runner, state = setup_run(tmp_path, SUCCESS)
    from langchain_core.messages import HumanMessage, messages_to_dict
    pending = AIMessage(**SUCCESS[0])
    store.save_native_messages(run, "owner", messages_to_dict([HumanMessage(content="计算 2^10"), pending]))
    store.close(run, "owner", outcome="paused", error_code="interrupted")
    paused = store.snapshot(run)
    new = store.resume("rtask_math", expected_revision=paused["task_revision"], request_key="resume",
        request_id="resume", owner_token="new-owner", turn_id="turn")
    model.responses = [call("symbolic_math", {"operation": "calculate", "expression": "2^10"}, "retry"),
        {"content": "结果是 1024。"}]
    result = runner.run_bounded(new["run"]["id"], "new-owner", context=ToolContext())
    tool = next(m for m in model.received[0] if isinstance(m, ToolMessage))
    assert tool.tool_call_id == "calc-1" and json.loads(tool.content)["error_code"] == "interrupted"
    assert result["consumed_calls"] == 1
    assert store.snapshot(run)["run"]["status"] == "paused"


def test_sse_delta_arrives_while_run_is_running_and_final_is_independent(tmp_path, monkeypatch):
    import asyncio
    import backend.conversation_memory as conversation
    from backend.services.agent_runtime import chat_binding as binding
    store, run, model, runner, state = setup_run(tmp_path, SUCCESS)
    state["native_loop"] = True
    store.configure_chat(run, "owner", state=state, candidates=runner.candidate_tools,
        request_question="计算 2^10", book_name="", subject="数学")
    monkeypatch.setattr(conversation, "append_message", lambda *a, **k: {})
    monkeypatch.setattr(binding, "project_outcomes", lambda _: None)
    model.delays = .2
    async def check():
        response = binding.stream_run(store, run, "owner", runner.registry, runner.adapter)
        events, live_deltas = [], []
        async for data in response.body_iterator:
            event = json.loads(data[6:])["execution_event"]
            events.append(event)
            if event["type"] == "output_delta" and event["payload"]["text"] and not event["payload"]["replace"]:
                live_deltas.append((event, store.snapshot(run)["run"]["status"]))
        await response.aclose()
        assert any(status == "running" for _, status in live_deltas)
        assert all("runtime_call_id" not in event["payload"]["text"] for event, _ in live_deltas)
        assert events[-1]["type"] == "final"
        assert events[-2]["payload"]["replace"] is True
        assert events[-2]["payload"]["text"] == "结果是 1024。"
        assert [event["seq"] for event in events] == sorted(set(event["seq"] for event in events))
        assert {event["run_id"] for event in events} == {run}
    asyncio.run(check())


@pytest.mark.parametrize("streaming", [False, True])
def test_math_chat_ingress_uses_same_runtime_and_does_not_call_legacy_generator(tmp_path, monkeypatch, streaming):
    import asyncio
    import backend.conversation_memory as conversation
    from backend.services.agent_runtime import chat_binding as binding
    from tests.test_agent_runtime_chat_binding import prepared
    registry = build_math_registry()
    store = RuntimeStore(tmp_path / "runtime.db")
    model = ScriptedMathModel(responses=SUCCESS)
    adapter = model_adapter(model, registry)
    monkeypatch.setattr(binding, "runtime_store", lambda **kw: store)
    monkeypatch.setattr(binding, "build_math_registry", lambda: registry)
    monkeypatch.setattr(binding, "build_adapter", lambda _: adapter)
    monkeypatch.setattr(binding, "generate_answer", lambda _: pytest.fail("legacy generator called"))
    monkeypatch.setattr(binding, "project_outcomes", lambda _: None)
    monkeypatch.setattr(conversation, "append_message", lambda *a, **k: {})
    response = binding.try_chat_response(SimpleNamespace(question="计算 2^10"),
        {**prepared(), "rewritten_question": "计算 2^10", "use_textbook_context": True,
            "answer_mode": "textbook_grounded", "scope_reason": "book_selected"}, "ingress", streaming=streaming)
    if streaming:
        async def consume():
            values = [json.loads(data[6:]) async for data in response.body_iterator]
            await response.aclose()
            return values
        values = asyncio.run(consume())
        task_id = values[-1]["execution_event"]["task_id"]
    else:
        assert response["content"] == "结果是 1024。"
        task_id = response["learning_task"]["id"]
    snapshot = store.task_snapshot(task_id)
    assert snapshot["consumed_model_calls"] == 3
    assert snapshot["consumed_calls"] == 2
    assert snapshot["task"]["answer_mode"] == "textbook_grounded"
    assert snapshot["task"]["status"] == "completed"


@pytest.mark.parametrize("question", ["求 x^3 的导数", "化简 x+x"])
def test_no_receipt_math_cannot_be_completed(tmp_path, question):
    store, run, model, runner, state = setup_run(tmp_path, [{"content": "结果是 42。"}])
    state["user_input"] = question
    result = runner.run_bounded(run, "owner", context=ToolContext(), answer_state=state, answer_generator=lambda _: "")
    assert result["task"]["status"] == "degraded"
    assert any(check["id"] == "math_support" and check["status"] == "unverified" for check in result["task"]["verification"]["checks"])


def test_resume_prefers_committed_sql_receipt_and_rejects_repeated_id(tmp_path):
    from langchain_core.messages import HumanMessage, messages_to_dict
    from backend.services.agent_runtime.runner import FixedRunner
    from backend.services.agent_runtime.contracts import FixedAction
    store, run, model, runner, state = setup_run(tmp_path, SUCCESS)
    store.save_native_messages(run, "owner", messages_to_dict([HumanMessage(content="计算 2^10"), AIMessage(**SUCCESS[0])]))
    FixedRunner(store, runner.registry, allowlist=frozenset({"symbolic_math"})).execute(run, "owner",
        FixedAction("call", tool_id="symbolic_math", args=SUCCESS[0]["tool_calls"][0]["args"], operation_key="native-1-calc-1"), context=ToolContext())
    store.close(run, "owner", outcome="paused", error_code="interrupted")
    paused = store.snapshot(run)
    new = store.resume("rtask_math", expected_revision=paused["task_revision"], request_key="resume",
        request_id="resume", owner_token="new-owner", turn_id="turn")
    model.responses = [SUCCESS[0]]  # Same provider ID must be rejected, not executed twice.
    result = runner.run_bounded(new["run"]["id"], "new-owner", context=ToolContext())
    restored = next(m for m in model.received[0] if isinstance(m, ToolMessage))
    assert json.loads(restored.content)["success"] is True
    assert json.loads(restored.content)["data"]["result"]["exact"] == "1024"
    assert result["consumed_calls"] == 1
    assert result["run"]["error_code"] == "duplicate_native_call_id"


def test_model_timeout_never_publishes_late_answer(tmp_path):
    store, run, model, runner, state = setup_run(tmp_path, [{"content": "结果是 1024。"}])
    model.delays = .1
    runner.model_timeout_seconds = .02
    result = runner.run_bounded(run, "owner", context=ToolContext())
    assert result["run"]["status"] == "failed"
    time.sleep(.3)
    assert store.snapshot(run)["run"]["output"] is None
