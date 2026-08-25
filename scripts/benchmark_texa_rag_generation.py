"""Controlled DeepSeek Flash/Pro comparison using Texa's real EvidencePack."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graph.generator import _build_generate_messages
from graph.retrieval_node import retrieve_node

OUTPUT = ROOT / "benchmark_results" / "texa_rag_flash_vs_pro_20260824.json"
BOOK = "误差理论与数据处理"
QUESTION = "标准差和随机误差之间的联系"
MODELS = ("deepseek-v4-flash", "deepseek-v4-pro")


def _field(obj, name: str, default=0):
    value = getattr(obj, name, default)
    return default if value is None else value


def _state() -> dict:
    state = {
        "user_input": QUESTION,
        "book_name": BOOK,
        "subject": "专业课/误差理论",
        "intent": "comparison",
        "target_chapters": [],
        "use_textbook_context": True,
        "retrieval_error": "",
        "history_results": [],
        "teaching_content": "",
    }
    state.update(retrieve_node(state))
    return state


def _assessment(answer: str, valid_ids: set[str]) -> dict:
    cited = set(re.findall(r"\[\[cite:(E\d+)\]\]", answer))
    return {
        "mentions_both_objects": "标准差" in answer and "随机误差" in answer,
        "states_relationship": any(marker in answer for marker in ("评定", "反映", "表征", "衡量", "关系", "联系")),
        "false_no_evidence_refusal": any(marker in answer for marker in (
            "未检索到足够", "找不到依据", "没有找到能够直接支持", "教材没有提供",
        )),
        "citation_count": len(re.findall(r"\[\[cite:E\d+\]\]", answer)),
        "invalid_citation_ids": sorted(cited - valid_ids),
        "markdown_heading_count": len(re.findall(r"(?m)^#{1,6}\s", answer)),
        "bold_span_count": len(re.findall(r"\*\*[^*]+\*\*", answer)),
        "answer_chars": len(answer),
    }


def _call(client: OpenAI, model: str, messages: list[dict], valid_ids: set[str]) -> dict:
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 8192,
        "stream": False,
        "extra_body": {"user_id": f"texa-rag-controlled-{model}-20260824"},
    }
    if model.endswith("-pro"):
        kwargs["reasoning_effort"] = "high"
        kwargs["extra_body"]["thinking"] = {"type": "enabled"}
    started = time.perf_counter()
    response = client.chat.completions.create(**kwargs)
    elapsed = time.perf_counter() - started
    message = response.choices[0].message
    usage = response.usage
    details = _field(usage, "completion_tokens_details", None)
    answer = message.content or ""
    return {
        "model_requested": model,
        "model_returned": response.model,
        "finish_reason": response.choices[0].finish_reason,
        "elapsed_seconds": round(elapsed, 3),
        "usage": {
            "prompt_tokens": int(_field(usage, "prompt_tokens")),
            "prompt_cache_hit_tokens": int(_field(usage, "prompt_cache_hit_tokens")),
            "prompt_cache_miss_tokens": int(_field(usage, "prompt_cache_miss_tokens")),
            "completion_tokens": int(_field(usage, "completion_tokens")),
            "reasoning_tokens": int(_field(details, "reasoning_tokens")) if details else 0,
            "total_tokens": int(_field(usage, "total_tokens")),
        },
        "assessment": _assessment(answer, valid_ids),
        "answer": answer,
        "reasoning_content_saved": False,
    }


def main() -> None:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
    endpoint = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")

    retrieval_started = time.perf_counter()
    state = _state()
    retrieval_seconds = time.perf_counter() - retrieval_started
    support = state.get("evidence_support") or {}
    if support.get("status") != "supported":
        raise RuntimeError(f"controlled EvidencePack is not supported: {support}")
    langchain_messages = _build_generate_messages(state)
    messages = [
        {"role": "system" if index == 0 else "user", "content": item.content}
        for index, item in enumerate(langchain_messages)
    ]
    prompt_bytes = json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    evidence_sources = state.get("evidence_sources") or []
    valid_ids = {str(item.get("id") or "") for item in evidence_sources}
    client = OpenAI(api_key=api_key, base_url=endpoint, timeout=300.0)
    results = [_call(client, model, messages, valid_ids) for model in MODELS]

    artifact = {
        "run_at": datetime.now().astimezone().isoformat(),
        "question": QUESTION,
        "book": BOOK,
        "comparison_controls": {
            "same_messages": True,
            "message_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
            "message_roles": [item["role"] for item in messages],
            "system_chars": len(messages[0]["content"]),
            "human_chars": len(messages[1]["content"]),
            "tool_context_injected": bool(state.get("context_budget", {}).get("tool_context_injected")),
            "temperature": 0.1,
            "max_tokens": 8192,
            "stream": False,
            "model_runtime_options": {
                "deepseek-v4-flash": "production registry default (no explicit thinking option)",
                "deepseek-v4-pro": "production registry default (thinking enabled, reasoning_effort high)",
            },
        },
        "retrieval": {
            "elapsed_seconds": round(retrieval_seconds, 3),
            "support": support,
            "evidence_count": len(evidence_sources),
            "evidence_ids": sorted(valid_ids),
            "sections": [str(item.get("section_title") or "") for item in evidence_sources],
        },
        "results": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT),
        "message_sha256": artifact["comparison_controls"]["message_sha256"],
        "retrieval": artifact["retrieval"],
        "results": [{key: item[key] for key in (
            "model_requested", "model_returned", "finish_reason", "elapsed_seconds", "usage", "assessment",
        )} for item in results],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
