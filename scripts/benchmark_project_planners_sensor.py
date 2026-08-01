"""Benchmark DeepSeek models through the project's real planner/RAG prompts."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime
from pathlib import Path

import config


ROOT = Path(__file__).resolve().parents[1]
JSON_OUTPUT = ROOT / "benchmark_results" / "project_planners_sensor_20260801.json"
MD_OUTPUT = ROOT / "benchmark_results" / "project_planners_sensor_20260801.md"
BOOK_NAME = "传感器短书"
SUBJECT = "传感器"
MODELS = ("deepseek-v4-flash", "deepseek-v4-pro")
QUESTIONS = (
    ("simple_qa", "什么是传感器的迟滞？"),
    ("comparison", "金属电阻应变片和半导体应变片有什么区别？"),
    ("teach", "给我讲一讲压电式传感器的等效电路与测量电路。"),
)
PRICES = {
    "deepseek-v4-flash": {"hit": 0.02, "miss": 1.0, "output": 2.0},
    "deepseek-v4-pro": {"hit": 0.025, "miss": 3.0, "output": 6.0},
}


def prompt_kind(prompt: object) -> str:
    text = str(prompt)
    markers = (
        ("你是一个考研学习规划师", "planner"),
        ("基于以下章节内容，提取考研重点", "extract_keypoints"),
        ("基于以下章节内容，生成 3 道选择题", "quiz"),
        ("请基于以下教材内容，讲解", "teach"),
        ("请基于以下信息回答用户问题", "generate"),
        ("You are a postgraduate-study assistant", "general_qa"),
    )
    return next((kind for marker, kind in markers if marker in text), "other")


def token_usage(message: object) -> dict:
    usage = getattr(message, "usage_metadata", None) or {}
    response_meta = getattr(message, "response_metadata", None) or {}
    raw = response_meta.get("token_usage") or response_meta.get("usage") or {}
    details = raw.get("completion_tokens_details") or {}
    return {
        "prompt_tokens": int(raw.get("prompt_tokens", usage.get("input_tokens", 0)) or 0),
        "prompt_cache_hit_tokens": int(raw.get("prompt_cache_hit_tokens", 0) or 0),
        "prompt_cache_miss_tokens": int(raw.get("prompt_cache_miss_tokens", 0) or 0),
        "completion_tokens": int(raw.get("completion_tokens", usage.get("output_tokens", 0)) or 0),
        "reasoning_tokens": int(details.get("reasoning_tokens", 0) or 0),
        "total_tokens": int(raw.get("total_tokens", usage.get("total_tokens", 0)) or 0),
    }


class TrackingLLM:
    def __init__(self, base, model: str, temperature: float, records: list, lock):
        self.base = base
        self.model = model
        self.temperature = temperature
        self.records = records
        self.lock = lock

    def _record_start(self, prompt: object, mode: str) -> dict:
        text = str(prompt)
        return {
            "model": self.model,
            "kind": prompt_kind(text),
            "mode": mode,
            "temperature": self.temperature,
            "prompt": text,
            "prompt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "started_at": datetime.now().astimezone().isoformat(),
        }

    def _record_finish(self, record: dict, started: float, message: object) -> None:
        record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        record["usage"] = token_usage(message)
        with self.lock:
            self.records.append(record)

    def invoke(self, prompt: object, *args, **kwargs):
        record = self._record_start(prompt, "invoke")
        started = time.perf_counter()
        try:
            response = self.base.invoke(prompt, *args, **kwargs)
        except Exception as exc:
            record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            record["error"] = f"{type(exc).__name__}: {exc}"
            with self.lock:
                self.records.append(record)
            raise
        self._record_finish(record, started, response)
        return response

    def stream(self, prompt: object, *args, **kwargs):
        record = self._record_start(prompt, "stream")
        started = time.perf_counter()
        aggregate = None
        try:
            kwargs.setdefault("stream_usage", True)
            for chunk in self.base.stream(prompt, *args, **kwargs):
                aggregate = chunk if aggregate is None else aggregate + chunk
                yield chunk
        except Exception as exc:
            record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            record["error"] = f"{type(exc).__name__}: {exc}"
            with self.lock:
                self.records.append(record)
            raise
        self._record_finish(record, started, aggregate)


def aggregate_usage(calls: list[dict]) -> dict:
    keys = (
        "prompt_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "completion_tokens",
        "reasoning_tokens",
        "total_tokens",
    )
    return {key: sum(call.get("usage", {}).get(key, 0) for call in calls) for key in keys}


def calculate_cost(model: str, usage: dict) -> dict:
    price = PRICES[model]
    hit = usage["prompt_cache_hit_tokens"]
    miss = usage["prompt_cache_miss_tokens"]
    if hit == 0 and miss == 0:
        miss = usage["prompt_tokens"]
    components = {
        "cache_hit_input": hit * price["hit"] / 1_000_000,
        "cache_miss_input": miss * price["miss"] / 1_000_000,
        "output": usage["completion_tokens"] * price["output"] / 1_000_000,
    }
    return {"components": components, "total": sum(components.values())}


def run_model(model: str) -> list[dict]:
    import graph.chapter_subgraph as chapter_module
    import graph.feedback_node as feedback_module
    import graph.generator as generator_module
    import graph.main_graph as main_module
    import graph.planner as planner_module
    from knowledge.summary_store import SummaryStore

    original_model = config.DEEPSEEK_MODEL_NAME
    original_get_llm = config.get_llm
    original_planner_get_llm = planner_module.get_llm
    original_chapter_get_llm = chapter_module.get_llm
    original_generator_get_llm = generator_module.get_llm
    original_feedback = feedback_module.feedback_node
    original_summary_get = SummaryStore.get
    original_summary_set = SummaryStore.set
    records: list[dict] = []
    lock = threading.Lock()
    wrappers: dict[float, TrackingLLM] = {}

    config.DEEPSEEK_MODEL_NAME = model
    config.clear_llm_cache()

    def tracked_get_llm(temperature=1):
        key = float(temperature)
        if key not in wrappers:
            wrappers[key] = TrackingLLM(original_get_llm(temperature), model, key, records, lock)
        return wrappers[key]

    try:
        config.get_llm = tracked_get_llm
        planner_module.get_llm = tracked_get_llm
        chapter_module.get_llm = tracked_get_llm
        generator_module.get_llm = tracked_get_llm
        feedback_module.feedback_node = lambda state: {}
        SummaryStore.get = lambda self, chapter: None
        SummaryStore.set = lambda self, chapter, data: None

        results = []
        for category, question in QUESTIONS:
            before = len(records)
            started = time.perf_counter()
            state = {}
            error = ""
            try:
                for event in main_module.run_graph_stream(
                    user_input=question,
                    book_name=BOOK_NAME,
                    subject=SUBJECT,
                    conversation_id="",
                    target_chapters=[],
                    use_textbook_context=True,
                ):
                    if event.get("stage") == "done":
                        state = event.get("state") or {}
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            elapsed = round(time.perf_counter() - started, 3)
            question_calls = records[before:]
            usage = aggregate_usage(question_calls)
            results.append({
                "category": category,
                "question": question,
                "model": model,
                "intent": state.get("intent", ""),
                "target_chapters": state.get("target_chapters", []),
                "elapsed_seconds": elapsed,
                "answer": state.get("final_output", ""),
                "error": error or state.get("error", ""),
                "llm_call_count": len(question_calls),
                "llm_calls": question_calls,
                "usage": usage,
                "cost_cny": calculate_cost(model, usage),
            })
        return results
    finally:
        config.get_llm = original_get_llm
        planner_module.get_llm = original_planner_get_llm
        chapter_module.get_llm = original_chapter_get_llm
        generator_module.get_llm = original_generator_get_llm
        feedback_module.feedback_node = original_feedback
        SummaryStore.get = original_summary_get
        SummaryStore.set = original_summary_set
        config.DEEPSEEK_MODEL_NAME = original_model
        config.clear_llm_cache()


def render_markdown(artifact: dict) -> str:
    lines = [
        "# 项目 Planner 传感器问答基准",
        "",
        f"- 运行时间：{artifact['run_at']}",
        f"- 教材：{BOOK_NAME}",
        f"- 学科：{SUBJECT}",
        "- 思考模式：enabled",
        "- reasoning_effort：high",
        "- 回答正文均已由项目 ThinkingFilter 过滤",
        "",
    ]
    titles = {"simple_qa": "简单问答", "comparison": "对比", "teach": "教导"}
    for category, question in QUESTIONS:
        lines.extend([f"## {titles[category]}", "", f"**问题：** {question}", ""])
        for model in MODELS:
            item = next(row for row in artifact["results"] if row["category"] == category and row["model"] == model)
            lines.extend([
                f"### {model}",
                "",
                f"- Planner intent：{item['intent']}；章节：{' / '.join(item['target_chapters'])}",
                f"- 总耗时：{item['elapsed_seconds']:.3f} 秒；LLM 调用：{item['llm_call_count']} 次；费用：¥{item['cost_cny']['total']:.6f}",
                f"- Tokens：输入 {item['usage']['prompt_tokens']}，输出 {item['usage']['completion_tokens']}，其中 reasoning {item['usage']['reasoning_tokens']}",
                "",
                item["answer"] or f"> 未取得回答：{item['error']}",
                "",
            ])
    return "\n".join(lines)


def main() -> None:
    all_results = []
    for model in MODELS:
        all_results.extend(run_model(model))
    artifact = {
        "run_at": datetime.now().astimezone().isoformat(),
        "book_name": BOOK_NAME,
        "subject": SUBJECT,
        "models": list(MODELS),
        "questions": [{"category": category, "question": question} for category, question in QUESTIONS],
        "prompt_fidelity": (
            "Produced by graph.main_graph.run_graph_stream with the real planner, "
            "retrieval, GENERATE_PROMPT and TEACH_PROMPT. Only learning-memory "
            "writes and summary-cache reads/writes were disabled in-process."
        ),
        "results": all_results,
    }
    JSON_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_OUTPUT.write_text(render_markdown(artifact), encoding="utf-8")
    print(json.dumps({
        "json": str(JSON_OUTPUT),
        "markdown": str(MD_OUTPUT),
        "results": [{
            "category": item["category"],
            "model": item["model"],
            "intent": item["intent"],
            "chapters": item["target_chapters"],
            "elapsed_seconds": item["elapsed_seconds"],
            "llm_calls": item["llm_call_count"],
            "usage": item["usage"],
            "cost_cny": item["cost_cny"]["total"],
            "answer_chars": len(item["answer"]),
            "error": item["error"],
        } for item in all_results],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
