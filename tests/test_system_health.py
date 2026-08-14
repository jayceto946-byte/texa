from fastapi.testclient import TestClient

from backend.api import system
from backend.main import app


def test_system_health_reports_all_components(monkeypatch, tmp_path):
    monkeypatch.setattr(system, "PROGRESS_PATH", tmp_path / "progress")
    monkeypatch.setattr(
        system,
        "_check_vector_store",
        lambda: system._component("healthy", "vector ok", collection_count=3),
    )

    client = TestClient(app)
    response = client.get("/api/system/health?book_name=demo")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["book_name"] == "demo"
    assert set(data["components"]) == {
        "vector_store",
        "mistake_book",
        "exercise_bank",
        "rag_trace",
        "runtime_config",
        "embedding_runtime",
    }
    assert data["components"]["vector_store"]["details"]["collection_count"] == 3


def test_system_health_escalates_component_error(monkeypatch, tmp_path):
    monkeypatch.setattr(system, "PROGRESS_PATH", tmp_path / "progress")
    monkeypatch.setattr(system, "_check_vector_store", lambda: system._component("error", "disk I/O error"))

    client = TestClient(app)
    data = client.get("/api/system/health?book_name=demo").json()

    assert data["status"] == "error"
    assert data["components"]["vector_store"]["message"] == "disk I/O error"
