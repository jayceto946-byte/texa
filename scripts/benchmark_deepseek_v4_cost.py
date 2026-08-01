"""Run one controlled DeepSeek V4 Flash vs Pro comparison.

The script reads the project's .env, never prints the API key, excludes model
reasoning text from the saved artifact, and calculates cost from the official
2026-07-31 CNY price table.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "benchmark_results" / "deepseek_v4_flash_vs_pro_20260731.json"

SYSTEM_PROMPT = (
    "你是一名严谨的考研数学教师。请给出自洽、可核验的中文解答，公式使用 LaTeX。"
    "推导应完整但避免冗长，不要输出或提及内部思考过程。"
)
QUESTION = r"""设 $A$ 为 $n$ 阶实对称矩阵。请完成以下任务：
1. 不要只引用结论，证明 Rayleigh 商
$$R(x)=\frac{x^T A x}{x^T x}\quad(x\ne 0)$$
的最大值和最小值分别等于 $A$ 的最大、最小特征值，并准确说明取等条件（包括重特征值情形）。
2. 用上述结论求矩阵
$$A=\begin{pmatrix}2&1&0\\1&2&1\\0&1&2\end{pmatrix}$$
对应二次型在约束 $x^2+y^2+z^2=1$ 下的最大值、最小值以及全部取等点。

请把最终解答控制在 1200 个汉字左右，并在结尾列出两个最容易犯的错误。"""

PRICES_CNY_PER_MILLION = {
    "deepseek-v4-flash": {"cache_hit_input": 0.02, "cache_miss_input": 1.0, "output": 2.0},
    "deepseek-v4-pro": {"cache_hit_input": 0.025, "cache_miss_input": 3.0, "output": 6.0},
}


def field(obj, name: str, default=0):
    value = getattr(obj, name, default)
    return default if value is None else value


def run_model(client: OpenAI, model: str) -> dict:
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": QUESTION},
        ],
        reasoning_effort="high",
        max_tokens=8192,
        stream=False,
        extra_body={
            "thinking": {"type": "enabled"},
            "user_id": f"kaoyan-v4-benchmark-{model.split('-')[-1]}-20260731",
        },
    )
    elapsed = time.perf_counter() - started
    usage = response.usage
    details = field(usage, "completion_tokens_details", None)
    hit = int(field(usage, "prompt_cache_hit_tokens"))
    miss = int(field(usage, "prompt_cache_miss_tokens"))
    completion = int(field(usage, "completion_tokens"))
    prices = PRICES_CNY_PER_MILLION[model]
    components = {
        "cache_hit_input": hit * prices["cache_hit_input"] / 1_000_000,
        "cache_miss_input": miss * prices["cache_miss_input"] / 1_000_000,
        "output": completion * prices["output"] / 1_000_000,
    }
    message = response.choices[0].message
    return {
        "model_requested": model,
        "model_returned": response.model,
        "system_fingerprint": field(response, "system_fingerprint", ""),
        "finish_reason": response.choices[0].finish_reason,
        "elapsed_seconds": round(elapsed, 3),
        "usage": {
            "prompt_tokens": int(field(usage, "prompt_tokens")),
            "prompt_cache_hit_tokens": hit,
            "prompt_cache_miss_tokens": miss,
            "completion_tokens": completion,
            "reasoning_tokens": int(field(details, "reasoning_tokens")) if details else 0,
            "total_tokens": int(field(usage, "total_tokens")),
        },
        "price_cny_per_million_tokens": prices,
        "calculated_cost_cny_components": components,
        "calculated_cost_cny": sum(components.values()),
        "answer": message.content or "",
        "reasoning_content_saved": False,
    }


def main() -> None:
    load_dotenv(ROOT / ".env")
    import os

    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured in the project .env")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=300.0)

    results = [run_model(client, model) for model in ("deepseek-v4-flash", "deepseek-v4-pro")]
    artifact = {
        "run_at": datetime.now().astimezone().isoformat(),
        "endpoint": base_url,
        "comparison_controls": {
            "same_messages": True,
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
            "max_tokens": 8192,
            "stream": False,
            "separate_user_ids_for_cache_isolation": True,
        },
        "system_prompt": SYSTEM_PROMPT,
        "question": QUESTION,
        "pricing_source": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
        "results": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "output": str(OUTPUT),
        "results": [
            {
                "model": item["model_requested"],
                "returned": item["model_returned"],
                "finish_reason": item["finish_reason"],
                "elapsed_seconds": item["elapsed_seconds"],
                "usage": item["usage"],
                "calculated_cost_cny": item["calculated_cost_cny"],
                "answer_chars": len(item["answer"]),
            }
            for item in results
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
