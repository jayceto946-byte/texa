from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.security import (
    LocalApiBoundaryMiddleware,
    authorize_api_client,
    is_loopback_client,
    is_write_request,
)


def test_loopback_api_is_available_without_token():
    assert is_loopback_client("127.0.0.1") is True
    assert is_loopback_client("::1") is True
    assert authorize_api_client("127.0.0.1", "", "")[0] is True


def test_remote_api_is_closed_when_no_token_is_configured():
    allowed, reason = authorize_api_client("192.168.1.8", "", "")
    assert allowed is False
    assert reason == "remote_disabled"


def test_remote_api_requires_constant_time_shared_token():
    assert authorize_api_client("192.168.1.8", "wrong", "secret") == (False, "invalid_token")
    assert authorize_api_client("192.168.1.8", "secret", "secret") == (True, "token")


def test_token_can_be_required_even_for_loopback():
    assert authorize_api_client("127.0.0.1", "", "secret", require_token=True) == (False, "invalid_token")
    assert authorize_api_client("127.0.0.1", "secret", "secret", require_token=True) == (True, "token")


def _test_client(monkeypatch, *, token: str = "", require_token: bool = False):
    monkeypatch.setenv("KAOYAN_API_TOKEN", token)
    monkeypatch.setenv("KAOYAN_REQUIRE_API_TOKEN", "1" if require_token else "0")
    app = FastAPI()
    app.add_middleware(LocalApiBoundaryMiddleware)

    @app.post("/api/write")
    def write():
        return {"success": True}

    @app.post("/api/exercises/list")
    def list_exercises():
        return {"success": True, "data": []}

    return TestClient(app)


def test_untrusted_web_origin_cannot_write_to_loopback(monkeypatch):
    client = _test_client(monkeypatch)
    response = client.post("/api/write", headers={"Origin": "https://malicious.example"})
    assert response.status_code == 403
    assert response.json()["error_code"] == "UNTRUSTED_ORIGIN"


def test_untrusted_origin_can_call_read_only_post_endpoint(monkeypatch):
    client = _test_client(monkeypatch)
    response = client.post(
        "/api/exercises/list",
        headers={"Origin": "https://untrusted-ui.example"},
    )
    assert response.status_code == 200
    assert response.json() == {"success": True, "data": []}


def test_read_only_post_endpoints_are_not_classified_as_writes():
    for path in (
        "/api/exercises/list",
        "/api/exercises/overview",
        "/api/mistakes/list",
        "/api/mistakes/overview",
    ):
        assert is_write_request("POST", path) is False
        assert is_write_request("POST", f"{path}/") is False

    assert is_write_request("POST", "/api/chat/log") is True
    assert is_write_request("POST", "/api/exercises/practice") is True
    assert is_write_request("DELETE", "/api/exercises/list") is True


def test_trusted_local_ui_origins_and_non_browser_client_can_write(monkeypatch):
    client = _test_client(monkeypatch)
    for origin in (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ):
        assert client.post("/api/write", headers={"Origin": origin}).status_code == 200
    assert client.post("/api/write").status_code == 200


def test_valid_desktop_token_is_required_and_bypasses_origin_check(monkeypatch):
    client = _test_client(monkeypatch, token="desktop-secret", require_token=True)
    assert client.post("/api/write").status_code == 401
    response = client.post(
        "/api/write",
        headers={"Origin": "https://malicious.example", "X-Kaoyan-Token": "desktop-secret"},
    )
    assert response.status_code == 200


def test_oversized_upload_is_rejected_before_route_parsing(monkeypatch):
    client = _test_client(monkeypatch)
    response = client.post("/api/books/import", headers={"Content-Length": str(10**12)})
    assert response.status_code == 413
    assert response.json()["error_code"] == "UPLOAD_TOO_LARGE"


def test_request_host_cannot_make_untrusted_origin_trusted(monkeypatch):
    client = _test_client(monkeypatch)
    response = client.post(
        "/api/write",
        headers={"Origin": "http://evil.test", "Host": "evil.test"},
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "UNTRUSTED_ORIGIN"


def test_capture_token_does_not_bypass_upload_limit(monkeypatch):
    monkeypatch.setenv("KAOYAN_CAPTURE_TOKEN", "capture-secret")
    client = _test_client(monkeypatch)
    response = client.post(
        "/api/mistakes/recognize-image",
        headers={
            "X-Kaoyan-Token": "capture-secret",
            "Content-Length": str(10**12),
        },
    )
    assert response.status_code == 413
    assert response.json()["error_code"] == "UPLOAD_TOO_LARGE"
