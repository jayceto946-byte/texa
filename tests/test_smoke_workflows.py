from fastapi.testclient import TestClient

from backend.api import mistakes
from backend.main import app
from memory.mistake_book import MistakeBook


def test_local_smoke_mistake_review_loop(monkeypatch, tmp_path):
    book = MistakeBook(tmp_path / "smoke_mistakes.db")
    monkeypatch.setattr(mistakes, "_mb", lambda book_name="default": book)
    monkeypatch.setattr(mistakes, "_persist_mistake_concepts", lambda record, explanation="", book_name="default": [])

    client = TestClient(app)

    health = client.get("/health").json()
    assert health["status"] == "ok"

    add_res = client.post(
        "/api/mistakes/add",
        json={
            "question_text": "求导：$x^2$",
            "user_answer": "$x$",
            "correct_answer": "$2x$",
            "subject": "数学",
            "tags": "导数",
            "mistake_type": ["计算错误"],
            "explanation": "幂函数求导公式：$(x^2)'=2x$。",
        },
    ).json()
    assert add_res["success"] is True
    mistake_id = add_res["id"]

    list_res = client.post("/api/mistakes/list", json={"limit": 10}).json()
    assert list_res["success"] is True
    assert list_res["data"][0]["id"] == mistake_id

    due_res = client.get("/api/mistakes/due").json()
    assert due_res["success"] is True
    assert any(item["id"] == mistake_id for item in due_res["data"])

    review_res = client.post("/api/mistakes/review", json={"id": mistake_id, "quality": 4}).json()
    assert review_res["success"] is True
    assert review_res["data"]["review_history"][0]["quality"] == 4
    assert review_res["data"]["next_review"] == review_res["next_review"]

    stats = client.get("/api/mistakes/stats").json()
    assert stats["total"] == 1

    weak = client.get("/api/mistakes/weak-points").json()
    assert weak["success"] is True
    # A topic tag plus a legacy SM-2 self-rating is not confirmed attempt evidence.
    assert weak["data"] == []
