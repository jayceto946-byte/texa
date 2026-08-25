"""Deterministic post-generation checks for learning answers.

These checks do not try to prove an arbitrary derivation correct.  They enforce
the parts the harness can know: requested sections are present, citations point
to this turn's evidence, and numeric conclusions disclose whether a deterministic
tool or supplied evidence verified them.
"""
from __future__ import annotations

import re
from typing import Any


_CITATION_RE = re.compile(r"\[\[cite:(E[\w-]+)\]\]", re.I)
_NUMBER_RE = re.compile(r"(?<![\w])[-+]?\d+(?:\.\d+)?(?:\s*(?:°C|℃|%|V|mV|A|mA|Ω|Pa|kPa|MPa|Hz|mm|cm|m|s))?")
_UNIT_RE = re.compile(r"(?<![A-Za-z])(?:°C|℃|K|mV|V|mA|A|kΩ|MΩ|Ω|kPa|MPa|Pa|kHz|MHz|Hz|mm|cm|km|m|ms|s)(?![A-Za-z])")
_FORMULA_RE = re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]|\\\(.*?\\\)|\$[^$\n]+\$", re.S)
_PART_RE = re.compile(r"(?:第\s*(\d+)\s*问|[（(](\d+)[）)])")
_STOP_ANCHORS = {
    "请", "求", "计算", "说明", "分析", "回答", "问题", "分别", "根据", "给出", "为什么",
    "是多少", "是什么", "怎么", "如何", "下列", "其中", "以及", "并且", "最终", "结果",
}


def _anchors(text: str) -> list[str]:
    normalized = re.sub(r"^(?:请|写出|给出|说明|分析|计算|求出?|回答|判断)+", "", str(text or "").strip())
    candidates = re.findall(r"[\u4e00-\u9fff]{2,12}|[A-Za-z][A-Za-z0-9_]{1,15}", normalized)
    result: list[str] = []
    for value in candidates:
        if value in _STOP_ANCHORS or any(stop in value for stop in _STOP_ANCHORS if len(stop) >= 2):
            continue
        if value not in result:
            result.append(value)
    return result[:6]


def derive_required_outputs(question: str, *, intent: str = "qa", answer_mode: str = "") -> list[dict[str, Any]]:
    text = str(question or "").strip()
    outputs: list[dict[str, Any]] = [{
        "id": "answer", "label": "针对当前问题的回答", "kind": "content", "required": True,
    }]
    matches = list(_PART_RE.finditer(text))
    for index, match in enumerate(matches):
        part_number = match.group(1) or match.group(2) or str(index + 1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = text[match.end():end].strip(" ：:，,；;。")
        outputs.append({
            "id": f"part_{part_number}",
            "label": f"第 {part_number} 问：{segment[:80] or '作答'}",
            "kind": "question_part",
            "anchors": _anchors(segment),
            "required": True,
        })
    numeric_requested = intent == "calculation" or bool(re.search(
        r"计算|求值|数值|多少|结果为|反查|温度|电势|电压|电流|概率", text,
    ))
    if numeric_requested:
        outputs.append({
            "id": "final_numeric_answer", "label": "最终数值及单位", "kind": "numeric", "required": True,
        })
    expected_units = list(dict.fromkeys(_UNIT_RE.findall(text)))
    unit_requested = bool(expected_units) and (numeric_requested or bool(re.search(r"单位|量纲|换算|转换", text)))
    if unit_requested:
        outputs.append({
            "id": "final_unit", "label": "最终结果的单位", "kind": "unit",
            "expected_units": expected_units[-3:], "required": True,
        })
    if bool(re.search(r"公式|关系式|表达式|方程|推导|证明|列式", text)):
        outputs.append({
            "id": "formula", "label": "所需公式或推导关系", "kind": "formula", "required": True,
        })
    if answer_mode == "textbook_grounded":
        outputs.append({
            "id": "citations", "label": "教材结论的本轮来源", "kind": "citation", "required": True,
        })
    return outputs


def _verified_math(tool_context_pack: dict[str, Any] | None) -> bool:
    for item in (tool_context_pack or {}).get("outputs") or []:
        if not isinstance(item, dict):
            continue
        verification = item.get("verification") or {}
        if item.get("tool") == "verify_math_result" and verification.get("passed") is True:
            return True
    return False


def _evidence_text(evidence_items: list[dict[str, Any]] | None) -> str:
    parts = []
    for item in evidence_items or []:
        if isinstance(item, dict):
            parts.append(str(item.get("text") or item.get("problem_text") or ""))
    return "\n".join(parts)


def _balanced_formula_delimiters(text: str) -> bool:
    return text.count("$$") % 2 == 0 and text.count("\\[") == text.count("\\]") and text.count("\\(") == text.count("\\)")


def _source_texts(
    sources: list[dict[str, Any]] | None,
    evidence_items: list[dict[str, Any]] | None,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in [*(sources or []), *(evidence_items or [])]:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id") or item.get("evidence_id") or "").upper()
        content = str(item.get("text") or item.get("content") or item.get("problem_text") or "")
        if source_id and content:
            result[source_id] = content
    return result


def _citation_semantically_supported(answer: str, source_id: str, source_text: str) -> bool:
    marker = f"[[cite:{source_id}]]"
    position = answer.upper().find(marker.upper())
    claim = answer[max(0, position - 220):position] if position >= 0 else ""
    def terms(value: str) -> set[str]:
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", value))
        grams = {chinese[index:index + 2] for index in range(max(0, len(chinese) - 1))}
        return grams | {item.lower() for item in re.findall(r"[A-Za-z]{3,}", value)}

    claim_terms = terms(claim) - _STOP_ANCHORS
    source_terms = terms(source_text)
    return len(claim_terms & source_terms) >= 2


def verify_answer(
    answer: str,
    *,
    required_outputs: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    citation_trace: dict[str, Any] | None = None,
    tool_context_pack: dict[str, Any] | None = None,
    evidence_items: list[dict[str, Any]] | None = None,
    answer_policy: str = "exact",
) -> dict[str, Any]:
    text = str(answer or "").strip()
    checks: list[dict[str, Any]] = []
    for output in required_outputs or []:
        if not output.get("required", True):
            continue
        kind = str(output.get("kind") or "content")
        check = {"id": str(output.get("id") or kind), "label": str(output.get("label") or kind)}
        if kind == "content":
            check.update(status="passed" if len(text) >= 4 else "failed", reason="" if len(text) >= 4 else "回答正文为空或过短")
        elif kind == "question_part":
            anchors = [str(item) for item in output.get("anchors") or []]
            matched = [item for item in anchors if item and item in text]
            passed = not anchors or bool(matched)
            check.update(status="passed" if passed else "failed", matched=matched, reason="" if passed else "未找到该分项的核心对象")
        elif kind == "citation":
            valid_ids = {str(item.get("id") or "").upper() for item in (sources or []) if isinstance(item, dict)}
            cited_ids = {item.upper() for item in _CITATION_RE.findall(text)}
            invalid_removed = int((citation_trace or {}).get("invalid_ids_removed") or 0)
            if not valid_ids:
                check.update(status="not_applicable", reason="本轮没有可引用的结构化来源")
            else:
                matched_ids = cited_ids & valid_ids
                source_texts = _source_texts(sources, evidence_items)
                unsupported = [
                    source_id for source_id in matched_ids
                    if source_id in source_texts and not _citation_semantically_supported(text, source_id, source_texts[source_id])
                ]
                passed = bool(matched_ids) and invalid_removed == 0 and not unsupported
                check.update(
                    status="passed" if passed else "failed",
                    cited_ids=sorted(cited_ids),
                    unsupported_ids=sorted(unsupported),
                    reason="" if passed else "回答缺少有效的本轮教材引用、引用与相邻结论不相符，或生成了无效编号",
                )
        elif kind == "formula":
            formulas = _FORMULA_RE.findall(text)
            passed = bool(formulas) and _balanced_formula_delimiters(text)
            check.update(
                status="passed" if passed else "failed",
                formula_count=len(formulas),
                reason="" if passed else "问题要求公式或推导关系，但回答缺少完整的 LaTeX 公式",
            )
        elif kind == "unit":
            expected = [str(item) for item in output.get("expected_units") or []]
            conclusion = text[-700:]
            found = list(dict.fromkeys(_UNIT_RE.findall(conclusion)))
            passed = bool(found) and (not expected or bool(set(found) & set(expected)))
            check.update(
                status="passed" if passed else "failed",
                expected_units=expected,
                found_units=found,
                reason="" if passed else "最终结论缺少题目要求的单位或使用了不同单位",
            )
        elif kind == "numeric":
            numbers = [value.strip() for value in _NUMBER_RE.findall(text)]
            if answer_policy == "method_only" and not numbers:
                check.update(status="degraded", reason="用户选择只讲方法，未提交数值答案")
            elif not numbers:
                check.update(status="failed", reason="问题要求数值结果，但回答中未找到数值")
            elif answer_policy == "method_only":
                passed = "未验证估算" in text or "未作为精确答案" in text
                check.update(status="degraded" if passed else "failed", reason="用户选择只讲方法，数值不得标为精确答案")
            elif _verified_math(tool_context_pack):
                check.update(status="passed", verification="deterministic_math_tool")
            else:
                evidence_numbers = set(_NUMBER_RE.findall(_evidence_text(evidence_items)))
                supported = any(value in evidence_numbers for value in numbers)
                check.update(
                    status="passed" if supported else "unverified",
                    reason="" if supported else "数值未经过确定性计算工具或补充证据交叉验证",
                )
        checks.append(check)

    failed = [item for item in checks if item.get("status") == "failed"]
    unverified = [item for item in checks if item.get("status") == "unverified"]
    degraded = [item for item in checks if item.get("status") == "degraded"]
    status = "failed" if failed else "unverified" if unverified else "degraded" if degraded else "passed"
    return {
        "status": status,
        "passed": status in {"passed", "degraded"},
        "checks": checks,
        "failures": [{"id": item["id"], "reason": item.get("reason", "")} for item in failed],
        "unverified": [{"id": item["id"], "reason": item.get("reason", "")} for item in unverified],
    }


def verification_notice(result: dict[str, Any]) -> str:
    if result.get("status") == "failed":
        labels = [str(item.get("id") or "") for item in result.get("failures") or []]
        return f"> 回答验收未通过：{', '.join(labels)}。本轮结果未标记为完整答案。"
    if result.get("status") == "unverified":
        return "> 数值核对：当前数值未通过确定性计算工具或独立证据验证，请将其视为未验证估算。"
    return ""
