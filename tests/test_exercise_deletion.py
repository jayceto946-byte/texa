"""Deletion manages the current bank and pending practice without erasing history."""
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import exercises
from memory.exercise_bank import ExerciseBank, ExerciseRecord, PracticeSession


def test_delete_api_preserves_history_and_other_banks_and_advances_practice(tmp_path, monkeypatch):
    bank = ExerciseBank(tmp_path / 'bank.db')
    other = ExerciseBank(tmp_path / 'other.db')
    records = [ExerciseRecord(question_text=f'题目{i}') for i in range(4)]
    for record in records:
        bank.add(record)
    other.add(ExerciseRecord(id=records[1].id, question_text='另一题库中的题目'))
    ids = [record.id for record in records]
    history = {ids[0]: dict(quality=4, user_answer='已保存的作答', mistake_id='existing-mistake')}
    session = bank.save_practice_session(PracticeSession(exercise_ids=ids, current_index=1, results=history))
    monkeypatch.setattr(exercises, '_bank', lambda book_name: other if book_name == 'other' else bank)
    app = FastAPI(); app.include_router(exercises.router, prefix='/api')
    client = TestClient(app)

    response = client.post('/api/exercises/delete?book_name=current', json=dict(exercise_ids=ids[:3] + [ids[1], 'already-gone']))
    assert response.status_code == 200 and response.json()['data']['deleted'] == 3
    assert other.get(ids[1]) is not None
    assert [record.id for record in bank.list_all()] == [ids[3]]
    saved = bank.get_practice_session(session.id)
    assert saved.exercise_ids == [ids[0], ids[3]] and saved.current_index == 1
    assert saved.results == history and saved.summary()['remaining'] == 1
    assert bank.current_session_record(saved).id == ids[3]

    bank.set_practice_session_status(session.id, 'paused')
    assert client.delete(f'/api/exercises/{ids[3]}?book_name=current').json()['success']
    saved = bank.get_practice_session(session.id)
    assert saved.status == 'completed' and saved.completed_at
    assert saved.results == history and saved.summary()['remaining'] == 0
    assert bank.get_active_practice_session() is None
    assert client.post('/api/exercises/delete', json=dict(exercise_ids=ids)).json()['data']['deleted'] == 0


def test_delete_and_pending_queue_update_commit_together(tmp_path):
    bank = ExerciseBank(tmp_path / 'bank.db')
    record = ExerciseRecord(question_text='事务失败时应保留的题目')
    bank.add(record)
    session = bank.save_practice_session(PracticeSession(exercise_ids=[record.id]))
    with sqlite3.connect(bank.store.db_path) as connection:
        connection.execute("CREATE TRIGGER fail_queue BEFORE UPDATE ON exercise_practice_sessions BEGIN SELECT RAISE(ABORT, 'queue-write-failed'); END")
    with pytest.raises(sqlite3.IntegrityError, match='queue-write-failed'):
        bank.delete_many([record.id])
    assert bank.get(record.id) is not None
    assert bank.get_practice_session(session.id).exercise_ids == [record.id]
