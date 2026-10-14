"""Report scope/history regressions with isolated persisted study assets."""
import json
from datetime import datetime, timedelta

import pytest

from backend import conversation_memory as cm
from backend.api import reports
from memory.exercise_bank import ExerciseBank, ExerciseRecord
from memory.mistake_book import MistakeBook, MistakeRecord


@pytest.fixture
def assets(monkeypatch, tmp_path):
    bank = ExerciseBank(tmp_path / "exercises.db")
    mistakes = MistakeBook(tmp_path / "mistakes.db")
    monkeypatch.setattr(reports, "PROGRESS_PATH", tmp_path)
    monkeypatch.setattr(cm, "CONV_DIR", tmp_path / "conversations")
    monkeypatch.setattr(reports, "get_exercise_bank", lambda *_args: bank)
    monkeypatch.setattr(reports, "get_mistake_book", lambda *_args: mistakes)
    return bank, mistakes, tmp_path


def test_report_subject_filters_all_asset_cohorts(assets):
    bank, mistakes, root = assets
    for subject in ("数学/高数", "数学/线代", "高数", "英语/阅读"):
        eid = bank.add(ExerciseRecord(question_text=subject, subject=subject))
        bank.record_practice(eid, user_answer="answer", quality=4)
        mid = mistakes.add(MistakeRecord(question_text=subject, subject=subject, tags=[subject]))
        mistakes.review(mid, 4)
    directory = root / "default"
    directory.mkdir()
    (directory / "concept_memory.json").write_text(json.dumps({"exposures":[
        {"concept":subject or "unknown-scoped concept", "subject":subject, "timestamp":datetime.now().isoformat()}
        for subject in ("数学/高数", "数学/线代", "高数", "英语/阅读", "")
    ]}), encoding="utf-8")
    for query, expected in (("数学",3),("数学/高数",2),("英语",1),("专业课",0),("",4)):
        result = reports.weekly_report(subject=query)["data"]
        for key in ("new_exercises", "practiced_exercises", "new_mistakes", "reviewed_mistakes"):
            assert result["summary"][key] == expected, (query,key)
        assert result["summary"]["concept_exposures"] == (5 if not query else expected)
        assert len(result["weak_points"]) == expected


def test_report_reads_multiple_cursor_pages_and_sqlite_only_session(assets):
    _, _, root = assets
    for index in range(230):
        cm.append_message("long", "user", f"question{index}", "demo", "数学/高数", turn_id=f"turn{index}")
        cm.append_message("long", "assistant", "answer", "demo", "数学/高数", turn_id=f"turn{index}")
    # Removing the expendable recent projection must not erase report history.
    (root / "conversations" / "long.json").unlink()
    cm.append_message("other", "user", "English", "demo", "英语")
    cm.append_message("other-book", "user", "math other book", "other", "数学")
    cm.append_message("unscoped", "user", "unknown scope")
    result = reports.weekly_report(book_name="demo", subject="数学")["data"]
    assert result["summary"]["qa_count"] == 230
    assert len(result["recent_questions"]) == 10
    assert result["recent_questions"][-1]["question"] == "question229"
    assert reports.weekly_report(subject="专业课")["data"]["summary"]["qa_count"] == 0


def test_report_legacy_projection_import_and_date_cutoff(assets):
    _, _, root = assets
    directory = root / "conversations"
    directory.mkdir()
    (directory / "legacy.json").write_text(json.dumps({"messages":[
        {"role":"user", "content":"today", "book_name":"demo", "subject":"高数", "created_at":datetime.now().isoformat()},
        {"role":"user", "content":"old", "book_name":"demo", "subject":"高数", "created_at":(datetime.now()-timedelta(days=40)).isoformat()},
        {"role":"assistant", "content":"not a question", "created_at":datetime.now().isoformat()},
    ]}), encoding="utf-8")
    result = reports.weekly_report(book_name="demo", subject="数学")["data"]
    assert result["summary"]["qa_count"] == 1
    assert result["recent_questions"][0]["question"] == "today"


@pytest.mark.parametrize("requested,effective", [(-2,1),(0,1),(1,1),(7,7),(31,31),(100,31)])
def test_report_day_metadata_matches_cutoff(assets, requested, effective):
    result = reports.weekly_report(days=requested)["data"]
    assert result["range_days"] == effective
    assert result["start_date"] == (datetime.now()-timedelta(days=effective)).date().isoformat()
