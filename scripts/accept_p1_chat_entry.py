"""One C/B/AB sample through the real /api/chat/stream entry and SQL/SSE.

Default: local scripted provider only. --paid uses the existing authorized
DeepSeek profile, <=2 requests per task, <=6 total, no retries or resampling.
Only retrieval is adapted: active read-only BM25/Canonical C/B anchors and
the existing self-authored AB fixture. No route/preparation/budget overrides.
This does not certify full hybrid retrieval or whole-task mathematical proof.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
QA = Path('/private/tmp/texa-p1-chat-entry-20261019')
OUT = ROOT / 'docs/qa/p1-chat-entry'


def run(case, paid, replay=False):
    import accept_p1_joint as joint
    joint.QA, joint.OUT = QA, OUT
    _, sensor, role = joint.setup()
    import accept_p1_reliability as harness
    from graph import retrieval_node
    from backend.services.agent_runtime import chat_binding
    from backend.services.agent_runtime.locator import runtime_store
    from llm.agent_adapter import NativeToolAdapter
    _, rows, _, service, identity = sensor.sources()
    if case == 'AB':
        _, anchors = harness.old.corpus()
        from graph.textbook_context import expand_textbook_context
        question = harness.old.CASES['AB'][2]
        items = expand_textbook_context([anchors['extrema']], intent='teach', query=question)
        book, subject = harness.old.BOOK, '数学'
    else:
        question = sensor.CASES[case][2]
        items = sensor.retrieve_for(rows, service, sensor.CASES[case][1])
        book, subject = sensor.BOOK, '传感器'
    suffix = case if paid else ('replay-final-' if replay else 'preflight-') + case
    summary_path = OUT / f'chat-{suffix}.json'
    assert not summary_path.exists(), 'one sample only; do not silently repeat'
    source_calls, mock_requests = [], []

    def retrieve(state, **kwargs):
        assert state['book_name'] == book and state['subject'] == subject
        resources = kwargs['retrieval_resources_override']
        assert {r['book_name'] for r in resources} == {book}
        source_calls.append({'query_sha256': hashlib.sha256(state['user_input'].encode()).hexdigest(),
                             'book_name': book, 'chapters': state['target_chapters']})
        return {'evidence_items': items, 'evidence_support': {'status': 'supported'},
                'retrieval_status': 'scoped_active_bm25_canonical_fixture' if case != 'AB' else 'self_authored_canonical_fixture'}

    retrieval_node.retrieve_node = retrieve
    if paid:
        prior = OUT / 'joint-usage.json'
        assert not prior.exists() or not any(r['case'] == case for r in json.loads(prior.read_text())['requests']), 'case already attempted; no paid resampling'
        factory, cleanup = joint.paid_meter(role, case)
    else:
        import httpx
        from llm.deepseek_chat import DeepSeekChatOpenAI
        from tests.test_deepseek_production import completion

        recorded = []
        if replay:
            snap = json.loads((QA / f'{case}-snapshot.json').read_text())
            recorded = [m['data'] for m in snap['run']['checkpoint']['native_messages'] if m['type'] == 'ai']

        def transport(request):
            payload = json.loads(request.content)
            mock_requests.append(payload)
            assert {t['function']['name'] for t in payload['tools']} == {'symbolic_math', 'verify_math_result'}
            if case == 'C':
                visible = '\n'.join(m.get('content') or '' for m in payload['messages'])
                assert all(r'\tag{1.' + str(n) + '}' in visible for n in range(5, 12))
            if replay:
                source = recorded[len(mock_requests) - 1]
                chunks = completion(source['content'], source.get('tool_calls'), reasoning='')
            else:
                chunks = completion('依据教材给出测试回答。[[cite:E1]]', reasoning='')
            body = ''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks) + 'data: [DONE]\n\n'
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=body)

        http = httpx.Client(transport=httpx.MockTransport(transport))
        model = DeepSeekChatOpenAI(model=role.model, api_key='local-test-only',
            http_client=http, stream_usage=True, streaming=True, extra_body=role.options['extra_body'])
        factory, cleanup = (lambda *a, **kw: model), http.close

    def adapter(registry):
        return NativeToolAdapter(role, registry, model_factory=factory)

    chat_binding.build_adapter = adapter
    from fastapi.testclient import TestClient
    from backend.main import app
    started = time.monotonic()
    # Full transport and production preparation; no _prepare_chat_turn patches.
    try:
        with closing(TestClient(app, base_url='http://127.0.0.1')) as client:
            response = client.post('/api/chat/stream', json={
                'question': question, 'book_name': book, 'subject': subject,
                'answer_mode': 'auto', 'conversation_id': 'chat-entry-' + suffix,
                'turn_id': 'chat-entry-' + suffix})
            assert response.status_code == 200
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
            joint.write(QA / f'{suffix}-events.json', events)
            terminal = [e for e in events if (e.get('execution_event') or {}).get('task_id', '').startswith('rtask_')][-1]
            task_id = terminal['execution_event']['task_id']
            snap = runtime_store().task_snapshot(task_id)
            assert snap['budget_calls'] == 3 and snap['budget_model_calls'] == 5
            assert {c['id'] for c in snap['run']['checkpoint']['candidates']} == {'symbolic_math', 'verify_math_result'}
            assert source_calls and snap['tool_calls'][0]['tool_id'] == 'search_textbook'
            final = snap['run'].get('output') or {}
            answer = final.get('answer') or ''
            verification = snap['task']['verification']
            assert terminal['execution_event']['payload']['task_status'] == snap['task']['status']
            assert terminal['execution_event']['payload']['verification_status'] == verification['status']
            assert terminal['learning_task']['verification'] == verification
            for bound in verification.get('claim_bindings', []):
                start, end = bound['answer_span']
                assert hashlib.sha256(answer[start:end].encode()).hexdigest() == bound['formula_sha256']
                assert bound['runtime_call_id'] in {c['id'] for c in snap['tool_calls']}
            conversation = client.get('/api/chat/conversations/chat-entry-' + suffix).json()['data']
            assistant = [m for m in conversation['messages'] if m.get('role') == 'assistant']
            assert len(assistant) == 1 and assistant[0]['content'] == answer
            assert assistant[0]['learning_task']['status'] == snap['task']['status']
            assert assistant[0]['learning_task']['verification'] == verification
            joint.write(QA / f'{suffix}-snapshot.json', snap)
            (QA / f'{suffix}-final.txt').write_text(answer)
            calls = snap['tool_calls']
            native = snap['run']['checkpoint'].get('native_messages') or []
            proposed = [c for m in native if m['type'] == 'ai' for c in m['data']['tool_calls']]
            summary = {'case': case, 'paid': paid, 'replay_of_saved_public_response': replay, 'entry': 'POST /api/chat/stream',
                'production_preparation': True, 'route_budget_overrides': False,
                'retrieval_limit': 'scoped active BM25/Canonical anchor fixture; full hybrid not tested',
                'run_status': snap['run']['status'], 'task_status': snap['task']['status'],
                'error_code': snap['run']['error_code'], 'verification': verification,
                'budget_calls': snap['budget_calls'], 'budget_model_calls': snap['budget_model_calls'],
                'consumed_calls': snap['consumed_calls'], 'model_calls': snap['consumed_model_calls'],
                'answer_chars': len(answer), 'answer_sha256': hashlib.sha256(answer.encode()).hexdigest(),
                'total_ms': round((time.monotonic() - started) * 1000, 2), 'source_calls': source_calls,
                'tools': [{'id': c['id'], 'tool': c['tool_id'], 'status': c['status'], 'error_code': c['error_code'],
                    'args': c['args'] if c['tool_id'] != 'search_textbook' else {},
                    'result': c['result'] if c['tool_id'] != 'search_textbook' else None} for c in calls],
                'proposed_tools': proposed, 'terminal_event': terminal['execution_event']['type'],
                'sql_sse_conversation_agree': True, 'mock_requests': len(mock_requests) if not paid else None}
            joint.write(summary_path, summary)
            print(json.dumps({k: summary[k] for k in ('case', 'paid', 'run_status', 'task_status', 'error_code', 'model_calls', 'consumed_calls')}, ensure_ascii=False))
    finally:
        cleanup()
        actual = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in identity['files']}
        assert identity['files'] == actual
        joint.write(OUT / f'source-integrity-{suffix}.json', {'unchanged': True, 'files': actual})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=['C', 'B', 'AB'], required=True)
    parser.add_argument('--paid', action='store_true')
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    assert not (args.paid and args.replay)
    run(args.case, args.paid, args.replay)
