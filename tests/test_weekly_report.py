from datetime import datetime
from types import SimpleNamespace


def test_weekly_report_reads_current_date_fields(monkeypatch):
    import backend.api.reports as reports

    now = datetime.now().isoformat()
    mistake = SimpleNamespace(
        created_at=now,
        review_history=[{"date": now}],
        tags=[],
        linked_concepts=[],
    )
    exercise = SimpleNamespace(
        created_at=now,
        practice_history=[{"date": now}],
    )
    monkeypatch.setattr(
        reports,
        "get_mistake_book",
        lambda *_args, **_kwargs: SimpleNamespace(list_all=lambda **_kwargs: [mistake]),
    )
    monkeypatch.setattr(
        reports,
        "get_exercise_bank",
        lambda *_args, **_kwargs: SimpleNamespace(list_all=lambda **_kwargs: [exercise]),
    )
    monkeypatch.setattr(reports, "_conversation_stats", lambda *_args: ([], 0))
    monkeypatch.setattr(reports, "_concept_stats", lambda *_args: {"exposure_count": 0, "top_concepts": []})

    result = reports.weekly_report(book_name="demo", days=7)

    assert result["data"]["summary"]["reviewed_mistakes"] == 1
    assert result["data"]["summary"]["practiced_exercises"] == 1
