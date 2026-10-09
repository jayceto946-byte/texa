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
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.])[-+]?\d+(?:\.\d+)?(?:\s*(?:°C|℃|%|V|mV|A|mA|Ω|Pa|kPa|MPa|Hz|mm|cm|m|s))?")
_UNIT_RE = re.compile(r"(?<![A-Za-z])(?:°C|℃|K|mV|V|mA|A|kΩ|MΩ|Ω|kPa|MPa|Pa|kHz|MHz|Hz|mm|cm|km|m|ms|s)(?![A-Za-z])")
_FORMULA_RE = re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]|\\\(.*?\\\)|\$[^$\n]+\$", re.S)
_PART_RE = re.compile(r"(?:第\s*(\d+)\s*问|[（(](\d+)[）)])")
_STOP_ANCHORS = {
    "请", "求", "计算", "说明", "分析", "回答", "问题", "分别", "根据", "给出", "为什么",
    "是多少", "是什么", "怎么", "如何", "下列", "其中", "以及", "并且", "最终", "结果",
}


def _anchors(text: str) -> list[str]:
    normalized = re.sub(r"^(?:请|写出|给出|说明|分析|计算|求出?|回答|判断)+", "", str(text or "").strip())
    from graph.retrieval_node import _FOCUS_TERM_ALIASES
    dimensions = [canonical for canonical, aliases in _FOCUS_TERM_ALIASES.items()
                  if any(alias in normalized for alias in aliases)]
    dimensions = [value for value in dimensions if not any(value != other and value in other for other in dimensions)]
    if dimensions:
        return dimensions
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
    # Unnumbered requests still have independent deliverables.
    if not matches:
        segments = re.split(r"[、；;]|(?:以及|并且|并说明)", text)
        if len(segments) > 1:
            segments = [part for segment in segments for part in re.split(r"和|与", segment)]
            for index, segment in enumerate(segments):
                anchors = _anchors(segment.strip(" ，,。"))
                if anchors:
                    outputs.append({"id": f"item_{index + 1}", "label": segment[:80],
                                    "kind": "question_part", "anchors": anchors, "required": True})
    numeric_requested = intent == "calculation" or bool(re.search(
        r"计算|求值|数值|多少|结果为|反查|求出|最终.{0,8}(?:温度|电势|电压|电流|概率)", text,
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
    if answer_mode in {"textbook_grounded", "visual_grounded"}:
        outputs.append({
            "id": "citations", "label": "教材结论的本轮来源", "kind": "citation", "required": True,
        })
    elif answer_mode in {"subject_general", "global_general"}:
        outputs.append({
            "id": "answer_mode", "label": "通用模式的回答范围", "kind": "general_answer", "required": True,
        })
    return outputs


def _balanced_formula_delimiters(text: str) -> bool:
    return text.count("$$") % 2 == 0 and len(re.findall(r"(?<!\\)\$", text.replace("$$", ""))) % 2 == 0 and text.count("\\[") == text.count("\\]") and text.count("\\(") == text.count("\\)")


def _source_texts(
    sources: list[dict[str, Any]] | None,
    evidence_items: list[dict[str, Any]] | None,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in [*(sources or []), *(evidence_items or [])]:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id") or item.get("evidence_id") or "").upper()
        content = str(item.get("text") or item.get("content") or item.get("problem_text") or item.get("caption") or "")
        if source_id and content:
            result[source_id] = content
    return result


def _citation_semantically_supported(answer: str, source_id: str, source_text: str, position: int | None = None) -> bool:
    marker = f"[[cite:{source_id}]]"
    position = answer.upper().find(marker.upper()) if position is None else position
    prefix = answer[:position] if position >= 0 else ""
    # A contiguous citation group refers to one claim. Earlier markers in the
    # group are annotations, not sentence boundaries. Do not cross newlines or
    # remove an intervening claim: each source must still support that claim.
    prefix = re.sub(r"(?:[ \t]*\[\[cite:E[\w-]+\]\])+[ \t]*$", "", prefix, flags=re.I)
    claim = prefix[-220:]
    claim = re.split(r"[。！？\n]|\[\[cite:E[\w-]+\]\]", claim.rstrip(" 。！？\n"))[-1]
    def terms(value: str) -> set[str]:
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", value))
        grams = {chinese[index:index + 2] for index in range(max(0, len(chinese) - 1))}
        return grams | {item.lower() for item in re.findall(r"[A-Za-z]{3,}", value)}

    claim_terms = terms(claim) - _STOP_ANCHORS
    source_terms = terms(source_text)
    if len(claim_terms & source_terms) >= 2:
        return True

    if _FORMULA_RE.search(source_text) and _FORMULA_RE.search(claim):
        return _formula_support(claim, source_text) == "passed"
    return False


def _compact_formula(value: str) -> str:
    value = re.sub(r"\\tag\{[^}]*\}", "", value)
    value = re.sub(r"[\s$]", "", value).replace(r"\(", "").replace(r"\)", "").replace(r"\[", "").replace(r"\]", "").replace(r"\mathrm", "").replace(r"\left", "").replace(r"\right", "")
    if not re.search(r"\\(?:frac|dfrac|sqrt|begin|end)", value):
        # Atomic braces are formatting; compound groups and command arguments
        # carry mathematical structure and must remain distinct.
        while re.search(r"\{[A-Za-z0-9]+\}", value):
            value = re.sub(r"\{([A-Za-z0-9]+)\}", r"\1", value)
    return value


def _formula_support(answer: str, evidence: str) -> str:
    """Exact formulas or bounded elementary equalities; other math stays unverified."""
    formulas = _FORMULA_RE.findall(answer)
    source_formulas = _FORMULA_RE.findall(evidence)
    if not formulas or not source_formulas:
        return "unverified"
    statuses = []
    for formula in formulas:
        compact = _compact_formula(formula)
        if any(compact == _compact_formula(source) for source in source_formulas):
            statuses.append("passed")
            continue
        comparable = []
        # Only scalar, one-letter equalities. Do not send arbitrary LaTeX to a parser.
        if re.fullmatch(r"[A-Za-z0-9=+*/().^\-]+", compact) and compact.count("=") == 1:
            for source in source_formulas:
                other = _compact_formula(source)
                if (not re.fullmatch(r"[A-Za-z0-9=+*/().^\-]+", other) or other.count("=") != 1
                        or set(re.findall(r"[A-Za-z]", compact)) != set(re.findall(r"[A-Za-z]", other))):
                    continue
                from backend.tools.math_tools import parse_restricted_expression, RestrictedMathError
                import sympy as sp
                names = sorted(set(re.findall(r"[A-Za-z]", compact)))
                if len(names) > 7:
                    continue
                mapping = dict(zip(names, ("x", "y", "z", "t", "a", "b", "c")))
                def residual(value):
                    left, right = value.split("=")
                    def parse(term):
                        term = re.sub(r"(?<=[A-Za-z])(?=[A-Za-z(])", "*", term)
                        term = re.sub(r"[A-Za-z]", lambda m: mapping[m[0]], term)
                        return parse_restricted_expression(term)
                    return parse(left) - parse(right)
                try:
                    actual, expected = residual(compact), residual(other)
                    ratio = sp.cancel(actual / expected)
                    comparable.append(bool(ratio.is_number and ratio.is_finite and ratio != 0))
                except (RestrictedMathError, ValueError, TypeError, ZeroDivisionError):
                    continue
        statuses.append("passed" if any(comparable) else "failed" if comparable else "unverified")
    return "failed" if "failed" in statuses else "unverified" if "unverified" in statuses else "passed"



def _verified_numeric_conclusion(answer: str, question: str, pack: dict) -> bool:
    # A successful receipt alone says nothing about this question. Consume only
    # closed expressions explicitly requested here and their matching verifier.
    outputs = pack.get("outputs") or []
    for item in outputs:
        data = item.get("data") or {}
        if item.get("tool") != "symbolic_math" or not item.get("success") or data.get("operation") != "calculate":
            continue
        expression = str(data.get("expression") or "")
        if not expression or not re.search(r"(?<![A-Za-z0-9.+*/^\-])" + re.escape(re.sub(r"\s", "", expression)) + r"(?![A-Za-z0-9.+*/^\-])", re.sub(r"\s", "", question)):
            continue
        request = data.get("verification_request") or {}
        bound = any(receipt.get("tool") == "verify_math_result" and receipt.get("success")
                    and receipt.get("verification", {}).get("passed") is True
                    and receipt.get("args") == request for receipt in outputs)
        if not bound:
            continue
        conclusion = re.split(r"[。\n]", answer.strip(" 。\n"))[-1]
        numbers = _NUMBER_RE.findall(conclusion)
        numeric = (data.get("result") or {}).get("numeric")
        if len(numbers) == 1 and isinstance(numeric, (int, float)):
            raw = re.match(r"[-+]?\d+(?:\.\d+)?", numbers[0].strip())
            if raw and float(raw[0]) == numeric:
                return True
    return False


def verify_answer(
    answer: str,
    *,
    required_outputs: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    citation_trace: dict[str, Any] | None = None,
    tool_context_pack: dict[str, Any] | None = None,
    evidence_items: list[dict[str, Any]] | None = None,
    answer_policy: str = "exact",
    question: str = "",
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
        elif kind == "general_answer":
            # Detect the specific mode violation, not legitimate requests for
            # missing problem conditions or out-of-subject explanations.
            refusal = bool(re.search(
                r"(?:未提供|缺少|没有|不足|未检索到).{0,15}教材(?:证据|内容).{0,45}(?:无法|不能)",
                text.split("\n\n", 1)[0],
            ))
            # A source caveat followed by a general explanation is allowed.
            if re.search(r"但(?:是)?|不过|一般(?:而言|来说)|通常", text):
                refusal = False
            check.update(status="failed" if refusal else "passed", reason="通用模式仍因缺少教材证据拒答" if refusal else "")
        elif kind == "question_part":
            anchors = [str(item) for item in output.get("anchors") or []]
            matched = [item for item in anchors if item and item in text]
            passed = not anchors or len(matched) == len(anchors)
            check.update(status="passed" if passed else "failed", matched=matched, reason="" if passed else "未找到该分项的核心对象")
        elif kind == "citation":
            valid_ids = {str(item.get("id") or "").upper() for item in (sources or []) if isinstance(item, dict)}
            cited_ids = {item.upper() for item in _CITATION_RE.findall(text)}
            invalid_removed = int((citation_trace or {}).get("invalid_ids_removed") or 0)
            if not valid_ids:
                check.update(status="failed", reason="本轮没有可引用的结构化来源")
            else:
                matched_ids = cited_ids & valid_ids
                source_texts = _source_texts(sources, evidence_items)
                unsupported = sorted({
                    match.group(1).upper() for match in _CITATION_RE.finditer(text)
                    if match.group(1).upper() in matched_ids and (
                        match.group(1).upper() not in source_texts or
                        not _citation_semantically_supported(text, match.group(1).upper(),
                                                            source_texts[match.group(1).upper()], match.start()))
                })
                passed = bool(matched_ids) and not (cited_ids - valid_ids) and invalid_removed == 0 and not unsupported
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
                status=_formula_support(text, "\n".join(_source_texts(sources, evidence_items).values())) if passed else "failed",
                structure_status="passed" if passed else "failed",
                formula_count=len(formulas),
                reason="公式结构完整；等价性仅在可核验范围内检查" if passed else "问题要求公式或推导关系，但回答缺少完整的 LaTeX 公式",
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
            else:
                verified = _verified_numeric_conclusion(text, question, tool_context_pack or {})
                check.update(status="passed" if verified else "unverified", reason="" if verified else "数值缺少与最终结论绑定的核验依据")
        checks.append(check)

    if _FORMULA_RE.search(text) and not any(item["id"] == "formula" for item in checks):
        math_status = _formula_support(text, "\n".join(_source_texts(sources, evidence_items).values()))
        checks.append({"id": "formula", "label": "回答公式的核验依据", "status": math_status,
                       "reason": "公式尚无等价性核验依据" if math_status == "unverified" else ""})
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
        labels_by_id = {"formula": "公式或推导关系未通过检查", "numeric": "数值未通过检查", "unit": "单位未通过检查", "required_outputs": "必要结论或步骤缺失", "citations": "引用未通过检查"}
        labels = [labels_by_id.get(str(item.get("id") or ""), str(item.get("reason") or "必要内容需要核对")) for item in result.get("failures") or []]
        return f"> 回答验收未通过：{', '.join(labels)}。本轮结果未标记为完整答案。"
    if result.get("status") == "unverified":
        return "> 回答核对：部分公式或数值尚无确定性核验依据，本轮结果未标记为完整答案。"
    return ""
