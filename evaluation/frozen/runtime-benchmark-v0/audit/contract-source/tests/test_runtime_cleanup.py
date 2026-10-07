import sys
import types

from fastapi.testclient import TestClient

from backend.main import app
from ingestion.background_reader import BackgroundReader


def test_health_is_available_while_warmup_has_separate_state():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["warmup"]["status"] in {
        "pending", "starting", "running", "ready", "degraded"
    }


def test_preread_initialization_failure_clears_running(monkeypatch, tmp_path):
    class BrokenReader:
        def __init__(self, book_name):
            raise RuntimeError("reader init failed")

    monkeypatch.setitem(
        sys.modules,
        "ingestion.kimi_reader",
        types.SimpleNamespace(KimiReader=BrokenReader),
    )

    reader = BackgroundReader("demo", [{"title": "chapter"}], tmp_path / "book.pdf")
    reader.progress_file = tmp_path / "progress.json"
    reader._running = True
    reader._run()

    assert reader._running is False
    assert reader.status["running"] is False
    assert reader.status["current"] == "\u5931\u8d25"
    assert "reader init failed" in reader.status["error"]
