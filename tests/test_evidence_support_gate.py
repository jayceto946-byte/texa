from graph.generator import grounded_failure_message, has_textbook_evidence
from graph.retrieval_node import (
    _assess_evidence_support,
    _extract_query_focus,
    _is_enumeration_query,
    _is_formula_item,
    _is_table_query,
    _looks_like_toc_chunk,
    _needs_teaching_unit_context,
    _retrieval_query_for_intent,
    _select_enumeration_anchor,
)


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


def test_textbook_definition_wording_does_not_become_a_fact_requirement():
    topics, focus = _extract_query_focus("教材如何定义有效数字？", ["有效数字"])
    assert topics == ["有效数字"]
    assert focus == []


def test_definition_and_range_keeps_the_range_as_a_real_fact_dimension():
    topics, focus = _extract_query_focus("误差相关系数的定义和取值范围是什么？", ["误差相关系数"])
    assert topics == ["误差相关系数"]
    assert "取值范围" in focus


def test_numbered_class_question_uses_enumeration_retrieval():
    assert _is_enumeration_query("误差按性质分为哪三类？", "factual_recall") is True


def test_untitled_table_question_with_adjacent_prompt_uses_table_retrieval():
    assert _is_table_query("热电偶在如下表中的温度下会输出什么数据？") is True


def test_topic_is_inferred_for_negative_sensor_question_without_specific_kg_match():
    topics, focus = _extract_query_focus(
        "电容式传感器未来的商业销售预测是什么？",
        ["传感器"],
    )
    assert topics == ["电容式传感器"]
    assert focus == ["未来的商业销售预测"]


def test_generated_list_context_is_not_inferred_as_a_sensor_topic():
    topics, focus = _extract_query_focus(
        "内容简介主要包括哪些内容？传感器的概念 分类",
        ["传感器"],
    )
    assert topics == ["传感器"]
    assert focus == ["分类"]


def test_enumeration_anchor_prefers_same_topic_body_over_generic_classification():
    items = [
        {
            "chunk_id": "wrong", "section_title": "温敏传感器的分类",
            "text": "接触式传感器的优点是测量简单。",
            "enumeration_match_quality": 0.3, "title_match_quality": 0.4,
            "retrieval_rank": 1,
        },
        {
            "chunk_id": "right", "section_title": "概述",
            "text": "光电传感器属于非接触测量器件，具有体积小、质量轻、响应快、灵敏度高、功耗低等优点。",
            "enumeration_match_quality": 0.0, "title_match_quality": 0.0,
            "retrieval_rank": 5,
        },
    ]

    assert _select_enumeration_anchor(items, "光电传感器的优点有哪些？")["chunk_id"] == "right"


def test_enumeration_anchor_uses_post_question_hint_over_unrelated_list_structure():
    items = [
        {
            "chunk_id": "wrong", "section_title": "第十一章",
            "text": "本节另有第一类、第二类和第三类防护方法。",
            "enumeration_match_quality": 0.9, "title_match_quality": 1.0,
            "retrieval_rank": 1,
        },
        {
            "chunk_id": "right", "section_title": "第十一章",
            "text": "核辐射包括α粒子、β粒子和γ射线。",
            "enumeration_match_quality": 0.0, "title_match_quality": 1.0,
            "retrieval_rank": 8,
        },
    ]

    selected = _select_enumeration_anchor(items, "本章主要包括哪些内容？α粒子 β粒子")

    assert selected["chunk_id"] == "right"


def test_enumeration_anchor_prefers_requested_disadvantage_over_generic_feature_header():
    items = [
        {
            "chunk_id": "generic", "section_title": "电容式传感器的特点",
            "text": "电容式传感器有以下优点。",
            "enumeration_match_quality": 0.8, "title_match_quality": 0.8,
            "retrieval_rank": 1,
        },
        {
            "chunk_id": "disadvantages", "section_title": "动态响应好",
            "text": "电容式传感器的缺点是输出阻抗高、寄生电容影响大。",
            "enumeration_match_quality": 0.0, "title_match_quality": 0.0,
            "retrieval_rank": 7,
        },
    ]

    selected = _select_enumeration_anchor(items, "电容式传感器有哪些缺点？")

    assert selected["chunk_id"] == "disadvantages"


def test_spaced_chinese_toc_heading_is_not_treated_as_content():
    assert _looks_like_toc_chunk({"section_title": "目 录", "text": "6.1 概述 144"}) is True


def test_formula_intent_restores_adjacent_formula_units():
    assert _needs_teaching_unit_context("误差相关系数的定义和取值范围是什么？", "formula") is True


def test_formula_metadata_marks_paragraph_as_formula_bearing():
    assert _is_formula_item({"block_type": "paragraph", "equations": ["U_o=Sx"]}) is True
    assert _is_formula_item({"block_type": "paragraph", "equations": '["U_o=Sx"]'}) is True
    assert _is_formula_item({"block_type": "paragraph", "equations": "[]"}) is False


def test_definition_retrieval_query_promotes_the_named_concept_section():
    query = _retrieval_query_for_intent("不等精度测量中的权表示什么？", "definition")
    assert query.startswith("权 权的概念 定义 ")


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


def test_support_gate_treats_adjacent_table_prompt_and_table_as_one_unit():
    item = _item(
        text="| mV | 4.37 | 8.74 | 13.11 | 17.48 |\n|---|---|---|---|---|",
        coverage=0.0,
        sources=["dense"],
    ) | {
        "block_type": "table",
        "is_table_neighbor": True,
        "table_anchor_text": "钨铼热电偶在如下表温度下有对应电动势，试确定灵敏度。",
    }

    result = _assess_evidence_support(
        "钨铼热电偶在如下表温度下的输出电动势和灵敏度是什么？",
        [item],
        matched_concepts=["热电偶"],
    )

    assert result["status"] == "supported"
    assert result["matched_focus_terms"] == ["灵敏度"]


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


def test_factual_enumeration_keeps_selected_book_group_before_core_group():
    from graph.retrieval_node import _merge_and_rerank

    common = {
        "section_title": "特点", "chapter": "chapter", "source": "neighbor",
        "retrieval_rank": 1, "list_group_order": 0, "list_group_part": "header",
    }
    _, items = _merge_and_rerank(
        [],
        [
            {**common, "chunk_id": "core", "text": "核心教材列表", "book_name": "core", "is_selected_book": False},
            {**common, "chunk_id": "selected", "text": "选中教材列表", "book_name": "selected", "is_selected_book": True},
        ],
        include_metadata=True,
        query="电容式传感器有哪些优点？",
        intent="factual_recall",
    )

    assert items[0]["chunk_id"] == "selected"


def test_factual_enumeration_keeps_numbered_member_heading_as_evidence():
    from graph.evidence_pack import build_evidence_pack
    from graph.retrieval_node import _merge_and_rerank

    item = {
        "chunk_id": "temperature", "text": "电容值与电极材料无关，本身发热极小。",
        "section_title": "1. 温度稳定性好", "chapter": "第四章",
        "source": "bm25", "retrieval_rank": 4, "book_name": "selected",
        "book_role": "core", "is_selected_book": True,
    }
    _chapters, debug = _merge_and_rerank(
        [], [item], include_metadata=True,
        query="电容式传感器有哪些优点？", intent="factual_recall",
    )
    pack = build_evidence_pack(debug, intent="factual_recall")

    assert debug[0]["text"].startswith("## 1. 温度稳定性好")
    assert "温度稳定性好" in pack["text"]


def test_section_number_is_not_mistaken_for_enumeration_member():
    from graph.retrieval_node import _is_enumeration_member_title

    assert _is_enumeration_member_title("1. 温度稳定性好") is True
    assert _is_enumeration_member_title("（2）结构简单") is True
    assert _is_enumeration_member_title("11.1.4 电容测量电路") is False


def test_list_group_reassembles_numbered_sibling_sections_under_same_parent():
    from graph.retrieval_node import _list_group_neighbors

    anchor = {
        "chunk_id": "header", "chapter": "第四章", "chunk_index": 20,
        "section_title": "4.3.1 电容式传感器的特点",
        "section_path": ["第四章", "教材名", "4.3.1 电容式传感器的特点"],
        "text": "与其他传感器相比，电容式传感器有以下优点。",
    }
    expanded = [
        {
            "chunk_id": "previous", "chapter": "第四章", "chunk_index": 19,
            "section_title": "2. 上一节的编号项",
            "section_path": ["第四章", "教材名", "2. 上一节的编号项"],
            "text": "不应从列表引导句向前恢复。",
        },
        anchor,
        {
            "chunk_id": "temperature", "chapter": "第四章", "chunk_index": 21,
            "section_title": "1. 温度稳定性好",
            "section_path": ["第四章", "教材名", "1. 温度稳定性好"],
            "text": "电极材料温度系数低。",
        },
        {
            "chunk_id": "structure", "chapter": "第四章", "chunk_index": 22,
            "section_title": "2. 结构简单",
            "section_path": ["第四章", "教材名", "2. 结构简单"],
            "text": "结构简单，易于制造。",
        },
        {
            "chunk_id": "other-parent", "chapter": "第四章", "chunk_index": 23,
            "section_title": "1. 无关条目",
            "section_path": ["第四章", "另一节", "1. 无关条目"],
            "text": "不应混入。",
        },
    ]

    selected = _list_group_neighbors(anchor, expanded)

    assert [item["chunk_id"] for item in selected] == ["header", "temperature", "structure"]

def test_support_gate_application_phrasing_not_rejected_as_focus():
    """Context Test A：\"压阻效应通常用在哪些传感器里？\" 的\"通常用在哪些\"是功能词，
    不应变成无法被证据逐字覆盖的 focus 词导致误拒答。"""
    topics, focus = _extract_query_focus(
        "那压阻效应通常用在哪些传感器里？",
        ["压阻效应", "传感器"],
    )
    assert any("压阻效应" in t for t in topics)
    assert focus == []  # 应用介词/疑问词不构成需要证据覆盖的 focus

    result = _assess_evidence_support(
        "那压阻效应通常用在哪些传感器里？",
        [_item(text="压阻式传感器利用压阻效应测量压力，广泛应用于工业测量。", sources=["dense", "bm25"], direct=True)],
        matched_concepts=["压阻效应", "传感器"],
    )
    assert result["status"] == "supported"


def test_support_gate_still_verifies_real_focus_terms():
    """扩展 filler 后，缺点/特点等真实 focus 词仍必须被证据覆盖，gate 目的不变。"""
    result = _assess_evidence_support(
        "压阻效应的缺点是什么？",
        [_item(text="压阻式传感器结构简单，温度稳定性较好。", coverage=0.5)],
        matched_concepts=["压阻效应"],
    )
    assert result["status"] != "supported"  # 缺点 focus 未被证据覆盖，不能整答
    assert result["matched_focus_terms"] == []


def test_support_gate_strips_user_correction_speech_act():
    query = "其他两个方法应该叫别捷尔斯法和极差法"
    topics, focus = _extract_query_focus(query, ["别捷尔斯法", "极差法"])
    assert topics == ["别捷尔斯法", "极差法"]
    assert focus == []
    result = _assess_evidence_support(
        query,
        [_item(title="标准差的其他计算法", text="计算标准差还有别捷尔斯法、极差法。", direct=True)],
        matched_concepts=["别捷尔斯法", "极差法"],
    )
    assert result["status"] == "supported"


def test_support_gate_requires_topic_and_focus_in_same_evidence():
    result = _assess_evidence_support(
        "电容式传感器有哪些缺点？",
        [
            _item(text="电容式传感器结构简单。", coverage=0.7),
            _item(title="其他器件的缺点", text="缺点是输出不稳定。", coverage=0.7),
        ],
        matched_concepts=["电容式传感器"],
    )
    assert result["status"] != "supported"
    assert result["matched_focus_terms"] == []


def test_relationship_question_is_supported_by_explicit_cross_topic_evidence():
    result = _assess_evidence_support(
        "标准差和随机误差之间的联系",
        [
            _item(
                title="函数随机误差",
                text="随机误差是用表征其取值分散程度的标准差来评定的。",
                direct=True,
                coverage=0.6,
            ),
            _item(
                text="标准差不是某一次具体随机误差，而是反映测量列随机误差分散程度的统计量。",
                coverage=0.6,
            ),
        ],
        matched_concepts=["标准差", "随机误差"],
        intent="comparison",
    )
    assert result["status"] == "supported"
    assert result["matched_focus_terms"] == ["关系"]


def test_relationship_question_stays_partial_without_an_explicit_relation():
    result = _assess_evidence_support(
        "标准差和随机误差之间的联系",
        [
            _item(text="标准差用于表示数据分散程度。", direct=True, coverage=0.5),
            _item(text="随机误差的符号和绝对值不可预定。", direct=True, coverage=0.5),
        ],
        matched_concepts=["标准差", "随机误差"],
        intent="comparison",
    )
    assert result["status"] != "supported"


def test_enumeration_count_is_supported_by_four_named_methods():
    result = _assess_evidence_support(
        "求标准差的四个方法是什么？",
        [_item(
            title="标准差的其他计算法",
            text="除了贝塞尔公式外，计算标准差还有别捷尔斯法、极差法及最大误差法。",
            direct=True,
            coverage=0.5,
        )],
        matched_concepts=["标准差"],
        intent="factual_recall",
    )
    assert result["status"] == "supported"


def test_formula_role_supports_specific_formula_followup():
    result = _assess_evidence_support(
        "标准差的四个方法分别有哪些具体公式？",
        [_item(
            title="标准差的其他计算法",
            text="贝塞尔公式、别捷尔斯法、极差法和最大误差法都有对应公式。",
            direct=True,
            coverage=0.5,
        ) | {"role": "formula"}],
        matched_concepts=["标准差"],
        intent="formula",
    )
    assert result["status"] == "supported"
    assert "具体公式" in result["matched_focus_terms"]


def test_derivation_request_is_decomposed_into_supported_dimensions():
    query = "请从基本公式开始，推导差动电容式传感器的灵敏度，并说明近似成立条件。"
    topics, focus = _extract_query_focus(query, ["传感器"])
    assert topics == ["传感器"]
    assert focus == ["基本公式", "灵敏度", "近似成立条件"]

    result = _assess_evidence_support(
        query,
        [
            _item(title="静态灵敏度", text="由式（4-2）可得灵敏度表达式。"),
            {**_item(text="当相对位移为小量时，可忽略高阶项并作近似。"), "role": "derivation"},
        ],
        matched_concepts=["传感器"],
        intent="derivation",
    )
    assert result["status"] == "supported"


def test_multi_sensor_comparison_can_be_partially_grounded_per_dimension():
    query = "比较压阻式、压电式和电容式传感器，并分别说明灵敏度、频响、静态测量能力和典型误差来源。"
    _, focus = _extract_query_focus(query, ["传感器"])
    assert focus == ["灵敏度", "频率响应", "静态测量能力", "典型误差来源"]

    result = _assess_evidence_support(
        query,
        [_item(title="静态灵敏度", text="本节给出灵敏度计算公式。")],
        matched_concepts=["传感器"],
        intent="comparison",
    )
    assert result["status"] == "partial"


def test_calculation_retrieval_query_requests_formulas_not_device_examples():
    query = _retrieval_query_for_intent("压阻式传感器怎么算？", "calculation")
    assert query.startswith("压阻式传感器 ")
    assert "计算公式" in query
    assert "变量" in query
