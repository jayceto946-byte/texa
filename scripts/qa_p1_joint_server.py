"""Disposable SQL/SSE replay for the existing Electron conversation view."""
import os
from pathlib import Path
import tempfile

qa = Path(os.environ['TEXA_JOINT_UI_ROOT']).resolve()
assert qa.is_relative_to(Path(tempfile.gettempdir()).resolve()) and qa.name.startswith('texa-joint-ui-')
assert Path(os.environ['DATA_DIR']).resolve() == qa / 'data'
assert Path(os.environ['PROGRESS_PATH']).resolve() == qa / 'progress'

from backend.main import app, _update_warmup
from backend.conversation_memory import append_message
from backend.services.agent_runtime.locator import public_task
from tests.test_deepseek_production import completion, wire_run
from tests.test_native_math_loop import SUCCESS
from backend.services.agent_runtime import chat_binding as binding
import pytest
import asyncio
import json


def replay(root, question, responses):
    store, run, runner, state, requests = wire_run(root, responses)
    state['user_input'] = question
    store.configure_chat(run, 'owner', state=state, candidates=runner.candidate_tools,
                         request_question=question, book_name='', subject='数学')
    async def consume():
        response = binding.stream_run(store, run, 'owner', runner.registry, runner.adapter)
        events = [json.loads(chunk[6:]) async for chunk in response.body_iterator]
        await response.aclose()
        return events
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(binding, 'project_outcomes', lambda _: None)
        events = asyncio.run(consume())
    return store, store.snapshot(run), events, requests

cases = []
for name in ('strict', 'failed', 'verified'):
    question = '计算 2^10'
    if name == 'strict':
        question += '。只输出三行，依次以“结论：”“反例：”“原因：”开头。'
        responses = [completion('先进行公开计算。', SUCCESS[0]['tool_calls']),
                     completion('结论：1024\n反例：无\n原因：计算得到', reasoning='')]
    elif name == 'failed':
        calls = [{'id': f'calc-{n}', 'name': 'symbolic_math',
                  'args': {'operation': 'calculate', 'expression': f'2^{n}'}} for n in (10, 9, 8, 7)]
        responses = [completion('', calls)]
    else:
        responses = [completion('', SUCCESS[0]['tool_calls'] + SUCCESS[1]['tool_calls']),
                     completion('结果是 1024。', reasoning='')]
    root = qa / name
    root.mkdir(parents=True, exist_ok=True)
    store, snapshot, events, requests = replay(root, question, responses)
    task = public_task(store, snapshot)
    conversation = 'qa-joint-' + name
    append_message(conversation, 'user', question, subject='数学', turn_id='fixture-' + name)
    append_message(conversation, 'assistant', snapshot['run']['output']['answer'], subject='数学',
                   turn_id='fixture-' + name, learning_task=task,
                   delivery_status='error' if name == 'failed' else 'degraded' if name == 'strict' else 'complete')
    cases.append({'case': name, 'conversation': conversation, 'task_status': task['status'],
                  'verification': task['verification']['status']})

_update_warmup(status='ready', stage='ready', message='Isolated joint fixture; startup not tested')


@app.get('/p1-joint-fixture')
def fixture():
    return {'cases': cases, 'synthetic': True, 'real_model_ui': False}


app.router.routes.insert(0, app.router.routes.pop())
