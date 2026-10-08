import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from backend.remote_reads import RemoteReadOptimization
from backend.security import LocalApiBoundaryMiddleware


def test_finite_lists_are_compressed_timed_and_never_log_credentials(monkeypatch, caplog):
    monkeypatch.setenv('KAOYAN_REQUIRE_API_TOKEN', '1')
    monkeypatch.setenv('KAOYAN_API_TOKEN', 'test-only-secret')
    payload = {'success': True, 'data': {'items': [{'title': '教材会话'}] * 40}}
    app = FastAPI()
    app.add_middleware(RemoteReadOptimization)
    app.add_middleware(LocalApiBoundaryMiddleware)

    @app.get('/api/chat/conversations')
    def sessions():
        return payload

    client = TestClient(app)
    assert client.get('/api/chat/conversations').status_code == 401
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    response = client.get('/api/chat/conversations?subject=private-subject',
        headers={'X-Kaoyan-Token': 'test-only-secret', 'Accept-Encoding': 'gzip'})
    assert response.json() == payload
    assert response.headers['content-encoding'] == 'gzip'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['server-timing'].startswith('texa_read;dur=')
    assert 'S0 read session-list status=200' in caplog.text
    assert 'test-only-secret' not in caplog.text
    assert 'private-subject' not in caplog.text
    assert '教材会话' not in caplog.text


def test_streams_and_writes_bypass_list_optimization():
    app = FastAPI()
    app.add_middleware(RemoteReadOptimization)

    @app.get('/api/chat/stream')
    def stream():
        return StreamingResponse(iter(['data: first\n\n', 'data: done\n\n']), media_type='text/event-stream')

    @app.post('/api/chat/conversations')
    def write():
        return {'success': True}

    client = TestClient(app)
    response = client.get('/api/chat/stream', headers={'Accept-Encoding': 'gzip'})
    assert response.text == 'data: first\n\ndata: done\n\n'
    assert 'content-encoding' not in response.headers
    assert 'server-timing' not in response.headers
    assert 'server-timing' not in client.post('/api/chat/conversations').headers


def test_conversation_body_compression_preserves_auth_and_excludes_subroutes(monkeypatch, caplog):
    monkeypatch.setenv('KAOYAN_REQUIRE_API_TOKEN', '1')
    monkeypatch.setenv('KAOYAN_API_TOKEN', 'test-only-secret')
    app = FastAPI()
    app.add_middleware(RemoteReadOptimization)
    app.add_middleware(LocalApiBoundaryMiddleware)
    payload = {'success': True, 'data': {'messages': [{'content': '教材正文与引用' * 100}]}}

    @app.get('/api/chat/conversations/{identity}')
    def detail(identity: str):
        return payload

    @app.get('/api/chat/conversations/{identity}/messages-after')
    def subroute(identity: str):
        return payload

    client = TestClient(app)
    assert client.get('/api/chat/conversations/private-identity').status_code == 401
    headers = {'X-Kaoyan-Token': 'test-only-secret', 'Accept-Encoding': 'gzip'}
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    response = client.get('/api/chat/conversations/private-identity', headers=headers)
    assert response.json() == payload
    assert response.headers['content-encoding'] == 'gzip'
    assert response.headers['cache-control'] == 'no-store'
    assert 'session-detail' in caplog.text
    assert 'private-identity' not in caplog.text
    assert 'test-only-secret' not in caplog.text
    assert '教材正文' not in caplog.text
    assert 'content-encoding' not in client.get('/api/chat/conversations/private-identity/messages-after', headers=headers).headers
