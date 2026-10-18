"""Production LangChain wire -> native loop -> FixedRunner -> SQL, no network."""
import json
import httpx
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage, messages_to_dict
from backend.tools.registry import ToolContext
from llm.agent_adapter import NativeToolAdapter
from llm.configuration import resolve_model_role
from llm.deepseek_chat import DeepSeekChatOpenAI, PrivateProtocol, DeepSeekProtocolError, _protocol, private_protocol_scope
from tests.test_native_math_loop import setup_run, SUCCESS

PRIVATE = "PRIVATE_REASONING_NEVER_EXPORT"


def completion(content="结果是 1024。", calls=None, reasoning=PRIVATE, finish=None):
    delta = {"role": "assistant", "content": content, "reasoning_content": reasoning}
    if calls:
        delta["tool_calls"] = [{"index": i, "id": c["id"], "type": "function",
            "function": {"name": c["name"], "arguments": json.dumps(c["args"])}} for i, c in enumerate(calls)]
    return [
        {"id": "wire", "model": "deepseek-flash", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {"id": "wire", "model": "deepseek-flash", "choices": [{"index": 0, "delta": {}, "finish_reason": finish or ("tool_calls" if calls else "stop")}]},
        {"id": "wire", "model": "deepseek-flash", "choices": [], "usage": {"prompt_tokens": 100,
            "completion_tokens": 50, "total_tokens": 150, "completion_tokens_details": {"reasoning_tokens": 20}}},
    ]


def wire_run(tmp_path, responses, *, budget_calls=3, budget_model_calls=5, on_output=None):
    store, run, _, runner, state = setup_run(tmp_path, [SUCCESS[-1]], budget_calls=budget_calls,
        budget_model_calls=budget_model_calls, on_output=on_output)
    requests = []
    def transport(request):
        body = json.loads(request.content)
        requests.append(body)
        chunks = responses[len(requests)-1]
        stream = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=stream)
    resolved = resolve_model_role("reasoning", {"LLM_REASONING_PROVIDER": "deepseek",
        "LLM_REASONING_MODEL": "deepseek-flash", "DEEPSEEK_API_KEY": "fake-test-key"})
    model = DeepSeekChatOpenAI(model="deepseek-flash", api_key="fake-test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(transport)), stream_usage=True,
        streaming=True, extra_body=resolved.options["extra_body"])
    runner.adapter = NativeToolAdapter(resolved, runner.registry, model_factory=lambda *a, **k: model)
    runner.adapter.allow_native_attempt = True
    return store, run, runner, state, requests


def execute(store, run, runner, state):
    return runner.run_bounded(run, "owner", context=ToolContext(), answer_state=state,
        answer_generator=lambda _: pytest.fail("no second generation"))


def test_native_output_allowance_honors_smaller_explicit_cap(tmp_path):
    store, run, runner, state, requests = wire_run(tmp_path, [completion()])
    model = runner.adapter.model_factory().model_copy(update={"max_tokens": 512})
    runner.adapter.model_factory = lambda *a, **k: model
    result = execute(store, run, runner, state)
    assert result["run"]["status"] == "completed"
    assert requests[0]["max_tokens"] == 512


@pytest.mark.parametrize("calls", [[], [SUCCESS[0]["tool_calls"][0]],
    [SUCCESS[0]["tool_calls"][0], SUCCESS[1]["tool_calls"][0]]])
def test_real_adapter_single_multi_and_plain_stream(tmp_path, calls):
    deltas = []
    responses = [completion("正在计算。" if calls else "结果是 1024。", calls)]
    if calls:
        responses.append(completion(reasoning=""))  # zero new thinking final round
    store, run, runner, state, requests = wire_run(tmp_path, responses,
        on_output=lambda text, replace: deltas.append(text))
    result = execute(store, run, runner, state)
    assert result["run"]["status"] == "completed", result["run"]["error_code"]
    assert result["consumed_calls"] == len(calls)
    assert result["consumed_model_calls"] == len(responses)
    assert "max_tokens" in requests[0] and "max_completion_tokens" not in requests[0]
    assert requests[0]["max_tokens"] == 8192
    assert requests[0]["extra_body"] if "extra_body" in requests[0] else requests[0]["thinking"] == {"type": "enabled"}
    if calls:
        assistants = [m for m in requests[1]["messages"] if m["role"] == "assistant"]
        assert assistants[0]["reasoning_content"] == PRIVATE
        assert [c["id"] for c in assistants[0]["tool_calls"]] == [c["id"] for c in calls]
        tools = [m for m in requests[1]["messages"] if m["role"] == "tool"]
        assert [m["tool_call_id"] for m in tools] == [c["id"] for c in calls]
        assert all(json.loads(m["content"])["success"] for m in tools)
    assert PRIVATE not in json.dumps(result) + "".join(deltas)
    assert PRIVATE.encode() not in store.db_path.read_bytes()
    assert _protocol.get() is None
    completed = [e for e in result["execution_events"] if e["payload"].get("lifecycle") == "model.completed"]
    assert completed[0]["payload"]["performance"]["reasoning_tokens"] == 20


def test_multiround_replays_all_native_assistant_reasoning(tmp_path):
    responses = [completion("", SUCCESS[0]["tool_calls"]), completion("", SUCCESS[1]["tool_calls"], "second-private"), completion(reasoning="")]
    store, run, runner, state, requests = wire_run(tmp_path, responses)
    result = execute(store, run, runner, state)
    assert result["run"]["status"] == "completed"
    assert [m["reasoning_content"] for m in requests[2]["messages"] if m["role"] == "assistant"] == [PRIVATE, "second-private"]
    assert result["task"]["verification"]["status"] == "passed"


def test_schema_error_is_failed_native_tool_message_then_legal_continuation(tmp_path):
    bad = {**SUCCESS[0]["tool_calls"][0], "args": {"operation": "invalid", "expression": "2"}}
    store, run, runner, state, requests = wire_run(tmp_path, [completion("", [bad]), completion("计算失败。", reasoning="")])
    result = execute(store, run, runner, state)
    tool = next(m for m in requests[1]["messages"] if m["role"] == "tool")
    assert tool["tool_call_id"] == bad["id"] and not json.loads(tool["content"])["success"]
    assert result["task"]["status"] != "completed"


@pytest.mark.parametrize("bad", ["duplicate", "unknown", "missing"])
def test_whole_batch_rejected_before_any_execution(tmp_path, bad):
    calls = [dict(SUCCESS[0]["tool_calls"][0]), dict(SUCCESS[1]["tool_calls"][0])]
    if bad == "duplicate": calls[1]["id"] = calls[0]["id"]
    elif bad == "unknown": calls[1]["name"] = "unauthorized"
    else: calls[1]["id"] = ""
    store, run, runner, state, requests = wire_run(tmp_path, [completion("", calls)])
    result = execute(store, run, runner, state)
    assert result["run"]["status"] == "failed"
    assert result["consumed_calls"] == 0 and len(requests) == 1


def test_budget_failure_fences_presubmitted_batch(tmp_path):
    calls = [SUCCESS[0]["tool_calls"][0], SUCCESS[1]["tool_calls"][0],
        {**SUCCESS[0]["tool_calls"][0], "id": "third"}]
    store, run, runner, state, requests = wire_run(tmp_path, [completion("", calls)], budget_calls=1)
    result = execute(store, run, runner, state)
    assert result["run"]["status"] == "failed"
    assert result["run"]["error_code"] == "tool_budget_exhausted"
    assert result["consumed_calls"] == 1
    assert len(result["tool_calls"]) == 1 and result["tool_calls"][0]["status"] == "succeeded"
    assert len(requests) == 1


@pytest.mark.parametrize("identity", ["missing", "changed", "same"])
def test_checkpoint_recovery_never_replays_without_private_state(tmp_path, identity):
    store, run, runner, state, requests = wire_run(tmp_path, [completion()])
    native = messages_to_dict([HumanMessage(content="计算"), AIMessage(**SUCCESS[0])])
    stamp = runner.adapter.protocol_identity()
    if identity == "changed": stamp = {**stamp, "model": "other"}
    store.save_native_messages(run, "owner", native, protocol_identity=None if identity == "missing" else stamp)
    store.close(run, "owner", outcome="paused", error_code="process_restarted")
    old = store.snapshot(run)
    resumed = store.resume("rtask_math", expected_revision=old["task_revision"], request_key="resume",
        request_id="resume", owner_token="owner", turn_id="turn")
    result = execute(store, resumed["run"]["id"], runner, state)
    assert result["run"]["error_code"] == {"missing": "native_protocol_identity_missing",
        "changed": "native_model_changed", "same": "provider_protocol_state_lost"}[identity]
    assert requests == [] and result["consumed_calls"] == result["consumed_model_calls"] == 0
    assert store.snapshot(run)["run"]["status"] == "paused"


def test_copied_scope_cannot_refill_after_close():
    from contextvars import copy_context
    with private_protocol_scope() as state:
        copied = copy_context()
        state.consume(PRIVATE)
        state.commit(AIMessage(content="public", id="one"))
    assert state._messages == {} and state._parts == []
    with pytest.raises(DeepSeekProtocolError, match="provider_protocol_state_lost"):
        copied.run(lambda: _protocol.get().consume("late-private"))
    assert state._messages == {} and state._parts == []


def test_nonstream_private_field_stays_outside_messages_and_requires_original_state():
    model = DeepSeekChatOpenAI(model="deepseek-flash", api_key="fake", extra_body={"thinking": {"type": "enabled"}})
    with private_protocol_scope() as state:
        state.begin()
        result = model._create_chat_result({"choices": [{"message": {"role": "assistant", "content": "public",
            "reasoning_content": PRIVATE}, "finish_reason": "stop"}]})
        ai = result.generations[0].message
        ai.id = "native"
        state.commit(ai)
        assert PRIVATE not in ai.model_dump_json()
        payload = model._get_request_payload([ai, HumanMessage(content="continue")], tools=[{}], max_tokens=4096)
        assert payload["messages"][0]["reasoning_content"] == PRIVATE
    with pytest.raises(DeepSeekProtocolError):
        model._get_request_payload([ai], tools=[{}])


def test_factory_keeps_qwen_default_and_isolates_cached_models():
    from llm.factory import build_chat_model
    from langchain_openai import ChatOpenAI
    qwen = resolve_model_role("reasoning", {})
    ds = resolve_model_role("reasoning", {"LLM_REASONING_PROVIDER": "deepseek", "LLM_REASONING_MODEL": "deepseek-flash"})
    assert qwen.model == "qwen3.7-plus"
    assert type(build_chat_model(qwen, 0)) is ChatOpenAI
    assert isinstance(build_chat_model(ds, 0), DeepSeekChatOpenAI)
    assert PRIVATE not in repr(build_chat_model(ds, 0))


def test_cancel_after_first_tool_stops_rest_of_batch(tmp_path, monkeypatch):
    calls = [SUCCESS[0]['tool_calls'][0], SUCCESS[1]['tool_calls'][0]]
    store, run, runner, state, requests = wire_run(tmp_path, [completion('', calls)])
    original = store.finish_tool
    def stop(*args, **kwargs):
        result = original(*args, **kwargs)
        store.close(run, 'owner', outcome='paused', error_code='user_stop')
        return result
    monkeypatch.setattr(store, 'finish_tool', stop)
    result = execute(store, run, runner, state)
    assert result['run']['status'] == 'paused'
    assert len(requests) == len(result['tool_calls']) == 1
    assert result['tool_calls'][0]['status'] == 'succeeded'
    assert result['run']['output'] is None


def test_checkpoint_failure_after_first_receipt_stops_batch(tmp_path, monkeypatch):
    store, run, runner, state, requests = wire_run(tmp_path, [completion('',
        [SUCCESS[0]['tool_calls'][0], SUCCESS[1]['tool_calls'][0]])])
    original = store.save_native_messages
    def fail(run_id, owner, messages, **kwargs):
        if any(m['type'] == 'tool' for m in messages):
            raise ValueError('fixture checkpoint failure')
        return original(run_id, owner, messages, **kwargs)
    monkeypatch.setattr(store, 'save_native_messages', fail)
    result = execute(store, run, runner, state)
    assert result['run']['status'] == 'failed'
    assert len(requests) == len(result['tool_calls']) == 1
    assert result['tool_calls'][0]['status'] == 'succeeded'


def test_model_timeout_clears_private_state_before_late_delta(tmp_path, monkeypatch):
    import time
    import llm.deepseek_chat as provider
    captured = []
    old_init = provider.PrivateProtocol.__init__
    def capture(self):
        old_init(self)
        captured.append(self)
    monkeypatch.setattr(provider.PrivateProtocol, '__init__', capture)
    store, run, runner, state, requests = wire_run(tmp_path, [completion()])
    model = runner.adapter.model_factory()
    original = model.client.create
    def slow(**kwargs):
        time.sleep(.12)
        return original(**kwargs)
    monkeypatch.setattr(model.client, 'create', slow)
    runner.model_timeout_seconds = .03
    result = execute(store, run, runner, state)
    assert result['run']['error_code'] == 'model_deadline_exceeded'
    time.sleep(.2)
    assert captured[0]._closed and captured[0]._parts == [] and captured[0]._messages == {}
    assert store.snapshot(run)['run']['output'] is None


def test_truncated_response_never_executes_tools_and_preserves_numeric_usage(tmp_path):
    store, run, runner, state, requests = wire_run(tmp_path, [completion('', SUCCESS[0]['tool_calls'], finish='length')])
    result = execute(store, run, runner, state)
    assert result['run']['error_code'] == 'provider_output_truncated'
    assert result['consumed_calls'] == 0
    completed = next(e for e in result['execution_events'] if e['payload'].get('lifecycle') == 'model.completed')
    assert completed['payload']['performance']['output_tokens'] == 50


def test_missing_reasoning_tool_round_fails_before_execution(tmp_path):
    chunks = completion('', SUCCESS[0]['tool_calls'])
    chunks[0]['choices'][0]['delta'].pop('reasoning_content')
    store, run, runner, state, requests = wire_run(tmp_path, [chunks])
    result = execute(store, run, runner, state)
    assert result['run']['error_code'] == 'provider_protocol_invalid'
    assert result['consumed_calls'] == 0


def test_sdk_exception_is_sanitized_before_callback(tmp_path):
    from langchain_core.callbacks import BaseCallbackHandler
    seen = []
    class Errors(BaseCallbackHandler):
        def on_llm_error(self, error, **kwargs):
            seen.append(str(error))
    def transport(request):
        return httpx.Response(400, json={'error': {'message': PRIVATE, 'type': 'bad_request'}})
    model = DeepSeekChatOpenAI(model='deepseek-flash', api_key='fake', streaming=True, max_retries=0,
        callbacks=[Errors()], http_client=httpx.Client(transport=httpx.MockTransport(transport)))
    with pytest.raises(DeepSeekProtocolError, match='provider_request_failed'):
        list(model.stream([HumanMessage(content='public')]))
    assert seen == ['provider_request_failed']


def test_concurrent_scopes_share_client_without_protocol_crosstalk():
    from concurrent.futures import ThreadPoolExecutor
    import threading
    barrier = threading.Barrier(2)
    model = DeepSeekChatOpenAI(model='deepseek-flash', api_key='fake')
    def run(identity):
        with private_protocol_scope() as state:
            state.begin()
            state.consume(identity)
            ai = AIMessage(content='public', id='same-id')
            state.commit(ai)
            barrier.wait(timeout=2)
            wire = model._get_request_payload([ai], tools=[{}])
            return wire['messages'][0]['reasoning_content']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(run, ['private-A', 'private-B'])) == ['private-A', 'private-B']
    assert _protocol.get() is None


def test_private_capacity_limit_fails_without_truncating_replay():
    state = PrivateProtocol()
    with pytest.raises(DeepSeekProtocolError, match='provider_protocol_budget_exhausted'):
        state.consume('x' * (1024 * 1024 + 1))
    state.close()
    assert state._messages == {} and state._parts == []


def test_restart_recovery_retains_receipt_and_never_reexecutes(tmp_path):
    import subprocess
    import sys
    from backend.services.agent_runtime.runner import FixedRunner
    from backend.services.agent_runtime.contracts import FixedAction
    store, run, runner, state, requests = wire_run(tmp_path, [completion()])
    store.save_native_messages(run, 'owner', messages_to_dict([HumanMessage(content='计算'), AIMessage(**SUCCESS[0])]),
        protocol_identity=runner.adapter.protocol_identity())
    FixedRunner(store, runner.registry, allowlist=frozenset({'symbolic_math'})).execute(run, 'owner',
        FixedAction('call', tool_id='symbolic_math', args=SUCCESS[0]['tool_calls'][0]['args'],
            operation_key='native-1-calc-1'), context=ToolContext())
    script = 'from backend.services.agent_runtime.store import RuntimeStore; import sys; assert RuntimeStore(sys.argv[1]).recover_unfinished()==1'
    subprocess.run([sys.executable, '-c', script, str(store.db_path)], check=True, timeout=10)
    old = store.snapshot(run)
    resumed = store.resume('rtask_math', expected_revision=old['task_revision'], request_key='resume',
        request_id='resume', owner_token='owner', turn_id='turn')
    result = execute(store, resumed['run']['id'], runner, state)
    assert result['run']['error_code'] == 'provider_protocol_state_lost'
    assert result['consumed_calls'] == 1 and result['tool_calls'][0]['attempt_count'] == 1
    assert requests == []


def test_fragmented_reasoning_and_tool_arguments_are_preserved():
    model = DeepSeekChatOpenAI(model='deepseek-flash', api_key='fake')
    with private_protocol_scope() as state:
        state.begin()
        chunks = []
        for delta in [{'role': 'assistant', 'reasoning_content': 'private-'},
                      {'reasoning_content': 'tail', 'content': '公开', 'tool_calls': [{'index': 0, 'id': 'one', 'type': 'function', 'function': {'name': 'symbolic_math', 'arguments': '{"operation":'}}]},
                      {'tool_calls': [{'index': 0, 'function': {'arguments': '"calculate","expression":"2"}'}}]}]:
            chunks.append(model._convert_chunk_to_generation_chunk({'choices': [{'index': 0, 'delta': delta}]}, AIMessageChunk, None))
        merged = chunks[0] + chunks[1] + chunks[2]
        ai = AIMessage(content=merged.message.content, tool_calls=merged.message.tool_calls, id='lc-id')
        state.commit(ai)
        assert state.reasoning(ai) == 'private-tail'
        assert ai.tool_calls[0]['args']['expression'] == '2'
        assert 'private-tail' not in ai.model_dump_json()


def test_interrupted_delivery_is_read_only_bounded_projection(tmp_path):
    from backend.services.agent_runtime.chat_binding import overlay_runtime_delivery
    store, run, runner, state, requests = wire_run(tmp_path, [completion()])
    store.close(run, 'owner', outcome='paused', error_code='user_stop')
    data = {'id': 'session', 'messages': [{'id': 'user', 'role': 'user', 'turn_id': 'turn', 'content': '计算'}],
        'page': {'total': 1, 'next_before_seq': 1}}
    before = store.snapshot(run)
    result = overlay_runtime_delivery(data, store=store)
    assert len(result['messages']) == 2 and result['page'] == data['page']
    assistant = result['messages'][1]
    assert assistant['runtime_delivery_projection'] and assistant['learning_task']['resumable']
    assert len(data['messages']) == 1 and store.snapshot(run) == before
    assert overlay_runtime_delivery(result, store=store)['messages'] == result['messages']
    assert overlay_runtime_delivery({**data, 'messages': []}, store=store)['messages'] == []
    real = {**data, 'messages': [data['messages'][0], {'id': assistant['id'], 'role': 'assistant',
        'turn_id': 'turn', 'content': 'authoritative final'}]}
    assert overlay_runtime_delivery(real, store=store)['messages'] == real['messages']


def test_delivery_projection_failure_keeps_message_page(tmp_path, monkeypatch):
    from backend.services.agent_runtime.chat_binding import overlay_runtime_delivery
    store, run, runner, state, requests = wire_run(tmp_path, [completion()])
    def unavailable(*args):
        raise OSError('fixture')
    monkeypatch.setattr(store, 'turn_snapshots', unavailable)
    data = {'id': 'session', 'messages': [{'role': 'user', 'turn_id': 'turn'}], 'page': {'total': 1}}
    result = overlay_runtime_delivery(data, store=store)
    assert result['messages'] == data['messages'] and result['runtime_projection_error'] == 'unavailable'


def test_out_of_order_toolnode_entry_still_executes_in_native_order(tmp_path, monkeypatch):
    import time
    import backend.services.agent_runtime.native_loop as loop
    original = loop.create_agent
    entered = []
    def instrument(model, *, tools, middleware):
        wrapped = middleware[0].wrap_tool_call
        def delayed(request, handler):
            if request.tool_call['id'] == 'calc-1':
                time.sleep(.06)
            entered.append(request.tool_call['id'])
            return wrapped(request, handler)
        middleware[0].wrap_tool_call = delayed
        return original(model, tools=tools, middleware=middleware)
    monkeypatch.setattr(loop, 'create_agent', instrument)
    store, run, runner, state, requests = wire_run(tmp_path,
        [completion('', [SUCCESS[0]['tool_calls'][0], SUCCESS[1]['tool_calls'][0]]), completion(reasoning='')])
    result = execute(store, run, runner, state)
    assert entered == ['verify-2', 'calc-1']
    assert [c['tool_id'] for c in result['tool_calls']] == ['symbolic_math', 'verify_math_result']
    assert result['run']['status'] == 'completed'


def test_cached_input_usage_and_async_public_delta_are_safe():
    import asyncio
    model = DeepSeekChatOpenAI(model='deepseek-flash', api_key='fake')
    chunk = model._convert_chunk_to_generation_chunk({'choices': [], 'usage': {
        'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150,
        'prompt_cache_hit_tokens': 80}}, AIMessageChunk, None)
    assert chunk.message.usage_metadata['input_token_details']['cache_read'] == 80
    async def run():
        async def transport(request):
            chunks = completion()
            return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                content=''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks) + 'data: [DONE]\n\n')
        client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        model = DeepSeekChatOpenAI(model='deepseek-flash', api_key='fake', http_async_client=client)
        received = [c async for c in model.astream([HumanMessage(content='question')])]
        assert PRIVATE not in ''.join(c.model_dump_json() for c in received)
        assert ''.join(c.content for c in received) == '结果是 1024。'
        await client.aclose()
    asyncio.run(run())


def test_qwen_native_multitool_wire_unchanged(tmp_path):
    from langchain_openai import ChatOpenAI
    store, run, runner, state, requests = wire_run(tmp_path,
        [completion('', [SUCCESS[0]['tool_calls'][0], SUCCESS[1]['tool_calls'][0]]), completion(reasoning='')])
    ds = runner.adapter.model_factory()
    resolved = resolve_model_role('reasoning', {'DASHSCOPE_API_KEY': 'fake'})
    model = ChatOpenAI(model='qwen3.7-plus', api_key='fake', client=ds.client, streaming=True,
        stream_usage=True, extra_body=resolved.options['extra_body'])
    runner.adapter = NativeToolAdapter(resolved, runner.registry, model_factory=lambda *a, **k: model)
    runner.adapter.allow_native_attempt = True
    result = execute(store, run, runner, state)
    assert result['task']['verification']['status'] == 'passed'
    assert requests[0]['model'] == 'qwen3.7-plus'
    assert requests[0]['enable_thinking'] is True
    assert 'max_completion_tokens' in requests[0] and 'max_tokens' not in requests[0]
    assert requests[0]['max_completion_tokens'] == 4096
    assert all('reasoning_content' not in m for m in requests[1]['messages'])

@pytest.mark.parametrize("grounded", [False, True])
@pytest.mark.parametrize("streaming", [False, True])
def test_teaching_ingress_shared_native_sql_evidence_before_stream(tmp_path, monkeypatch, grounded, streaming):
    import asyncio
    from types import SimpleNamespace
    import backend.conversation_memory as conversation
    from backend.services.agent_runtime import chat_binding as binding
    from backend.services.agent_runtime import textbook_tool
    from tests.test_agent_runtime_chat_binding import prepared
    from tests.test_agent_runtime_textbook import scope
    question = "给我讲解概念及适用条件" if grounded else "简要说明如何复习"
    answer = "概念定义及适用条件。[[cite:E1]]" if grounded else "按计划复习并检查理解。"
    store, _, runner, _, requests = wire_run(tmp_path, [completion(answer)])
    # No user-selected math tools for a teaching question.
    registry, adapter = runner.registry, runner.adapter
    observed = []
    frozen = scope()
    original = textbook_tool.register_textbook_search_runtime
    def register(registry, frozen):
        def retrieve(state, **kwargs):
            observed.append((state, kwargs))
            return {"evidence_items": [{"book_name": "main", "chunk_id": "a", "text": "概念定义及适用条件。"}],
                "evidence_support": {"status": "sufficient"}, "retrieval_status": "ok"}
        return original(registry, frozen, retrieve=retrieve, versions=lambda name: frozen["index_versions"][name])
    monkeypatch.setattr(textbook_tool, "register_textbook_search_runtime", register)
    monkeypatch.setattr(textbook_tool, "freeze_textbook_scope", lambda *a: frozen)
    monkeypatch.setattr(binding, "model_requires_native_transcript", lambda: True)
    monkeypatch.setattr(binding, "runtime_store", lambda **kw: store)
    monkeypatch.setattr(binding, "build_math_registry", lambda: registry)
    monkeypatch.setattr(binding, "build_adapter", lambda _: adapter)
    monkeypatch.setattr(binding, "generate_answer", lambda _: pytest.fail("second generation"))
    monkeypatch.setattr(binding, "project_outcomes", lambda _: None)
    monkeypatch.setattr(conversation, "append_message", lambda *a, **k: {})
    data = {**prepared(), "rewritten_question": question, "conversation_id": "teaching", "turn_id": "teaching-turn",
        "book_name": "main" if grounded else "", "subject": "数学" if grounded else "",
        "use_textbook_context": grounded, "answer_mode": "textbook_grounded" if grounded else "global_general"}
    response = binding.try_chat_response(SimpleNamespace(question=question), data, "teaching-req", streaming=streaming)
    assert response is not None
    if streaming:
        async def consume():
            items = [json.loads(item[6:]) async for item in response.body_iterator]
            await response.aclose()
            return items
        items = asyncio.run(consume())
        task_id = items[-1]["execution_event"]["task_id"]
        if grounded:
            chapter = next(i for i, item in enumerate(items) if item.get("stage") == "chapter")
            public = next(i for i, item in enumerate(items) if item.get("execution_event", {}).get("type") == "output_delta")
            assert chapter < public
    else:
        task_id = response["learning_task"]["id"]
    snapshot = store.task_snapshot(task_id)
    assert snapshot["run"]["status"] in {"completed", "degraded"}
    assert snapshot["consumed_model_calls"] == 1
    assert snapshot["consumed_calls"] == int(grounded)
    assert snapshot["run"]["checkpoint"]["candidates"] == []
    assert len(requests) == 1
    assert not requests[0].get("tools")
    if grounded:
        assert observed[0][1]["retrieval_resources_override"] == frozen["resources"]
        assert "概念定义及适用条件" in json.dumps(requests[0]["messages"], ensure_ascii=False)
        assert snapshot["task"]["artifacts"]["evidence_sources"][0]["chunk_id"] == "a"
        assert snapshot["tool_calls"][0]["tool_id"] == "search_textbook"
        assert snapshot["tool_calls"][0]["attempt_count"] == 1
    assert PRIVATE not in json.dumps(snapshot, ensure_ascii=False)

@pytest.mark.parametrize("failure", ["schema", "index", "missing"])
def test_native_evidence_preparation_rejects_before_model(tmp_path, failure):
    from backend.services.agent_runtime.textbook_tool import register_textbook_search_runtime
    from tests.test_agent_runtime_textbook import scope
    store, run, runner, _, requests = wire_run(tmp_path, [completion()])
    runner.candidate_tools = ()
    frozen = scope()
    register_textbook_search_runtime(runner.registry, frozen,
        versions=lambda name: "changed" if failure == "index" else frozen["index_versions"][name],
        retrieve=lambda *a, **k: {"evidence_items": [], "evidence_support": {"status": "insufficient"}})
    metadata = runner.registry.runtime_tool("search_textbook").runtime_metadata()
    ref = {k: metadata[k] for k in ("id", "version", "schema_hash")}
    if failure == "schema":
        ref["schema_hash"] = "changed"
    state = {"user_input": "讲解概念", "answer_mode": "textbook_grounded", "use_textbook_context": True,
        "intent": "teach", "_runtime_textbook_scope": frozen, "_native_preparation_ref": ref}
    result = runner.run_bounded(run, "owner", context=ToolContext(book_name="main", subject="数学"),
        answer_state=state, answer_generator=lambda _: pytest.fail("no fallback"))
    assert result["run"]["status"] == "failed"
    assert result["consumed_model_calls"] == 0 and requests == []
    assert result["consumed_calls"] == int(failure == "missing")
    assert result["run"]["error_code"] == {"schema": "answer_scope_changed", "index": "answer_scope_changed",
        "missing": "answer_evidence_missing"}[failure]


def test_native_evidence_pause_before_model_reuses_sql_receipt(tmp_path, monkeypatch):
    from backend.services.agent_runtime.textbook_tool import register_textbook_search_runtime
    from tests.test_agent_runtime_textbook import scope
    store, run, runner, _, requests = wire_run(tmp_path, [completion("概念定义。[[cite:E1]]")])
    runner.candidate_tools = ()
    frozen = scope()
    retrieved = []
    def retrieve(*a, **k):
        retrieved.append(True)
        return {"evidence_items": [{"book_name": "main", "chunk_id": "a", "text": "概念定义。"}],
            "evidence_support": {"status": "sufficient"}, "retrieval_status": "ok"}
    register_textbook_search_runtime(runner.registry, frozen, retrieve=retrieve,
        versions=lambda name: frozen["index_versions"][name])
    metadata = runner.registry.runtime_tool("search_textbook").runtime_metadata()
    state = {"user_input": "讲解概念", "answer_mode": "textbook_grounded", "use_textbook_context": True,
        "intent": "teach", "_runtime_textbook_scope": frozen,
        "_native_preparation_ref": {k: metadata[k] for k in ("id", "version", "schema_hash")}}
    store.configure_chat(run, "owner", state=state, candidates=(), request_question="讲解概念", book_name="main", subject="数学")
    original = store.finish_tool
    def finish(*a, **k):
        original(*a, **k)
        return store.close(run, "owner", outcome="paused", error_code="user_stop")
    monkeypatch.setattr(store, "finish_tool", finish)
    context = ToolContext(book_name="main", subject="数学")
    result = runner.run_bounded(run, "owner", context=context, answer_state=state, answer_generator=lambda _: "")
    assert result["run"]["status"] == "paused" and requests == []
    monkeypatch.setattr(store, "finish_tool", original)
    resumed = store.resume("rtask_math", request_key="resume", request_id="resume", owner_token="new",
        expected_revision=result["task_revision"], turn_id="turn")
    result = runner.run_bounded(resumed["run"]["id"], "new", context=context,
        answer_state=state, answer_generator=lambda _: pytest.fail("no fallback"))
    assert result["run"]["status"] in {"completed", "degraded"}, result["run"]["error_code"]
    assert len(retrieved) == 1 and len(requests) == 1
    assert result["consumed_calls"] == 1 and result["tool_calls"][0]["attempt_count"] == 1
