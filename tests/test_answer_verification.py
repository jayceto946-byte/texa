from backend.services.answer_verification import derive_required_outputs, verify_answer


def test_general_mode_rejects_textbook_evidence_refusal_but_allows_missing_conditions():
    required = derive_required_outputs("列举传感器的分类", answer_mode="subject_general")
    bad = verify_answer("当前未提供相关教材证据，无法根据教材列举对应的类型。", required_outputs=required)
    assert bad["status"] == "failed"
    assert any(item["id"] == "answer_mode" for item in bad["failures"])
    for answer in [
        "按物理机制可分为结构型、物性型和复合型。",
        "缺少电源电压，无法计算输出数值。请补充电源电压。",
        "没有相关教材内容，无法确认原书措辞。但一般来说，按物理机制分为结构型、物性型和复合型。",
    ]:
        assert verify_answer(answer, required_outputs=required)["status"] == "passed"


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


def test_numeric_overlap_alone_is_unverified():
    result = verify_answer(
        "查表得到最终温度为 120°C。",
        required_outputs=[{"id": "final_numeric_answer", "label": "数值", "kind": "numeric", "required": True}],
        evidence_items=[{"text": "E 型热电偶 5mV 对应 120°C"}],
    )

    assert result["status"] == "unverified"


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
    assert passed["status"] == "unverified"
    assert next(item for item in passed["checks"] if item["id"] == "formula")["structure_status"] == "passed"
    assert next(item for item in passed["checks"] if item["id"] == "final_unit")["status"] == "passed"


def test_citation_must_support_its_adjacent_claim_when_source_text_is_available():
    result = verify_answer(
        "霍尔效应由磁场引起。[[cite:E1]]",
        required_outputs=[{"id": "citations", "kind": "citation", "required": True}],
        sources=[{"id": "E1", "text": "压阻效应是材料受力后电阻率发生变化的现象。"}],
    )
    assert result["status"] == "failed"
    assert result["checks"][0]["unsupported_ids"] == ["E1"]


def test_adjacent_citations_each_verify_the_shared_claim():
    sources = [{"id": "E1", "text": "弹性元件把压力转换为应变。"},
               {"id": "E2", "text": "电阻应变片把应变转换为电阻变化。"},
               {"id": "E3", "text": "应变式电阻传感器组合使用弹性元件和应变片。"}]
    required = [{"id": "citations", "kind": "citation", "required": True}]
    for separator in ("", " ", "\t"):
        answer = "弹性元件把压力转换为应变，应变片再把应变转换为电阻变化。" + separator.join(
            f"[[cite:{item['id']}]]" for item in sources)
        assert verify_answer(answer, required_outputs=required, sources=sources)["status"] == "passed"
    # Membership in a group must not excuse an unrelated or absent source.
    sources[1]["text"] = "霍尔效应由磁场引起。"
    result = verify_answer(answer, required_outputs=required, sources=sources)
    assert result["checks"][0]["unsupported_ids"] == ["E2"]
    assert verify_answer(answer + "[[cite:E99]]", required_outputs=required,
                         sources=sources)["status"] == "failed"


def test_citation_group_does_not_inherit_across_another_claim_or_paragraph():
    required = [{"id": "citations", "kind": "citation", "required": True}]
    sources = [{"id": "E1", "text": "电阻应变片把应变转换为电阻变化。"},
               {"id": "E2", "text": "电阻应变片把应变转换为电阻变化。"}]
    for suffix in ("\n\n[[cite:E2]]", "霍尔效应由磁场引起。[[cite:E2]]"):
        result = verify_answer("应变片将应变转换为电阻变化。[[cite:E1]]" + suffix,
                               required_outputs=required, sources=sources)
        assert result["checks"][0]["unsupported_ids"] == ["E2"]


def test_formula_only_source_can_support_an_equivalent_formula_citation():
    result = verify_answer(
        r"线圈电感满足 $L=N^2/R_{\mathrm m}$。[[cite:E1]]",
        required_outputs=[{"id": "citations", "kind": "citation", "required": True}],
        sources=[{"id": "E1", "text": r"$$L = N ^ { 2 } / R _ { \mathrm { m } }\tag{4.46}$$"}],
    )
    assert result["status"] == "passed"


def test_explanatory_temperature_question_does_not_require_numeric_answer():
    outputs = derive_required_outputs(
        "说明参考端温度变化如何影响补偿电势。",
        intent="application",
        answer_mode="visual_grounded",
    )
    assert "final_numeric_answer" not in {item["id"] for item in outputs}


def test_production_pack_citations_and_formula_equivalence():
    from graph.evidence_pack import build_evidence_pack
    from graph.generator import finalize_answer_verification
    raw = [{"chunk_id": "ohm", "text": "欧姆定律为 $U=IR$。"}]
    pack = build_evidence_pack(raw)
    for formula, expected in (("U=I/R", "failed"), ("U=IR", "passed"), ("IR=U", "passed")):
        state = {"user_input": "写出欧姆定律公式", "evidence_items": raw, "evidence_sources": pack["items"]}
        finalize_answer_verification(state, f"欧姆定律为 ${formula}$。[[cite:E1]]")
        assert state["answer_verification"]["status"] == expected
    assert verify_answer(r"公式为 $\frac{ab}{c}$。", required_outputs=[{"kind": "formula"}],
                         sources=[{"id": "E1", "text": r"公式为 $\frac{a}{bc}$。"}])["status"] != "passed"
    result = verify_answer("欧姆定律说明电压与电流的关系。[[cite:E1]]\n霍尔效应由磁场引起。[[cite:E1]]",
                           required_outputs=[{"id": "citations", "kind": "citation"}],
                           sources=pack["items"], evidence_items=pack["verification_items"])
    assert result["status"] == "failed"
    assert verify_answer("欧姆定律说明电压与电流的关系。[[cite:E1]]", required_outputs=[{"kind": "citation"}], sources=pack["items"])["status"] == "failed"


def test_unnumbered_deliverables_and_bound_numeric_receipt():
    outputs = derive_required_outputs("写出微分方程、灵敏度、固有频率、阻尼比和阶跃响应")
    result = verify_answer("灵敏度是输出变化与输入变化之比。", required_outputs=outputs)
    assert {item["id"] for item in result["failures"]} >= {"item_1", "item_3", "item_4", "item_5"}
    from backend.tools.math_tools import symbolic_math, verify_math_result
    from backend.services.tool_orchestration import build_tool_context_pack
    calculation = symbolic_math(None, {"operation": "calculate", "expression": "2+3"})
    request = calculation.data["verification_request"]
    verified = verify_math_result(None, request)
    pack = build_tool_context_pack([
        {"tool": "symbolic_math", "result": calculation.to_dict()},
        {"tool": "verify_math_result", "args": request, "result": verified.to_dict()},
    ])
    required = [{"id": "numeric", "kind": "numeric"}]
    for question, answer, expected in (("计算2+3", "最终结果为5。", "passed"),
                                       ("计算2+4", "最终结果为5。", "unverified"),
                                       ("计算2+3", "最终结果为6。", "unverified")):
        assert verify_answer(answer, question=question, required_outputs=required, tool_context_pack=pack)["status"] == expected


def test_figure_caption_is_citable_but_asset_metadata_cannot_support_a_claim():
    required = [{"id": "citations", "kind": "citation", "required": True}]
    caption = {"id": "E1", "figure_id": "fig-1", "caption": "结构示意图。"}
    assert verify_answer("这是结构示意图。[[cite:E1]]", required_outputs=required,
                         sources=[caption])["status"] == "passed"
    assert verify_answer("这是结构示意图。[[cite:E1]]", required_outputs=required,
                         sources=[{"id": "E1", "figure_id": "fig-1"}])["status"] == "failed"
    assert verify_answer("半导体应变片用于微小应变测量。[[cite:E1]]", required_outputs=required,
                         sources=[caption])["status"] == "failed"
