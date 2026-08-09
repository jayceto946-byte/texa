"""Planner / Router — 意图识别 + 任务拆解 + 路由决策

2026-06-04 更新：
- 支持细粒度意图（definition/formula/property/derivation/comparison/application/...）
- 接受本地分类器的 hint，减少 LLM 猜测
- Fast Path：simple intent 跳过本节点的 LLM 调用
"""
from __future__ import annotations

import json
import time

from langchain_core.callbacks import BaseCallbackHandler

from config import get_llm


def _safe_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _usage_value(usage: dict, *keys: str):
    for key in keys:
        value = usage.get(key)
        if value is not None:
            return _safe_int(value, value)
    return None


class _PlannerTokenTimer(BaseCallbackHandler):
    """Capture the first streamed Planner token without storing token text."""

    def __init__(self):
        self.first_token_at: float | None = None

    def on_llm_new_token(self, token, **kwargs) -> None:  # pragma: no cover - provider callback
        if self.first_token_at is None:
            self.first_token_at = time.perf_counter()


def _planner_response_telemetry(response, llm, *, api_started: float, first_token_at: float | None) -> dict:
    usage = dict(getattr(response, "usage_metadata", None) or {})
    metadata = dict(getattr(response, "response_metadata", None) or {})
    token_usage = dict(metadata.get("token_usage") or {})
    if not usage:
        usage = token_usage

    output_details = dict(usage.get("output_token_details") or {})
    completion_details = dict(token_usage.get("completion_tokens_details") or {})
    headers = dict(metadata.get("headers") or {})
    retry_value = next((
        value for key, value in headers.items()
        if str(key).lower() in {"x-stainless-retry-count", "x-retry-count"}
    ), None)
    request_id = next((
        value for key, value in headers.items()
        if str(key).lower() in {"x-request-id", "request-id"}
    ), "")

    return {
        "model": str(metadata.get("model_name") or getattr(llm, "model_name", "") or ""),
        "input_tokens": _usage_value(usage, "input_tokens", "prompt_tokens"),
        "output_tokens": _usage_value(usage, "output_tokens", "completion_tokens"),
        "total_tokens": _usage_value(usage, "total_tokens"),
        "reasoning_tokens": (
            _usage_value(output_details, "reasoning")
            or _usage_value(completion_details, "reasoning_tokens")
        ),
        "finish_reason": str(metadata.get("finish_reason") or ""),
        "first_token_ms": round((first_token_at - api_started) * 1000, 2) if first_token_at else None,
        "retry_count": _safe_int(retry_value),
        "request_id": str(request_id or ""),
    }

INTENT_PROMPT = """你是一个考研学习规划师。分析用户意图，只返回 JSON。

## 可用意图类型（细粒度）
- definition: 问定义/概念（什么是XX？）
- factual_recall: textbook facts, reasons, features, advantages/disadvantages, or enumerated points
- formula: 问公式/表达式（XX公式是什么？）
- property: 问性质/定理（XX有什么性质？）
- calculation: 问公式如何代入、变量如何计算或通用计算方法（XX怎么算？）
- derivation: 推导/证明（怎么推导XX？证明XX？）
- comparison: 比较/区别（XX和YY的区别？）
- application: 应用/计算题（用XX解这道题/计算XX）
- teach: 系统讲解（给我讲XX）
- summarize: 总结/概括（总结XX）
- quiz: 出题测验（出几道XX的题）
- plan: 学习规划（怎么学XX）
- cross_chapter: 跨章节关联问题
- qa: 通用问答（无法归入以上类别）

## 本地分类器提示（供参考，LLM 可覆盖）
{local_hint}

## 已知章节（target_chapters 必须从这些精确名称中选取，不能自行构造小节标题）
{chapters}

## 用户输入
{user_input}

只返回 JSON（不要其他内容）:
{{"intent": "...", "target_chapters": ["..."], "confidence": 0.9, "sub_tasks": [{{"step": 1, "action": "retrieve", "chapter": "..."}}]}}

注意：target_chapters 必须是"已知章节"列表中的精确名称，不要返回小节标题或自行构造的章节名。
"""


def plan_node(state: dict) -> dict:
    """Planner节点：意图识别 + 任务拆解 + 路由

    如果 state 中已有 _local_intent（Fast Path 未命中但本地有 hint），
    将其传入 LLM prompt 减少猜测。
    """
    from graph.safe_retrieval import get_safe_vector_store

    plan_enter = time.perf_counter()
    planner_trace = {
        "mode": "llm",
        "prompt_build_ms": 0.0,
        "api_request_start_ms": None,
        "api_response_elapsed_ms": None,
        "api_response_end_ms": None,
        "first_token_ms": None,
        "response_parse_ms": 0.0,
        "retry_count": None,
        "plan_total_ms": 0.0,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "reasoning_tokens": None,
        "finish_reason": "",
        "model": "",
        "parse_fallback": False,
        "chapter_fallback_ms": 0.0,
    }
    user_input = state.get("user_input", "")
    if not user_input:
        planner_trace.update({
            "mode": "empty_input",
            "plan_total_ms": round((time.perf_counter() - plan_enter) * 1000, 2),
        })
        return {
            "intent": "qa", "target_chapters": [], "sub_tasks": [],
            "error": "empty input", "planner_trace": planner_trace,
        }

    if not state.get("use_textbook_context", True):
        intent = state.get("_local_intent", "qa") or "qa"
        planner_trace.update({
            "mode": "general_qa_bypass",
            "plan_total_ms": round((time.perf_counter() - plan_enter) * 1000, 2),
        })
        return {
            "intent": intent,
            "target_chapters": [],
            "sub_tasks": [],
            "route_decision": intent,
            "retrieval_status": "ordinary_qa",
            "retrieval_error": "",
            "planner_trace": planner_trace,
        }

    retrieval_errors = []
    if state.get("retrieval_error"):
        retrieval_errors.append(str(state.get("retrieval_error")))

    vector_started = time.perf_counter()
    vs, vector_error = get_safe_vector_store()
    planner_trace["vector_store_ms"] = round((time.perf_counter() - vector_started) * 1000, 2)
    if vector_error:
        retrieval_errors.append(f"vector_store: {vector_error}")
    chapter_names_started = time.perf_counter()
    try:
        chapters = vs.get_chapter_names(book_name=state.get("book_name", ""))
    except Exception as exc:
        chapters = []
        retrieval_errors.append(f"chapter_names: {exc}")
    planner_trace["chapter_names_ms"] = round((time.perf_counter() - chapter_names_started) * 1000, 2)
    planner_trace["chapter_count"] = len(chapters)

    # 读取本地分类器 hint（如果有）
    local_hint = state.get("_local_intent_hint", "无")

    try:
        llm = get_llm(include_response_headers=True, stream_usage=True)
    except TypeError:  # test doubles and non-ChatOpenAI backends
        llm = get_llm()
    prompt_started = time.perf_counter()
    prompt = INTENT_PROMPT.format(
        chapters="\n".join(f"- {c}" for c in chapters) if chapters else "（无章节）",
        user_input=user_input,
        local_hint=local_hint,
    )
    planner_trace["prompt_chars"] = len(prompt)
    planner_trace["prompt_build_ms"] = round((time.perf_counter() - prompt_started) * 1000, 2)

    token_timer = _PlannerTokenTimer()
    api_started = time.perf_counter()
    planner_trace["api_request_start_ms"] = round((api_started - plan_enter) * 1000, 2)
    try:
        response = llm.invoke(prompt, config={"callbacks": [token_timer]})
    except TypeError:  # narrow compatibility fallback for simple test doubles
        response = llm.invoke(prompt)
    api_finished = time.perf_counter()
    planner_trace["api_response_elapsed_ms"] = round((api_finished - api_started) * 1000, 2)
    planner_trace["api_response_end_ms"] = round((api_finished - plan_enter) * 1000, 2)
    planner_trace.update(_planner_response_telemetry(
        response, llm, api_started=api_started, first_token_at=token_timer.first_token_at,
    ))
    result = str(response.content or "").strip()

    parse_started = time.perf_counter()
    if result.startswith("```"):
        result = result.split("\n", 1)[-1].rsplit("\n", 1)[0]

    try:
        plan = json.loads(result)
    except json.JSONDecodeError:
        # 降级：如果本地有分类结果，直接用它
        fallback_intent = state.get("_local_intent", "qa")
        plan = {
            "intent": fallback_intent,
            "target_chapters": chapters[:1] if chapters else [],
            "sub_tasks": [],
        }
        planner_trace["parse_fallback"] = True
    planner_trace["response_parse_ms"] = round((time.perf_counter() - parse_started) * 1000, 2)

    intent = plan.get("intent", "qa")
    if state.get("_local_intent_locked"):
        intent = state.get("_local_intent", intent) or intent
        planner_trace["intent_locked"] = True
    target_chapters = plan.get("target_chapters", [])
    sub_tasks = plan.get("sub_tasks", [])

    # 如果 planner 没指定章节，用向量检索找
    if not target_chapters and chapters:
        chapter_fallback_started = time.perf_counter()
        target_chapters = _find_relevant_chapters(user_input, chapters, vs, book_name=state.get("book_name", ""))
        planner_trace["chapter_fallback_ms"] = round((time.perf_counter() - chapter_fallback_started) * 1000, 2)

    # 为 teach/summarize 意图构建分步任务
    if intent in ("teach", "summarize") and not sub_tasks and target_chapters:
        ch = target_chapters[0]
        sub_tasks = [
            {"step": 1, "action": "retrieve", "description": f"获取{ch}内容", "chapter": ch},
            {"step": 2, "action": "extract_keypoints", "description": "提炼重点概念", "chapter": ch},
            {"step": 3, "action": "teach", "description": "生成讲解", "chapter": ch},
            {"step": 4, "action": "summarize", "description": "生成总结", "chapter": ch},
        ]
        if intent == "teach":
            sub_tasks.append({"step": 5, "action": "quiz", "description": "生成练习题", "chapter": ch})

    planner_trace["plan_total_ms"] = round((time.perf_counter() - plan_enter) * 1000, 2)
    return {
        "intent": intent,
        "target_chapters": target_chapters,
        "sub_tasks": sub_tasks,
        "route_decision": intent,
        "retrieval_status": "degraded" if retrieval_errors else state.get("retrieval_status", "ok"),
        "retrieval_error": "; ".join(dict.fromkeys(retrieval_errors)),
        "planner_trace": planner_trace,
    }


def _find_relevant_chapters(question: str, chapters: list[str], vs, book_name: str = "") -> list[str]:
    """用向量检索找相关章节"""
    try:
        all_results = vs.search_all(question, k=1, book_name=book_name)
    except Exception:
        return []
    return list(all_results.keys())[:3]
