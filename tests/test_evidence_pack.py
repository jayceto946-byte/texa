import pytest

from graph.evidence_pack import build_evidence_pack
from graph.generator import _build_generate_prompt


def _item(chunk_id: str, chapter: str, text: str, *, book_name: str = "Sensor Textbook") -> dict:
    return {
        "chunk_id": chunk_id,
        "chapter": chapter,
        "section_title": chapter,
        "page_idx": 0,
        "text": text,
        "book_name": book_name,
        "book_role": "core",
    }


def test_evidence_pack_deduplicates_ids_and_content():
    evidence = [
        _item("a", "chapter-1", "definition text"),
        _item("a", "chapter-1", "definition text"),
        _item("b", "chapter-2", "definition   text"),
        _item("c", "chapter-2", "different text"),
    ]

    pack = build_evidence_pack(evidence, {})

    assert [item["chunk_id"] for item in pack["items"]] == ["a", "c"]
    assert pack["text"].count("definition text") == 1


def test_evidence_pack_limits_default_intent_to_two_items_per_chapter():
    evidence = [
        _item("a", "chapter-1", "first"),
        _item("b", "chapter-1", "second"),
        _item("c", "chapter-1", "third"),
        _item("d", "chapter-2", "fourth"),
    ]

    pack = build_evidence_pack(evidence, {})

    assert [item["chunk_id"] for item in pack["items"]] == ["a", "b", "d"]


def test_factual_recall_preserves_parallel_points_from_same_chapter():
    evidence = [
        _item("a", "chapter-1", "point one"),
        _item("b", "chapter-1", "point two"),
        _item("c", "chapter-1", "point three"),
        _item("d", "chapter-1", "point four"),
        _item("e", "chapter-1", "point five"),
        _item("f", "chapter-1", "point six"),
    ]

    pack = build_evidence_pack(evidence, {}, intent="factual_recall")

    assert [item["chunk_id"] for item in pack["items"]] == ["a", "b", "c", "d", "e", "f"]


def test_evidence_pack_uses_real_book_label_and_omits_unknown_page():
    item = _item("a", "chapter-1", "definition")
    item["page_idx"] = -1

    pack = build_evidence_pack([item], {})

    assert "[Sensor Textbook\u00b7chapter-1 / chapter-1]" in pack["text"]
    assert "p.?" not in pack["text"]


def test_generator_uses_selected_evidence_only_once():
    state = {
        "intent": "definition",
        "user_input": "what is it",
        "use_textbook_context": True,
        "chapter_contents": {"chapter-1": ["UNIQUE_EVIDENCE_TEXT"]},
        "evidence_items": [_item("a", "chapter-1", "UNIQUE_EVIDENCE_TEXT")],
        "concept_results": [{"chapter": "chapter-1", "content": "UNIQUE_EVIDENCE_TEXT"}],
        "history_results": [],
        "teaching_content": "",
    }

    prompt = _build_generate_prompt(state)

    assert prompt.count("UNIQUE_EVIDENCE_TEXT") == 1


def test_evidence_pack_falls_back_to_legacy_chapter_contents():
    chapter_contents = {
        "chapter-1": ["first legacy chunk", "second legacy chunk", "third legacy chunk"],
    }

    pack = build_evidence_pack([], chapter_contents)

    assert all(text in pack["text"] for text in (
        "first legacy chunk",
        "second legacy chunk",
        "third legacy chunk",
    ))


@pytest.mark.parametrize(
    ("intent", "expected_count"),
    [
        ("definition", 3),
        ("factual_recall", 6),
        ("comparison", 4),
        ("qa", 4),
        ("derivation", 4),
        ("application", 4),
    ],
)

def test_evidence_pack_quality_contract_by_question_type(intent, expected_count):
    evidence = [
        _item(f"chunk-{index}", "chapter-1", f"independent fact {index}")
        for index in range(1, 7)
    ]

    pack = build_evidence_pack(evidence, {}, intent=intent)

    assert len(pack["items"]) == expected_count
    assert all(
        f"independent fact {index}" in pack["text"]
        for index in range(1, expected_count + 1)
    )


def test_cross_chapter_questions_preserve_three_items_from_each_chapter():
    evidence = [
        _item(f"{chapter}-{index}", chapter, f"{chapter} fact {index}")
        for chapter in ("chapter-1", "chapter-2", "chapter-3")
        for index in range(1, 4)
    ]

    pack = build_evidence_pack(evidence, {}, intent="cross_chapter")

    assert len(pack["items"]) == 9
    assert {item["chapter"] for item in pack["items"]} == {
        "chapter-1",
        "chapter-2",
        "chapter-3",
    }
