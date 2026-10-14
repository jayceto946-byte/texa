"""Seed reporting: formal gold, fixed denominators and independent-group uncertainty."""
from __future__ import annotations

from collections import Counter
import hashlib
import random
import re
from .evaluator import original_action_id
from .report import generate_report, rate
from .labels import label_hash
from .serialization import permute_sample, strict_loads
from .splits import groups, leakage_checks, sample_fingerprint
from .seed_production import verify_trace
from .seed_reviews import verify_final_review, bound_review_statistics
from backend.services.decision.policy_contracts import canonical_json


def assert_public_artifact(value):
    raw = canonical_json(value)
    if re.search(r"(?:sk-[A-Za-z0-9_-]{16,}|/Users/|[A-Za-z]:\\\\|Bearer\s+\S+)", raw) or re.search(
            r'"(?:api_key|authorization|access_token|password|secret)"\s*:', raw, re.I):
        # authorization_ref and the reviewed authorization object contain no secret.
        raise ValueError("private path or credential in offline artifact")


def formal_qualities(samples, manifest, records, evidence, traces, review_bindings):
    from .validation import validate_sample
    result = {}
    for sample in samples:
        quality = validate_sample(sample, manifest=manifest, records=records, evidence=evidence, locked=True)
        try:
            trace = traces[sample.sample_id]
            if canonical_json(trace).encode() != evidence[sample.source.ref]:
                raise ValueError("source projection evidence mismatch")
            verify_trace(sample, trace)
        except (KeyError, ValueError, TypeError):
            quality.unverified.append("candidate_reachability")
            quality.candidate_reviewed = False
        human = any(s.kind == "human" for s in sample.label_source)
        if human:
            try:
                verify_final_review(sample, review_bindings[sample.sample_id], evidence)
            except (KeyError, ValueError, TypeError):
                quality.unverified.append("independent_blind_review_chain")
        if quality.unverified:
            quality.selection_eligible = quality.diagnostic_eligible = False
        result[sample.sample_id] = quality
    return result


def _hit(sample, prediction):
    return prediction is not None and original_action_id(prediction) in (sample.acceptable_action_ids or [])


def _metrics(samples, lookup, *, enabled):
    if not enabled:
        return {"status": "not_run", "acceptable_accuracy": rate(0, 0), "scheduled_denominator": len(samples)}
    pairs = [(s, lookup.get(s.sample_id)) for s in samples]
    single = [(s, p) for s, p in pairs if s.ambiguity_status == "single_correct"]
    multi = [(s, p) for s, p in pairs if s.ambiguity_status == "multiple_acceptable"]
    choices = [(s, p, original_action_id(p)) for s, p in pairs if p is not None and p.status == "accepted"]
    tool = answer = unnecessary = premature = 0
    for sample, _, action_id in choices:
        action = next(a for a in sample.observation.admissible_actions if a.id == action_id)
        judgment = next(j for j in sample.action_judgments if j.action_id == action_id)
        tool += action.kind == "call_tool"
        answer += action.kind == "generate_answer"
        unnecessary += "unnecessary_tool_call" in judgment.reason_tags
        premature += "premature_answer" in judgment.reason_tags
    statuses = Counter(p.status if p else "missing" for _, p in pairs)
    return {"status": "incomplete" if statuses["missing"] or statuses["disabled/not_run"] else "complete",
        "acceptable_accuracy": rate(sum(_hit(s, p) for s, p in pairs), len(pairs)),
        "single_correct_accuracy": rate(sum(_hit(s, p) for s, p in single), len(single)),
        "multiple_acceptable_accuracy": rate(sum(_hit(s, p) for s, p in multi), len(multi)),
        "invalid_format_rate": rate(statuses["invalid_format"], len(pairs)),
        "unknown_action_id_rate": rate(statuses["unknown_action_id"], len(pairs)),
        "runtime_failure_rate": rate(sum(p is None or p.status in {"timeout", "selector_exception", "disabled/not_run"} for _, p in pairs), len(pairs)),
        "unnecessary_tool_rate": rate(unnecessary, len(pairs)), "unnecessary_among_tools": rate(unnecessary, tool),
        "premature_answer_rate": rate(premature, len(pairs)), "premature_among_answers": rate(premature, answer),
        "prediction_statuses": dict(statuses)}


def _pairwise(samples, left, right, grouped, *, enabled):
    if not enabled:
        return {"status": "not_run", "disagreement": rate(0, 0), "harmful_disagreement": rate(0, 0), "delta": rate(0, 0)}
    legal = [(s, left.get(s.sample_id), right.get(s.sample_id)) for s in samples
        if left.get(s.sample_id) and right.get(s.sample_id) and left[s.sample_id].status == right[s.sample_id].status == "accepted"]
    disagree = [(s, a, b) for s, a, b in legal if original_action_id(a) != original_action_id(b)]
    win = sum(not _hit(s, left.get(s.sample_id)) and _hit(s, right.get(s.sample_id)) for s in samples)
    loss = sum(_hit(s, left.get(s.sample_id)) and not _hit(s, right.get(s.sample_id)) for s in samples)
    clusters = {}
    for sample in samples:
        clusters.setdefault(grouped[sample.source.source_family_id], []).append(
            int(_hit(sample, right.get(sample.sample_id))) - int(_hit(sample, left.get(sample.sample_id))))
    interval = None
    if len(clusters) >= 2:
        rng = random.Random(1701)
        values = list(clusters.values())
        bootstrap = []
        for _ in range(1000):
            selected = [rng.choice(values) for _ in values]
            bootstrap.append(sum(sum(v) for v in selected) / sum(len(v) for v in selected))
        bootstrap.sort()
        interval = [bootstrap[24], bootstrap[974]]
    return {"status": "complete" if all(s.sample_id in left and s.sample_id in right for s in samples) else "incomplete",
        "disagreement": rate(len(disagree), len(legal)),
        "harmful_disagreement": rate(sum(_hit(s, a) != _hit(s, b) for s, a, b in disagree), len(disagree)),
        "both_acceptable_but_different": sum(_hit(s, a) and _hit(s, b) for s, a, b in disagree),
        "right_win": win, "left_win": loss, "tie": len(samples) - win - loss,
        "delta": rate(win - loss, len(samples)), "independent_groups": len(clusters),
        "group_bootstrap_95_interval": interval, "bootstrap_seed": 1701, "bootstrap_resamples": 1000}


def compare_seed(samples, predictions, qualities, splits, *, manifest, traces, review_bindings,
                 teacher_run=None, response_logs=(), review_stats=None, evidence=None):
    # An unbound summary can be displayed as a provisional process note, but
    # cannot authorize the training-preparation gate.
    bound_stats = bound_review_statistics(samples, review_bindings, evidence) if evidence is not None else None
    gate_review_stats = bound_stats
    review_stats = bound_stats or review_stats
    raw_predictions = predictions
    # Gold-only versions are linked explicitly; first responses/logs stay unchanged.
    # Rebind a copy only after proving that the canonical main view is identical.
    remapping = {}
    for sample in samples:
        binding = review_bindings.get(sample.sample_id)
        if binding and binding["base_sample_id"] != sample.sample_id:
            base_id = binding["base_sample_id"]
            if base_id in remapping:
                raise ValueError("multiple gold versions for one teacher decision point")
            remapping[base_id] = sample
    rebound = []
    for prediction in predictions:
        target = remapping.get(prediction.sample_id) if prediction.selector in {"sol", "luna"} else None
        if target is None:
            rebound.append(prediction)
            continue
        if teacher_run and teacher_run["label_hashes"].get(prediction.sample_id) != review_bindings[target.sample_id]["base_label_hash"]:
            raise ValueError("pre-adjudication teacher label binding mismatch")
        viewed, transform = permute_sample(target, seed=prediction.transform.seed, mode=prediction.transform.mode)
        old_transform = prediction.transform.model_copy(update={"original_sample_id": target.sample_id})
        if old_transform != transform or prediction.observation_hash != viewed.observation_hash:
            raise ValueError("adjudication changed the frozen teacher view")
        rebound.append(prediction.model_copy(update={"sample_id": target.sample_id, "transform": transform}))
    predictions = rebound
    # Reuse strict raw-output/membership/transform validation; main Rule must be complete.
    base = generate_report(samples, predictions, qualities, splits)
    grouped = groups(samples)
    eligible = [s for s in samples if qualities[s.sample_id].selection_eligible
                and len(s.observation.admissible_actions) >= 2 and s.source.type != "fault_injection"]
    lookup = {role: {p.sample_id: p for p in predictions if p.selector == role and p.view == "main"}
              for role in ("rule", "sol", "luna")}
    enabled = {"rule": True, "sol": bool(teacher_run and teacher_run.get("enabled")), "luna": bool(teacher_run and teacher_run.get("enabled"))}
    if any(p.selector in {"sol", "luna"} and p.status != "disabled/not_run" for p in predictions) and not teacher_run:
        raise ValueError("teacher predictions require a bound run manifest")
    if teacher_run:
        expected_dataset = hashlib.sha256(canonical_json({s.sample_id: sample_fingerprint(s) for s in samples}).encode()).hexdigest()
        expected_split = hashlib.sha256(canonical_json(splits.model_dump()).encode()).hexdigest()
        exact_release = teacher_run.get("dataset_hash") == expected_dataset and teacher_run.get("split_hash") == expected_split
        if not exact_release:
            for sample in samples:
                if qualities[sample.sample_id].selection_eligible:
                    binding = review_bindings.get(sample.sample_id)
                    current_label_matches = teacher_run["label_hashes"].get(sample.sample_id) == label_hash(sample)
                    if not current_label_matches and (not binding or teacher_run["label_hashes"].get(binding["base_sample_id"]) != binding["base_label_hash"]):
                        raise ValueError("teacher run dataset/split mismatch")
            if any(teacher_run.get("family_assignments", {}).get(s.source.source_family_id) != splits.assignments[s.source.source_family_id] for s in samples):
                raise ValueError("teacher run family split changed after adjudication")
        if (teacher_run.get("runtime_version"), teacher_run.get("registry_version")) != (manifest.runtime_version, manifest.registry_version):
            raise ValueError("teacher run pins mismatch")
        scheduled = [(k["sample_id"], k["selector"]) for k in teacher_run["scheduled"]]
        completed = [(k["sample_id"], k["selector"]) for k in teacher_run["completed"]]
        if len(set(scheduled)) != len(scheduled) or len(set(completed)) != len(completed) or not set(completed) <= set(scheduled):
            raise ValueError("teacher schedule/completion mismatch")
        actual = {(p.sample_id, p.selector) for p in raw_predictions if p.selector in {"sol", "luna"} and p.view == "main"}
        if actual != {key for key in completed if key[1] != "rule"}:
            raise ValueError("teacher prediction completion mismatch")
        expected_missing = set(scheduled) - set(completed)
        if {(k["sample_id"], k["selector"]) for k in teacher_run["missing"]} != expected_missing:
            raise ValueError("teacher missing list mismatch")
        if teacher_run["status"] == "complete" and expected_missing:
            raise ValueError("incomplete batch cannot claim completion")
        if teacher_run["seed"] != splits.seed:
            raise ValueError("teacher main view seed differs from split release")
        for role in ("sol", "luna"):
            for sample in samples:
                pred = lookup[role].get(sample.sample_id)
                if pred:
                    _, transform = permute_sample(sample, seed=teacher_run["seed"])
                    if pred.transform != transform:
                        raise ValueError("teacher main view mismatch")
        logs = {(log["sample_id"], log["selector"]): log for log in response_logs}
        if response_logs and (len(logs) != len(response_logs) or set(logs) != set(completed)):
            raise ValueError("first-response log completion mismatch")
        for (sample_id, role), log in logs.items():
            target_id = remapping[sample_id].sample_id if sample_id in remapping else sample_id
            pred = lookup[role].get(target_id)
            if pred is None or log["raw_output"] != pred.raw_output or not log["first_response"]:
                raise ValueError("first-response raw output mismatch")
            allowed_failure = {"accepted": {None}, "invalid_format": {"malformed"},
                "unknown_action_id": {"unknown_action_id"}, "timeout": {"timeout"},
                "selector_exception": {"refusal", "transport_failure"}}
            if log["failure_type"] not in allowed_failure.get(pred.status, set()):
                raise ValueError("first-response failure attribution mismatch")
            sample = next(s for s in samples if s.sample_id == target_id)
            viewed, _ = permute_sample(sample, seed=teacher_run["seed"])
            if log["sent_input_hash"] != hashlib.sha256(viewed.observation.canonical_json().encode()).hexdigest():
                raise ValueError("logged Policy input mismatch")
    policies = {role: _metrics(eligible, lookup[role], enabled=enabled[role]) for role in lookup}
    pairs = {f"{a}-{b}": _pairwise(eligible, lookup[a], lookup[b], grouped, enabled=enabled[a] and enabled[b])
             for a, b in (("rule", "sol"), ("rule", "luna"), ("sol", "luna"))}
    common_three = [s for s in eligible if all(s.sample_id in lookup[role] and lookup[role][s.sample_id].status == "accepted" for role in lookup)]
    all_disagree = [s for s in common_three if len({original_action_id(lookup[role][s.sample_id]) for role in lookup}) == 3]
    def strata(items):
        scoring = [s for s in items if s in eligible]
        return {"samples": len(items), "families": len({s.source.source_family_id for s in items}),
            "independent_groups": len({grouped[s.source.source_family_id] for s in items}),
            "eligible": len(scoring), "excluded": len(items) - len(scoring),
            "sources": dict(Counter(s.source.type for s in items)),
            "splits": dict(Counter(splits.assignments[s.source.source_family_id] for s in items)),
            "policies": {role: _metrics(scoring, lookup[role], enabled=enabled[role]) for role in lookup},
            "pairwise": {f"{a}-{b}": _pairwise(scoring, lookup[a], lookup[b], grouped, enabled=enabled[a] and enabled[b])
                         for a, b in (("rule", "sol"), ("rule", "luna"), ("sol", "luna"))}}
    split_report = {split: strata([s for s in samples if splits.assignments[s.source.source_family_id] == split])
                    for split in ("development", "validation", "locked_test")}
    reasons = Counter(reason for s in samples if not qualities[s.sample_id].selection_eligible
                      for reason in (qualities[s.sample_id].machine_errors + qualities[s.sample_id].frozen_errors + qualities[s.sample_id].unverified))
    all_selection = [s for s in samples if qualities[s.sample_id].selection_eligible]
    unresolved = [s for s in samples if not (qualities[s.sample_id].selection_eligible or qualities[s.sample_id].diagnostic_eligible)]
    seed_go = bool(samples) and not unresolved and splits.locked and not any(base["data_quality"]["leakage"].values())
    training_go = False
    if seed_go and len(eligible) >= 60 and len({s.source.source_family_id for s in eligible}) >= 40 and gate_review_stats:
        stable = ((gate_review_stats.get("acceptable_set_agreement", {}).get("value") or 0) >= .9
                  and gate_review_stats.get("repeated_families", 0) >= 10
                  and gate_review_stats.get("repeat_comparisons", 0) > 0
                  and gate_review_stats.get("repeat_label_changes", 0) / gate_review_stats["repeat_comparisons"] <= .05)
        if stable:
            for role in ("sol", "luna"):
                good = True
                for split in ("validation", "locked_test"):
                    row = split_report[split]
                    pair = row["pairwise"][f"rule-{role}"]
                    ci = pair.get("group_bootstrap_95_interval")
                    good &= (pair.get("independent_groups", 0) >= 10 and row["policies"][role]["status"] == "complete"
                             and ci is not None and ci[0] > 0 and row["policies"][role]["premature_answer_rate"]["numerator"] <=
                             row["policies"]["rule"]["premature_answer_rate"]["numerator"])
                training_go |= good
    report = {"version": "seed-comparison/v0", "binding": {"dataset_hash": hashlib.sha256(canonical_json({s.sample_id: sample_fingerprint(s) for s in samples}).encode()).hexdigest(),
        "split_hash": hashlib.sha256(canonical_json(splits.model_dump()).encode()).hexdigest(),
        "label_hashes": {s.sample_id: label_hash(s) for s in samples}, "runtime_version": manifest.runtime_version,
        "registry_version": manifest.registry_version, "teacher_run_id": teacher_run.get("run_id") if teacher_run else None},
        "data_quality": {**base["data_quality"], "independent_groups": len(set(grouped.values())),
            "source_types": dict(Counter(s.source.type for s in samples)),
            "projection_scopes": dict(Counter(traces.get(s.sample_id, {}).get("scope", "unverified") for s in samples)),
            "locked_selection": len(all_selection) if splits.locked else 0,
            "locked_diagnostics": sum(q.diagnostic_eligible for q in qualities.values()) if splits.locked else 0,
            "provisional_or_unresolved": len(unresolved), "formal_multicandidate": len(eligible)},
        "candidate_generation": base["candidate_generation"], "policies": policies, "pairwise": pairs,
        "prediction_relations": {"all_three_disagree": rate(len(all_disagree), len(common_three)),
            "all_three_acceptable_but_different": sum(all(_hit(s, lookup[role][s.sample_id]) for role in lookup) for s in all_disagree)},
        "batch_status": teacher_run["status"] if teacher_run else "not_run",
        "failure_types": dict(Counter(log["failure_type"] for log in response_logs if log.get("failure_type"))),
        "splits": split_report,
        "scenarios": {tag: strata([s for s in samples if tag in s.scenario_tags]) for tag in sorted({t for s in samples for t in s.scenario_tags})},
        "hard_tags": {tag: strata([s for s in samples if tag in s.hard_tags]) for tag in sorted({t for s in samples for t in s.hard_tags})},
        "adjudication": {"human_adjudicated": sum(q.semantic_adjudicated and any(l.kind == "human" for l in s.label_source) for s in samples for q in [qualities[s.sample_id]]),
            "automatically_proven": sum(q.semantic_adjudicated and any(l.kind == "approved_rule" for l in s.label_source) for s in samples for q in [qualities[s.sample_id]]),
            "unresolved": len(unresolved), "unresolved_reasons": dict(reasons),
            "multiple_acceptable_all_selection": rate(sum(s.ambiguity_status == "multiple_acceptable" for s in all_selection), len(all_selection)),
            "multiple_acceptable_multicandidate": rate(sum(s.ambiguity_status == "multiple_acceptable" for s in eligible), len(eligible)),
            "review_statistics": review_stats or {"status": "not_supplied"}},
        "forced_runtime_only": base["forced_runtime_only"], "ordering_controls": base["ordering_controls"],
        "end_to_end": {"status": "not_evaluated"},
        "decision": {"seed_quality": "SEED QUALITY GO" if seed_go else "SEED QUALITY HOLD",
            "training_prep": "GO" if training_go else "NO-GO", "training_authorized": False},
        "limitations": ["Synthetic/harness error rates are not production incident rates.",
            "Selector accuracy is not answer accuracy.", "Intervals resample independent related groups, not individual decision points.",
            "Human identity and blind-review declarations require accountable external review; local files cannot authenticate people."]}
    return report
