from fastapi.testclient import TestClient

from backend.main import app


def test_client_side_routes_fall_back_to_react_entrypoint():
    client = TestClient(app)

    response = client.get("/settings")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<div id="root">' in response.text


def test_unknown_api_and_asset_paths_do_not_fall_back_to_react():
    client = TestClient(app)

    api_response = client.get("/api/does-not-exist")
    api_root_response = client.get("/api")
    asset_response = client.get("/assets/does-not-exist.js")
    extensionless_asset_response = client.get("/assets/does-not-exist")

    assert api_response.status_code == 404
    assert api_response.json() == {"detail": "Not Found"}
    assert api_root_response.status_code == 404
    assert asset_response.status_code == 404
    assert extensionless_asset_response.status_code == 404

def test_health_exposes_current_desktop_instance_id(monkeypatch):
    monkeypatch.setenv("KAOYAN_INSTANCE_ID", "desktop-instance-test")
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["instance_id"] == "desktop-instance-test"
