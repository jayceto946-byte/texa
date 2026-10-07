import pytest

from backend.services.pending_actions import PendingActionStore
from memory.exercise_bank import ExerciseRecord, PracticeSession, get_exercise_bank
from memory.learning_events import get_learning_event_store
from memory.mistake_book import MistakeRecord, get_mistake_book


def test_update_receipt_revision_and_changed_arguments(tmp_path):
    bank = get_mistake_book("math", str(tmp_path))
    rid = bank.add(MistakeRecord(question_text="原题"))
    first = bank.update_once(rid, operation_id="op", expected_revision=1, changes={"notes": "已核对"})
    assert first["revision"] == 2
    assert bank.update_once(rid, operation_id="op", expected_revision=1, changes={"notes": "已核对"}) == first
    with pytest.raises(ValueError, match="arguments changed"):
        bank.update_once(rid, operation_id="op", expected_revision=1, changes={"notes": "篡改"})
    with pytest.raises(ValueError, match="revision changed"):
        bank.update_once(rid, operation_id="op2", expected_revision=1, changes={"notes": "过期"})
    current = bank.get(rid)
    current.notes = "手工更新"
    bank.update(current)
    assert bank.get(rid).revision == 3
    assert bank.get(rid).question_text == "原题"


def test_practice_core_commit_then_learning_projection_crash_reconciles(tmp_path, monkeypatch):
    bank = get_exercise_bank("math", str(tmp_path))
    rid = bank.add(ExerciseRecord(question_text="1+1?", subject="数学"))
    bank.create_practice_session_once(PracticeSession(id="session", exercise_ids=[rid]))
    pending = PendingActionStore(tmp_path)
    action = pending.create({"type": "record_practice_result", "payload": {
        "book_name": "math", "session_id": "session", "exercise_id": rid,
        "user_answer": "2", "quality": 4, "note": ""}}, context={"book_name": "math"})
    import backend.services.pending_actions as module
    reconcile = module._reconcile_domain_projection
    monkeypatch.setattr(module, "_reconcile_domain_projection", lambda *args: (_ for _ in ()).throw(OSError("projection crash")))
    with pytest.raises(OSError):
        pending.confirm(action["action_id"])
    assert bank.get(rid).practice_count == 1
    monkeypatch.setattr(module, "_reconcile_domain_projection", reconcile)
    assert pending.confirm(action["action_id"])["status"] == "confirmed"
    pending.confirm(action["action_id"])
    assert bank.get(rid).practice_count == 1
    assert len(get_learning_event_store(tmp_path).list_recent(book_name="math", limit=10)) == 1
    altered = pending.create({"type": "record_practice_result", "payload": {
        **action["payload"], "user_answer": "3"}}, context={"book_name": "math"})
    with pytest.raises(ValueError, match="arguments differ"):
        pending.confirm(altered["action_id"])
