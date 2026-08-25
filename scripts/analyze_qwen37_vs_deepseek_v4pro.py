"""Produce deterministic aggregate metrics from the raw controlled benchmark."""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "benchmark_results" / "qwen37_vs_deepseek_v4pro_20260825.json"
OUTPUT = ROOT / "benchmark_results" / "qwen37_vs_deepseek_v4pro_analysis_20260825.json"
USAGE_FIELDS = (
    "input_tokens", "output_tokens", "total_tokens",
    "cached_input_tokens", "reasoning_tokens",
)


def median(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return round(statistics.median(values), 4) if values else None


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [row.get("score") or {} for row in rows]
    recalls = [float(score["required_point_recall"]) for score in scores if score.get("required_point_recall") is not None]
    chars = [int(score.get("answer_chars") or 0) for score in scores]
    currencies = sorted({str((row.get("cost") or {}).get("currency") or "") for row in rows} - {""})
    return {
        "samples": len(rows),
        "median_seconds": median(rows, "elapsed_seconds"),
        "median_ttft_seconds": median(rows, "ttft_seconds"),
        "median_answer_chars": statistics.median(chars) if chars else None,
        "empty_answers": sum(value == 0 for value in chars),
        "finish_reason_length": sum(row.get("finish_reason") == "length" for row in rows),
        "mean_required_point_recall": round(sum(recalls) / len(recalls), 6) if recalls else None,
        "recall_scored_samples": len(recalls),
        "zero_valid_citations": sum(int(score.get("citation_count") or 0) == 0 for score in scores),
        "invalid_citation_samples": sum(bool(score.get("invalid_citations")) for score in scores),
        "structured_parse_ok": sum(score.get("structured_parse_ok") is True for score in scores),
        "structured_intent_match": sum(score.get("structured_intent_match") is True for score in scores),
        "usage": {
            field: sum(int((row.get("usage") or {}).get(field) or 0) for row in rows)
            for field in USAGE_FIELDS
        },
        "estimated_cost": {
            currency: round(sum(
                float((row.get("cost") or {}).get("estimated_amount") or 0)
                for row in rows if (row.get("cost") or {}).get("currency") == currency
            ), 8)
            for currency in currencies
        },
    }


def vision_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    qwen = [row["qwen_native"] for row in rows]
    combos = [row["split_combo"] for row in rows]
    kimi = [row["kimi_stage"] for row in combos]
    deepseek = [row["deepseek_stage"] for row in combos]
    qwen_summary = summarize_rows(qwen)
    combo_summary = {
        "samples": len(combos),
        "median_seconds": median(combos, "elapsed_seconds"),
        "median_ttft_seconds": median(combos, "ttft_seconds"),
        "mean_required_point_recall": round(sum(
            float((row.get("score") or {}).get("required_point_recall") or 0)
            for row in combos
        ) / len(combos), 6),
        "empty_answers": sum(int((row.get("score") or {}).get("answer_chars") or 0) == 0 for row in combos),
        "kimi_stage": summarize_rows(kimi),
        "deepseek_stage": summarize_rows(deepseek),
    }
    return {"qwen_native": qwen_summary, "kimi_then_deepseek": combo_summary}


def main() -> None:
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in raw["results"]:
        grouped[(row["group"], row["model"])].append(row)
        by_model[row["model"]].append(row)
    analysis = {
        "source": str(SOURCE),
        "status": raw.get("status"),
        "text_result_count": len(raw["results"]),
        "overall": {model: summarize_rows(rows) for model, rows in sorted(by_model.items())},
        "by_group": {
            group: {
                model: summarize_rows(grouped[(group, model)])
                for model in sorted({key[1] for key in grouped if key[0] == group})
            }
            for group in sorted({key[0] for key in grouped})
        },
        "vision": vision_summary(raw["vision_results"]),
    }
    OUTPUT.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(analysis, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
