"""Compare official V4-Flash-0731 with V4-Pro-Preview on a sensor question."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "benchmark_results" / "deepseek_v4_sensor_comparison_20260801.json"

SYSTEM_PROMPT = (
    "你是一名严谨的考研专业课教师，科目是传感器与检测技术。"
    "请给出自洽、可核验的中文解答，定义符号后再使用，公式统一使用 LaTeX。"
    "推导完整但避免堆砌概念，不要输出或提及内部思考过程。"
)

QUESTION = r"""某电阻应变式压力传感器采用四片相同应变片组成全桥。各片初始电阻均为 \(R\)，灵敏系数 \(K=2.1\)，压力 \(p\) 与应变的关系为

\[
\varepsilon=\alpha p,\qquad \alpha=8.0\times10^{-6}\ {\rm kPa}^{-1}.
\]

恒压桥源 \(U_E=5.0\ {\rm V}\)。受压后，桥臂 \(R_1,R_4\) 受拉，\(\Delta R/R=+K\varepsilon\)；桥臂 \(R_2,R_3\) 受压，\(\Delta R/R=-K\varepsilon\)。定义电桥输出极性，使压力增大时输出为正。电桥后接理想增益 \(G=100\) 的放大器。传感器动态可用一阶环节

\[
H(s)=\frac{1}{\tau s+1},\qquad \tau=0.080\ {\rm s}
\]

描述。

请完成：

1. 从惠斯通电桥分压关系出发，推导电桥输出 \(U_o(p)\)，说明这里的结果是精确式还是小信号近似；再求放大后静态灵敏度（单位分别写成 \({\rm V/kPa}\) 和 \({\rm mV/kPa}\)）以及 \(p=200\ {\rm kPa}\) 时的稳态输出。
2. 压力从 0 突变为 \(100\ {\rm kPa}\) 时，写出放大后输出 \(U(t)\)，计算 \(t=0.10\ {\rm s}\) 的输出，以及进入并保持在最终值 \(\pm5\%\) 误差带内所需的最短时间。
3. 若 \(K,\alpha,U_E,G\) 的相对标准不确定度分别为 \(1.0\%,1.5\%,0.2\%,0.5\%\)，彼此独立，按均方根法求合成相对标准不确定度；同时给出最坏情况线性相加值，并换算成满量程 \(200\ {\rm kPa}\) 处的输出电压不确定度和等效压力不确定度。
4. 解释为什么只给出静态灵敏度不足以描述该传感器对快速变化压力的测量能力，并指出本题两个最常见的计算错误。

请按步骤作答，数值至少保留三位有效数字，全文控制在 1800 个汉字左右。"""

PRICES_CNY_PER_MILLION = {
    "deepseek-v4-flash": {"cache_hit_input": 0.02, "cache_miss_input": 1.0, "output": 2.0},
    "deepseek-v4-pro": {"cache_hit_input": 0.025, "cache_miss_input": 3.0, "output": 6.0},
}


def get(obj, name: str, default=0):
    value = getattr(obj, name, default)
    return default if value is None else value


def call(client: OpenAI, model: str) -> dict:
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
            "user_id": f"kaoyan-sensor-{model.split('-')[-1]}-20260801",
        },
    )
    elapsed = time.perf_counter() - started
    usage = response.usage
    details = get(usage, "completion_tokens_details", None)
    hit = int(get(usage, "prompt_cache_hit_tokens"))
    miss = int(get(usage, "prompt_cache_miss_tokens"))
    completion = int(get(usage, "completion_tokens"))
    prices = PRICES_CNY_PER_MILLION[model]
    costs = {
        "cache_hit_input": hit * prices["cache_hit_input"] / 1_000_000,
        "cache_miss_input": miss * prices["cache_miss_input"] / 1_000_000,
        "output": completion * prices["output"] / 1_000_000,
    }
    return {
        "model_requested": model,
        "model_returned": response.model,
        "system_fingerprint": get(response, "system_fingerprint", ""),
        "finish_reason": response.choices[0].finish_reason,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "usage": {
            "prompt_tokens": int(get(usage, "prompt_tokens")),
            "prompt_cache_hit_tokens": hit,
            "prompt_cache_miss_tokens": miss,
            "completion_tokens": completion,
            "reasoning_tokens": int(get(details, "reasoning_tokens")) if details else 0,
            "total_tokens": int(get(usage, "total_tokens")),
        },
        "calculated_cost_cny_components": costs,
        "calculated_cost_cny": sum(costs.values()),
        "answer": response.choices[0].message.content or "",
        "reasoning_content_saved": False,
    }


def main() -> None:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
    controls = [
        (index, ord(char))
        for index, char in enumerate(QUESTION)
        if ord(char) < 32 and char not in "\r\n\t"
    ]
    if controls:
        raise RuntimeError(f"Question contains unexpected control characters: {controls}")

    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=300.0)
    results = [call(client, model) for model in ("deepseek-v4-flash", "deepseek-v4-pro")]
    artifact = {
        "run_at": datetime.now().astimezone().isoformat(),
        "official_version_basis": (
            "DeepSeek 2026-07-31 changelog: deepseek-v4-flash routes to the official "
            "DeepSeek-V4-Flash-0731 public beta; deepseek-v4-pro remains Preview."
        ),
        "official_source": "https://api-docs.deepseek.com/updates/",
        "endpoint": base_url,
        "comparison_controls": {
            "same_messages": True,
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
            "max_tokens": 8192,
            "stream": False,
            "separate_user_ids_for_cache_isolation": True,
            "question_control_characters_checked": True,
        },
        "system_prompt": SYSTEM_PROMPT,
        "question": QUESTION,
        "results": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT),
        "results": [{
            "model": result["model_returned"],
            "fingerprint": result["system_fingerprint"],
            "finish_reason": result["finish_reason"],
            "elapsed_seconds": result["elapsed_seconds"],
            "usage": result["usage"],
            "cost_cny": result["calculated_cost_cny"],
            "answer_chars": len(result["answer"]),
        } for result in results],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
