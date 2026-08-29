"""LangGraph 主图 — 总调度器，支持条件路由加速 QA

2026-06-04 更新：
- 接入细粒度意图分类器（intent_classifier）
- Fast Path：definition/formula/property 跳过 plan LLM
- 集成 ConceptMemory：回答后自动提取概念 + 附加学习提醒
"""
import queue
import threading
import time
from langgraph.graph import StateGraph, START, END
from graph.state import AgentState
from graph.planner import plan_node
from graph.retrieval_node import retrieve_node
from graph.chapter_subgraph import chapter_subgraph_run
from graph.generator import generate_node
from graph.feedback_node import feedback_node


def _route_after_retrieve(state: dict) -> str:
    """条件路由：teach/summarize 走 chapter subgraph，其余直接 generate"""
    intent = state.get("intent", "qa")
    if not state.get("use_textbook_context", True):
        return "generate"
    return "chapter" if intent in ("teach", "summarize") else "generate"


def _route_from_start(state: dict) -> str:
    if state.get("resume_phase") == "post_retrieve":
        return _route_after_retrieve(state)
    return "plan"


def build_main_graph() -> StateGraph:
    """构建考研学习主图

    流程:
      START -> plan -> retrieve -> [chapter ->] generate -> feedback -> END
      qa/quiz/plan/cross_chapter: 跳过 chapter，直接 generate（省 2-3 次 LLM 调用）
      teach/summarize: 走完整 chapter subgraph
    """
    graph = StateGraph(AgentState)

    graph.add_node("plan", plan_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("chapter", chapter_subgraph_run)
    graph.add_node("generate", generate_node)
    graph.add_node("feedback", feedback_node)

    graph.add_conditional_edges(START, _route_from_start, {
        "plan": "plan",
        "chapter": "chapter",
        "generate": "generate",
    })
    graph.add_edge("plan", "retrieve")
    graph.add_conditional_edges("retrieve", _route_after_retrieve, {
        "chapter": "chapter",
        "generate": "generate",
    })
    graph.add_edge("chapter", "generate")
    graph.add_edge("generate", "feedback")
    graph.add_edge("feedback", END)

    return graph.compile()


# 全局编译好的图实例（单例）
_main_graph = None
PROGRESS_INTERVAL_SECONDS = 10.0


def _run_blocking_with_progress(
    action,
    *,
    phase: str,
    operation_id: str,
    label: str,
    summary: str,
    interval_seconds: float | None = None,
):
    """Run blocking orchestration work while yielding neutral elapsed progress."""
    result_queue: queue.Queue = queue.Queue(maxsize=1)

    def execute() -> None:
        try:
            result_queue.put(("done", action()))
        except Exception as exc:
            result_queue.put(("error", exc))

    threading.Thread(target=execute, name=f"graph-{phase}-progress", daemon=True).start()
    interval = max(0.01, float(interval_seconds or PROGRESS_INTERVAL_SECONDS))
    waiting_started = time.perf_counter()
    while True:
        try:
            status, value = result_queue.get(timeout=interval)
        except queue.Empty:
            yield {
                "stage": "progress",
                "phase": phase,
                "operation_id": operation_id,
                "label": label,
                "kind": "evidence" if phase == "retrieval" else "analysis",
                "message": summary,
                "waited_ms": round((time.perf_counter() - waiting_started) * 1000, 2),
            }
            continue
        if status == "error":
            raise value
        return value


def _iterate_stream_with_progress(
    stream_factory,
    *,
    phase: str,
    operation_id: str,
    label: str,
    summary: str,
    interval_seconds: float | None = None,
):
    """Move a blocking provider iterator off the SSE producer thread."""
    item_queue: queue.Queue = queue.Queue()
    stop_requested = threading.Event()

    def execute() -> None:
        iterator = None
        try:
            iterator = iter(stream_factory())
            for item in iterator:
                if stop_requested.is_set():
                    break
                item_queue.put(("item", item))
            item_queue.put(("done", None))
        except Exception as exc:
            item_queue.put(("error", exc))
        finally:
            close = getattr(iterator, "close", None)
            if close:
                try:
                    close()
                except Exception:
                    pass

    threading.Thread(target=execute, name=f"graph-{phase}-stream", daemon=True).start()
    interval = max(0.01, float(interval_seconds or PROGRESS_INTERVAL_SECONDS))
    waiting_started = time.perf_counter()
    try:
        while True:
            try:
                status, value = item_queue.get(timeout=interval)
            except queue.Empty:
                yield "progress", {
                    "stage": "progress",
                    "phase": phase,
                    "operation_id": operation_id,
                    "label": label,
                    "kind": "reasoning",
                    "message": summary,
                    "waited_ms": round((time.perf_counter() - waiting_started) * 1000, 2),
                }
                continue
            if status == "done":
                return
            if status == "error":
                raise value
            yield "item", value
    finally:
        stop_requested.set()


def get_graph() -> StateGraph:
    global _main_graph
    if _main_graph is None:
        _main_graph = build_main_graph()
    return _main_graph


def build_initial_state(
    user_input: str,
    book_name: str = "default",
    subject: str = "",
    conversation_id: str = "",
    user_images: list[str] = None,
    user_feedback: dict = None,
    target_chapters: list[str] = None,
    use_textbook_context: bool | None = None,
    answer_mode: str = "",
    scope_reason: str = "",
    continuity_context: dict | None = None,
) -> dict:
    """构建 LangGraph 的初始状态字典。"""
    continuity = continuity_context if isinstance(continuity_context, dict) else {}
    return {
        "user_input": user_input,
        "user_images": user_images or [],
        "user_profile": {},
        "learning_progress": {},
        "long_term_memory": {},
        "book_name": book_name,
        "subject": subject,
        "conversation_id": conversation_id,
        "use_textbook_context": bool(book_name) if use_textbook_context is None else use_textbook_context,
        "answer_mode": answer_mode or ("textbook_grounded" if (bool(book_name) if use_textbook_context is None else use_textbook_context) else ("subject_general" if subject else "global_general")),
        "scope_reason": scope_reason,
        "active_evidence_sources": list(continuity.get("active_evidence_sources") or [])[:12],
        "active_evidence_ids": list(continuity.get("active_evidence_ids") or [])[:12],
        "active_evidence_support": str(continuity.get("active_evidence_support") or ""),
        "active_evidence_invalidation_reason": str(continuity.get("active_evidence_invalidation_reason") or ""),
        "same_topic": bool(continuity.get("same_topic")),
        "requires_new_facet": bool(continuity.get("requires_new_facet")),
        "previous_intent": str(continuity.get("previous_intent") or ""),
        "previous_book_name": str(continuity.get("previous_book_name") or ""),
        "previous_subject": str(continuity.get("previous_subject") or ""),
        "conversation_context_seed": dict(continuity.get("conversation_context_seed") or {}),
        "conversation_context_pack": {},
        "learning_context_pack": dict(continuity.get("learning_context_pack") or {}),
        "tool_context_pack": dict(continuity.get("tool_context_pack") or {}),
        "learning_task": dict(continuity.get("learning_task") or {}),
        "required_outputs": list(continuity.get("required_outputs") or []),
        "answer_verification": {},
        "messages": [],
        "intent": "",
        "_local_intent": "qa",
        "_local_intent_hint": "无",
        "_local_intent_locked": False,
        "sub_tasks": [],
        "target_chapters": target_chapters or [],
        "route_decision": "",
        "planner_trace": {},
        "chapter_contents": {},
        "retrieval_debug_items": [],
        "evidence_items": [],
        "evidence_sources": [],
        "evidence_support": {},
        "evidence_gate_applied": False,
        "suggested_answer_mode": "",
        "citation_trace": {},
        "index_stats": {},
        "concept_results": [],
        "history_results": [],
        "knowledge_graph_path": [],
        "knowledge_graph_formulas": [],
        "matched_concepts": [],
        "linked_concepts": [],
        "retrieval_status": "ok",
        "retrieval_error": "",
        "retrieval_action": "none",
        "retrieval_query": "",
        "reused_evidence_ids": [],
        "new_evidence_ids": [],
        "dropped_evidence_ids": [],
        "teaching_content": "",
        "key_points": [],
        "extracted_examples": [],
        "quiz_questions": [],
        "chapter_summary": "",
        "final_output": "",
        "output_type": "text",
        "context_budget": {},
        "user_feedback": user_feedback,
        "mastery_update": {},
        "next_review": None,
        "error": "",
        "iteration": 0,
        "max_iterations": 10,
        "resume_phase": "",
        "resume_checkpoint_version": 1,
    }


def run_graph(user_input: str, book_name: str = "default",
              subject: str = "",
              conversation_id: str = "",
              user_images: list[str] = None,
              user_feedback: dict = None,
              target_chapters: list[str] = None,
              use_textbook_context: bool | None = None,
              answer_mode: str = "",
              scope_reason: str = "",
              continuity_context: dict | None = None) -> dict:
    """运行一次完整的图谱推理（同步阻塞版）。"""
    graph = get_graph()
    initial_state = build_initial_state(
        user_input=user_input,
        book_name=book_name,
        subject=subject,
        conversation_id=conversation_id,
        user_images=user_images,
        user_feedback=user_feedback,
        target_chapters=target_chapters,
        use_textbook_context=use_textbook_context,
        answer_mode=answer_mode,
        scope_reason=scope_reason,
        continuity_context=continuity_context,
    )
    return graph.invoke(initial_state)


def _validated_resume_state(resume_state: dict | None, book_name: str) -> dict:
    if not isinstance(resume_state, dict) or not resume_state:
        return {}
    required = {
        "intent", "target_chapters", "chapter_contents", "evidence_items",
        "evidence_sources", "retrieval_status", "evidence_support",
    }
    if any(key not in resume_state for key in required):
        return {}

    checkpoint_version = str(
        resume_state.get("index_version")
        or (resume_state.get("index_stats") or {}).get("index_version")
        or ""
    )
    if checkpoint_version and book_name and book_name != "default":
        try:
            from ingestion.index_pipeline import load_index_manifest

            active_version = str(load_index_manifest(book_name).get("index_version") or "")
        except Exception:
            return {}
        if active_version and active_version != checkpoint_version:
            return {}

    reusable_keys = (
        "intent", "target_chapters", "chapter_contents", "evidence_items", "evidence_sources",
        "retrieval_status", "retrieval_error", "evidence_support", "retrieval_debug_items",
        "evidence_gate_applied", "suggested_answer_mode", "index_stats", "retrieval_action",
        "retrieval_query", "reused_evidence_ids", "new_evidence_ids", "dropped_evidence_ids",
    )
    return {key: resume_state[key] for key in reusable_keys if key in resume_state}


def _stream_item_parts(item) -> tuple[str, object]:
    if isinstance(item, tuple) and len(item) == 2 and item[0] in {"messages", "updates"}:
        return str(item[0]), item[1]
    return "updates", item


def _message_stream_parts(payload) -> tuple[object | None, dict]:
    if isinstance(payload, (tuple, list)) and len(payload) == 2:
        message, metadata = payload
        return message, metadata if isinstance(metadata, dict) else {}
    return None, {}


def _answer_chunk(message) -> str:
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""


def run_graph_stream(
    user_input: str,
    book_name: str = "default",
    subject: str = "",
    conversation_id: str = "",
    user_images: list[str] = None,
    user_feedback: dict = None,
    target_chapters: list[str] = None,
    use_textbook_context: bool | None = None,
    answer_mode: str = "",
    scope_reason: str = "",
    continuity_context: dict | None = None,
    resume_state: dict | None = None,
):
    """Adapt one compiled-graph execution into transport-level progress events."""
    state = build_initial_state(
        user_input=user_input,
        book_name=book_name,
        subject=subject,
        conversation_id=conversation_id,
        user_images=user_images,
        user_feedback=user_feedback,
        target_chapters=target_chapters,
        use_textbook_context=use_textbook_context,
        answer_mode=answer_mode,
        scope_reason=scope_reason,
        continuity_context=continuity_context,
    )
    reusable = _validated_resume_state(resume_state, book_name)
    if reusable:
        state.update(reusable)
        state["resume_phase"] = "post_retrieve"
        yield {
            "stage": "plan",
            "intent": state.get("intent", "qa"),
            "chapters": state.get("target_chapters", []),
            "fast_path": True,
            "resumed": True,
            "planner_trace": {"mode": "resume_checkpoint"},
            "use_textbook_context": state.get("use_textbook_context", True),
            "answer_mode": state.get("answer_mode", ""),
        }
        yield {
            "stage": "retrieve",
            "content_count": len(state.get("chapter_contents") or {}),
            "retrieval_status": state.get("retrieval_status", "ok"),
            "retrieval_error": state.get("retrieval_error", ""),
            "use_textbook_context": state.get("use_textbook_context", True),
            "answer_mode": state.get("answer_mode", ""),
            "resumed": True,
            "checkpoint_state": dict(reusable),
        }

    graph = get_graph()
    answer_chunks: list[str] = []
    chapter_announced = False
    generation_done = False

    graph_stream = lambda: graph.stream(
        state,
        stream_mode=["messages", "updates"],
    )
    for item_type, raw_item in _iterate_stream_with_progress(
        graph_stream,
        phase="execution",
        operation_id="execute",
        label="执行学习任务",
        summary="主执行图仍在处理当前学习任务",
    ):
        if item_type == "progress":
            yield raw_item
            continue

        mode, payload = _stream_item_parts(raw_item)
        if mode == "messages":
            message, metadata = _message_stream_parts(payload)
            node = str(metadata.get("langgraph_node") or "")
            if node not in {"chapter", "generate"}:
                continue
            text = _answer_chunk(message)
            if not text:
                continue
            if node == "chapter" and not chapter_announced:
                chapter_announced = True
                yield {"stage": "chapter", "has_teaching": True}
            answer_chunks.append(text)
            yield {"stage": "generate", "chunk": text, "done": False}
            continue

        if not isinstance(payload, dict):
            continue
        for node, update in payload.items():
            if not isinstance(update, dict):
                continue
            state.update(update)
            if node == "plan":
                trace = state.get("planner_trace") or {}
                yield {
                    "stage": "plan",
                    "intent": state.get("intent", "qa"),
                    "chapters": state.get("target_chapters", []),
                    "fast_path": trace.get("mode") == "fast_path",
                    "planner_trace": trace,
                    "use_textbook_context": state.get("use_textbook_context", True),
                    "answer_mode": state.get("answer_mode", ""),
                }
            elif node == "retrieve":
                checkpoint_state = {
                    key: state.get(key) for key in (
                        "intent", "target_chapters", "chapter_contents", "evidence_items",
                        "evidence_sources", "retrieval_status", "retrieval_error",
                        "evidence_support", "retrieval_debug_items", "evidence_gate_applied",
                        "suggested_answer_mode", "index_stats", "retrieval_action",
                        "retrieval_query", "reused_evidence_ids", "new_evidence_ids",
                        "dropped_evidence_ids",
                    )
                }
                checkpoint_state["index_version"] = str(
                    (state.get("index_stats") or {}).get("index_version") or ""
                )
                yield {
                    "stage": "retrieve",
                    "content_count": len(state.get("chapter_contents") or {}),
                    "retrieval_status": state.get("retrieval_status", "ok"),
                    "retrieval_error": state.get("retrieval_error", ""),
                    "use_textbook_context": state.get("use_textbook_context", True),
                    "answer_mode": state.get("answer_mode", ""),
                    "resumed": False,
                    "checkpoint_state": checkpoint_state,
                }
            elif node == "chapter":
                if not chapter_announced:
                    chapter_announced = True
                    yield {
                        "stage": "chapter",
                        "has_teaching": bool(state.get("teaching_content")),
                    }
            elif node == "generate":
                final_output = str(state.get("final_output") or "")
                streamed_output = "".join(answer_chunks)
                if final_output and not streamed_output:
                    answer_chunks[:] = [final_output]
                    yield {"stage": "generate", "chunk": final_output, "done": False}
                elif final_output != streamed_output:
                    answer_chunks[:] = [final_output]
                    yield {
                        "stage": "generate",
                        "chunk": final_output,
                        "replace": True,
                        "done": False,
                    }
                generation_done = True
                yield {
                    "stage": "generate",
                    "chunk": "",
                    "done": True,
                    "evidence_sources": state.get("evidence_sources", []),
                    "suggested_answer_mode": state.get("suggested_answer_mode", ""),
                }

    if not generation_done:
        final_output = str(state.get("final_output") or "")
        if final_output:
            yield {"stage": "generate", "chunk": final_output, "done": False}
        yield {
            "stage": "generate",
            "chunk": "",
            "done": True,
            "evidence_sources": state.get("evidence_sources", []),
            "suggested_answer_mode": state.get("suggested_answer_mode", ""),
        }
    yield {"stage": "done", "state": state, "enriched": False}
