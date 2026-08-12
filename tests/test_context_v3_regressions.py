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
