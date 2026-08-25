"""Bounded read-only tool orchestration shared by chat and the compatibility API."""
from __future__ import annotations

import json
import queue
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from backend.tools.registry import ToolContext, ToolResult, get_tool_registry
from backend.services.pending_actions import get_pending_action_store


DEFAULT_TOOL_TIMEOUT_SECONDS = 8.0
DEFAULT_TOTAL_TIMEOUT_SECONDS = 18.0
TOOL_CONTEXT_CHAR_BUDGET = 9000

_TOOL_REQUIRED_OUTPUTS: dict[str, list[dict[str, str]]] = {
    "symbolic_math": [{"key": "computed_result", "path": "data.result"}],
    "verify_math_result": [{"key": "verified_math", "path": "verification.passed"}],
    "search_textbook": [{"key": "textbook_evidence", "path": "data.snippets"}],
    "find_textbook_examples": [{"key": "textbook_examples", "path": "data.examples"}],
    "search_concepts": [{"key": "concept_matches", "path": "data.concepts"}],
    "search_exercises": [{"key": "exercise_matches", "path": "data.exercises"}],
    "propose_add_mistake": [{"key": "confirmable_action", "path": "pending_action.action_id"}],
    "propose_concept_review": [{"key": "confirmable_action", "path": "pending_action.action_id"}],
    "propose_practice_session": [{"key": "confirmable_action", "path": "pending_action.action_id"}],
}


def _required_outputs(tool: str) -> list[dict[str, str]]:
    return [dict(item) for item in _TOOL_REQUIRED_OUTPUTS.get(tool, [{"key": "successful_result", "path": "success"}])]


def _path_value(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _validate_required_outputs(result: dict[str, Any], requirements: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    satisfied: list[str] = []
    missing: list[str] = []
    for requirement in requirements:
        key = str(requirement.get("key") or requirement.get("path") or "output")
        value = _path_value(result, str(requirement.get("path") or ""))
        valid = value is True or (value not in (None, "", [], {}))
        (satisfied if valid else missing).append(key)
    return satisfied, missing


@dataclass(frozen=True)
class ToolOrchestrationRequest:
    question: str
    book_name: str = ""
    subject: str = ""
    conversation_id: str = ""
    max_tools: int = 6
    include_textbook_tool: bool = False
    learning_task_id: str = ""
    max_followup_rounds: int = 1


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term.lower() in text for term in terms)


def _clean_math_expression(value: str) -> str:
    text = str(value or "").strip().strip("。；;，,")
    text = text.replace("$", "").replace("\\(", "").replace("\\)", "")
    return " ".join(text.split())


def _math_tool_call(question: str) -> dict[str, Any] | None:
    compact = " ".join(str(question or "").strip().split())
    if not compact:
        return None

    solve = re.search(r"(?:解|求解)方程\s*([^=。；]+)=([^。；]+)", compact, re.I)
    if solve:
        left, right = _clean_math_expression(solve.group(1)), _clean_math_expression(solve.group(2))
        variable_match = re.search(r"[xyzt]", f"{left}{right}")
        return {"tool": "symbolic_math", "args": {
            "operation": "solve", "expression": left, "right": right,
            "variable": variable_match.group(0) if variable_match else "x",
        }}

    definite = re.search(
        r"(?:求|计算)\s*(.+?)\s*在\s*([xyzt])\s*=\s*([^\s，,]+)\s*(?:到|至)\s*([^\s。；,，]+)\s*的定积分",
        compact, re.I,
    )
    if definite:
        return {"tool": "symbolic_math", "args": {
            "operation": "integrate", "expression": _clean_math_expression(definite.group(1)),
            "variable": definite.group(2), "lower": definite.group(3), "upper": definite.group(4),
        }}

    derivative = re.search(
        r"(?:求|计算)(?:函数)?\s*(.+?)\s*(?:关于\s*([xyzt])\s*)?的(?:一阶)?导数",
        compact, re.I,
    )
    if derivative:
        expression = _clean_math_expression(derivative.group(1))
        variable = derivative.group(2) or (re.search(r"[xyzt]", expression).group(0) if re.search(r"[xyzt]", expression) else "x")
        return {"tool": "symbolic_math", "args": {
            "operation": "differentiate", "expression": expression, "variable": variable,
        }}

    integral = re.search(
        r"(?:求|计算)\s*(.+?)\s*(?:关于\s*([xyzt])\s*)?的(?:不定)?积分",
        compact, re.I,
    )
    if integral:
        expression = _clean_math_expression(integral.group(1))
        variable = integral.group(2) or (re.search(r"[xyzt]", expression).group(0) if re.search(r"[xyzt]", expression) else "x")
        return {"tool": "symbolic_math", "args": {
            "operation": "integrate", "expression": expression, "variable": variable,
        }}

    numeric = re.search(r"(?:计算|算出|求值)\s*([0-9pie\.\+\-\*/\^×÷（）()\s]+)$", compact, re.I)
    if numeric and re.search(r"\d", numeric.group(1)):
        return {"tool": "symbolic_math", "args": {
            "operation": "calculate", "expression": _clean_math_expression(numeric.group(1)),
        }}
    return None


def select_tool_calls(req: ToolOrchestrationRequest) -> list[dict[str, Any]]:
    question = req.question.strip()
    lowered = question.lower()
    calls: list[dict[str, Any]] = []

    math_call = _math_tool_call(question)
    if math_call:
        calls.append(math_call)

    review_terms = ["复习", "到期", "薄弱", "弱点", "错题", "错因", "掌握", "review", "mistake", "weak"]
    add_terms = ["加入错题", "添加错题", "记到错题", "收进错题", "add mistake"]
    concept_terms = ["概念", "公式", "定义", "定理", "知识点", "concept", "formula"]
    example_terms = ["例题", "教材例子", "典型例", "example"]
    exercise_terms = ["习题", "练习题", "做题", "抽题", "题库", "exercise", "practice question"]
    practice_terms = ["开始练习", "安排练习", "练几道", "做几道", "组一套", "practice session"]
    progress_terms = ["最近进度", "学习进度", "最近学了", "学习记录", "本周学习", "recent progress"]

    wants_add_mistake = _contains_any(lowered, add_terms)
    wants_review = bool(req.book_name) and not wants_add_mistake and _contains_any(lowered, review_terms)
    wants_progress = bool(req.book_name) and _contains_any(lowered, progress_terms)
    wants_examples = bool(req.book_name) and _contains_any(lowered, example_terms)
    wants_exercises = bool(req.book_name) and _contains_any(lowered, exercise_terms + practice_terms)
    wants_practice = bool(req.book_name) and _contains_any(lowered, practice_terms)
    wants_concepts = bool(req.book_name) and _contains_any(lowered, concept_terms)

    if wants_review:
        calls.extend([
            {"tool": "build_review_plan", "args": {"limit": 8}},
            {"tool": "get_weak_concepts", "args": {"limit": 8}},
        ])
    if wants_progress:
        calls.append({"tool": "get_recent_progress", "args": {"days": 7, "limit": 12}})
    if wants_examples and req.include_textbook_tool:
        calls.append({"tool": "find_textbook_examples", "args": {"query": question, "limit": 5}})
    if wants_exercises:
        calls.append({"tool": "search_exercises", "args": {"query": question, "limit": 8}})
    if wants_practice:
        calls.append({"tool": "propose_practice_session", "args": {"query": question, "limit": 5}})
    if wants_concepts and req.include_textbook_tool:
        calls.append({"tool": "search_concepts", "args": {"query": question, "limit": 5}})

    specialized = bool(math_call or wants_review or wants_progress or wants_examples or wants_exercises or wants_practice)
    if req.include_textbook_tool and req.book_name and (wants_concepts or not specialized):
        calls.append({"tool": "search_textbook", "args": {"query": question, "limit": 5}})
        if not any(call["tool"] == "search_concepts" for call in calls):
            calls.append({"tool": "search_concepts", "args": {"query": question, "limit": 3}})
    if wants_add_mistake:
        calls.append({"tool": "propose_add_mistake", "args": {"question_text": question, "subject": req.subject}})

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for call in calls:
        key = (call["tool"], json.dumps(call.get("args") or {}, ensure_ascii=False, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(call)
        if len(deduped) >= max(1, min(req.max_tools, 10)):
            break
    return deduped


def _run_bounded(action, timeout_seconds: float) -> dict[str, Any]:
    started = time.perf_counter()
    result_queue: queue.Queue = queue.Queue(maxsize=1)

    def execute() -> None:
        try:
            result_queue.put(("complete", action(), ""))
        except Exception as exc:  # pragma: no cover - registry normally contains handler errors
            result_queue.put(("error", None, str(exc)))

    threading.Thread(target=execute, name="tool-orchestration-call", daemon=True).start()
    try:
        status, value, message = result_queue.get(timeout=max(0.001, timeout_seconds))
    except queue.Empty:
        status, value, message = "timeout", None, f"timed out after {timeout_seconds:.1f}s"
    return {
        "status": status, "value": value, "message": message,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }


def _compact_result(item: dict[str, Any]) -> dict[str, Any]:
    result = item.get("result") or {}
    data = result.get("data")
    encoded = json.dumps(data, ensure_ascii=False, default=str)
    if len(encoded) > 3500:
        data = {"summary": encoded[:3500], "truncated": True}
    return {
        "tool": item.get("tool"), "success": bool(result.get("success")),
        "message": str(result.get("message") or "")[:300], "data": data,
        "verification": result.get("verification") or {},
        "warnings": list(result.get("warnings") or [])[:5],
        "pending_action": result.get("pending_action"),
        "required_outputs": list(item.get("required_outputs") or []),
        "satisfied_required_outputs": list(item.get("satisfied_required_outputs") or []),
        "missing_required_outputs": list(item.get("missing_required_outputs") or []),
    }


def build_tool_context_pack(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    compact = [_compact_result(item) for item in outputs]
    text = json.dumps(compact, ensure_ascii=False, indent=2, default=str)
    if len(text) > TOOL_CONTEXT_CHAR_BUDGET:
        text = text[:TOOL_CONTEXT_CHAR_BUDGET] + "\n[tool context truncated]"
    successful = [item for item in compact if item["success"]]
    missing_required = [
        {"tool": item["tool"], "outputs": item["missing_required_outputs"]}
        for item in compact if item["missing_required_outputs"]
    ]
    tool_names = [str(item.get("tool") or "") for item in compact]
    state_only = bool(tool_names) and all(name in {
        "build_review_plan", "get_weak_concepts", "get_recent_progress",
        "search_exercises", "propose_practice_session", "propose_add_mistake",
    } for name in tool_names)
    return {
        "text": text,
        "char_count": len(text),
        "tool_count": len(compact),
        "successful_tool_count": len(successful),
        "selected_tools": tool_names,
        "sufficient": bool(successful) and not missing_required,
        "missing_required_outputs": missing_required,
        "skip_textbook_retrieval": state_only and bool(successful) and not missing_required,
        "outputs": compact,
    }


def execute_read_only_tools(
    req: ToolOrchestrationRequest,
    *,
    total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SECONDS,
    per_tool_timeout_seconds: float | None = None,
    registry=None,
) -> dict[str, Any]:
    started = time.perf_counter()
    registry = registry or get_tool_registry()
    context = ToolContext(req.book_name, req.subject, req.conversation_id)
    selected = select_tool_calls(req)
    outputs: list[dict[str, Any]] = []
    followup_rounds = 0

    index = 0
    while index < len(selected) and len(outputs) < max(1, min(req.max_tools, 10)):
        call = selected[index]
        index += 1
        remaining = total_timeout_seconds - (time.perf_counter() - started)
        spec = registry.get(call["tool"]) if hasattr(registry, "get") else None
        configured_timeout = (
            float(per_tool_timeout_seconds)
            if per_tool_timeout_seconds is not None
            else float((getattr(spec, "timeout_seconds", None) or DEFAULT_TOOL_TIMEOUT_SECONDS))
        )
        timeout = min(configured_timeout, max(0.0, remaining))
        outcome = _run_bounded(
            lambda current=call: registry.call(current["tool"], current.get("args") or {}, context, allow_write=False),
            timeout,
        ) if timeout > 0 else {"status": "timeout", "value": None, "message": "tool budget exhausted", "elapsed_ms": 0}
        result = outcome["value"] if outcome["status"] == "complete" else ToolResult(False, message=outcome["message"])
        result_dict = result.to_dict()
        pending_action = result_dict.get("pending_action")
        if result.success and isinstance(pending_action, dict):
            result_dict["pending_action"] = get_pending_action_store().create(
                pending_action,
                context={
                    "book_name": req.book_name or "default",
                    "subject": req.subject,
                    "conversation_id": req.conversation_id,
                    "learning_task_id": req.learning_task_id,
                },
            )
        requirements = _required_outputs(call["tool"])
        satisfied, missing = _validate_required_outputs(result_dict, requirements)
        outputs.append({
            "tool": call["tool"], "args": call.get("args") or {}, "result": result_dict,
            "required_outputs": requirements,
            "satisfied_required_outputs": satisfied,
            "missing_required_outputs": missing,
            "timing": {"status": outcome["status"], "elapsed_ms": outcome["elapsed_ms"], "timeout_seconds": round(timeout, 3)},
        })

        verification_request = (result.data or {}).get("verification_request") if isinstance(result.data, dict) else None
        if (
            result.success and verification_request and len(selected) < req.max_tools
            and followup_rounds < max(0, min(req.max_followup_rounds, 1))
        ):
            verification_call = {"tool": "verify_math_result", "args": verification_request}
            selected.insert(index, verification_call)
            followup_rounds += 1

    pack = build_tool_context_pack(outputs)
    return {
        "selected_tools": selected[:len(outputs)],
        "tool_outputs": outputs,
        "tool_context_pack": pack,
        "execution_trace": {
            "total_elapsed_ms": round((time.perf_counter() - started) * 1000),
            "budget_seconds": total_timeout_seconds,
            "followup_rounds": followup_rounds,
            "followup_policy": "required_output_gap_max_one_round",
            "tools": [
                {"tool": item["tool"], "success": bool(item["result"].get("success")), **item["timing"]}
                for item in outputs
            ],
        },
    }
