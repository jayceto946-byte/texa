from evaluation.rag_eval import aggregate, score_case
from graph.generator import grounded_failure_message
from graph.intent_classifier import classify_intent_local
from graph.retrieval_node import (
    _list_group_neighbors,
    _merge_and_rerank,
    _select_enumeration_anchor,
    _teaching_unit_neighbors,
)
from ingestion.chapter_splitter import ChapterSplitter
from ingestion.lexical_index import expand_neighbors_rows, search_rows


def test_factual_recall_intent_for_reason_question():
    result = classify_intent_local("\u7535\u5bb9\u5f0f\u4f20\u611f\u5668\u662f\u5426\u9002\u5408\u52a8\u6001\u6d4b\u91cf\uff1f\u4e3a\u4ec0\u4e48\uff1f")
    assert result["intent"] == "factual_recall"


def test_structure_aware_chunks_keep_context_and_neighbors():
    splitter = ChapterSplitter(chunk_size=80, chunk_overlap=10)
    rows = splitter.split_chapter(
        "chapter 4",
        "## 4.3 capacitor\n\n### dynamic response\nsmall force, low mass, low dielectric loss.",
        book_name="sensors",
    )
    assert rows
    assert rows[0]["section_path"][0] == "chapter 4"
    assert "sensors" in rows[0]["retrieval_text"]
    if len(rows) > 1:
        assert rows[0]["next_chunk_id"] == rows[1]["chunk_id"]


def test_structure_aware_chunks_keep_equations_atomic_and_structured():
    splitter = ChapterSplitter(chunk_size=80, chunk_overlap=10)
    formula = "$$\\sigma = \\sqrt{\\frac{1}{n-1}\\sum v_i^2}$$"
    rows = splitter.split_chapter(
        "第二章", f"## 标准差\n\n公式如下。\n\n{formula}\n\n适用于等精度测量。", book_name="误差理论",
    )
    formula_rows = [row for row in rows if row["equations"]]
    assert len(formula_rows) == 1
    assert formula in formula_rows[0]["content"]
    assert formula_rows[0]["block_type"] == "formula"


def test_structure_aware_chunks_drop_leading_toc_block():
    splitter = ChapterSplitter(chunk_size=200, chunk_overlap=10)
    toc = "\n".join(f"第{i}节……{i}" for i in range(1, 7))
    rows = splitter.split_chapter("第一章", f"{toc}\n\n## 正文\n\n有效正文。", book_name="教材")
    assert rows
    assert all("第1节……1" not in row["content"] for row in rows)


def test_rrf_fusion_promotes_chunk_found_by_dense_and_bm25():
    common = {
        "chapter": "c", "chunk_id": "gold", "text": "capacitor dynamic response low mass",
        "source": "vector", "retrieval_rank": 4, "role": "property",
    }
    lexical = dict(common, source="bm25", retrieval_rank=1)
    distractor = {
        "chapter": "c", "chunk_id": "distractor", "text": "general sensor introduction",
        "source": "vector", "retrieval_rank": 1, "role": "definition",
    }
    _, debug = _merge_and_rerank(
        [], [common, lexical, distractor], query="capacitor dynamic response",
        intent="factual_recall", include_metadata=True,
    )
    assert debug[0]["chunk_id"] == "gold"
    assert set(debug[0]["fusion_sources"]) == {"dense", "bm25"}


def test_bm25_heading_match_is_applied_before_top_k():
    rows = [
        {
            "chunk_id": "generic", "chapter": "第一章", "section_title": "第一章",
            "retrieval_text": "精度包括测量过程的很多方面，以下介绍其他内容", "content": "泛化内容",
        },
        {
            "chunk_id": "exact", "chapter": "第一章", "section_title": "精度可分为",
            "retrieval_text": "准确度、精密度、精确度", "content": "准确度、精密度、精确度",
        },
    ]
    result = search_rows(rows, "精度包括哪些方面？", k=1)
    assert result[0]["chunk_id"] == "exact"
    assert result[0]["title_match_quality"] > 0


def test_bm25_complete_enumeration_survives_generic_section_intro():
    rows = [
        {"chunk_id": "intro", "section_title": "系统误差的发现", "content": "下面介绍发现系统误差的几种方法。"},
        {
            "chunk_id": "list", "section_title": "小结",
            "content": "上面介绍七种方法，包括实验对比法、观察法、校核法和比较法；第二类包括秩和检验法和t检验法。",
        },
    ]
    result = search_rows(rows, "发现系统误差的七种方法有哪些？", k=1)
    assert result[0]["chunk_id"] == "list"
    assert result[0]["enumeration_match_quality"] == 1.0


def test_standard_deviation_method_group_outranks_unrelated_four_method_hit():
    rows = [
        {
            "chunk_id": "wrong", "chapter": "第二章", "section_title": "秩和检验法",
            "content": "系统误差包括前四种方法，其中一种是不同公式计算标准差比较法。",
        },
        {
            "chunk_id": "header", "chapter": "第二章", "section_title": "标准差的其他计算法",
            "content": "除了贝塞尔公式外，计算标准差还有别捷尔斯法、极差法及最大误差法等。",
        },
        {
            "chunk_id": "peters", "chapter": "第二章", "section_title": "1. 别捷尔斯法（Peters）",
            "block_type": "paragraph", "content": "别捷尔斯法可由残余误差绝对值之和计算标准差。",
        },
        {
            "chunk_id": "peters-formula", "chapter": "第二章", "section_title": "1. 别捷尔斯法（Peters）",
            "block_type": "formula", "content": "$$\\sigma=1.253A\\tag{2-26}$$",
        },
        {
            "chunk_id": "range", "chapter": "第二章", "section_title": "2. 极差法",
            "block_type": "paragraph", "content": "极差法用于迅速计算标准差。",
        },
        {
            "chunk_id": "range-formula", "chapter": "第二章", "section_title": "2. 极差法",
            "block_type": "formula", "content": "$$\\sigma=\\omega_n/d_n\\tag{2-30}$$",
        },
        {
            "chunk_id": "maximum", "chapter": "第二章", "section_title": "3. 最大误差法",
            "block_type": "paragraph", "content": "最大误差法使用最大残余误差。",
        },
        {
            "chunk_id": "maximum-formula", "chapter": "第二章", "section_title": "3. 最大误差法",
            "block_type": "formula", "content": "$$\\sigma=|v|_{max}/K_n\\tag{2-32}$$",
        },
    ]
    hits = search_rows(rows, "求标准差的四个方法是什么？", k=8)
    anchor = _select_enumeration_anchor(hits)
    assert anchor and anchor["chunk_id"] == "header"
    group = _list_group_neighbors(
        anchor, expand_neighbors_rows(rows, [anchor["chunk_id"]], window=8),
    )
    for item in hits + group:
        item.update({"is_selected_book": True, "is_primary_book": True})

    _, debug = _merge_and_rerank(
        [], hits + group, query="求标准差的四个方法是什么？", intent="factual_recall",
        max_chunks_per_chapter=12, max_total_chunks=8, include_metadata=True,
    )

    assert debug[0]["chunk_id"] == "header"
    assert {item["chunk_id"] for item in debug[:7]} >= {
        "peters-formula", "range-formula", "maximum-formula",
    }

    _, formula_debug = _merge_and_rerank(
        [], hits + group,
        query="标准差的四个方法分别有哪些具体公式？", intent="formula",
        max_chunks_per_chapter=12, max_total_chunks=8, include_metadata=True,
    )
    assert formula_debug[0]["chunk_id"] == "header"
    assert {item["chunk_id"] for item in formula_debug[:7]} >= {
        "peters-formula", "range-formula", "maximum-formula",
    }


def test_formula_rerank_preserves_formula_and_local_ir_neighbors():
    neighborhood = [
        {
            "chunk_id": f"formula-{index}",
            "chapter": "第二章",
            "text": f"公式证据 {index}",
            "source": "neighbor",
            "retrieval_rank": 20 + index,
            "role": "reference" if index != 2 else "formula",
            "is_primary_book": True,
            "formula_anchor_order": 1,
            "formula_neighbor_distance": abs(index - 2),
            "chunk_index": 100 + index,
            "section_title": "最大误差法",
        }
        for index in range(1, 4)
    ]
    dense = [
        {
            "chunk_id": f"dense-{index}",
            "chapter": "第二章",
            "text": "最大误差法 标准差 最大残余误差 " * 3,
            "source": "vector",
            "retrieval_rank": index,
            "role": "formula",
        }
        for index in range(1, 9)
    ]

    _, debug = _merge_and_rerank(
        [],
        dense + neighborhood,
        query="最大误差法怎样计算标准差？",
        intent="formula",
        max_chunks_per_chapter=12,
        max_total_chunks=3,
        include_metadata=True,
    )

    assert [item["chunk_id"] for item in debug] == ["formula-2", "formula-1", "formula-3"]
    assert all("最大误差法" in item["text"] for item in debug)


def test_relationship_teaching_unit_keeps_same_section_formula_sibling():
    anchors = [{
        "chunk_id": "explanation", "chapter": "第二章",
        "section_title": "单次测量的标准差", "chunk_index": 10,
        "block_type": "paragraph", "text": "标准差说明随机误差的分散程度。",
    }]
    expanded = [
        *anchors,
        {
            "chunk_id": "bridge", "chapter": "第二章",
            "section_title": "单次测量的标准差", "chunk_index": 11,
            "block_type": "paragraph", "text": "按下式计算：",
        },
        {
            "chunk_id": "formula", "chapter": "第二章",
            "section_title": "单次测量的标准差", "chunk_index": 12,
            "block_type": "formula", "text": "$$\\sigma=\\sqrt{\\sum_i\\delta_i^2/n}$$",
        },
        {
            "chunk_id": "wrong-formula", "chapter": "第二章",
            "section_title": "系统误差", "chunk_index": 9,
            "block_type": "formula", "text": "$$\\Delta=x-x_0$$",
        },
    ]

    selected = _teaching_unit_neighbors(anchors, expanded)

    assert [item["chunk_id"] for item in selected] == ["explanation", "formula"]
    assert selected[0]["is_teaching_anchor"] is True
    assert selected[1]["is_teaching_neighbor"] is True
    assert selected[1]["teaching_neighbor_distance"] == 2


def test_relationship_rerank_does_not_drop_structurally_linked_formula():
    prose = [
        {
            "chunk_id": f"prose-{index}", "chapter": "第二章",
            "section_title": "单次测量的标准差",
            "text": "标准差与随机误差之间的关系和分散程度。",
            "source": "bm25", "retrieval_rank": index,
            "is_selected_book": True, "is_primary_book": True,
        }
        for index in range(1, 7)
    ]
    formula = {
        "chunk_id": "formula", "chapter": "第二章",
        "section_title": "单次测量的标准差",
        "text": "$$\\sigma=\\sqrt{\\sum_i\\delta_i^2/n}$$",
        "source": "neighbor", "retrieval_rank": 20,
        "is_selected_book": True, "is_primary_book": True,
        "is_teaching_neighbor": True, "teaching_anchor_order": 1,
        "teaching_neighbor_distance": 2, "role": "formula",
    }

    _, debug = _merge_and_rerank(
        [], prose + [formula], query="标准差和随机误差之间的关系",
        intent="comparison", max_chunks_per_chapter=6, max_total_chunks=6,
        include_metadata=True,
    )

    assert "formula" in {item["chunk_id"] for item in debug}


def test_point_completeness_requires_all_parallel_points():
    case = {
        "id": "dynamic", "answerable": True,
        "required_points": ["small force", "low mass", "low loss"],
    }
    partial = score_case(case, [{"text": "low mass"}], k=5)
    complete = score_case(case, [{"text": "small force; low mass; low loss"}], k=5)
    assert partial["recall_at_k"] == 0
    assert partial["point_recall"] == 1 / 3
    assert complete["recall_at_k"] == 1
    assert complete["reciprocal_rank"] == 1


def test_retrieval_evaluation_scores_final_evidence_pack(monkeypatch):
    from evaluation import rag_eval

    def fake_retrieve(_state):
        return {
            "retrieval_debug_items": [{"chunk_id": "debug-only", "text": "目标答案"}],
            "evidence_items": [{"chunk_id": "packed", "text": "最终证据"}],
            "chapter_contents": {},
            "evidence_support": {"status": "supported"},
        }

    monkeypatch.setattr("graph.retrieval_node.retrieve_node", fake_retrieve)
    items = rag_eval.retrieve_case({
        "question": "问题", "book_name": "教材", "answerable": True,
    })
    assert [item["chunk_id"] for item in items] == ["final-evidence-pack"]
    assert "最终证据" in items[0]["text"]
    assert "目标答案" not in "\n".join(item["text"] for item in items)


def test_chapter_vector_failure_falls_back_to_filtered_book_aggregate():
    from langchain_core.documents import Document

    from graph.retrieval_node import _vector_retrieval
    from ingestion.vector_store import RetrievalOutcome

    calls = []

    class Store:
        def search_chapter(self, *_args, **_kwargs):
            return RetrievalOutcome(items=[])

        def search_all(self, query, **kwargs):
            calls.append((query, kwargs))
            return RetrievalOutcome(items={
                "第二章": [
                    Document(
                        page_content="最大误差法使用最大残余误差。",
                        metadata={
                            "chunk_id": "aggregate-hit",
                            "chapter": "第二章",
                            "role": "formula",
                        },
                    )
                ]
            })

    rows, failures, succeeded = _vector_retrieval(
        Store(),
        "最大误差法公式",
        intent="formula",
        book_name="误差理论",
        target_chapters=["第二章"],
        precise_chapters=[],
        k=3,
        top_n=2,
    )

    assert rows[0]["chunk_id"] == "aggregate-hit"
    assert rows[0]["source"] == "vector(aggregate_chapter_fallback)"
    assert failures == []
    assert succeeded is True
    assert calls[0][1]["filter"] == {"chapter": "第二章"}


def test_aggregate_metrics():
    report = aggregate([
        {"recall_at_k": 1.0, "reciprocal_rank": 1.0, "point_recall": 1.0},
        {"recall_at_k": 0.0, "reciprocal_rank": 0.0, "point_recall": 0.5},
    ])
    assert report == {"cases": 2, "recall_at_k": 0.5, "mrr": 0.5, "point_recall": 0.75}


def test_empty_book_index_message_disallows_model_fallback():
    message = grounded_failure_message({"retrieval_error": "book_index_empty"})
    assert "\u6a21\u578b\u81ea\u8eab\u77e5\u8bc6" in message
    assert "\u91cd\u5efa" in message
