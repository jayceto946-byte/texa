from memory.mistake_book import MistakeBook, MistakeRecord


def test_mistake_record_persists_rich_fields(tmp_path):
    book = MistakeBook(tmp_path / "mistakes.db")
    record = MistakeRecord(
        question_text="corrected $x^2$",
        ocr_text="raw OCR x^2",
        user_answer="x",
        correct_answer="2x",
        source="2024 mock",
        subject="math",
        chapter="derivative",
        tags=["derivative", "calculus"],
        mistake_type=["calculation"],
        difficulty=5,
        image_path="image.jpg",
        explanation="Use $2x$.",
        linked_concepts=[{"name": "derivative", "concept_id": "c1", "confidence": 1.0}],
    )

    rid = book.add(record)
    loaded = book.get(rid)

    assert loaded is not None
    assert loaded.question_text == "corrected $x^2$"
    assert loaded.ocr_text == "raw OCR x^2"
    assert loaded.explanation == "Use $2x$."
    assert loaded.linked_concepts[0]["name"] == "derivative"
    assert loaded.chapter == "derivative"
    assert loaded.difficulty == 5
    assert loaded.tags == ["derivative", "calculus"]
    assert loaded.sm2["next_review"]


def test_review_history_is_persisted(tmp_path):
    book = MistakeBook(tmp_path / "mistakes.db")
    rid = book.add(MistakeRecord(question_text="q", subject="math"))

    updated = book.review(rid, 4)
    reloaded = book.get(rid)

    assert updated.review_history
    assert reloaded is not None
    assert len(reloaded.review_history) == 1
    assert reloaded.review_history[0]["quality"] == 4
    assert reloaded.sm2["repetitions"] == 1
    assert reloaded.sm2["next_review"] != updated.review_history[0]["date"]


def test_weak_points_label_tags_as_concepts(tmp_path):
    book = MistakeBook(tmp_path / "mistakes.db")
    book.add(MistakeRecord(question_text="q", subject="math", tags=["导数"], mistake_type=["计算错误"]))

    weak = book.get_weak_points()

    assert {"type": "知识点", "name": "导数", "count": 1} in weak


def test_explain_persists_explanation(tmp_path):
    book = MistakeBook(tmp_path / "mistakes.db")
    rid = book.add(MistakeRecord(question_text="q", subject="math"))

    explanation = book.explain(rid, lambda prompt: "stored explanation")
    reloaded = book.get(rid)

    assert explanation == "stored explanation"
    assert reloaded is not None
    assert reloaded.explanation == "stored explanation"

def test_subject_hierarchy_filters_parent_child_and_legacy_values(tmp_path):
    book = MistakeBook(tmp_path / "mistakes.db")
    high_math = MistakeRecord(question_text="q1", subject="\u6570\u5b66/\u9ad8\u6570")
    linear = MistakeRecord(question_text="q2", subject="\u6570\u5b66/\u7ebf\u4ee3")
    english = MistakeRecord(question_text="q3", subject="\u82f1\u8bed/\u9605\u8bfb")
    legacy_high_math = MistakeRecord(question_text="q4", subject="\u9ad8\u6570")
    for record in [high_math, linear, english, legacy_high_math]:
        book.add(record)

    assert {r.id for r in book.list_all(subject="\u6570\u5b66")} == {high_math.id, linear.id, legacy_high_math.id}
    assert {r.id for r in book.list_all(subject="\u6570\u5b66/\u9ad8\u6570")} == {high_math.id, legacy_high_math.id}
    assert {r.id for r in book.get_due(subject="\u9ad8\u6570")} == {high_math.id, legacy_high_math.id}
    assert book.get_stats(subject="\u6570\u5b66")["total"] == 3

def test_subject_parent_matches_custom_second_level_path(tmp_path):
    book = MistakeBook(tmp_path / "mistakes.db")
    sensor = MistakeRecord(question_text="q", subject="\u4e13\u4e1a\u8bfe/\u4f20\u611f\u5668")
    book.add(sensor)

    assert {r.id for r in book.list_all(subject="\u4e13\u4e1a\u8bfe")} == {sensor.id}
