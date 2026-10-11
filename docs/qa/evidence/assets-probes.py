"""Offline audit probes. Run with isolated config paths, never real data."""
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta

from backend.api import reports, exercises
from backend.schemas import ExercisePracticeRequest
from backend import conversation_memory as cm
from memory.exercise_bank import ExerciseBank, ExerciseRecord
from memory.mistake_book import MistakeBook, MistakeRecord

with tempfile.TemporaryDirectory(prefix="texa-assets-probes-") as directory:
    root = Path(directory)
    bank = ExerciseBank(root / "exercises.db")
    mistakes = MistakeBook(root / "mistakes.db")
    eid = bank.add(ExerciseRecord(question_text="English", subject="英语"))
    mistakes.add(MistakeRecord(question_text="English mistake", subject="英语"))
    with patch.object(reports, "get_exercise_bank", return_value=bank), patch.object(reports, "get_mistake_book", return_value=mistakes), patch.object(reports, "PROGRESS_PATH", root):
        report = reports.weekly_report(subject="数学", days=100)["data"]
        assert report["summary"]["new_exercises"] == 1
        assert report["summary"]["new_mistakes"] == 1
        assert report["range_days"] == 100
        print("REPRO REPORT_SCOPE: math report counts English exercise/mistake", report["summary"])
        print("REPRO REPORT_DAYS: range_days=100 but start limited to31", report["start_date"])
    with patch.object(cm, "CONV_DIR", root / "conversations"), patch.object(reports, "PROGRESS_PATH", root):
        for index in range(25):
            cm.append_message("audit", "user", f"question{index}", turn_id=f"turn{index}")
            cm.append_message("audit", "assistant", "answer", turn_id=f"turn{index}")
        questions, count = reports._conversation_stats(datetime.now()-timedelta(days=1), "default", "")
        assert count == 20, count
        print("REPRO REPORT_HISTORY: 25 authoritative questions, weekly count", count)
    with patch.object(exercises, "_bank", return_value=bank), patch.object(exercises, "_log_learning_event"), patch.object(exercises, "get_mistake_book", side_effect=OSError("injected mistake store failure")):
        request = ExercisePracticeRequest(id=eid, user_answer="wrong", quality=1, add_to_mistake=True)
        for index in range(2):
            try:
                exercises.practice_exercise(request)
            except OSError:
                pass
            else:
                raise AssertionError("expected failure")
        assert bank.get(eid).practice_count == 2
        print("REPRO LEGACY_PRACTICE_PARTIAL: two failed requests commit practice_count", bank.get(eid).practice_count)

checked = []
for path in Path("/private/tmp/texa-assets-pytest").rglob("*"):
    if path.is_file() and path.suffix in {".db", ".sqlite3"}:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            result = conn.execute("PRAGMA integrity_check").fetchall()
            foreign = conn.execute("PRAGMA foreign_key_check").fetchall()
            checked.append({"fixture":str(path), "integrity":result, "foreign_key_violations":foreign})
bad = [item for item in checked if item["integrity"] != [("ok",)] or item["foreign_key_violations"]]
print("FIXTURE_SQLITE_INTEGRITY", json.dumps({"checked":len(checked), "failures":bad}, ensure_ascii=False))
assert checked and not bad
