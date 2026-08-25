"""Produce deterministic metrics and a raw-answer review for prompt presets."""
from __future__ import annotations

import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmark_results" / "qwen37_prompt_presets_abg_20260825.json"
ANALYSIS = ROOT / "benchmark_results" / "qwen37_prompt_presets_abg_analysis_20260825.json"
REVIEW = ROOT / "benchmark_results" / "qwen37_prompt_presets_abg_raw_20260825.md"
PRESETS = ("legacy", "refined", "minimal")


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def _mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def _answer_style(answer: str) -> dict[str, int]:
    return {
        "heading_count": len(re.findall(r"(?m)^#{1,6}\s", answer)),
        "bold_span_count": len(re.findall(r"\*\*[^*]+\*\*", answer)),
        "bullet_count": len(re.findall(r"(?m)^\s*(?:[-*]|\d+[.)])\s+", answer)),
        "encouragement_count": sum(answer.count(term) for term in (
            "希望", "帮助你", "记住", "如果你愿意", "如果需要", "可以把", "直观地",
        )),
    }


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    fixture = payload["fixture"]
    cases = {(row["group"], row["id"]): row for row in fixture["cases"]}
    rows = [item for item in payload["results"] if not item.get("error")]
    metrics: dict[str, Any] = {"overall": {}, "by_group": {}, "by_case": {}}
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in rows:
        buckets[(item["group"], item["preset"])].append(item)

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        recalls = [
            float(item["score"]["required_point_recall"])
            for item in items if (item.get("score") or {}).get("required_point_recall") is not None
        ]
        style = [_answer_style(str(item.get("answer") or "")) for item in items]
        return {
            "samples": len(items),
            "median_elapsed_seconds": _median([float(item["elapsed_seconds"]) for item in items]),
            "p90_elapsed_seconds": round(sorted(float(item["elapsed_seconds"]) for item in items)[max(0, int(len(items) * .9) - 1)], 4) if items else None,
            "median_ttft_seconds": _median([float(item["ttft_seconds"]) for item in items if item.get("ttft_seconds") is not None]),
            "median_answer_chars": _median([float(item["score"]["answer_chars"]) for item in items]),
            "mean_required_point_recall": _mean(recalls),
            "scored_samples": len(recalls),
            "citation_count": sum(int(item["score"]["citation_count"]) for item in items),
            "invalid_citation_count": sum(len(item["score"]["invalid_citations"]) for item in items),
            "responses_without_citation": sum(int(item["score"]["citation_count"] == 0) for item in items),
            "input_tokens": sum(int(item["usage"]["input_tokens"]) for item in items),
            "output_tokens": sum(int(item["usage"]["output_tokens"]) for item in items),
            "reasoning_tokens": sum(int(item["usage"]["reasoning_tokens"]) for item in items),
            "estimated_cost_cny": round(sum(float(item["cost"]["estimated_amount"]) for item in items), 8),
            "mean_heading_count": _mean([float(item["heading_count"]) for item in style]),
            "mean_bold_span_count": _mean([float(item["bold_span_count"]) for item in style]),
            "mean_bullet_count": _mean([float(item["bullet_count"]) for item in style]),
            "encouragement_count": sum(item["encouragement_count"] for item in style),
            "finish_reasons": dict(sorted({
                reason: sum(1 for item in items if str(item.get("finish_reason") or "") == reason)
                for reason in {str(item.get("finish_reason") or "") for item in items}
            }.items())),
        }

    for preset in PRESETS:
        metrics["overall"][preset] = summarize([item for item in rows if item["preset"] == preset])
    for group in ("A_textbook_rag", "B_conversation", "G_session"):
        metrics["by_group"][group] = {
            preset: summarize(buckets[(group, preset)]) for preset in PRESETS
        }
    for key, case in cases.items():
        case_key = f"{key[0]}/{key[1]}"
        metrics["by_case"][case_key] = {
            preset: summarize([
                item for item in rows
                if item["group"] == key[0] and item["case_id"] == key[1] and item["preset"] == preset
            ])
            for preset in PRESETS
        }
    ANALYSIS.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Qwen 3.7 Plus：Legacy / Refined / Minimal 原始回答复查",
        "",
        "> 同一 case 的三套 preset 使用完全相同的 frozen human payload；温度 0.1、thinking 开启、max_tokens 4096。每个 case 重复 3 次。本文不改写模型答案。",
        "",
    ]
    for case in fixture["cases"]:
        human = case["presets"]["minimal"]["messages"][1]["content"]
        query_match = re.search(r"## 用户问题\n(.*?)(?:\n\n##|\Z)", human, re.S)
        query = query_match.group(1).strip() if query_match else case["id"]
        lines.extend([
            f"## {case['group']} / {case['id']}", "", f"问题：{query}", "",
            f"Resolved query：{case.get('resolved_query') or '(none)'}", "",
        ])
        for preset in PRESETS:
            prompt = case["presets"][preset]["messages"][0]["content"]
            lines.extend([
                f"### {preset}", "", "<details><summary>System prompt</summary>", "",
                "```text", prompt, "```", "", "</details>", "",
            ])
            answers = sorted([
                item for item in rows
                if item["group"] == case["group"] and item["case_id"] == case["id"] and item["preset"] == preset
            ], key=lambda item: int(item["repeat"]))
            for item in answers:
                lines.extend([
                    f"<details><summary>Repeat {item['repeat']} · {item['elapsed_seconds']}s · TTFT {item.get('ttft_seconds')}s · input/output/reasoning {item['usage']['input_tokens']}/{item['usage']['output_tokens']}/{item['usage']['reasoning_tokens']}</summary>",
                    "", str(item.get("answer") or ""), "", "</details>", "",
                ])
    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    REVIEW.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(json.dumps({"analysis": str(ANALYSIS), "review": str(REVIEW), "cases": len(cases)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
