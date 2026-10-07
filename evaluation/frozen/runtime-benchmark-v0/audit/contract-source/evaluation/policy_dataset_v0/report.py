"""Three independent layers, explicit denominators, no raw private input in reports."""
from __future__ import annotations

from collections import Counter
from typing import Literal
from pydantic import Field
from backend.services.decision.policy_contracts import StrictV0, parse_decision
from .evaluator import original_action_id
from .splits import leakage_checks
from .serialization import permute_sample


def rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None,
            "display": f"{numerator}/{denominator}" if denominator else "N/A"}


class ExecutionRecordV0(StrictV0):
    """Independent supplied acceptance; not derived from Runtime task status."""
    task_ref: str
    scope: Literal["offline_stub", "real_execution"]
    executed: bool
    acceptance_basis_ref: str | None
    acceptance_passed: bool | None
    original_rejected: int = Field(ge=0)
    fallback_attempted: int = Field(ge=0)
    fallback_accepted: int = Field(ge=0)
    fallback_executed: int = Field(ge=0)
    tool_succeeded: int = Field(ge=0)
    tool_attempted: int = Field(ge=0)
    answer_verification: Literal["verified", "degraded", "unverified", "not_evaluated"]


def _correct(sample, prediction):
    return original_action_id(prediction) in (sample.acceptable_action_ids or [])


def selection_metrics(samples, predictions, qualities):
    eligible = [(s, predictions[s.sample_id]) for s in samples if s.sample_id in predictions
        and qualities[s.sample_id].selection_eligible and len(s.observation.admissible_actions) >= 2
        and predictions[s.sample_id].status != "disabled/not_run"]
    single = [(s, p) for s, p in eligible if s.ambiguity_status == "single_correct"]
    preferred = [(s, p) for s, p in eligible if s.preferred_action_id is not None]
    premature = unnecessary = tool_choices = answer_choices = input_choices = input_true = input_required = 0
    for sample, prediction in eligible:
        action_id = original_action_id(prediction)
        chosen = next((a for a in sample.observation.admissible_actions if a.id == action_id), None)
        judgment = next((j for j in sample.action_judgments if j.action_id == action_id), None)
        if chosen:
            tool_choices += chosen.kind == "call_tool"
            answer_choices += chosen.kind == "generate_answer"
            input_choices += chosen.kind == "request_input"
            input_true += chosen.kind == "request_input" and sample.input_requirement == "required"
        if judgment:
            unnecessary += "unnecessary_tool_call" in judgment.reason_tags
            premature += "premature_answer" in judgment.reason_tags
        input_required += sample.input_requirement == "required"
    return {
        "acceptable_accuracy": rate(sum(_correct(s, p) for s, p in eligible), len(eligible)),
        "single_correct_accuracy": rate(sum(_correct(s, p) for s, p in single), len(single)),
        "preferred_agreement": rate(sum(original_action_id(p) == s.preferred_action_id for s, p in preferred), len(preferred)),
        "invalid_rate": rate(sum(p.status in {"invalid_format", "unknown_action_id"} for _, p in eligible), len(eligible)),
        "timeout": sum(p.status == "timeout" for _, p in eligible),
        "selector_exception": sum(p.status == "selector_exception" for _, p in eligible),
        "unnecessary_tool_call_rate": rate(unnecessary, len(eligible)),
        "unnecessary_among_tool_choices": rate(unnecessary, tool_choices),
        "premature_answer_rate": rate(premature, len(eligible)),
        "premature_among_answer_choices": rate(premature, answer_choices),
        "missing_input_precision": rate(input_true, input_choices),
        "missing_input_recall": rate(input_true, input_required),
    }


def generate_report(samples, predictions, qualities, split_manifest, *, executions=()):
    leakage = leakage_checks(samples, split_manifest)
    if split_manifest.locked and (leakage["blockers"] or leakage["pending"] or any(
            not q.locked_checked or not (q.selection_eligible or q.diagnostic_eligible) for q in qualities.values())):
        raise ValueError("locked report quality/leakage mismatch")
    by_key = {}
    by_sample = {sample.sample_id: sample for sample in samples}
    if len(by_sample) != len(samples):
        raise ValueError("duplicate sample ID")
    for prediction in predictions:
        sample = by_sample.get(prediction.sample_id)
        if sample is None:
            raise ValueError("prediction has no sample")
        expected_hash = prediction.transform.transformed_observation_hash if prediction.transform else sample.observation_hash
        if prediction.observation_hash != expected_hash or (prediction.transform and (
                prediction.transform.original_observation_hash != sample.observation_hash
                or prediction.transform.original_sample_id != sample.sample_id)):
            raise ValueError("prediction/sample binding mismatch")
        if prediction.transform:
            viewed_sample, expected_transform = permute_sample(sample, seed=prediction.transform.seed, mode=prediction.transform.mode)
            if prediction.transform != expected_transform or prediction.view != prediction.transform.mode:
                raise ValueError("invalid transformation mapping")
        else:
            viewed_sample = sample
        candidate_ids = {a.id for a in viewed_sample.observation.admissible_actions}
        if prediction.status in {"accepted", "forced"} and prediction.action_id not in candidate_ids:
            raise ValueError("prediction membership mismatch")
        if prediction.status == "accepted" and parse_decision(prediction.raw_output).action_id != prediction.action_id:
            raise ValueError("raw prediction mismatch")
        key = (prediction.selector, prediction.view, prediction.sample_id)
        if key in by_key:
            raise ValueError("duplicate original prediction")
        by_key[key] = prediction
    if any(("rule", "main", s.sample_id) not in by_key for s in samples):
        raise ValueError("missing original rule prediction; cannot shrink denominator")
    exclusions = Counter()
    for sample in samples:
        quality = qualities[sample.sample_id]
        if not quality.selection_eligible:
            exclusions.update(quality.machine_errors + quality.frozen_errors + quality.unverified or [sample.ambiguity_status])
    split_counts = Counter(split_manifest.assignments[s.source.source_family_id] for s in samples)
    candidate = {}
    for name, fault in (("natural", False), ("fault_injection", True)):
        items = [s for s in samples if (s.source.type == "fault_injection") == fault]
        reviewed = [s for s in items if qualities[s.sample_id].candidate_reviewed]
        candidate[name] = {"sample_count": len(items), "reviewed_count": len(reviewed),
            "unverified_count": len(items) - len(reviewed),
            "unverified_rate": rate(len(items) - len(reviewed), len(items)),
            "failure_rate": rate(sum(s.candidate_generation_valid is False for s in reviewed), len(reviewed)),
            "failures": dict(Counter(e.code for s in reviewed for e in s.candidate_generation_errors))}
    original = {s.sample_id: by_key[("rule", "original", s.sample_id)] for s in samples if ("rule", "original", s.sample_id) in by_key}
    main = {s.sample_id: by_key[("rule", "main", s.sample_id)] for s in samples if ("rule", "main", s.sample_id) in by_key}
    ordering = {"original": selection_metrics(samples, original, qualities), "views": {}}
    for view in ("main", "position_only", "position_and_id"):
        pairs = [(s, original[s.sample_id], by_key[("rule", view, s.sample_id)]) for s in samples
            if s.sample_id in original and ("rule", view, s.sample_id) in by_key
            and qualities[s.sample_id].selection_eligible and len(s.observation.admissible_actions) >= 2]
        legal = [(s, left, right) for s, left, right in pairs if left.status == right.status == "accepted"]
        positions = Counter()
        gold_positions = Counter()
        for sample, _, prediction in pairs:
            local_order = prediction.transform.transformed_order
            if prediction.status == "accepted":
                positions[str(local_order.index(prediction.action_id))] += 1
            for acceptable in sample.acceptable_action_ids or []:
                gold_positions[str(local_order.index(prediction.transform.action_mapping[acceptable]))] += 1
        ordering["views"][view] = {"pair_count": len(pairs), "selected_position_distribution": dict(positions),
            "acceptable_position_distribution": dict(gold_positions),
            "semantic_choice_change": rate(sum(original_action_id(l) != original_action_id(r) for _, l, r in legal), len(legal)),
            "acceptable_status_change": rate(sum(_correct(s, l) != _correct(s, r) for s, l, r in legal), len(legal))}
    ordering["original_position_distribution"] = dict(Counter(str(next(i for i, a in enumerate(s.observation.admissible_actions)
        if a.id == original_action_id(original[s.sample_id]))) for s in samples if s.sample_id in original
        and qualities[s.sample_id].selection_eligible and len(s.observation.admissible_actions) > 1
        and original[s.sample_id].status == "accepted"))
    ordering["original_acceptable_position_distribution"] = dict(Counter(str(i) for s in samples
        if qualities[s.sample_id].selection_eligible and len(s.observation.admissible_actions) > 1
        for i, action in enumerate(s.observation.admissible_actions) if action.id in (s.acceptable_action_ids or [])))
    forced = [(s, main[s.sample_id]) for s in samples if s.sample_id in main and len(s.observation.admissible_actions) == 1]
    forced_reviewed = [(s, p) for s, p in forced if qualities[s.sample_id].selection_eligible]
    gates = [(s, p) for s, p in forced_reviewed if s.source.decision_position == "pre_sql_input_gate"]
    required_gates = [(s, p) for s, p in gates if s.input_requirement == "required"]
    teachers = [p for p in predictions if p.selector != "rule"]
    active_teacher_name = "fake_teacher" if any(p.selector == "fake_teacher" for p in teachers) else "teacher"
    teacher_main = {p.sample_id: p for p in teachers if p.selector == active_teacher_name and p.view == "main"}
    jointly_eligible = [s for s in samples if qualities[s.sample_id].selection_eligible
        and len(s.observation.admissible_actions) > 1 and s.sample_id in main and s.sample_id in teacher_main
        and teacher_main[s.sample_id].status != "disabled/not_run"]
    common = [s for s in jointly_eligible if main[s.sample_id].status == teacher_main[s.sample_id].status == "accepted"]
    disagreements = [s for s in common if original_action_id(main[s.sample_id]) != original_action_id(teacher_main[s.sample_id])]
    teacher_comparison = {"status": "test_only" if active_teacher_name == "fake_teacher" else "disabled/not_run",
        "accuracy": selection_metrics(samples, teacher_main, qualities),
        "disagreement": rate(len(disagreements), len(common)),
        "harmful_disagreement": rate(sum(_correct(s, main[s.sample_id]) != _correct(s, teacher_main[s.sample_id]) for s in disagreements), len(disagreements)),
        "paired_rule_win": sum(_correct(s, main[s.sample_id]) and not _correct(s, teacher_main[s.sample_id]) for s in jointly_eligible),
        "paired_teacher_win": sum(not _correct(s, main[s.sample_id]) and _correct(s, teacher_main[s.sample_id]) for s in jointly_eligible),
        "paired_tie": sum(_correct(s, main[s.sample_id]) == _correct(s, teacher_main[s.sample_id]) for s in jointly_eligible),
        "delta": rate(sum(_correct(s, teacher_main[s.sample_id]) - _correct(s, main[s.sample_id]) for s in jointly_eligible), len(jointly_eligible))}
    executed = [r for r in executions if r.executed]
    if len({r.task_ref for r in executions}) != len(executions):
        raise ValueError("duplicate task acceptance record")
    judged = [r for r in executed if r.acceptance_basis_ref and r.acceptance_passed is not None]
    e2e = {"status": "not_evaluated" if not executed else "independent_records",
        "task_acceptance": rate(sum(r.acceptance_passed for r in judged), len(judged)),
        "acceptance_coverage": rate(len(judged), len(executed)),
        "tool_success": rate(sum(r.tool_succeeded for r in executed), sum(r.tool_attempted for r in executed)),
        "scope_counts": dict(Counter(r.scope for r in executed)),
        "answer_verification": dict(Counter(r.answer_verification for r in executed)),
        **{field: sum(getattr(r, field) for r in executions) for field in (
            "original_rejected", "fallback_attempted", "fallback_accepted", "fallback_executed")}}
    return {"format_version": "policy-dataset-report/v0", "scope": "finite offline fixtures; no online answer-quality claim",
        "data_quality": {"samples": len(samples), "families": len({s.source.source_family_id for s in samples}),
            "splits": dict(split_counts), "ambiguity": dict(Counter(s.ambiguity_status for s in samples)),
            "family_splits": dict(Counter(split_manifest.assignments[f] for f in {s.source.source_family_id for s in samples})),
            "scenarios": dict(Counter(tag for s in samples for tag in s.scenario_tags)),
            "exclusions": dict(exclusions), "pending_adjudication": sum("semantic_adjudication" in q.unverified for q in qualities.values()),
            "fixture_labels_pending_human_or_approved_rule": sum(any(l.kind == "fixture_review" for l in s.label_source) for s in samples),
            "leakage": leakage, "manifest_locked": split_manifest.locked},
        "candidate_generation": candidate, "policy_selection": selection_metrics(samples, main, qualities),
        "forced_runtime_only": {"forced": len(forced), "forced_correct": rate(sum(_correct(s, p) for s, p in forced_reviewed), len(forced_reviewed)),
            "forced_excluded": len(forced) - len(forced_reviewed),
            "zero_candidate_routes": sum(p.status == "runtime_only" for p in main.values()),
            "runtime_only": sum(s.ambiguity_status == "runtime_only" for s in samples),
            "runtime_only_confirmed": sum(qualities[s.sample_id].diagnostic_eligible and s.ambiguity_status == "runtime_only" for s in samples),
            "gate_precision": rate(len(required_gates), len(gates)), "gate_recall": rate(sum(p.status == "forced" for _, p in required_gates), len(required_gates))},
        "ordering_controls": ordering, "teacher_comparison": teacher_comparison, "end_to_end": e2e,
        "prediction_statuses": dict(Counter(p.status for p in predictions if p.selector == "rule" and p.view == "main"))}
