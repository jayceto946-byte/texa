"""Bounded joint acceptance: read-only textbook, disposable stores, <=6 HTTP.

Default is deterministic only. --case selects one paid task (<=2 requests).
Native tool candidates match the historical harness; the production budget
value is three. This does not claim production chat routing exposes math tools.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
QA = Path('/private/tmp/texa-p1-joint-20261019')
OUT = ROOT / 'docs/qa/p1-joint'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def setup():
    import accept_p1_context_packing as packing
    packing.QA, packing.OUT = QA, OUT
    sensor, role = packing.setup()
    assert Path(os.environ['PROGRESS_PATH']).resolve() == QA / 'progress'
    return packing, sensor, role


def production_admission(role):
    """Observe production chat's frozen candidates without starting generation."""
    from types import SimpleNamespace
    from backend.services.agent_runtime import chat_binding as binding, textbook_tool
    from backend.services.agent_runtime.store import RuntimeStore
    from llm.agent_adapter import NativeToolAdapter
    frozen = {'id': 'admission-fixture', 'book_name': 'admission-fixture', 'subject': '数学',
              'resources': [], 'index_versions': {}}
    store = RuntimeStore(QA / 'admission/runtime.db')
    originals = binding.runtime_store, binding.build_adapter, textbook_tool.freeze_textbook_scope
    binding.runtime_store = lambda **kw: store

    def adapter(registry):
        def no_model(*a, **kw):
            raise AssertionError('admission probe must not call a model')
        result = NativeToolAdapter(role, registry, model_factory=no_model)
        result.allow_native_attempt = True
        return result

    binding.build_adapter = adapter
    textbook_tool.freeze_textbook_scope = lambda *a: frozen
    rows = []
    try:
        for name, question in [('AB', '依据教材讲解闭区间最值，并计算和核验 f(x)=x^3-3*x 在[-3,3]的最值。'),
                               ('B', '依据教材计算表1.1的灵敏度并核验关键数值。')]:
            prepared = {'rewritten_question': question, 'book_name': frozen['book_name'], 'subject': '数学',
                        'use_textbook_context': True, 'answer_mode': 'textbook_grounded', 'scope_reason': 'explicit',
                        'resolution_trace': {}, 'continuity_context': {},
                        'conversation_id': 'admission-' + name, 'turn_id': 'admission-' + name}
            response = binding.try_chat_response(SimpleNamespace(question=question), prepared, 'admission-' + name)
            assert response is not None
            # No iterator consumption: production admission/configuration only.
            import sqlite3
            with sqlite3.connect(store.db_path) as conn:
                run_id = conn.execute('SELECT id FROM agent_runs ORDER BY created_at DESC LIMIT 1').fetchone()[0]
            snap = store.snapshot(run_id)
            rows.append({'case': name, 'budget_calls': snap['budget_calls'],
                         'candidates': snap['run']['checkpoint']['candidates'],
                         'fixed_preparation': snap['run']['checkpoint']['answer_state'].get('_native_preparation_ref'),
                         'model_calls': snap['consumed_model_calls']})
            asyncio.run(response.aclose())
        assert all(r['budget_calls'] == 3 and not r['candidates'] and r['model_calls'] == 0 for r in rows)
    finally:
        binding.runtime_store, binding.build_adapter, textbook_tool.freeze_textbook_scope = originals
    write(OUT / 'production-admission.json', {'probe': 'configuration only, no model or retrieval execution',
          'rows': rows, 'limitation': 'grounded chat answer route has no model-selected math candidates; not changed here'})


def paid_meter(role, case):
    import httpx
    from langchain_core.callbacks import BaseCallbackHandler
    from llm.factory import build_chat_model
    from utils.thinking_filter import strip_thinking
    path = OUT / 'joint-usage.json'
    ledger = json.loads(path.read_text()) if path.exists() else {
        'provider': 'deepseek', 'model': 'deepseek-flash', 'request_limit': 6,
        'per_case_limit': 2, 'automatic_retries': 0, 'requests': []}
    lock, current = threading.RLock(), {}
    original_init = httpx.Client.__init__
    clients = []

    def guard(request):
        if request.url.host in {'localhost', '127.0.0.1', '::1'}:
            return
        assert request.url.host == 'api.deepseek.com' and request.url.path.endswith('/chat/completions')
        payload = json.loads(request.content)
        assert payload['model'] == role.model == 'deepseek-flash' and payload['temperature'] == 1
        assert payload['thinking'] == {'type': 'enabled'} and payload['reasoning_effort'] == 'high'
        assert payload['max_tokens'] == 8192
        public = [{k: v for k, v in m.items() if k != 'reasoning_content'} for m in payload['messages']]
        assert all(isinstance(m.get('content'), (str, type(None))) for m in public)
        if case == 'C':
            text = '\n'.join(m.get('content') or '' for m in public)
            assert all('\\tag{1.' + str(n) + '}' in text for n in range(5, 12))
        with lock:
            assert len(ledger['requests']) < 6 and sum(r['case'] == case for r in ledger['requests']) < 2
            encoded = json.dumps(public, ensure_ascii=False, sort_keys=True)
            record = {'index': len(ledger['requests']) + 1, 'case': case, 'status': 'requested',
                      'public_input_sha256': hashlib.sha256(encoded.encode()).hexdigest(),
                      'input_bytes': len(request.content), 'temperature': 1}
            ledger['requests'].append(record)
            current[threading.get_ident()] = record, time.monotonic()
            write(path, ledger)
            write(QA / f'{case}-request-{record["index"]}.json', public)

    def init(self, *args, **kwargs):
        hooks = dict(kwargs.pop('event_hooks', {}) or {})
        kwargs.update(event_hooks={**hooks, 'request': [guard, *hooks.get('request', [])]}, trust_env=False)
        original_init(self, *args, **kwargs)
        clients.append(self)
    httpx.Client.__init__ = init

    class Receipt(BaseCallbackHandler):
        def on_llm_end(self, response, **kw):
            with lock:
                record, start = current[threading.get_ident()]
                message = response.generations[0][0].message
                record.update(status='returned', usage=message.usage_metadata or {},
                              request_ms=round((time.monotonic() - start) * 1000, 2),
                              finish_reason=message.response_metadata.get('finish_reason'),
                              response_model=message.response_metadata.get('model_name'))
                write(path, ledger)
                text = strip_thinking(message.content) if isinstance(message.content, str) else ''
                (QA / f'{case}-answer-{record["index"]}.txt').write_text(text)

        def on_llm_error(self, error, **kw):
            with lock:
                pair = current.get(threading.get_ident())
                if pair:
                    pair[0].update(status='error', error_type=type(error).__name__)
                    write(path, ledger)

    def factory(resolved, temperature=1, **kwargs):
        kwargs.update(max_retries=0, stream_usage=True, request_timeout=180)
        return build_chat_model(resolved, 1, **kwargs).model_copy(update={'callbacks': [Receipt()], 'max_tokens': 8192})

    def cleanup():
        httpx.Client.__init__ = original_init
        for client in clients:
            client.close()
    return factory, cleanup


def run_paid(sensor, role, case):
    import accept_p1_reliability as harness
    from backend.services.agent_runtime import contracts
    from backend.services.agent_runtime.store import RuntimeStore
    assert not (OUT / f'joint-{case}.json').exists(), 'one task sample only; no silent repeat'
    factory, cleanup = paid_meter(role, case)
    original_command = contracts.RunCommand

    def bounded_command(*args, **kwargs):
        kwargs.update(budget_calls=3, budget_model_calls=2)
        return original_command(*args, **kwargs)
    contracts.RunCommand = bounded_command
    start = time.monotonic()
    identity = sensor.sources()[-1]
    try:
        if case == 'AB':
            _, anchors = harness.old.corpus()
            _, key, question = harness.old.CASES['AB']
            result = harness.old.native('joint-AB', question, key, anchors, role, factory)
        else:
            _, rows, manifest, service, _ = sensor.sources()
            items = sensor.retrieve_for(rows, service, sensor.CASES[case][1])
            result = sensor.native('joint-' + case, sensor.CASES[case][2], items, manifest, role, factory)
        assert 'reasoning_content' not in json.dumps(result, ensure_ascii=False)
        write(QA / f'joint-{case}.json', result)
        run_id = result['tool_calls'][0]['requested_run_id']
        snap = RuntimeStore(QA / 'progress/runtime.db').snapshot(run_id)
        answer = result['answer']
        summary = {k: result.get(k) for k in ('run_status', 'task_status', 'error_code', 'verification')}
        summary.update(case=case, harness='existing bounded native/SSE; not production router',
                       budget_calls=snap['budget_calls'], consumed_calls=snap['consumed_calls'],
                       model_calls=snap['consumed_model_calls'], answer_chars=len(answer),
                       answer_sha256=hashlib.sha256(answer.encode()).hexdigest(),
                       total_ms=round((time.monotonic() - start) * 1000, 2),
                       tools=[{'tool': c['tool_id'], 'status': c['status'], 'error_code': c['error_code'],
                               'args': c['args'] if c['tool_id'] != 'search_textbook' else {},
                               'result': c['result'] if c['tool_id'] != 'search_textbook' else None}
                              for c in result['tool_calls']],
                       terminal_event=result['events'][-1].get('execution_event', {}).get('type'),
                       whole_task_verified=snap['task']['verification'].get('passed') is True)
        native = snap['run']['checkpoint'].get('native_messages') or []
        summary['proposed_tools'] = [c for m in native if m['type'] == 'ai' for c in m['data']['tool_calls']]
        write(OUT / f'joint-{case}.json', summary)
        print(json.dumps({k: summary[k] for k in ('case', 'run_status', 'task_status', 'error_code', 'model_calls', 'consumed_calls')}, ensure_ascii=False))
    finally:
        contracts.RunCommand = original_command
        cleanup()
        # The reused synthetic corpus installs an in-process manifest provider.
        # Check real files directly so that provider cannot mask the postcheck.
        actual = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in identity['files']}
        assert identity['files'] == actual
        write(OUT / f'source-integrity-{case}.json', {'unchanged': True, 'files': actual})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=['C', 'B', 'AB'])
    options = parser.parse_args()
    packing, sensor, role = setup()
    if options.case:
        run_paid(sensor, role, options.case)
    else:
        packing.run_deterministic(sensor)
        production_admission(role)


if __name__ == '__main__':
    main()
