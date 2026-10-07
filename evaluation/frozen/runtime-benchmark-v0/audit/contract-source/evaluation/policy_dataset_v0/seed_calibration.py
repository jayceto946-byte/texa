"""18-fixture review queue. Proposals are never human adjudications."""
from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from backend.services.decision.policy_contracts import canonical_json
from .labels import label_hash
from .seed_production import SeedRecipeV0, PriorCallV0, project_recipe, generate_sample, load_dataset, write_bundle
from .splits import assign_splits
from .serialization import write_samples

PLAN = {
    "direct": ("single_correct", ["a0"], "概念解释可直接回答；仅 harness forced。"),
    "input-gate": ("single_correct", ["a0"], "附表阻断精确计算；真实 pre-SQL 使用空上下文，原 fixture 不能证明真实 gate 投影。"),
    "textbook-needed": ("single_correct", ["a0"], "教材证据缺失；还需真实范围与索引依据，synthetic scope 仅验证 binder。"),
    "textbook-empty": ("diagnostic-only", [], "空证据、不重试、禁止普通生成；保留 runtime_only。"),
    "progress-needed": ("single_correct", ["a0"], "必须读取实际记录；确认默认七天符合请求。"),
    "progress-done": ("invalid_sample", None, "bounded_result_available 仅在无其他 flag 时生成，不能和 coverage_incomplete 共存。"),
    "multi": ("multiple_acceptable", ["a0", "a1"], "两项查询可以任选第一步；全请求作为习题 query 的相关性仍需人工审查。"),
    "lexical": ("single_correct", ["a2"], "明确不要查询，两项工具无必要信息收益。"),
    "resolved": ("diagnostic-only", None, "当前 matcher 使用 resolved_query，只产生进度工具；原习题候选来源未证明。"),
    "goal": ("single_correct", ["a1"], "目标仅解释指标；goal 来源仍需独立审查，未接 Goal worker。"),
    "optional": ("multiple_acceptable", ["a0", "a1"], "查询为可选，两项均合理；不填写唯一 preferred。"),
    "exercise-empty": ("single_correct", ["a0"], "如实说明同范围无匹配；不允许临场编题。"),
    "failed-allowed": ("single_correct", ["a0"], "可披露记录读取失败，不编造结果。"),
    "unknown-forbidden": ("diagnostic-only", [], "教材结果未知，不得视为成功、不重试；保留 runtime_only。"),
    "scope-defect": ("candidate_generation_error", [], "错误范围注入；与合法投影逐项比较。"),
    "missing-defect": ("candidate_generation_error", [], "原请求未匹配进度 capability；先补合法原投影，再证明漏候选注入。"),
    "pending": ("insufficient_information", None, "缺记录对象、已有信息和目的；当前 query 未匹配进度工具。"),
    "insufficient": ("insufficient_information", None, "指代、结果摘要及充分性标准均缺失；当前 query 未匹配习题工具。"),
}


def fixture_recipe(sample, *, sample_id=None):
    """Construct a test hypothesis, never claim to recover an actual runtime call."""
    obs = sample.observation
    constraints = obs.context.constraints
    calls = []
    prior = obs.previous_result
    if prior:
        counts = {}
        for flag in prior.summary.split(";"):
            if "_count=" in flag:
                field, count = flag.split("_count=")
                counts[field] = int(count)
        code = prior.summary.split("execution_failed_or_unknown:")[-1].split(";")[0] if prior.status != "succeeded" else None
        calls = [PriorCallV0(tool_id=prior.tool_id, status=prior.status, counts=counts,
            error_code=code, coverage_incomplete="coverage_incomplete" in prior.summary,
            evidence_insufficient="evidence_insufficient" in prior.summary)]
    return SeedRecipeV0(sample_id=sample_id or sample.sample_id, source_family_id=sample.source.source_family_id,
        source_ref=f"calibration-projection/{sample_id or sample.sample_id}",
        related_refs=[sample.source.ref, *sample.source.related_refs], request=obs.request,
        resolved_query=obs.context.resolved_query, book_name=constraints.get("book_name", ""),
        subject=constraints.get("subject", ""), answer_mode=constraints.get("answer_mode", "global_general"),
        goal=obs.context.goal, goal_origin_ref=f"calibration-goal/{sample.sample_id}" if obs.context.goal else None,
        prior_calls=calls, missing_inputs=obs.missing_inputs,
        position=sample.source.decision_position, scenario_tags=sample.scenario_tags, used_for_tuning=True)


def calibrate(dataset, output):
    samples, manifest, records, evidence = load_dataset(dataset)
    if {s.sample_id for s in samples} != {f"{name}@v0" for name in PLAN}:
        raise ValueError("calibration expects the original 18 fixture versions")
    queue, traces, derived = [], {}, []
    for sample in samples:
        name = sample.sample_id.split("@")[0]
        disposition, acceptable, reason = PLAN[name]
        recipe = fixture_recipe(sample)
        observation, trace = project_recipe(recipe)
        trace["calibration_note"] = "Constructed hypothesis from visible fixture fields; original runtime provenance remains unverified."
        traces[sample.sample_id] = trace
        matches = observation == sample.observation
        judgments = []
        for action in sample.observation.admissible_actions:
            tags = []
            judgment = "undetermined" if acceptable is None else "acceptable" if action.id in acceptable else "unacceptable"
            if judgment == "unacceptable" and disposition in {"single_correct", "multiple_acceptable"}:
                tags = ["premature_answer" if action.kind == "generate_answer" else "unnecessary_tool_call"]
            judgments.append({"action_id": action.id, "judgment": judgment, "reason_tags": tags,
                              "basis": reason})
        queue.append({"sample_id": sample.sample_id, "observation_hash": sample.observation_hash,
            "label_hash": label_hash(sample), "disposition": disposition,
            "proposed_acceptable_action_ids": acceptable, "action_judgments": judgments,
            "reason": reason, "replay_matches_original": matches,
            "replay_observation_hash": trace["observation_hash"],
            "candidate_origin_status": "constructed_harness_match" if matches else "source_mismatch",
            "responsible_role": "Codex preliminary calibration", "human_reviewer": None,
            "status": "pending_independent_review", "formal_gold": False,
            "required_reviews": ["candidate_source", "all_candidates_semantics", "human_or_approved_rule"]})
        if name not in {"pending", "insufficient", "missing-defect"}:
            variant = fixture_recipe(sample, sample_id=f"{name}@calibration-v1")
            if name == "scope-defect":
                variant = variant.model_copy(update={"fault": "wrong_book"})
            new, new_trace = generate_sample(variant)
            derived.append(new)
            traces[new.sample_id] = new_trace
            evidence[new.source.ref] = canonical_json(new_trace).encode()
            if variant.goal_origin_ref:
                evidence[variant.goal_origin_ref] = canonical_json({"kind": "synthetic_goal", "goal": variant.goal}).encode()
        if name == "missing-defect":
            # Change the unmatched request openly; do not invent an omitted matcher hit.
            variant = fixture_recipe(sample, sample_id="missing-defect@calibration-v1").model_copy(update={
                "request": "查询最近学习进度", "resolved_query": "查询最近学习进度", "fault": "drop_tools"})
            new, new_trace = generate_sample(variant)
            derived.append(new)
            traces[new.sample_id] = new_trace
            evidence[new.source.ref] = canonical_json(new_trace).encode()
    all_samples = samples + derived
    manifest = manifest.model_copy(update={"evidence_digests": {
        ref: hashlib.sha256(data).hexdigest() for ref, data in evidence.items()}})
    splits = assign_splits(all_samples, seed="calibration-v0", overrides={s.source.source_family_id: "development" for s in all_samples})
    write_bundle(output, all_samples, manifest, evidence, records=records, traces=traces, splits=splits)
    write_samples(Path(output) / "original-samples.jsonl", samples)
    write_samples(Path(output) / "derived-samples.jsonl", derived)
    (Path(output) / "calibration-queue.jsonl").write_text("".join(canonical_json(item) + "\n" for item in queue))
    (Path(output) / "calibration-recipes.jsonl").write_text("".join(canonical_json(traces[s.sample_id]["recipe"]) + "\n" for s in derived))
    summary = {"original_samples": 18, "source_families": 15, "derived_versions": len(derived),
        "dispositions": dict(Counter(item["disposition"] for item in queue)),
        "constructed_replay_matches": sum(item["replay_matches_original"] for item in queue),
        "human_reviews": 0, "formally_locked": 0, "teacher_calls": 0,
        "seed_quality": "SEED QUALITY HOLD", "training_prep": "NO-GO",
        "phase_0_complete": False, "blocked_requirements": ["independent candidate review", "human or approved-rule adjudication"],
        "baseline": "previous 4/6 and forced 6/6 are provisional tooling results"}
    (Path(output) / "calibration-summary.json").write_text(canonical_json(summary) + "\n")
    return summary
