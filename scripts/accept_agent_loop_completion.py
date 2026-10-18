"""Authorized two-case acceptance: hard total four HTTP requests, no retries.

Reuse existing profile, real source preflight and Runtime/SSE harness. Writes are
explicitly isolated; committed sensor evidence excludes textbook/answer bodies.
"""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import accept_p1_reliability as harness
import accept_p1_sensor as sensor
ROOT = Path(__file__).resolve().parents[1]
QA = Path('/private/tmp/texa-agent-completion-20261018')
OUT = ROOT / 'docs/qa/agent-loop-completion'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=['AB', 'sensor-B'], required=True)
    args = parser.parse_args()
    case = 'completion-' + args.case
    harness.QA = QA
    harness.OUT = OUT
    sensor.QA = QA
    sensor.OUT = OUT
    role = harness.setup()
    import config
    assert Path(config.PROGRESS_PATH).resolve() == QA / 'progress'
    assert Path(config.DATA_DIR).resolve().is_relative_to(QA)
    assert not (QA / (case + '.json')).exists(), 'explicit unique case required'
    OUT.mkdir(parents=True, exist_ok=True)
    usage_path = OUT / 'usage.json'
    if not usage_path.exists():
        harness.old.write(usage_path, {'model': role.model, 'provider': 'deepseek', 'request_limit': 4, 'requests': []})
    factory = harness.meter(role, case)
    # Prepend a hard guard ahead of the reused meter; a denied request never
    # reaches the transport or enters the paid-request ledger.
    import httpx
    metered_init = httpx.Client.__init__
    denied = []
    def hard_limit(request):
        if request.url.host in {'localhost', '127.0.0.1', '::1'}:
            return
        requests = json.loads(usage_path.read_text())['requests']
        if len(requests) >= 4 or sum(r['case'] == case for r in requests) >= 2:
            denied.append('acceptance_request_limit')
            raise RuntimeError('acceptance_request_limit')
    def init(self, *a, **kw):
        hooks = dict(kw.pop('event_hooks', {}) or {})
        hooks['request'] = [hard_limit, *hooks.get('request', [])]
        return metered_init(self, *a, event_hooks=hooks, **kw)
    httpx.Client.__init__ = init
    start = time.monotonic()
    if args.case == 'AB':
        _, anchors = harness.old.corpus()
        _, key, question = harness.old.CASES['AB']
        result = harness.old.native(case, question, key, anchors, role, factory)
    else:
        _, rows, manifest, service, identity = sensor.sources()
        _, query, question = sensor.CASES['B']
        items = sensor.retrieve_for(rows, service, query)
        _, trace = sensor.trace_pack(items)
        result = sensor.native(case, question, items, manifest, role, factory)
        assert identity['files'] == sensor.sources()[-1]['files']
        result['trace'] = trace
        result['source_identity'] = identity
        # Recover only public native protocol from our own disposable SQL.
        from backend.services.agent_runtime.store import RuntimeStore
        store = RuntimeStore(QA / 'progress/runtime.db')
        result['native_messages'] = store.snapshot(result['tool_calls'][0]['requested_run_id'])['run']['checkpoint']['native_messages']
    result['total_ms'] = round((time.monotonic() - start) * 1000, 2)
    result['denied_requests'] = denied
    harness.old.write(QA / (case + '.json'), result)
    public = {k: v for k, v in result.items() if k not in {'answer', 'events', 'native_messages', 'tool_calls'}}
    public['answer_sha256'] = hashlib.sha256(result['answer'].encode()).hexdigest()
    public['tools'] = [{k: c[k] for k in ['tool_id', 'status', 'error_code', 'attempt_count']} | {
        'args': c['args'] if c['tool_id'] != 'search_textbook' else {},
        'result': c['result'] if c['tool_id'] != 'search_textbook' else None} for c in result['tool_calls']]
    public['model_calls'] = len([e for e in result['events'] if e.get('execution_event', {}).get('payload', {}).get('lifecycle') == 'model.started'])
    public['proposed_tools'] = [call for m in result.get('native_messages', []) if m['type'] == 'ai' for call in m['data']['tool_calls']]
    public['terminal_event'] = [e['execution_event']['type'] for e in result['events'] if 'execution_event' in e][-1]
    harness.old.write(OUT / (case + '.json'), public)
    print(json.dumps({'case': case, 'run_status': result['run_status'], 'task_status': result['task_status'],
        'tool_executions': len(result['tool_calls']), 'model_calls': public['model_calls'], 'total_ms': result['total_ms'],
        'error_code': result['error_code']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
