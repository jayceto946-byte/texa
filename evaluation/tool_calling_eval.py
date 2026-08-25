"""Offline routing and deterministic-tool contract evaluation.

This suite intentionally does not score LLM answer quality. It compares the
server router with a no-tool policy and separately checks deterministic math
execution and verification.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from backend.services.tool_orchestration import (
    ToolOrchestrationRequest,
    execute_read_only_tools,
    select_tool_calls,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "tool_calling.jsonl"


def load_cases(path: str | Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    cases = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if not item.get("id") or "question" not in item or "expected_tools" not in item:
                raise ValueError(f"invalid tool eval case at line {line_number}")
            cases.append(item)
    return cases


def _request(case: dict[str, Any]) -> ToolOrchestrationRequest:
    return ToolOrchestrationRequest(
        question=str(case["question"]),
        book_name=str(case.get("book_name") or ""),
        subject=str(case.get("subject") or ""),
        max_tools=6,
        include_textbook_tool=False,
    )


def evaluate(path: str | Path = DEFAULT_DATASET, *, execute: bool = True) -> dict[str, Any]:
    cases = load_cases(path)
    rows = []
    category_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "route_pass": 0})
    math_executed = math_success = math_verified = 0

    for case in cases:
        selected = select_tool_calls(_request(case))
        actual_tools = [str(item.get("tool") or "") for item in selected]
        expected_tools = [str(item) for item in case.get("expected_tools") or []]
        route_pass = actual_tools == expected_tools
        operation_pass = True
        if case.get("expected_operation"):
            operation_pass = bool(selected) and (selected[0].get("args") or {}).get("operation") == case["expected_operation"]
        route_pass = route_pass and operation_pass

        category = str(case.get("category") or "uncategorized")
        category_counts[category]["total"] += 1
        category_counts[category]["route_pass"] += int(route_pass)
        row = {
            "id": case["id"], "category": category,
            "expected_tools": expected_tools, "actual_tools": actual_tools,
            "route_pass": route_pass,
        }

        if execute and case.get("execute") and route_pass:
            math_executed += 1
            run = execute_read_only_tools(_request(case))
            outputs = run.get("tool_outputs") or []
            symbolic = next((item for item in outputs if item.get("tool") == "symbolic_math"), None)
            verifier = next((item for item in outputs if item.get("tool") == "verify_math_result"), None)
            execution_pass = bool(symbolic and (symbolic.get("result") or {}).get("success"))
            expected_exact = case.get("expected_exact")
            if execution_pass and expected_exact is not None:
                actual_exact = (((symbolic or {}).get("result") or {}).get("data") or {}).get("result", {}).get("exact")
                execution_pass = actual_exact == expected_exact
                row["expected_exact"] = expected_exact
                row["actual_exact"] = actual_exact
            verification_pass = bool(
                verifier
                and (verifier.get("result") or {}).get("success")
                and ((verifier.get("result") or {}).get("verification") or {}).get("passed")
            )
            math_success += int(execution_pass)
            math_verified += int(verification_pass)
            row.update({"execution_pass": execution_pass, "verification_pass": verification_pass})
        rows.append(row)

    total = len(rows)
    route_passes = sum(int(item["route_pass"]) for item in rows)
    no_tool_cases = [item for item in rows if not item["expected_tools"]]
    no_tool_passes = sum(int(not item["actual_tools"]) for item in no_tool_cases)
    no_tool_policy_passes = len(no_tool_cases)
    route_accuracy = route_passes / total if total else 0.0
    no_tool_precision = no_tool_passes / len(no_tool_cases) if no_tool_cases else 1.0
    math_success_rate = math_success / math_executed if math_executed else 1.0
    math_verification_rate = math_verified / math_executed if math_executed else 1.0
    thresholds = {
        "route_accuracy": 0.90,
        "no_tool_precision": 0.95,
        "math_execution_success": 1.0,
        "math_verification": 1.0,
    }
    metrics = {
        "case_count": total,
        "route_accuracy": round(route_accuracy, 6),
        "no_tool_precision": round(no_tool_precision, 6),
        "math_execution_success": round(math_success_rate, 6),
        "math_verification": round(math_verification_rate, 6),
        "no_tool_policy_route_accuracy": round(no_tool_policy_passes / total if total else 0.0, 6),
        "router_gain_vs_no_tool_policy": round((route_passes - no_tool_policy_passes) / total if total else 0.0, 6),
    }
    release_pass = all(metrics[name] >= threshold for name, threshold in thresholds.items())
    return {
        "dataset": str(Path(path)),
        "metrics": metrics,
        "thresholds": thresholds,
        "release_pass": release_pass,
        "categories": {
            name: {**counts, "route_accuracy": round(counts["route_pass"] / counts["total"], 6)}
            for name, counts in sorted(category_counts.items())
        },
        "failures": [item for item in rows if not item["route_pass"] or item.get("execution_pass") is False or item.get("verification_pass") is False],
        "scope_note": "Offline routing/tool contract only; this is not online model answer accuracy.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", nargs="?", default=str(DEFAULT_DATASET))
    parser.add_argument("--route-only", action="store_true")
    args = parser.parse_args()
    report = evaluate(args.dataset, execute=not args.route_only)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["release_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
