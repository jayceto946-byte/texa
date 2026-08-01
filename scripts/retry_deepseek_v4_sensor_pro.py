"""Retry only the truncated Pro response from the sensor comparison."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from scripts.benchmark_deepseek_v4_sensor import (
    OUTPUT,
    QUESTION,
    ROOT,
    SYSTEM_PROMPT,
    get as value,
)


def main() -> None:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=300.0)
    started = time.perf_counter()
    response = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": QUESTION},
        ],
        reasoning_effort="high",
        max_tokens=16384,
        stream=False,
        extra_body={
            "thinking": {"type": "enabled"},
            "user_id": "kaoyan-sensor-pro-retry-20260801",
        },
    )
    usage = response.usage
    details = value(usage, "completion_tokens_details", None)
    hit = int(value(usage, "prompt_cache_hit_tokens"))
    miss = int(value(usage, "prompt_cache_miss_tokens"))
    completion = int(value(usage, "completion_tokens"))
    components = {
        "cache_hit_input": hit * 0.025 / 1_000_000,
        "cache_miss_input": miss * 3.0 / 1_000_000,
        "output": completion * 6.0 / 1_000_000,
    }
    retry = {
        "model_requested": "deepseek-v4-pro",
        "model_returned": response.model,
        "system_fingerprint": value(response, "system_fingerprint", ""),
        "finish_reason": response.choices[0].finish_reason,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "max_tokens": 16384,
        "usage": {
            "prompt_tokens": int(value(usage, "prompt_tokens")),
            "prompt_cache_hit_tokens": hit,
            "prompt_cache_miss_tokens": miss,
            "completion_tokens": completion,
            "reasoning_tokens": int(value(details, "reasoning_tokens")) if details else 0,
            "total_tokens": int(value(usage, "total_tokens")),
        },
        "calculated_cost_cny_components": components,
        "calculated_cost_cny": sum(components.values()),
        "answer": response.choices[0].message.content or "",
        "reasoning_content_saved": False,
    }

    artifact_path = Path(OUTPUT)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    prior_pro = artifact["results"][1]
    artifact["truncated_attempts"] = [prior_pro]
    artifact["results"][1] = retry
    artifact["comparison_controls"]["pro_retry_max_tokens"] = 16384
    artifact["comparison_controls"]["pro_retry_reason"] = (
        "Initial Pro attempt used all 8193 completion tokens as reasoning and "
        "returned no final answer; only Pro was retried."
    )
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({
        "finish_reason": retry["finish_reason"],
        "elapsed_seconds": retry["elapsed_seconds"],
        "usage": retry["usage"],
        "cost_cny": retry["calculated_cost_cny"],
        "answer_chars": len(retry["answer"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
