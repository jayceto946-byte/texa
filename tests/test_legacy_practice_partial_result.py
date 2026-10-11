import pytest
from fastapi.testclient import TestClient

from backend.api import exercises
from backend.main import app
from memory.exercise_bank import ExerciseBank, ExerciseRecord
from memory.mistake_book import MistakeBook


def _setup(monkeypatch, tmp_path):
    bank = ExerciseBank(tmp_path / "exercises.db")
    exercise_id = bank.add(ExerciseRecord(
        question_text="求导 x²",
        answer="2x",
        subject="数学",
    ))
    mistake_book = MistakeBook(tmp_path / "mistakes.db")
    monkeypatch.setattr(exercises, "_bank", lambda book_name="default": bank)
    monkeypatch.setattr(exercises, "get_mistake_book", lambda book_name="default", data_dir="": mistake_book)
    monkeypatch.setattr(exercises, "_log_learning_event", lambda *args, **kwargs: None)
    return bank, exercise_id, mistake_book, TestClient(app)


def _practice(client, exercise_id, **overrides):
    payload = {"id": exercise_id, "user_answer": "x", "quality": 1, "add_to_mistake": True}
    payload.update(overrides)
    return client.post("/api/exercises/practice", json=payload)


def _practice_count(bank, exercise_id):
    return bank.get(exercise_id).practice_count


def test_healthy_linked_practice_keeps_existing_success_shape(monkeypatch, tmp_path):
    bank, exercise_id, mistake_book, client = _setup(monkeypatch, tmp_path)

    response = _practice(client, exercise_id)

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "练习结果已记录"
    assert payload["data"]["practice_count"] == 1
    assert payload["mistake_id"]
    assert "completion_status" not in payload
    assert "warning" not in payload
    assert _practice_count(bank, exercise_id) == 1
    assert mistake_book.get(payload["mistake_id"]).user_answer == "x"


def test_primary_practice_failure_propagates_without_optional_linkage(monkeypatch, tmp_path):
    bank, exercise_id, _, client = _setup(monkeypatch, tmp_path)

    def fail_primary(*args, **kwargs):
        raise RuntimeError("primary practice failed")

    monkeypatch.setattr(bank, "record_practice", fail_primary)
    with pytest.raises(RuntimeError, match="primary practice failed"):
        _practice(client, exercise_id)

    assert _practice_count(bank, exercise_id) == 0


def test_optional_linkage_failure_before_write_returns_partial_success(monkeypatch, tmp_path):
    bank, exercise_id, _, client = _setup(monkeypatch, tmp_path)

    def fail_before_write(*args, **kwargs):
        raise RuntimeError("sensitive secondary error")

    monkeypatch.setattr(exercises, "get_mistake_book", fail_before_write)
    response = _practice(client, exercise_id)

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["practice_count"] == 1
    assert payload["completion_status"] == "partial"
    assert payload["practice_saved"] is True
    assert payload["linkage_status"] == "unconfirmed"
    assert "不要重复提交整次练习" in payload["warning"]
    assert "sensitive secondary error" not in response.text
    assert _practice_count(bank, exercise_id) == 1


def test_optional_failure_after_linkage_commit_reports_unconfirmed_without_rollback(monkeypatch, tmp_path):
    bank, exercise_id, mistake_book, client = _setup(monkeypatch, tmp_path)

    def fail_after_linkage_commit(event_type, **kwargs):
        if event_type == "exercise_to_mistake":
            raise RuntimeError("sensitive post-commit error")

    monkeypatch.setattr(exercises, "_log_learning_event", fail_after_linkage_commit)
    response = _practice(client, exercise_id)

    assert response.status_code == 200
    payload = response.json()
    assert payload["completion_status"] == "partial"
    assert payload["practice_saved"] is True
    assert payload["linkage_status"] == "unconfirmed"
    assert "不要重复提交整次练习" in payload["warning"]
    assert "sensitive post-commit error" not in response.text
    assert _practice_count(bank, exercise_id) == 1
    assert payload["mistake_id"]
    assert mistake_book.get(payload["mistake_id"]) is not None
    with mistake_book.store._connect() as conn:
        source = conn.execute(
            "SELECT mistake_id FROM mistake_sources WHERE source_key=?",
            (f"exercise:default:{exercise_id}",),
        ).fetchone()
        attempts = conn.execute(
            "SELECT COUNT(*) FROM mistake_attempts WHERE mistake_id=?",
            (payload["mistake_id"],),
        ).fetchone()[0]
    assert source == (payload["mistake_id"],)
    assert attempts == 1

