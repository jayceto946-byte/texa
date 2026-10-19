import asyncio
import json
from types import SimpleNamespace

import pytest

from backend.services.answer_verification import verify_answer
from backend.services.math_claim_binding import bind_math_claims
from tests.test_agent_runtime_chat_binding import prepared
from tests.test_agent_runtime_textbook import scope
from tests.test_deepseek_production import wire_run, completion
from tests.test_native_math_loop import SUCCESS


def receipt(left='2+3', right='5', **overrides):
    return {'outputs': [{'tool': 'verify_math_result', 'runtime_call_id': 'receipt-one',
        'success': True, 'args': {'kind': 'equivalence', 'left': left, 'right': right},
        'verification': {'passed': True, 'scope': 'input_expressions_under_explicit_assumptions'}, **overrides}]}


def test_exact_formula_is_linked_to_the_receipt_not_merely_a_matching_number():
    pack = receipt('(328-307)/(290-200)', '7/30')
    answer = r'工具仅核验 $\frac{328-307}{290-200}=\frac{7}{30}$。'
    result = verify_answer(answer, tool_context_pack=pack)
    assert result['claim_bindings'][0]['runtime_call_id'] == 'receipt-one'
    assert result['checks'][0]['status'] == 'passed'
    assert bind_math_claims(r'\[\frac{328-307}{290-200}=\frac{7}{30},\]', '', pack)
    # Binding a local relation does not prove the table/model or entire question.
    result = verify_answer(answer, question='依据教材计算灵敏度', tool_context_pack=pack,
        required_outputs=[{'id': 'whole', 'kind': 'math_support'}])
    assert result['status'] == 'unverified' and result['claim_bindings']
    for bad in [r'$\frac{328-307}{290-200}=\frac{8}{30}$', r'$21/90=7/30$', r'$0.233=0.233$']:
        assert not bind_math_claims(bad, '', pack)


@pytest.mark.parametrize('change', ['failed', 'unknown', 'computed', 'assumptions'])
def test_unverified_or_conditional_receipts_cannot_certify_a_formula(change):
    pack = receipt()
    row = pack['outputs'][0]
    if change == 'failed': row['success'] = False
    elif change == 'unknown': row['verification']['passed'] = False
    elif change == 'computed': row['tool'] = 'symbolic_math'
    else: row['args']['assumptions'] = {'x': 'positive'}
    assert not bind_math_claims('$2+3=5$', '', pack)


def test_domain_structure_and_unchecked_chain_are_not_folded_into_a_binding():
    assert not bind_math_claims('$1=1$', '', receipt('x/x', '1'))
    assert not bind_math_claims('$2+3=5=6$', '', receipt())
    assert not bind_math_claims('$sin(x)=x$', '', receipt('sin*x', 'x'))
    assert not bind_math_claims('$1e3=1000$', '', receipt('1*e3', '1000'))


def test_only_status_or_exact_final_duplicates_avoid_interim_degradation():
    from backend.services.agent_runtime.native_loop import _interim_covered
    assert _interim_covered('正在计算。', '结果是1024。')
    assert _interim_covered('结果是1024。', '说明：结果是1024。')
    assert not _interim_covered('$1 2=12$', '$12=12$')
    assert not _interim_covered('正在计算。\n\n结果是1025。', '结果是1024。')
    assert not _interim_covered('CDF 推导已经完成。', '结果是1024。')


def test_named_derivative_requires_the_same_original_function_in_the_question():
    pack = receipt()
    pack['outputs'][0]['args'] = {'kind': 'derivative', 'original': 'x^3-3*x', 'candidate': '3*x^2-3', 'variable': 'x'}
    answer = r"$f'(x)=3x^{2}-3$"
    assert bind_math_claims(answer, '计算 f(x)=x^3-3x 在闭区间的最值', pack)
    assert not bind_math_claims(answer, '计算 f(x)=x^3+3x 在闭区间的最值', pack)
    assert not bind_math_claims(answer, '未提供函数', pack)


def test_receipt_span_still_points_to_final_formula_after_retained_interim(tmp_path):
    from tests.test_native_math_loop import setup_run
    from backend.tools.registry import ToolContext
    from backend.services.math_claim_binding import formula_hash
    responses = [{**SUCCESS[0], 'content': '先核验关键等式。'}, SUCCESS[1],
                 {'content': r'结果是1024。$2^{10}=1024$'}]
    _, run, _, runner, state = setup_run(tmp_path, responses)
    snap = runner.run_bounded(run, 'owner', context=ToolContext(), answer_state=state, answer_generator=lambda _: '')
    answer = snap['run']['output']['answer']
    binding = snap['task']['verification']['claim_bindings'][0]
    start, end = binding['answer_span']
    assert formula_hash(answer[start:end]) == binding['formula_sha256']
    assert start > answer.index('## 最终解答')
    assert binding['runtime_call_id'] == snap['tool_calls'][1]['id']
    assert any(x['id'] == 'interim_delivery' for x in snap['task']['verification']['unverified'])


@pytest.mark.parametrize('enabled', [True, False])
def test_textbook_chat_exposes_only_existing_math_tools_and_honors_switch(tmp_path, monkeypatch, enabled):
    from backend.services.agent_runtime import chat_binding as binding, textbook_tool
    import backend.conversation_memory as conversation
    responses = [completion('正在计算。', SUCCESS[0]['tool_calls'] + SUCCESS[1]['tool_calls']),
                 completion('依据教材，结果是1024。[[cite:E1]]', reasoning='')] if enabled else [completion('依据教材，结果是1024。[[cite:E1]]')]
    store, _, runner, _, requests = wire_run(tmp_path, responses)
    frozen = scope()
    original = textbook_tool.register_textbook_search_runtime
    def register(registry, actual_scope):
        original(registry, actual_scope, versions=lambda name: frozen['index_versions'][name],
                 retrieve=lambda *a, **kw: {'evidence_items': [{'book_name': 'main', 'chunk_id': 'number',
                     'text': '依据教材，计算2^10的结果是1024。'}], 'evidence_support': {'status': 'sufficient'}})
    monkeypatch.setenv('TEXA_AGENT_RUNTIME_MATH', '1' if enabled else '0')
    monkeypatch.setattr(binding, 'model_requires_native_transcript', lambda: True)
    monkeypatch.setattr(binding, 'runtime_store', lambda **kw: store)
    monkeypatch.setattr(binding, 'build_math_registry', lambda: runner.registry)
    monkeypatch.setattr(binding, 'build_adapter', lambda _: runner.adapter)
    monkeypatch.setattr(binding, 'project_outcomes', lambda _: None)
    monkeypatch.setattr(conversation, 'append_message', lambda *a, **kw: {})
    monkeypatch.setattr(textbook_tool, 'freeze_textbook_scope', lambda *a: frozen)
    monkeypatch.setattr(textbook_tool, 'register_textbook_search_runtime', register)
    question = '依据教材计算2^10'
    state = {**prepared(), 'rewritten_question': question, 'book_name': 'main', 'subject': '数学',
             'answer_mode': 'textbook_grounded', 'use_textbook_context': True}
    response = binding.try_chat_response(SimpleNamespace(question=question), state, 'book-math')
    async def consume():
        events = [json.loads(chunk[6:]) async for chunk in response.body_iterator]
        await response.aclose()
        return events
    events = asyncio.run(consume())
    snap = store.task_snapshot(events[-1]['execution_event']['task_id'])
    assert snap['budget_calls'] == 3
    tools = [t['function']['name'] for t in requests[0].get('tools', [])]
    assert set(tools) == ({'symbolic_math', 'verify_math_result'} if enabled else set())
    assert snap['tool_calls'][0]['tool_id'] == 'search_textbook'
    assert snap['consumed_calls'] == (3 if enabled else 1)
    if enabled:
        assert snap['task']['status'] == 'completed'
        assert not snap['task']['verification']['unverified']
        assert snap['task']['verification']['delivery_notes']
        assert '阶段推导' not in snap['run']['output']['answer']


def test_numeric_result_with_trailing_explanation_keeps_binding_but_conflicts_do_not(tmp_path):
    from tests.test_native_math_loop import setup_run
    from backend.tools.registry import ToolContext
    from backend.services.tool_orchestration import build_tool_context_pack
    _, run, _, runner, state = setup_run(tmp_path, SUCCESS)
    snap = runner.run_bounded(run, 'owner', context=ToolContext(), answer_state=state, answer_generator=lambda _: '')
    pack = build_tool_context_pack([{'tool': c['tool_id'], 'args': c['args'], 'result': c['result']} for c in snap['tool_calls']])
    required = [{'id': 'number', 'kind': 'numeric'}, {'id': 'whole', 'kind': 'math_support'}]
    answer = '结果是1024。该核验只覆盖这次给定运算。'
    assert verify_answer(answer, question='计算 2^10。', required_outputs=required, tool_context_pack=pack)['status'] == 'passed'
    for bad in ['结果是1024。最终结果为1025。', '结果是1024/3。']:
        assert verify_answer(bad, question='计算 2^10。', required_outputs=required, tool_context_pack=pack)['status'] != 'passed'
