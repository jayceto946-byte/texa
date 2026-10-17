"""Local-only R1/R2 QA: read-only source snapshots, real APIs, isolated writes.

Run with venv310 Python, --source DESKTOP_DATA --work PRIVATE_IGNORED_DIR.
No credentials are copied. --serve uses controlled answer generation, never a model.
All payloads and screenshots must remain outside Git.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--serve', action='store_true')
parser.add_argument('--port', type=int, default=18065)
args = parser.parse_args()
source, work = args.source.resolve(), args.work.resolve()
assert source != work and source not in work.parents and work not in source.parents
assert work.is_relative_to(ROOT / 'artifacts') or work.is_relative_to(Path('/private/tmp'))
work.mkdir(parents=True, exist_ok=True)

def connect_ro(path):
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)

def fingerprint(path):
    with connect_ro(path) as connection:
        return hashlib.sha256('\n'.join(connection.iterdump()).encode()).hexdigest()

databases = sorted([*(source / 'progress').glob('exercise_bank_*.db'), *(source / 'progress').glob('mistake_book_*.db')])
before = {p.name: fingerprint(p) for p in databases}
if not args.serve:
    assert not (work / 'data').exists(), 'use a fresh QA directory'
    (work / 'source-fingerprints.json').write_text(json.dumps(before, sort_keys=True))
    (work / 'data/progress').mkdir(parents=True)
    for path in databases:
        with connect_ro(path) as src, sqlite3.connect(work / 'data/progress' / path.name) as dst:
            src.backup(dst)
    for path in (source / 'progress').glob('*/canonical_document.jsonl'):
        shutil.copytree(path.parent, work / 'data/progress' / path.parent.name)
    registry = source / 'progress/book_registry.json'
    if registry.exists():
        shutil.copy2(registry, work / 'data/progress/book_registry.json')
    if (source / 'images').exists():
        shutil.copytree(source / 'images', work / 'data/images')
    # Absolute image references in the copy must never access the source images.
    for path in [*(work / 'data/progress').glob('exercise_bank_*.db'), *(work / 'data/progress').glob('mistake_book_*.db')]:
        with sqlite3.connect(path) as conn:
            table = 'exercises' if path.name.startswith('exercise_') else 'mistakes'
            for rid, payload in conn.execute(f'SELECT id, data FROM {table}').fetchall():
                payload = payload.replace(str(source), str(work / 'data'))
                conn.execute(f'UPDATE {table} SET data=? WHERE id=?', (payload, rid))

# Isolation is established before any application import. Never load the real .env.
for key in list(os.environ):
    if key.endswith(('_API_KEY', '_API_TOKEN')) or key in {'PROGRESS_PATH', 'BOOKS_PATH', 'VECTOR_DB_PATH', 'IMAGES_PATH'}:
        os.environ.pop(key)
os.environ.update(ENV_PATH='/dev/null', DATA_DIR=str(work / 'data'), MINERU_OUTPUT_PATH=str(work / 'mineru'),
                  KAOYAN_REQUIRE_API_TOKEN='0', KAOYAN_TRUSTED_ORIGINS=f'http://127.0.0.1:{args.port}',
                  SKIP_VECTOR_WARMUP='1', SKIP_EMBEDDING_WARMUP='1')
from backend.main import app
from backend.api import exercises
from fastapi.testclient import TestClient
import memory.exercise_file_importer as file_importer

def reject_model_refinement(*_args, **_kwargs):
    raise RuntimeError('Model refinement is disabled in isolated QA')

exercises.refine_low_confidence_candidates = reject_model_refinement
file_importer.MINERU_API_URL = ''  # text-layer file checks only; never remote OCR

# Fixed answer producer only; production job creation/polling/persistence/save remain real.
def controlled_answer(req, book_name='default'):
    time.sleep(.3)
    return {'success': True, 'data': {'answer': '## 隔离任务合同样例\n\n$1+1=2$\n\n' + '这是受控结果，不是真实模型验证。\n\n' * 100}}
exercises.generate_exercise_answer = controlled_answer

@app.middleware('http')
async def disallow_paid_requests(request, call_next):
    from starlette.responses import JSONResponse
    path = request.url.path
    if path == '/api/system/remote-ready':
        return JSONResponse({'success': True, 'data': {'ready': True, 'qa_controlled_producer': True}})
    if path == '/api/system/settings' and request.method == 'GET':
        from backend.api.system import get_settings
        settings = get_settings()
        settings['data']['models']['credentials']['reasoning']['required'] = False
        settings['data']['qa_controlled_producer'] = True
        return JSONResponse(settings)
    allowed_write = path.startswith(('/api/exercises/', '/api/review/sessions', '/api/mistakes/query'))
    allowed_mistake = path.startswith('/api/mistakes/') and (request.method == 'PATCH' or path.endswith('/actions'))
    if request.method != 'GET' and not (allowed_write or allowed_mistake):
        return JSONResponse({'success': False, 'message': 'QA environment: operation blocked'}, status_code=403)
    if path.endswith(('/explain', '/solve-image', '/recognize-image')):
        return JSONResponse({'success': False}, status_code=403)
    return await call_next(request)

if args.serve:
    import uvicorn
    from backend.main import _update_warmup
    _update_warmup(status='ready', stage='ready', message='Isolated QA: warmup and lifecycle disabled')
    uvicorn.run(app, host='127.0.0.1', port=args.port, lifespan='off', log_level='warning')
    raise SystemExit

client = TestClient(app)  # no lifespan: no schedulers, warmups, or recovery workers
checks = []
def check(ok, name):
    checks.append({'name': name, 'status': 'PASS' if ok else 'FAIL'})
    assert ok, name

def request(method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    assert response.status_code < 400, (path, response.status_code)
    result = response.json()
    assert result.get('success') is True, (path, result.get('message'))
    return result

try:
    candidates = []
    for path in (work / 'data/progress').glob('exercise_bank_*.db'):
        with sqlite3.connect(path) as connection:
            n = connection.execute('SELECT count(*) FROM exercises').fetchone()[0]
        if n:
            candidates.append((n, path.name[len('exercise_bank_'):-3]))
    count, book = max(candidates)
    query = '?book_name=' + quote(book)
    overview = request('POST', '/api/exercises/overview' + query, json={})['data']
    records = overview['records']
    check(len(records) == count, 'real bank records / overview contract')
    bank = exercises._bank(book)
    check(all(bank.get(row['id']).question_text == row['question_text'] for row in records), 'API preserves complete real question text')
    active = overview.get('practice_session')
    if active and active['status'] in {'active', 'paused'}:
        request('POST', f"/api/exercises/practice-sessions/{active['id']}/abandon" + query, json={})
    session = request('POST', '/api/exercises/practice-sessions' + query, json={'limit': 2})['data']
    session_id = session['id']
    base = f'/api/exercises/practice-sessions/{session_id}'
    check(request('POST', base + '/pause' + query, json={})['data']['status'] == 'paused', 'pause real practice')
    check(request('POST', base + '/resume' + query, json={})['data']['id'] == session_id, 'resume same persisted practice')
    for _ in range(2):
        exercise_id = session['current_exercise']['id']
        body = {'exercise_id': exercise_id, 'user_answer': '隔离副本作答 $x^2$', 'quality': 3}
        answer = request('POST', base + '/answer' + query, json=body)
        session = answer['data']
        replay = request('POST', base + '/answer' + query, json=body)
        check(replay['record']['practice_count'] == answer['record']['practice_count'], 'answer replay does not duplicate practice count')
    check(session['status'] == 'completed' and session['summary']['answered'] == 2, 'complete practice and update summary')
    check(request('GET', base + query)['data']['status'] == 'completed', 'reload persisted completion')
    ex = records[0]
    original_answer = bank.get(ex['id']).answer
    job = request('POST', '/api/exercises/answer/jobs' + query, json={'id': ex['id']})['data']
    again = request('POST', '/api/exercises/answer/jobs' + query, json={'id': ex['id']})['data']
    check(again['id'] == job['id'], 'active job reuse on real API with controlled producer')
    for _ in range(100):
        job = request('GET', '/api/exercises/answer/jobs/' + job['id'])['data']
        if job['status'] == 'completed': break
        time.sleep(.02)
    check(job['status'] == 'completed' and bank.get(ex['id']).answer == original_answer, 'controlled completed job never saves official answer')
    saved = request('POST', '/api/exercises/answer/save' + query, json={'id': ex['id'], 'answer': job['result']['answer']})['data']
    check(bank.get(ex['id']).answer == saved['answer'], 'explicit save persists edited answer')
    extracted = request('POST', '/api/exercises/textbook-analyze' + query, json={'book_name': book, 'limit': 200, 'use_llm': False})
    check(len(extracted['data']) > 0 and bool(extracted['extract']['text']), 'real Canonical textbook extraction without OCR/model')
    # Store private identities separately; never commit this file or real payloads.
    (work / 'private-context.json').write_text(json.dumps({'book': book, 'exercise_id': ex['id'], 'candidate_count': len(extracted['data'])}, ensure_ascii=False))
    query_result = request('POST', '/api/mistakes/query' + query, json={'limit': 100})['data']['items']
    default_result = request('POST', '/api/mistakes/query?book_name=default', json={'limit': 100})['data']['items']
    mistake_records = [(book, x) for x in query_result] + [('default', x) for x in default_result]
    if not mistake_records:
        checks.append({'name': 'real mistake lifecycle (source has zero records)', 'status': 'NOT TESTED'})
    for scope, row in mistake_records[:2]:
        mq = '?book_name=' + quote(scope)
        detail = request('GET', '/api/mistakes/' + row['id'] + mq)['data']
        check(all(key in detail for key in ['question_text', 'user_answer', 'correct_answer', 'source_ref', 'revision', 'review_history']), 'real mistake detail fields')
        if detail.get('image_path'):
            check(client.get('/api/mistakes/' + row['id'] + '/image' + mq).status_code == 200, 'isolated image resource resolves within copied image root')
        original_visibility = detail['visibility']
        action = 'restore' if original_visibility == 'archived' else 'archive'
        changed = request('POST', '/api/mistakes/' + row['id'] + '/actions' + mq, json={'action': action, 'expected_revision': detail['revision'], 'operation_id': 'qa-archive-' + row['id']})['data']
        request('POST', '/api/mistakes/' + row['id'] + '/actions' + mq, json={'action': 'archive' if action == 'restore' else 'restore', 'expected_revision': changed['revision'], 'operation_id': 'qa-restore-' + row['id']})
        restored = request('GET', '/api/mistakes/' + row['id'] + mq)['data']
        check(restored['visibility'] == original_visibility and restored['question_text'] == detail['question_text'], 'archive/restore preserves real content')
        session = request('POST', '/api/review/sessions', json={'mistake_ids': [row['id']], 'book_name': scope})['data']
        session_path = '/api/review/sessions/' + session['id']
        draft = request('PATCH', session_path + mq, json={'expected_revision': session['revision'], 'answer': '隔离副本独立重做', 'revealed': False})['data']
        revealed = request('PATCH', session_path + mq, json={'expected_revision': draft['revision'], 'answer': '隔离副本独立重做', 'revealed': True})['data']
        result = request('POST', session_path + '/results' + mq, json={'expected_revision': revealed['revision'], 'operation_id': 'qa-redo-' + row['id'], 'result': 'partial'})['data']
        check(result['index'] == 1, 'real mistake independent redo persists user-confirmed result')
        private = json.loads((work / 'private-context.json').read_text())
        private.update(mistake_id=row['id'], mistake_book=scope)
        (work / 'private-context.json').write_text(json.dumps(private, ensure_ascii=False))
    # Large/malformed/empty inputs remain explicitly synthetic supplements.
    invalid = client.post('/api/exercises/batch-add' + query, json={'exercises': [{'question_text': 'q', 'tags': 42}]})
    check(invalid.status_code == 422, 'synthetic malformed batch rejected')
    empty = request('POST', '/api/exercises/batch-add' + query, json={'exercises': []})
    check(empty['count'] == 0, 'empty batch is explicit')
    batch = request('POST', '/api/exercises/batch-add' + query, json={'exercises': [{'question_text': f'隔离规模题{i}：求 $x^2$ 的导数。', 'origin_id': f'qa-{i}'} for i in range(220)]})
    check(batch['count'] == 220, 'synthetic 220 record batch persists')
except Exception as exc:
    checks.append({'name': 'runner exception', 'status': 'FAIL', 'error_type': type(exc).__name__})
    raise
finally:
    unchanged = before == {p.name: fingerprint(p) for p in databases}
    checks.append({'name': 'source database logical fingerprints unchanged', 'status': 'PASS' if unchanged else 'FAIL'})
    (work / 'results.json').write_text(json.dumps({'environment': 'local real-data copies; real API/storage; controlled answer producer; no model/OCR calls; no lifespan workers', 'checks': checks}, ensure_ascii=False, indent=2))
    print(json.dumps({'checks': len(checks), 'failures': sum(x['status'] == 'FAIL' for x in checks), 'source_unchanged': unchanged}))
