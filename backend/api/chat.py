"""Chat API: SSE streaming and non-streaming dialogue."""
from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.conversation_memory import (
    append_message,
    ensure_conversation_id,
    ensure_turn_id,
    get_conversation,
    list_conversations,
    load_history,
    load_turn_messages,
    resolve_conversation_id_for_scope,
    reclassify_conversation,
    rewrite_followup,
    split_turn_to_conversation,
    update_message_evidence_support,
    update_message_linked_concepts,
    update_learning_task_projection,
)
from backend.schemas import ChatRequest, ConversationScopeRequest, ConversationSplitTurnRequest, SubjectRoutingFeedbackRequest
from backend.schemas import AnswerFeedbackRequest
from backend.services.answer_feedback import record_answer_feedback
from backend.services.context_versions import current_context_versions
from backend.services.session_context import build_resolution_trace
from backend.services.learning_state_bridge import bridge_learning_request
from backend.services.evidence_continuity import build_evidence_continuity_context
from backend.services.session_ledger import (
    get_or_rebuild_session_ledger,
    record_assistant_in_ledger,
    save_resolution_to_ledger,
    update_ledger_evidence_invalidation,
    update_ledger_evidence_support,
)
from backend.services.subject_routing import record_subject_routing_feedback, suggest_subject_scope
from backend.services.textbook_scope import decide_answer_scope
from backend.services.tool_orchestration import (
    ToolOrchestrationRequest,
    execute_read_only_tools,
    select_tool_calls,
)
from backend.services.answer_verification import derive_required_outputs, verify_answer
from backend.services.learning_task import (
    LearningTask,
    get_learning_task_store,
    interrupt_learning_task,
    is_interruptible_task_status,
    is_resumable_task_status,
    mark_required_inputs,
    resume_learning_task,
    task_requires_input_action,
)
from backend.services.execution_events import (
    ExecutionEventEmitter,
    execution_sse_payload,
    legacy_activity_from_execution,
)
from graph.conversation_context import (
    assemble_conversation_context_pack,
    build_conversation_context_seed,
)

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

_TOOL_ACTIVITY_LABELS = {
    "symbolic_math": "执行确定性计算",
    "verify_math_result": "核对计算结果",
    "build_review_plan": "读取复习队列",
    "get_weak_concepts": "读取薄弱概念",
    "get_recent_progress": "汇总学习进度",
    "search_exercises": "筛选练习题",
    "propose_practice_session": "准备练习方案",
    "propose_add_mistake": "准备错题记录",
}


def _main_tool_request(
    question: str, book_name: str, subject: str, conversation_id: str,
    learning_task_id: str = "",
) -> ToolOrchestrationRequest:
    return ToolOrchestrationRequest(
        question=question,
        book_name=book_name,
        subject=subject,
        conversation_id=conversation_id,
        max_tools=6,
        include_textbook_tool=False,
        learning_task_id=learning_task_id,
    )


def _start_chat_learning_task(
    *, question: str, rewritten_question: str, history: list[dict],
    conversation_id: str, turn_id: str, answer_mode: str,
) -> LearningTask:
    store = get_learning_task_store()
    for message in reversed(history[-6:]):
        task_ref = message.get("learning_task") if isinstance(message, dict) else None
        if not isinstance(task_ref, dict) or task_ref.get("task_type") != "qa":
            continue
        if not task_requires_input_action(str(task_ref.get("status") or "")):
            break
        task = store.get(str(task_ref.get("id") or ""))
        if task is not None and task.conversation_id == conversation_id:
            mark_required_inputs(task, "provided")
            task.artifacts["clarification_response"] = question
            return store.checkpoint(task, "input_provided", status="running", detail="resumed from clarification")
        break
    return store.create(
        task_type="qa", goal=question, conversation_id=conversation_id, turn_id=turn_id,
        answer_mode=answer_mode,
        required_outputs=derive_required_outputs(rewritten_question, answer_mode=answer_mode),
        artifacts={"resolved_query": rewritten_question},
    )


def _finish_chat_learning_task(
    task: LearningTask,
    state: dict,
    *,
    waiting_reason: str = "",
    run_id: str = "",
) -> LearningTask:
    store = get_learning_task_store()
    if waiting_reason:
        task.required_inputs = [{
            "type": "clarification", "name": "用户澄清", "reason": waiting_reason[:500],
            "affects": ["answer_scope"], "blocking": True, "status": "missing",
        }]
        task.verification = {"status": "waiting_for_input", "passed": False, "checks": []}
        checkpoint = store.checkpoint_for_run if run_id else store.checkpoint
        args = (task, run_id, "waiting_for_input") if run_id else (task, "waiting_for_input")
        return checkpoint(*args, status="waiting_for_input", detail=waiting_reason)
    verification = dict(state.get("answer_verification") or {})
    if not verification:
        verification = verify_answer(
            str(state.get("final_output") or ""), required_outputs=task.required_outputs,
            sources=state.get("evidence_sources") or [], citation_trace=state.get("citation_trace") or {},
            tool_context_pack=state.get("tool_context_pack") or {}, evidence_items=state.get("evidence_items") or [],
        )
    task.verification = verification
    task.required_outputs = list(state.get("required_outputs") or task.required_outputs)
    task.artifacts.update({
        "final_output": str(state.get("final_output") or ""),
        "evidence_ids": [
            str(item.get("id") or item.get("chunk_id") or "")
            for item in state.get("evidence_sources") or [] if isinstance(item, dict)
        ][:20],
    })
    pending_actions = list(task.artifacts.get("pending_actions") or [])
    has_pending = any(
        str(item.get("status") or "pending") == "pending"
        for item in pending_actions if isinstance(item, dict)
    )
    status = "waiting_for_confirmation" if has_pending else (
        "completed" if verification.get("status") == "passed" else "degraded"
    )
    if run_id:
        return store.checkpoint_for_run(
            task, run_id, "verified", status=status,
            detail=str(verification.get("status") or "unknown"),
        )
    return store.checkpoint(task, "verified", status=status, detail=str(verification.get("status") or "unknown"))


def _attach_pending_actions(task: LearningTask, tool_run: dict, *, run_id: str = "") -> LearningTask:
    actions = [
        item.get("result", {}).get("pending_action")
        for item in tool_run.get("tool_outputs") or []
        if isinstance(item, dict) and item.get("result", {}).get("pending_action")
    ]
    if actions:
        task.artifacts["pending_actions"] = actions[:10]
        store = get_learning_task_store()
        if run_id:
            return store.save_for_run(task, run_id)
        return store.save(task)
    return task


def _prepare_main_tool_context(
    question: str, book_name: str, subject: str, conversation_id: str,
    learning_task_id: str = "",
    on_event=None,
) -> dict:
    try:
        return execute_read_only_tools(_main_tool_request(
            question, book_name, subject, conversation_id, learning_task_id,
        ), on_event=on_event)
    except Exception as exc:
        logger.exception("main chat tool orchestration failed")
        return {
            "selected_tools": [], "tool_outputs": [],
            "tool_context_pack": {
                "text": "", "char_count": 0, "tool_count": 0,
                "successful_tool_count": 0, "selected_tools": [],
                "sufficient": False, "skip_textbook_retrieval": False,
                "outputs": [], "error": str(exc)[:300],
            },
            "execution_trace": {"total_elapsed_ms": 0, "budget_seconds": 0, "tools": []},
        }


def _activity_for_chat_event(event: dict) -> dict | None:
    """Describe real completed/active work without exposing model reasoning."""
    stage = str(event.get("stage") or "")
    duration_ms = event.get("stage_ms")
    if stage == "progress":
        return {
            "id": str(event.get("operation_id") or "progress"),
            "kind": str(event.get("kind") or "analysis"),
            "label": str(event.get("label") or "继续处理"),
            "status": "active",
            "detail": str(event.get("message") or "仍在等待当前步骤完成"),
            "meta": {
                "waited_ms": event.get("waited_ms"),
            } if event.get("waited_ms") is not None else {},
        }
    if stage == "plan":
        chapters = [str(item) for item in event.get("chapters") or [] if str(item)]
        return {
            "id": "understand", "kind": "analysis", "label": "理解问题与确定范围",
            "status": "completed",
            "detail": f"已定位到：{'、'.join(chapters[:3])}" if chapters else "已识别问题意图与回答范围",
            "duration_ms": duration_ms,
        }
    if stage == "retrieve":
        ordinary = event.get("use_textbook_context") is False or event.get("retrieval_status") == "ordinary_qa"
        failed = bool(event.get("retrieval_error"))
        count = int(event.get("content_count") or 0)
        return {
            "id": "retrieve", "kind": "tool", "label": "检索教材上下文",
            "status": "failed" if failed else ("skipped" if ordinary else "completed"),
            "detail": str(event.get("retrieval_error") or (
                "本题不需要教材证据" if ordinary else f"已整理 {count} 条相关教材内容"
            )),
            "duration_ms": duration_ms,
        }
    if stage == "chapter":
        return {
            "id": "evidence", "kind": "evidence", "label": "整理教材证据",
            "status": "completed",
            "detail": f"已准备 {int(event.get('content_count') or 0)} 项章节内容",
            "duration_ms": duration_ms,
        }
    if stage == "generate":
        return {
            "id": "generate", "kind": "generation", "label": "生成答案",
            "status": "completed" if event.get("done") else "active",
            "detail": "答案生成完成" if event.get("done") else "正在把证据与推导组织成讲解",
            "duration_ms": duration_ms,
        }
    if stage == "done":
        state = event.get("state") or {}
        concepts = state.get("linked_concepts") or []
        return {
            "id": "memory", "kind": "memory", "label": "关联学习记录",
            "status": "completed" if concepts else "skipped",
            "detail": f"已关联 {len(concepts)} 个核心概念；学习记录在后台更新" if concepts else "本轮没有可靠的概念标签",
        }
    if stage == "error":
        return {
            "id": "error", "kind": "system", "label": "回答中断",
            "status": "failed", "detail": str(event.get("message") or "后端生成失败"),
        }
    return None


def _persisted_evidence_sources(
    sources: list | None,
    *,
    book_name: str,
    context_versions: dict,
) -> list[dict]:
    book_id = ""
    if book_name:
        try:
            from utils.book_registry import BookRegistry

            identity = BookRegistry().resolve(book_name)
            book_id = str((identity or {}).get("book_id") or "")
        except Exception:
            logger.exception("failed to resolve textbook identity for evidence metadata")
    corpus_version = str(context_versions.get("corpus_version") or "")
    result = []
    for source in (sources or [])[:20]:
        if not isinstance(source, dict):
            continue
        result.append({
            **source,
            "book_id": str(source.get("book_id") or book_id)[:100],
            "corpus_version": str(source.get("corpus_version") or corpus_version)[:100],
        })
    return result


def _append_assistant_result(
    *,
    conversation_id: str,
    content: str,
    book_name: str,
    subject: str,
    turn_id: str,
    sources: list | None,
    context_versions: dict,
    answer_mode: str,
    scope_reason: str,
    suggested_answer_mode: str,
    request_id: str,
    learning_task: LearningTask,
    linked_concepts: list | None = None,
    delivery_status: str = "complete",
    evidence_support_status: str = "",
) -> dict:
    """Persist the canonical assistant projection for either chat transport."""
    return append_message(
        conversation_id,
        "assistant",
        content,
        book_name=book_name,
        subject=subject,
        turn_id=turn_id,
        sources=_persisted_evidence_sources(
            sources, book_name=book_name, context_versions=context_versions,
        ),
        linked_concepts=linked_concepts,
        answer_mode=answer_mode,
        scope_reason=scope_reason,
        suggested_answer_mode=suggested_answer_mode,
        delivery_status=delivery_status,
        evidence_support_status=evidence_support_status,
        request_id=request_id,
        context_versions=context_versions,
        learning_task=learning_task.to_dict(public=True),
    )


def _resolve_request_question(
    question: str,
    history: list[dict],
    conversation_id: str,
    *,
    book_name: str,
    subject: str,
) -> tuple[str, dict]:
    try:
        ledger = get_or_rebuild_session_ledger(conversation_id, history)
        trace = build_resolution_trace(
            question, history, initial_state=ledger.get("state") or {},
        )
        bridge = bridge_learning_request(
            question,
            str(trace.get("speech_act") or ""),
            book_name=book_name,
            subject=subject,
            conversation_id=conversation_id,
            current_topic=str((trace.get("state_before") or {}).get("topic") or ""),
        )
        trace["learning_bridge"] = {
            "action": bridge.action,
            "learning_context": bridge.learning_context,
            "state_operations": bridge.state_operations,
            "error": bridge.error,
        }
        for operation in bridge.state_operations:
            if operation not in trace["state_operations"]:
                trace["state_operations"].append(operation)
        if bridge.action in {"clarify", "handled"}:
            trace["resolution_action"] = "respond" if bridge.action == "handled" else "clarify"
            trace["clarification_message"] = bridge.clarification_message
        elif bridge.resolved_query:
            trace["resolved_query"] = bridge.resolved_query
        return str(trace.get("resolved_query") or question), trace
    except Exception:
        logger.exception("session ledger resolution failed; falling back to recent history")
        rewritten = rewrite_followup(
            question, history, book_name=book_name, subject=subject,
        )
        return rewritten, build_resolution_trace(question, history, rewritten)


def _conversation_context_seed(
    conversation_id: str,
    history: list[dict],
    resolution_trace: dict,
) -> dict:
    try:
        referenced_ids = [
            str(value) for value in resolution_trace.get("referenced_turn_ids") or []
            if str(value).strip()
        ]
        recent_ids = {
            str(item.get("turn_id") or "") for item in history if isinstance(item, dict)
        }
        missing_ids = [value for value in referenced_ids if value not in recent_ids]
        supplemental = load_turn_messages(conversation_id, missing_ids, max_turns=2)
        return build_conversation_context_seed(
            history,
            resolution_trace,
            supplemental_history=supplemental,
        )
    except Exception:
        # Context continuity is a best-effort enhancement. A damaged projection
        # must not prevent the current question from reaching the graph.
        logger.exception("failed to assemble conversation context seed")
        return {}


def _safe_save_resolution_ledger(
    conversation_id: str,
    resolution_trace: dict,
    user_message: dict | None,
) -> None:
    try:
        save_resolution_to_ledger(conversation_id, resolution_trace, user_message)
    except Exception:
        logger.exception("failed to persist session ledger resolution")


def _safe_record_assistant_ledger(conversation_id: str, assistant_message: dict | None) -> None:
    try:
        record_assistant_in_ledger(conversation_id, assistant_message)
    except Exception:
        logger.exception("failed to persist assistant session ledger state")


def _safe_record_evidence_invalidation(conversation_id: str, context: dict) -> None:
    reason = str(context.get("active_evidence_invalidation_reason") or "")
    if not reason:
        return
    try:
        update_ledger_evidence_invalidation(conversation_id, reason)
    except Exception:
        logger.exception("failed to persist active evidence invalidation")


def _clarification_result(
    resolution_trace: dict,
    conversation_context_seed: dict | None = None,
) -> dict:
    message = str(resolution_trace.get("clarification_message") or "").strip()
    intent = "direct_response" if resolution_trace.get("resolution_action") == "respond" else "clarification"
    conversation_pack = assemble_conversation_context_pack({
        "intent": intent,
        "conversation_context_seed": conversation_context_seed or {},
        "retrieval_action": "none",
    })
    conversation_pack.pop("text", None)
    return {
        "final_output": message,
        "intent": intent,
        "target_chapters": [],
        "linked_concepts": [],
        "evidence_sources": [],
        "evidence_items": [],
        "retrieval_debug_items": [],
        "evidence_support": {"status": "not_applicable", "reason": f"{intent}_no_retrieval"},
        "retrieval_status": intent,
        "retrieval_error": "",
        "retrieval_action": "none",
        "retrieval_query": "",
        "reused_evidence_ids": [],
        "new_evidence_ids": [],
        "dropped_evidence_ids": [],
        "conversation_context_pack": conversation_pack,
        "context_budget": {
            "assembly_mode": f"{intent}_no_generation",
            "budget_unit": "characters",
            "prompt_chars": 0,
            "conversation_context_budget_chars": int(conversation_pack.get("budget") or 0),
            "conversation_context_chars": int(conversation_pack.get("char_count") or 0),
            "session_state_chars": int(conversation_pack.get("state_chars") or 0),
            "recent_turns_chars": int(conversation_pack.get("recent_turns_chars") or 0),
            "conversation_turn_count": len(conversation_pack.get("turn_ids") or []),
        },
    }


def _learning_context_for_graph(resolution_trace: dict) -> dict:
    bridge = resolution_trace.get("learning_bridge")
    if not isinstance(bridge, dict):
        return {}
    value = bridge.get("learning_context")
    return dict(value) if isinstance(value, dict) else {}


def _scope_from_learning_context(book_name: str, subject: str, resolution_trace: dict) -> tuple[str, str]:
    pack = _learning_context_for_graph(resolution_trace)
    return (
        str(pack.get("book_name") or "") or book_name,
        str(pack.get("subject") or "") or subject,
    )


def _target_chapters_from_learning_context(requested: list[str], resolution_trace: dict) -> list[str]:
    if requested:
        return requested
    progress = _learning_context_for_graph(resolution_trace).get("current_progress") or {}
    chapter_name = str(progress.get("chapter_name") or "")
    return [chapter_name] if chapter_name else []


def _context_trace_payload(
    resolution_trace: dict,
    final_state: dict,
    context_versions: dict | None = None,
) -> dict:
    support = final_state.get("evidence_support") or {}
    reused_candidates = list(final_state.get("reused_evidence_ids") or [])
    new_candidates = list(final_state.get("new_evidence_ids") or [])
    candidate_ids = list(dict.fromkeys([*reused_candidates, *new_candidates]))
    evidence_sources = final_state.get("evidence_sources")
    if isinstance(evidence_sources, list):
        included_ids = list(dict.fromkeys(
            str(item.get("chunk_id") or "")
            for item in evidence_sources
            if isinstance(item, dict) and item.get("chunk_id")
        ))
    else:
        included_ids = candidate_ids
    reused_ids = [item for item in reused_candidates if item in included_ids]
    new_ids = [item for item in new_candidates if item in included_ids]
    dropped_ids = list(dict.fromkeys([
        *(final_state.get("dropped_evidence_ids") or []),
        *(item for item in candidate_ids if item not in included_ids),
    ]))
    return {
        "resolution": resolution_trace,
        "conversation_context": final_state.get("conversation_context_pack") or {},
        "retrieval": {
            "action": str(final_state.get("retrieval_action") or "none"),
            "query": str(final_state.get("retrieval_query") or ""),
            "reused_evidence_ids": reused_ids,
            "new_evidence_ids": new_ids,
            "dropped_evidence_ids": dropped_ids,
            "support_status": str(support.get("status") or ""),
            "status": str(final_state.get("retrieval_status") or ""),
            "error": str(final_state.get("retrieval_error") or ""),
        },
        "context_budget": final_state.get("context_budget") or {},
        "versions": context_versions or {},
    }

def _safe_subject_suggestion(question: str, subject: str, book_name: str) -> dict | None:
    try:
        # A closed expression already accepted by the restricted math router is
        # not evidence of another textbook scope. Let it remain in the current
        # learning context instead of asking vector retrieval to guess a subject.
        math_calls = select_tool_calls(_main_tool_request(question, book_name, subject, ""))
        if any(item.get("tool") == "symbolic_math" for item in math_calls):
            return None
        return suggest_subject_scope(question, subject, book_name)
    except Exception:
        logger.exception("subject routing suggestion failed")
        return None


def _prepare_chat_turn(
    req: ChatRequest,
    *,
    resume_task: LearningTask | None = None,
    resume: bool = False,
) -> dict:
    """Resolve the transport-independent input, scope, and context for one chat turn."""
    book_name = (req.book_name or "").strip()
    subject = (req.subject or "").strip()
    conversation_id = resolve_conversation_id_for_scope(req.conversation_id, subject, book_name)
    turn_id = ensure_turn_id(req.turn_id)
    history = load_history(conversation_id)
    rewritten_question, resolution_trace = _resolve_request_question(
        req.question, history, conversation_id, book_name=book_name, subject=subject,
    )
    if resume and resume_task is not None:
        rewritten_question = str(resume_task.artifacts.get("resolved_query") or rewritten_question)
        resolution_trace["resolution_action"] = "continue"
        resolution_trace["resolved_query"] = rewritten_question

    book_name, subject = _scope_from_learning_context(book_name, subject, resolution_trace)
    conversation_id = resolve_conversation_id_for_scope(conversation_id, subject, book_name)
    target_chapters = _target_chapters_from_learning_context(req.target_chapters, resolution_trace)
    continuity_context = build_evidence_continuity_context(
        history, resolution_trace, book_name=book_name, subject=subject,
    )
    _safe_record_evidence_invalidation(conversation_id, continuity_context)
    continuity_context["conversation_context_seed"] = _conversation_context_seed(
        conversation_id, history, resolution_trace,
    )
    continuity_context["learning_context_pack"] = _learning_context_for_graph(resolution_trace)
    subject_suggestion = _safe_subject_suggestion(rewritten_question, subject, book_name)
    scope_decision = decide_answer_scope(
        req.question,
        rewritten_question,
        book_name=book_name,
        subject=subject,
        subject_suggestion=subject_suggestion,
        requested_mode=req.answer_mode,
    )
    return {
        "book_name": book_name,
        "subject": subject,
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "history": history,
        "rewritten_question": rewritten_question,
        "resolution_trace": resolution_trace,
        "target_chapters": target_chapters,
        "continuity_context": continuity_context,
        "subject_suggestion": subject_suggestion,
        "use_textbook_context": scope_decision.use_textbook_context,
        "scope_reason": scope_decision.reason,
        "answer_mode": scope_decision.answer_mode,
        "context_versions": current_context_versions(book_name),
    }



def _safe_record_subject_feedback(source: str, target: str, action: str) -> None:
    try:
        record_subject_routing_feedback(source, target, action)
    except Exception:
        logger.exception("subject routing feedback persistence failed")

@router.get("/conversations")
def conversations(subject: str = "", book_name: str = "", limit: int = 80):
    return {"success": True, "data": list_conversations(subject=subject, book_name=book_name, limit=limit)}


@router.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: str, limit: int = 40, before_seq: int | None = None):
    conversation_id = ensure_conversation_id(conversation_id)
    return {
        "success": True,
        "data": get_conversation(conversation_id, limit=limit, before_seq=before_seq),
    }


@router.get("/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str, limit: int = 40, before_seq: int | None = None):
    conversation_id = ensure_conversation_id(conversation_id)
    data = get_conversation(conversation_id, limit=limit, before_seq=before_seq)
    return {"success": True, "data": {"messages": data["messages"], "page": data["page"]}}


@router.patch("/conversations/{conversation_id}/scope")
def update_conversation_scope(conversation_id: str, req: ConversationScopeRequest):
    try:
        data = reclassify_conversation(conversation_id, req.subject, req.book_name)
        _safe_record_subject_feedback(req.source_subject, req.subject, "accepted")
        return {"success": True, "data": data}
    except ValueError as exc:
        return {"success": False, "message": str(exc)}


@router.post("/conversations/{conversation_id}/split-turn")
def split_conversation_turn(conversation_id: str, req: ConversationSplitTurnRequest):
    try:
        source, target = split_turn_to_conversation(
            conversation_id,
            req.turn_id,
            req.subject,
            req.book_name,
        )
        _safe_record_subject_feedback(req.source_subject, req.subject, "accepted")
        return {"success": True, "data": {"source": source, "target": target}}
    except ValueError as exc:
        return {"success": False, "message": str(exc)}


@router.post("/subject-routing/feedback")
def subject_routing_feedback(req: SubjectRoutingFeedbackRequest):
    try:
        data = record_subject_routing_feedback(
            req.source_subject,
            req.target_subject,
            req.action,
        )
        return {"success": True, "data": data}
    except ValueError as exc:
        return {"success": False, "message": str(exc)}


@router.post("/feedback")
def answer_feedback(req: AnswerFeedbackRequest):
    try:
        data = record_answer_feedback(
            conversation_id=req.conversation_id,
            message_id=req.message_id,
            rating=req.rating,
            reasons=req.reasons,
            note=req.note,
        )
        return {"success": True, "data": data}
    except ValueError as exc:
        return {"success": False, "message": str(exc)}


@router.post("/log")
def log_conversation_messages(payload: dict):
    book_name = str(payload.get("book_name") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    conversation_id = resolve_conversation_id_for_scope(
        str(payload.get("conversation_id") or ""), subject, book_name
    )
    turn_id = ensure_turn_id(str(payload.get("turn_id") or ""))
    messages = payload.get("messages") or []
    if not isinstance(messages, list):
        return {"success": False, "message": "messages must be a list", "conversation_id": conversation_id}
    appended = 0
    for item in messages[:8]:
        if not isinstance(item, dict):
            continue
        role = "assistant" if item.get("role") == "assistant" else "user"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        append_message(
            conversation_id,
            role,
            content,
            book_name=book_name,
            subject=subject,
            turn_id=str(item.get("turn_id") or turn_id),
            delivery_status=str(item.get("delivery_status") or "complete"),
            learning_task=item.get("learning_task") if isinstance(item.get("learning_task"), dict) else None,
        )
        appended += 1
    return {"success": True, "conversation_id": conversation_id, "appended": appended}


def _prepared_chat_stream(
    req: ChatRequest,
    _learning_task: LearningTask | None = None,
    _resume: bool = False,
    _run_id: str = "",
    _request_id: str = "",
    _start_seq: int = 0,
):
    from graph.main_graph import run_graph_stream

    prepared = _prepare_chat_turn(req, resume_task=_learning_task, resume=_resume)
    book_name = prepared["book_name"]
    subject = prepared["subject"]
    conversation_id = prepared["conversation_id"]
    turn_id = prepared["turn_id"]
    history = prepared["history"]
    rewritten_question = prepared["rewritten_question"]
    resolution_trace = prepared["resolution_trace"]
    target_chapters = prepared["target_chapters"]
    continuity_context = prepared["continuity_context"]
    subject_suggestion = prepared["subject_suggestion"]
    use_textbook_context = prepared["use_textbook_context"]
    scope_reason = prepared["scope_reason"]
    answer_mode = prepared["answer_mode"]
    context_versions = prepared["context_versions"]
    learning_task = _learning_task or _start_chat_learning_task(
        question=req.question, rewritten_question=rewritten_question, history=history,
        conversation_id=conversation_id, turn_id=turn_id, answer_mode=answer_mode,
    )
    if _resume:
        rewritten_question = str(learning_task.artifacts.get("resolved_query") or rewritten_question)
        turn_id = learning_task.turn_id or turn_id
    run_id = _run_id or f"run_{uuid.uuid4().hex}"
    learning_task.artifacts.update({
        "resolved_query": rewritten_question,
        "book_name": book_name,
        "subject": subject,
        "target_chapters": target_chapters,
        "use_textbook_context": use_textbook_context,
        "scope_reason": scope_reason,
        "active_run_id": run_id,
    })
    get_learning_task_store().save(learning_task)
    continuity_context["learning_task"] = learning_task.to_dict()
    continuity_context["required_outputs"] = learning_task.required_outputs

    def event_generator():
        nonlocal learning_task
        from backend.rag_trace import new_request_id, save_trace

        request_id = _request_id or new_request_id()
        task_store = get_learning_task_store()
        def persist_execution_event(event: dict) -> None:
            updated = task_store.append_execution_event_for_run(learning_task.id, run_id, event)
            if (
                updated is None
                or str(updated.artifacts.get("active_run_id") or "") != run_id
            ):
                raise ValueError("stale chat execution run cannot persist events")
            if event.get("type") in {"final", "error"}:
                event_task_status = str((event.get("payload") or {}).get("task_status") or "")
                if not event_task_status or updated.status != event_task_status:
                    raise ValueError("chat terminal event does not match the current task state")
            elif not task_store.run_is_active(learning_task.id, run_id):
                raise ValueError("stale chat execution run cannot persist events")
            learning_task.artifacts["execution_events"] = list(
                updated.artifacts.get("execution_events") or []
            )[-40:]

        emitter = ExecutionEventEmitter(
            request_id=request_id,
            task_id=learning_task.id,
            run_id=run_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            start_seq=_start_seq,
            persist=persist_execution_event,
        )
        started = time.perf_counter()
        last_milestone_at = started
        generation_started = None
        last_stage = "context"
        timings: dict[str, float] = {}
        ttft_ms = None
        final_state: dict = {}
        intent = ""
        fast_path = False
        assistant_chunks: list[str] = []
        assistant_persisted = False
        assistant_persistence_error = ""
        assistant_sources: list = []
        assistant_message_id = ""
        assistant_message: dict | None = None
        suggested_answer_mode = ""
        disconnected = False
        reason_active = False
        reason_started_at: float | None = None
        evidence_active = False
        generation_handoff_done = False

        def execution_sse(
            event_type: str,
            *,
            phase: str,
            status: str,
            summary: str,
            operation_id: str,
            label: str,
            kind: str,
            payload: dict | None = None,
            duration_ms: int | float | None = None,
            stage: str = "execution",
        ) -> str:
            if not task_store.run_is_active(learning_task.id, run_id):
                raise ValueError("stale chat execution run cannot emit events")
            execution_event = emitter.emit(
                event_type,
                phase=phase,
                status=status,
                summary=summary,
                operation_id=operation_id,
                label=label,
                kind=kind,
                payload=payload,
                duration_ms=duration_ms,
            )
            return f"data: {json.dumps(execution_sse_payload(execution_event, stage=stage), ensure_ascii=False)}\n\n"

        def activity_sse(activity: dict, *, event_type: str | None = None, phase: str = "orchestration") -> str:
            raw_status = str(activity.get("status") or "pending")
            status = {
                "active": "started",
                "completed": "completed",
                "failed": "failed",
                "skipped": "skipped",
            }.get(raw_status, "running")
            resolved_type = event_type or ("progress" if raw_status == "active" else "state_transition")
            return execution_sse(
                resolved_type,
                phase=phase,
                status=status,
                summary=str(activity.get("detail") or activity.get("label") or ""),
                operation_id=str(activity.get("id") or f"{phase}:{resolved_type}"),
                label=str(activity.get("label") or "执行任务"),
                kind=str(activity.get("kind") or "system"),
                payload=dict(activity.get("meta") or {}),
                duration_ms=activity.get("duration_ms"),
                stage="activity",
            )

        def stream_tool_context():
            event_queue: queue.Queue = queue.Queue()

            def on_tool_event(event: dict) -> None:
                event_queue.put(("event", event))

            def execute_tools() -> None:
                try:
                    result = _prepare_main_tool_context(
                        rewritten_question,
                        book_name,
                        subject,
                        conversation_id,
                        learning_task.id,
                        on_event=on_tool_event,
                    )
                    event_queue.put(("done", result))
                except Exception as exc:  # pragma: no cover - service already degrades safely
                    event_queue.put(("error", exc))

            worker = threading.Thread(target=execute_tools, name="chat-tool-events", daemon=True)
            worker.start()
            active_tool = "学习工具"
            while True:
                try:
                    item_type, value = event_queue.get(timeout=10.0)
                except queue.Empty:
                    yield execution_sse(
                        "progress",
                        phase="tool",
                        status="running",
                        summary=f"{active_tool}仍在执行，正在等待可验证结果",
                        operation_id="tools",
                        label="使用学习工具",
                        kind="tool",
                    )
                    continue
                if item_type == "done":
                    return value
                if item_type == "error":
                    raise value
                tool_name = str(value.get("tool") or "")
                active_tool = _TOOL_ACTIVITY_LABELS.get(tool_name, "执行学习工具")
                internal_event_type = str(value.get("type") or "")
                if internal_event_type == "tool_call":
                    event_type = "progress"
                    tool_event = "call_started"
                elif internal_event_type == "tool_result":
                    event_type = "tool_result"
                    tool_event = "result_available"
                else:
                    raise ValueError(f"unsupported chat tool event type: {internal_event_type}")
                status = str(value.get("status") or "running")
                summary = str(value.get("message") or (
                    f"开始{active_tool}" if internal_event_type == "tool_call" else f"{active_tool}已返回结果"
                ))
                yield execution_sse(
                    event_type,
                    phase="tool",
                    status=status,
                    summary=summary,
                    operation_id=str(value.get("operation_id") or f"tool:{tool_name}"),
                    label=active_tool,
                    kind="tool",
                    payload={
                        "tool_event": tool_event,
                        **{
                            key: value.get(key)
                            for key in (
                                "tool", "args_summary", "timeout_seconds", "success", "required_outputs",
                                "satisfied_required_outputs", "missing_required_outputs", "followup",
                            )
                            if value.get(key) is not None
                        },
                    },
                    duration_ms=value.get("elapsed_ms"),
                )

        def persist_assistant(delivery_status: str = "complete") -> str:
            nonlocal assistant_persisted, assistant_persistence_error, assistant_message_id, assistant_message
            if assistant_persisted:
                return assistant_persistence_error

            content = "".join(assistant_chunks)
            if not content.strip():
                assistant_persisted = True
                assistant_persistence_error = ""
                return ""

            try:
                item = _append_assistant_result(
                    conversation_id=conversation_id,
                    content=content,
                    book_name=book_name,
                    subject=subject,
                    turn_id=turn_id,
                    sources=assistant_sources,
                    context_versions=context_versions,
                    answer_mode=answer_mode,
                    scope_reason=scope_reason,
                    suggested_answer_mode=suggested_answer_mode,
                    delivery_status=delivery_status,
                    request_id=request_id,
                    learning_task=learning_task,
                )
                assistant_message_id = str((item or {}).get("id") or "")
                assistant_message = item if isinstance(item, dict) else None
                if delivery_status == "complete":
                    _safe_record_assistant_ledger(conversation_id, assistant_message)
                assistant_persisted = True
                assistant_persistence_error = ""
            except Exception as exc:
                assistant_persistence_error = str(exc)
                logger.exception("assistant persistence failed")
            return assistant_persistence_error

        def observe(event: dict) -> None:
            nonlocal last_milestone_at, generation_started, last_stage, ttft_ms, final_state, intent, fast_path
            now = time.perf_counter()
            stage = str(event.get("stage") or "unknown")
            if stage not in {"done", "error"} and not task_store.run_is_active(
                learning_task.id, run_id,
            ):
                raise ValueError("stale chat execution run cannot emit events")
            if stage in {"plan", "retrieve", "chapter"}:
                stage_ms = round((now - last_milestone_at) * 1000, 2)
                timings[stage] = stage_ms
                event["stage_ms"] = stage_ms
                last_milestone_at = now
            if stage == "generate" and generation_started is None:
                generation_started = last_milestone_at
            if stage == "plan":
                intent = str(event.get("intent") or "")
                fast_path = bool(event.get("fast_path"))
                if event.get("planner_trace"):
                    timings["planner"] = event["planner_trace"]
            if stage == "generate" and event.get("chunk") and ttft_ms is None:
                ttft_ms = round((now - started) * 1000, 2)
                timings["generate_ttft"] = round((now - (generation_started or started)) * 1000, 2)
                event["ttft_ms"] = ttft_ms
            if stage == "done":
                final_state = event.get("state") or {}
                if final_state.get("citation_trace"):
                    timings["citation"] = final_state["citation_trace"]
                stage_ms = round((now - (generation_started or last_milestone_at)) * 1000, 2)
                timings["generate"] = stage_ms
                timings["total"] = round((now - started) * 1000, 2)
                event["stage_ms"] = stage_ms
                event["timings"] = dict(timings)
            last_stage = stage
            event["request_id"] = request_id
            event["elapsed_ms"] = round((now - started) * 1000, 2)
            activity = _activity_for_chat_event(event)
            if activity:
                stage_type = {
                    "progress": "progress",
                    "generate": "output_delta" if not event.get("done") else "state_transition",
                    "done": "final",
                    "error": "error",
                }.get(stage, "state_transition")
                activity_status = str(activity.get("status") or "")
                status = {
                    "completed": "completed",
                    "skipped": "skipped",
                    "failed": "failed",
                    "active": "running",
                }.get(activity_status, "failed" if stage == "error" else "running")
                if stage == "generate" and not event.get("done"):
                    payload = {
                        "text": str(event.get("chunk") or ""),
                        "replace": bool(event.get("replace", False)),
                    }
                else:
                    payload = dict(activity.get("meta") or {})
                    if stage == "done":
                        task_snapshot = (event.get("state") or {}).get("learning_task") or {}
                        payload["task_status"] = str(task_snapshot.get("status") or "")
                        status = "completed"
                    elif stage == "error":
                        task_snapshot = event.get("learning_task") or {}
                        payload["task_status"] = str(task_snapshot.get("status") or "")
                execution_event = emitter.emit(
                    stage_type,
                    phase={
                        "progress": str(event.get("phase") or "orchestration"),
                        "plan": "planning", "retrieve": "retrieval", "chapter": "evidence",
                        "generate": "generation", "done": "final", "error": "error",
                    }.get(stage, stage),
                    status=status,
                    summary=str(activity.get("detail") or activity.get("label") or ""),
                    operation_id=str(activity.get("id") or stage),
                    label=str(activity.get("label") or stage),
                    kind=str(activity.get("kind") or "system"),
                    payload=payload,
                    duration_ms=activity.get("duration_ms"),
                )
                event["execution_event"] = execution_event
                event["activity"] = legacy_activity_from_execution(execution_event)

        graph_events = None
        try:
            context_execution = emitter.emit(
                "state_transition",
                phase="context",
                status="completed",
                summary="已解析当前问题、指代与学习范围",
                operation_id="context",
                label="读取会话上下文",
                kind="analysis",
            )
            yield f"data: {json.dumps({'stage': 'context', 'request_id': request_id, 'conversation_id': conversation_id, 'turn_id': turn_id, 'book_name': book_name, 'subject': subject, 'rewritten_question': rewritten_question if rewritten_question != req.question else '', 'resolution_action': resolution_trace.get('resolution_action', 'continue'), 'use_textbook_context': use_textbook_context, 'scope_reason': scope_reason, 'answer_mode': answer_mode, 'learning_task': learning_task.to_dict(public=True), 'execution_event': context_execution, 'activity': legacy_activity_from_execution(context_execution)}, ensure_ascii=False)}\n\n"
            if not _resume:
                user_message = append_message(
                    conversation_id, "user", req.question,
                    book_name=book_name, subject=subject, turn_id=turn_id,
                    request_id=request_id, context_versions=context_versions,
                )
                _safe_save_resolution_ledger(conversation_id, resolution_trace, user_message)
            context_finished = time.perf_counter()
            timings["context"] = round((context_finished - started) * 1000, 2)
            last_milestone_at = context_finished
            if resolution_trace.get("resolution_action") in {"clarify", "respond"}:
                final_state = _clarification_result(
                    resolution_trace,
                    continuity_context.get("conversation_context_seed"),
                )
                clarification = str(final_state.get("final_output") or "")
                assistant_chunks.append(clarification)
                generate_event = {"stage": "generate", "chunk": clarification, "done": False}
                observe(generate_event)
                generate_event.update({"conversation_id": conversation_id, "turn_id": turn_id})
                yield f"data: {json.dumps(generate_event, ensure_ascii=False)}\n\n"
                generate_done = {
                    "stage": "generate", "chunk": "", "done": True,
                    "evidence_sources": [], "conversation_id": conversation_id, "turn_id": turn_id,
                }
                observe(generate_done)
                yield f"data: {json.dumps(generate_done, ensure_ascii=False)}\n\n"
                done_event = {
                    "stage": "done", "state": final_state, "enriched": False,
                    "conversation_id": conversation_id, "turn_id": turn_id,
                    "message_id": assistant_message_id,
                    "subject_suggestion": subject_suggestion,
                    "answer_mode": answer_mode, "scope_reason": scope_reason,
                }
                waiting_reason = clarification if resolution_trace.get("resolution_action") == "clarify" else ""
                completed_task = _finish_chat_learning_task(
                    learning_task, final_state, waiting_reason=waiting_reason, run_id=run_id,
                )
                if (
                    is_resumable_task_status(completed_task.status)
                    or str(completed_task.artifacts.get("active_run_id") or "") != run_id
                ):
                    return
                final_state["learning_task"] = completed_task.to_dict(public=True)
                persist_assistant()
                observe(done_event)
                yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"
                return
            tool_request = _main_tool_request(
                rewritten_question, book_name, subject, conversation_id,
            )
            planned_tools = select_tool_calls(tool_request)
            if planned_tools and answer_mode != "subject_mismatch":
                yield activity_sse({
                    "id": "tools", "kind": "tool", "label": "使用学习工具",
                    "status": "active", "detail": f"正在执行 {len(planned_tools)} 项受控只读操作",
                }, phase="tool")
                tool_run = yield from stream_tool_context()
                learning_task = _attach_pending_actions(learning_task, tool_run, run_id=run_id)
                continuity_context["learning_task"] = learning_task.to_dict()
                tool_pack = dict(tool_run.get("tool_context_pack") or {})
                tool_pack["execution_trace"] = tool_run.get("execution_trace") or {}
                continuity_context["tool_context_pack"] = tool_pack
                yield activity_sse({
                    "id": "tools", "kind": "tool", "label": "使用学习工具",
                    "status": "completed" if tool_pack.get("sufficient") else "failed",
                    "detail": (
                        f"{int(tool_pack.get('successful_tool_count') or 0)} 项操作可用于本轮回答"
                        if tool_pack.get("sufficient") else "工具未提供可用结果，继续使用原回答路径"
                    ),
                    "duration_ms": (tool_run.get("execution_trace") or {}).get("total_elapsed_ms"),
                }, phase="tool")
            graph_events = run_graph_stream(
                user_input=rewritten_question,
                book_name=book_name,
                subject=subject,
                conversation_id=conversation_id,
                target_chapters=target_chapters,
                use_textbook_context=use_textbook_context,
                answer_mode=answer_mode,
                scope_reason=scope_reason,
                continuity_context=continuity_context,
                resume_state=(learning_task.artifacts.get("resume_state") or {}) if _resume else None,
            )
            yield activity_sse({
                "id": "understand", "kind": "analysis", "label": "理解问题与确定范围",
                "status": "active", "detail": "正在识别问题意图、对象与回答边界",
            })
            for event in graph_events:
                if not get_learning_task_store().run_is_active(learning_task.id, run_id):
                    disconnected = True
                    last_stage = "interrupted"
                    logger.info("stale chat stream stopped", extra={"request_id": request_id})
                    return
                checkpoint_state = event.pop("checkpoint_state", None)
                if isinstance(checkpoint_state, dict):
                    learning_task.artifacts["resume_state"] = checkpoint_state
                    learning_task.artifacts["resume_stage"] = "retrieve"
                    get_learning_task_store().save_for_run(learning_task, run_id)
                if event.get("stage") == "generate" and learning_task.artifacts.get("resume_stage") != "generate":
                    learning_task.artifacts["resume_stage"] = "generate"
                    get_learning_task_store().save_for_run(learning_task, run_id)
                if event.get("suggested_answer_mode"):
                    suggested_answer_mode = str(event["suggested_answer_mode"])
                if event.get("stage") == "generate" and not generation_handoff_done:
                    generation_handoff_done = True
                    if reason_active:
                        yield activity_sse({
                            "id": "reason", "kind": "reasoning", "label": "综合证据与知识推理",
                            "status": "completed", "detail": "已形成可展示的回答路径",
                            "duration_ms": round((time.perf_counter() - (reason_started_at or time.perf_counter())) * 1000, 2),
                        })
                    else:
                        if evidence_active:
                            yield activity_sse({
                                "id": "evidence", "kind": "evidence", "label": "整理教材证据",
                                "status": "skipped", "detail": "无需额外展开章节内容",
                            })
                        yield activity_sse({
                            "id": "reason", "kind": "reasoning", "label": "综合证据与知识推理",
                            "status": "completed", "detail": "已形成可展示的回答路径",
                        })
                event["conversation_id"] = conversation_id
                event["turn_id"] = turn_id
                if event.get("stage") == "generate":
                    if event.get("evidence_sources") is not None:
                        assistant_sources = event["evidence_sources"]
                    if event.get("replace"):
                        assistant_chunks[:] = [str(event.get("chunk") or "")]
                    elif event.get("chunk"):
                        assistant_chunks.append(str(event.get("chunk")))
                if event.get("stage") == "done":
                    completed_task = _finish_chat_learning_task(
                        learning_task, event.get("state") or {}, run_id=run_id,
                    )
                    if (
                        is_resumable_task_status(completed_task.status)
                        or str(completed_task.artifacts.get("active_run_id") or "") != run_id
                    ):
                        disconnected = True
                        last_stage = "interrupted"
                        return
                    event.setdefault("state", {})["learning_task"] = completed_task.to_dict(public=True)
                    observe(event)
                    persistence_error = persist_assistant()
                    event["message_id"] = assistant_message_id
                    event["subject_suggestion"] = subject_suggestion
                    event["answer_mode"] = answer_mode
                    event["scope_reason"] = scope_reason
                    event["suggested_answer_mode"] = (
                        suggested_answer_mode
                        or str((event.get("state") or {}).get("suggested_answer_mode") or "")
                    )
                    if persistence_error:
                        event["persistence_error"] = persistence_error
                    # 概念标签在 done 阶段才计算完成：补写历史回读所需的快照，避免重抽。
                    concepts = (event.get("state") or {}).get("linked_concepts") or []
                    if concepts and assistant_message_id:
                        try:
                            update_message_linked_concepts(conversation_id, assistant_message_id, concepts[:12])
                        except Exception:
                            logger.exception("concepts persistence failed")
                    support_status = str(
                        ((event.get("state") or {}).get("evidence_support") or {}).get("status") or ""
                    )
                    if support_status and assistant_message_id:
                        try:
                            update_message_evidence_support(
                                conversation_id, assistant_message_id, support_status,
                            )
                            update_ledger_evidence_support(conversation_id, support_status)
                        except Exception:
                            logger.exception("evidence support persistence failed")
                else:
                    observe(event)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("stage") == "plan":
                    yield activity_sse({
                        "id": "retrieve", "kind": "tool", "label": "检索教材上下文",
                        "status": "active", "detail": "正在定位相关章节、定义、公式与例题",
                    })
                elif event.get("stage") == "retrieve":
                    has_chapter_step = (
                        bool(event.get("use_textbook_context", True))
                        and intent in {"teach", "summarize"}
                        and int(event.get("content_count") or 0) > 0
                    )
                    if has_chapter_step:
                        evidence_active = True
                        yield activity_sse({
                            "id": "evidence", "kind": "evidence", "label": "整理教材证据",
                            "status": "active", "detail": "正在准备章节内容与可引用依据",
                        })
                    else:
                        reason_active = True
                        reason_started_at = time.perf_counter()
                        yield activity_sse({
                            "id": "reason", "kind": "reasoning", "label": "综合证据与知识推理",
                            "status": "active", "detail": "正在基于问题与已取得证据组织回答",
                        })
                elif event.get("stage") == "chapter":
                    evidence_active = False
                    reason_active = True
                    reason_started_at = time.perf_counter()
                    yield activity_sse({
                        "id": "reason", "kind": "reasoning", "label": "综合证据与知识推理",
                        "status": "active", "detail": "正在基于章节证据组织讲解结构",
                    })
        except GeneratorExit:
            disconnected = True
            last_stage = "disconnected"
            store = get_learning_task_store()
            current = store.get(learning_task.id)
            if current and str(current.artifacts.get("active_run_id") or "") == run_id:
                interrupted_task = interrupt_learning_task(
                    store, current,
                    stage=str(current.artifacts.get("resume_stage") or last_stage),
                    partial_output="".join(assistant_chunks),
                    expected_run_id=run_id,
                )
                if (
                    is_resumable_task_status(interrupted_task.status)
                    and str(interrupted_task.artifacts.get("active_run_id") or "") == run_id
                ):
                    persist_assistant("partial")
            logger.info("chat stream disconnected", extra={"request_id": request_id})
            raise
        except Exception as exc:
            if not get_learning_task_store().run_is_active(learning_task.id, run_id):
                disconnected = True
                last_stage = "interrupted"
                logger.info("stale chat stream failure ignored", extra={"request_id": request_id})
                return
            logger.exception("chat stream failed", extra={"request_id": request_id})
            pending_actions = list(learning_task.artifacts.get("pending_actions") or [])
            failure_status = "waiting_for_confirmation" if pending_actions else "failed"
            failed_task = get_learning_task_store().checkpoint_for_run(
                learning_task, run_id, "generation_failed", status=failure_status, detail=str(exc),
            )
            if str(failed_task.artifacts.get("active_run_id") or "") != run_id:
                disconnected = True
                last_stage = "interrupted"
                return
            persist_assistant("error")
            event = {
                "stage": "error", "message": str(exc), "done": True,
                "conversation_id": conversation_id, "turn_id": turn_id,
                "learning_task": failed_task.to_dict(public=True),
            }
            observe(event)
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            close = getattr(graph_events, "close", None)
            if close:
                try:
                    close()
                except Exception:
                    logger.exception("failed to close chat graph stream", extra={"request_id": request_id})
            now = time.perf_counter()
            timings.setdefault("total", round((now - started) * 1000, 2))
            try:
                save_trace({
                    "request_id": request_id, "conversation_id": conversation_id,
                    "book_name": book_name, "question": req.question, "intent": intent,
                    "answer_mode": answer_mode, "scope_reason": scope_reason,
                    "fast_path": fast_path,
                    "status": "disconnected" if disconnected else ("error" if last_stage == "error" else "done"),
                    "ttft_ms": ttft_ms, "total_ms": round((now - started) * 1000, 2),
                    "timings": timings, "evidence": final_state.get("retrieval_debug_items", []),
                    "context": _context_trace_payload(
                        resolution_trace, final_state, context_versions,
                    ),
                    "error": final_state.get("error", ""),
                })
            except Exception:
                logger.exception("failed to persist RAG trace", extra={"request_id": request_id})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _chat_stream(
    req: ChatRequest,
    _learning_task: LearningTask | None = None,
    _resume: bool = False,
    _run_id: str = "",
):
    """Open SSE immediately, then prepare the context without a blank TTFB gap."""
    from backend.rag_trace import new_request_id

    request_id = new_request_id()

    async def outer_events():
        preflight = ExecutionEventEmitter(request_id=request_id)
        accepted = preflight.emit(
            "progress",
            phase="context",
            status="started",
            summary="正在读取会话上下文并确认学习范围",
            operation_id="context",
            label="读取会话上下文",
            kind="analysis",
        )
        yield f"data: {json.dumps(execution_sse_payload(accepted), ensure_ascii=False)}\n\n"
        try:
            prepared = await asyncio.to_thread(
                _prepared_chat_stream,
                req,
                _learning_task,
                _resume,
                _run_id,
                request_id,
                int(accepted["seq"]),
            )
            async for chunk in prepared.body_iterator:
                yield chunk
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failed = preflight.emit(
                "error",
                phase="context",
                status="failed",
                summary=str(exc),
                operation_id="context",
                label="读取会话上下文",
                kind="system",
            )
            payload = execution_sse_payload(failed, stage="error")
            payload.update({"done": True, "message": str(exc)})
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        outer_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/stream")
def chat_stream(req: ChatRequest):
    return _chat_stream(req)


@router.post("/tasks/{task_id}/resume-stream")
def resume_chat_task_stream(task_id: str):
    store = get_learning_task_store()
    task = store.get(task_id)
    if task is None or task.task_type != "qa":
        raise HTTPException(status_code=404, detail="learning task not found")
    run_id = f"run_{uuid.uuid4().hex}"
    try:
        task = resume_learning_task(store, task, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    artifacts = task.artifacts or {}
    request = ChatRequest(
        question=str(artifacts.get("resolved_query") or task.goal),
        book_name=str(artifacts.get("book_name") or ""),
        subject=str(artifacts.get("subject") or ""),
        conversation_id=task.conversation_id,
        turn_id=task.turn_id,
        target_chapters=list(artifacts.get("target_chapters") or []),
        answer_mode=task.answer_mode or "auto",
    )
    return _chat_stream(request, _learning_task=task, _resume=True, _run_id=run_id)


@router.post("/tasks/{task_id}/interrupt")
def interrupt_chat_task(task_id: str, payload: dict | None = None):
    """Acknowledge a user stop before the UI exposes the resume action."""
    store = get_learning_task_store()
    task = store.get(task_id)
    if task is None or task.task_type != "qa":
        raise HTTPException(status_code=404, detail="learning task not found")
    body = payload or {}
    if is_interruptible_task_status(task.status):
        task = interrupt_learning_task(
            store,
            task,
            stage=str(body.get("stage") or task.artifacts.get("resume_stage") or "stopped"),
            partial_output=str(body.get("partial_output") or ""),
        )
    public_task = task.to_dict(public=True)
    update_learning_task_projection(task.conversation_id, task.id, public_task)
    return {"success": True, "learning_task": public_task}


@router.post("/ask")
def chat_ask(req: ChatRequest):
    from graph.main_graph import run_graph
    from backend.rag_trace import new_request_id, save_trace

    request_id = new_request_id()
    started = time.perf_counter()
    prepared = _prepare_chat_turn(req)
    book_name = prepared["book_name"]
    subject = prepared["subject"]
    conversation_id = prepared["conversation_id"]
    turn_id = prepared["turn_id"]
    history = prepared["history"]
    rewritten_question = prepared["rewritten_question"]
    resolution_trace = prepared["resolution_trace"]
    target_chapters = prepared["target_chapters"]
    continuity_context = prepared["continuity_context"]
    subject_suggestion = prepared["subject_suggestion"]
    use_textbook_context = prepared["use_textbook_context"]
    scope_reason = prepared["scope_reason"]
    answer_mode = prepared["answer_mode"]
    context_versions = prepared["context_versions"]
    learning_task = _start_chat_learning_task(
        question=req.question, rewritten_question=rewritten_question, history=history,
        conversation_id=conversation_id, turn_id=turn_id, answer_mode=answer_mode,
    )
    continuity_context["learning_task"] = learning_task.to_dict()
    continuity_context["required_outputs"] = learning_task.required_outputs
    user_message = append_message(
        conversation_id, "user", req.question,
        book_name=book_name, subject=subject, turn_id=turn_id,
        request_id=request_id, context_versions=context_versions,
    )
    _safe_save_resolution_ledger(conversation_id, resolution_trace, user_message)

    if resolution_trace.get("resolution_action") in {"clarify", "respond"}:
        result = _clarification_result(
            resolution_trace,
            continuity_context.get("conversation_context_seed"),
        )
    else:
        if answer_mode != "subject_mismatch":
            tool_run = _prepare_main_tool_context(
                rewritten_question, book_name, subject, conversation_id, learning_task.id,
            )
            learning_task = _attach_pending_actions(learning_task, tool_run)
            continuity_context["learning_task"] = learning_task.to_dict()
            tool_pack = dict(tool_run.get("tool_context_pack") or {})
            tool_pack["execution_trace"] = tool_run.get("execution_trace") or {}
            continuity_context["tool_context_pack"] = tool_pack
        result = run_graph(
            user_input=rewritten_question,
            book_name=book_name,
            subject=subject,
            conversation_id=conversation_id,
            target_chapters=target_chapters,
            use_textbook_context=use_textbook_context,
            answer_mode=answer_mode,
            scope_reason=scope_reason,
            continuity_context=continuity_context,
        )
    waiting_reason = str(result.get("final_output") or "") if resolution_trace.get("resolution_action") == "clarify" else ""
    learning_task = _finish_chat_learning_task(learning_task, result, waiting_reason=waiting_reason)
    result["learning_task"] = learning_task.to_dict(public=True)
    content = result.get("final_output", "")
    assistant_message: dict | None = None
    if content.strip():
        assistant_message = _append_assistant_result(
            conversation_id=conversation_id,
            content=content,
            book_name=book_name,
            subject=subject,
            turn_id=turn_id,
            sources=result.get("evidence_sources", []),
            context_versions=context_versions,
            linked_concepts=result.get("linked_concepts", []),
            answer_mode=answer_mode,
            scope_reason=scope_reason,
            suggested_answer_mode=str(result.get("suggested_answer_mode") or ""),
            evidence_support_status=str((result.get("evidence_support") or {}).get("status") or ""),
            request_id=request_id,
            learning_task=learning_task,
        )
        _safe_record_assistant_ledger(conversation_id, assistant_message)

    try:
        save_trace({
            "request_id": request_id,
            "conversation_id": conversation_id,
            "book_name": book_name,
            "question": req.question,
            "intent": result.get("intent", ""),
            "answer_mode": answer_mode,
            "scope_reason": scope_reason,
            "fast_path": False,
            "status": "done",
            "total_ms": round((time.perf_counter() - started) * 1000, 2),
            "timings": {"total": round((time.perf_counter() - started) * 1000, 2)},
            "evidence": result.get("retrieval_debug_items", []),
            "context": _context_trace_payload(resolution_trace, result, context_versions),
            "error": result.get("error", ""),
        })
    except Exception:
        logger.exception("failed to persist non-streaming Context Trace", extra={"request_id": request_id})

    return {
        "request_id": request_id,
        "message_id": str((assistant_message or {}).get("id") or ""),
        "context_versions": context_versions,
        "content": content,
        "intent": result.get("intent", ""),
        "chapters": result.get("target_chapters", []),
        "linked_concepts": result.get("linked_concepts", []),
        "sources": result.get("evidence_sources", []),
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "book_name": book_name,
        "subject": subject,
        "subject_suggestion": subject_suggestion,
        "use_textbook_context": use_textbook_context,
        "scope_reason": scope_reason,
        "answer_mode": answer_mode,
        "suggested_answer_mode": str(result.get("suggested_answer_mode") or ""),
        "rewritten_question": rewritten_question if rewritten_question != req.question else "",
        "resolution_action": str(resolution_trace.get("resolution_action") or "continue"),
        "learning_task": learning_task.to_dict(public=True),
        "chapter_contents": {k: [d[:200] for d in v[:3]] for k, v in result.get("chapter_contents", {}).items()},
    }
