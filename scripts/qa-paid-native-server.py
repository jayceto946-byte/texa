"""Explicitly authorized, synthetic-session real provider acceptance; no production data.

Budget instrumentation is process-local. It does not replace model responses, tools,
routing, Runtime, verification or SSE. Provider errors never persist their text.
"""
import argparse
import json
import os
import sys
import threading
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--authorized', action='store_true')
    p.add_argument('--env-file', type=Path, required=True)
    p.add_argument('--qa-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prior-receipts', type=Path)
    args = p.parse_args()
    if not args.authorized or not args.env_file.is_file():
        p.error('explicit authorization and configured environment required')
    root = args.qa_root.resolve()
    if not root.is_relative_to(Path('/private/tmp')):
        p.error('QA data must be isolated in /private/tmp')
    root.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        p.error('preserve prior paid evidence; output already exists')
    os.environ.update(ENV_PATH=str(args.env_file.resolve()), DATA_DIR=str(root/'data'),
        PROGRESS_PATH=str(root/'progress'), BOOKS_PATH=str(root/'books'),
        VECTOR_DB_PATH=str(root/'vector'), MINERU_OUTPUT_PATH=str(root/'mineru'),
        HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
        TEXA_NATIVE_MODEL_TIMEOUT='180', TEXA_NATIVE_RUN_TIMEOUT='600',
        KAOYAN_TRUSTED_ORIGINS='http://127.0.0.1:18042')
    from config import get_model_role_config
    from urllib.parse import urlparse
    role = get_model_role_config()
    if role.model != 'qwen3.7-plus' or urlparse(role.endpoint).hostname != 'dashscope.aliyuncs.com' or not role.credential_configured:
        raise SystemExit('pricing preflight only covers configured Beijing qwen3.7-plus')
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.RLock()
    prior = json.loads(args.prior_receipts.read_text()) if args.prior_receipts else {}
    evidence = {'authorization': 'user 2026-10-13: three difficult exam problems and one no-tool comparison, screenshots and metrics',
        'model': role.model, 'remote_attempts': 0, 'input_bytes': 0,
        'cost_cap_cny': 1, 'max_calls': 16, 'max_completion_tokens': 16384,
        'prior_attempts': prior.get('remote_attempts', 0)+prior.get('prior_attempts', 0),
        'prior_reserved_or_used_cny': prior.get('reserved_or_used_cny', 0)+prior.get('prior_reserved_or_used_cny', 0),
        'price_cny_per_million': {'input': 2, 'output': 8},
        'pricing_source': 'https://help.aliyun.com/zh/model-studio/qwen3-7-plus',
        'reserved_or_used_cny': 0, 'calls': [], 'errors': []}
    def save():
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    save()
    requests_by_thread = {}
    # Scope the network guard to this disposable process. No credentials in logs.
    import httpx
    original_init = httpx.Client.__init__
    def guard(request):
        if request.url.host in {'127.0.0.1', 'localhost', '::1'}:
            return
        if request.url.host != 'dashscope.aliyuncs.com' or not request.url.path.endswith('/chat/completions'):
            raise RuntimeError('unexpected remote request blocked')
        payload = json.loads(request.content)
        if payload.get('model') != role.model or payload.get('max_completion_tokens') != 16384 or payload.get('max_tokens') is not None:
            raise RuntimeError('request output budget missing')
        count = len(request.content)
        # UTF-8 bytes upper-bound byte-level input tokens; +10 documented output tolerance.
        reserve = count*2/1_000_000 + (16384+10)*8/1_000_000
        with lock:
            if evidence['errors'] or evidence['remote_attempts'] >= 16 or evidence['input_bytes']+count > 180000 or evidence['prior_reserved_or_used_cny']+evidence['reserved_or_used_cny']+reserve > 1:
                raise RuntimeError('paid acceptance budget exhausted or prior failure')
            evidence['remote_attempts'] += 1
            evidence['input_bytes'] += count
            evidence['reserved_or_used_cny'] += reserve
            evidence['calls'].append({'index': evidence['remote_attempts'], 'input_bytes': count,
                'reserved_cny': reserve, 'status': 'requested', 'started_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                'mode': 'no_tools' if not payload.get('tools') else 'tools_available'})
            requests_by_thread[threading.get_ident()] = evidence['calls'][-1]
            save()
    def guarded_init(self, *a, **k):
        hooks = dict(k.pop('event_hooks', {}) or {})
        hooks['request'] = [*hooks.get('request', []), guard]
        k['event_hooks'] = hooks
        k.setdefault('trust_env', False)
        original_init(self, *a, **k)
    httpx.Client.__init__ = guarded_init
    from langchain_openai import ChatOpenAI
    original_payload = ChatOpenAI._get_request_payload
    def paid_payload(self, *a, **k):
        payload = original_payload(self, *a, **k)
        # QA-only larger combined allowance includes reasoning; production is untouched.
        payload.pop('max_tokens', None)
        payload['max_completion_tokens'] = 16384
        content = '\n'.join(str(m.get('content', '')) for m in payload.get('messages', []))
        if 'x_n=-2x_{n-1}+2z_{n-1}' in content:
            payload.pop('tools', None)
            payload.pop('tool_choice', None)
            payload.pop('parallel_tool_calls', None)
        return payload
    ChatOpenAI._get_request_payload = paid_payload
    from langchain_core.callbacks import BaseCallbackHandler
    class Receipt(BaseCallbackHandler):
        def on_llm_end(self, response, **kwargs):
            message = response.generations[0][0].message
            usage = message.usage_metadata or {}
            with lock:
                receipt = requests_by_thread.get(threading.get_ident())
                if receipt:
                    receipt.update(status='returned', usage=usage,
                        ended_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                        finish_reason=message.response_metadata.get('finish_reason'))
                    if usage.get('input_tokens') is not None and usage.get('output_tokens') is not None:
                        actual = (usage['input_tokens']*2+usage['output_tokens']*8)/1_000_000
                        receipt['estimated_cost_cny'] = actual
                        evidence['reserved_or_used_cny'] += actual-receipt['reserved_cny']
                save()
        def on_llm_error(self, error, **kwargs):
            with lock:
                evidence['errors'].append({'error_type': type(error).__name__})
                save()
    from llm.factory import build_chat_model
    from llm.agent_adapter import NativeToolAdapter
    from backend.services.agent_runtime import chat_binding
    def factory(resolved, temperature, **kwargs):
        model = build_chat_model(resolved, temperature, **kwargs, stream_usage=True)
        model.callbacks = [Receipt()]
        return model
    chat_binding.build_adapter = lambda registry: NativeToolAdapter(role, registry, model_factory=factory)
    # Reject a fourth UI task, before any remote request; preserve existing per-run budgets.
    from backend.services.agent_runtime.store import RuntimeStore
    original_create = RuntimeStore.create
    tasks = set()
    def limited_create(self, command):
        if command.request_key not in tasks and len(tasks) >= 4:
            raise RuntimeError('four-question acceptance complete')
        tasks.add(command.request_key)
        if 'x_n=-2x_{n-1}+2z_{n-1}' in command.goal:
            command = replace(command, budget_calls=0, budget_model_calls=1)
        return original_create(self, command)
    RuntimeStore.create = limited_create
    import backend.main as backend
    backend._start_warmup = lambda: None
    backend._update_warmup(status='ready', stage='ready', message='隔离真实模型验收')
    backend.app.router.routes = [r for r in backend.app.router.routes if getattr(r, 'name', None) != 'static']
    backend.app.mount('/', backend.SPAStaticFiles(directory=str(ROOT/'frontend/dist'), html=True), name='qa-static')
    import uvicorn
    uvicorn.run(backend.app, host='127.0.0.1', port=18042, log_level='warning')


if __name__ == '__main__':
    main()
