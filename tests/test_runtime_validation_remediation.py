"""Frozen public response replay through production HTTP wire/Runtime/SQL/SSE."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from backend.services.answer_verification import derive_required_outputs, verify_answer
from backend.services.tool_orchestration import build_tool_context_pack
from tests.test_deepseek_production import completion, wire_run
from tests.test_agent_runtime_chat_binding import prepared

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/qa/evidence/deepseek-production'
ACCEPTANCE = json.loads((EVIDENCE / 'paid/FINAL-ACCEPTANCE.json').read_text())
PLAN = json.loads((EVIDENCE / 'PAID-ACCEPTANCE-PLAN.json').read_text())


def frozen(case):
    row = next(r for r in ACCEPTANCE['cases'] if r['case'] == case)
    question = next(c for c in PLAN['cases'] if c['id'] == case.split('.')[0])['questions'][-1]
    return question, row


def production_stream(tmp_path, monkeypatch, question, responses):
    import backend.conversation_memory as conversation
    from backend.services.agent_runtime import chat_binding as binding
    store, _, runner, _, requests = wire_run(tmp_path, responses)
    monkeypatch.setattr(binding, 'model_requires_native_transcript', lambda: True)
    monkeypatch.setattr(binding, 'runtime_store', lambda **kw: store)
    monkeypatch.setattr(binding, 'build_math_registry', lambda: runner.registry)
    monkeypatch.setattr(binding, 'build_adapter', lambda _: runner.adapter)
    monkeypatch.setattr(binding, 'generate_answer', lambda _: pytest.fail('no extra model request'))
    monkeypatch.setattr(binding, 'project_outcomes', lambda _: None)
    monkeypatch.setattr(conversation, 'append_message', lambda *a, **k: {})
    data = {**prepared(), 'rewritten_question': question, 'conversation_id': 'replay', 'turn_id': 'replay-turn',
            'book_name': '', 'subject': '', 'use_textbook_context': False, 'answer_mode': 'global_general'}
    response = binding.try_chat_response(SimpleNamespace(question=question), data, 'replay-request', streaming=True)
    async def consume():
        items = [json.loads(item[6:]) async for item in response.body_iterator]
        await response.aclose()
        return items
    items = asyncio.run(consume())
    task_id = items[-1]['execution_event']['task_id']
    snapshot = store.task_snapshot(task_id)
    if snapshot['run']['output']:
        import sqlite3
        with sqlite3.connect(store.db_path) as conn:
            payload = json.loads(conn.execute("SELECT payload_json FROM runtime_outbox WHERE run_id=? AND kind='assistant_message'", (snapshot['run']['id'],)).fetchone()[0])
        assert payload['answer'] == snapshot['run']['output']['answer']
    return store, snapshot, items, requests


def assert_delivery(snapshot, events):
    answer = snapshot['run']['output']['answer']
    assert answer == snapshot['task']['artifacts']['final_answer']
    replacements = [e['execution_event']['payload']['text'] for e in events
                    if e.get('execution_event', {}).get('type') == 'output_delta'
                    and e['execution_event']['payload']['replace']]
    assert replacements == [answer]
    final = events[-1]
    assert final['learning_task']['verification'] == snapshot['task']['verification']
    assert final['execution_event']['payload']['verification_status'] == snapshot['task']['verification']['status']
    return answer


def test_frozen_s5_production_tool_replay_no_false_failure(tmp_path, monkeypatch):
    question, row = frozen('S5')
    calls = [{'id': t['operation_key'].split('native-1-')[1], 'name': t['tool_id'], 'args': t['args']}
             for t in row['tools']]
    _, snapshot, events, requests = production_stream(tmp_path, monkeypatch, question,
        [completion('', calls), completion(row['raw_final_public_model_answer'], reasoning='')])
    assert len(requests) == 2
    assert all(t['status'] == 'succeeded' and t['attempt_count'] == 1 for t in snapshot['tool_calls'])
    verification = snapshot['task']['verification']
    assert not verification['failures']
    checks = {c['id']: c for c in verification['checks']}
    assert checks['precision']['status'] == checks['tool_verification']['status'] == 'passed'
    assert verification['status'] == 'unverified'  # Entire derivation is not Oracle-proven.
    answer = assert_delivery(snapshot, events)
    assert '回答核对' not in answer and '验收未通过' not in answer


@pytest.mark.parametrize('case', ['S6.turn1', 'S6.turn2'])
def test_frozen_s6_public_replay_preserves_body_and_disclosure(tmp_path, monkeypatch, case):
    question, row = frozen(case)
    if case.endswith('turn1'):
        question = next(c for c in PLAN['cases'] if c['id'] == 'S6')['questions'][0]
    _, snapshot, events, requests = production_stream(tmp_path, monkeypatch, question,
        [completion(row['raw_final_public_model_answer'])])
    answer = assert_delivery(snapshot, events)
    assert len(requests) == 1
    assert not snapshot['task']['verification']['failures']
    if case.endswith('turn2'):
        assert len(answer.splitlines()) == 3
        assert len(answer.replace('\n', '')) <= 180
        assert [line[:3] for line in answer.splitlines()] == ['结论：', '反例：', '原因：']
    assert snapshot['task']['verification']['status'] == 'unverified'


@pytest.mark.parametrize('question,answer,expected', [
    ('只输出三行，依次以“结论：”“反例：”“原因：”开头。总长度不超过30个Unicode码点（不含换行）。', '结论：可导推出连续\n反例：绝对值\n原因：左右不同', False),
    ('只输出三行', '第一行\n第二行', True),
    ('只输出JSON', '{"answer": 42}', False),
    ('只输出JSON', '{"answer": 42}\n解释文字', True),
    ('使用Markdown表格', '| 项目 | 值 |\n| --- | --- |\n| a | b |', False),
    ('使用Markdown表格', '普通回答文本。', True),
    ('纯文本输出', '回答完整。', False),
    ('纯文本输出', '**回答完整。**', True),
])
def test_formats_through_native_production_delivery(tmp_path, monkeypatch, question, answer, expected):
    _, snapshot, events, _ = production_stream(tmp_path, monkeypatch, question, [completion(answer)])
    assert assert_delivery(snapshot, events) == answer
    assert bool(snapshot['task']['verification']['failures']) == expected


def test_precision_and_receipt_negative_boundaries():
    question, row = frozen('S5')
    pack = build_tool_context_pack([{'tool': t['tool_id'], 'args': t['args'], 'result': t['result']} for t in row['tools']])
    question = question.split('。', 1)[0]
    required = [{'id': 'precision', 'kind': 'precision', 'digits': 6}, {'id': 'tool', 'kind': 'tool_verification'}]
    assert verify_answer('数值为 0.184320', question=question, required_outputs=required, tool_context_pack=pack)['status'] == 'passed'
    for answer in ('$J=0.18432$', '$J=0.284320$'):
        assert verify_answer(answer, question=question, required_outputs=required, tool_context_pack=pack)['status'] == 'failed'
    for bad_pack, bad_question in (({}, question), (pack, question.replace('x²', 'x³'))):
        assert verify_answer('$J=0.184320$', question=bad_question, required_outputs=required, tool_context_pack=bad_pack)['status'] == 'unverified'
    assert verify_answer('最终结果为 0.184320。', question='给出完整原函数及推导步骤',
                         required_outputs=derive_required_outputs('给出完整原函数及推导步骤'))['status'] == 'failed'


@pytest.mark.parametrize('finish', ['stop', 'length'])
def test_empty_public_answer_never_commits(tmp_path, monkeypatch, finish):
    _, snapshot, events, _ = production_stream(tmp_path, monkeypatch, '说明连续性的意义', [completion('', finish=finish)])
    assert snapshot['run']['status'] == 'failed'
    assert snapshot['run']['error_code'] == ('provider_output_truncated' if finish == 'length' else 'missing_final_answer')
    assert snapshot['run']['output'] is None
    assert not any(e.get('execution_event', {}).get('type') == 'final' for e in events)


@pytest.mark.parametrize('failure', ['wrong_result', 'insufficient_precision', 'missing_derivation', 'no_tools'])
def test_s5_negative_through_production_chain(tmp_path, monkeypatch, failure):
    question, row = frozen('S5')
    answer = row['raw_final_public_model_answer']
    calls = [{'id': t['operation_key'].split('native-1-')[1], 'name': t['tool_id'], 'args': t['args']} for t in row['tools']]
    if failure == 'wrong_result':
        answer = answer.replace('0.184320', '0.284320')
    elif failure == 'insufficient_precision':
        import re
        answer = re.sub(r'0\.184320\d*', '0.18432', answer)
    elif failure == 'missing_derivation':
        answer = '数值为 0.184320。'
    responses = [completion(answer)] if failure == 'no_tools' else [completion('', calls), completion(answer, reasoning='')]
    _, snapshot, events, _ = production_stream(tmp_path, monkeypatch, question, responses)
    assert snapshot['task']['verification']['status'] != 'passed'
    if failure != 'no_tools':
        assert snapshot['task']['verification']['status'] == 'failed'
    else:
        assert next(c for c in snapshot['task']['verification']['checks'] if c['id'] == 'tool_verification')['status'] == 'unverified'
    assert_delivery(snapshot, events)


def test_strict_final_does_not_merge_unverified_preamble(tmp_path, monkeypatch):
    from tests.test_native_math_loop import SUCCESS
    question = '计算 2^10。只输出三行，依次以“结论：”“反例：”“原因：”开头。'
    answer = '结论：1024\n反例：无\n原因：计算得到'
    _, snapshot, events, _ = production_stream(tmp_path, monkeypatch, question,
        [completion('先进行公开计算。', [SUCCESS[0]['tool_calls'][0]]), completion(answer, reasoning='')])
    assert assert_delivery(snapshot, events) == answer
    assert '先进行公开计算。' in json.dumps(snapshot['run']['checkpoint']['native_messages'], ensure_ascii=False)
    assert any(c['id'] == 'interim_delivery' for c in snapshot['task']['verification']['unverified'])
    verification = snapshot['task']['verification']
    assert snapshot['task']['status'] == 'degraded' and verification['passed'] is False
    assert any(c['id'] == 'math_receipts' for c in verification['unverified'])
    assert all(c['status'] == 'passed' for c in verification['checks']
               if c['id'] in {'line_count', 'prefixes'})


@pytest.mark.parametrize('format_request,answer', [
    ('只输出JSON', '{"answer":1024}'),
    ('纯文本输出', '结果为1024。'),
])
def test_strict_computed_only_discloses_in_verification_without_changing_body(
        tmp_path, monkeypatch, format_request, answer):
    from tests.test_native_math_loop import SUCCESS
    _, snapshot, events, _ = production_stream(tmp_path, monkeypatch,
        '计算 2^10。' + format_request,
        [completion('', [SUCCESS[0]['tool_calls'][0]]), completion(answer, reasoning='')])
    assert assert_delivery(snapshot, events) == answer
    verification = snapshot['task']['verification']
    assert not verification['failures'] and verification['passed'] is False
    assert snapshot['task']['status'] == 'degraded'
    assert any(c['id'] == 'math_receipts' for c in verification['unverified'])


def test_numeric_only_does_not_satisfy_required_closed_form():
    q = '给出闭式结果和至少6位有效数字'
    r = verify_answer('数值为 0.184320。', question=q, required_outputs=derive_required_outputs(q))
    assert any(c['id'] == 'closed_form' for c in r['failures'])


def test_legacy_checkpoint_language_anchors_reclassified_without_migration():
    q, row = frozen('S5')
    pack = build_tool_context_pack([{'tool': t['tool_id'], 'args': t['args'], 'result': t['result']} for t in row['tools']])
    legacy = [{'id': 'old', 'kind': 'question_part', 'label': '明确区分自己推导', 'anchors': ['明确区分自己推导']}]
    result = verify_answer(row['raw_final_public_model_answer'], question=q, required_outputs=legacy, tool_context_pack=pack)
    assert not result['failures']
    assert next(c for c in result['checks'] if c['id'] == 'old')['status'] == 'unverified'
    assert next(c for c in result['checks'] if c['id'] == 'precision')['status'] == 'passed'
    assert legacy[0]['anchors'] == ['明确区分自己推导']
