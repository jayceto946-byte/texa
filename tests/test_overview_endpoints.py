from fastapi.testclient import TestClient

from backend.api import exercises, mistakes
from backend.main import app
from memory.exercise_bank import ExerciseBank, ExerciseRecord
from memory.mistake_book import MistakeBook, MistakeRecord


def test_exercise_overview_combines_records_stats_and_active_session(tmp_path, monkeypatch):
    bank = ExerciseBank(tmp_path / "exercises.db")
    record = ExerciseRecord(question_text="聚合接口习题", subject="数学")
    bank.add(record)
    session = bank.create_practice_session(subject="数学", limit=1)
    monkeypatch.setattr(exercises, "_bank", lambda book_name="default": bank)

    response = TestClient(app).post(
        "/api/exercises/overview",
        json={"subject": "数学", "limit": 100},
    ).json()

    assert response["success"] is True
    assert response["data"]["records"][0]["id"] == record.id
    assert response["data"]["stats"]["total"] == 1
    assert response["data"]["practice_session"]["id"] == session.id


def test_mistake_overview_combines_records_and_due_queue(tmp_path, monkeypatch):
    book = MistakeBook(tmp_path / "mistakes.db")
    record = MistakeRecord(question_text="聚合接口错题", subject="数学")
    book.add(record)
    monkeypatch.setattr(mistakes, "_mb", lambda book_name="default": book)

    response = TestClient(app).post(
        "/api/mistakes/overview",
        json={"subject": "数学", "limit": 50},
    ).json()

    assert response["success"] is True
    assert response["data"]["records"][0]["id"] == record.id
    assert isinstance(response["data"]["due_records"], list)


def test_exercise_overview_keeps_records_when_optional_sections_fail(tmp_path, monkeypatch):
    bank = ExerciseBank(tmp_path / "degraded_exercises.db")
    record = ExerciseRecord(question_text="降级后仍展示习题", subject="数学")
    bank.add(record)
    monkeypatch.setattr(exercises, "_bank", lambda book_name="default": bank)
    monkeypatch.setattr(bank, "stats", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("stats broken")))
    monkeypatch.setattr(bank, "get_active_practice_session", lambda: (_ for _ in ()).throw(RuntimeError("session broken")))

    response = TestClient(app).post(
        "/api/exercises/overview",
        json={"subject": "数学", "limit": 100},
    ).json()

    assert response["success"] is True
    assert response["data"]["records"][0]["id"] == record.id
    assert response["data"]["stats"] is None
    assert response["data"]["practice_session"] is None
    assert set(response["data"]["errors"]) == {"stats", "practice_session"}


def test_mistake_overview_keeps_records_when_due_queue_fails(tmp_path, monkeypatch):
    book = MistakeBook(tmp_path / "degraded_mistakes.db")
    record = MistakeRecord(question_text="降级后仍展示错题", subject="数学")
    book.add(record)
    monkeypatch.setattr(mistakes, "_mb", lambda book_name="default": book)
    monkeypatch.setattr(book, "get_due", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("due broken")))

    response = TestClient(app).post(
        "/api/mistakes/overview",
        json={"subject": "数学", "limit": 50},
    ).json()

    assert response["success"] is True
    assert response["data"]["records"][0]["id"] == record.id
    assert response["data"]["due_records"] == []
    assert set(response["data"]["errors"]) == {"due_records"}
