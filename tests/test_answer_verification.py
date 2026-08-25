from backend.services.answer_verification import derive_required_outputs, verify_answer


def test_required_outputs_extract_numbered_question_parts():
    outputs = derive_required_outputs(
        "（1）写出公式；（2）计算输出电压；（3）说明误差来源。",
        intent="application",
        answer_mode="textbook_grounded",
    )

    ids = [item["id"] for item in outputs]
    assert ids[:4] == ["answer", "part_1", "part_2", "part_3"]
    assert "final_numeric_answer" in ids
    assert "formula" in ids
    assert "citations" in ids


def test_verification_rejects_missing_required_part_and_invalid_citation():
    required = derive_required_outputs(
        "（1）写出灵敏度公式；（2）说明温度误差。",
        intent="application",
        answer_mode="textbook_grounded",
    )
    result = verify_answer(
        r"灵敏度公式为 $S=\Delta y/\Delta x$。[[cite:E9]]",
        required_outputs=required,
        sources=[{"id": "E1"}],
        citation_trace={"invalid_ids_removed": 1},
    )

    assert result["status"] == "failed"
    assert {item["id"] for item in result["failures"]} >= {"part_2", "citations"}


def test_numeric_answer_is_verified_by_matching_supplied_evidence():
    result = verify_answer(
        "查表得到最终温度为 120°C。",
        required_outputs=[{"id": "final_numeric_answer", "label": "数值", "kind": "numeric", "required": True}],
        evidence_items=[{"text": "E 型热电偶 5mV 对应 120°C"}],
    )

    assert result["status"] == "passed"


def test_method_only_without_numeric_is_valid_degradation():
    result = verify_answer(
        "先补偿冷端温度，再用热电势查分度表。",
        required_outputs=[{"id": "final_numeric_answer", "label": "数值", "kind": "numeric", "required": True}],
        answer_policy="method_only",
    )

    assert result["status"] == "degraded"
    assert result["passed"] is True


def test_required_unit_and_formula_are_enforced_in_final_answer():
    required = derive_required_outputs("列出公式并计算输出电压，结果用 mV 表示。", intent="calculation")
    failed = verify_answer("最终结果为 12 V。", required_outputs=required)
    assert {item["id"] for item in failed["failures"]} >= {"formula", "final_unit"}

    passed = verify_answer(
        r"由 $U=IR$，最终结果为 12 mV。",
        required_outputs=required,
        evidence_items=[{"text": "输出电压为 12 mV"}],
    )
    assert passed["status"] == "passed"


def test_citation_must_support_its_adjacent_claim_when_source_text_is_available():
    result = verify_answer(
        "霍尔效应由磁场引起。[[cite:E1]]",
        required_outputs=[{"id": "citations", "kind": "citation", "required": True}],
        sources=[{"id": "E1", "text": "压阻效应是材料受力后电阻率发生变化的现象。"}],
    )
    assert result["status"] == "failed"
    assert result["checks"][0]["unsupported_ids"] == ["E1"]
