import sqlite3

import pytest

from memory.mistake_book import MistakeBookStore
from memory.mistake_lifecycle import MistakeLifecycleStore


def test_candidate_acceptance_is_idempotent_and_unscheduled_until_confirmed(tmp_path):
    store = MistakeBookStore(tmp_path / "mistakes.db")
    lifecycle = MistakeLifecycleStore(store)
    candidate = lifecycle.create_candidate("exercise:book:attempt-1", {
        "question_text": "求极限", "user_answer": "0", "failure_confirmed": True,
        "content_complete": False,
    })
    assert store.list_all() == []
    assert store.get_due() == []
    with pytest.raises(ValueError, match="needs correction"):
        lifecycle.resolve_candidate(candidate["id"], accept=True, expected_revision=1, operation_id="incomplete")
    corrected = lifecycle.update_candidate(candidate["id"], expected_revision=1, changes={"question_text": "求极限（已校对）", "content_complete": True})
    assert corrected["revision"] == 2
    with pytest.raises(ValueError, match="revision changed"):
        lifecycle.update_candidate(candidate["id"], expected_revision=1, changes={"question_text": "迟到的校对"})
    candidate = lifecycle.create_candidate("exercise:book:attempt-2", {
        "question_text": "求极限", "user_answer": "0", "failure_confirmed": True,
        "content_complete": True,
    })
    receipt = lifecycle.resolve_candidate(candidate["id"], accept=True, expected_revision=1, operation_id="accept-1")
    assert lifecycle.resolve_candidate(candidate["id"], accept=True, expected_revision=1, operation_id="accept-1") == receipt
    record = store.get(receipt["mistake_id"])
    assert record and record.content_status == "ready"
    assert record.sm2
    assert len(lifecycle.list_attempts(record.id)) == 1
    with pytest.raises(ValueError, match="arguments changed"):
        lifecycle.resolve_candidate(candidate["id"], accept=False, expected_revision=1, operation_id="accept-1")
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4


def test_review_session_reveal_result_and_retry_preserve_one_attempt(tmp_path):
    store = MistakeBookStore(tmp_path / "mistakes.db")
    lifecycle = MistakeLifecycleStore(store)
    candidate = lifecycle.create_candidate("manual:one", {"question_text": "1+1", "correct_answer": "2", "content_complete": True})
    mistake_id = lifecycle.resolve_candidate(candidate["id"], accept=True, expected_revision=1, operation_id="accept")['mistake_id']
    session = lifecycle.create_review_session([mistake_id], scope="default")
    session = lifecycle.update_review_draft(session["id"], expected_revision=1, answer="2", revealed=False)
    with pytest.raises(ValueError, match="reveal feedback"):
        lifecycle.submit_review_result(session["id"], expected_revision=2, operation_id="result", result="independent_correct", hint_used=False, judgement_source="user_confirmed")
    session = lifecycle.update_review_draft(session["id"], expected_revision=2, answer="", revealed=True)
    with pytest.raises(ValueError, match="locked"):
        lifecycle.update_review_draft(session["id"], expected_revision=3, answer="3", revealed=False)
    receipt = lifecycle.submit_review_result(session["id"], expected_revision=3, operation_id="result", result="independent_correct", hint_used=False, judgement_source="user_confirmed")
    assert lifecycle.submit_review_result(session["id"], expected_revision=3, operation_id="result", result="independent_correct", hint_used=False, judgement_source="user_confirmed") == receipt
    attempts = lifecycle.list_attempts(mistake_id)
    assert len(attempts) == 1
    assert attempts[0]["answer"] == "2"
    assert attempts[0]["was_due"] is True
    assert lifecycle.get_review_session(session["id"])["index"] == 1


def test_legacy_record_survives_v2_to_v3_without_invented_attempts(tmp_path):
    path = tmp_path / "legacy.db"
    import json
    from memory.mistake_book import MistakeRecord
    record = MistakeRecord(question_text="旧错题", review_history=[{"date": "2024-01-01", "quality": 5}])
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE mistakes (id TEXT PRIMARY KEY,data TEXT NOT NULL,created_at TEXT NOT NULL,next_review TEXT,subject TEXT,chapter TEXT)")
        conn.execute("CREATE TABLE mistake_operations (operation_id TEXT PRIMARY KEY,args_hash TEXT NOT NULL,result_json TEXT NOT NULL)")
        conn.execute("INSERT INTO mistakes VALUES (?,?,?,?,?,?)", (record.id, json.dumps(record.to_dict(), ensure_ascii=False), record.created_at, None, record.subject, record.chapter))
        conn.execute("PRAGMA user_version=2")
    reopened = MistakeBookStore(path)
    assert reopened.get(record.id).review_history == record.review_history
    assert MistakeLifecycleStore(reopened).list_attempts(record.id) == []
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
        assert conn.execute("SELECT data FROM mistakes WHERE id=?", (record.id,)).fetchone()[0] == json.dumps(record.to_dict(), ensure_ascii=False)


def test_query_cursor_does_not_skip_extra_row(tmp_path, monkeypatch):
    from backend.api import mistake_lifecycle as api
    store = MistakeBookStore(tmp_path / "query.db")
    from memory.mistake_book import MistakeBook, MistakeRecord
    book = MistakeBook(tmp_path / "query.db")
    monkeypatch.setattr(api, "_mb", lambda _name: book)
    for index in range(3):
        store.add(MistakeRecord(id=f"q{index}", question_text=f"题目 {index}"))
    first = api.query_mistakes(api.MistakeQuery(limit=2))['data']
    second = api.query_mistakes(api.MistakeQuery(limit=2, cursor=first['next_cursor']))['data']
    assert len(first['items']) == 2
    assert len(second['items']) == 1
    assert {item['id'] for item in first['items'] + second['items']} == {'q0', 'q1', 'q2'}


def test_new_failure_clears_manual_mastery_and_is_idempotent(tmp_path):
    from backend.services.mistake_lifecycle import project_mistake
    store = MistakeBookStore(tmp_path / "mistakes.db")
    lifecycle = MistakeLifecycleStore(store)
    candidate = lifecycle.create_candidate("manual:mastered", {"question_text": "题目", "content_complete": True})
    mistake_id = lifecycle.resolve_candidate(candidate["id"], accept=True, expected_revision=1, operation_id="accept")['mistake_id']
    record = store.get(mistake_id)
    lifecycle.change_record(mistake_id, expected_revision=record.revision, operation_id="mastered", changes={"manual_mastered": True})
    assert project_mistake(store.get(mistake_id), [])["mastery_status"] == "mastered"
    first = lifecycle.append_occurrence_once(mistake_id, "exercise:attempt-1", answer="错解", source_ref={"type": "exercise"})
    assert lifecycle.append_occurrence_once(mistake_id, "exercise:attempt-1", answer="错解", source_ref={"type": "exercise"}) == first
    record = store.get(mistake_id)
    assert not record.manual_mastered
    assert project_mistake(record, lifecycle.list_attempts(mistake_id))["mastery_status"] == "unresolved"
    assert len(lifecycle.list_attempts(mistake_id)) == 1


def test_draft_list_recovers_open_work_and_hides_accepted_draft(tmp_path):
    store = MistakeBookStore(tmp_path / "mistakes.db")
    lifecycle = MistakeLifecycleStore(store)
    draft = lifecycle.create_draft({"question_text": "草稿题目", "content_complete": True})
    assert [item["id"] for item in lifecycle.list_drafts()] == [draft["id"]]
    candidate = lifecycle.create_candidate(f"manual:{draft['id']}", {"question_text": "草稿题目", "content_complete": True})
    lifecycle.resolve_candidate(candidate["id"], accept=True, expected_revision=1, operation_id="save-draft")
    assert lifecycle.list_drafts() == []


def test_diagnosis_uses_shared_cohort_and_excludes_legacy_quality(tmp_path, monkeypatch):
    import json
    from datetime import datetime, timedelta, timezone
    from backend.api import mistake_lifecycle as api
    from memory.mistake_book import MistakeBook, MistakeRecord
    book = MistakeBook(tmp_path / "diagnosis.db")
    monkeypatch.setattr(api, "_mb", lambda _name: book)
    record = MistakeRecord(id="d1", question_text="积分题", tags=["积分"], mistake_type=["换元错误"], diagnosis_status="confirmed", review_history=[{"quality": 5}])
    book.store.add(record)
    with book.store._connect() as conn:
        for days, result in [(40, "wrong"), (5, "independent_correct")]:
            created = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            conn.execute("INSERT INTO mistake_attempts VALUES (?,?,?,?,?,?)", (f"a{days}", record.id, f"test:{days}", "redo", json.dumps({"answer": "步骤", "result": result, "hint_used": False, "judgement_source": "user_confirmed"}), created))
    data = api.diagnose_mistakes()["data"]
    assert data["groups"][0]["recent_correct"] == 1
    assert data["comparison"]["prior_total"] == 1
    assert data["comparison"]["recent_total"] == 1
    assert data["comparison"]["comparable"] is False
    assert data["reasons"][0]["mistake_ids"] == ["d1"]


def test_mastery_requires_two_spaced_due_independent_redos_after_last_failure():
    from backend.services.mistake_lifecycle import project_mistake
    from memory.mistake_book import MistakeRecord
    record = MistakeRecord(question_text="题目")
    def redo(day, result="independent_correct", due=True):
        return {"kind": "redo", "created_at": f"2026-09-{day:02d}T12:00:00+08:00", "result": result,
                "answer": "过程", "hint_used": False, "judgement_source": "user_confirmed", "question_revision": 1, "was_due": due}
    assert project_mistake(record, [redo(1)])["mastery_status"] == "consolidating"
    assert project_mistake(record, [redo(1), redo(5)])["mastery_status"] == "consolidating"
    assert project_mistake(record, [redo(1), redo(5), redo(8)])["mastery_status"] == "mastered"
    assert project_mistake(record, [redo(1), redo(8, due=False)])["mastery_status"] == "consolidating"
    assert project_mistake(record, [redo(1), redo(8), redo(9, "wrong")])["mastery_status"] == "unresolved"
