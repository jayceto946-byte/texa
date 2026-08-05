from graph.generator import grounded_failure_message, has_textbook_evidence
from graph.retrieval_node import _assess_evidence_support, _extract_query_focus


def _item(*, text: str, title: str = "", coverage: float = 0.7, sources=None, direct=False):
    return {
        "text": text,
        "section_title": title,
        "query_coverage": coverage,
        "fusion_sources": sources or ["dense", "bm25"],
        "is_direct_hit": direct,
    }


def test_query_focus_separates_topic_from_requested_fact():
    topics, focus = _extract_query_focus(
        "教材有没有讲电容式传感器的全球市场规模？",
        ["电容式传感器"],
    )
    assert topics == ["电容式传感器"]
    assert focus == ["全球市场规模"]


def test_support_gate_rejects_topic_only_market_evidence():
    result = _assess_evidence_support(
        "教材有没有讲电容式传感器的全球市场规模？",
        [_item(text="电容式传感器结构简单，温度稳定性较好。", coverage=0.36)],
        matched_concepts=["电容式传感器"],
    )
    assert result["status"] == "insufficient"
    assert result["reason"] == "topic_matched_but_question_focus_missing"


def test_support_gate_accepts_focus_in_section_title():
    result = _assess_evidence_support(
        "电容式传感器有哪些优点？",
        [_item(title="电容式传感器的优点", text="结构简单，动态响应时间短。")],
        matched_concepts=["电容式传感器"],
    )
    assert result["status"] == "supported"
    assert result["matched_focus_terms"] == ["优点"]


def test_support_gate_marks_incomplete_multi_focus_as_partial():
    result = _assess_evidence_support(
        "比较电容式传感器的优点以及市场规模",
        [_item(title="电容式传感器的优点", text="结构简单。")],
        matched_concepts=["电容式传感器"],
    )
    assert result["status"] == "partial"


def test_generator_rejects_insufficient_support_even_with_candidates():
    state = {
        "use_textbook_context": True,
        "evidence_gate_applied": True,
        "evidence_items": [_item(text="topic-only")],
        "evidence_support": {
            "status": "insufficient",
            "reason": "topic_matched_but_question_focus_missing",
        },
    }
    assert has_textbook_evidence(state) is False
    assert "只检索到与问题主题相关" in grounded_failure_message(state)


def test_fusion_keeps_complete_lexical_text_for_duplicate_chunk_id():
    from graph.retrieval_node import _merge_and_rerank

    dense = {
        "chunk_id": "same", "text": "灵敏度高", "section_title": "主要特点",
        "chapter": "chapter", "source": "dense", "retrieval_rank": 1,
        "book_name": "selected", "is_selected_book": True,
    }
    lexical = {
        **dense, "text": "灵敏度高、热惯性小、互换性较差", "source": "bm25",
    }
    _, items = _merge_and_rerank(
        [], [dense, lexical], include_metadata=True,
        query="热敏电阻的主要特点有哪些？", intent="factual_recall",
    )
    assert items[0]["text"] == lexical["text"]
    assert items[0]["fusion_sources"] == ["dense", "bm25"]


def test_factual_enumeration_preserves_selected_book_bm25_order():
    from graph.retrieval_node import _merge_and_rerank

    core = {
        "chunk_id": "core", "text": "电容式传感器有哪些优点", "section_title": "概述",
        "chapter": "core", "source": "dense", "retrieval_rank": 1,
        "book_name": "core", "book_role": "core", "is_selected_book": False,
        "is_direct_hit": True,
    }
    selected = {
        "chunk_id": "selected", "text": "温度稳定性好", "section_title": "1. 温度稳定性好",
        "chapter": "selected", "source": "bm25", "retrieval_rank": 10,
        "book_name": "selected", "book_role": "reference", "is_selected_book": True,
    }
    _, items = _merge_and_rerank(
        [], [core, selected], include_metadata=True,
        query="电容式传感器有哪些优点？", intent="factual_recall",
    )
    assert items[0]["chunk_id"] == "selected"