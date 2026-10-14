"""Disposable Electron QA: production factory/adapter/SQL/SSE, HTTP model fixture."""
from pathlib import Path
import os
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['TEXA_QA_NATIVE_MATH'] = '0'
fixture = runpy.run_path(str(ROOT / 'scripts/qa-live-server.py'), run_name='qa_fixture')
from backend.api import system
from llm import profiles
from llm.configuration import model_settings_payload

# Real profile/catalog selection; only fake keys and disposable profile files.
system.profiles_payload = profiles.profiles_payload
for identity, provider, model, name in [('qa-qwen', 'qwen', 'qwen3.7-plus', 'QA Qwen 默认'),
                                        ('qa-flash', 'deepseek', 'deepseek-flash', 'QA Flash 可选')]:
    payload = model_settings_payload({})
    payload.update(id=identity, name=name, multimodal_mode='native')
    for role in ('reasoning', 'vision'):
        payload['roles'][role].update(provider=provider, model=model, credential_id=provider)
        payload['credentials'][role]['api_key'] = 'qa-fake-key'
        payload['endpoints'][role]['base_url'] = 'https://example.invalid/v1'
    result = system.save_model_profile({'profile': payload, 'activate': identity == 'qa-qwen'})
    if not result['success']:
        raise RuntimeError('QA profile setup failed')

import httpx
import json
import time
from openai import OpenAI
from llm import factory
from llm.types import Capability
from tests.test_deepseek_production import completion
from tests.test_native_math_loop import SUCCESS

original_factory = factory._chat_transports['openai_compatible']

def controlled(resolved, temperature, **kwargs):
    def transport(request):
        body = json.loads(request.content)
        messages = body['messages']
        slow = any('计算 7' in str(m.get('content')) for m in messages if m['role'] == 'user')
        if not body.get('tools'):
            chunks = completion('建议先梳理概念，再用例题检查理解。', reasoning='PRIVATE_REASONING_NEVER_EXPORT')
        elif any(m['role'] == 'tool' for m in messages):
            if slow:
                time.sleep(8)
            chunks = completion('结果是 7。' if slow else '结果是 1024。', reasoning='')
        else:
            calls = [dict(c) for step in SUCCESS[:2] for c in step['tool_calls']]
            if slow:
                calls[0] = {**calls[0], 'args': {'operation': 'calculate', 'expression': '7'}}
                calls[1] = {**calls[1], 'args': {'kind': 'equivalence', 'left': '7', 'right': '7'}}
            chunks = completion('正在计算并核验。', calls)
        stream = ''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks) + 'data: [DONE]\n\n'
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=stream)
    client = OpenAI(api_key='qa-fake-key', base_url='https://example.invalid/v1',
        http_client=httpx.Client(transport=httpx.MockTransport(transport)), max_retries=0)
    return original_factory(resolved, temperature, **kwargs).model_copy(update={'client': client.chat.completions})

factory.register_chat_transport('openai_compatible', controlled,
    capabilities=factory.transport_capabilities('openai_compatible'))
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(fixture['main'].app, host='127.0.0.1', port=18041, log_level='warning')
