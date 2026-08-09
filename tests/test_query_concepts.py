"""Query-first 概念抽取 + Coverage Gate + Targeted repair 专项回归测试。

覆盖任务 CASE 1-12：
- 并列结构（、和与或）多概念召回
- 任务词（定义/区别/特点/优点/缺点/应用）过滤
- 别名覆盖（正态分布 -> 高斯分布）
- 相似但不同概念（压阻效应 vs 压电效应）绝不 fuzzy 合并
- 无效候选允许被拒绝
"""
import pytest


# ---------------------------------------------------------------------------
# 假 KG：只暴露 query_concepts 需要的最小接口
# ---------------------------------------------------------------------------

def _concept(name, aliases=(), cid=None):
    return {
        "concept_id": cid or f"CONCEPT_{name}",
        "canonical_name": name,
        "aliases": list(aliases),
        "roles": ["definition"],
    }


class FakeKG:
    _is_local = True

    def __init__(self, concepts):
        self.concepts = list(concepts)

    def get_concept_detail(self, name):
        for c in self.concepts:
            if c["canonical_name"] == name or name in c.get("aliases", []):
                return {"concept": c}
        return None


# ---------------------------------------------------------------------------
# 确定性候选抽取（无 KG / 有 KG 两种）
# ---------------------------------------------------------------------------

def test_case1_parallel_three_effects_all_captured():
    from knowledge.query_concepts import extract_query_candidates
    cands = extract_query_candidates(
        "总结一下横向效应、压阻效应、压电效应的定义和区别", kg=None)
    assert {c.name for c in cands} == {"横向效应", "压阻效应", "压电效应"}
    assert all(c.source == "query_parallel" for c in cands)


def test_case2_limit_continuity_derivable():
    from knowledge.query_concepts import extract_query_candidates
    cands = extract_query_candidates("比较极限、连续和可导之间的关系", kg=None)
    assert {c.name for c in cands} == {"极限", "连续", "可导"}


def test_case3_random_systemic_gross_errors():
    from knowledge.query_concepts import extract_query_candidates
    cands = extract_query_candidates("什么是随机误差、系统误差和粗大误差？", kg=None)
    assert {c.name for c in cands} == {"随机误差", "系统误差", "粗大误差"}


def test_case4_newton_and_lagrange_interpolation():
    from knowledge.query_concepts import extract_query_candidates
    cands = extract_query_candidates("牛顿插值和拉格朗日插值有什么区别？", kg=None)
    assert {c.name for c in cands} == {"牛顿插值", "拉格朗日插值"}


def test_case5_ntc_ptc_ctr():
    from knowledge.query_concepts import extract_query_candidates
    cands = extract_query_candidates("解释NTC、PTC和CTR热敏电阻的区别", kg=None)
    assert {c.name for c in cands} == {"NTC", "PTC", "CTR热敏电阻"}


def test_case6_task_words_not_concepts():
    from knowledge.query_concepts import extract_query_candidates
    cands = extract_query_candidates(
        "总结热敏电阻的定义、特点、优点、缺点和应用", kg=None)
    assert [c.name for c in cands] == ["热敏电阻"]


def test_case7_definition_and_application_not_concepts():
    from knowledge.query_concepts import extract_query_candidates
    cands = extract_query_candidates("解释压阻效应的定义和应用", kg=None)
    assert [c.name for c in cands] == ["压阻效应"]


def test_case8_single_topic_without_kg_yields_no_false_positive():
    # 无 KG 时，“为什么金属应变片受力以后电阻会变化？”不做单名词猜测，
    # 也不把 受力/变化 当概念。字典命中由有 KG 的测试覆盖。
    from knowledge.query_concepts import extract_query_candidates
    cands = extract_query_candidates("为什么金属应变片受力以后电阻会变化？", kg=None)
    assert cands == []


def test_case8_dictionary_resolves_strain_gauge():
    from knowledge.query_concepts import extract_query_candidates
    kg = FakeKG([_concept("电阻应变片", ["应变片"])])
    cands = extract_query_candidates("为什么金属应变片受力以后电阻会变化？", kg=kg)
    assert [(c.name, c.source) for c in cands] == [("电阻应变片", "query_dictionary")]


def test_case9_comparison_with_advantages_only_effects():
    from knowledge.query_concepts import extract_query_candidates
    cands = extract_query_candidates(
        "比较压阻效应和压电效应，再说明它们各自的优缺点", kg=None)
    assert {c.name for c in cands} == {"压阻效应", "压电效应"}


def test_case10_alias_coverage_gauss():
    from knowledge.query_concepts import (
        QueryCandidate, coverage_gate,
    )
    # 用户问 正态分布，KG canonical 是 高斯分布（别名 正态分布）
    cands = [
        QueryCandidate(name="高斯分布", source="query_dictionary",
                       concept_id="C_GAUSS", canonical_name="高斯分布", confidence=1.0,
                       aliases=["正态分布"]),
    ]
    final = [{"name": "高斯分布", "concept_id": "C_GAUSS", "confidence": 1.0, "aliases": ["正态分布"]}]
    auto, validate = coverage_gate(cands, final)
    assert auto == [] and validate == []


def test_case11_effects_never_fuzzy_merged():
    from knowledge.query_concepts import append_concepts
    a = {"name": "压阻效应", "confidence": 1.0}
    b = {"name": "压电效应", "confidence": 0.9}
    merged = append_concepts([a], [b])
    names = [c["name"] for c in merged]
    assert names == ["压阻效应", "压电效应"]
    assert len(merged) == 2


def test_case12_invalid_candidate_can_be_rejected():
    from knowledge.query_concepts import validate_missing_candidates
    from knowledge.query_concepts import QueryCandidate

    class FakeLLM:
        def invoke(self, prompt):
            class R:
                content = (
                    '[{"candidate": "横向效应", "valid_concept": true, "canonical_name": "横向效应", "reason": "ok"},'
                    '{"candidate": "考试", "valid_concept": false, "canonical_name": "", "reason": "非教材概念"}]'
                )
            return R()

    missing = [
        QueryCandidate(name="横向效应", source="query_parallel"),
        QueryCandidate(name="考试", source="query_parallel"),
    ]
    result = validate_missing_candidates("压阻效应和考试的关系", missing, FakeLLM())
    assert [c["name"] for c in result] == ["横向效应"]


def test_validate_parser_strips_thinking_and_code_fence():
    from knowledge.query_concepts import _parse_validation_response
    raw = (
        "当然可以。\n\n<think>先判断每个候选是否成立</think>\n\n"
        "```json\n[{\"candidate\": \"横向效应\", \"valid_concept\": true}]\n```"
    )
    parsed = _parse_validation_response(raw)
    assert parsed[0]["candidate"] == "横向效应"
    assert parsed[0]["valid_concept"] is True


def test_dictionary_priority_over_parallel():
    from knowledge.query_concepts import extract_query_candidates
    kg = FakeKG([_concept("压阻效应", ["压阻效应"])])
    cands = extract_query_candidates("总结压阻效应的定义和区别", kg=kg)
    assert [(c.name, c.source) for c in cands] == [("压阻效应", "query_dictionary")]


def test_dictionary_subsumed_term_not_candidate():
    # 随机误差、系统误差、粗大误差 都包含 "误差"，但 "误差" 从未独立出现，
    # 因此 "误差/绝对误差(别名 误差)" 不应成为独立候选。
    from knowledge.query_concepts import extract_query_candidates
    kg = FakeKG([
        _concept("随机误差"),
        _concept("系统误差"),
        _concept("粗大误差"),
        _concept("误差", ["测量误差"]),
        _concept("绝对误差", ["误差"]),  # 数据别名瑕疵：不应污染候选
    ])
    cands = extract_query_candidates("什么是随机误差、系统误差和粗大误差？", kg=kg)
    assert {c.name for c in cands} == {"随机误差", "系统误差", "粗大误差"}


def test_dictionary_standalone_parent_term_kept():
    # "误差" 有独立出现（"什么是误差和随机误差的区别"），应保留；
    # 但 绝对误差 仅靠别名 "误差" 命中，被 canonical 优先规则剔除。
    from knowledge.query_concepts import extract_query_candidates
    kg = FakeKG([
        _concept("随机误差"),
        _concept("误差", ["测量误差"]),
        _concept("绝对误差", ["误差"]),
    ])
    cands = extract_query_candidates("什么是误差和随机误差的区别", kg=kg)
    assert {c.name for c in cands} == {"误差", "随机误差"}


def test_append_concepts_dedupe_by_id_keeps_exact_different():
    from knowledge.query_concepts import append_concepts
    existing = [{"name": "压阻效应", "concept_id": "C_1", "confidence": 1.0}]
    extra = [{"name": "压阻效应", "concept_id": "C_1", "confidence": 0.9},  # 同一 concept_id -> 去重
             {"name": "压电效应", "concept_id": "C_2", "confidence": 0.9}]  # 不同 -> 保留
    merged = append_concepts(existing, extra)
    assert [c["name"] for c in merged] == ["压阻效应", "压电效应"]


# ---------------------------------------------------------------------------
# 集成：feedback_node._resolve_final_concepts
# ---------------------------------------------------------------------------

def test_resolve_final_concepts_case1_three_effects(monkeypatch):
    import graph.feedback_node as feedback

    kg = FakeKG([_concept("压阻效应", ["压阻效应"])])

    def fake_link(state):
        # 模拟现有 KG linker 只命中 压阻效应（当前真实 bug 的中间结果）
        return [{
            "name": "压阻效应", "concept_id": "CONCEPT_压阻效应", "type": "concept",
            "confidence": 0.88, "source": "question_mention", "evidence": "压阻效应",
            "aliases": [], "roles": [], "definition": "", "related_concepts": [],
            "source_chapters": [],
        }]

    def fake_repair(question, auto_missing, validate_missing, kg_, **kwargs):
        # 模拟受限验证：两个缺失候选都有效
        return [
            {"name": "横向效应", "concept_id": "", "type": "concept", "confidence": 0.9,
             "source": "query_repair", "evidence": "横向效应", "aliases": []},
            {"name": "压电效应", "concept_id": "", "type": "concept", "confidence": 0.9,
             "source": "query_repair", "evidence": "压电效应", "aliases": []},
        ]

    monkeypatch.setattr(feedback, "_link_concepts_locally", fake_link)
    monkeypatch.setattr(feedback, "_kg_for_state", lambda state: kg)
    monkeypatch.setattr(feedback, "_targeted_repair", fake_repair)

    final = feedback._resolve_final_concepts({
        "book_name": "传感器长书",
        "user_input": "总结一下横向效应、压阻效应、压电效应的定义和区别",
        "intent": "comparison",
        "use_textbook_context": True,
    })
    names = {c["name"] for c in final}
    assert {"横向效应", "压阻效应", "压电效应"} <= names
    assert "定义" not in names and "区别" not in names


def test_resolve_final_concepts_dictionary_missing_auto_added_without_llm(monkeypatch):
    import graph.feedback_node as feedback

    kg = FakeKG([_concept("粗大误差"), _concept("系统误差"), _concept("随机误差")])

    def fake_link(state):
        # 现有 linker 只命中了 随机误差 和 系统误差，漏掉 粗大误差
        return [
            {"name": "随机误差", "concept_id": "CONCEPT_随机误差", "confidence": 1.0, "aliases": []},
            {"name": "系统误差", "concept_id": "CONCEPT_系统误差", "confidence": 1.0, "aliases": []},
        ]

    repair_calls = []

    def fake_repair(question, auto_missing, validate_missing, kg_, **kwargs):
        repair_calls.append(len(auto_missing))
        # 字典缺失候选应直接补回（不调用 LLM）
        return [
            {"name": c.canonical_name or c.name, "concept_id": c.concept_id or "",
             "confidence": 1.0, "source": "query_dictionary", "aliases": list(c.aliases or [])}
            for c in auto_missing
        ]

    monkeypatch.setattr(feedback, "_link_concepts_locally", fake_link)
    monkeypatch.setattr(feedback, "_kg_for_state", lambda state: kg)
    monkeypatch.setattr(feedback, "_targeted_repair", fake_repair)

    final = feedback._resolve_final_concepts({
        "book_name": "误差理论与数据处理",
        "user_input": "什么是随机误差、系统误差和粗大误差？",
        "intent": "qa",
        "use_textbook_context": True,
    })
    names = {c["name"] for c in final}
    assert {"随机误差", "系统误差", "粗大误差"} <= names
    # 粗大误差 是字典确认候选，走 auto_missing（repair 里不需要 LLM 验证逻辑）
    assert repair_calls and repair_calls[0] == 1


def test_resolve_final_concepts_non_textbook_context_unchanged(monkeypatch):
    import graph.feedback_node as feedback

    kg = FakeKG([_concept("关联词")])

    monkeypatch.setattr(feedback, "_link_concepts_locally",
                        lambda state: [{"name": "关联词", "confidence": 1.0, "aliases": []}])
    monkeypatch.setattr(feedback, "_kg_for_state", lambda state: kg)
    # 即使 KG 字典能命中 关联词，非教材上下文（学科路由）也不走 query-first / repair
    final = feedback._resolve_final_concepts({
        "book_name": "sensor-book",
        "user_input": "介绍几个英语写作中常用的关联词",
        "use_textbook_context": False,
    })
    assert [c["name"] for c in final] == ["关联词"]


def test_link_concepts_for_response_preserves_existing_strict_behavior(monkeypatch):
    import graph.feedback_node as feedback

    monkeypatch.setattr(
        feedback,
        "_link_concepts_locally",
        lambda state: [
            {"name": "梯度", "confidence": 1.0, "aliases": []},
            {"name": "直接命中", "confidence": 0.88, "aliases": []},
            {"name": "候选词", "confidence": 0.8, "aliases": []},
        ],
    )
    result = feedback.link_concepts_for_response({"user_input": "什么是梯度和直接命中"})
    assert result == [
        {"name": "梯度", "confidence": 1.0, "aliases": []},
        {"name": "直接命中", "confidence": 0.88, "aliases": []},
    ]


# ---------------------------------------------------------------------------
# Concept Scope：book/subject/chapter container 不因词面出现而进入 core concepts
# ---------------------------------------------------------------------------

def test_resolve_final_concepts_filters_book_container_from_ordinary_question(monkeypatch):
    import graph.feedback_node as feedback

    kg = FakeKG([_concept("传感器"), _concept("压阻效应")])

    def fake_link(state):
        # 模拟现有 KG linker：普通压阻问题只命中 压阻效应（传感器 只作为词面出现）
        return [{
            "name": "压阻效应", "concept_id": "CONCEPT_压阻效应", "type": "concept",
            "confidence": 1.0, "source": "kg_matched", "evidence": "压阻效应",
            "aliases": [], "roles": [], "definition": "", "related_concepts": [], "source_chapters": [],
        }]

    monkeypatch.setattr(feedback, "_link_concepts_locally", fake_link)
    monkeypatch.setattr(feedback, "_kg_for_state", lambda state: kg)

    final = feedback._resolve_final_concepts({
        "book_name": "传感器长书",  # de-suffix -> "传感器" 是 container
        "subject": "专业课",
        "user_input": "压阻效应通常应用于哪些传感器？",
        "intent": "qa",
        "use_textbook_context": True,
        "target_chapters": ["第1章 绪论"],
        "matched_concepts": ["压阻效应"],
    })
    names = {c["name"] for c in final}
    assert "压阻效应" in names
    assert "传感器" not in names  # 容器只因词面出现，不得进入 core concepts


def test_resolve_final_concepts_keeps_container_when_explicitly_asked(monkeypatch):
    import graph.feedback_node as feedback

    kg = FakeKG([_concept("传感器")])

    def fake_link(state):
        # "什么是传感器？" 时 传感器 是显式询问对象（kg_matched），必须保留
        return [{
            "name": "传感器", "concept_id": "CONCEPT_传感器", "type": "concept",
            "confidence": 1.0, "source": "kg_matched", "evidence": "传感器",
            "aliases": [], "roles": [], "definition": "", "related_concepts": [], "source_chapters": [],
        }]

    monkeypatch.setattr(feedback, "_link_concepts_locally", fake_link)
    monkeypatch.setattr(feedback, "_kg_for_state", lambda state: kg)

    final = feedback._resolve_final_concepts({
        "book_name": "传感器长书",
        "subject": "专业课",
        "user_input": "什么是传感器？",
        "intent": "definition",
        "use_textbook_context": True,
        "target_chapters": ["第1章 绪论"],
        "matched_concepts": ["传感器"],
    })
    names = {c["name"] for c in final}
    assert "传感器" in names
