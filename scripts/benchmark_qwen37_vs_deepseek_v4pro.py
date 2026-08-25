"""Controlled Qwen 3.7 Plus vs DeepSeek V4 Pro Texa benchmark.

The default dry run freezes production retrieval, conversation context and
deterministic tool outputs without calling a paid model. Online execution is
explicit and refuses to start unless both credentials are configured.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from dotenv import load_dotenv
import httpx
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.tool_orchestration import (
    ToolOrchestrationRequest,
    execute_read_only_tools,
)
from evaluation.context_eval_v3 import DEFAULT_DATASET, prepare_production_state
from evaluation.context_replay import load_approved_cases
from graph.generator import _build_generate_messages, grounded_failure_message
from graph.planner import INTENT_PROMPT
from graph.teaching_prompts import MINIMAL_TEACHING_PROMPT, MINIMAL_TEACHING_PROMPT_VERSION
from backend.services.multimodal_bridge import VisionModelBridge, build_solution_prompt


OUTPUT = ROOT / "benchmark_results" / "qwen37_vs_deepseek_v4pro_20260825.json"
FIXTURE_OUTPUT = ROOT / "benchmark_results" / "qwen37_vs_deepseek_v4pro_fixture_20260825.json"
PROMPT_BACKUP_OUTPUT = ROOT / "benchmark_results" / "prompt_backups" / "teaching_prompt_legacy_20260825.json"
MODELS = {
    "deepseek-v4-pro": {
        "provider": "deepseek",
        "endpoint": "https://api.deepseek.com/v1",
        "key_names": ("LLM_CREDENTIAL_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"),
        "extra_body": {"thinking": {"type": "enabled"}},
        "reasoning_effort": "high",
    },
    "qwen3.7-plus": {
        "provider": "qwen",
        "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "key_names": ("LLM_CREDENTIAL_QWEN_API_KEY", "DASHSCOPE_API_KEY"),
        "extra_body": {"enable_thinking": True},
    },
}

# Reference pay-as-you-go rates captured from provider documentation on
# 2026-08-25. Provider billing statements remain authoritative. The configured
# DashScope endpoint is the Beijing endpoint, so the <=256K mainland rate is
# used for this fixture. Costs are kept in native billing currency.
PRICING = {
    "deepseek-v4-pro": {
        "currency": "USD", "input_per_million": 0.435,
        "cached_input_per_million": 0.003625, "output_per_million": 0.87,
    },
    "qwen3.7-plus": {
        "currency": "CNY", "input_per_million": 2.0,
        "cached_input_per_million": 0.4, "output_per_million": 8.0,
    },
    "kimi-k2.5": {
        "currency": "CNY", "input_per_million": 4.0,
        "cached_input_per_million": 0.7, "output_per_million": 21.0,
    },
}

VISION_QUESTION = "请读取这张教材题图，完整解答图中的四个小问。公式使用 LaTeX；图中未提供分度表数值时要明确说明，并给出可验证的计算关系。"
VISION_EXPECTED_POINTS = (
    ("补偿导线",),
    ("显示仪表内部", "仪表内部"),
    ("35.0", "35℃", "35\\,^\\circ", "35^\\circ"),
    ("492.4", "492.5"),
)

A_CASE_IDS = (
    "prod_sensor_capacitive_dynamic",
    "prod_sensor_thermistor_features",
    "prod_sensor_piezo_static",
    "prod_error_std_methods_formula_followup",
)
B_CASE_IDS = (
    "prod_followup_capacitive_disadvantages",
    "prod_followup_thermistor_fourth",
    "prod_correction_inductive_high_frequency",
    "prod_error_std_methods_formula_followup",
    "prod_error_std_third_formula",
)
INSUFFICIENT_CASES = (
    {
        "id": "insufficient-market-forecast", "status": "approved", "history": [],
        "query": "教材是否预测了2035年测量仪器的全球市场规模？",
        "book_name": "误差理论与数据处理", "subject": "专业课/误差理论",
        "intent": "factual_recall", "expected": {"support_status": "insufficient"},
    },
    {
        "id": "insufficient-python-version", "status": "approved", "history": [],
        "query": "教材推荐使用哪个版本的Python进行最小二乘计算？",
        "book_name": "误差理论与数据处理", "subject": "专业课/误差理论",
        "intent": "factual_recall", "expected": {"support_status": "insufficient"},
    },
)
TOOL_CASES = (
    {"id": "tool-math", "question": "计算 x^2 在 x=0 到 1 的定积分", "subject": "数学"},
    {"id": "tool-progress", "question": "总结一下我最近的学习进度", "book_name": "误差理论与数据处理", "subject": "专业课"},
    {"id": "tool-none", "question": "什么是随机误差？", "book_name": "误差理论与数据处理", "subject": "专业课"},
)
STRUCTURED_CASES = (
    {"id": "intent-definition", "query": "什么是随机误差？", "expected_intent": "definition"},
    {"id": "intent-calculation", "query": "标准差怎么算？", "expected_intent": "calculation"},
    {"id": "intent-quiz", "query": "按本章内容出三道题", "expected_intent": "quiz"},
    {"id": "intent-followup", "query": "条件呢？", "expected_intent": "qa"},
)
SESSION_TURNS = (
    ("什么是随机误差？", "definition"),
    ("标准差和它有什么关系？", "comparison"),
    ("对应的公式是什么？", "formula"),
    ("公式里的符号分别表示什么？", "formula"),
    ("求标准差的四种方法是什么？", "factual_recall"),
    ("第一个方法怎么算？", "calculation"),
    ("它有什么适用条件？", "property"),
    ("第三个方法呢？", "formula"),
    ("前者和第三个方法有什么区别？", "comparison"),
    ("如果给出一组测量值，应该先做什么？", "application"),
    ("再解释一下为什么标准差不是某次随机误差。", "explanation"),
    ("把这一章刚才讨论的主线总结一下。", "summarize"),
)


def _first_secret(names: tuple[str, ...]) -> str:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return ""


def _messages(state: dict[str, Any]) -> list[dict[str, str]]:
    os.environ["TEXA_TEACHING_PROMPT_MODE"] = "minimal"
    return [
        {"role": "system" if index == 0 else "user", "content": str(item.content)}
        for index, item in enumerate(_build_generate_messages(state))
    ]


def _hash_messages(messages: list[dict[str, str]]) -> str:
    raw = json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _fixture_row(group: str, case: dict[str, Any]) -> dict[str, Any]:
    state, diagnostics = prepare_production_state(case)
    support = str((state.get("evidence_support") or {}).get("status") or "")
    if support in {"insufficient", "unavailable"}:
        return {
            "id": case["id"], "group": group, "model_call": False,
            "production_output": grounded_failure_message(state),
            "resolved_query": diagnostics["resolved_query"],
            "resolution_trace": diagnostics["resolution_trace"],
            "support_status": support,
            "evidence_pack": diagnostics["evidence_pack"],
            "context_pack": diagnostics["context_pack"],
            "expected": case.get("expected") or {},
        }
    messages = _messages(state)
    return {
        "id": case["id"], "group": group, "model_call": True,
        "resolved_query": diagnostics["resolved_query"],
        "resolution_trace": diagnostics["resolution_trace"],
        "support_status": support,
        "evidence_pack": diagnostics["evidence_pack"],
        "context_pack": diagnostics["context_pack"],
        "context_budget": state.get("context_budget") or {},
        "messages": messages,
        "message_sha256": _hash_messages(messages),
        "expected": case.get("expected") or {},
    }


def _tool_fixture(case: dict[str, Any]) -> dict[str, Any]:
    request = ToolOrchestrationRequest(
        question=case["question"], book_name=case.get("book_name", ""),
        subject=case.get("subject", ""), max_tools=6, include_textbook_tool=False,
    )
    run = execute_read_only_tools(request)
    state = {
        "intent": "calculation" if case["id"] == "tool-math" else "qa",
        "user_input": case["question"], "subject": case.get("subject", ""),
        "book_name": case.get("book_name", ""), "use_textbook_context": False,
        "answer_mode": "subject_general", "history_results": [],
        "tool_context_pack": run["tool_context_pack"], "teaching_content": "",
    }
    messages = _messages(state)
    return {
        "id": case["id"], "group": "D_tool_calling", "model_call": True,
        "selected_tools": run["selected_tools"], "tool_outputs": run["tool_outputs"],
        "messages": messages, "message_sha256": _hash_messages(messages),
    }


def _structured_fixture(case: dict[str, Any]) -> dict[str, Any]:
    prompt = INTENT_PROMPT.format(
        chapters="- 第一章 误差基础\n- 第二章 测量误差的统计处理",
        user_input=case["query"], local_hint="无",
    )
    messages = [{"role": "user", "content": prompt}]
    return {
        **case, "group": "E_structured_output", "model_call": True,
        "schema": {"intent": "str", "target_chapters": "list[str]", "confidence": "number", "sub_tasks": "list[object]"},
        "messages": messages, "message_sha256": _hash_messages(messages),
    }


def _session_fixtures() -> list[dict[str, Any]]:
    history: list[dict[str, str]] = []
    rows: list[dict[str, Any]] = []
    canonical_answers = (
        "随机误差是在相同条件下多次测量时，以不可预定方式变化的误差。",
        "标准差用于评定随机误差的分散程度。",
        "标准差公式使用各次偏差的平方和。",
        "σ 表示标准差，δ 表示随机误差。",
        "四种方法是贝塞尔法、别捷尔斯法、极差法、最大误差法。",
        "第一个方法是贝塞尔法。",
        "适用条件需要结合教材公式说明。",
        "第三个方法是极差法。",
        "前者指贝塞尔法。",
        "先确认测量列和适用公式。",
        "标准差描述整组分散程度，不等于一次误差。",
        "本章主线是随机误差及其统计评定。",
    )
    for index, ((query, intent), canonical) in enumerate(zip(SESSION_TURNS, canonical_answers), 1):
        case = {
            "id": f"session-{index:02d}", "status": "approved", "history": list(history),
            "query": query, "book_name": "误差理论与数据处理",
            "subject": "专业课/误差理论", "intent": intent, "expected": {},
        }
        row = _fixture_row("G_session", case)
        row["turn"] = index
        rows.append(row)
        turn_id = f"s{index}"
        history.extend([
            {"role": "user", "content": query, "turn_id": turn_id},
            {"role": "assistant", "content": canonical, "turn_id": turn_id},
        ])
    return rows


def build_fixture() -> dict[str, Any]:
    cases = {item["id"]: item for item in load_approved_cases(DEFAULT_DATASET)}
    rows = [*(_fixture_row("A_textbook_rag", cases[item]) for item in A_CASE_IDS)]
    rows.extend(_fixture_row("B_conversation", cases[item]) for item in B_CASE_IDS)
    rows.extend(_fixture_row("C_evidence_insufficiency", item) for item in INSUFFICIENT_CASES)
    rows.extend(_tool_fixture(case) for case in TOOL_CASES)
    rows.extend(_structured_fixture(case) for case in STRUCTURED_CASES)
    rows.extend(_session_fixtures())
    image_path = ROOT / "data" / "eval" / "image_reasoning_20260813_201703" / "source_ocr.jpg"
    rows.append({
        "id": "vision-textbook-01", "group": "F_vision_textbook",
        "model_call": False, "online_handler": "vision_pipeline",
        "image_path": str(image_path), "image_exists": image_path.exists(),
        "comparison": "qwen3.7-plus native image vs Kimi K2.5 VisualProblemIR then deepseek-v4-pro",
    })
    return {
        "schema_version": 1, "created_at": datetime.now().astimezone().isoformat(),
        "prompt_version": MINIMAL_TEACHING_PROMPT_VERSION,
        "controls": {"temperature": 0.1, "max_tokens": 4096, "repeats": 3, "same_messages_by_case": True},
        "cases": rows,
    }


def write_prompt_backup(path: Path = PROMPT_BACKUP_OUTPUT) -> Path:
    """Preserve exact UTF-8 source snapshots containing the legacy prompt policy."""
    sources = {}
    for relative in ("graph/generator.py", "graph/chapter_subgraph.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        sources[relative] = {
            "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "content": source,
        }
    payload = {
        "created_at": datetime.now().astimezone().isoformat(),
        "legacy_prompt_version": "generator-teaching-units-v1-2026-08-25",
        "note": "Legacy constants and branches remain active by default; this is an exact source snapshot preserved before any paid online model run.",
        "sources": sources,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _usage_value(usage: Any, name: str) -> int:
    return int(getattr(usage, name, 0) or 0) if usage is not None else 0


def _nested_usage_value(usage: Any, parent: str, name: str) -> int:
    details = getattr(usage, parent, None) if usage is not None else None
    return int(getattr(details, name, 0) or 0) if details is not None else 0


def _usage_payload(usage: Any) -> dict[str, int]:
    return {
        "input_tokens": _usage_value(usage, "prompt_tokens"),
        "output_tokens": _usage_value(usage, "completion_tokens"),
        "total_tokens": _usage_value(usage, "total_tokens"),
        "cached_input_tokens": _nested_usage_value(usage, "prompt_tokens_details", "cached_tokens"),
        "reasoning_tokens": _nested_usage_value(usage, "completion_tokens_details", "reasoning_tokens"),
    }


def _estimate_cost(model: str, usage: dict[str, int]) -> dict[str, Any]:
    rates = PRICING[model]
    cached = min(usage.get("cached_input_tokens", 0), usage.get("input_tokens", 0))
    uncached = max(0, usage.get("input_tokens", 0) - cached)
    amount = (
        uncached * rates["input_per_million"]
        + cached * rates["cached_input_per_million"]
        + usage.get("output_tokens", 0) * rates["output_per_million"]
    ) / 1_000_000
    return {
        "currency": rates["currency"], "estimated_amount": round(amount, 8),
        "pricing_basis": "provider_usage_tokens; cache split when reported",
    }


def _invoke(
    model: str,
    messages: list[dict[str, Any]],
    repeat: int,
    *,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    config = MODELS[model]
    key = _first_secret(config["key_names"])
    client = OpenAI(
        api_key=key, base_url=config["endpoint"], timeout=420, max_retries=0,
        http_client=httpx.Client(trust_env=False, timeout=420),
    )
    kwargs: dict[str, Any] = {
        "model": model, "messages": messages, "temperature": 0.1,
        "max_tokens": max_tokens, "stream": True,
        "stream_options": {"include_usage": True},
        "extra_body": dict(config["extra_body"]),
    }
    if config.get("reasoning_effort"):
        kwargs["reasoning_effort"] = config["reasoning_effort"]
    started = time.perf_counter()
    stream = client.chat.completions.create(**kwargs)
    first_token_seconds: float | None = None
    answer_parts: list[str] = []
    reasoning_chars = 0
    usage = None
    finish_reason = None
    for chunk in stream:
        if getattr(chunk, "usage", None) is not None:
            usage = chunk.usage
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        choice = choices[0]
        delta = getattr(choice, "delta", None)
        content = getattr(delta, "content", None) if delta is not None else None
        reasoning = getattr(delta, "reasoning_content", None) if delta is not None else None
        if first_token_seconds is None and (content or reasoning):
            first_token_seconds = time.perf_counter() - started
        if isinstance(content, str):
            answer_parts.append(content)
        if isinstance(reasoning, str):
            reasoning_chars += len(reasoning)
        if getattr(choice, "finish_reason", None):
            finish_reason = choice.finish_reason
    elapsed = time.perf_counter() - started
    answer = "".join(answer_parts)
    usage_payload = _usage_payload(usage)
    return {
        "model": model, "repeat": repeat, "elapsed_seconds": round(elapsed, 3),
        "ttft_seconds": round(first_token_seconds, 3) if first_token_seconds is not None else None,
        "finish_reason": finish_reason, "reasoning_stream_chars": reasoning_chars,
        "usage": usage_payload, "cost": _estimate_cost(model, usage_payload),
        "answer": answer,
    }


def _score(row: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    answer = result["answer"]
    expected = row.get("expected") or {}
    required = expected.get("required_answer_points") or []
    def matched(value: Any) -> bool:
        return any(str(item) in answer for item in value) if isinstance(value, list) else str(value) in answer
    cited = set(re.findall(r"\[\[cite:(E\d+)\]\]", answer))
    valid = {str(item.get("id") or "") for item in (row.get("evidence_pack") or {}).get("items") or []}
    structured = row.get("group") == "E_structured_output"
    parsed: dict[str, Any] | None = None
    parse_error = ""
    if structured:
        try:
            start, end = answer.find("{"), answer.rfind("}")
            parsed = json.loads(answer[start:end + 1])
        except Exception as exc:
            parse_error = f"{type(exc).__name__}: {exc}"
    return {
        "required_point_recall": (
            sum(matched(item) for item in required) / len(required) if required else None
        ),
        "citation_count": len(cited), "invalid_citations": sorted(cited - valid),
        "structured_parse_ok": parsed is not None if structured else None,
        "structured_parse_error": parse_error,
        "structured_intent_match": (
            str((parsed or {}).get("intent") or "") == str(row.get("expected_intent") or "")
            if structured and parsed else None
        ),
        "answer_chars": len(answer),
    }


def _image_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = {".png": "image/png", ".webp": "image/webp"}.get(suffix, "image/jpeg")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _vision_score(answer: str) -> dict[str, Any]:
    matched = [any(value in answer for value in alternatives) for alternatives in VISION_EXPECTED_POINTS]
    return {
        "required_point_recall": sum(matched) / len(matched),
        "matched_points": matched,
        "answer_chars": len(answer),
    }


@contextmanager
def _temporary_env(values: dict[str, str]):
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _extract_with_kimi(image_path: Path) -> tuple[Any, dict[str, Any]]:
    """Run the production VisualProblemIR bridge while capturing its API telemetry."""
    capture: dict[str, Any] = {}
    with _temporary_env({
        "LLM_VISION_PROVIDER": "moonshot",
        "LLM_VISION_MODEL": "kimi-k2.5",
        "LLM_VISION_CREDENTIAL_ID": "moonshot",
        "LLM_VISION_BASE_URL": "https://api.moonshot.cn/v1",
    }):
        bridge = VisionModelBridge()
        original = bridge.client.chat.completions

        class CapturingCompletions:
            def create(self, **kwargs):
                started = time.perf_counter()
                response = original.create(**kwargs)
                capture["elapsed_seconds"] = round(time.perf_counter() - started, 3)
                capture["usage"] = _usage_payload(getattr(response, "usage", None))
                capture["finish_reason"] = response.choices[0].finish_reason
                return response

        bridge.client = SimpleNamespace(
            chat=SimpleNamespace(completions=CapturingCompletions()),
        )
        visual_ir = bridge.analyze(
            image_path, user_question=VISION_QUESTION, subject="传感器与检测技术",
        )
    usage = capture.get("usage") or _usage_payload(None)
    capture.update({
        "model": "kimi-k2.5", "usage": usage,
        "cost": _estimate_cost("kimi-k2.5", usage),
    })
    return visual_ir, capture


def run_vision_online(
    image_path: Path,
    repeats: int,
    *,
    existing_results: list[dict[str, Any]] | None = None,
    retry_errors: bool = False,
    on_progress: Callable[[list[dict[str, Any]]], None] | None = None,
) -> list[dict[str, Any]]:
    if not image_path.exists():
        return [{"error": f"vision fixture missing: {image_path}"}]
    if not _first_secret(("LLM_CREDENTIAL_MOONSHOT_API_KEY", "MOONSHOT_API_KEY")):
        return [{"error": "missing credentials for: kimi-k2.5"}]
    existing_by_repeat = {
        int(item.get("repeat") or 0): item for item in (existing_results or [])
    }
    results: list[dict[str, Any]] = []
    for repeat in range(1, repeats + 1):
        previous = existing_by_repeat.get(repeat) or {}
        qwen = previous.get("qwen_native") if isinstance(previous.get("qwen_native"), dict) else None
        if not qwen or (retry_errors and qwen.get("error")):
            qwen_messages = [
                {"role": "system", "content": MINIMAL_TEACHING_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": VISION_QUESTION},
                    {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                ]},
            ]
            try:
                qwen = _invoke("qwen3.7-plus", qwen_messages, repeat)
                qwen["score"] = _vision_score(qwen["answer"])
            except Exception as exc:
                qwen = {"model": "qwen3.7-plus", "repeat": repeat, "error": f"{type(exc).__name__}: {str(exc)[:1000]}"}
        combo = previous.get("split_combo") if isinstance(previous.get("split_combo"), dict) else None
        if not combo or (retry_errors and combo.get("error")):
            try:
                visual_ir, kimi = _extract_with_kimi(image_path)
                combo = {
                    "pipeline": "kimi-k2.5-visual-ir+deepseek-v4-pro",
                    "repeat": repeat, "visual_ir": visual_ir.to_dict(),
                    "kimi_stage": kimi,
                }
                solution_messages = [
                    {"role": "system", "content": MINIMAL_TEACHING_PROMPT},
                    {"role": "user", "content": build_solution_prompt(
                        visual_ir, user_question=VISION_QUESTION, subject="传感器与检测技术",
                    )},
                ]
                deepseek = _invoke("deepseek-v4-pro", solution_messages, repeat)
                deepseek["score"] = _vision_score(deepseek["answer"])
                combo.update({
                    "deepseek_stage": deepseek,
                    "elapsed_seconds": round(kimi["elapsed_seconds"] + deepseek["elapsed_seconds"], 3),
                    "ttft_seconds": (
                        round(kimi["elapsed_seconds"] + deepseek["ttft_seconds"], 3)
                        if deepseek.get("ttft_seconds") is not None else None
                    ),
                    "score": deepseek["score"],
                })
            except Exception as exc:
                combo = combo or {"pipeline": "kimi-k2.5-visual-ir+deepseek-v4-pro", "repeat": repeat}
                combo["error"] = f"{type(exc).__name__}: {str(exc)[:1000]}"
        results.append({"repeat": repeat, "qwen_native": qwen, "split_combo": combo})
        if on_progress is not None:
            on_progress(results)
        print(f"VISION_PROGRESS repeat={repeat}/{repeats} qwen_error={bool(qwen.get('error'))} combo_error={bool(combo.get('error'))}", flush=True)
    return results


def _model_summary(results: list[dict[str, Any]], model: str) -> dict[str, Any]:
    rows = [item for item in results if item.get("model") == model]
    success = [item for item in rows if "elapsed_seconds" in item]
    usage = {
        name: sum(int((item.get("usage") or {}).get(name) or 0) for item in success)
        for name in ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens", "reasoning_tokens")
    }
    currency = PRICING[model]["currency"]
    return {
        "samples": len(success), "errors": len(rows) - len(success),
        "median_seconds": statistics.median([item["elapsed_seconds"] for item in success]) if success else None,
        "median_ttft_seconds": statistics.median([item["ttft_seconds"] for item in success if item.get("ttft_seconds") is not None]) if any(item.get("ttft_seconds") is not None for item in success) else None,
        "usage": usage, "estimated_cost": {
            "currency": currency,
            "amount": round(sum(float((item.get("cost") or {}).get("estimated_amount") or 0) for item in success), 8),
        },
    }


def _write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    last_error: Exception | None = None
    for attempt in range(12):
        try:
            temporary.write_text(serialized, encoding="utf-8")
            temporary.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.25 * (attempt + 1))
    # A transient reader must never abort paid jobs. Preserve the newest
    # checkpoint beside the stable file and let the next checkpoint retry.
    fallback = path.with_suffix(path.suffix + ".pending")
    fallback.write_text(serialized, encoding="utf-8")
    print(f"CHECKPOINT_WARNING {type(last_error).__name__}: {last_error}", flush=True)


def _result_log_path(output_path: Path) -> Path:
    return output_path.with_suffix(output_path.suffix + ".results.jsonl")


def _result_key(item: dict[str, Any]) -> tuple[str, str, str, int]:
    """Keep identically named cases from different benchmark groups distinct."""
    return (
        str(item.get("group") or ""),
        str(item.get("case_id") or ""),
        str(item.get("model") or ""),
        int(item.get("repeat") or 0),
    )


def _read_result_log(output_path: Path) -> dict[tuple[str, str, str, int], dict[str, Any]]:
    logged: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    path = _result_log_path(output_path)
    if not path.exists():
        return logged
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            logged[_result_key(item)] = item
        except Exception:
            continue
    return logged


def _append_result_log(output_path: Path, result: dict[str, Any]) -> None:
    path = _result_log_path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _preflight_models() -> dict[str, Any]:
    messages = [
        {"role": "system", "content": MINIMAL_TEACHING_PROMPT},
        {"role": "user", "content": "只回复：OK"},
    ]
    results = {}
    for model in MODELS:
        results[model] = _invoke(model, messages, 0, max_tokens=512)
        print(
            f"PREFLIGHT model={model} elapsed={results[model]['elapsed_seconds']} "
            f"ttft={results[model]['ttft_seconds']} output_tokens={results[model]['usage']['output_tokens']}",
            flush=True,
        )
    return results


def run_online(
    fixture: dict[str, Any], repeats: int, workers: int, output_path: Path,
    *, retry_errors: bool = False,
) -> dict[str, Any]:
    missing = [name for name, item in MODELS.items() if not _first_secret(item["key_names"])]
    if missing:
        raise RuntimeError(f"missing credentials for: {', '.join(missing)}")
    preflight = _preflight_models()
    resumed_results: list[dict[str, Any]] = []
    resumed_vision_results: list[dict[str, Any]] = []
    prior_status = ""
    checkpoint_candidates = [
        output_path,
        output_path.with_suffix(output_path.suffix + ".tmp"),
        output_path.with_suffix(output_path.suffix + ".pending"),
    ]
    for checkpoint_path in checkpoint_candidates:
        if not checkpoint_path.exists():
            continue
        try:
            previous = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            candidate_status = str(previous.get("status") or "")
            resumable_statuses = {"running", "partial"}
            if retry_errors:
                resumable_statuses.add("complete")
            if candidate_status in resumable_statuses:
                previous_hashes = {
                    item["id"]: item.get("message_sha256")
                    for item in (previous.get("fixture") or {}).get("cases") or []
                }
                current_hashes = {
                    item["id"]: item.get("message_sha256")
                    for item in fixture["cases"]
                }
                candidate = list(previous.get("results") or [])
                candidate_ids = {str(item.get("case_id") or "") for item in candidate}
                if (
                    len(candidate) > len(resumed_results)
                    and all(previous_hashes.get(case_id) == current_hashes.get(case_id) for case_id in candidate_ids)
                ):
                    resumed_results = candidate
                    prior_status = candidate_status
                    resumed_vision_results = list(previous.get("vision_results") or [])
        except Exception as exc:
            print(f"RESUME_WARNING path={checkpoint_path.name} {type(exc).__name__}: {str(exc)[:500]}", flush=True)
    logged = _read_result_log(output_path)
    if logged:
        existing = {_result_key(item): item for item in resumed_results}
        existing.update(logged)
        resumed_results = list(existing.values())
    if retry_errors:
        resumed_results = [item for item in resumed_results if not item.get("error")]
    completed_keys = {_result_key(item) for item in resumed_results}
    jobs = []
    for row in fixture["cases"]:
        if not row.get("model_call"):
            continue
        for model in MODELS:
            for repeat in range(1, repeats + 1):
                if (row["group"], row["id"], model, repeat) not in completed_keys:
                    jobs.append((row, model, repeat))
    results = list(resumed_results)
    total_jobs = len(results) + len(jobs)
    if resumed_results:
        print(
            f"RESUME_RESULTS saved={len(resumed_results)} missing={len(jobs)} "
            f"prior_status={prior_status}", flush=True,
        )
    base_report = {
        "schema_version": 2, "run_at": datetime.now().astimezone().isoformat(),
        "status": "running", "preflight": preflight,
        "fixture_sha256": hashlib.sha256(json.dumps(fixture, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        "fixture": fixture, "results": results,
        "vision_results": resumed_vision_results,
    }
    _write_checkpoint(output_path, base_report)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        futures = {pool.submit(_invoke, model, row["messages"], repeat): (row, model, repeat) for row, model, repeat in jobs}
        for future in as_completed(futures):
            row, model, repeat = futures[future]
            try:
                result = future.result()
                result.update({"case_id": row["id"], "group": row["group"], "score": _score(row, result)})
            except Exception as exc:
                result = {"case_id": row["id"], "group": row["group"], "model": model, "repeat": repeat, "error": f"{type(exc).__name__}: {str(exc)[:1000]}"}
            results.append(result)
            _append_result_log(output_path, result)
            completed = len(results)
            print(
                f"TEXT_PROGRESS {completed}/{total_jobs} case={row['id']} model={model} "
                f"repeat={repeat} error={bool(result.get('error'))}",
                flush=True,
            )
            base_report["progress"] = {"completed": completed, "total": total_jobs}
            _write_checkpoint(output_path, base_report)
    vision_case = next(item for item in fixture["cases"] if item.get("group") == "F_vision_textbook")
    def checkpoint_vision(partial: list[dict[str, Any]]) -> None:
        base_report["vision_results"] = partial
        _write_checkpoint(output_path, base_report)

    vision_results = run_vision_online(
        Path(vision_case["image_path"]), repeats,
        existing_results=resumed_vision_results,
        retry_errors=retry_errors,
        on_progress=checkpoint_vision,
    )
    has_text_errors = any(item.get("error") for item in results)
    has_vision_errors = any(
        (item.get("qwen_native") or {}).get("error")
        or (item.get("split_combo") or {}).get("error")
        for item in vision_results
    )
    report = {
        **base_report,
        "status": "partial" if has_text_errors or has_vision_errors else "complete",
        "results": results,
        "vision_results": vision_results,
        "model_summary": {model: _model_summary(results, model) for model in MODELS},
        "scope_limitations": [
            "Conversation resolution and tool selection are deterministic in current Texa and are not model-native comparisons.",
            "Evidence-insufficient production cases are rejected before generation and therefore have no model call.",
            "The native vision arm is one Qwen image-to-answer call; the split arm is the production VisualProblemIR extraction followed by DeepSeek reasoning.",
            "The vision fixture does not include the referenced thermocouple appendix table, so numerical lookup behavior is judged with that limitation visible.",
        ],
    }
    _write_checkpoint(output_path, report)
    return report


def rebuild_report_from_log(output_path: Path) -> dict[str, Any]:
    """Rebuild the checkpoint from durable rows without making provider calls."""
    report = json.loads(output_path.read_text(encoding="utf-8"))
    fixture = report.get("fixture") or {}
    merged = {_result_key(item): item for item in report.get("results") or []}
    merged.update(_read_result_log(output_path))
    expected_keys = [
        (row["group"], row["id"], model, repeat)
        for row in fixture.get("cases") or [] if row.get("model_call")
        for model in MODELS
        for repeat in range(1, int((fixture.get("controls") or {}).get("repeats") or 3) + 1)
    ]
    results = [merged[key] for key in expected_keys if key in merged]
    missing = [key for key in expected_keys if key not in merged]
    vision_results = report.get("vision_results") or []
    has_errors = bool(missing) or any(item.get("error") for item in results) or any(
        (item.get("qwen_native") or {}).get("error")
        or (item.get("split_combo") or {}).get("error")
        for item in vision_results
    )
    report.update({
        "status": "partial" if has_errors else "complete",
        "results": results,
        "progress": {"completed": len(results), "total": len(expected_keys)},
        "model_summary": {model: _model_summary(results, model) for model in MODELS},
        "rebuild": {
            "source": str(_result_log_path(output_path)),
            "expected": len(expected_keys),
            "restored": len(results),
            "missing": [list(key) for key in missing],
        },
    })
    _write_checkpoint(output_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--confirm-paid-model", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume-errors", action="store_true")
    parser.add_argument("--rebuild-from-log", action="store_true")
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--fixture-output", default=str(FIXTURE_OUTPUT))
    args = parser.parse_args()
    if args.rebuild_from_log:
        report = rebuild_report_from_log(Path(args.output))
        print(json.dumps({
            "output": args.output,
            "status": report["status"],
            "result_count": len(report["results"]),
            "rebuild": report["rebuild"],
        }, ensure_ascii=False, indent=2))
        return 0
    if args.online and not args.confirm_paid_model:
        parser.error("--online requires --confirm-paid-model")
    load_dotenv(ROOT / ".env")
    prompt_backup = write_prompt_backup()
    output = Path(args.output)
    fixture = None
    if args.online and output.exists():
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
            allowed_statuses = {"running", "partial"}
            if args.resume_errors:
                allowed_statuses.add("complete")
            if str(previous.get("status") or "") in allowed_statuses:
                fixture = previous.get("fixture")
                if fixture:
                    print(f"REUSE_FROZEN_FIXTURE source={output}", flush=True)
        except Exception as exc:
            print(f"FIXTURE_REUSE_WARNING {type(exc).__name__}: {str(exc)[:500]}", flush=True)
    fixture = fixture or build_fixture()
    fixture_path = Path(args.fixture_output)
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.online:
        print(json.dumps({
            "fixture": str(fixture_path), "prompt_backup": str(prompt_backup),
            "case_count": len(fixture["cases"]),
            "model_call_cases": sum(bool(item.get("model_call")) for item in fixture["cases"]),
            "qwen_credential_configured": bool(_first_secret(MODELS["qwen3.7-plus"]["key_names"])),
            "deepseek_credential_configured": bool(_first_secret(MODELS["deepseek-v4-pro"]["key_names"])),
        }, ensure_ascii=False, indent=2))
        return 0
    report = run_online(
        fixture, max(1, args.repeats), args.workers, output,
        retry_errors=args.resume_errors,
    )
    print(json.dumps({"output": str(output), "result_count": len(report["results"]), "model_summary": report["model_summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
