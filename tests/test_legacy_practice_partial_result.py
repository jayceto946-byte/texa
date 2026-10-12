"""A4 real SQLite failure/replay checks; all writes use tmp_path."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from backend.api import exercises
from backend.main import app
from memory.exercise_bank import ExerciseBank, ExerciseRecord
from memory.mistake_book import MistakeBook
from memory.mistake_lifecycle import MistakeLifecycleStore
from memory.learning_events import LearningEvent, LearningEventStore


def _setup(monkeypatch, tmp_path):
    bank = ExerciseBank(tmp_path / 'exercises.db')
    rid = bank.add(ExerciseRecord(question_text='求导 x²', answer='2x', subject='数学'))
    mb = MistakeBook(tmp_path / 'mistakes.db')
    events = LearningEventStore(tmp_path / 'events.db')
    monkeypatch.setattr(exercises, '_bank', lambda book_name='default': bank)
    monkeypatch.setattr(exercises, 'get_mistake_book', lambda *args: mb)
    def log(event_type, **kwargs):
        payload = kwargs['payload']
        events.append(LearningEvent(id=payload['event_id'], event_type=event_type, payload=payload))
    monkeypatch.setattr(exercises, '_log_learning_event', log)
    return bank, rid, mb, events, TestClient(app)


def _practice(client, rid, **overrides):
    payload = dict(id=rid, operation_id='attempt-1', user_answer='x', quality=1, add_to_mistake=True)
    payload.update(overrides)
    return client.post('/api/exercises/practice', json=payload)


def _counts(bank, rid, mb, events):
    with mb.store._connect() as conn:
        occurrences = conn.execute('SELECT COUNT(*) FROM mistake_attempts').fetchone()[0]
        candidates = conn.execute('SELECT COUNT(*) FROM mistake_candidates').fetchone()[0]
    return bank.get(rid).practice_count, occurrences, candidates, len(events.list_recent())


def test_missing_identity_does_not_write(monkeypatch, tmp_path):
    bank, rid, mb, events, client = _setup(monkeypatch, tmp_path)
    assert not _practice(client, rid, operation_id='').json()['success']
    assert _counts(bank, rid, mb, events) == (0, 0, 0, 0)


def test_lost_response_replay_and_readonly_status(monkeypatch, tmp_path):
    bank, rid, mb, events, client = _setup(monkeypatch, tmp_path)
    _practice(client, rid)  # Ignore a committed success, like a lost response.
    result = _practice(client, rid).json()
    assert result['completion_status'] == 'complete'
    assert result['mistake_id'] and mb.get(result['mistake_id']).user_answer == 'x'
    assert _counts(bank, rid, mb, events) == (1, 1, 0, 2)
    status = client.get(f'/api/exercises/practice/{rid}/operations/attempt-1').json()
    assert status['completion_status'] == 'complete'
    assert _counts(bank, rid, mb, events) == (1, 1, 0, 2)


def test_conflicting_payload_does_not_overwrite_attempt(monkeypatch, tmp_path):
    bank, rid, mb, events, client = _setup(monkeypatch, tmp_path)
    _practice(client, rid)
    assert not _practice(client, rid, user_answer='2x', quality=5).json()['success']
    assert bank.get(rid).practice_history[0]['user_answer'] == 'x'
    assert _counts(bank, rid, mb, events) == (1, 1, 0, 2)


def test_distinct_identity_is_a_genuine_second_attempt(monkeypatch, tmp_path):
    bank, rid, mb, events, client = _setup(monkeypatch, tmp_path)
    _practice(client, rid)
    _practice(client, rid, operation_id='attempt-2')
    assert _counts(bank, rid, mb, events) == (2, 2, 0, 4)


def test_concurrent_retries_do_not_duplicate(monkeypatch, tmp_path):
    bank, rid, mb, events, client = _setup(monkeypatch, tmp_path)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: _practice(client, rid).json(), range(12)))
    assert all(r['completion_status'] == 'complete' for r in results)
    assert _counts(bank, rid, mb, events) == (1, 1, 0, 2)


@pytest.mark.parametrize('after_write', [False, True])
def test_secondary_failure_reconciles_after_restart(monkeypatch, tmp_path, after_write):
    bank, rid, mb, events, client = _setup(monkeypatch, tmp_path)
    original = MistakeLifecycleStore.append_occurrence_once
    def fail(self, *args, **kwargs):
        if after_write:
            original(self, *args, **kwargs)
        raise RuntimeError('synthetic-sensitive-secondary-error')
    monkeypatch.setattr(MistakeLifecycleStore, 'append_occurrence_once', fail)
    result = _practice(client, rid).json()
    assert result['completion_status'] == 'partial' and result['retryable']
    assert 'synthetic-sensitive' not in str(result)
    assert bank.get(rid).practice_count == 1
    monkeypatch.setattr(MistakeLifecycleStore, 'append_occurrence_once', original)
    restarted = ExerciseBank(tmp_path / 'exercises.db')
    monkeypatch.setattr(exercises, '_bank', lambda book_name='default': restarted)
    result = _practice(client, rid).json()
    assert result['completion_status'] == 'complete'
    assert _counts(restarted, rid, mb, events) == (1, 1, 0, 2)


def test_candidate_write_then_error_reuses_candidate(monkeypatch, tmp_path):
    bank, rid, mb, events, client = _setup(monkeypatch, tmp_path)
    original = MistakeLifecycleStore.create_candidate
    def fail(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError('after candidate commit')
    monkeypatch.setattr(MistakeLifecycleStore, 'create_candidate', fail)
    assert _practice(client, rid, add_to_mistake=False).json()['completion_status'] == 'partial'
    monkeypatch.setattr(MistakeLifecycleStore, 'create_candidate', original)
    result = _practice(client, rid, add_to_mistake=False).json()
    assert result['candidate_id'] and result['completion_status'] == 'complete'
    assert _counts(bank, rid, mb, events) == (1, 0, 1, 1)


def test_event_commit_then_error_reconciles_once(monkeypatch, tmp_path):
    bank, rid, mb, events, client = _setup(monkeypatch, tmp_path)
    log = exercises._log_learning_event
    def fail(event_type, **kwargs):
        log(event_type, **kwargs)
        raise RuntimeError('after event commit')
    monkeypatch.setattr(exercises, '_log_learning_event', fail)
    assert _practice(client, rid).json()['completion_status'] == 'partial'
    monkeypatch.setattr(exercises, '_log_learning_event', log)
    assert _practice(client, rid).json()['completion_status'] == 'complete'
    assert _counts(bank, rid, mb, events) == (1, 1, 0, 2)


def test_primary_receipt_transaction_rolls_back(monkeypatch, tmp_path):
    bank, rid, mb, events, client = _setup(monkeypatch, tmp_path)
    with bank.store._connect() as conn:
        conn.execute("CREATE TRIGGER fail_primary BEFORE UPDATE ON exercises BEGIN SELECT RAISE(ABORT, 'primary failed'); END")
    with pytest.raises(Exception, match='primary failed'):
        _practice(client, rid)
    assert _counts(bank, rid, mb, events) == (0, 0, 0, 0)


def test_retry_keeps_original_source_when_exercise_edited(monkeypatch, tmp_path):
    bank, rid, mb, events, client = _setup(monkeypatch, tmp_path)
    provider = exercises.get_mistake_book
    monkeypatch.setattr(exercises, 'get_mistake_book', lambda *args: (_ for _ in ()).throw(RuntimeError('offline')))
    assert _practice(client, rid).json()['completion_status'] == 'partial'
    record = bank.get(rid); record.question_text = 'changed question'; bank.update(record)
    monkeypatch.setattr(exercises, 'get_mistake_book', provider)
    result = _practice(client, rid).json()
    assert mb.get(result['mistake_id']).question_text == '求导 x²'
    assert bank.get(rid).question_text == 'changed question'


def test_stale_content_edit_cannot_erase_receipt(monkeypatch, tmp_path):
    bank, rid, mb, events, client = _setup(monkeypatch, tmp_path)
    stale = bank.get(rid)
    _practice(client, rid)
    stale.explanation = 'edited independently'
    bank.update(stale)
    assert _practice(client, rid).json()['completion_status'] == 'complete'
    assert _counts(bank, rid, mb, events) == (1, 1, 0, 2)
    assert bank.get(rid).explanation == 'edited independently'
    assert bank.get(rid).status == 'needs_review'
