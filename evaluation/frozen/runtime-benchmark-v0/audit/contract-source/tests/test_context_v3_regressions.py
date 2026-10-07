from backend.services.assistant_artifacts import (
    extract_assistant_artifacts,
    match_assistant_artifact,
    rewrite_artifact_reference,
)
from backend.services.session_context import resolve_followup_with_trace


def test_plain_numbered_list_supports_chinese_point_reference():
    artifacts = extract_assistant_artifacts(
        "1. 灵敏度高\n2. 体积小\n3. 热惯性小\n4. 电阻与温度呈非线性关系",
        user_query="热敏电阻的主要特点有哪些？",
        turn_id="t1",
    )
    artifact = match_assistant_artifact("第四点是什么意思？", artifacts)
    assert artifact and artifact["target"] == "电阻与温度呈非线性关系"
    assert "电阻与温度呈非线性关系" in rewrite_artifact_reference("第四点是什么意思？", artifact)


def test_measurement_facet_correction_keeps_previous_topic():
    history = [
        {"role": "user", "content": "电感式传感器适合动态测量吗？", "turn_id": "t1"},
        {"role": "assistant", "content": "需要结合测量频率判断。", "turn_id": "t1"},
    ]
    resolved, trace = resolve_followup_with_trace("我问的是高频动态测量，不是低频", history)
    assert "电感式传感器" in resolved
    assert "高频动态测量" in resolved
    assert trace["is_followup"] is True


def test_named_method_group_supports_formula_followup():
    history = [
        {"role": "user", "content": "求标准差的四个方法是什么？", "turn_id": "t1"},
        {
            "role": "assistant",
            "content": "1. 贝塞尔法\n2. 别捷尔斯法\n3. 极差法\n4. 最大误差法",
            "turn_id": "t1",
        },
    ]
    resolved, trace = resolve_followup_with_trace("介绍四个方法的公式", history)
    assert all(name in resolved for name in ("贝塞尔法", "别捷尔斯法", "极差法", "最大误差法"))
    assert trace["method"] == "deterministic_assistant_artifact"
    assert trace["is_followup"] is True


def test_numbered_method_formula_followup_resolves_list_item():
    history = [
        {"role": "user", "content": "求标准差的四个方法是什么？", "turn_id": "t1"},
        {"role": "assistant", "content": "1. 贝塞尔法\n2. 别捷尔斯法\n3. 极差法\n4. 最大误差法", "turn_id": "t1"},
    ]
    resolved, trace = resolve_followup_with_trace("第三个方法的公式是什么？", history)
    assert "极差法" in resolved
    assert trace["method"] == "deterministic_assistant_artifact"


def test_recheck_formula_followups_inherit_previous_question():
    history = [
        {"role": "user", "content": "求标准差的四个方法是什么？", "turn_id": "t1"},
        {"role": "assistant", "content": "教材列出了四种方法，但本轮没有展开公式。", "turn_id": "t1"},
    ]
    for followup in ("真的没有具体公式吗？再查查", "具体公式呢？", "再查查"):
        resolved, trace = resolve_followup_with_trace(followup, history)
        assert "标准差的四个方法" in resolved
        assert "检索教材" in resolved
        assert trace["method"] == "deterministic_rephrase"
        assert trace["is_followup"] is True
        assert trace["speech_act"] == "continue"


def test_other_two_is_not_treated_as_pronoun_qi():
    history = [
        {"role": "user", "content": "求标准差的方法有哪些？", "turn_id": "t1"},
        {"role": "assistant", "content": "贝塞尔法和最大误差法。", "turn_id": "t1"},
    ]
    resolved, trace = resolve_followup_with_trace("其他两个方法应该叫别捷尔斯法和极差法", history)
    assert resolved == "其他两个方法应该叫别捷尔斯法和极差法"
    assert trace["method"] == "identity"
