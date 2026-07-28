from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.services.kg_learning_summary import (
    build_concept_review_plan,
    days_since,
    mistake_summary,
)


def _mistake(**updates):
    values = {
        "id": "m-1",
        "question_text": "请说明牛顿第二定律",
        "ocr_text": "",
        "explanation": "",
        "source": "manual",
        "subject": "物理",
        "chapter": "力学",
        "tags": ["动力学"],
        "mistake_type": "概念不清",
        "review_history": [],
        "linked_concepts": [{"name": "牛顿第二定律"}],
        "sm2": {"next_review": "2026-07-24", "interval": 2},
    }
    values.update(updates)
    return SimpleNamespace(**values)


def test_days_since_uses_supplied_reference_time():
    reference = datetime(2026, 7, 23, 12, 0, 0)
    assert days_since("2026-07-13T11:00:00", now=reference) == 10
    assert days_since("not-a-date", now=reference) is None


def test_review_plan_is_calculated_from_preloaded_records():
    reference = datetime(2026, 7, 23, 12, 0, 0)
    concepts = {
        "牛顿第二定律": {
            "weak_flag": True,
            "exposure_count": 3,
            "last_exposed_at": (reference - timedelta(days=10)).isoformat(),
            "source_chapters": ["第二章"],
        }
    }
    exposures = [{
        "concept": "牛顿第二定律",
        "question": "请说明牛顿第二定律",
        "source": "mistake",
        "timestamp": "2026-07-12T08:00:00",
        "weak": True,
    }]

    result = build_concept_review_plan(
        concepts,
        exposures,
        Counter({"牛顿第二定律": 3}),
        [],
        [_mistake()],
        now=reference,
    )

    assert len(result) == 1
    assert result[0]["name"] == "牛顿第二定律"
    assert result[0]["related_mistakes"][0]["id"] == "m-1"
    assert result[0]["recent_questions"][0]["mistake_id"] == "m-1"
    assert result[0]["textbook_snippets"][0]["chapter"] == "第二章"


def test_mistake_summary_keeps_existing_response_shape():
    summary = mistake_summary(_mistake())
    assert summary["next_review"] == "2026-07-24"
    assert summary["interval"] == 2
    assert summary["linked_concepts"] == [{"name": "牛顿第二定律"}]


def test_days_since_aligns_aware_and_naive_datetimes():
    reference = datetime(2026, 7, 23, 12, 0, 0)
    assert days_since("2026-07-13T11:00:00+08:00", now=reference) == 10


def test_review_plan_uses_name_as_stable_tie_breaker():
    reference = datetime(2026, 7, 23, 12, 0, 0)
    concepts = {
        "概念 B": {"weak_flag": True, "exposure_count": 1},
        "概念 A": {"weak_flag": True, "exposure_count": 1},
    }
    result = build_concept_review_plan(
        concepts,
        [],
        Counter({"概念 B": 1, "概念 A": 1}),
        [],
        [_mistake(linked_concepts=[])],
        now=reference,
    )
    assert [item["name"] for item in result] == ["概念 A", "概念 B"]


def test_review_plan_does_not_use_substring_matches_for_mistakes():
    result = build_concept_review_plan(
        {"力": {"weak_flag": True, "exposure_count": 1}},
        [{"concept": "力", "question": "请说明牛顿", "source": "mistake"}],
        Counter({"力": 1}),
        [],
        [_mistake(linked_concepts=[{"name": "动力学"}])],
        now=datetime(2026, 7, 23, 12, 0, 0),
    )
    assert result[0]["related_mistakes"] == []
    assert result[0]["recent_questions"][0]["mistake_id"] == ""


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("question_text", "请使用拉格朗日中值定理证明"),
        ("ocr_text", "拉格朗日中值定理的扫描题干"),
        ("explanation", "本题关键是拉格朗日中值定理"),
        ("tags", ["拉格朗日中值定理"]),
        ("linked_concepts", [{"name": "拉格朗日中值定理"}]),
    ],
)

def test_review_plan_matches_legacy_unstructured_fields(field, value):
    values = {
        "question_text": "其他题目",
        "ocr_text": "",
        "explanation": "",
        "tags": [],
        "linked_concepts": [],
    }
    values[field] = value
    record = _mistake(**values)
    result = build_concept_review_plan(
        {"拉格朗日中值定理": {"weak_flag": True, "exposure_count": 1}},
        [],
        Counter({"拉格朗日中值定理": 1}),
        [],
        [record],
        now=datetime(2026, 7, 23, 12, 0, 0),
    )
    assert [item["id"] for item in result[0]["related_mistakes"]] == ["m-1"]


def test_review_plan_prefers_explicit_links_before_legacy_text_fallback():
    explicit = _mistake(
        id="explicit",
        question_text="显式关联题",
        tags=["拉格朗日中值定理"],
        linked_concepts=[],
    )
    legacy = _mistake(
        id="legacy",
        question_text="请使用拉格朗日中值定理证明",
        tags=[],
        linked_concepts=[],
    )
    result = build_concept_review_plan(
        {"拉格朗日中值定理": {"weak_flag": True, "exposure_count": 1}},
        [],
        Counter({"拉格朗日中值定理": 1}),
        [],
        [explicit, legacy],
        now=datetime(2026, 7, 23, 12, 0, 0),
    )
    assert [item["id"] for item in result[0]["related_mistakes"]] == ["explicit"]


def test_recent_question_uses_guarded_legacy_contains_match():
    question = "求函数在区间上的拉格朗日中值定理应用"
    result = build_concept_review_plan(
        {"拉格朗日中值定理": {"weak_flag": True, "exposure_count": 1}},
        [{
            "concept": "拉格朗日中值定理",
            "question": f"{question}（复习）",
            "source": "mistake",
        }],
        Counter({"拉格朗日中值定理": 1}),
        [],
        [_mistake(question_text=question, tags=[], linked_concepts=[])],
        now=datetime(2026, 7, 23, 12, 0, 0),
    )
    assert result[0]["recent_questions"][0]["mistake_id"] == "m-1"
