"""Deterministic post-generation checks for learning answers.

These checks do not try to prove an arbitrary derivation correct.  They enforce
the parts the harness can know: requested sections are present, citations point
to this turn's evidence, and numeric conclusions disclose whether a deterministic
tool or supplied evidence verified them.
"""
from __future__ import annotations

import re
import json
import math
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


def _coverage_anchors(segment: str) -> list[str]:
    from graph.retrieval_node import _FOCUS_TERM_ALIASES
    if re.search(r"格式|码点|字符|Markdown|JSON|(?:不|禁止)使用|开头|前缀|后缀|有效数字|小数位|公式符号", segment, re.I):
        return []
    anchors = [a for a in _anchors(segment) if a in _FOCUS_TERM_ALIASES]
    # Short explicit subject nouns are presence obligations; directives about
    # style, precision or provenance are not objects of a textbook answer.
    subject = re.fullmatch(r"(?:说明|解释|写出|列出)\s*([\u4e00-\u9fff]{2,10}(?:误差|原因|定义|原函数))\s*[。；;]?", segment.strip())
    if subject:
        anchors.append(subject[1])
    return list(dict.fromkeys(anchors))


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
            "anchors": _coverage_anchors(segment),
            "required": True,
        })
    # Only known curriculum dimensions have lexical *coverage* probes. Free
    # natural language remains a semantic obligation, never a literal assertion.
    if not matches:
        segments = re.split(r"[、；;]|(?:以及|并且|并说明)", text)
        if len(segments) > 1:
            segments = [part for segment in segments for part in re.split(r"和|与", segment)]
            for index, segment in enumerate(segments):
                anchors = _coverage_anchors(segment)
                outputs.append({"id": f"item_{index + 1}", "label": segment[:80],
                                "kind": "question_part" if anchors else "semantic",
                                "anchors": anchors, "required": True})
    outputs.extend(_format_requirements(text))
    precision = re.search(r"(?:至少|不少于)\s*(\d+)\s*位有效数字", text)
    if precision:
        outputs.append({"id": "precision", "kind": "precision", "digits": int(precision[1]),
                        "label": "数值有效数字", "required": True})
    if re.search(r"(?:独立|工具).{0,8}(?:校验|核验|验证)", text):
        outputs.append({"id": "tool_verification", "kind": "tool_verification", "required": True})
    if re.search(r"闭式(?:结果|表达式)|精确表达式", text):
        outputs.append({"id": "closed_form", "kind": "closed_form", "required": True})
    if re.search(r"(?:推导|证明|步骤)", text):
        outputs.append({"id": "derivation_structure", "kind": "derivation", "required": True})
    if re.search(r"原函数|不定积分", text):
        outputs.append({"id": "antiderivative", "kind": "antiderivative", "required": True})
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
    if bool(re.search(r"公式(?!符号)|关系式|表达式|方程|推导|证明|列式", text)):
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
    # Numbered natural-language parts have the same boundary as unnumbered ones.
    for output in outputs:
        if output["kind"] == "question_part":
            if not output["anchors"]:
                output["kind"] = "semantic"
    return outputs


def _format_requirements(text: str) -> list[dict]:
    requirements = []
    count = re.search(r"(?:只输出|严格|恰好|仅输出)\s*([一二三四五六七八九十]|\d+)\s*行", text)
    if count:
        n = int(count[1]) if count[1].isdigit() else "一二三四五六七八九十".index(count[1]) + 1
        requirements.append({"id": "line_count", "kind": "format", "format": "lines", "value": n})
    length = re.search(r"(?:不超过|最多|上限为?)\s*(\d+)\s*(?:个Unicode码点|个字符|字)", text, re.I)
    if length:
        requirements.append({"id": "length", "kind": "format", "format": "length", "value": int(length[1]),
                             "exclude_newlines": "不含换行" in text})
    prefix = re.search(r"依次以(.+?)开头", text)
    if prefix:
        values = re.findall(r"[“\"]([^”\"]+)[”\"]", prefix[1])
        if values:
            requirements.append({"id": "prefixes", "kind": "format", "format": "prefixes", "value": values})
    if re.search(r"(?:只|仅).{0,5}(?:输出|返回).{0,5}JSON", text, re.I):
        requirements.append({"id": "json", "kind": "format", "format": "json"})
    if re.search(r"(?:用|使用|输出|返回)\s*Markdown\s*表格", text, re.I):
        requirements.append({"id": "table", "kind": "format", "format": "table"})
    if re.search(r"纯文本|不使用Markdown", text, re.I):
        requirements.append({"id": "plain_text", "kind": "format", "format": "plain"})
    literal = re.search(r"(?:必须包含|原样输出)[“\"]([^”\"]+)[”\"]", text)
    if literal:
        requirements.append({"id": "literal", "kind": "literal", "value": literal[1]})
    return requirements


def _check_format(text: str, output: dict) -> bool:
    fmt, value = output.get("format"), output.get("value")
    if fmt == "lines":
        return len(text.splitlines()) == value
    if fmt == "length":
        return len(text.replace("\n", "").replace("\r", "") if output.get("exclude_newlines") else text) <= value
    if fmt == "prefixes":
        lines = text.splitlines()
        return len(lines) == len(value) and all(line.startswith(prefix) for line, prefix in zip(lines, value))
    if fmt == "json":
        try:
            json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-JSON constant")))
            return True
        except (ValueError, TypeError):
            return False
    if fmt == "table":
        lines = text.splitlines()
        if len(lines) < 3:
            return False
        cells = [line.strip().strip("|").split("|") for line in lines]
        return len(cells[0]) >= 2 and all(len(row) == len(cells[0]) for row in cells) and all(
            re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in cells[1])
    if fmt == "plain":
        return not bool(re.search(r"(?m)^\s*(?:[-*+] |\d+[.)] |#{1,6} |```)|\*\*", text))
    return False


def _requested_math(question: str) -> dict | None:
    from backend.services.tool_orchestration import _math_tool_call
    expected = _math_tool_call(question)
    if expected:
        return expected["args"]
    # A bounded conventional Unicode integral notation; unsupported notation
    # remains unknown. Never infer a request from the tool output itself.
    normalized = question.translate(str.maketrans({**dict(zip("₀₁₂₃₄₅₆₇₈₉", "0123456789")),
        **{char: "^" + str(index) for index, char in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")}}))
    # Superscript upper bound follows the lower bound, rather than a power.
    normalized = re.sub(r"∫(\d)\^(\d)", r"∫\1\2", normalized)
    match = re.search(r"∫([0-9])([0-9])\s*([A-Za-z0-9+*/^(). \-]+)\s*d([xyzt])", normalized)
    if match:
        expression = re.sub(r"\s+(?=[A-Za-z(])", "*", match[3].strip())
        return {"operation": "integrate", "expression": expression, "lower": match[1], "upper": match[2], "variable": match[4]}
    return None


def _same_expression(left: str, right: str) -> bool:
    from backend.tools.math_tools import parse_restricted_expression, RestrictedMathError
    try:
        return bool((parse_restricted_expression(left) - parse_restricted_expression(right)).simplify() == 0)
    except (RestrictedMathError, ValueError, TypeError):
        return False


def _bound_numeric_reference(question: str, pack: dict) -> tuple[float, list[str]] | None:
    requested = _requested_math(question)
    if not requested or requested["operation"] not in {"calculate", "integrate"}:
        return None
    if requested["operation"] == "integrate" and not all(k in requested for k in ("lower", "upper")):
        return None
    outputs = pack.get("outputs") or []
    for item in outputs:
        data, args = item.get("data") or {}, item.get("args") or {}
        if item.get("tool") != "symbolic_math" or not item.get("success") or data.get("assumptions"):
            continue
        if data.get("operation") != requested["operation"] or not _same_expression(data.get("expression", ""), requested["expression"]):
            continue
        if data.get("variable", "x") != requested.get("variable", "x") or any(
                not _same_expression(str(args.get(k, "")), requested[k]) for k in ("lower", "upper") if k in requested):
            continue
        for receipt in outputs:
            r = receipt.get("args") or {}
            if receipt.get("tool") != "verify_math_result" or not receipt.get("success") or receipt.get("verification", {}).get("passed") is not True or r.get("assumptions"):
                continue
            vr = data.get("verification_request") or {}
            # Bind the actual verification to operation, source, limits and result;
            # equivalent candidate spellings are allowed, unrelated success is not.
            if not vr or r.get("kind") != vr.get("kind"):
                continue
            keys = [k for k in vr if k not in {"assumptions", "candidate", "right"}]
            if any(r.get(k) != vr[k] for k in keys):
                continue
            result_key = "candidate" if "candidate" in vr else "right"
            if not _same_expression(str(r.get(result_key, "")), str(vr.get(result_key, ""))):
                continue
            numeric = (data.get("result") or {}).get("numeric")
            if isinstance(numeric, (int, float)) and math.isfinite(numeric):
                return float(numeric), ["symbolic_math", "verify_math_result", str(r.get("kind"))]
    return None


def _numeric_candidates(text: str, question: str = "") -> list[str]:
    # Read decimal result fields, not arbitrary intermediate quantities. The
    # supported surfaces are scalar formula outputs, named task results and
    # explicit numeric conclusion labels. Ambiguous prose stays unverified.
    number = r"[-+]?\d+\.\d+(?:[eE][-+]?\d+)?"
    target = re.search(r"\b([A-Za-z])\s*=", question)
    values = []
    for formula in _FORMULA_RE.findall(text):
        value = _compact_formula(formula).replace(r"\boxed{", "").replace("}", "")
        value = value.replace(r"\ldots", "").rstrip(".")
        if re.fullmatch(number, value):
            values.append(value)
        elif target:
            match = re.fullmatch(re.escape(target[1]) + "=(" + number + ")", value)
            if match:
                values.append(match[1])
    values.extend(re.findall(r"(?:最终结果|结果|数值)(?:为|是|：|:)\s*(" + number + ")", text))
    if re.fullmatch(number + r"[。.]?", text.strip()):
        values.append(text.strip().rstrip("。"))
    return list(dict.fromkeys(values))


def _precision_status(text: str, question: str, pack: dict, digits: int) -> tuple[str, dict]:
    reference = _bound_numeric_reference(question, pack)
    candidates = _numeric_candidates(text, question)
    if not candidates:
        return "failed", {"reason": "缺少可检查的十进制数值输出", "evidence": []}
    if not reference:
        return "unverified", {"reason": "数值未绑定本题及成功的独立数学收据", "evidence": []}
    expected, evidence = reference
    details = []
    for raw in candidates:
        mantissa = raw.lower().split("e")[0].lstrip("+-").replace(".", "").lstrip("0")
        n = len(mantissa)
        exponent = math.floor(math.log10(abs(expected))) if expected else 0
        tolerance = .5 * 10 ** (exponent - min(n, digits) + 1)
        details.append({"value": raw, "digits": n, "matches": abs(float(raw) - expected) <= tolerance + abs(expected)*1e-14})
    passed = any(d["digits"] >= digits and d["matches"] for d in details) and all(d["matches"] for d in details)
    return "passed" if passed else "failed", {"reason": "与本题独立核验结果及舍入精度比较" if passed else "数值错误或有效数字不足",
                                               "evidence": evidence, "candidates": details}


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



def _math_text(value: str) -> str:
    return re.sub(r"\s", "", str(value)).replace("**", "^").replace("×", "*").replace("÷", "/").replace("−", "-")


def _verified_math_conclusion(answer: str, question: str, pack: dict) -> bool:
    from backend.services.tool_orchestration import _math_tool_call
    expected = _math_tool_call(question)
    if not expected:
        return False  # Unsupported answer bindings stay unverified, never guess.
    requested = expected["args"]
    outputs = pack.get("outputs") or []
    for item in outputs:
        data = item.get("data") or {}
        if item.get("tool") != "symbolic_math" or not item.get("success") or data.get("assumptions"):
            continue
        if data.get("operation") != requested.get("operation") or _math_text(data.get("expression", "")) != _math_text(requested.get("expression", "")):
            continue
        if data.get("variable", "x") != requested.get("variable", "x") or data.get("status") != "computed":
            continue
        actual = item.get("args") or {}
        if any(_math_text(actual.get(key, "")) != _math_text(requested[key]) for key in ("lower", "upper", "right") if key in requested):
            continue
        request = data.get("verification_request") or {}
        verified = any(receipt.get("tool") == "verify_math_result" and receipt.get("success")
            and receipt.get("verification", {}).get("passed") is True
            and (receipt.get("args") or {}).get("kind") != "steps"
            and all((receipt.get("args") or {}).get(key) == value for key, value in request.items()) for receipt in outputs)
        if not verified:
            continue
        if requested["operation"] == "calculate":
            return _verified_numeric_conclusion(answer, question, pack)
        if requested["operation"] == "solve":
            continue  # Substitution checks do not prove solution-set completeness.
        expected_latex = _compact_formula((data.get("result") or {}).get("latex", ""))
        formulas = _FORMULA_RE.findall(answer)
        if expected_latex and any(_compact_formula(formula).split("=")[-1] == expected_latex for formula in formulas):
            return True
    return False


def _verified_numeric_conclusion(answer: str, question: str, pack: dict) -> bool:
    # A successful receipt alone says nothing about this question. Consume only
    # closed expressions explicitly requested here and their matching verifier.
    outputs = pack.get("outputs") or []
    for item in outputs:
        data = item.get("data") or {}
        if item.get("tool") != "symbolic_math" or not item.get("success") or data.get("operation") != "calculate":
            continue
        expression = str(data.get("expression") or "")
        if not expression or not re.search(r"(?<![A-Za-z0-9.+*/^\-])" + re.escape(_math_text(expression)) + r"(?![A-Za-z0-9.+*/^\-])", _math_text(question)):
            continue
        request = data.get("verification_request") or {}
        bound = any(receipt.get("tool") == "verify_math_result" and receipt.get("success")
                    and receipt.get("verification", {}).get("passed") is True
                    and (receipt.get("args") or {}).get("kind") != "steps"
                    and all((receipt.get("args") or {}).get(key) == value for key, value in request.items()) for receipt in outputs)
        if not bound:
            continue
        conclusion = re.split(r"[。\n]", answer.strip(" 。\n"))[-1]
        numbers = _NUMBER_RE.findall(conclusion)
        numeric = (data.get("result") or {}).get("numeric")
        if len(numbers) == 1 and isinstance(numeric, (int, float)):
            raw = re.match(r"[-+]?\d+(?:\.\d+)?", numbers[0].strip())
            if raw:
                from fractions import Fraction
                exact = str((data.get("result") or {}).get("exact") or "")
                try:
                    if len(raw[0]) <= 320 and len(exact) <= 700 and Fraction(raw[0]) == Fraction(exact):
                        return True
                except (ValueError, ZeroDivisionError, OverflowError):
                    pass
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
    outputs = list(required_outputs or [])
    # Old checkpoints may carry the former natural-language anchor contract.
    # Reclassify those probes at read time without rewriting persisted tasks.
    structural_kinds = {"format", "literal", "precision", "tool_verification", "antiderivative", "closed_form", "derivation"}
    existing_ids = {item.get("id") for item in outputs}
    if question:
        outputs.extend(item for item in derive_required_outputs(question) if item["kind"] in structural_kinds and item["id"] not in existing_ids)
    for output in outputs:
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
            from graph.retrieval_node import _FOCUS_TERM_ALIASES
            anchors = [str(item) for item in output.get("anchors") or [] if
                       str(item) in _FOCUS_TERM_ALIASES or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,15}", str(item)) or
                       re.fullmatch(r"[\u4e00-\u9fff]{2,10}(?:误差|原因|定义|原函数)", str(item))]
            matched = [item for item in anchors if any(alias in text for alias in _FOCUS_TERM_ALIASES.get(item, (item,)))]
            covered = bool(anchors) and len(matched) == len(anchors)
            check.update(status="unverified" if covered or not anchors else "failed", matched=matched,
                         evidence=["answer coverage probe"],
                         reason="仅确认对象出现，内容完整性与正确性未核验" if covered or not anchors else "未找到该分项的核心对象")
        elif kind == "semantic":
            check.update(status="unverified", evidence=[], reason="自然语言内容义务保留，无法确定性核验语义完整性")
        elif kind == "literal":
            ok = bool(output.get("value")) and output["value"] in text
            check.update(status="passed" if ok else "failed", evidence=["answer literal"], reason="明确文本要求匹配" if ok else "缺少明确要求的文本")
        elif kind == "format":
            ok = _check_format(text, output)
            check.update(status="passed" if ok else "failed", evidence=["answer format"], reason=f"检查 {output.get('format')}，约束 {output.get('value')}")
        elif kind == "precision":
            status, details = _precision_status(text, question, tool_context_pack or {}, min(100, max(1, int(output.get("digits", 6)))))
            check.update(status=status, **details)
        elif kind == "tool_verification":
            reference = _bound_numeric_reference(question, tool_context_pack or {})
            check.update(status="passed" if reference else "unverified", evidence=reference[1] if reference else [],
                         reason="本题计算与独立核验收据已绑定" if reference else "没有可绑定本题结论的独立核验收据")
        elif kind == "closed_form":
            candidates = [_compact_formula(formula).split("=")[-1] for formula in _FORMULA_RE.findall(text)]
            present = any(not re.search(r"\\int|\bdx\b", value) and re.search(r"\\(?:frac|ln|log|sqrt)|[A-Za-z].*[+*/^]|[+*/^].*[A-Za-z]", value)
                          for value in candidates)
            check.update(status="unverified" if present else "failed", evidence=["answer symbolic result structure"],
                         reason="闭式结构存在，表达式等价性尚未绑定核验" if present else "明确要求闭式结果，但没有符号结果结构")
        elif kind == "derivation":
            formulas = _FORMULA_RE.findall(text)
            present = len(formulas) >= 2 and sum(formula.count("=") for formula in formulas) >= 2
            check.update(status="unverified" if present else "failed", evidence=["answer formula sequence"],
                         reason="推导关系存在，教学完整性与逐步正确性未核验" if present else "明确要求推导，但缺少可复现的公式关系序列")
        elif kind == "antiderivative":
            present = bool(re.search(r"[+＋]\s*C\b", text)) and bool(_FORMULA_RE.search(text))
            check.update(status="unverified" if present else "failed", evidence=["answer structure"],
                         reason="原函数结构存在，尚未逐式求导核验" if present else "缺少完整原函数及积分常数")
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
        elif kind == "math_support":
            supported = _verified_math_conclusion(text, question, tool_context_pack or {})
            check.update(status="passed" if supported else "unverified", reason="" if supported else "数学结论缺少与题目、运算及结果绑定的核验依据")
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
        else:
            check.update(status="unverified", reason="不支持的验证项类型", evidence=[])
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
        return f"> 回答验收未通过：{', '.join(labels)}。这些结论仍需核对。"
    if result.get("status") == "unverified":
        return "> 回答核对：部分公式或数值尚无确定性核验依据，请核对后使用。"
    return ""
