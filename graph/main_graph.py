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

    graph.add_edge(START, "plan")
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
    result = graph.invoke(initial_state)
    return result


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
    """流式运行 graph pipeline，yield 事件供 UI 消费。

    事件格式:
        {"stage": "plan",     "intent": str, "chapters": list, "fast_path": bool}
        {"stage": "retrieve", "content_count": int}
        {"stage": "chapter",  "has_teaching": bool}
        {"stage": "generate", "chunk": str, "done": bool}
        {"stage": "done",     "state": dict, "enriched": bool}
    """
    from graph.intent_classifier import classify_intent_local, is_fast_path_eligible
    from graph.planner import plan_node
    from graph.retrieval_node import retrieve_node
    from graph.chapter_subgraph import (
        prepare_chapter_subgraph, TEACH_PROMPT, _future_result_if_done,
    )
    from graph.generator import _build_generate_messages, _format_quiz_appendix, _record_context_budget, finalize_answer_verification, grounded_failure_message, has_generation_support, has_textbook_evidence, scope_boundary_message, suggested_fallback_mode
    from graph.conversation_context import prepare_conversation_context
    from graph.feedback_node import feedback_node, link_concepts_for_response
    from knowledge.summary_store import SummaryStore
    from utils.latex_sanitizer import sanitize_latex
    from utils.citation_protocol import sanitize_citation_protocol
    from utils.thinking_filter import ThinkingFilter
    from config import get_llm

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

    reusable = dict(resume_state or {})
    if reusable:
        for key in (
            "intent", "target_chapters", "chapter_contents", "evidence_items", "evidence_sources",
            "retrieval_status", "retrieval_error", "evidence_support", "retrieval_debug_items",
        ):
            if key in reusable:
                state[key] = reusable[key]

    # ── Step 0: 本地意图分类 ──
    plan_enter = time.perf_counter()
    local_result = classify_intent_local(user_input)
    fast_path = is_fast_path_eligible(user_input, local_result)
    intent = str(state.get("intent") or local_result["intent"])

    if reusable and state.get("intent"):
        yield {
            "stage": "plan", "intent": intent, "chapters": state.get("target_chapters", []),
            "fast_path": True, "resumed": True, "planner_trace": {"mode": "resume_checkpoint"},
            "use_textbook_context": state.get("use_textbook_context", True),
            "answer_mode": state.get("answer_mode", ""),
        }
    elif fast_path:
        # Fast Path：跳过 plan LLM，直接用本地分类结果
        state["intent"] = intent
        state["planner_trace"] = {
            "mode": "fast_path",
            "model": "deterministic",
            "chapter_fallback_ms": 0.0,
            "chapter_lookup_skipped": True,
            "plan_total_ms": round((time.perf_counter() - plan_enter) * 1000, 2),
        }
        yield {
            "stage": "plan",
            "intent": intent,
            "chapters": state.get("target_chapters", []),
            "fast_path": True,
            "planner_trace": state["planner_trace"],
            "use_textbook_context": state.get("use_textbook_context", True),
            "answer_mode": state.get("answer_mode", ""),
        }
    else:
        # 正常路径：把本地分类结果作为 hint 传给 plan_node
        state["_local_intent"] = intent
        state["_local_intent_hint"] = local_result["hint"]
        state["_local_intent_locked"] = bool(local_result.get("intent_locked"))
        plan_result = yield from _run_blocking_with_progress(
            lambda: plan_node(state),
            phase="planning",
            operation_id="understand",
            label="理解问题与确定范围",
            summary="问题范围分析仍在进行，正在等待可验证的规划结果",
        )
        state.update(plan_result)
        intent = state.get("intent", "qa")
        yield {
            "stage": "plan",
            "intent": intent,
            "chapters": state.get("target_chapters", []),
            "fast_path": False,
            "planner_trace": state.get("planner_trace", {}),
            "use_textbook_context": state.get("use_textbook_context", True),
            "answer_mode": state.get("answer_mode", ""),
        }

    # ── Retrieve ──
    if not reusable:
        retrieval_result = yield from _run_blocking_with_progress(
            lambda: retrieve_node(state),
            phase="retrieval",
            operation_id="retrieve",
            label="检索教材上下文",
            summary="仍在检索和筛选教材证据",
        )
        state.update(retrieval_result)
    yield {
        "stage": "retrieve",
        "content_count": len(state.get("chapter_contents", {})),
        "retrieval_status": state.get("retrieval_status", "ok"),
        "retrieval_error": state.get("retrieval_error", ""),
        "use_textbook_context": state.get("use_textbook_context", True),
        "answer_mode": state.get("answer_mode", ""),
        "resumed": bool(reusable),
        "checkpoint_state": {
            key: state.get(key) for key in (
                "intent", "target_chapters", "chapter_contents", "evidence_items", "evidence_sources",
                "retrieval_status", "retrieval_error", "evidence_support", "retrieval_debug_items",
            )
        },
    }

    # ── Chapter subgraph (条件) ──
    if (
        state.get("use_textbook_context", True)
        and intent in ("teach", "summarize")
        and has_textbook_evidence(state)
    ):
        # 获取内容 + 启动后台任务
        content, chapter, book_name_sub, executor, futures = prepare_chapter_subgraph(state)

        if content == "（无内容）":
            # 空字符串让后续 generate 阶段 fallback 到正常 QA 流程
            state["teaching_content"] = ""
            yield {
                "stage": "chapter",
                "has_teaching": False,
            }
        else:
            yield {
                "stage": "chapter",
                "has_teaching": True,
            }

            # 流式生成 teach 内容
            llm = get_llm()
            conversation_text, _conversation_pack = prepare_conversation_context(state)
            teach_prompt = TEACH_PROMPT.format(
                chapter=chapter,
                content=content[:6000],
                conversation_context=conversation_text,
            )
            _record_context_budget(
                state,
                teach_prompt,
                assembly_mode="teach",
                # The current TEACH_PROMPT receives chapter content, not the
                # raw user query; keep the telemetry faithful to that input.
                query_text=str(state.get("user_input") or ""),
                teaching_text=content[:6000],
            )
            buffer = ""
            tf = ThinkingFilter()
            visible_started = False
            for item_type, value in _iterate_stream_with_progress(
                lambda: llm.stream(teach_prompt),
                phase="generation",
                operation_id="reason",
                label="组织讲解路径",
                summary="仍在等待推理服务返回可展示的讲解内容",
            ):
                if item_type == "progress":
                    if not visible_started:
                        yield value
                    continue
                chunk = value
                text = tf.filter(chunk.content)
                if text:
                    visible_started = True
                    buffer += text
                    yield {"stage": "generate", "chunk": text, "done": False}
            # flush 剩余非 thinking 内容
            final_flush = tf.flush()
            if final_flush:
                buffer += final_flush
                yield {"stage": "generate", "chunk": final_flush, "done": False}

            # 清洗 LaTeX 定界符，避免前端 KaTeX 报红。流式 chunk 已经发出，
            # 若清洗结果不同，需要发 replace 事件让前端用最终全文替换。
            sanitized_teaching = sanitize_latex(buffer)
            sanitized_teaching, citation_trace = sanitize_citation_protocol(
                sanitized_teaching,
                state.get("evidence_sources") or [],
            )
            state["citation_trace"] = citation_trace
            verified_teaching = finalize_answer_verification(
                state, sanitized_teaching, citation_trace=citation_trace,
            )
            if verified_teaching != buffer:
                yield {"stage": "generate", "chunk": verified_teaching, "replace": True, "done": False}
            state["teaching_content"] = verified_teaching
            state["chapter_summary"] = ""

            # 收集后台任务结果。后台任务不阻塞主讲解；没完成就跳过。
            kp = _future_result_if_done(futures, "keypoints", "")
            key_points = kp.split("\n") if kp else []
            quiz_questions = _future_result_if_done(futures, "quiz", [])

            if executor:
                executor.shutdown(wait=False, cancel_futures=True)

            state["key_points"] = key_points
            state["quiz_questions"] = quiz_questions

            # 缓存结果
            ss = SummaryStore(book_name_sub)
            ss.set(chapter, {
                "summary": "",
                "key_points": key_points,
                "teaching": buffer[:2000],
            })

    # ── Generate (流式) ──
    if intent in ("teach", "summarize") and state.get("teaching_content"):
        # teach 内容已经在上面流式生成了，这里直接标记完成
        content = state["teaching_content"]
        chapter_summary = state.get("chapter_summary", "")
        if chapter_summary and intent == "summarize":
            content = chapter_summary
        elif chapter_summary:
            content += f"\n\n---\n\n## 章节总结\n{chapter_summary}"
        state["final_output"] = sanitize_latex(content)
        yield {"stage": "generate", "chunk": "", "done": True, "evidence_sources": state.get("evidence_sources", [])}
    else:
        if state.get("answer_mode") == "subject_mismatch":
            buffer = scope_boundary_message(state)
            _record_context_budget(
                state, "", assembly_mode="subject_mismatch_no_generation", query_text="",
            )
            state["final_output"] = buffer
            yield {"stage": "generate", "chunk": buffer, "done": False}
            yield {"stage": "generate", "chunk": "", "done": True, "evidence_sources": []}
        elif state.get("use_textbook_context", True) and not has_generation_support(state):
            buffer = grounded_failure_message(state)
            _record_context_budget(
                state, "", assembly_mode="grounded_refusal_no_generation", query_text="",
            )
            state["suggested_answer_mode"] = suggested_fallback_mode(state)
            state["final_output"] = buffer
            yield {"stage": "generate", "chunk": buffer, "done": False, "suggested_answer_mode": state["suggested_answer_mode"]}
            yield {"stage": "generate", "chunk": "", "done": True, "evidence_sources": state.get("evidence_sources", []), "suggested_answer_mode": state["suggested_answer_mode"]}
        else:
            prompt = _build_generate_messages(state)
            try:
                llm = get_llm(temperature=0.1 if state.get("use_textbook_context", True) else 1)
            except TypeError:
                llm = get_llm()
            buffer = ""
            tf = ThinkingFilter()
            visible_started = False
            for item_type, value in _iterate_stream_with_progress(
                lambda: llm.stream(prompt),
                phase="generation",
                operation_id="reason",
                label="组织回答",
                summary="仍在等待推理服务返回可展示内容",
            ):
                if item_type == "progress":
                    if not visible_started:
                        yield value
                    continue
                chunk = value
                text = tf.filter(chunk.content)
                if text:
                    visible_started = True
                    buffer += text
                    yield {"stage": "generate", "chunk": text, "done": False}
            final_flush = tf.flush()
            if final_flush:
                buffer += final_flush
                yield {"stage": "generate", "chunk": final_flush, "done": False}
            quiz_appendix = _format_quiz_appendix(state)
            if quiz_appendix:
                buffer += quiz_appendix
                yield {"stage": "generate", "chunk": quiz_appendix, "done": False}
            sanitized_output = sanitize_latex(buffer)
            sanitized_output, citation_trace = sanitize_citation_protocol(
                sanitized_output,
                state.get("evidence_sources") or [],
            )
            state["citation_trace"] = citation_trace
            verified_output = finalize_answer_verification(
                state, sanitized_output, citation_trace=citation_trace,
            )
            if verified_output != buffer:
                yield {"stage": "generate", "chunk": verified_output, "replace": True, "done": False}
            state["final_output"] = verified_output
            yield {"stage": "generate", "chunk": "", "done": True, "evidence_sources": state.get("evidence_sources", [])}

    # UI concept links are resolved locally. Learning-memory writes are
    # best-effort background work and must never delay or replace the answer.
    state["conversation_context_seed"] = {}
    state["linked_concepts"] = link_concepts_for_response(state)

    def _record_feedback() -> None:
        try:
            feedback_node(dict(state))
        except Exception as exc:
            print(f"[feedback] background record failed: {exc}", flush=True)

    threading.Thread(target=_record_feedback, name="chat-feedback", daemon=True).start()
    yield {"stage": "done", "state": state, "enriched": False}
