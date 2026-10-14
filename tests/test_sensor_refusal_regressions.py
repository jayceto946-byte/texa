"""Offline regressions for the diagnosed desktop sensor questions."""
import pytest

from graph import retrieval_node as retrieval
from graph.evidence_pack import build_evidence_pack
from graph.safe_retrieval import SafeKG
from ingestion.lexical_index import _enumeration_match_quality, expand_neighbors_rows, search_rows
from ingestion.vector_store import RetrievalOutcome


def row(key, index, title, text, parent="4.1 应变式电阻传感器", **extra):
    return {
        "chunk_id": key, "chunk_index": index, "section_chunk_index": 0,
        "book_name": "demo", "chapter": "第四章", "section_title": title,
        "section_path": ["第四章", parent, title], "content": text,
        "block_type": "paragraph", "role": "definition", **extra,
    }


@pytest.mark.parametrize("lead", ["根据", "按照", "关于", "针对", "对于"])
def test_discourse_prefix_does_not_pollute_sensor_topic(lead):
    topics, focus = retrieval._extract_query_focus(f"{lead}传感器的分类，举例说明物性型和结构型。", ["传感器"])
    assert topics == ["传感器"]
    assert focus == ["分类"]
    support = retrieval._assess_evidence_support(
        f"{lead}传感器的分类，举例说明物性型和结构型。",
        [{"section_title": "传感器的分类", "text": "分类包括物性型和结构型。", "is_direct_hit": True}],
        matched_concepts=["传感器"],
    )
    assert support["status"] == "supported"


def test_sensor_principle_variation_preserves_other_principle_boundary():
    assert retrieval._topic_term_matches("电阻式传感器", "应变式电阻传感器")
    assert not retrieval._topic_term_matches("电阻式传感器", "电容式传感器的分类")
    support = retrieval._assess_evidence_support(
        "电阻式传感器可以分成哪两种类型",
        [{"section_title": "电容式传感器的分类", "text": "可分为两种类型。", "is_direct_hit": True}],
    )
    assert support["status"] == "insufficient"


def test_two_types_count_equivalence_does_not_hide_wrong_counts():
    query = "电阻式传感器可以分成哪两种类型"
    assert retrieval._is_enumeration_query(query, "factual_recall")
    assert _enumeration_match_quality(query, "可分为金属应变片和半导体应变片两大类。") >= 0.55
    assert _enumeration_match_quality(query, "分为三个类型。") == 0


class EmptyVectors:
    def search_all(self, *_args, **_kwargs):
        return RetrievalOutcome(items={})

    def search_chapter(self, *_args, **_kwargs):
        return RetrievalOutcome(items=[])


@pytest.mark.parametrize("query", [
    "电阻式传感器可以分成哪两种类型",
    "电阻式传感器，它有两种材料，这两种材料构成的不同种类的传感器各有什么特点？适用于哪种场景",
])
def test_material_classification_reaches_final_pack_with_bounded_type_explanations(monkeypatch, query):
    rows = [
        row("application", 1, "4.1.5 电阻应变式传感器的应用", "电阻式传感器的类型很多，可以用于测量力和压力。"),
        row("types", 10, "4.1.1 电阻应变片的种类", "按敏感栅材料分类，可分为金属应变片和半导体应变片两大类。"),
        row("metal", 11, "4.1.2 金属电阻应变片", "金属应变片的特点是性能稳定，适用于静态测量。"),
        # This named type is beyond the normal adjacency window.
        row("semiconductor", 70, "4.1.3 半导体应变片", "半导体应变片的优点是灵敏度高，缺点是温度稳定性差。"),
    ]
    monkeypatch.setattr(retrieval, "get_safe_kg", lambda _book: (SafeKG(), ""))
    monkeypatch.setattr(retrieval, "_load_history", lambda *_args: [])
    result = retrieval.retrieve_node(
        {"user_input": query, "book_name": "demo", "intent": "factual_recall", "target_chapters": ["第四章"], "use_textbook_context": True},
        vector_store=EmptyVectors(),
        lexical_search=lambda _book, question, **kw: search_rows(rows, question, **kw),
        neighbor_expander=lambda _book, ids, **kw: expand_neighbors_rows(rows, ids, **kw),
        index_stats_override={"demo": {"healthy": True}},
        retrieval_resources_override=[{"book_name": "demo", "is_primary": True, "is_selected": True, "role": "core", "priority": 1}],
    )
    pack = build_evidence_pack(result["evidence_items"], intent="factual_recall")
    assert result["evidence_support"]["status"] in {"supported", "partial"}
    assert pack["items"][0]["chunk_id"] == "types"
    assert "金属应变片" in pack["text"] and "半导体应变片" in pack["text"]
    if "材料" in query:
        assert "性能稳定" in pack["text"] and "温度稳定性差" in pack["text"]


def test_named_type_neighbors_cannot_expand_book_chapter_or_ir_parent():
    anchor = row("types", 10, "种类", "分为金属应变片和半导体应变片两大类。")
    members = retrieval._classification_members(anchor["content"])
    good = row("good", 70, "半导体应变片", "温度稳定性差。", retrieval_rank=1)
    candidates = [
        good, dict(good),
        {**good, "chunk_id": "other-book", "book_name": "other"},
        {**good, "chunk_id": "other-chapter", "chapter": "第五章"},
        {**good, "chunk_id": "other-parent", "section_path": ["第四章", "其他父节点", "半导体应变片"]},
        {**good, "chunk_id": "excluded", "retrieval_excluded": True},
    ]
    result = retrieval._classification_member_neighbors(anchor, candidates, members)
    assert [item["chunk_id"] for item in result] == ["good"]


def test_definition_variants_and_literal_roles():
    for question in ("什么是电阻式传感器？", "电阻式传感器是什么？", "请解释电阻式传感器", "16.什么是电阻式传感器？"):
        assert retrieval._extract_query_focus(question) == (["电阻式传感器"], [])
    for number in (16, 17, 100):
        assert retrieval._supports_query_literals(f"{number}. 写出二阶系统动态响应，输入16V", "二阶系统动态响应方法")
    assert retrieval._supports_query_literals("已知k1=16、f0=100Hz，求动态响应", "动态响应计算方法")
    assert retrieval._assess_evidence_support("16. 已知k1=16、f0=100Hz，求二阶测量系统动态响应",
        [{"text": "二阶测量系统的动态响应方法", "is_direct_hit": True}])["status"] == "supported"
    assert retrieval._supports_query_literals("型号PT100", "型号PT100 的定义")
    assert not retrieval._supports_query_literals("型号PT100", "型号PT1000 的定义")
    _, focus = retrieval._extract_query_focus("写出二阶测量系统微分方程、灵敏度、固有频率、阻尼比和阶跃响应")
    assert set(focus) == {"微分方程", "灵敏度", "固有频率", "阻尼比", "阶跃响应"}


@pytest.mark.parametrize("intent", ["qa", "comparison", "factual_recall"])
def test_short_material_question_preserves_topic_and_all_deliverables(intent):
    query = "电阻式传感器两种材料各有什么特点，适用于什么场景？"
    topics, focus = retrieval._extract_query_focus(query)
    assert topics == ["电阻式传感器"]
    assert set(focus) == {"两种材料", "特点", "应用场景"}
    assert retrieval._is_enumeration_query(query, intent)
    wrong = [{"text": "电容式传感器的特点是适用于动态测量。", "is_direct_hit": True}]
    assert retrieval._assess_evidence_support(query, wrong)["status"] == "insufficient"


def test_final_material_coverage_requires_each_member_and_visible_body():
    from graph.generator import _prepare_evidence_pack
    query = "电阻式传感器两种材料各有什么特点，适用于什么场景？"
    items = [
        {**row("types", 1, "种类", "可分为金属应变片和半导体应变片两大类。"), "text": "可分为金属应变片和半导体应变片两大类。"},
        {**row("metal", 2, "金属电阻应变片", "金属电阻应变片性能稳定，适用于静态测量。"), "text": "金属电阻应变片性能稳定，适用于静态测量。"},
        {**row("semi", 3, "半导体应变片", "半导体应变片灵敏度高，适用于微小应变测量。"), "text": "半导体应变片灵敏度高，适用于微小应变测量。"},
    ]
    for item in items:
        item["is_direct_hit"] = True
    def final(evidence):
        state = {"user_input": query, "intent": "comparison", "evidence_gate_applied": True,
                 "evidence_items": evidence, "evidence_support": {"topic_terms": ["电阻式传感器"]}}
        pack = _prepare_evidence_pack(state)
        return state["evidence_support"], pack
    support, pack = final(items)
    assert support["status"] == "supported"
    assert set(support["matched_focus_terms"]) == {"两种材料", "特点", "应用场景"}
    assert all(value.startswith("E") for ids in support["fact_evidence"].values() for value in ids)
    # The list header alone cannot stand in for explanations for both members.
    assert final(items[:2])[0]["status"] == "partial"
    hidden = {**items[2], "text": "半导体应变片结构如图所示。", "section_title": "半导体应变片特点及应用场景"}
    assert final([*items[:2], hidden])[0]["status"] == "partial"
    clipped = {**items[2], "text": "半导体应变片结构。" + "填充文字" * 600 + "灵敏度高，适用于微小应变测量。"}
    assert final([*items[:2], clipped])[0]["status"] == "partial"


def test_model_literal_hyphen_and_numeric_input_boundaries():
    assert not retrieval._supports_query_literals("DEMO-X1 测量模块", "DEMO-X10 测量模块")
    assert retrieval._supports_query_literals("DEMO-X1 测量模块", "DEMO-X1 测量模块")
    assert retrieval._supports_query_literals("已知k1=16，计算响应", "响应计算方法")
