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
            if response.get("content"):
                yield ChatGenerationChunk(message=AIMessageChunk(content=response["content"]))
            for call_index, tool_call in enumerate(calls):
                args = json.dumps(tool_call["args"])
                for index, part in enumerate([args[:len(args)//2], args[len(args)//2:]]):
                    yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[{
                        "name": tool_call["name"] if index == 0 else None, "id": tool_call["id"] if index == 0 else None,
                        "args": part, "index": call_index}]))
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


def test_tool_boundary_preserves_public_derivation_and_final_verification(tmp_path):
    deltas = []
    responses = [{**SUCCESS[0], "content": "CDF 推导：F_M(x)=F(x)^n。"}, SUCCESS[-1]]
    store, run, model, runner, state = setup_run(tmp_path, responses,
        on_output=lambda text, replace: deltas.append((text, replace)))
    state["required_outputs"] = []
    result = runner.run_bounded(run, "owner", context=ToolContext(), answer_state=state, answer_generator=lambda _: pytest.fail("no extra generation"))
    assert not any(replace for _, replace in deltas)
    assert "CDF 推导" in "".join(text for text, _ in deltas)
    answer = result["run"]["output"]["answer"]
    assert "CDF 推导" in answer and "## 最终解答" in answer and "结果是 1024。" in answer
    assert result["task"]["verification"]["status"] == "unverified"
    assert any(x["id"] == "interim_delivery" for x in result["task"]["verification"]["unverified"])
    from backend.services.agent_runtime.native_loop import PUBLIC_DELIVERY_INSTRUCTION
    assert any(m.content == PUBLIC_DELIVERY_INSTRUCTION for m in model.received[1])


def test_public_interim_is_not_credited_as_complete_final_answer(tmp_path):
    from backend.services.agent_runtime.contracts import RunCommand
    store, run, model, runner, state = setup_run(tmp_path,
        [{**SUCCESS[0], "content": "CDF 推导已经完成。"}, SUCCESS[-1]])
    # The final required-output check must not pass on an earlier draft anchor.
    run = store.create(RunCommand("request2", "request2", "rtask_math2", "session", "turn2", "计算 2^10", "owner",
        budget_calls=3, budget_model_calls=4,
        required_outputs=[{"id": "distribution", "kind": "question_part", "anchors": ["CDF"], "required": True}]))["run"]["id"]
    result = runner.run_bounded(run, "owner", context=ToolContext(), answer_state=state, answer_generator=lambda _: pytest.fail("no extra generation"))
    assert result["task"]["verification"]["status"] == "failed"
    assert any(x["id"] == "distribution" for x in result["task"]["verification"]["failures"])
    assert "CDF" in result["run"]["output"]["answer"]


def test_public_interim_excludes_previous_turn_and_private_reasoning():
    from backend.services.agent_runtime.native_loop import _public_interim_text
    from langchain_core.messages import HumanMessage
    before = AIMessage(**{**SUCCESS[0], "content": "旧题推导"})
    current = AIMessage(**{**SUCCESS[0], "content": "<think>隐藏推理</think>公开 CDF 推导",
        "additional_kwargs": {"reasoning_content": "供应商隐藏推理"}})
    assert _public_interim_text([before, HumanMessage(content="新题"), current,
        ToolMessage(content="工具内部回执", tool_call_id="calc-1"), AIMessage(content="最终正文")]) == "公开 CDF 推导"


def test_resumed_public_interim_survives_final_delivery(tmp_path):
    from langchain_core.messages import HumanMessage, messages_to_dict
    store, run, model, runner, state = setup_run(tmp_path, [SUCCESS[-1]])
    pending = AIMessage(**{**SUCCESS[0], "content": "恢复前的 CDF 推导。"})
    store.save_native_messages(run, "owner", messages_to_dict([HumanMessage(content="计算 2^10"), pending]), protocol_identity=runner.adapter.protocol_identity())
    store.close(run, "owner", outcome="paused", error_code="interrupted")
    paused = store.snapshot(run)
    resumed = store.resume("rtask_math", expected_revision=paused["task_revision"], request_key="resume",
        request_id="resume", owner_token="new-owner", turn_id="turn")
    result = runner.run_bounded(resumed["run"]["id"], "new-owner", context=ToolContext(), answer_state=state, answer_generator=lambda _: pytest.fail("no extra generation"))
    assert "恢复前的 CDF 推导。" in result["run"]["output"]["answer"]
    assert result["consumed_calls"] == 0


def test_sse_final_replacement_preserves_tool_preamble(tmp_path, monkeypatch):
    import asyncio
    import backend.conversation_memory as conversation
    from backend.services.agent_runtime import chat_binding as binding
    responses = [{**SUCCESS[0], "content": "CDF 推导：F_M(x)=F(x)^n。"}, SUCCESS[-1]]
    store, run, model, runner, state = setup_run(tmp_path, responses)
    state["native_loop"] = True
    store.configure_chat(run, "owner", state=state, candidates=runner.candidate_tools,
        request_question="计算 2^10", book_name="", subject="数学")
    monkeypatch.setattr(conversation, "append_message", lambda *a, **k: {})
    monkeypatch.setattr(binding, "project_outcomes", lambda _: None)
    async def check():
        response = binding.stream_run(store, run, "owner", runner.registry, runner.adapter)
        events = [json.loads(data[6:])["execution_event"] async for data in response.body_iterator]
        await response.aclose()
        replacements = [e for e in events if e["type"] == "output_delta" and e["payload"]["replace"]]
        assert len(replacements) == 1
        assert "CDF 推导" in replacements[0]["payload"]["text"]
        assert replacements[0]["payload"]["text"] == store.snapshot(run)["run"]["output"]["answer"]
        assert events[-1]["type"] == "final"
    asyncio.run(check())


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
    store.save_native_messages(run, "owner", messages_to_dict([HumanMessage(content="计算 2^10"), pending]), protocol_identity=runner.adapter.protocol_identity())
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
    monkeypatch.setenv("TEXA_NATIVE_MODEL_TIMEOUT", "80")
    monkeypatch.setenv("TEXA_NATIVE_RUN_TIMEOUT", "200")
    response = binding.try_chat_response(SimpleNamespace(question="计算 2^10"),
        {**prepared(), "rewritten_question": "计算 2^10", "use_textbook_context": True,
            "answer_mode": "textbook_grounded", "scope_reason": "book_selected"}, "ingress", streaming=streaming)
    monkeypatch.setenv("TEXA_NATIVE_MODEL_TIMEOUT", "150")
    monkeypatch.setenv("TEXA_NATIVE_RUN_TIMEOUT", "500")
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
    assert snapshot["run"]["checkpoint"]["answer_state"]["_native_limits"] == {
        "model_timeout_seconds": 80, "run_timeout_seconds": 200}
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
    store.save_native_messages(run, "owner", messages_to_dict([HumanMessage(content="计算 2^10"), AIMessage(**SUCCESS[0])]), protocol_identity=runner.adapter.protocol_identity())
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
    assert result["run"]["error_code"] == "model_deadline_exceeded"
    time.sleep(.3)
    assert store.snapshot(run)["run"]["output"] is None


def test_native_reasoning_deadline_is_configurable_but_bounded(tmp_path):
    store, run, model, runner, state = setup_run(tmp_path, SUCCESS)
    runner.model_timeout_seconds = 180
    runner.run_timeout_seconds = 600
    result = runner.run_bounded(run, "owner", context=ToolContext(), answer_state=state,
        answer_generator=lambda _: pytest.fail("native must not call another generator"))
    assert result["run"]["status"] == "completed"
    assert result["consumed_model_calls"] == 3
    assert result["consumed_calls"] == 2


def test_cancel_fence_survives_model_tool_binding_and_stops_token_iteration(tmp_path):
    class ManyChunksModel(ScriptedMathModel):
        tokens: list = Field(default_factory=list)
        def _stream(self, messages, **kwargs):
            self.received.append(messages)
            for index in range(30):
                time.sleep(.02)
                self.tokens.append(index)
                yield ChatGenerationChunk(message=AIMessageChunk(content="结果是1024。"))
    store, run, old, runner, state = setup_run(tmp_path, [])
    model = ManyChunksModel(responses=[])
    runner.adapter = model_adapter(model, runner.registry)
    def stop(text, replace):
        if text and store.snapshot(run)["run"]["status"] == "running":
            store.close(run, "owner", outcome="paused", error_code="user_stop")
    runner.on_output = stop
    result = runner.run_bounded(run, "owner", context=ToolContext())
    assert result["run"]["status"] == "paused"
    time.sleep(.15)
    assert len(model.tokens) < 10, "cancel must stop actual iteration, not just hide late text"
    assert store.snapshot(run)["run"]["output"] is None


@pytest.mark.parametrize("model_timeout,run_timeout", [(0,120),(301,120),(35,0),(35,601)])
def test_native_deadline_rejects_unbounded_configuration(tmp_path, model_timeout, run_timeout):
    store, run, model, runner, state = setup_run(tmp_path, SUCCESS)
    runner.model_timeout_seconds = model_timeout
    runner.run_timeout_seconds = run_timeout
    with pytest.raises(ValueError, match="deadline"):
        runner.run_bounded(run, "owner", context=ToolContext())
    assert store.snapshot(run)["consumed_model_calls"] == 0


def test_profile_metadata_and_chunk_fence_do_not_read_full_snapshot(tmp_path, monkeypatch):
    store, run, model, runner, state = setup_run(tmp_path, [SUCCESS[-1]])
    # Reading the authority is independent of decoding messages/receipts/events.
    original = store._snapshot
    reads = []
    def counted(*args):
        reads.append(1)
        return original(*args)
    monkeypatch.setattr(store, '_snapshot', counted)
    store.assert_run_active(run, 'owner')
    assert not reads
    result = runner.run_bounded(run, 'owner', context=ToolContext(), answer_state=state, answer_generator=lambda _: pytest.fail('extra request'))
    completed = next(e for e in result['execution_events'] if e['payload'].get('lifecycle') == 'model.completed')
    perf = completed['payload']['performance']
    assert perf['handler_ms'] >= perf['first_chunk_ms'] >= 0
    assert perf['first_public_ms'] >= perf['first_chunk_ms']
    assert 'input_tokens' not in perf  # Missing usage is unknown, never zero.
    profile = next(e for e in result['execution_events'] if e['payload'].get('lifecycle') == 'runtime.profile')
    assert profile['payload']['performance']['verification_ms'] >= 0
    with pytest.raises(Exception, match='run stopped'):
        store.assert_run_active(run, 'owner')


def test_performance_payload_cannot_persist_provider_text(tmp_path):
    store, run, _, _, _ = setup_run(tmp_path, [SUCCESS[-1]])
    store.start_model_step(run, 'owner')
    store.complete_model_step(run, 'owner', action_kind='finish', transcript=[],
        performance={'first_chunk_ms': 10, 'reasoning_content': 'private', 'input_tokens': -1, 'handler_ms': float('nan')})
    event = store.events(run)[-1]
    assert event['payload']['performance'] == {'first_chunk_ms': 10}


def test_exact_original_delivery_requirements_survive_all_native_rounds(tmp_path):
    from pathlib import Path
    from langchain_core.messages import SystemMessage
    fixture = Path(__file__).resolve().parents[1] / 'docs/qa/evidence/native-tool-loop/paid-2026-10-13/extended-deadline/questions.json'
    original = next(q['question'] for q in json.loads(fixture.read_text()) if q['id'] == 'q3-estimation')
    responses = [call('symbolic_math', {'operation': 'integrate', 'expression': 'n*x^n/theta^n',
        'variable': 'x', 'lower': '0', 'upper': 'theta',
        'assumptions': {'theta': 'positive', 'n': 'positive'}}, 'moment'),
        {'content': r'最终结果为 $n\theta/(n+1)$。'}]
    store, run, model, runner, state = setup_run(tmp_path, responses)
    state.update(user_input='求最大次序统计量的均值', support_type='',
                 answer_mode='global_general', use_textbook_context=False)
    store.configure_chat(run, 'owner', state=state, candidates=runner.candidate_tools,
                         request_question=original, book_name='', subject='数学')
    result = runner.run_bounded(run, 'owner', context=ToolContext(), answer_state=state,
                               answer_generator=lambda _: pytest.fail('no additional review LLM'))
    assert len(model.received) == result['consumed_model_calls'] == 2
    for messages in model.received:
        reminders = [m for m in messages if isinstance(m, SystemMessage) and '本轮原题' in m.content]
        assert len(reminders) == 1  # no growing reminder history
        assert json.dumps(original, ensure_ascii=False) in reminders[0].content
        assert '请推导分布和所需矩' in reminders[0].content
        assert '不将数值核验扩大' in reminders[0].content
    returned = json.loads(next(m.content for m in model.received[1] if isinstance(m, ToolMessage)))
    receipt = result['tool_calls'][0]['result']
    assert returned['data'] == receipt['data']
    assert returned['warnings'] == receipt['warnings']
    assert returned['data']['result']['exact'] == 'n*theta/(n + 1)'
    assert returned['data']['assumptions'] == {'theta': 'positive', 'n': 'positive'}
    assert result['task']['verification']['status'] != 'passed'
    # This tests contract retention, not whether a real model follows it.


def test_unverified_conditions_are_delivered_to_model_without_upgrade(tmp_path):
    responses = [call('verify_math_result', {'kind': 'equivalence', 'left': 'x/x', 'right': '1'}, 'domain'),
                 {'content': '缺少非零条件，不能断言普遍成立。'}]
    store, run, model, runner, state = setup_run(tmp_path, responses)
    result = runner.run_bounded(run, 'owner', context=ToolContext(), answer_state=state,
                               answer_generator=lambda _: pytest.fail('no additional review LLM'))
    message = next(m for m in model.received[1] if isinstance(m, ToolMessage))
    returned = json.loads(message.content)
    assert not returned['success']
    assert returned['data']['status'] == 'unverified'
    assert returned['data']['limitations'] and returned['data']['scope']
    assert returned['verification']['passed'] is False
    assert result['task']['verification']['status'] != 'passed'


def test_superseded_math_contract_cannot_reuse_receipts_even_without_new_calls(tmp_path):
    store, run, model, runner, state = setup_run(tmp_path, [SUCCESS[-1]])
    runner.candidate_tools = tuple({**ref, 'version': 'superseded'} for ref in runner.candidate_tools)
    result = runner.run_bounded(run, 'owner', context=ToolContext(), answer_state=state,
                               answer_generator=lambda _: pytest.fail('no model on stale contract'))
    assert result['run']['error_code'] == 'tool_step_denied'
    assert result['consumed_model_calls'] == 0
    assert not model.received
