"""V0.1 review controls: corpus continuity, new source pins and Runtime fences."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from evaluation.policy_dataset_v0.baseline import (
    APPROVED_RUNTIME_VERSION, DEFAULT_DATASET, REPO_ROOT, RUNTIME_SOURCES,
)
from evaluation.policy_dataset_v0.validation import validate_manifest

REVIEW = REPO_ROOT / "docs/validation/runtime-policy-evaluation-dataset-v0_1"


def test_active_baseline_preserves_original_gold_and_rejects_legacy_manifest():
    transition = json.loads((REVIEW / "baseline-transition.json").read_text())
    old = REPO_ROOT / "evaluation/fixtures/policy_dataset_v0"
    for name, expected in transition["retained_corpus_sha256"].items():
        assert hashlib.sha256((old / name).read_bytes()).hexdigest() == expected
        assert (DEFAULT_DATASET / name).read_bytes() == (old / name).read_bytes()
    assert hashlib.sha256((old / "manifest.json").read_bytes()).hexdigest() == transition["old_manifest_sha256"]
    old_pins = REPO_ROOT / "docs/validation/runtime-policy-evaluation-dataset-v0/source-manifest.json"
    assert hashlib.sha256(old_pins.read_bytes()).hexdigest() == transition["old_source_manifest_sha256"]
    current = json.loads((DEFAULT_DATASET / "manifest.json").read_text())
    assert current["runtime_version"] == APPROVED_RUNTIME_VERSION
    assert validate_manifest(current)[1] == []
    assert "manifest_runtime_version_mismatch" in validate_manifest(json.loads((old / "manifest.json").read_text()))[1]


@pytest.mark.parametrize("source", [
    "backend/services/decision/contracts.py", "backend/services/decision/resolver.py",
    "graph/question_understanding.py",
])
def test_new_transitive_dependencies_are_pinned_and_fail_on_drift(source, monkeypatch):
    assert source in RUNTIME_SOURCES
    original = Path.read_bytes
    def altered(path):
        raw = original(path)
        return raw + b"drift" if path == REPO_ROOT / source else raw
    monkeypatch.setattr(Path, "read_bytes", altered)
    manifest = json.loads((DEFAULT_DATASET / "manifest.json").read_text())
    assert "source_content_digest_mismatch" in validate_manifest(manifest)[1]


def test_rehashed_manifest_cannot_approve_another_source_version():
    from backend.services.decision.policy_projection import digest
    manifest = json.loads((DEFAULT_DATASET / "manifest.json").read_text())
    manifest["source_digests"]["graph/question_understanding.py"] = "1" * 64
    manifest["runtime_version"] = "sha256:" + digest({key: manifest["source_digests"][key] for key in RUNTIME_SOURCES})
    errors = validate_manifest(manifest)[1]
    assert "manifest_runtime_version_mismatch" in errors
    assert "manifest_source_digest_mismatch" in errors


def test_reviewed_source_snapshots_match_active_pins():
    manifest = json.loads((DEFAULT_DATASET / "manifest.json").read_text())
    for source, expected in manifest["source_digests"].items():
        assert hashlib.sha256((REVIEW / "source" / source).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize("mutation", [
    {"accepted": False}, {"action": "clarify"}, {"version": "unknown"},
    {"intent": "write"}, {"dimensions": ["save_mistake"]},
])
def test_unaccepted_or_invalid_hint_cannot_change_capability_candidates(mutation):
    from backend.services.decision.router import matching_capabilities
    from graph.question_understanding import VERSION
    hint = {"version": VERSION, "accepted": True, "action": "continue", "intent": "quiz", "dimensions": ["exercises"], **mutation}
    assert matching_capabilities("计算2+3", understanding=hint) == matching_capabilities("计算2+3")


@pytest.mark.parametrize("fence", ["missing_input", "tool_budget", "duplicate", "inactive"])
def test_accepted_hint_does_not_bypass_runtime_fences(tmp_path, fence):
    from evaluation.runtime_policy_v0 import fixture_runtime
    from backend.services.decision.policy_projection import matched_tool_refs, project_observation, runtime_identity
    from graph.question_understanding import VERSION
    store, registry, state, _, context = fixture_runtime(tmp_path, {
        "id": "baseline-review", "request": "捞几道题做做", "book_name": "fixture", "grounded": False,
    })
    state["question_understanding"] = {"version": VERSION, "accepted": True, "action": "continue",
        "intent": "quiz", "dimensions": ["exercises"], "entities": ["private entity"], "credential": "private marker"}
    refs, _ = matched_tool_refs(state["user_input"], registry, understanding=state["question_understanding"])
    assert [item["id"] for item in refs] == ["search_exercises"]
    snapshot = copy.deepcopy(store.task_snapshot("rtask_fixture"))
    missing = []
    if fence == "missing_input": missing = [{"name": "missing page", "blocking": True}]
    if fence == "tool_budget": snapshot["consumed_calls"] = snapshot["budget_calls"]
    if fence == "duplicate": snapshot["tool_calls"] = [{"id": "prior", "tool_id": "search_exercises", "status": "failed", "result": None, "error_code": "failed"}]
    if fence == "inactive": snapshot["run"]["status"] = "interrupted"
    frozen = project_observation(request=state["user_input"], resolved_query=state["user_input"], registry=registry,
        context=context, identity=runtime_identity(snapshot), snapshot=snapshot,
        answer_state=state, candidate_tools=refs, missing_inputs=missing)
    assert all(action.kind != "call_tool" for action in frozen.envelope.payload.admissible_actions)
    if fence in {"missing_input", "inactive"}: assert not frozen.envelope.payload.admissible_actions
    projected = frozen.envelope.payload.context.constraints["question_understanding"]
    assert set(projected) == {"version", "accepted", "action", "intent", "dimensions"}
