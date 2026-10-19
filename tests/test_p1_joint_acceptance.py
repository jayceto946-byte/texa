"""Recorded native batches at the production budget value, no network.

These exercise existing math candidates plus fixed retrieval, not chat routing.
"""
import asyncio
import json
from pathlib import Path
import pytest

from tests.test_agent_runtime_chat_binding import prepared
from tests.test_agent_runtime_textbook import scope
from tests.test_deepseek_production import wire_run, completion

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('case,expected', [('AB', 'failed'), ('sensor-B', 'degraded')])
def test_recorded_completion_batches_respect_production_budget(tmp_path, monkeypatch, case, expected):
    from backend.services.agent_runtime import chat_binding as binding, textbook_tool
    import backend.conversation_memory as conversation
    evidence = json.loads((ROOT / 'docs/qa/agent-loop-completion' / f'completion-{case}.json').read_text())
    calls = evidence['proposed_tools']
    answer = ('闭区间最值比较驻点与端点，最大18，最小-18。' if case == 'AB'
              else '灵敏度为7/30，约0.233 Ω/°C；仅在表中区间采用线性模型。')
    store, run, runner, _, requests = wire_run(tmp_path, [completion('', calls), completion(answer, reasoning='')],
                                             budget_calls=3)
    frozen = scope()
    original_register = textbook_tool.register_textbook_search_runtime

    def register(registry, actual_scope):
        original_register(registry, actual_scope,
            versions=lambda name: frozen['index_versions'][name],
            retrieve=lambda *a, **kw: {
                'evidence_items': [{'book_name': 'main', 'chunk_id': 'joint-anchor',
                                   'text': '闭区间连续函数比较驻点、不可导点及端点；灵敏度为输出变化与输入变化之比。'}],
                'evidence_support': {'status': 'sufficient'}, 'retrieval_status': 'joint-fixture'})

    monkeypatch.setattr(binding, 'model_requires_native_transcript', lambda: True)
    monkeypatch.setattr(binding, 'runtime_store', lambda **kw: store)
    monkeypatch.setattr(binding, 'build_math_registry', lambda: runner.registry)
    monkeypatch.setattr(binding, 'build_adapter', lambda _: runner.adapter)
    monkeypatch.setattr(binding, 'generate_answer', lambda _: pytest.fail('no implicit generation'))
    monkeypatch.setattr(binding, 'project_outcomes', lambda _: None)
    monkeypatch.setattr(conversation, 'append_message', lambda *a, **kw: {})
    monkeypatch.setattr(textbook_tool, 'freeze_textbook_scope', lambda *a: frozen)
    monkeypatch.setattr(textbook_tool, 'register_textbook_search_runtime', register)
    question = ('依据教材讲解闭区间最值，并计算和核验 f(x)=x^3-3*x 在[-3,3]的最值。' if case == 'AB'
                else '依据教材计算并核验表1.1的灵敏度，保留单位及线性条件。')
    state = {**prepared(), 'rewritten_question': question, 'conversation_id': 'joint-' + case,
             'turn_id': 'joint-turn-' + case, 'book_name': 'main', 'subject': '数学',
             'use_textbook_context': True, 'answer_mode': 'textbook_grounded'}
    register(runner.registry, frozen)
    meta = runner.registry.runtime_tool('search_textbook').runtime_metadata()
    state.update(user_input=question, native_loop=True, intent='qa',
                 _runtime_textbook_scope=frozen,
                 _native_preparation_ref={k: meta[k] for k in ('id', 'version', 'schema_hash')})
    store.configure_chat(run, 'owner', state=state, candidates=runner.candidate_tools,
                         request_question=question, book_name='main', subject='数学')
    response = binding.stream_run(store, run, 'owner', runner.registry, runner.adapter)

    async def consume():
        events = [json.loads(item[6:]) async for item in response.body_iterator]
        await response.aclose()
        return events

    events = asyncio.run(consume())
    snapshot = store.task_snapshot(events[-1]['execution_event']['task_id'])
    assert snapshot['budget_calls'] == snapshot['consumed_calls'] == 3
    assert snapshot['tool_calls'][0]['tool_id'] == 'search_textbook'
    assert '剩余 2 次 / 总计 3 次' in requests[0]['messages'][-1]['content']
    assert snapshot['task']['status'] == expected
    assert snapshot['task']['verification']['passed'] is False
    if expected == 'failed':
        assert len(requests) == 1 and snapshot['run']['error_code'] == 'tool_budget_exhausted'
        assert events[-1]['execution_event']['type'] == 'error'
        assert not store.pending_outbox()
        native = snapshot['run']['checkpoint']['native_messages']
        tools = [m['data'] for m in native if m['type'] == 'tool']
        assert [m['tool_call_id'] for m in tools] == [c['id'] for c in calls]
        assert json.loads(tools[-1]['content'])['error_code'] == 'tool_budget_exhausted'
    else:
        assert len(requests) == 2 and snapshot['run']['status'] == 'completed'
        assert '剩余 0 次 / 总计 3 次' in requests[1]['messages'][-1]['content']
        final = events[-1]
        assert final['execution_event']['type'] == 'final'
        assert final['learning_task']['status'] == 'degraded'
        assert final['learning_task']['verification']['status'] == 'unverified'
        messages = [r for r in store.pending_outbox() if r['kind'] == 'assistant_message']
        assert len(messages) == 1 and messages[0]['payload']['delivery_status'] == 'degraded'
