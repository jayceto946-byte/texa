import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.services.decision.policy_contracts import canonical_json
from evaluation.policy_dataset_v0.seed_production import (
    SeedRecipeV0, PriorCallV0, generate_sample, project_recipe, verify_trace,
    load_dataset, produce, offline_registry,
)
from evaluation.policy_dataset_v0.seed_reviews import (
    HumanReviewV0, review_packet, validate_review, finalize_sample, verify_final_review, review_statistics,
    confirm_candidates, bound_review_statistics,
)
from evaluation.policy_dataset_v0.seed import main, calibration_safe_splits
from evaluation.policy_dataset_v0.seed_report import formal_qualities, compare_seed
from evaluation.policy_dataset_v0.teacher_batch import (
    TeacherConfigV0, TeacherResponseV0, BatchAuthorizationV0, prepare_batch, run_batch,
)
from evaluation.policy_dataset_v0.serialization import strict_loads, permute_sample
from evaluation.policy_dataset_v0.splits import assign_splits, lock_manifest
from evaluation.policy_dataset_v0.evaluator import evaluate_views

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evaluation/fixtures/policy_dataset_v0_1"


def recipe(**updates):
    return SeedRecipeV0.model_validate({"sample_id": "independent-progress@v0", "source_family_id": "independent-progress",
        "source_ref": "synthetic/independent-progress@v0", "request": "查询最近学习进度", "resolved_query": "查询最近学习进度",
        "book_name": "synthetic-book", "subject": "数学", **updates})


def blank_manifest():
    _, manifest, _, _ = load_dataset(FIXTURES)
    return manifest.model_copy(update={"reviews": {}, "evidence_digests": {}, "approved_rules": {}})


def human_review(sample, *, reviewer="human-A", acceptable=None, **updates):
    template = review_packet(sample)["review_template"]
    acceptable = acceptable if acceptable is not None else ["a0"]
    template.update(reviewer_id=reviewer, candidate_generation_valid=True,
        candidate_reason="Matcher and binder reproduce this frozen synthetic task; no scope conflict.",
        ambiguity_status="single_correct" if len(acceptable) == 1 else "multiple_acceptable",
        acceptable_action_ids=acceptable, action_judgments=[{
            "action_id": a.id, "judgment": "acceptable" if a.id in acceptable else "unacceptable",
            "reason_tags": [] if a.id in acceptable else ["premature_answer"]} for a in sample.observation.admissible_actions],
        action_reasons={a.id: "Retrieves the required bounded progress facts." if a.kind == "call_tool" else
                        "The request requires current records before an answer." for a in sample.observation.admissible_actions},
        input_requirement="not_required", reason="Actual record request requires the progress tool before an answer.",
        elapsed_seconds=10.0, **updates)
    return HumanReviewV0.model_validate(template)


def finalized():
    sample, trace = generate_sample(recipe())
    content = canonical_json(trace).encode()
    evidence = {sample.source.ref: content}
    manifest = blank_manifest()
    manifest.evidence_digests = {sample.source.ref: hashlib.sha256(content).hexdigest()}
    reviews = [human_review(sample), human_review(sample, reviewer="human-B")]
    final = finalize_sample(sample, reviews, reviews[0], new_sample_id="independent-progress@gold-v1",
        manifest=manifest, evidence=evidence, trace=trace)
    return sample, trace, reviews, final


def configs():
    return [TeacherConfigV0(role=role, provider="test-provider", model_id=f"test-{role}-snapshot-001",
        snapshot="001", temperature=0.0, top_p=1.0, token_limit=100, reasoning={}, seed=1,
        timeout_seconds=1.0, response_format="json_object", sdk_version="test/1") for role in ("sol", "luna")]


def prepared():
    _, _, _, (sample, manifest, evidence, record, trace, binding) = finalized()
    splits = assign_splits([sample], seed="seed-v0")
    traces, bindings = {sample.sample_id: trace}, {sample.sample_id: binding}
    qualities = formal_qualities([sample], manifest, [record], evidence, traces, bindings)
    assert qualities[sample.sample_id].selection_eligible
    plan, inputs = prepare_batch([sample], manifest, splits, traces, qualities, seed=splits.seed, configs=configs())
    return sample, manifest, splits, traces, bindings, qualities, plan, inputs


class FakeTransport:
    max_retries = 0
    def __init__(self, raw=None, failure=None, refusal=False):
        self.raw, self.failure, self.refusal, self.calls = raw, failure, refusal, []
    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure("private transport detail must not be logged")
        value = strict_loads(kwargs["observation_json"])
        action = next(a["id"] for a in value["admissible_actions"] if a["kind"] == "call_tool")
        return TeacherResponseV0(raw_output=self.raw if self.raw is not None else canonical_json({"action_id": action}),
            refusal=self.refusal, usage={"input_tokens": 20, "output_tokens": 5}, returned_model=kwargs["config"].model_id)


def authorization(plan, **updates):
    return BatchAuthorizationV0.model_validate({"authorization_ref": "test-authorization/001",
        "data_scope_hash": plan["input_hash"], "paid_calls_approved": True, "data_export_approved": True,
        "plan_hash": plan["plan_hash"],
        "max_calls": 2, "max_output_tokens": 200, "max_seconds": 10.0, **updates})


def test_calibration_preserves_originals_and_development(tmp_path):
    original = (FIXTURES / "samples.jsonl").read_bytes()
    output = tmp_path / "calibration"
    main(["calibrate", "--output", str(output)])
    assert (FIXTURES / "samples.jsonl").read_bytes() == original
    samples, _, records, _ = load_dataset(output)
    assert len(samples) == 34
    assert len(records) == 16  # Preserved provisional fixture records, no invented humans.
    split = strict_loads((output / "split.json").read_text())
    assert set(split["assignments"].values()) == {"development"} and not split["locked"]
    summary = strict_loads((output / "calibration-summary.json").read_text())
    assert summary["dispositions"] == {"single_correct": 8, "multiple_acceptable": 2,
        "candidate_generation_error": 2, "insufficient_information": 2, "invalid_sample": 1, "diagnostic-only": 3}
    assert summary["derived_versions"] == 16
    assert summary["constructed_replay_matches"] == 11 and summary["phase_0_complete"] is False
    queue = [strict_loads(line) for line in (output / "calibration-queue.jsonl").read_text().splitlines()]
    by_id = {row["sample_id"]: row for row in queue}
    assert by_id["progress-done@v0"]["disposition"] == "invalid_sample"
    assert all(by_id[f"{name}@v0"]["candidate_origin_status"] == "source_mismatch"
               for name in ("resolved", "pending", "insufficient", "missing-defect", "input-gate"))
    assert all(row["status"] == "pending_independent_review" and row["human_reviewer"] is None for row in queue)
    with pytest.raises(ValueError, match="already exists"):
        main(["calibrate", "--output", str(output)])


def test_actual_matcher_binder_and_previous_result_are_used():
    sample, trace = generate_sample(recipe())
    assert [a.kind for a in sample.observation.admissible_actions] == ["call_tool", "generate_answer"]
    assert sample.observation.admissible_actions[0].args.input == {"book_name": "synthetic-book", "subject": "数学", "days": 7, "limit": 12}
    assert trace["matched_tool_refs"][0]["id"] == "get_recent_progress"
    assert sample.candidate_generation_valid is None and sample.acceptable_action_ids is None
    after, trace = project_recipe(recipe(prior_calls=[{"tool_id": "get_recent_progress", "status": "succeeded", "coverage_incomplete": True}]))
    assert after.previous_result.summary == "coverage_incomplete"
    assert [a.kind for a in after.admissible_actions] == ["generate_answer"]
    assert {e["reason"] for e in trace["projection_exclusions"]} == {"duplicate_or_retry"}


@pytest.mark.parametrize("status", ["succeeded", "failed", "unknown"])
def test_never_retry_completed_or_uncertain_tool(status):
    obs, trace = project_recipe(recipe(prior_calls=[{"tool_id": "get_recent_progress", "status": status}]))
    assert all(a.kind != "call_tool" for a in obs.admissible_actions)
    assert obs.previous_result.status == status


def test_candidate_changes_only_via_legal_state_or_explicit_fault():
    normal, _ = generate_sample(recipe())
    bounded, _ = generate_sample(recipe(budget_calls=0))
    assert len(normal.observation.admissible_actions) == 2 and len(bounded.observation.admissible_actions) == 1
    faulty, trace = generate_sample(recipe(fault="drop_tools"))
    assert faulty.source.type == "fault_injection" and len(trace["legal_observation"]["admissible_actions"]) == 2
    assert verify_trace(faulty, trace)
    bad = copy.deepcopy(trace)
    bad["matched_tool_refs"] = []
    with pytest.raises(ValueError, match="trace mismatch"):
        verify_trace(faulty, bad)
    with pytest.raises(ValueError, match="original legal tool"):
        generate_sample(recipe(request="解释概念", resolved_query="解释概念", fault="drop_tools"))


def test_textbook_zero_and_real_gate_scope():
    text = "按教材检索连续定义"
    needed, _ = project_recipe(recipe(request=text, resolved_query=text, answer_mode="textbook_grounded"))
    assert [a.kind for a in needed.admissible_actions] == ["call_tool"]
    empty, _ = project_recipe(recipe(request=text, resolved_query=text, answer_mode="textbook_grounded",
        prior_calls=[{"tool_id": "search_textbook", "status": "succeeded", "counts": {"evidence_items": 0}, "evidence_insufficient": True}]))
    assert empty.admissible_actions == []
    gated, _ = project_recipe(recipe(position="pre_sql_input_gate", missing_inputs=[{"name": "附表", "blocking": True}]))
    assert gated.context.constraints == {"book_name": "", "subject": ""}
    assert [a.kind for a in gated.admissible_actions] == ["request_input"]


@pytest.mark.parametrize("updates", [
    {"goal": "解释方法"}, {"budget_calls": 0, "prior_calls": [{"tool_id": "get_recent_progress", "status": "failed"}]},
    {"prior_calls": [{"tool_id": "get_recent_progress", "status": "succeeded", "counts": {"anything": 1}}]},
    {"prior_calls": [{"tool_id": "search_textbook", "status": "succeeded", "counts": {"evidence_items": 1}}]},
    {"position": "pre_sql_input_gate"},
])
def test_unreproducible_states_are_rejected(updates):
    with pytest.raises(ValueError):
        generate_sample(recipe(**updates))


def test_production_batches_separate_faults_and_merge_related_groups(tmp_path):
    recipes = [recipe(related_refs=["template/task-A"]).model_dump(),
        recipe(sample_id="paired@v0", source_family_id="paired", source_ref="synthetic/paired@v0",
               budget_calls=0, related_refs=["template/task-A"]).model_dump(),
        recipe(sample_id="fault@v0", source_ref="synthetic/fault@v0", fault="wrong_book").model_dump()]
    output = tmp_path / "batch"
    produce(recipes, blank_manifest(), output)
    samples, _, _, _ = load_dataset(output)
    assert len(samples) == 3
    assert len((output / "natural-samples.jsonl").read_text().splitlines()) == 2
    assert len((output / "fault-controls.jsonl").read_text().splitlines()) == 1
    split = strict_loads((output / "split.json").read_text())
    assert len(set(split["assignments"].values())) == 1


def test_review_packet_hides_labels_and_predictions():
    sample, _ = generate_sample(recipe())
    packet = review_packet(sample)
    assert "acceptable_action_ids" not in packet
    assert packet["review_template"]["acceptable_action_ids"] is None
    assert packet["review_template"]["reviewer_id"] == ""
    assert not any(k in packet for k in ("scenario_tags", "split", "predictions"))


@pytest.mark.parametrize("damage", ["hash", "missing_judgment", "missing_reason", "extra_gold", "unblinded", "model_reviewer"])
def test_blind_review_integrity(damage):
    sample, _ = generate_sample(recipe())
    review = human_review(sample).model_dump()
    if damage == "hash": review["label_hash"] = "0" * 64
    elif damage == "missing_judgment": review["action_judgments"].pop()
    elif damage == "missing_reason": review["action_reasons"].pop("a1")
    elif damage == "extra_gold": review["acceptable_action_ids"].append("a999")
    elif damage == "unblinded": review["predictions_visible"] = True
    elif damage == "model_reviewer": review["reviewer_kind"] = "teacher"
    with pytest.raises(ValueError): validate_review(sample, review)


def test_finalization_requires_dual_blind_review_and_third_for_disagreement():
    sample, trace, reviews, result = finalized()
    _, manifest, evidence, _, _, _ = result
    with pytest.raises(ValueError, match="two independent"):
        finalize_sample(sample, reviews[:1], reviews[0], new_sample_id="new@v1", manifest=manifest, evidence=evidence, trace=trace)
    other = human_review(sample, reviewer="human-B", acceptable=["a0", "a1"])
    with pytest.raises(ValueError, match="third human"):
        finalize_sample(sample, [reviews[0], other], reviews[0], new_sample_id="new@v1", manifest=manifest, evidence=evidence, trace=trace)
    stats = review_statistics([sample], [reviews[0], other])
    assert stats["acceptable_set_agreement"]["numerator"] == 0
    assert stats["per_candidate_disagreements"] == 1
    third = human_review(sample, reviewer="human-C", round="adjudication", predictions_visible=True)
    third_result = finalize_sample(sample, [reviews[0], other], third, new_sample_id="new@v1", manifest=manifest, evidence=evidence, trace=trace)
    assert third_result[0].sample_id == "new@v1"


def test_release_chain_and_formal_quality():
    _, _, _, (sample, manifest, evidence, record, trace, binding) = finalized()
    assert verify_final_review(sample, binding, evidence)
    qualities = formal_qualities([sample], manifest, [record], evidence, {sample.sample_id: trace}, {sample.sample_id: binding})
    assert qualities[sample.sample_id].selection_eligible
    locked = lock_manifest([sample], assign_splits([sample]), qualities)
    assert locked.locked
    bad = formal_qualities([sample], manifest, [record], evidence, {}, {})
    assert not bad[sample.sample_id].selection_eligible
    assert "candidate_reachability" in bad[sample.sample_id].unverified


def test_duplicate_human_and_repeat_review_counts():
    sample, _, reviews, _ = finalized()
    with pytest.raises(ValueError, match="duplicate"):
        review_statistics([sample], [reviews[0], reviews[0]])
    repeat = human_review(sample, round="repeat")
    stats = review_statistics([sample], [*reviews, repeat])
    assert stats["double_blind_samples"] == 1 and stats["repeated_families"] == 1
    assert stats["repeat_label_changes"] == 0


def test_no_teacher_calls_before_independent_candidate_review():
    sample, trace = generate_sample(recipe())
    manifest = blank_manifest()
    qualities = formal_qualities([sample], manifest, [], {}, {sample.sample_id: trace}, {})
    plan, inputs = prepare_batch([sample], manifest, assign_splits([sample]), {sample.sample_id: trace}, qualities, seed="dataset-v0")
    assert inputs == [] and plan["enabled"] is False


def test_teachers_and_rule_receive_identical_frozen_bytes(tmp_path):
    sample, manifest, splits, traces, bindings, qualities, plan, inputs = prepared()
    sol, luna = FakeTransport(), FakeTransport()
    predictions, run = run_batch(plan, inputs, {"sol": sol, "luna": luna}, authorization(plan), tmp_path / "run", run_id="test-run")
    assert run["status"] == "complete" and run["calls"] == 2
    assert len(sol.calls) == len(luna.calls) == 1
    assert sol.calls[0]["observation_json"] == luna.calls[0]["observation_json"] == inputs[0]["input_json"]
    assert sol.calls[0]["prompt"] == luna.calls[0]["prompt"]
    report = compare_seed([sample], predictions, qualities, splits, manifest=manifest, traces=traces, review_bindings=bindings,
        teacher_run=run, response_logs=[strict_loads(line) for line in (tmp_path / "run/responses.jsonl").read_text().splitlines()])
    assert all(report["policies"][role]["acceptable_accuracy"]["value"] == 1 for role in ("rule", "sol", "luna"))
    assert report["end_to_end"]["status"] == "not_evaluated"
    assert report["decision"]["training_prep"] == "NO-GO"


@pytest.mark.parametrize("kwargs,status,failure", [
    ({"raw": "oops"}, "invalid_format", "malformed"),
    ({"raw": '{"action_id":"x"}'}, "unknown_action_id", "unknown_action_id"),
    ({"failure": TimeoutError}, "timeout", "timeout"),
    ({"failure": ConnectionError}, "selector_exception", "transport_failure"),
    ({"raw": "refused", "refusal": True}, "selector_exception", "refusal"),
])
def test_first_failures_retained_without_retry(tmp_path, kwargs, status, failure):
    sample, manifest, splits, traces, bindings, qualities, plan, inputs = prepared()
    sol, luna = FakeTransport(**kwargs), FakeTransport()
    predictions, run = run_batch(plan, inputs, {"sol": sol, "luna": luna}, authorization(plan), tmp_path / "run", run_id="test-failure")
    assert len(sol.calls) == 1
    first = next(p for p in predictions if p.selector == "sol")
    assert first.status == status
    logs = [strict_loads(line) for line in (tmp_path / "run/responses.jsonl").read_text().splitlines()]
    assert next(log for log in logs if log["selector"] == "sol")["failure_type"] == failure
    report = compare_seed([sample], predictions, qualities, splits, manifest=manifest, traces=traces,
        review_bindings=bindings, teacher_run=run, response_logs=logs)
    assert report["policies"]["sol"]["acceptable_accuracy"] == {"numerator": 0, "denominator": 1, "value": 0.0, "display": "0/1"}
    assert "private transport detail" not in (tmp_path / "run/responses.jsonl").read_text()


def test_incomplete_batch_keeps_common_denominator_and_missing_list(tmp_path):
    sample, manifest, splits, traces, bindings, qualities, plan, inputs = prepared()
    sol, luna = FakeTransport(), FakeTransport()
    predictions, run = run_batch(plan, inputs, {"sol": sol, "luna": luna}, authorization(plan, max_calls=1), tmp_path / "run", run_id="test-budget")
    assert run["status"] == "incomplete" and run["missing"] == [{"sample_id": sample.sample_id, "selector": "luna"}]
    assert len(sol.calls) == 1 and not luna.calls
    report = compare_seed([sample], predictions, qualities, splits, manifest=manifest, traces=traces,
        review_bindings=bindings, teacher_run=run)
    assert report["policies"]["luna"]["status"] == "incomplete"
    assert report["policies"]["luna"]["acceptable_accuracy"]["denominator"] == 1
    assert report["policies"]["luna"]["acceptable_accuracy"]["numerator"] == 0


@pytest.mark.parametrize("damage", ["authorization", "prompt", "input", "retry", "model", "schedule"])
def test_teacher_preflight_fails_before_creating_output(tmp_path, damage):
    _, _, _, _, _, _, plan, inputs = prepared()
    auth = authorization(plan)
    transports = {"sol": FakeTransport(), "luna": FakeTransport()}
    if damage == "authorization": auth = authorization(plan, data_scope_hash="0" * 64)
    elif damage == "prompt": plan["prompt"] += "extra"
    elif damage == "input": inputs[0]["input_json"] += " "
    elif damage == "retry": transports["sol"].max_retries = 2
    elif damage == "model": plan["configs"][0]["model_id"] = "latest"
    elif damage == "schedule": plan["scheduled"].pop()
    with pytest.raises(ValueError): run_batch(plan, inputs, transports, auth, tmp_path / "run", run_id="rejected")
    assert not (tmp_path / "run").exists()
    assert not transports["sol"].calls and not transports["luna"].calls


def test_fixture_families_cannot_become_independent_test():
    samples, _, _, _ = load_dataset(FIXTURES)
    split = calibration_safe_splits(samples)
    assert set(split.assignments.values()) == {"development"}
    wrong = assign_splits(samples, seed=split.seed, overrides={s.source.source_family_id: "locked_test" for s in samples})
    with pytest.raises(ValueError, match="conflict"):
        calibration_safe_splits(samples, seed=wrong.seed, previous=wrong)


def test_cold_calibration_never_imports_config_or_reads_credentials(tmp_path):
    code = '''
import sys, socket, sqlite3, pathlib, os
oldread = pathlib.Path.read_bytes
def read(self):
    assert self.name != ".env" and "credential" not in self.name
    return oldread(self)
pathlib.Path.read_bytes = read
socket.socket.connect = lambda *_: (_ for _ in ()).throw(AssertionError("network"))
sqlite3.connect = lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("database"))
from evaluation.policy_dataset_v0.seed import main
main(["calibrate", "--output", sys.argv[1]])
assert "config" not in sys.modules
assert "graph.generator" not in sys.modules
'''
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path / "cold")], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_teacher_predictions_survive_blind_gold_version_without_view_changes(tmp_path):
    sample, trace = generate_sample(recipe())
    manifest = blank_manifest()
    content = canonical_json(trace).encode()
    evidence = {sample.source.ref: content}
    manifest.evidence_digests = {sample.source.ref: hashlib.sha256(content).hexdigest()}
    candidate = human_review(sample, reviewer="candidate-human")
    reviewed, manifest, evidence, trace = confirm_candidates(sample, candidate, new_sample_id="candidate-reviewed@v1",
        manifest=manifest, evidence=evidence, trace=trace)
    assert reviewed.acceptable_action_ids is None and reviewed.label_source == []
    splits = assign_splits([reviewed], seed="seed-v0")
    from evaluation.policy_dataset_v0.validation import validate_sample
    q = validate_sample(reviewed, manifest=manifest, records=[], evidence=evidence, locked=True)
    assert q.candidate_reviewed and not q.semantic_adjudicated
    plan, inputs = prepare_batch([reviewed], manifest, splits, {reviewed.sample_id: trace}, {reviewed.sample_id: q}, seed=splits.seed, configs=configs())
    sol, luna = FakeTransport(), FakeTransport()
    predictions, run = run_batch(plan, inputs, {"sol": sol, "luna": luna}, authorization(plan), tmp_path / "run", run_id="pre-gold-run")
    reviews = [human_review(reviewed), human_review(reviewed, reviewer="human-B")]
    gold, manifest, evidence, record, trace, binding = finalize_sample(reviewed, reviews, reviews[0],
        new_sample_id="final-gold@v2", manifest=manifest, evidence=evidence, trace=trace)
    assert gold.source.ref == sample.source.ref and gold.source.related_refs == sample.source.related_refs
    assert inputs[0]["input_json"] == permute_sample(gold, seed=splits.seed)[0].observation.canonical_json()
    qualities = formal_qualities([gold], manifest, [record], evidence, {gold.sample_id: trace}, {gold.sample_id: binding})
    final_split = assign_splits([gold], seed=splits.seed, previous=splits)
    final_split = lock_manifest([gold], final_split, qualities)
    # Fresh Rule uses final gold version; teacher responses remain bound to the pre-gold ID.
    rule = [p for p in evaluate_views([gold], seed=splits.seed) if p.selector == "rule"]
    incoming = rule + [p for p in predictions if p.selector in {"sol", "luna"}]
    logs = [strict_loads(line) for line in (tmp_path / "run/responses.jsonl").read_text().splitlines()]
    report = compare_seed([gold], incoming, qualities, final_split, manifest=manifest, traces={gold.sample_id: trace},
        review_bindings={gold.sample_id: binding}, teacher_run=run, response_logs=logs, evidence=evidence)
    assert report["policies"]["sol"]["acceptable_accuracy"]["value"] == 1
    assert predictions[1].sample_id == reviewed.sample_id  # First output was not overwritten.
    assert report["adjudication"]["review_statistics"]["double_blind_samples"] == 1
    assert report["decision"]["seed_quality"] == "SEED QUALITY GO"


def test_release_cli_rejects_provisional_before_creating_directory(tmp_path):
    calibration = tmp_path / "calibration"
    main(["calibrate", "--output", str(calibration)])
    with pytest.raises(ValueError, match="quality gate"):
        main(["release", "--dataset", str(calibration), "--output", str(tmp_path / "locked"), "--include", "progress-done@calibration-v1"])
    assert not (tmp_path / "locked").exists()


def test_report_cli_formal_denominator_is_zero_for_calibration(tmp_path):
    calibration, report = tmp_path / "calibration", tmp_path / "report"
    main(["calibrate", "--output", str(calibration)])
    main(["report", "--dataset", str(calibration), "--output", str(report)])
    data = strict_loads((report / "report.json").read_text())
    assert data["data_quality"]["formal_multicandidate"] == 0
    assert data["policies"]["rule"]["acceptable_accuracy"]["display"] == "N/A"
    assert data["policies"]["sol"]["status"] == "not_run"
    assert data["decision"]["seed_quality"] == "SEED QUALITY HOLD"


def test_cli_review_finalize_release_roundtrip(tmp_path):
    from evaluation.policy_dataset_v0.seed_production import write_bundle
    draft = tmp_path / "draft"
    produce([recipe().model_dump()], blank_manifest(), draft)
    samples, _, _, _ = load_dataset(draft)
    sample = samples[0]
    review = human_review(sample, reviewer="test-only-candidate-reviewer")
    review_file = tmp_path / "candidate-reviews.jsonl"
    review_file.write_text(canonical_json(review.model_dump()) + "\n")
    instructions = tmp_path / "candidate-versions.json"
    instructions.write_text(canonical_json([{"base_sample_id": sample.sample_id, "new_sample_id": "candidate@v1",
        "reviewer_id": review.reviewer_id}]))
    candidate_dir = tmp_path / "candidate"
    main(["review-candidates", "--dataset", str(draft), "--reviews", str(review_file), "--finalizations", str(instructions), "--output", str(candidate_dir)])
    candidates, _, _, _ = load_dataset(candidate_dir)
    candidate = next(s for s in candidates if s.sample_id == "candidate@v1")
    assert candidate.acceptable_action_ids is None
    human_records = [human_review(candidate, reviewer="test-only-human-A"), human_review(candidate, reviewer="test-only-human-B")]
    final_reviews = tmp_path / "final-reviews.jsonl"
    final_reviews.write_text("".join(canonical_json(r.model_dump()) + "\n" for r in human_records))
    finalizations = tmp_path / "finalizations.json"
    finalizations.write_text(canonical_json([{"base_sample_id": candidate.sample_id, "new_sample_id": "gold@v2", "final": human_records[0].model_dump()}]))
    final_dir, release_dir = tmp_path / "final", tmp_path / "release"
    main(["finalize", "--dataset", str(candidate_dir), "--reviews", str(final_reviews), "--finalizations", str(finalizations), "--output", str(final_dir)])
    main(["release", "--dataset", str(final_dir), "--include", "gold@v2", "--output", str(release_dir)])
    released, _, _, _ = load_dataset(release_dir)
    assert [s.sample_id for s in released] == ["gold@v2"]
    split = strict_loads((release_dir / "split.json").read_text())
    assert split["locked"]
    tracks = strict_loads((release_dir / "release-tracks.json").read_text())
    assert tracks["selection"] == ["gold@v2"] and tracks["diagnostics"] == []
    main(["report", "--dataset", str(release_dir), "--output", str(tmp_path / "report")])
    report = strict_loads((tmp_path / "report/report.json").read_text())
    assert report["data_quality"]["locked_selection"] == 1
    assert report["adjudication"]["review_statistics"]["double_blind_samples"] == 1


def test_snapshot_binding_matches_canonical_runtime_models():
    from backend.services.agent_runtime.exercise_tool import SearchExercisesInput
    from backend.services.agent_runtime.progress_tool import RecentProgressInput
    from backend.services.agent_runtime.textbook_tool import TextbookSearchInput
    registry = offline_registry(recipe())
    for tool, model, args in (
        ("get_recent_progress", RecentProgressInput, {"book_name": "synthetic-book", "subject": "数学", "days": 7, "limit": 12}),
        ("search_exercises", SearchExercisesInput, {"book_name": "synthetic-book", "subject": "数学", "query": "查询习题", "limit": 8}),
        ("search_textbook", TextbookSearchInput, {"query": "检索定义", "chapter": ""}),
    ):
        assert registry.runtime_tool(tool).runtime_input.model_validate(args).model_dump() == model.model_validate(args).model_dump()


def test_sensitive_provider_response_metadata_is_not_persisted(tmp_path):
    _, _, _, _, _, _, plan, inputs = prepared()
    class PrivateMetadata(FakeTransport):
        def __call__(self, **kwargs):
            return TeacherResponseV0(raw_output='{"action_id":"a0"}', returned_model="Bearer provider-private-key")
    predictions, _ = run_batch(plan, inputs, {"sol": PrivateMetadata(), "luna": FakeTransport()},
        authorization(plan), tmp_path / "run", run_id="private-response-test")
    assert next(p for p in predictions if p.selector == "sol").status == "selector_exception"
    assert "provider-private-key" not in (tmp_path / "run/responses.jsonl").read_text()
