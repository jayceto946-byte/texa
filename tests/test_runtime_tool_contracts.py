"""Historical approvals and current-tool checks must remain separate gates."""
import copy
from pathlib import Path

import pytest
from pydantic import ValidationError, create_model

from evaluation.runtime_policy_v0 import fixture_runtime, run_baseline
from evaluation.runtime_tool_contracts import (
    CONTRACT_VERSION, reviewed_contract, verify_runtime_registry,
    assert_frozen_schema_compatibility, upgrade_frozen_input, downgrade_runtime_input,
)


@pytest.fixture
def parts(tmp_path):
    return fixture_runtime(tmp_path, {"request": "教材中的连续定义", "book_name": "fixture", "grounded": True})


def test_current_registry_and_legacy_snapshot_have_distinct_identities(parts):
    from evaluation.policy_dataset_v0.validation import _canonical_tool, canonical_tool_metadata
    registry = parts[1]
    identity = verify_runtime_registry(registry)
    spec = registry.runtime_tool("search_textbook")
    assert identity["contract"] == CONTRACT_VERSION
    assert canonical_tool_metadata("search_textbook")["version"] == "1"
    assert spec.version == "3"
    assert canonical_tool_metadata("search_textbook")["schema_hash"] != spec.runtime_metadata()["schema_hash"]
    assert "continuation" not in _canonical_tool("search_textbook")["input_schema"]["properties"]
    assert "continuation" in spec.runtime_input.model_json_schema()["properties"]
    assert_frozen_schema_compatibility("search_textbook", spec.runtime_input, spec.runtime_output)


@pytest.mark.parametrize("field,value", [
    ("version", "1"), ("permission", "LOCAL_WRITE"), ("source", "plugin"),
    ("timeout_seconds", 9.0), ("read_only", False), ("provenance", "other"),
    ("idempotency", "other"),
])
def test_unreviewed_metadata_changes_fail_closed(parts, field, value):
    registry = parts[1]
    setattr(registry.get("search_textbook"), field, value)
    with pytest.raises(ValueError, match="runtime_tool_metadata_changed"):
        verify_runtime_registry(registry)


@pytest.mark.parametrize("which", ["input", "output"])
def test_unreviewed_schema_changes_are_not_treated_as_compatible(parts, which):
    spec = parts[1].runtime_tool("search_textbook")
    incoming, outgoing = spec.runtime_input, spec.runtime_output
    if which == "input":
        incoming = create_model("TextbookSearchInput", __base__=incoming, future_option=(str, ""))
    else:
        outgoing = create_model("TextbookSearchOutput", __base__=outgoing, future_result=(str, ""))
    with pytest.raises(ValueError, match="runtime_tool_schema_changed"):
        assert_frozen_schema_compatibility("search_textbook", incoming, outgoing)


def test_legacy_upgrade_is_explicit_and_does_not_mutate_inputs(parts):
    spec = parts[1].runtime_tool("search_textbook")
    legacy = {"query": "连续定义", "chapter": ""}
    before = copy.deepcopy(legacy)
    upgraded = upgrade_frozen_input("search_textbook", legacy, spec.runtime_input)
    assert upgraded == {**legacy, "continuation": None}
    assert legacy == before
    assert downgrade_runtime_input("search_textbook", upgraded, spec.runtime_input) == legacy
    assert "continuation" in upgraded


@pytest.mark.parametrize("mutation", [
    {"continuation": None}, {"continuation": {}}, {"book_name": "outside"},
    {"query": True}, {"chapter": None},
])
def test_legacy_adapter_rejects_new_fields_or_invalid_scalars(parts, mutation):
    spec = parts[1].runtime_tool("search_textbook")
    with pytest.raises(ValueError):
        upgrade_frozen_input("search_textbook", {"query": "连续定义", "chapter": "", **mutation}, spec.runtime_input)


def test_current_continuation_cannot_be_dropped_to_claim_frozen_compatibility(parts):
    spec = parts[1].runtime_tool("search_textbook")
    pointer = {"book_name": "fixture", "index_version": "fixture_v1", "canonical_hash": "a" * 64,
               "unit_id": "h", "block_id": "b", "anchor_chunk_id": "anchor"}
    args = {"query": "继续", "chapter": "", "continuation": pointer}
    spec.runtime_input.model_validate(args)  # Legal v3 shape, not an executable source claim.
    with pytest.raises(ValueError, match="not_representable"):
        downgrade_runtime_input("search_textbook", args, spec.runtime_input)
    with pytest.raises(ValidationError):
        spec.runtime_input.model_validate({**args, "continuation": {**pointer, "unknown": "value"}})


@pytest.mark.parametrize("target", ["current_manifest", "historical_source"])
def test_changed_approval_bytes_fail_closed(monkeypatch, target):
    from evaluation.runtime_tool_contracts import MANIFEST
    from evaluation.policy_dataset_v0.baseline import FROZEN_SOURCE_ROOT
    path = MANIFEST if target == "current_manifest" else FROZEN_SOURCE_ROOT / "backend/services/agent_runtime/textbook_tool.py"
    original = Path.read_bytes

    def changed(file):
        raw = original(file)
        return raw + b"\n" if file == path else raw

    monkeypatch.setattr(Path, "read_bytes", changed)
    with pytest.raises(ValueError, match="manifest_changed|source_content_digest_mismatch"):
        reviewed_contract()


def test_current_projection_binds_null_and_rejects_historical_tool_refs(parts):
    from backend.services.decision.policy_projection import project_observation, runtime_identity
    from evaluation.policy_dataset_v0.validation import canonical_tool_metadata
    store, registry, state, refs, context = parts
    snapshot = store.task_snapshot("rtask_fixture")
    kwargs = dict(request=state["user_input"], resolved_query=state["user_input"], registry=registry,
                  context=context, identity=runtime_identity(snapshot), snapshot=snapshot, answer_state=state)
    projected = project_observation(**kwargs, candidate_tools=refs)
    actions = projected.envelope.payload.admissible_actions
    textbook = next(a for a in actions if a.kind == "call_tool" and a.args.tool_id == "search_textbook")
    assert textbook.args.input == {"query": state["user_input"], "chapter": "", "continuation": None}
    legacy = {"id": "search_textbook", **{key: canonical_tool_metadata("search_textbook")[key] for key in ("version", "schema_hash")}}
    rejected = project_observation(**kwargs, candidate_tools=[legacy])
    assert not rejected.envelope.payload.admissible_actions
    assert any(e["reason"] == "version_or_schema_changed" for e in rejected.exclusions)


def test_current_baseline_labels_its_contract_and_has_no_binding_errors():
    report = run_baseline()
    assert report["baseline_version"] == "current-runtime-policy-tools/v1"
    assert report["runtime_tool_contract"]["contract"] == CONTRACT_VERSION
    assert report["runtime_tool_contract"]["frozen_baseline"] == "runtime-source/v0.1"
    assert report["metrics"]["candidate_generation"]["binding_checks"] > 0
    assert report["metrics"]["candidate_generation"]["binding_errors"] == 0
    assert all(item["passed"] for item in report["fixtures"])


@pytest.mark.parametrize("group,field", [
    ("candidate_generation", "binding_errors"),
    ("candidate_generation", "forbidden_leaks"),
    ("overhead", "real_model_calls"),
])
def test_baseline_cli_rejects_contract_failures_even_with_successful_tasks(tmp_path, monkeypatch, group, field):
    import evaluation.runtime_policy_v0 as baseline
    report = {"fixtures": [{"passed": True}], "metrics": {
        "candidate_generation": {"binding_errors": 0, "forbidden_leaks": 0},
        "overhead": {"real_model_calls": 0}}}
    report["metrics"][group][field] = 1
    monkeypatch.setattr(baseline, "run_baseline", lambda: report)
    monkeypatch.setattr("sys.argv", ["runtime_policy_v0", "--output", str(tmp_path / "report.json")])
    assert baseline.main() == 1
