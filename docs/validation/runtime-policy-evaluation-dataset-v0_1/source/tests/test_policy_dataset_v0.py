import copy
import hashlib
import json
import socket
from pathlib import Path

import pytest

from backend.services.decision.policy import RulePolicyV0
from backend.services.decision.policy_contracts import PolicyObservationV0, canonical_json
from evaluation.policy_dataset_v0.contracts import EvaluationSampleV0, DatasetManifestV0
from evaluation.policy_dataset_v0.serialization import (
    read_samples, serialize_sample, deserialize_sample, policy_input, serialize_policy_input,
    observation_hash, permute_sample, action_hash, write_samples,
)
from evaluation.policy_dataset_v0.labels import label_hash, AdjudicationRecordV0, record_adjudication
from evaluation.policy_dataset_v0.validation import validate_sample
from evaluation.policy_dataset_v0.splits import (
    assign_splits, leakage_checks, lock_manifest, write_manifest, sample_fingerprint,
)
from evaluation.policy_dataset_v0.evaluator import evaluate, evaluate_views, original_action_id
from evaluation.policy_dataset_v0.teacher_adapter import DisabledTeacherV0
from evaluation.policy_dataset_v0.report import generate_report, rate, ExecutionRecordV0
from evaluation.policy_dataset_v0.__main__ import main

ROOT = Path(__file__).resolve().parents[1] / "evaluation/fixtures/policy_dataset_v0_1"


@pytest.fixture
def dataset():
    samples = read_samples(ROOT / "samples.jsonl")
    manifest = DatasetManifestV0.model_validate_json((ROOT / "manifest.json").read_text())
    records = [AdjudicationRecordV0.model_validate_json(line) for line in (ROOT / "adjudications.jsonl").read_text().splitlines()]
    evidence = {ref: (ROOT / relative).read_bytes() for ref, relative in json.loads((ROOT / "evidence-files.json").read_text()).items()}
    return {s.sample_id.split("@")[0]: s for s in samples}, manifest, records, evidence


def quality(sample, dataset, **kwargs):
    _, manifest, records, evidence = dataset
    return validate_sample(sample, manifest=manifest, records=records, evidence=evidence, **kwargs)


def changed(sample, **fields):
    value = sample.model_dump()
    value.update(fields)
    value["observation_hash"] = observation_hash(value["observation"])
    return EvaluationSampleV0.model_validate(value)


def assert_reason(q, reason):
    assert reason in q.machine_errors + q.frozen_errors + q.unverified
    assert not q.selection_eligible


def test_roundtrip_hash_null_and_empty(dataset):
    samples, _, _, _ = dataset
    for sample in samples.values():
        loaded = deserialize_sample(serialize_sample(sample))
        assert loaded == sample and loaded.observation_hash == sample.observation_hash
    assert deserialize_sample(serialize_sample(samples["pending"])).acceptable_action_ids is None
    assert deserialize_sample(serialize_sample(samples["textbook-empty"])).acceptable_action_ids == []
    value = samples["multi"].observation.model_dump()
    value["context"]["resolved_query"] += "变化"
    assert observation_hash(value) != samples["multi"].observation_hash


@pytest.mark.parametrize("damage", ["extra", "hash", "duplicate", "observation", "duplicate_json", "nonfinite"])
def test_serializer_rejects_corruption(dataset, damage):
    value = dataset[0]["multi"].model_dump()
    if damage == "extra":
        value["split"] = "test"
    elif damage == "hash":
        value["observation_hash"] = "0" * 64
    elif damage == "duplicate":
        value["observation"]["admissible_actions"][1]["id"] = "a0"
    elif damage == "observation":
        value["observation"]["envelope"] = {}
    if damage == "duplicate_json":
        raw = '{"sample_id":"a","sample_id":"b"}'
    elif damage == "nonfinite":
        raw = '{"sample_id":NaN}'
    else:
        raw = json.dumps(value)
    with pytest.raises((ValueError, TypeError)):
        deserialize_sample(raw)


def test_metadata_sentinels_and_nested_detachment(dataset):
    sample = dataset[0]["multi"]
    value = sample.model_dump()
    value.update(sample_id="SENTINEL_ID", scenario_tags=["SENTINEL_SCENARIO"], hard_tags=["SENTINEL_HARD"],
        adjudication_reason="SENTINEL_REASON", evidence_refs=["SENTINEL_REF"])
    value["source"]["ref"] = "SENTINEL_PATH"
    value["label_source"][0]["ref"] = "SENTINEL_LABEL"
    altered = EvaluationSampleV0.model_validate(value)
    assert serialize_policy_input(altered) == serialize_policy_input(sample)
    assert "SENTINEL" not in serialize_policy_input(altered)
    detached = policy_input(altered)
    detached.context.constraints["book_name"] = "changed"
    detached.admissible_actions[0].args.input["book_name"] = "changed"
    detached.admissible_actions.clear()
    assert altered.observation == sample.observation


@pytest.mark.parametrize("field", ["gold", "split", "scenario_tags", "acceptable_action_ids", "run_id"])
def test_metadata_cannot_be_smuggled_into_open_constraints(dataset, field):
    sample = dataset[0]["multi"]
    obs = sample.observation.model_dump()
    obs["context"]["constraints"]["nested"] = {field: "SENTINEL"}
    bad = changed(sample, observation=obs)
    assert_reason(validate_sample(bad), "policy_input_metadata")
    called = []
    assert evaluate(bad, selector=lambda _: called.append(True)).status == "invalid_sample"
    assert not called


@pytest.mark.parametrize("case,field,reason", [
    ("multi", "acceptable_action_ids", "acceptable_ids"),
    ("multi", "preferred_action_id", "preferred_id"),
    ("multi", "action_judgments", "judgment_coverage"),
])
def test_label_reference_consistency(dataset, case, field, reason):
    bad_values = {"acceptable_action_ids": ["old-id"], "preferred_action_id": "a2", "action_judgments": []}
    assert_reason(quality(changed(dataset[0][case], **{field: bad_values[field]}), dataset), reason)


def test_judgments_and_ambiguity_consistency(dataset):
    sample = dataset[0]["multi"]
    judgments = [j.model_dump() for j in sample.action_judgments]
    judgments[0]["judgment"] = "unacceptable"
    assert_reason(quality(changed(sample, action_judgments=judgments), dataset), "judgment_consistency")
    assert_reason(quality(changed(sample, ambiguity_status="single_correct"), dataset), "single_correct_cardinality")
    assert_reason(quality(changed(dataset[0]["pending"], acceptable_action_ids=[]), dataset), "insufficient_information_gold")


def test_boolean_validity_is_not_a_quality_gate(dataset):
    sample = dataset[0]["multi"]
    assert_reason(validate_sample(sample), "frozen_candidate_basis")
    assert_reason(validate_sample(sample), "semantic_adjudication")
    _, manifest, records, evidence = dataset
    empty_reviews = manifest.model_copy(deep=True)
    empty_reviews.reviews.clear()
    q = validate_sample(sample, manifest=empty_reviews, records=records, evidence=evidence)
    assert_reason(q, "frozen_candidate_basis")


@pytest.mark.parametrize("mutation", ["scope", "schema", "evidence", "query", "label"])
def test_frozen_basis_is_checked(dataset, mutation):
    sample = dataset[0]["progress-needed"]
    _, manifest, records, evidence = dataset
    manifest = manifest.model_copy(deep=True)
    evidence = dict(evidence)
    if mutation == "scope":
        manifest.reviews[sample.sample_id].scope["book_name"] = "wrong"
        expected = "scope_binding"
    elif mutation == "schema":
        manifest.reviews[sample.sample_id].tool_metadata["get_recent_progress"]["schema_hash"] = "wrong"
        expected = "registry_version_or_schema"
    elif mutation == "evidence":
        evidence["fixture-basis/v0"] = b"changed"
        expected = "unavailable_or_changed_evidence"
    elif mutation == "query":
        sample = dataset[0]["resolved"]
        obs = sample.observation.model_dump()
        obs["admissible_actions"][0]["args"]["input"]["query"] = "wrong binding"
        sample = changed(sample, observation=obs)
        review = manifest.reviews[sample.sample_id]
        review.observation_hash = sample.observation_hash
        review.expected_action_hashes = [action_hash(a) for a in sample.observation.admissible_actions]
        expected = "invalid_bound_args"
    else:
        sample = changed(sample, adjudication_reason="Changed label basis")
        expected = "semantic_adjudication"
    assert_reason(validate_sample(sample, manifest=manifest, records=records, evidence=evidence), expected)


def test_diagnostic_tracks_and_lock_semantics(dataset):
    samples = dataset[0]
    for name in ("scope-defect", "missing-defect", "textbook-empty", "unknown-forbidden"):
        q = quality(samples[name], dataset)
        assert q.diagnostic_eligible and not q.selection_eligible
    assert samples["textbook-empty"].candidate_generation_valid is True
    assert samples["missing-defect"].candidate_generation_valid is False
    for name in ("pending", "insufficient"):
        assert not quality(samples[name], dataset).selection_eligible
    assert_reason(quality(samples["progress-needed"], dataset, locked=True), "semantic_adjudication")
    invalid = json.loads((ROOT / "invalid-sample.json").read_text())
    assert validate_sample(invalid).machine_errors == ["invalid_schema_or_hash"]


@pytest.mark.parametrize("mode", ["main", "position_only", "position_and_id"])
def test_permutation_reversibility_and_gold_independence(dataset, mode):
    sample = dataset[0]["multi"]
    transformed, record = permute_sample(sample, seed="test", mode=mode)
    repeated, repeated_record = permute_sample(sample, seed="test", mode=mode)
    assert (transformed, record) == (repeated, repeated_record)
    assert sorted(action_hash(a) for a in transformed.observation.admissible_actions) == sorted(action_hash(a) for a in sample.observation.admissible_actions)
    assert len(set(record.action_mapping.values())) == len(record.action_mapping) == 3
    assert transformed.acceptable_action_ids == [record.action_mapping[a] for a in sample.acceptable_action_ids]
    assert {j.action_id for j in transformed.action_judgments} == set(record.action_mapping.values())
    altered = changed(sample, acceptable_action_ids=["a2"], preferred_action_id="a2", hard_tags=["new"])
    other, other_record = permute_sample(altered, seed="test", mode=mode)
    assert other.observation == transformed.observation and record == other_record
    assert sample.observation_hash == record.original_observation_hash
    if mode == "position_only":
        assert record.action_mapping == {"a0": "a0", "a1": "a1", "a2": "a2"}
    else:
        assert [a.id for a in transformed.observation.admissible_actions] == ["a0", "a1", "a2"]


def test_split_determinism_incremental_lock_and_tuning(dataset, tmp_path):
    samples = list(dataset[0].values())
    manifest = assign_splits(samples)
    assert manifest == assign_splits(list(reversed(samples)))
    extra = changed(samples[0], sample_id="new@v0")
    extra.source.source_family_id = "new-family"
    extra.source.ref = "new-ref"
    extra.source.related_refs = []
    incremented = assign_splits([extra, *samples], previous=manifest.model_copy(update={"locked": True}))
    assert all(incremented.assignments[f] == split for f, split in manifest.assignments.items())
    assert not incremented.locked
    write_manifest(tmp_path / "manifest.json", manifest.model_copy(update={"locked": True}))
    with pytest.raises(FileExistsError):
        write_manifest(tmp_path / "manifest.json", manifest)
    altered = changed(samples[0], adjudication_reason="changed")
    with pytest.raises(ValueError, match="frozen sample changed"):
        assign_splits([altered, *samples[1:]], previous=manifest)
    extra.source.used_for_tuning = True
    assert assign_splits([extra]).assignments["new-family"] == "development"
    with pytest.raises(ValueError, match="tuned family"):
        assign_splits([extra], overrides={"new-family": "locked_test"})


def test_family_controls_counterfactual_and_known_relationships(dataset):
    sample = dataset[0]["multi"]
    transformed, _ = permute_sample(sample)
    transformed = changed(transformed, sample_id="permutation@v0")
    sibling = changed(sample, sample_id="counterfactual@v0")
    sibling.source.source_family_id = "other-name"
    sibling.source.related_refs = list(sample.source.related_refs)
    manifest = assign_splits([sample, transformed, sibling])
    assert len(set(manifest.assignments.values())) == 1
    with pytest.raises(ValueError, match="related family split conflict"):
        assign_splits([sample, sibling], overrides={"multi": "development", "other-name": "locked_test"})
    manifest.assignments["other-name"] = "locked_test" if manifest.assignments["multi"] != "locked_test" else "development"
    assert any(b["code"] == "related_family_leakage" for b in leakage_checks([sample, sibling], manifest)["blockers"])


def test_exact_and_near_duplicates_block_lock(dataset):
    left = dataset[0]["progress-needed"]
    right = changed(left, sample_id="duplicate@v0")
    right.source.source_family_id = "other"
    right.source.ref = "other/ref"
    right.source.related_refs = []
    manifest = assign_splits([left, right], overrides={"progress": "development", "other": "locked_test"})
    assert leakage_checks([left, right], manifest)["blockers"][0]["code"] == "cross_split_exact_duplicate"
    obs = right.observation.model_dump()
    obs["request"] += "，谢谢"
    obs["context"]["resolved_query"] += "，谢谢"
    right = changed(right, observation=obs)
    manifest = assign_splits([left, right], overrides={"progress": "development", "other": "locked_test"})
    assert leakage_checks([left, right], manifest)["pending"]
    with pytest.raises(ValueError, match="unresolved split leakage"):
        lock_manifest([left, right], manifest, {})


def test_lock_requires_approved_review_and_separate_adjudication(dataset):
    sample = dataset[0]["progress-needed"]
    splits = assign_splits([sample])
    with pytest.raises(ValueError, match="quality gate"):
        lock_manifest([sample], splits, {sample.sample_id: quality(sample, dataset)})
    _, manifest, _, evidence = dataset
    manifest = manifest.model_copy(deep=True)
    sample = sample.model_copy(deep=True)
    # Test-only approved deterministic rule; not installed in fixture manifests.
    source = sample.label_source[0].model_copy(update={"kind": "approved_rule", "ref": "test-rule"})
    manifest.approved_rules[source.ref] = source.version
    manifest.reviews[sample.sample_id].reviewer = source
    sample.label_source = [source]
    records = [record_adjudication(sample, source, confirmed=True)]
    q = validate_sample(sample, manifest=manifest, records=records, evidence=evidence, locked=True)
    assert q.selection_eligible
    assert lock_manifest([sample], assign_splits([sample]), {sample.sample_id: q}).locked


@pytest.mark.parametrize("name,expected", [("direct", "forced"), ("input-gate", "forced"), ("textbook-empty", "runtime_only"), ("missing-defect", "runtime_only")])
def test_zero_single_call_no_selector(dataset, name, expected):
    called = []
    p = evaluate(dataset[0][name], selector=lambda _: called.append(True))
    assert p.status == expected and not called


@pytest.mark.parametrize("raw,status", [('{"action_id":"a0","reason":"x"}', "invalid_format"),
                                       ('{"action_id":"old"}', "unknown_action_id"),
                                       ('prefix', "invalid_format")])
def test_original_bad_output_kept(dataset, raw, status):
    sample = dataset[0]["multi"]
    before = serialize_sample(sample)
    p = evaluate(sample, selector=lambda _: raw)
    assert p.status == status and p.raw_output == raw
    assert serialize_sample(sample) == before


@pytest.mark.parametrize("exception,status", [(RuntimeError("private text"), "selector_exception"), (TimeoutError(), "timeout")])
def test_exception_types_are_preserved_without_private_message(dataset, exception, status):
    def fail(_):
        raise exception
    p = evaluate(dataset[0]["multi"], selector=fail)
    assert p.status == status and p.exception_type == type(exception).__name__
    assert "private text" not in canonical_json(p.model_dump())


def test_membership_uses_frozen_ids_even_if_selector_mutates_input(dataset):
    sample = dataset[0]["multi"]
    original = serialize_sample(sample)
    def selector(observation):
        observation.admissible_actions.clear()
        observation.context.constraints["book_name"] = "altered"
        return '{"action_id":"a0"}'
    p = evaluate(sample, selector=selector, view="original")
    assert p.status == "accepted" and serialize_sample(sample) == original
    assert label_hash(sample) == label_hash(deserialize_sample(original))


class FakeTeacher:
    enabled = True
    test_only = True
    def __init__(self, result=None):
        self.inputs = []
        self.result = result
    def __call__(self, observation):
        self.inputs.append(observation.canonical_json())
        return self.result if self.result is not None else RulePolicyV0(observation)


def test_teacher_is_disabled_with_credentials_and_network_blocked(dataset, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-not-a-real-key")
    monkeypatch.setenv("QWEN_API_KEY", "test")
    def forbidden(*args, **kwargs):
        raise AssertionError("network or credential access")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr("os.getenv", forbidden)
    assert DisabledTeacherV0()(policy_input(dataset[0]["multi"])).status == "disabled/not_run"
    p = evaluate(dataset[0]["multi"], selector=DisabledTeacherV0(), selector_name="teacher")
    assert p.status == "disabled/not_run"


def test_rule_and_fake_receive_same_canonical_observation(dataset):
    sample = dataset[0]["multi"]
    captures = []
    def rule(observation):
        captures.append(observation.canonical_json())
        return RulePolicyV0(observation)
    fake = FakeTeacher()
    left = evaluate(sample, selector=rule)
    right = evaluate(sample, selector=fake, selector_name="fake_teacher")
    assert left.action_id == right.action_id
    assert captures == fake.inputs
    assert all(key not in fake.inputs[0] for key in ("acceptable_action_ids", "label_source", "sample_id", "split"))


def build_report(dataset, **kwargs):
    samples = list(dataset[0].values())
    qualities = {s.sample_id: quality(s, dataset) for s in samples}
    results = evaluate_views(samples, control_families=("multi", "lexical", "optional"), **kwargs)
    report = generate_report(samples, results, qualities, assign_splits(samples))
    return report, samples, results, qualities


def test_hand_calculated_report_denominators(dataset):
    report, _, _, _ = build_report(dataset)
    selection = report["policy_selection"]
    assert selection["acceptable_accuracy"] == rate(4, 6)
    assert selection["single_correct_accuracy"] == rate(2, 4)
    assert selection["unnecessary_tool_call_rate"] == rate(2, 6)
    assert selection["invalid_rate"] == rate(0, 6)
    assert selection["missing_input_precision"] == rate(0, 0)
    assert selection["missing_input_recall"] == rate(0, 0)
    assert report["forced_runtime_only"]["forced_correct"] == rate(6, 6)
    assert report["forced_runtime_only"]["runtime_only_confirmed"] == 2
    assert report["candidate_generation"]["natural"]["failure_rate"] == rate(0, 16)
    assert report["candidate_generation"]["fault_injection"]["failure_rate"] == rate(2, 2)
    assert report["teacher_comparison"]["status"] == "disabled/not_run"
    assert report["teacher_comparison"]["accuracy"]["acceptable_accuracy"] == rate(0, 0)
    assert report["end_to_end"]["status"] == "not_evaluated"
    assert report["end_to_end"]["task_acceptance"] == rate(0, 0)
    assert report["data_quality"]["pending_adjudication"] == 2
    assert report["data_quality"]["fixture_labels_pending_human_or_approved_rule"] == 16
    assert report["data_quality"]["leakage"] == {"blockers": [], "pending": []}
    assert "/Users/" not in canonical_json(report)


def test_multi_acceptable_permutation_does_not_make_harmful_disagreement(dataset):
    sample = dataset[0]["multi"]
    fake = FakeTeacher()
    # Always choose another acceptable original identity. Gold stays outside fake.
    fake.result = '{"action_id":"a1"}'
    transformed, transform = permute_sample(sample)
    fake.result = canonical_json({"action_id": transform.action_mapping["a1"]})
    results = evaluate_views([sample], control_families=("multi",), teacher=fake)
    report = generate_report([sample], results, {sample.sample_id: quality(sample, dataset)}, assign_splits([sample]))
    assert report["policy_selection"]["acceptable_accuracy"] == rate(1, 1)
    assert report["teacher_comparison"]["accuracy"]["acceptable_accuracy"] == rate(1, 1)
    assert report["teacher_comparison"]["harmful_disagreement"]["numerator"] == 0


@pytest.mark.parametrize("raw", ['bad output', '{"action_id":"unknown"}'])
def test_fake_invalid_counts_and_not_repaired(dataset, raw):
    report, _, results, _ = build_report(dataset, teacher=FakeTeacher(raw))
    assert report["teacher_comparison"]["status"] == "test_only"
    assert report["teacher_comparison"]["accuracy"]["acceptable_accuracy"] == rate(0, 6)
    assert report["teacher_comparison"]["accuracy"]["invalid_rate"] == rate(6, 6)
    assert report["teacher_comparison"]["disagreement"] == rate(0, 0)
    assert all(p.raw_output == raw for p in results if p.selector == "fake_teacher" and p.status in {"invalid_format", "unknown_action_id"})


def test_aggregation_rejects_duplicate_missing_and_forged_predictions(dataset):
    _, samples, results, qualities = build_report(dataset)
    splits = assign_splits(samples)
    with pytest.raises(ValueError, match="duplicate original prediction"):
        generate_report(samples, [*results, results[0]], qualities, splits)
    with pytest.raises(ValueError, match="cannot shrink denominator"):
        generate_report(samples, results[2:], qualities, splits)
    p = next(p for p in results if p.transform and len(p.transform.action_mapping) > 1)
    forged = p.model_copy(deep=True)
    forged.transform.action_mapping["a0"] = "wrong"
    replacements = [forged if item is p else item for item in results]
    with pytest.raises(ValueError, match="invalid transformation mapping"):
        generate_report(samples, replacements, qualities, splits)


def test_e2e_original_failure_fallback_and_task_success_are_separate(dataset):
    _, samples, results, qualities = build_report(dataset)
    record = ExecutionRecordV0(task_ref="stub-task@v0", scope="offline_stub", executed=True,
        acceptance_basis_ref="test-standard@v0", acceptance_passed=True, original_rejected=1,
        fallback_attempted=1, fallback_accepted=1, fallback_executed=1, tool_succeeded=1,
        tool_attempted=1, answer_verification="unverified")
    report = generate_report(samples, results, qualities, assign_splits(samples), executions=[record])
    e2e = report["end_to_end"]
    assert e2e["original_rejected"] == e2e["fallback_executed"] == 1
    assert e2e["task_acceptance"] == rate(1, 1)
    assert e2e["scope_counts"] == {"offline_stub": 1}
    assert e2e["answer_verification"] == {"unverified": 1}
    bad = evaluate(dataset[0]["progress-needed"], selector=lambda _: "bad output")
    replaced = [bad if p.selector == "rule" and p.view == "main" and p.sample_id == bad.sample_id else p for p in results]
    failed_report = generate_report(samples, replaced, qualities, assign_splits(samples), executions=[record])
    assert failed_report["policy_selection"]["invalid_rate"] == rate(1, 6)
    assert failed_report["policy_selection"]["acceptable_accuracy"] == rate(3, 6)
    assert failed_report["end_to_end"]["task_acceptance"] == rate(1, 1)
    with pytest.raises(ValueError, match="duplicate task"):
        generate_report(samples, results, qualities, assign_splits(samples), executions=[record, record])


def test_nullable_candidate_review_and_declared_invalid_source(dataset):
    unknown = changed(dataset[0]["pending"], candidate_generation_valid=None)
    assert unknown.candidate_generation_valid is None
    assert not quality(unknown, dataset).candidate_reviewed
    sample = dataset[0]["multi"].model_copy(deep=True)
    sample.source.projection_version = "unknown-version"
    assert_reason(quality(sample, dataset), "projection_version_mismatch")


def test_locked_report_refuses_draft_quality(dataset):
    _, samples, results, qualities = build_report(dataset)
    splits = assign_splits(samples).model_copy(update={"locked": True})
    with pytest.raises(ValueError, match="locked report quality"):
        generate_report(samples, results, qualities, splits)


def test_preferred_and_error_refs_follow_permutation(dataset):
    sample = changed(dataset[0]["multi"], preferred_action_id="a1")
    transformed, record = permute_sample(sample, mode="position_and_id")
    assert transformed.preferred_action_id == record.action_mapping["a1"]
    fault = dataset[0]["scope-defect"]
    transformed, record = permute_sample(fault, mode="position_and_id")
    assert transformed.candidate_generation_errors[0].action_ids == [record.action_mapping["a0"]]


@pytest.mark.parametrize("operation", ["validate", "split", "evaluate", "report"])
def test_cli_confined_output_no_network_and_reproducible(dataset, tmp_path, monkeypatch, operation):
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.iterdir() if p.is_file()}
    def forbidden(*args, **kwargs):
        raise AssertionError("network")
    monkeypatch.setattr(socket, "socket", forbidden)
    first, second = tmp_path / "first", tmp_path / "second"
    assert main([operation, "--dataset", str(ROOT), "--output", str(first), "--control-family", "multi"]) == 0
    assert main([operation, "--dataset", str(ROOT), "--output", str(second), "--control-family", "multi"]) == 0
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {p.name: p.read_bytes() for p in second.iterdir()}
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.iterdir() if p.is_file()}
    with pytest.raises(FileExistsError):
        main([operation, "--dataset", str(ROOT), "--output", str(first)])


def test_cli_lock_rejects_fixture_authority_and_path_escape(dataset, tmp_path):
    with pytest.raises(ValueError, match="quality gate"):
        main(["report", "--dataset", str(ROOT), "--output", str(tmp_path / "locked"), "--lock"])
    assert not (tmp_path / "locked").exists()
    import shutil
    copied = tmp_path / "input"
    shutil.copytree(ROOT, copied)
    (copied / "evidence-files.json").write_text('{"fixture-basis/v0":"../outside.txt"}')
    with pytest.raises(ValueError, match="outside dataset"):
        main(["validate", "--dataset", str(copied), "--output", str(tmp_path / "bad")])


def test_cold_cli_does_not_import_config_read_keys_or_connect(tmp_path):
    import os
    import subprocess
    import sys
    script = '''
import os, socket, sqlite3, sys
original = os._Environ.__getitem__
def guarded(self, key):
    if "API_KEY" in str(key) or "API_SECRET" in str(key):
        raise AssertionError("credential read")
    return original(self, key)
os._Environ.__getitem__ = guarded
def forbidden(*a, **kw):
    raise AssertionError("external IO")
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.create_connection = forbidden
sqlite3.connect = forbidden
from evaluation.policy_dataset_v0.__main__ import main
main(["report", "--output", sys.argv[1]])
assert "config" not in sys.modules
assert not any(name == "llm" or name.startswith("llm.") for name in sys.modules)
assert "backend.tools.learning_tools" not in sys.modules
'''
    env = dict(os.environ, OPENAI_API_KEY="fixture-present", QWEN_API_KEY="fixture-present")
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "cold")],
        cwd=ROOT.parents[2], env=env, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("tool", ["get_recent_progress", "search_exercises", "search_textbook"])
def test_frozen_schema_matches_existing_canonical_models(tool):
    from evaluation.policy_dataset_v0.validation import canonical_tool_metadata, _canonical_tool
    if tool == "get_recent_progress":
        from backend.services.agent_runtime.progress_tool import RecentProgressInput as In, RecentProgressOutput as Out
    elif tool == "search_exercises":
        from backend.services.agent_runtime.exercise_tool import SearchExercisesInput as In, SearchExercisesOutput as Out
    else:
        from backend.services.agent_runtime.textbook_tool import TextbookSearchInput as In, TextbookSearchOutput as Out
    snapshot = _canonical_tool(tool)
    assert snapshot["input_schema"] == In.model_json_schema()
    assert snapshot["output_schema"] == Out.model_json_schema()
    assert canonical_tool_metadata(tool)["schema_hash"] == hashlib.sha256(json.dumps(
        [In.model_json_schema(), Out.model_json_schema()], sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize("mutation", [{"days": True}, {"days": 0}, {"limit": 51}, {"extra": "x"}, {"book_name": None}])
def test_fixed_canonical_input_validation_fails_closed(dataset, mutation):
    from evaluation.policy_dataset_v0.validation import validate_bound_args
    args = dataset[0]["progress-needed"].observation.admissible_actions[0].args.input
    with pytest.raises(ValueError):
        validate_bound_args("get_recent_progress", {**args, **mutation})


@pytest.mark.parametrize("field,value,code", [
    ("runtime_version", "", "manifest_runtime_version_invalid"),
    ("runtime_version", "bogus", "manifest_runtime_version_invalid"),
    ("runtime_version", "sha256:" + "1" * 64, "manifest_runtime_version_mismatch"),
    ("registry_version", "bogus", "manifest_registry_version_invalid"),
    ("registry_version", "sha256:" + "1" * 64, "manifest_registry_version_mismatch"),
    ("label_policy_version", "bogus", "manifest_label_policy_version_invalid"),
    ("source_digest", "not-a-sha256", "manifest_source_digests_invalid"),
    ("source_digest", "0" * 64, "manifest_source_digest_zero"),
    ("source_digest", "1" * 64, "manifest_source_digest_mismatch"),
    ("source_digests", {}, "manifest_source_digest_set_mismatch"),
])
@pytest.mark.parametrize("representation", ["raw_dict", "mutated_model"])
def test_manifest_version_and_digest_corruption_never_selection_eligible(dataset, field, value, code, representation):
    from evaluation.policy_dataset_v0.validation import validate_manifest
    sample = dataset[0]["progress-needed"]
    before = serialize_sample(sample)
    manifest = dataset[1].model_dump()
    if field == "source_digest":
        manifest["source_digests"]["backend/services/decision/policy.py"] = value
    else:
        manifest[field] = value
    if representation == "mutated_model":
        update_key = "source_digests" if field == "source_digest" else field
        manifest = dataset[1].model_copy(update={update_key: manifest[update_key]}, deep=True)
    _, errors = validate_manifest(manifest)
    assert code in errors
    q = validate_sample(sample, manifest=manifest, records=dataset[2], evidence=dataset[3])
    assert code in q.frozen_errors
    assert not q.selection_eligible and not q.diagnostic_eligible and not q.candidate_reviewed
    assert serialize_sample(sample) == before


@pytest.mark.parametrize("field", ["runtime_version", "registry_version", "label_policy_version", "source_digests"])
def test_missing_manifest_version_fields_fail_closed(dataset, field):
    manifest = dataset[1].model_dump()
    del manifest[field]
    q = validate_sample(dataset[0]["progress-needed"], manifest=manifest, records=dataset[2], evidence=dataset[3])
    assert_reason(q, f"manifest_{field}_missing")


def test_actual_source_bytes_are_checked_without_editing_production(dataset, monkeypatch):
    original = Path.read_bytes
    def changed_source(path):
        raw = original(path)
        return raw + b"changed" if str(path).endswith("backend/services/decision/policy.py") else raw
    monkeypatch.setattr(Path, "read_bytes", changed_source)
    assert_reason(quality(dataset[0]["progress-needed"], dataset), "source_content_digest_mismatch")


def test_unavailable_approved_digest_basis_fails_closed(dataset, monkeypatch):
    original = Path.read_text
    def unavailable(path, *args, **kwargs):
        if path.name == "source-manifest.json":
            raise FileNotFoundError("test basis unavailable")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", unavailable)
    assert_reason(quality(dataset[0]["progress-needed"], dataset), "approved_source_digests_unavailable")


def test_cli_rejects_corrupt_manifest_before_any_output(dataset, tmp_path):
    import shutil
    copied = tmp_path / "input"
    shutil.copytree(ROOT, copied)
    manifest = dataset[1].model_dump()
    manifest["registry_version"] = "bogus"
    (copied / "manifest.json").write_text(canonical_json(manifest))
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="manifest_registry_version_invalid"):
        main(["report", "--dataset", str(copied), "--output", str(output)])
    assert not output.exists()


def injected_input(sample, location):
    obs = sample.observation.model_dump()
    payload = {"gold": {"acceptable_action_ids": ["a0"], "preferred_action_id": "a0"}}
    if location == "constraints_ambiguity":
        obs["context"]["constraints"]["ambiguity_status"] = "single_correct"
    elif location == "nested_gold":
        obs["context"]["constraints"]["domain"] = {"details": payload}
    elif location == "metadata_list":
        obs["context"]["constraints"]["domain"] = [{"details": {"candidate_generation_errors": ["a0"]}}]
    elif location == "encoded_object":
        obs["context"]["constraints"]["description"] = canonical_json(payload)
    elif location == "encoded_list":
        obs["context"]["constraints"]["description"] = canonical_json([{"evaluator_result": {"action_id": "a0"}}])
    elif location == "double_encoded":
        obs["context"]["constraints"]["description"] = json.dumps(json.dumps(payload))
    elif location == "embedded_json":
        obs["context"]["goal"] = "Extra context: " + canonical_json(payload)
    elif location == "missing_inputs":
        obs["missing_inputs"] = [{"name": "supplement", "details": {"label_source": ["fixture"]}}]
    elif location == "summary_json":
        obs["previous_result"] = {"action_kind": "call_tool", "tool_id": "get_recent_progress",
            "status": "succeeded", "summary": canonical_json({"prediction_result": {"action_id": "a0"}})}
    elif location == "tool_args":
        obs["admissible_actions"][0]["args"]["input"]["query"] = canonical_json(payload)
    elif location == "action_ids_object":
        obs["context"]["constraints"]["details"] = {"action_ids": ["a0", "a1"], "preferred_action_id": "a0"}
    elif location == "action_judgment":
        obs["context"]["constraints"]["details"] = {"judgment": "acceptable", "reason_tags": ["single_correct"]}
    elif location == "action_id_text":
        # Inject into the legal string ID field, with all dataset references updated.
        new_id = 'a0-gold-single_correct'
        obs["admissible_actions"][0]["id"] = new_id
        value = sample.model_dump()
        value["observation"] = obs
        value["acceptable_action_ids"] = [new_id if a == "a0" else a for a in value["acceptable_action_ids"]]
        for judgment in value["action_judgments"]:
            if judgment["action_id"] == "a0":
                judgment["action_id"] = new_id
        return changed(sample, **value)
    else:
        raise AssertionError(location)
    return changed(sample, observation=obs)


@pytest.mark.parametrize("location", ["constraints_ambiguity", "nested_gold", "metadata_list", "encoded_object",
    "encoded_list", "double_encoded", "embedded_json", "missing_inputs", "summary_json", "tool_args",
    "action_ids_object", "action_id_text", "action_judgment"])
@pytest.mark.parametrize("path", ["serializer", "evaluator", "teacher", "rule_adapter"])
def test_all_policy_paths_reject_structured_evaluation_metadata(dataset, location, path):
    from evaluation.policy_dataset_v0.serialization import PolicyInputRejected
    from evaluation.policy_dataset_v0.evaluator import rule_policy_adapter
    from evaluation.policy_dataset_v0.teacher_adapter import call_teacher
    bad = injected_input(dataset[0]["multi"], location)
    expected = "policy_input_action_id" if location == "action_id_text" else "policy_input_metadata"
    assert_reason(validate_sample(bad), expected)
    before = serialize_sample(bad)
    if path == "serializer":
        with pytest.raises(PolicyInputRejected, match=expected):
            serialize_policy_input(bad)
    elif path == "evaluator":
        fake = FakeTeacher()
        p = evaluate(bad, selector=fake, selector_name="fake_teacher")
        assert p.status == "invalid_sample" and not fake.inputs
    elif path == "teacher":
        fake = FakeTeacher()
        with pytest.raises(PolicyInputRejected, match=expected):
            call_teacher(fake, bad.observation)
        assert not fake.inputs
        with pytest.raises(PolicyInputRejected, match=expected):
            DisabledTeacherV0()(bad.observation)
    else:
        with pytest.raises(PolicyInputRejected, match=expected):
            rule_policy_adapter(bad.observation)
    assert serialize_sample(bad) == before


@pytest.mark.parametrize("text", ["Explain gold and ambiguity in ordinary language.",
    "gold、ambiguity_status 这些词是什么意思？", "请解释 acceptable_action_ids、candidate_generation_errors 字段的用途。"])
def test_normal_user_text_is_not_keyword_filtered(dataset, text):
    from evaluation.policy_dataset_v0.teacher_adapter import call_teacher
    from evaluation.policy_dataset_v0.evaluator import rule_policy_adapter
    sample = dataset[0]["multi"]
    obs = sample.observation.model_dump()
    obs["request"] = text
    obs["context"]["resolved_query"] = text
    obs["context"]["goal"] = "解释 gold 与 ambiguity 的术语，不读取额外数据"
    obs["context"]["constraints"]["description"] = "ordinary gold and ambiguity wording"
    allowed = changed(sample, observation=obs)
    wire = serialize_policy_input(allowed)
    assert json.loads(wire)["request"] == text
    assert policy_input(allowed).context.constraints["description"] == "ordinary gold and ambiguity wording"
    fake = FakeTeacher()
    call_teacher(fake, allowed.observation)
    assert fake.inputs == [wire]
    rule_policy_adapter(allowed.observation)
    assert evaluate(allowed).status == "accepted"
