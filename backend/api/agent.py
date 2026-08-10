"""Controlled read-only agent API.

This is the first step toward tool calling: the backend chooses from a small
Tool Registry, executes only read-only/proposal tools, and returns evidence.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.tools.learning_tools import summarize_learning_evidence
from backend.tools.registry import ToolContext, ToolResult, get_tool_registry
from utils.thinking_filter import strip_thinking

router = APIRouter(prefix="/agent", tags=["controlled-agent"])
logger = logging.getLogger(__name__)

AGENT_TOOL_TIMEOUT_SECONDS = 8.0
AGENT_SYNTHESIS_TIMEOUT_SECONDS = 35.0
AGENT_TOTAL_TIMEOUT_SECONDS = 50.0


class ToolCallRequest(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    book_name: str = ""
    subject: str = ""
    conversation_id: str = ""
    allow_write: bool = False


class ReadOnlyAgentRequest(BaseModel):
    question: str
    book_name: str = ""
    subject: str = ""
    conversation_id: str = ""
    synthesize: bool = True
    max_tools: int = Field(default=6, ge=1, le=10)


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term.lower() in text for term in terms)


def _select_tool_calls(req: ReadOnlyAgentRequest) -> list[dict]:
    question = req.question.strip()
    lowered = question.lower()
    calls: list[dict] = []

    review_terms = ["复习", "到期", "薄弱", "弱点", "错题", "错因", "掌握", "review", "mistake", "weak"]
    add_terms = ["加入错题", "添加错题", "记到错题", "收进错题", "add mistake"]
    concept_terms = ["概念", "公式", "定义", "定理", "知识点", "concept", "formula"]
    example_terms = ["例题", "教材例子", "典型例", "example"]
    exercise_terms = ["习题", "练习题", "做题", "抽题", "题库", "exercise", "practice question"]
    practice_terms = ["开始练习", "安排练习", "练几道", "做几道", "组一套", "practice session"]
    progress_terms = ["最近进度", "学习进度", "最近学了", "学习记录", "本周学习", "recent progress"]

    wants_add_mistake = _contains_any(lowered, add_terms)
    wants_review = req.book_name and not wants_add_mistake and _contains_any(lowered, review_terms)
    wants_progress = req.book_name and _contains_any(lowered, progress_terms)
    wants_examples = req.book_name and _contains_any(lowered, example_terms)
    wants_exercises = req.book_name and _contains_any(lowered, exercise_terms + practice_terms)
    wants_practice = req.book_name and _contains_any(lowered, practice_terms)
    wants_concepts = req.book_name and _contains_any(lowered, concept_terms)

    if wants_review:
        calls.append({"tool": "build_review_plan", "args": {"limit": 8}})
        calls.append({"tool": "get_weak_concepts", "args": {"limit": 8}})

    if wants_progress:
        calls.append({"tool": "get_recent_progress", "args": {"days": 7, "limit": 12}})

    if wants_examples:
        calls.append({"tool": "find_textbook_examples", "args": {"query": question, "limit": 5}})

    if wants_exercises:
        calls.append({"tool": "search_exercises", "args": {"query": question, "limit": 8}})

    if wants_practice:
        calls.append({"tool": "propose_practice_session", "args": {"query": question, "limit": 5}})

    if wants_concepts:
        calls.append({"tool": "search_concepts", "args": {"query": question, "limit": 5}})

    specialized_intent = wants_review or wants_progress or wants_examples or wants_exercises or wants_practice
    if req.book_name and (wants_concepts or not specialized_intent):
        calls.append({"tool": "search_textbook", "args": {"query": question, "limit": 5}})
        if not any(call["tool"] == "search_concepts" for call in calls):
            calls.append({"tool": "search_concepts", "args": {"query": question, "limit": 3}})

    if wants_add_mistake:
        calls.append({"tool": "propose_add_mistake", "args": {"question_text": question, "subject": req.subject}})

    if not calls and req.book_name:
        calls.append({"tool": "search_textbook", "args": {"query": question, "limit": 5}})

    deduped = []
    seen = set()
    for call in calls:
        key = (call["tool"], json.dumps(call["args"], ensure_ascii=False, sort_keys=True))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(call)
        if len(deduped) >= req.max_tools:
            break
    return deduped


def _compact_tool_outputs(outputs: list[dict]) -> str:
    compact = []
    for item in outputs:
        result = item.get("result", {})
        data = result.get("data")
        if isinstance(data, dict) and "snippets" in data:
            data = {
                "book_name": data.get("book_name"),
                "snippets": [
                    {
                        "chapter": s.get("chapter"),
                        "chunk_id": s.get("chunk_id"),
                        "role": s.get("role"),
                        "text": str(s.get("text") or "")[:500],
                    }
                    for s in data.get("snippets", [])[:4]
                ],
            }
        elif isinstance(data, dict) and "examples" in data:
            data = {
                "book_name": data.get("book_name"),
                "query": data.get("query"),
                "examples": [
                    {
                        "chapter": item.get("chapter"),
                        "chunk_id": item.get("chunk_id"),
                        "section_title": item.get("section_title"),
                        "text": str(item.get("text") or "")[:700],
                    }
                    for item in data.get("examples", [])[:4]
                ],
            }
        elif isinstance(data, dict) and "exercises" in data:
            data = {
                "book_name": data.get("book_name"),
                "query": data.get("query"),
                "filters": data.get("filters"),
                "exercises": data.get("exercises", [])[:8],
                "solution_fields_omitted": data.get("solution_fields_omitted", True),
            }
        elif isinstance(data, dict) and "recent_events" in data:
            data = {
                "book_name": data.get("book_name"),
                "subject": data.get("subject"),
                "range_days": data.get("range_days"),
                "summary": data.get("summary"),
                "top_concepts": data.get("top_concepts", [])[:10],
                "recent_events": data.get("recent_events", [])[:8],
            }
        compact.append({
            "tool": item.get("tool"),
            "success": result.get("success"),
            "message": result.get("message"),
            "data": data,
            "pending_action": result.get("pending_action"),
        })
    return json.dumps(compact, ensure_ascii=False, indent=2)


def _run_bounded(action, timeout_seconds: float) -> dict[str, Any]:
    """Run blocking work behind a hard response deadline.

    The worker is daemonized because Python cannot safely cancel an arbitrary
    running function. Network-backed actions still receive their own shorter
    request timeout so they should normally stop with the response deadline.
    """
    started = time.perf_counter()
    result_queue: queue.Queue = queue.Queue(maxsize=1)

    def execute():
        try:
            result_queue.put(("complete", action(), ""))
        except Exception as exc:
            result_queue.put(("error", None, str(exc)))

    worker = threading.Thread(target=execute, name="agent-bounded-call", daemon=True)
    worker.start()
    try:
        status, value, message = result_queue.get(timeout=max(0.001, timeout_seconds))
    except queue.Empty:
        status, value, message = "timeout", None, f"timed out after {timeout_seconds:.1f}s"
    return {
        "status": status,
        "value": value,
        "message": message,
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
    }


def _synthesize_answer(
    req: ReadOnlyAgentRequest,
    outputs: list[dict],
    summary: dict,
    *,
    request_timeout_seconds: float,
) -> str:
    from config import get_llm

    prompt = f"""You are a controlled study assistant for postgraduate exam preparation.
Answer in Chinese using only the tool evidence below. If evidence is missing, say what is missing and give a cautious next step.
Do not claim that any pending action has been executed.

Question:
{req.question}

Context:
- book_name: {req.book_name or "(none)"}
- subject: {req.subject or "(none)"}

Tool evidence:
{_compact_tool_outputs(outputs)}

Evidence summary:
{json.dumps(summary, ensure_ascii=False)}

Requirements:
1. Keep the answer concise and actionable.
2. Mention textbook evidence, due reviews, weak points, or pending confirmations only when they appear in the tool evidence.
3. For review plans, give the next 3-5 actions.
4. Do not output thinking.
"""
    content = get_llm(
        temperature=0.3,
        request_timeout=max(1.0, request_timeout_seconds),
        max_retries=0,
    ).invoke(prompt).content
    return strip_thinking(content).strip()


@router.get("/tools")
def list_agent_tools(include_write: bool = False):
    registry = get_tool_registry()
    return {"success": True, "data": registry.list_tools(include_write=include_write)}


@router.post("/tools/call")
def call_agent_tool(req: ToolCallRequest):
    registry = get_tool_registry()
    context = ToolContext(book_name=req.book_name, subject=req.subject, conversation_id=req.conversation_id)
    result = registry.call(req.tool, req.args, context, allow_write=req.allow_write)
    return {"success": result.success, "tool": req.tool, "result": result.to_dict()}


@router.post("/read-only")
def run_read_only_agent(req: ReadOnlyAgentRequest):
    request_started = time.perf_counter()
    registry = get_tool_registry()
    context = ToolContext(book_name=req.book_name, subject=req.subject, conversation_id=req.conversation_id)
    selected = _select_tool_calls(req)

    outputs = []
    for call in selected:
        elapsed_seconds = time.perf_counter() - request_started
        remaining_seconds = AGENT_TOTAL_TIMEOUT_SECONDS - elapsed_seconds
        timeout_seconds = min(AGENT_TOOL_TIMEOUT_SECONDS, max(0.0, remaining_seconds))
        if timeout_seconds <= 0:
            outcome = {
                "status": "timeout",
                "value": None,
                "message": "agent request time budget exhausted before tool execution",
                "elapsed_ms": 0,
            }
        else:
            outcome = _run_bounded(
                lambda selected_call=call: registry.call(
                    selected_call["tool"],
                    selected_call.get("args", {}),
                    context,
                    allow_write=False,
                ),
                timeout_seconds,
            )
        result = outcome["value"] if outcome["status"] == "complete" else ToolResult(
            success=False,
            message=f"tool '{call['tool']}' {outcome['message']}",
        )
        outputs.append({
            "tool": call["tool"],
            "args": call.get("args", {}),
            "result": result.to_dict(),
            "timing": {
                "status": outcome["status"],
                "elapsed_ms": outcome["elapsed_ms"],
                "timeout_seconds": round(timeout_seconds, 3),
            },
        })

    summary = summarize_learning_evidence(outputs)
    synthesis = {
        "status": "skipped",
        "elapsed_ms": 0,
        "timeout_seconds": 0,
        "message": "",
    }
    answer = ""
    if req.synthesize:
        elapsed_seconds = time.perf_counter() - request_started
        remaining_seconds = AGENT_TOTAL_TIMEOUT_SECONDS - elapsed_seconds
        synthesis_timeout = min(AGENT_SYNTHESIS_TIMEOUT_SECONDS, max(0.0, remaining_seconds))
        if synthesis_timeout <= 0:
            synthesis_outcome = {
                "status": "timeout",
                "value": None,
                "message": "agent request time budget exhausted before synthesis",
                "elapsed_ms": 0,
            }
        else:
            synthesis_outcome = _run_bounded(
                lambda: _synthesize_answer(
                    req,
                    outputs,
                    summary,
                    request_timeout_seconds=synthesis_timeout,
                ),
                synthesis_timeout,
            )
        synthesis = {
            "status": synthesis_outcome["status"],
            "elapsed_ms": synthesis_outcome["elapsed_ms"],
            "timeout_seconds": round(synthesis_timeout, 3),
            "message": str(synthesis_outcome["message"] or "")[:300],
        }
        if synthesis_outcome["status"] == "complete":
            answer = str(synthesis_outcome["value"] or "")
        elif synthesis_outcome["status"] == "timeout":
            answer = "学习工具已读取完成，但模型总结超时。你可以重试，或展开下方证据查看已读取结果。"
        else:
            answer = "学习工具已读取完成，但模型总结失败。你可以重试，或展开下方证据查看已读取结果。"

    total_elapsed_ms = round((time.perf_counter() - request_started) * 1000)
    successful_tools = sum(1 for item in outputs if item["result"].get("success"))
    execution_trace = {
        "total_elapsed_ms": total_elapsed_ms,
        "budget_seconds": AGENT_TOTAL_TIMEOUT_SECONDS,
        "tools": [
            {
                "tool": item["tool"],
                "success": bool(item["result"].get("success")),
                **item["timing"],
            }
            for item in outputs
        ],
        "synthesis": synthesis,
    }
    logger.info(
        "read-only agent completed conversation_id=%s tools=%s successful=%s synthesis=%s total_ms=%s",
        req.conversation_id or "(new)",
        ",".join(item["tool"] for item in outputs) or "(none)",
        successful_tools,
        synthesis["status"],
        total_elapsed_ms,
    )
    return {
        "success": bool(selected) and successful_tools > 0,
        "mode": "read_only",
        "answer": answer,
        "selected_tools": selected,
        "tool_outputs": outputs,
        "summary": summary,
        "execution_trace": execution_trace,
    }
