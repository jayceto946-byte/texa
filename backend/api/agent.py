"""Compatibility API over Texa's shared controlled tool orchestration."""
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
from backend.tools.registry import ToolContext, get_tool_registry
from backend.services.tool_orchestration import (
    ToolOrchestrationRequest,
    execute_read_only_tools,
    select_tool_calls,
)
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


def _select_tool_calls(req: ReadOnlyAgentRequest) -> list[dict]:
    return select_tool_calls(ToolOrchestrationRequest(
        question=req.question,
        book_name=req.book_name,
        subject=req.subject,
        conversation_id=req.conversation_id,
        max_tools=req.max_tools,
        include_textbook_tool=True,
    ))


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
    orchestration = execute_read_only_tools(
        ToolOrchestrationRequest(
            question=req.question,
            book_name=req.book_name,
            subject=req.subject,
            conversation_id=req.conversation_id,
            max_tools=req.max_tools,
            include_textbook_tool=True,
        ),
        total_timeout_seconds=AGENT_TOTAL_TIMEOUT_SECONDS,
        per_tool_timeout_seconds=AGENT_TOOL_TIMEOUT_SECONDS,
        registry=get_tool_registry(),
    )
    selected = orchestration["selected_tools"]
    outputs = orchestration["tool_outputs"]

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
        "tools": orchestration["execution_trace"]["tools"],
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
