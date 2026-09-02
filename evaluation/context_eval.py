"""Deterministic multi-turn Context Engineering evaluation."""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from backend.services.session_context import resolve_followup_with_trace
from graph.conversation_context import (
    assemble_conversation_context_pack,
    build_conversation_context_seed,
)
from graph.evidence_pack import build_evidence_pack
from graph.retrieval_node import _retrieval_query_for_intent
from graph.retrieval_policy import decide_retrieval_action, scope_changed


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "context_followup.jsonl"
DEFAULT_REPORT = ROOT / "data" / "eval" / "context_eval_report.json"
DEFAULT_LAYER_DATASET = ROOT / "evaluation" / "datasets" / "context_pipeline_layers.jsonl"

DEFAULT_RELEASE_THRESHOLDS = {
    "resolver_overall": 0.80,
    "user_correction": 1.0,
    "assistant_artifact": 1.0,
    "clarification": 1.0,
    "evidence_reuse": 1.0,
    "evidence_delta": 1.0,
    "negative": 1.0,
    "standalone": 1.0,
    "long_20": 0.80,
    "long_40": 0.80,
    "long_80": 0.80,
    "retrieval_overall": 0.80,
    "answer_overall": 0.80,
    "retrieval_min_cases": 10,
    "answer_min_cases": 10,
}


def _materialize_history(item: dict) -> list[dict]:
    history = list(item.get("history") or [])
    spec = item.get("history_spec") if isinstance(item.get("history_spec"), dict) else {}
    if not spec:
        return history
    if spec.get("kind") != "topic_sequence":
        raise ValueError(f"unsupported history_spec kind: {spec.get('kind')}")
    turns = max(0, min(int(spec.get("turns") or 0), 100))
    start = int(spec.get("start") or 1)
    topic_template = str(spec.get("topic_template") or "概念{index}")
    user_template = str(spec.get("user_template") or "解释{topic}。")
    assistant_template = str(spec.get("assistant_template") or "关于{topic}的回答。")
    turn_prefix = str(spec.get("turn_prefix") or "generated")
    for offset in range(turns):
        index = start + offset
        topic = topic_template.format(index=index)
        turn_id = f"{turn_prefix}-{index}"
        history.extend([
            {
                "role": "user",
                "content": user_template.format(index=index, topic=topic),
                "turn_id": turn_id,
            },
            {
                "role": "assistant",
                "content": assistant_template.format(index=index, topic=topic),
                "turn_id": turn_id,
            },
        ])
    return history


def load_cases(path: str | Path) -> list[dict]:
    cases: list[dict] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        item = json.loads(stripped)
        if not item.get("id") or "query" not in item:
            raise ValueError(f"invalid context eval case at line {line_number}")
        item["history"] = _materialize_history(item)
        item["history_turn_count"] = sum(
            entry.get("role") == "user" for entry in item["history"]
        )
        cases.append(item)
    return cases


def load_layer_cases(path: str | Path) -> list[dict]:
    cases: list[dict] = []
    target = Path(path)
    if not target.exists():
        return cases
    for line_number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        item = json.loads(stripped)
        if not item.get("id") or not item.get("base_case_id"):
            raise ValueError(f"invalid layered context case at line {line_number}")
        cases.append(item)
    return cases


def _normalized(value: str) -> str:
    return re.sub(r"[\s。？?!！]+", "", str(value or "")).lower()


def _state_matches(actual: dict, expected: dict) -> tuple[bool, dict]:
    mismatches: dict[str, dict[str, Any]] = {}
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if isinstance(expected_value, list):
            matched = list(actual_value or []) == expected_value
        else:
            matched = actual_value == expected_value
        if not matched:
            mismatches[key] = {"expected": expected_value, "actual": actual_value}
    return not mismatches, mismatches


def score_case(case: dict) -> dict:
    history = list(case.get("history") or [])
    query = str(case.get("query") or "")
    expected = dict(case.get("expected") or {})
    resolved, trace = resolve_followup_with_trace(query, history)

    checks: dict[str, bool] = {}
    if "resolved_query" in expected:
        checks["resolution"] = _normalized(resolved) == _normalized(expected["resolved_query"])
    if "is_followup" in expected:
        checks["followup"] = trace["is_followup"] is bool(expected["is_followup"])
    if "referenced_entities" in expected:
        expected_entities = {str(item) for item in expected["referenced_entities"]}
        actual_entities = {str(item) for item in trace.get("referenced_entities") or []}
        checks["references"] = expected_entities == actual_entities
    state_ok, state_mismatches = _state_matches(
        trace.get("state_after") or {},
        dict(expected.get("state_after") or {}),
    )
    if expected.get("state_after"):
        checks["state_after"] = state_ok

    policy_context = case.get("context") if isinstance(case.get("context"), dict) else {}
    retrieval_action = decide_retrieval_action(policy_context)
    retrieval_query = "" if retrieval_action in {"none", "reuse"} else _retrieval_query_for_intent(
        resolved,
        str(policy_context.get("intent") or trace.get("state_after", {}).get("intent") or "qa"),
    )
    observed_scope_change = scope_changed(policy_context)
    if "retrieval_action" in expected:
        checks["retrieval_action"] = retrieval_action == expected["retrieval_action"]
    if "retrieval_query" in expected:
        checks["retrieval_query"] = _normalized(retrieval_query) == _normalized(expected["retrieval_query"])
    if "retrieval_query_contains" in expected:
        checks["retrieval_query"] = all(
            _normalized(part) in _normalized(retrieval_query)
            for part in expected["retrieval_query_contains"]
        )
    if "scope_changed" in expected:
        checks["scope_changed"] = observed_scope_change is bool(expected["scope_changed"])
    if "resolution_action" in expected:
        checks["resolution_action"] = (
            str(trace.get("resolution_action") or "continue") == expected["resolution_action"]
        )
    if "speech_act" in expected:
        checks["speech_act"] = str(trace.get("speech_act") or "") == expected["speech_act"]
    if "state_operations" in expected:
        checks["state_operations"] = list(trace.get("state_operations") or []) == list(
            expected["state_operations"]
        )

    passed = bool(checks) and all(checks.values())
    return {
        "id": case["id"],
        "tags": list(case.get("tags") or []),
        "history_turn_count": int(case.get("history_turn_count") or sum(
            item.get("role") == "user" for item in history
        )),
        "passed": passed,
        "checks": checks,
        "expected": expected,
        "actual": {
            "resolved_query": resolved,
            "resolution_action": trace.get("resolution_action") or "continue",
            "speech_act": trace.get("speech_act") or "",
            "state_operations": trace.get("state_operations") or [],
            "is_followup": trace.get("is_followup"),
            "method": trace.get("method"),
            "confidence": trace.get("confidence"),
            "referenced_entities": trace.get("referenced_entities") or [],
            "referenced_turn_ids": trace.get("referenced_turn_ids") or [],
            "state_after": trace.get("state_after") or {},
            "retrieval_action": retrieval_action,
            "retrieval_query": retrieval_query,
            "scope_changed": observed_scope_change,
        },
        "state_mismatches": state_mismatches,
    }


def aggregate(details: list[dict]) -> dict:
    check_totals: dict[str, list[bool]] = defaultdict(list)
    tag_totals: dict[str, list[bool]] = defaultdict(list)
    for item in details:
        for name, passed in item["checks"].items():
            check_totals[name].append(bool(passed))
        for tag in item["tags"]:
            tag_totals[str(tag)].append(bool(item["passed"]))

    cases = len(details)
    passed = sum(bool(item["passed"]) for item in details)
    standalone = [
        item for item in details
        if "standalone" in item["tags"]
    ]
    standalone_preserved = sum(
        bool(item["checks"].get("resolution")) and bool(item["checks"].get("followup"))
        for item in standalone
    )
    metric_values = {
        name: sum(values) / len(values) if values else 0.0
        for name, values in sorted(check_totals.items())
    }
    return {
        "cases": cases,
        "passed": passed,
        "failed": cases - passed,
        "pass_rate": passed / cases if cases else 0.0,
        "metrics": {
            **metric_values,
            "resolution_accuracy": metric_values.get("resolution", 0.0),
            "followup_accuracy": metric_values.get("followup", 0.0),
            "reference_accuracy": metric_values.get("references", 0.0),
            "clarification_action_accuracy": metric_values.get("resolution_action", 0.0),
            "speech_act_accuracy": metric_values.get("speech_act", 0.0),
            "state_operation_accuracy": metric_values.get("state_operations", 0.0),
            "state_accuracy": metric_values.get("state_after", 0.0),
            "retrieval_action_accuracy": metric_values.get("retrieval_action", 0.0),
            "retrieval_query_accuracy": metric_values.get("retrieval_query", 0.0),
            "scope_change_accuracy": metric_values.get("scope_changed", 0.0),
            "standalone_preservation": (
                standalone_preserved / len(standalone) if standalone else 0.0
            ),
        },
        "by_tag": {
            tag: {
                "cases": len(values),
                "passed": sum(values),
                "pass_rate": sum(values) / len(values) if values else 0.0,
            }
            for tag, values in sorted(tag_totals.items())
        },
    }


def _aggregate_layer(details: list[dict]) -> dict:
    cases = len(details)
    passed = sum(bool(item.get("passed")) for item in details)
    check_totals: dict[str, list[bool]] = defaultdict(list)
    for item in details:
        for name, value in (item.get("checks") or {}).items():
            check_totals[name].append(bool(value))
    return {
        "cases": cases,
        "passed": passed,
        "failed": cases - passed,
        "pass_rate": passed / cases if cases else 0.0,
        "metrics": {
            name: sum(values) / len(values) if values else 0.0
            for name, values in sorted(check_totals.items())
        },
    }


def _score_retrieval_layer(base_case: dict, layer_case: dict) -> dict:
    history = list(base_case.get("history") or [])
    query = str(base_case.get("query") or "")
    resolved, trace = resolve_followup_with_trace(query, history)
    fixture = layer_case.get("retrieval") if isinstance(layer_case.get("retrieval"), dict) else {}
    expected = fixture.get("expected") if isinstance(fixture.get("expected"), dict) else {}
    policy_context = dict(base_case.get("context") or {})
    policy_context.update(fixture.get("policy_context") or {})
    action = (
        "none" if trace.get("resolution_action") == "clarify"
        else decide_retrieval_action(policy_context)
    )
    evidence_items = [item for item in fixture.get("evidence_items") or [] if isinstance(item, dict)]
    evidence_pack = build_evidence_pack(
        evidence_items,
        intent=str(policy_context.get("intent") or trace.get("state_after", {}).get("intent") or "qa"),
        char_budget=int(fixture.get("char_budget") or 9000),
    ) if action != "none" else {
        "items": [], "text": "", "char_count": 0, "budget": 0,
        "candidate_count": 0, "dropped_count": 0,
    }
    included_ids = [str(item.get("chunk_id") or "") for item in evidence_pack.get("items") or []]
    seed = build_conversation_context_seed(history, trace)
    state = {
        "intent": str(trace.get("state_after", {}).get("intent") or "qa"),
        "conversation_context_seed": seed,
        "retrieval_action": action,
        "reused_evidence_ids": list(fixture.get("reused_evidence_ids") or []),
        "new_evidence_ids": list(
            fixture["new_evidence_ids"]
            if "new_evidence_ids" in fixture else included_ids
        ),
    }
    context_pack = assemble_conversation_context_pack(state, evidence_pack)

    checks: dict[str, bool] = {}
    if "action" in expected:
        checks["action"] = action == expected["action"]
    if "included_chunk_ids" in expected:
        checks["included_chunks"] = included_ids == list(expected["included_chunk_ids"])
    if "excluded_chunk_ids" in expected:
        excluded = {str(value) for value in expected["excluded_chunk_ids"]}
        checks["excluded_chunks"] = not excluded.intersection(included_ids)
    if "context_turn_ids" in expected:
        checks["context_turns"] = context_pack.get("turn_ids") == list(expected["context_turn_ids"])
    if "artifact_targets" in expected:
        checks["context_artifacts"] = context_pack.get("artifact_targets") == list(expected["artifact_targets"])
    if "reused_evidence_refs" in expected:
        checks["reused_evidence_refs"] = context_pack.get("reused_evidence_refs") == list(
            expected["reused_evidence_refs"]
        )
    if "new_evidence_refs" in expected:
        checks["new_evidence_refs"] = context_pack.get("new_evidence_refs") == list(
            expected["new_evidence_refs"]
        )
    passed = bool(checks) and all(checks.values())
    return {
        "id": layer_case["id"],
        "base_case_id": base_case["id"],
        "passed": passed,
        "checks": checks,
        "actual": {
            "resolved_query": resolved,
            "action": action,
            "included_chunk_ids": included_ids,
            "context_turn_ids": context_pack.get("turn_ids") or [],
            "artifact_targets": context_pack.get("artifact_targets") or [],
            "reused_evidence_refs": context_pack.get("reused_evidence_refs") or [],
            "new_evidence_refs": context_pack.get("new_evidence_refs") or [],
        },
        "expected": expected,
    }


def _sentence_repetition_ok(answer: str, maximum: int) -> bool:
    sentences = [
        _normalized(value) for value in re.split(r"[。！？?!；;\n]+", answer)
        if len(_normalized(value)) >= 6
    ]
    counts: dict[str, int] = defaultdict(int)
    for sentence in sentences:
        counts[sentence] += 1
    return max(counts.values(), default=0) <= maximum


def _score_answer_layer(base_case: dict, layer_case: dict) -> dict:
    fixture = layer_case.get("answer") if isinstance(layer_case.get("answer"), dict) else {}
    answer = str(fixture.get("text") or "")
    expected = fixture.get("expected") if isinstance(fixture.get("expected"), dict) else {}
    normalized_answer = _normalized(answer)
    checks: dict[str, bool] = {}
    if "required_objects" in expected:
        checks["correct_object"] = all(
            _normalized(value) in normalized_answer for value in expected["required_objects"]
        )
    if "required_constraints" in expected:
        checks["inherited_constraints"] = all(
            _normalized(value) in normalized_answer for value in expected["required_constraints"]
        )
    if "required_phrases" in expected:
        checks["required_content"] = all(
            _normalized(value) in normalized_answer for value in expected["required_phrases"]
        )
    if "forbidden_terms" in expected:
        checks["no_drift"] = all(
            _normalized(value) not in normalized_answer for value in expected["forbidden_terms"]
        )
    checks["no_repetition"] = _sentence_repetition_ok(
        answer, int(expected.get("max_sentence_repeats") or 1),
    )
    passed = bool(answer.strip()) and bool(checks) and all(checks.values())
    return {
        "id": layer_case["id"],
        "base_case_id": base_case["id"],
        "passed": passed,
        "checks": checks,
        "actual": {"answer": answer},
        "expected": expected,
        "evaluation_mode": "offline_answer_snapshot_contract",
    }


def _release_gates(
    resolver_summary: dict,
    retrieval_summary: dict,
    answer_summary: dict,
) -> dict:
    thresholds = DEFAULT_RELEASE_THRESHOLDS
    by_tag = resolver_summary.get("by_tag") or {}
    checks = {
        "resolver_overall": resolver_summary.get("pass_rate", 0.0) >= thresholds["resolver_overall"],
        "user_correction": by_tag.get("user_correction", {}).get("pass_rate", 0.0) >= thresholds["user_correction"],
        "assistant_artifact": by_tag.get("assistant_artifact", {}).get("pass_rate", 0.0) >= thresholds["assistant_artifact"],
        "clarification": by_tag.get("clarification", {}).get("pass_rate", 0.0) >= thresholds["clarification"],
        "evidence_reuse": by_tag.get("evidence_reuse", {}).get("pass_rate", 0.0) >= thresholds["evidence_reuse"],
        "evidence_delta": by_tag.get("evidence_delta", {}).get("pass_rate", 0.0) >= thresholds["evidence_delta"],
        "negative": by_tag.get("negative", {}).get("pass_rate", 0.0) >= thresholds["negative"],
        "standalone": by_tag.get("standalone", {}).get("pass_rate", 0.0) >= thresholds["standalone"],
        "long_20": by_tag.get("long_20", {}).get("pass_rate", 0.0) >= thresholds["long_20"],
        "long_40": by_tag.get("long_40", {}).get("pass_rate", 0.0) >= thresholds["long_40"],
        "long_80": by_tag.get("long_80", {}).get("pass_rate", 0.0) >= thresholds["long_80"],
        "retrieval_coverage": retrieval_summary.get("cases", 0) >= thresholds["retrieval_min_cases"],
        "retrieval_overall": retrieval_summary.get("pass_rate", 0.0) >= thresholds["retrieval_overall"],
        "answer_coverage": answer_summary.get("cases", 0) >= thresholds["answer_min_cases"],
        "answer_overall": answer_summary.get("pass_rate", 0.0) >= thresholds["answer_overall"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "thresholds": thresholds,
    }


def evaluate(
    path: str | Path = DEFAULT_DATASET,
    layer_path: str | Path | None = None,
) -> dict:
    details = [score_case(case) for case in load_cases(path)]
    resolver_summary = aggregate(details)
    is_default_dataset = Path(path).resolve() == DEFAULT_DATASET.resolve()
    selected_layer_path = (
        Path(layer_path) if layer_path is not None
        else (DEFAULT_LAYER_DATASET if is_default_dataset else None)
    )
    base_cases = {case["id"]: case for case in load_cases(path)}
    layer_cases = load_layer_cases(selected_layer_path) if selected_layer_path else []
    unknown = [item["base_case_id"] for item in layer_cases if item["base_case_id"] not in base_cases]
    if unknown:
        raise ValueError(f"unknown base cases in layered dataset: {unknown}")
    retrieval_details = [
        _score_retrieval_layer(base_cases[item["base_case_id"]], item)
        for item in layer_cases if isinstance(item.get("retrieval"), dict)
    ]
    answer_details = [
        _score_answer_layer(base_cases[item["base_case_id"]], item)
        for item in layer_cases if isinstance(item.get("answer"), dict)
    ]
    retrieval_summary = _aggregate_layer(retrieval_details)
    answer_summary = _aggregate_layer(answer_details)
    release_gates = (
        _release_gates(resolver_summary, retrieval_summary, answer_summary)
        if is_default_dataset or layer_path is not None
        else {"passed": resolver_summary.get("failed", 0) == 0, "checks": {}, "thresholds": {}}
    )
    return {
        "schema_version": 2,
        "dataset": str(Path(path)),
        "layer_dataset": str(selected_layer_path) if selected_layer_path else "",
        "summary": resolver_summary,
        "layers": {
            "resolver": resolver_summary,
            "retrieval": retrieval_summary,
            "answer": answer_summary,
        },
        "layer_modes": {
            "resolver": "deterministic_production_resolver",
            "retrieval": "production_evidence_pack_with_fixture_candidates",
            "answer": "offline_answer_snapshot_contract",
        },
        "release_gates": release_gates,
        "failures": [item for item in details if not item["passed"]],
        "pipeline_failures": [
            *[item for item in retrieval_details if not item["passed"]],
            *[item for item in answer_details if not item["passed"]],
        ],
        "details": details,
        "retrieval_details": retrieval_details,
        "answer_details": answer_details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate deterministic multi-turn context resolution.")
    parser.add_argument("dataset", nargs="?", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_REPORT))
    parser.add_argument("--layers", default=None, help="Optional retrieval/answer layer fixture JSONL.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when any golden case fails.")
    args = parser.parse_args()

    report = evaluate(args.dataset, args.layers)
    print(json.dumps({
        "layers": report["layers"],
        "release_gates": report["release_gates"],
    }, ensure_ascii=False, indent=2))
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report: {output.resolve()}")
    return 1 if args.strict and not report["release_gates"]["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
