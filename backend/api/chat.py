"""Chat API: SSE streaming and non-streaming dialogue."""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.conversation_memory import (
    append_message,
    ensure_conversation_id,
    ensure_turn_id,
    get_conversation,
    list_conversations,
    load_history,
    resolve_conversation_id_for_scope,
    reclassify_conversation,
    rewrite_followup,
    split_turn_to_conversation,
)
from backend.schemas import ChatRequest, ConversationScopeRequest, ConversationSplitTurnRequest, SubjectRoutingFeedbackRequest
from backend.services.subject_routing import record_subject_routing_feedback, suggest_subject_scope

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

def _safe_subject_suggestion(question: str, subject: str, book_name: str) -> dict | None:
    try:
        return suggest_subject_scope(question, subject, book_name)
    except Exception:
        logger.exception("subject routing suggestion failed")
        return None



def _safe_record_subject_feedback(source: str, target: str, action: str) -> None:
    try:
        record_subject_routing_feedback(source, target, action)
    except Exception:
        logger.exception("subject routing feedback persistence failed")

@router.get("/conversations")
def conversations(subject: str = "", book_name: str = "", limit: int = 80):
    return {"success": True, "data": list_conversations(subject=subject, book_name=book_name, limit=limit)}


@router.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: str):
    conversation_id = ensure_conversation_id(conversation_id)
    return {"success": True, "data": get_conversation(conversation_id)}


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
        append_message(conversation_id, role, content, book_name=book_name, subject=subject, turn_id=str(item.get("turn_id") or turn_id))
        appended += 1
    return {"success": True, "conversation_id": conversation_id, "appended": appended}


@router.post("/stream")
def chat_stream(req: ChatRequest):
    from graph.main_graph import run_graph_stream

    book_name = (req.book_name or "").strip()
    subject = (req.subject or "").strip()
    conversation_id = resolve_conversation_id_for_scope(req.conversation_id, subject, book_name)
    turn_id = ensure_turn_id(req.turn_id)
    history = load_history(conversation_id)
    subject_suggestion = _safe_subject_suggestion(req.question, subject, book_name)
    # Do not retrieve from a known-wrong textbook while the user decides
    # whether to move the turn or relabel the conversation.
    use_textbook_context = bool(book_name) and subject_suggestion is None
    rewritten_question = rewrite_followup(req.question, history, book_name=book_name, subject=subject)

    def event_generator():
        from backend.rag_trace import new_request_id, save_trace

        request_id = new_request_id()
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

        def persist_assistant() -> str:
            nonlocal assistant_persisted, assistant_persistence_error
            if assistant_persisted:
                return assistant_persistence_error

            content = "".join(assistant_chunks)
            if not content.strip():
                assistant_persisted = True
                assistant_persistence_error = ""
                return ""

            try:
                append_message(conversation_id, "assistant", content, book_name=book_name, subject=subject, turn_id=turn_id)
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
            if stage == "generate" and event.get("chunk") and ttft_ms is None:
                ttft_ms = round((now - started) * 1000, 2)
                timings["generate_ttft"] = round((now - (generation_started or started)) * 1000, 2)
                event["ttft_ms"] = ttft_ms
            if stage == "done":
                final_state = event.get("state") or {}
                stage_ms = round((now - (generation_started or last_milestone_at)) * 1000, 2)
                timings["generate"] = stage_ms
                timings["total"] = round((now - started) * 1000, 2)
                event["stage_ms"] = stage_ms
                event["timings"] = dict(timings)
            last_stage = stage
            event["request_id"] = request_id
            event["elapsed_ms"] = round((now - started) * 1000, 2)

        graph_events = None
        try:
            yield f"data: {json.dumps({'stage': 'context', 'request_id': request_id, 'conversation_id': conversation_id, 'turn_id': turn_id, 'rewritten_question': rewritten_question if rewritten_question != req.question else ''}, ensure_ascii=False)}\n\n"
            append_message(conversation_id, "user", req.question, book_name=book_name, subject=subject, turn_id=turn_id)
            context_finished = time.perf_counter()
            timings["context"] = round((context_finished - started) * 1000, 2)
            last_milestone_at = context_finished
            graph_events = run_graph_stream(
                user_input=rewritten_question,
                book_name=book_name,
                subject=subject,
                conversation_id=conversation_id,
                target_chapters=req.target_chapters or [],
                use_textbook_context=use_textbook_context,
            )
            for event in graph_events:
                observe(event)
                event["conversation_id"] = conversation_id
                event["turn_id"] = turn_id
                if event.get("stage") == "generate":
                    if event.get("replace"):
                        assistant_chunks[:] = [str(event.get("chunk") or "")]
                    elif event.get("chunk"):
                        assistant_chunks.append(str(event.get("chunk")))
                    if event.get("done"):
                        persist_assistant()
                if event.get("stage") == "done":
                    persistence_error = persist_assistant()
                    event["subject_suggestion"] = subject_suggestion
                    if persistence_error:
                        event["persistence_error"] = persistence_error
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            logger.info("chat stream disconnected", extra={"request_id": request_id})
            raise
        except Exception as exc:
            logger.exception("chat stream failed", extra={"request_id": request_id})
            event = {"stage": "error", "message": str(exc), "done": True, "conversation_id": conversation_id, "turn_id": turn_id}
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
                    "fast_path": fast_path, "status": "error" if last_stage == "error" else "done",
                    "ttft_ms": ttft_ms, "total_ms": round((now - started) * 1000, 2),
                    "timings": timings, "evidence": final_state.get("retrieval_debug_items", []),
                    "error": final_state.get("error", ""),
                })
            except Exception:
                logger.exception("failed to persist RAG trace", extra={"request_id": request_id})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/ask")
def chat_ask(req: ChatRequest):
    from graph.main_graph import run_graph

    book_name = (req.book_name or "").strip()
    subject = (req.subject or "").strip()
    conversation_id = resolve_conversation_id_for_scope(req.conversation_id, subject, book_name)
    turn_id = ensure_turn_id(req.turn_id)
    history = load_history(conversation_id)
    subject_suggestion = _safe_subject_suggestion(req.question, subject, book_name)
    use_textbook_context = bool(book_name) and subject_suggestion is None
    rewritten_question = rewrite_followup(req.question, history, book_name=book_name, subject=subject)
    append_message(conversation_id, "user", req.question, book_name=book_name, subject=subject, turn_id=turn_id)

    result = run_graph(
        user_input=rewritten_question,
        book_name=book_name,
        subject=subject,
        conversation_id=conversation_id,
        target_chapters=req.target_chapters or [],
        use_textbook_context=use_textbook_context,
    )
    content = result.get("final_output", "")
    if content.strip():
        append_message(conversation_id, "assistant", content, book_name=book_name, subject=subject, turn_id=turn_id)

    return {
        "content": content,
        "intent": result.get("intent", ""),
        "chapters": result.get("target_chapters", []),
        "linked_concepts": result.get("linked_concepts", []),
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "subject_suggestion": subject_suggestion,
        "rewritten_question": rewritten_question if rewritten_question != req.question else "",
        "chapter_contents": {k: [d[:200] for d in v[:3]] for k, v in result.get("chapter_contents", {}).items()},
    }
