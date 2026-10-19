"""Budget and receipt reuse through the existing native/SQL/provider contracts."""
import json
from copy import deepcopy
import pytest
from langchain_core.messages import ToolMessage, messages_from_dict
from backend.tools.registry import ToolContext
from backend.services.agent_runtime.native_loop import _reusable_math_receipt
from tests.test_native_math_loop import setup_run, call, SUCCESS
from tests.test_deepseek_production import wire_run, completion, execute, PRIVATE


def run_case(tmp_path, responses, **limits):
    store, run, model, runner, state = setup_run(tmp_path, responses, **limits)
    result = runner.run_bounded(run, 'owner', context=ToolContext(), answer_state=state,
        answer_generator=lambda _: pytest.fail('no implicit model request'))
    return store, run, model, runner, result


def test_budget_visible_before_batch_and_after_last_execution(tmp_path):
    _, _, model, _, result = run_case(tmp_path, [SUCCESS[0], SUCCESS[-1]], budget_calls=1)
    assert result['consumed_calls'] == 1 and len(model.received) == 2
    assert '剩余 1 次 / 总计 1 次' in model.received[0][-1].content
    assert '剩余 0 次 / 总计 1 次' in model.received[1][-1].content
    assert '余额为零' in model.received[1][-1].content
    # Per-request guidance never grows the saved protocol/history.
    saved = messages_from_dict(result['run']['checkpoint']['native_messages'])
    assert not any('工具执行预算：' in str(m.content) for m in saved)


@pytest.mark.parametrize('same_batch', [False, True])
def test_exact_computed_receipt_reuse_spends_no_second_execution(tmp_path, same_batch):
    duplicate = call('symbolic_math', {'operation': 'calculate', 'expression': '2^10',
        'variable': 'x', 'assumptions': {}}, 'duplicate')
    responses = [SUCCESS[0], duplicate, SUCCESS[-1]]
    if same_batch:
        responses = [{'content': '', 'tool_calls': SUCCESS[0]['tool_calls'] + duplicate['tool_calls']}, SUCCESS[-1]]
    _, _, model, _, result = run_case(tmp_path, responses, budget_calls=1)
    assert result['consumed_calls'] == 1 and len(result['tool_calls']) == 1
    assert len(model.received) == len(responses)
    messages = messages_from_dict(result['run']['checkpoint']['native_messages'])
    receipts = [json.loads(m.content) for m in messages if isinstance(m, ToolMessage)]
    assert len(receipts) == 2 and receipts[1]['runtime_reused'] is True
    assert receipts[0]['runtime_call_id'] == receipts[1]['runtime_call_id']
    assert receipts[1]['data'] == receipts[0]['data']
    assert result['task']['verification']['passed'] is False  # computed stays computed


def test_verified_reuse_keeps_scope_and_native_deepseek_continuity(tmp_path):
    first = SUCCESS[1]['tool_calls'][0]
    second = {**first, 'id': 'same-check-new-id'}
    store, run, runner, state, requests = wire_run(tmp_path,
        [completion('', [first, second]), completion(reasoning='')], budget_calls=1)
    result = execute(store, run, runner, state)
    assert result['consumed_calls'] == 1 and result['consumed_model_calls'] == 2
    # Local equivalence is retained, but without a computed numeric binding
    # the whole required-output gate correctly remains unverified.
    assert result['task']['verification']['passed'] is False
    assistants = [m for m in requests[1]['messages'] if m['role'] == 'assistant']
    assert assistants[0]['reasoning_content'] == PRIVATE
    tools = [m for m in requests[1]['messages'] if m['role'] == 'tool']
    assert [m['tool_call_id'] for m in tools] == [first['id'], second['id']]
    original, reused = [json.loads(m['content']) for m in tools]
    assert original['verification'] == reused['verification']
    assert reused['runtime_reused'] is True
    assert PRIVATE not in json.dumps(result) and PRIVATE.encode() not in store.db_path.read_bytes()


@pytest.mark.parametrize('change', ['variable', 'assumptions', 'lower', 'upper', 'expression', 'version', 'schema', 'run', 'source'])
def test_reuse_identity_never_collapses_conditions_or_contracts(tmp_path, change):
    _, run, _, runner, result = run_case(tmp_path, [SUCCESS[0], SUCCESS[-1]])
    snapshot = deepcopy(result)
    receipt = snapshot['tool_calls'][0]
    spec = runner.registry.runtime_tool('symbolic_math')
    meta = spec.runtime_metadata()
    args = deepcopy(receipt['args'])
    assert _reusable_math_receipt(snapshot, run, spec, meta, args) is not None
    if change in {'variable', 'assumptions', 'lower', 'upper', 'expression'}:
        args[change] = {'variable': 'y', 'assumptions': {'x': 'real'}, 'lower': '0',
            'upper': '2', 'expression': '1024'}[change]
    elif change == 'version': meta['version'] = 'different'
    elif change == 'schema': meta['schema_hash'] = 'different'
    elif change == 'run': run = 'another-run'
    else:
        # The entire nested source/step contract is included in equality too.
        receipt['args']['context'] = {'source_ref': 'original', 'steps': []}
        args['context'] = {'source_ref': 'changed', 'steps': []}
    assert _reusable_math_receipt(snapshot, run, spec, meta, args) is None


@pytest.mark.parametrize('args', [
    {'operation': 'invalid', 'expression': '2'},
    {'operation': 'calculate', 'expression': "__import__('os')"},
])
def test_invalid_arguments_and_worker_failures_are_budgeted_and_not_reused(tmp_path, args):
    first, second = call('symbolic_math', args, 'bad1'), call('symbolic_math', args, 'bad2')
    _, _, model, _, result = run_case(tmp_path, [first, second, {'content': '失败，无法核验。'}], budget_calls=2)
    assert result['consumed_calls'] == 2 and len(result['tool_calls']) == 2
    assert all(c['status'] == 'failed' for c in result['tool_calls'])
    assert result['task']['status'] != 'completed'
    assert len(model.received) == 3
    assert '剩余 1 次' in model.received[1][-1].content
    receipt = next(m for m in model.received[1] if isinstance(m, ToolMessage))
    assert not json.loads(receipt.content)['success']


def test_unknown_is_not_reused_or_promoted(tmp_path):
    args = {'kind': 'equivalence', 'left': 'sqrt(x^2)', 'right': 'x'}
    _, _, _, _, result = run_case(tmp_path, [call('verify_math_result', args, 'u1'),
        call('verify_math_result', args, 'u2'), {'content': '条件不足，核验未通过。'}], budget_calls=2)
    assert result['consumed_calls'] == 2
    assert all(c['result']['verification']['passed'] is not True for c in result['tool_calls'])
    assert result['task']['status'] != 'completed'


def test_distinct_equivalent_inputs_still_spend_budget_and_close_all_messages(tmp_path):
    responses = [{'content': '', 'tool_calls': [*SUCCESS[0]['tool_calls'],
        *call('symbolic_math', {'operation': 'calculate', 'expression': '1024'}, 'different')['tool_calls'],
        *SUCCESS[1]['tool_calls']]}]
    _, _, model, _, result = run_case(tmp_path, responses, budget_calls=2)
    assert result['consumed_calls'] == 2 and result['run']['error_code'] == 'tool_budget_exhausted'
    assert len(model.received) == 1
    saved = messages_from_dict(result['run']['checkpoint']['native_messages'])
    receipts = [m for m in saved if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in receipts] == ['calc-1', 'different', 'verify-2']
    assert json.loads(receipts[-1].content)['error_code'] == 'tool_budget_exhausted'
    assert result['task']['status'] == 'failed' and '1024' in result['run']['output']['answer']


def test_repeated_reuse_is_bounded_by_model_budget(tmp_path):
    responses = [call('symbolic_math', {'operation': 'calculate', 'expression': '2^10'}, str(i)) for i in range(4)]
    _, _, model, _, result = run_case(tmp_path, responses, budget_calls=1, budget_model_calls=3)
    assert len(model.received) == 3 and result['consumed_calls'] == 1
    assert result['run']['error_code'] == 'model_budget_exhausted'
    assert result['task']['status'] == 'failed'


def test_simple_answer_keeps_one_request(tmp_path):
    _, _, model, _, result = run_case(tmp_path, [{'content': '导数描述变化率。'}])
    assert len(model.received) == 1 and result['consumed_calls'] == 0


def test_fixed_preparation_spends_same_budget_before_first_model(tmp_path):
    from backend.services.agent_runtime.textbook_tool import register_textbook_search_runtime
    from tests.test_agent_runtime_textbook import scope
    store, run, runner, _, requests = wire_run(tmp_path, [completion('概念定义。[[cite:E1]]')], budget_calls=4)
    runner.candidate_tools = ()
    frozen = scope()
    register_textbook_search_runtime(runner.registry, frozen,
        retrieve=lambda *a, **k: {'evidence_items': [{'book_name': 'main', 'chunk_id': 'a', 'text': '概念定义。'}],
            'evidence_support': {'status': 'sufficient'}, 'retrieval_status': 'ok'},
        versions=lambda name: frozen['index_versions'][name])
    metadata = runner.registry.runtime_tool('search_textbook').runtime_metadata()
    state = {'user_input': '讲解概念', 'answer_mode': 'textbook_grounded', 'use_textbook_context': True,
        'intent': 'teach', '_runtime_textbook_scope': frozen,
        '_native_preparation_ref': {k: metadata[k] for k in ('id', 'version', 'schema_hash')}}
    store.configure_chat(run, 'owner', state=state, candidates=(), request_question='讲解概念', book_name='main', subject='数学')
    result = runner.run_bounded(run, 'owner', context=ToolContext(book_name='main', subject='数学'), answer_state=state,
        answer_generator=lambda _: pytest.fail('no implicit generation'))
    assert result['consumed_calls'] == 1 and result['consumed_model_calls'] == 1
    notice = requests[0]['messages'][-1]['content']
    assert '剩余 3 次 / 总计 4 次' in notice and '固定教材检索 1 次' in notice


def test_tuple_failure_stays_visible_with_scalar_tool_guidance(tmp_path):
    args = {'kind': 'equivalence', 'left': '(1+1,2+2)', 'right': '(2,4)'}
    _, _, model, runner, result = run_case(tmp_path, [call('verify_math_result', args, 'tuple'),
        {'content': '批量表达式不受支持，本次核验失败，不能视作已验证。'}])
    assert result['consumed_calls'] == 1 and result['tool_calls'][0]['status'] == 'failed'
    receipt = next(m for m in model.received[1] if isinstance(m, ToolMessage))
    assert 'unsupported expression syntax' in json.loads(receipt.content)['message']
    assert 'scalar expressions' in runner.registry.get('verify_math_result').description
    assert result['task']['status'] != 'completed'


@pytest.mark.parametrize('trace', ['t1-after-AB', 't1-sensor-B'])
def test_recorded_overbudget_batch_has_no_post_result_model_decision(tmp_path, trace):
    from pathlib import Path
    audit = json.loads((Path(__file__).resolve().parents[1] / 'docs/qa/agent-loop-completion/trace-audit.json').read_text())[trace]
    # Fixed preparation consumes one of four; replay precisely the remaining
    # three math slots, using recorded original native call IDs/arguments.
    calls = [{'name': c['tool'], 'args': c['input'], 'id': c['model_tool_call_id'], 'type': 'tool_call'}
        for c in audit['chain'] if c['origin'] == 'model']
    _, _, model, _, result = run_case(tmp_path, [{'content': '', 'tool_calls': calls}], budget_calls=3)
    assert result['consumed_calls'] == 3 and len(model.received) == 1
    assert result['run']['error_code'] == 'tool_budget_exhausted'
    assert result['task']['status'] == 'failed'
    saved = messages_from_dict(result['run']['checkpoint']['native_messages'])
    receipts = [m for m in saved if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in receipts] == [c['id'] for c in calls]
    assert all(json.loads(m.content)['error_code'] == 'tool_budget_exhausted' for m in receipts[3:])
