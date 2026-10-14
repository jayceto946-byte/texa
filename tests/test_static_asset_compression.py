import gzip

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from backend.security import LocalApiBoundaryMiddleware
from backend.static_assets import StaticAssetCompression


def test_static_css_compressed_with_identity_and_range_preserved(tmp_path):
    assets = tmp_path / 'assets'
    assets.mkdir()
    css = 'body{color:black}\n' * 10000
    (assets / 'app.css').write_text(css)
    app = FastAPI()
    app.mount('/', StaticAssetCompression(StaticFiles(directory=tmp_path)))
    client = TestClient(app)
    compressed = client.get('/assets/app.css', headers={'Accept-Encoding': 'gzip'})
    assert compressed.status_code == 200
    assert compressed.headers['content-encoding'] == 'gzip'
    assert 'Accept-Encoding' in compressed.headers['vary']
    assert compressed.text == css
    with client.stream('GET', '/assets/app.css', headers={'Accept-Encoding': 'gzip'}) as stream:
        raw = b''.join(stream.iter_raw())
    assert len(raw) < len(css) / 10
    assert gzip.decompress(raw).decode() == css
    identity = client.get('/assets/app.css', headers={'Accept-Encoding': 'identity'})
    assert 'content-encoding' not in identity.headers
    assert identity.text == css
    partial = client.get('/assets/app.css', headers={'Range': 'bytes=0-15', 'Accept-Encoding': 'gzip'})
    assert partial.status_code == 206
    assert 'content-encoding' not in partial.headers
    assert len(partial.content) == 16


def test_wrapper_does_not_compress_sse_or_bypass_auth(monkeypatch):
    monkeypatch.setenv('KAOYAN_REQUIRE_API_TOKEN', '1')
    monkeypatch.setenv('KAOYAN_API_TOKEN', 'test-only-token')
    app = FastAPI()
    app.add_middleware(LocalApiBoundaryMiddleware)

    @app.get('/api/chat/test-stream')
    def stream():
        return StreamingResponse(iter(['data: first\n\n', 'data: final\n\n']), media_type='text/event-stream')

    # Even if used outside the static mount, the wrapper excludes all APIs.
    client = TestClient(StaticAssetCompression(app))
    assert client.get('/api/chat/test-stream').status_code == 401
    response = client.get('/api/chat/test-stream', headers={'X-Kaoyan-Token': 'test-only-token', 'Accept-Encoding': 'gzip'})
    assert response.status_code == 200
    assert 'content-encoding' not in response.headers
    assert response.text == 'data: first\n\ndata: final\n\n'


def test_only_successful_hashed_assets_are_immutable(tmp_path):
    assets = tmp_path / 'assets'
    assets.mkdir()
    (assets / 'app-abcdefgh.js').write_text('console.log(1)')
    (assets / 'plain.js').write_text('console.log(1)')
    app = FastAPI()
    app.mount('/', StaticAssetCompression(StaticFiles(directory=tmp_path)))
    client = TestClient(app)
    assert 'immutable' in client.get('/assets/app-abcdefgh.js').headers['cache-control']
    assert 'cache-control' not in client.get('/assets/plain.js').headers
    assert 'cache-control' not in client.get('/assets/missing-abcdefgh.js').headers
