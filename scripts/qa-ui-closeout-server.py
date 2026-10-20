"""Disposable production backend for UI evidence; no production storage mutations.

Notes use the real SessionNoteService/store. Live mode uses the configured provider
with authored input and a two-request guard; instrumentation never replaces SSE.
"""
import argparse
import copy
import hashlib
import json
import logging
import os
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['notes', 'live'], required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    qa = args.root.resolve()
    if not qa.is_relative_to(Path('/private/tmp')) or qa.exists():
        parser.error('use a new, disposable /private/tmp directory')
    qa.mkdir(parents=True)
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    env_file = Path.home() / 'Library/Application Support/kaoyan-assistant-desktop/.env'
    os.environ.update(ENV_PATH=str(env_file), DATA_DIR=str(qa/'data'),
        PROGRESS_PATH=str(qa/'progress'), BOOKS_PATH=str(qa/'books'),
        VECTOR_DB_PATH=str(qa/'vector'), MINERU_OUTPUT_PATH=str(qa/'mineru'),
        HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
        KAOYAN_TRUSTED_ORIGINS='http://127.0.0.1:18136',
        TEXA_NATIVE_MODEL_TIMEOUT='180', TEXA_NATIVE_RUN_TIMEOUT='240')
    from config import get_model_role_config
    role = get_model_role_config()
    endpoint = urlparse(role.endpoint)
    plan = json.loads((evidence/'real-sse-plan.json').read_text())
    if args.mode == 'live' and (role.provider.provider_id != plan['provider'] or role.model != plan['model'] or not role.credential_configured or endpoint.hostname != 'api.deepseek.com'):
        raise SystemExit('configured role no longer matches the reviewed plan')
    receipts = {'mode': args.mode, 'provider': role.provider.provider_id, 'model': role.model,
        'endpoint_host': endpoint.hostname, 'endpoint_path': endpoint.path,
        'max_remote_requests': 2 if args.mode == 'live' else 0,
        'requests': [], 'provider_errors': [], 'usage': [], 'notes_api': []}
    lock = threading.RLock()
    receipt_path = evidence/f'{args.mode}-server-receipts.json'
    if receipt_path.exists():
        raise SystemExit('preserve prior receipts; choose another evidence directory')
    def save():
        receipt_path.write_text(json.dumps(receipts, ensure_ascii=False, indent=2))
    save()
    import httpx
    original_init = httpx.Client.__init__
    def guard(request):
        if request.url.host in {'127.0.0.1', 'localhost', '::1'}:
            return
        body = json.loads(request.content) if request.content else {}
        with lock:
            if args.mode != 'live' or request.url.host != endpoint.hostname or not request.url.path.endswith('/chat/completions') or body.get('model') != role.model:
                raise RuntimeError('remote request outside UI verification scope')
            if len(receipts['requests']) >= 2 or receipts['provider_errors']:
                raise RuntimeError('UI verification remote budget exhausted')
            if len(request.content) > 80000 or not 1 <= int(body.get('max_tokens', body.get('max_completion_tokens', 0))) <= 4096:
                raise RuntimeError('UI verification payload budget invalid')
            # Only a new, authored UI prompt is permitted in the model's user text.
            text = '\n'.join(str(m.get('content', '')) for m in body.get('messages', []) if m.get('role') == 'user')
            if plan['prompt'] not in text:
                raise RuntimeError('unreviewed model input blocked')
            receipts['requests'].append({'number': len(receipts['requests'])+1,
                'payload_sha256': hashlib.sha256(request.content).hexdigest(),
                'input_bytes': len(request.content), 'stream': body.get('stream'),
                'max_tokens': body.get('max_tokens', body.get('max_completion_tokens'))})
            save()
    def response_hook(response):
        if response.request.url.host == endpoint.hostname and response.status_code >= 400:
            with lock:
                receipts['provider_errors'].append({'status': response.status_code})
                save()
    def guarded_init(self, *a, **kw):
        hooks = dict(kw.pop('event_hooks', {}) or {})
        hooks['request'] = [*hooks.get('request', []), guard]
        hooks['response'] = [*hooks.get('response', []), response_hook]
        kw['event_hooks'] = hooks
        original_init(self, *a, **kw)
    httpx.Client.__init__ = guarded_init
    from langchain_openai import ChatOpenAI
    payload = ChatOpenAI._get_request_payload
    def bounded_payload(self, *a, **kw):
        body = payload(self, *a, **kw)
        body.pop('max_tokens', None)
        body['max_completion_tokens'] = 4096
        return body
    ChatOpenAI._get_request_payload = bounded_payload
    # Set retries before the official factory constructs its transport.
    import llm.factory as factory
    original_transport = factory._chat_transports['openai_compatible']
    def bounded_transport(resolved, temperature, **kw):
        kw['max_retries'] = 0
        return original_transport(resolved, temperature, **kw)
    factory.register_chat_transport('openai_compatible', bounded_transport,
        capabilities=factory.transport_capabilities('openai_compatible'))
    from memory.session_notes import SessionNoteStore, encode, now
    from backend.services.session_notes.validation import validate_document
    store = SessionNoteStore(qa/'progress/session_notes.db')
    stamp = now()
    snapshot = {'id': 'review-snapshot', 'schema_version': 1,
        'conversation_id': 'review-origin', 'title_snapshot': '结构等价的长中文笔记样本',
        'subject': '数学/高数', 'captured_at': stamp,
        'selection': {'conversation_id': 'review-origin', 'turn_ids': ['review-turn'], 'through_seq': 2},
        'input_hash': 'authored-ui-sample', 'sources': [], 'evidence': [], 'warnings': [], 'chapter_refs': []}
    content = json.loads((evidence/'note-content.json').read_text())
    document, quality = validate_document(content, snapshot)
    draft = {'id': 'review-draft', 'schema_version': 1, 'kind': 'generation',
        'status': 'editable', 'draft_revision': 1, 'conversation_id': 'review-origin',
        'source_snapshot_ids': ['review-snapshot'], 'content': {**document, 'quality': quality},
        'base_note_id': None, 'base_note_revision': None, 'job_id': None,
        'created_at': stamp, 'updated_at': stamp}
    with store.transaction() as conn:
        conn.execute('INSERT INTO note_source_snapshots VALUES(?,?)', (snapshot['id'], encode(snapshot)))
        store.put_draft(conn, draft)
    from backend.services.session_notes.service import SessionNoteService
    service = SessionNoteService(store)
    receipt = service.save('review-draft', {'operation_id': 'review-seed-save', 'expected_draft_revision': 1, 'base_note_revision': None})
    # A fresh generation-style editable draft begins in preview; a real edit draft
    # of the saved asset begins in edit mode. Both contain the same source material.
    draft = {**copy.deepcopy(draft), 'id': 'review-preview', 'status': 'editable'}
    with store.transaction() as conn:
        store.put_draft(conn, draft)
    edit = service.create_draft(kind='edit', note_id=receipt['note_id'], base_revision=1)
    (evidence/f'{args.mode}-fixture-ids.json').write_text(json.dumps({'note_id': receipt['note_id'], 'draft_id': edit['id'], 'preview_id': 'review-preview', 'qa_root': str(qa)}, indent=2))
    import backend.main as backend
    backend._start_warmup = lambda: None
    backend._update_warmup(status='ready', stage='ready', message='isolated UI evidence backend')
    backend.app.router.routes = [r for r in backend.app.router.routes if getattr(r, 'name', None) != 'static']
    backend.app.mount('/', backend.SPAStaticFiles(directory=str(ROOT/'frontend/dist'), html=True), name='qa-static')
    @backend.app.middleware('http')
    async def note_receipt(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/notes'):
            with lock:
                receipts['notes_api'].append({'method': request.method, 'path': request.url.path, 'status': response.status_code})
                save()
        return response
    # Raw provider errors/bodies/credentials are intentionally excluded from evidence.
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING)
    import uvicorn
    uvicorn.run(backend.app, host='127.0.0.1', port=18136, log_level='error')


if __name__ == '__main__':
    main()
