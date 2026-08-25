"""Production-corpus Context Engineering evaluation with optional live answers.

The default path is read-only and never calls an LLM.  ``--online`` must be
combined with ``--confirm-paid-model`` so scheduled/CI runs cannot accidentally
spend API quota.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from backend.services.session_context import resolve_followup_with_trace
from evaluation.context_replay import load_approved_cases
from graph.conversation_context import (
    assemble_conversation_context_pack,
    build_conversation_context_seed,
)
from graph.evidence_pack import build_evidence_pack


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "context_production.jsonl"
DEFAULT_REPORT = ROOT / "data" / "eval" / "context_eval_v3_report.json"
CONTEXT_EVAL_SCHEMA_VERSION = 4


def _normalized(value: Any) -> str:
    return re.sub(r"[\s。？?!！；;，,、]+", "", str(value or "")).lower()


def _contains_all(text: str, values: list[Any]) -> bool:
    normalized = _normalized(text)
    return all(
        any(_normalized(option) in normalized for option in value)
        if isinstance(value, (list, tuple))
        else _normalized(value) in normalized
        for value in values
    )


def _contains_none(text: str, values: list[Any]) -> bool:
    normalized = _normalized(text)
    return all(_normalized(value) not in normalized for value in values)


def _contains_no_unnegated_terms(text: str, values: list[Any]) -> bool:
    """Reject forbidden claims without treating their explicit negation as drift."""
    normalized = _normalized(text)
    negations = ("不", "并不", "并非", "不是", "未", "不太", "不宜", "无法")
    for value in values:
        term = _normalized(value)
        if not term:
            continue
        start = 0
        while True:
            index = normalized.find(term, start)
            if index < 0:
                break
            prefix = normalized[max(0, index - 4):index]
            if not any(prefix.endswith(negation) for negation in negations):
                return False
            start = index + len(term)
    return True


def _summary(details: list[dict[str, Any]]) -> dict[str, Any]:
    cases = len(details)
    passed = sum(bool(item.get("passed")) for item in details)
    skipped = sum(bool(item.get("skipped")) for item in details)
    scored = cases - skipped
    return {
        "cases": cases,
        "scored": scored,
        "passed": passed,
        "failed": max(0, scored - passed),
        "skipped": skipped,
        "pass_rate": passed / scored if scored else 0.0,
    }


def _runtime_versions(book_name: str) -> dict[str, Any]:
    from backend.services.context_versions import current_context_versions

    return current_context_versions(book_name)


def prepare_production_state(
    case: dict[str, Any],
    *,
    retrieval_runner: Callable[[dict], dict] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    history = [item for item in case.get("history") or [] if isinstance(item, dict)]
    query = str(case.get("query") or "")
    resolved, trace = resolve_followup_with_trace(query, history)
    intent = str(case.get("intent") or (trace.get("state_after") or {}).get("intent") or "qa")
    seed = build_conversation_context_seed(history, trace)
    state = {
        "user_input": resolved,
        "book_name": str(case.get("book_name") or ""),
        "subject": str(case.get("subject") or ""),
        "intent": intent,
        "target_chapters": list(case.get("target_chapters") or []),
        "use_textbook_context": True,
        "answer_mode": "textbook_grounded",
        "retrieval_error": "",
        "conversation_context_seed": seed,
        **dict(case.get("retrieval_context") or {}),
    }
    if retrieval_runner is None:
        from graph.retrieval_node import retrieve_node

        retrieval_runner = retrieve_node
    retrieval = retrieval_runner(state)
    state.update(retrieval)
    evidence_pack = build_evidence_pack(
        state.get("evidence_items") or [],
        state.get("chapter_contents") or {},
        intent=intent,
    )
    state["evidence_sources"] = evidence_pack.get("items") or []
    context_pack = assemble_conversation_context_pack(state, evidence_pack)
    context_pack.pop("text", None)
    diagnostics = {
        "resolved_query": resolved,
        "resolution_trace": trace,
        "evidence_pack": evidence_pack,
        "context_pack": context_pack,
    }
    return state, diagnostics


def score_production_retrieval_case(
    case: dict[str, Any],
    *,
    retrieval_runner: Callable[[dict], dict] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = dict(case.get("expected") or {})
    state, diagnostics = prepare_production_state(case, retrieval_runner=retrieval_runner)
    resolved = str(diagnostics["resolved_query"] or "")
    evidence_pack = diagnostics["evidence_pack"]
    evidence_text = str(evidence_pack.get("text") or "")
    context_pack = diagnostics["context_pack"]
    support = str((state.get("evidence_support") or {}).get("status") or "")
    checks: dict[str, bool] = {}
    if "resolved_query" in expected:
        checks["resolved_query"] = _normalized(resolved) == _normalized(expected["resolved_query"])
    if "resolved_query_contains" in expected:
        checks["resolved_query_contains"] = _contains_all(resolved, expected["resolved_query_contains"])
    if "required_evidence_points" in expected:
        checks["evidence_points"] = _contains_all(evidence_text, expected["required_evidence_points"])
    if "forbidden_evidence_points" in expected:
        checks["no_forbidden_evidence"] = _contains_none(evidence_text, expected["forbidden_evidence_points"])
    if "retrieval_action" in expected:
        checks["retrieval_action"] = str(state.get("retrieval_action") or "") == expected["retrieval_action"]
    if "support_status" in expected:
        checks["support_status"] = support == expected["support_status"]
    if "context_turn_ids" in expected:
        checks["context_turns"] = list(context_pack.get("turn_ids") or []) == list(expected["context_turn_ids"])
    if "artifact_targets" in expected:
        checks["context_artifacts"] = list(context_pack.get("artifact_targets") or []) == list(expected["artifact_targets"])
    passed = bool(checks) and all(checks.values())
    detail = {
        "id": str(case.get("id") or ""),
        "tags": list(case.get("tags") or []),
        "passed": passed,
        "checks": checks,
        "actual": {
            "resolved_query": resolved,
            "retrieval_action": str(state.get("retrieval_action") or ""),
            "support_status": support,
            "evidence_chunk_ids": [
                str(item.get("chunk_id") or "")
                for item in evidence_pack.get("items") or [] if isinstance(item, dict)
            ],
            "context_turn_ids": list(context_pack.get("turn_ids") or []),
            "artifact_targets": list(context_pack.get("artifact_targets") or []),
            "missing_evidence_points": [
                value for value in expected.get("required_evidence_points") or []
                if not _contains_all(evidence_text, [value])
            ],
        },
        "expected": expected,
        "versions": _runtime_versions(str(case.get("book_name") or "")),
    }
    return detail, state


def _run_live_answer(state: dict[str, Any]) -> str:
    from graph.generator import generate_node

    return str(generate_node(state).get("final_output") or "")


def score_online_answer_case(
    case: dict[str, Any],
    state: dict[str, Any],
    *,
    answer_runner: Callable[[dict], str] | None = None,
) -> dict[str, Any]:
    expected = dict(case.get("expected") or {})
    if not any(key in expected for key in (
        "required_answer_points", "required_constraints", "forbidden_answer_terms", "require_citations",
    )):
        return {"id": case.get("id", ""), "skipped": True, "passed": False, "checks": {}}
    started = time.perf_counter()
    try:
        answer = (answer_runner or _run_live_answer)(state)
    except Exception as exc:
        return {
            "id": str(case.get("id") or ""),
            "skipped": False,
            "passed": False,
            "checks": {"model_call": False},
            "answer": "",
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "versions": _runtime_versions(str(case.get("book_name") or "")),
        }
    checks: dict[str, bool] = {}
    if "required_answer_points" in expected:
        checks["answer_points"] = _contains_all(answer, expected["required_answer_points"])
    if "required_constraints" in expected:
        checks["constraints"] = _contains_all(answer, expected["required_constraints"])
    if "forbidden_answer_terms" in expected:
        checks["no_drift"] = _contains_no_unnegated_terms(
            answer, expected["forbidden_answer_terms"],
        )
    if expected.get("require_citations"):
        checks["citations"] = bool(re.search(r"\[\[cite:E[\w-]+\]\]", answer, re.I))
    return {
        "id": str(case.get("id") or ""),
        "skipped": False,
        "passed": bool(checks) and all(checks.values()),
        "checks": checks,
        "answer": answer,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "versions": _runtime_versions(str(case.get("book_name") or "")),
    }


def evaluate(
    dataset: str | Path = DEFAULT_DATASET,
    *,
    online: bool = False,
    retrieval_runner: Callable[[dict], dict] | None = None,
    answer_runner: Callable[[dict], str] | None = None,
    lifecycle_runner: Callable[[], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    from evaluation.learning_task_lifecycle_eval import evaluate_learning_task_lifecycle

    cases = load_approved_cases(dataset)
    retrieval_details: list[dict[str, Any]] = []
    answer_details: list[dict[str, Any]] = []
    for case in cases:
        retrieval_detail, state = score_production_retrieval_case(
            case, retrieval_runner=retrieval_runner,
        )
        retrieval_details.append(retrieval_detail)
        if online:
            answer_details.append(score_online_answer_case(
                case, state, answer_runner=answer_runner,
            ))
    lifecycle_details = (lifecycle_runner or evaluate_learning_task_lifecycle)()
    retrieval_passed = bool(retrieval_details) and all(item.get("passed") for item in retrieval_details)
    lifecycle_passed = bool(lifecycle_details) and all(item.get("passed") for item in lifecycle_details)
    answer_passed = bool(answer_details) and all(item.get("passed") or item.get("skipped") for item in answer_details)
    offline_passed = retrieval_passed and lifecycle_passed
    production_passed = offline_passed and online and answer_passed
    return {
        "schema_version": CONTEXT_EVAL_SCHEMA_VERSION,
        "dataset": str(Path(dataset)),
        "modes": {
            "retrieval": "production_retrieval_and_evidence_pack",
            "answer": "live_model" if online else "disabled_no_model_call",
            "lifecycle": "deterministic_production_state_transitions",
        },
        "layers": {
            "retrieval": _summary(retrieval_details),
            "answer": _summary(answer_details),
            "lifecycle": _summary(lifecycle_details),
        },
        "release_gates": {
            "passed": production_passed,
            "offline_passed": offline_passed,
            "production_passed": production_passed,
            "online_answer_required": True,
        },
        "retrieval_details": retrieval_details,
        "answer_details": answer_details,
        "lifecycle_details": lifecycle_details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run production Context Eval v3.")
    parser.add_argument("dataset", nargs="?", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--confirm-paid-model", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if args.online and not args.confirm_paid_model:
        parser.error("--online requires --confirm-paid-model")
    report = evaluate(args.dataset, online=args.online)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
    try:
        print(payload)
    except UnicodeEncodeError:
        # Some Windows terminals still default to GBK. The report has already
        # been persisted above; keep the CLI usable with an ASCII-safe fallback.
        print(json.dumps(report, ensure_ascii=True, indent=2))
    return 1 if args.strict and not report["release_gates"]["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
