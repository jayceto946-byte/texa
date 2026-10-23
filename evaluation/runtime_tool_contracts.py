"""Reviewed current-tool contracts and evaluator-only legacy input adaptation.

Never used for execution or to approve frozen datasets against today's runtime.
Only search_textbook's explicit null continuation bridges the two contracts;
actual continuation reads have no representation in the historical dataset.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

CONTRACT_VERSION = "texa.runtime-tool-contracts/v1"
MANIFEST = Path(__file__).with_name("contracts") / "runtime-tools-v1.json"
MANIFEST_SHA256 = "3e5354ecc502fe83d16cc5bfc965e02ff5d9b5ab572000d6c7f9a2e4e6f4d832"


def reviewed_contract():
    from evaluation.policy_dataset_v0.baseline import BASELINE_VERSION, APPROVED_REGISTRY_VERSION
    from evaluation.policy_dataset_v0.frozen_runtime import _verified_sources

    _verified_sources()  # Keep the historical approval authority intact.
    raw = MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("runtime_tool_contract_manifest_changed")
    manifest = json.loads(raw)
    if (manifest["contract"] != CONTRACT_VERSION
            or manifest["frozen_baseline"] != BASELINE_VERSION
            or manifest["frozen_registry_version"] != APPROVED_REGISTRY_VERSION):
        raise ValueError("runtime_tool_contract_basis_changed")
    return manifest


def verify_runtime_schema(tool_id, input_model, output_model):
    expected = reviewed_contract()["tools"][tool_id]
    if (input_model.model_json_schema() != expected["input_schema"]
            or output_model.model_json_schema() != expected["output_schema"]):
        raise ValueError("runtime_tool_schema_changed:" + tool_id)
    return expected


def verify_runtime_registry(registry):
    manifest = reviewed_contract()
    for tool_id, expected in manifest["tools"].items():
        spec = registry.runtime_tool(tool_id)
        # Includes version/hash, permissions, timeout, provenance and retry mode.
        if not spec.read_only or spec.runtime_metadata() != expected:
            raise ValueError("runtime_tool_metadata_changed:" + tool_id)
        assert_frozen_schema_compatibility(tool_id, spec.runtime_input, spec.runtime_output)
    return {"contract": CONTRACT_VERSION, "manifest_sha256": MANIFEST_SHA256,
            "frozen_baseline": manifest["frozen_baseline"],
            "frozen_registry_version": manifest["frozen_registry_version"],
            "tool_refs": [{key: meta[key] for key in ("id", "version", "schema_hash")}
                          for meta in manifest["tools"].values()]}


def assert_frozen_schema_compatibility(tool_id, input_model, output_model):
    from evaluation.policy_dataset_v0.validation import _canonical_tool, canonical_tool_metadata

    current = verify_runtime_schema(tool_id, input_model, output_model)
    legacy_input = copy.deepcopy(current["input_schema"])
    if tool_id == "search_textbook":
        # The only reviewed delta. Current $defs/continuation are independently
        # pinned above, rather than accepting arbitrary future additive fields.
        del legacy_input["properties"]["continuation"]
        del legacy_input["$defs"]
    old = _canonical_tool(tool_id)
    if (legacy_input != old["input_schema"] or current["output_schema"] != old["output_schema"]
            or any(current[key] != old[key] for key in ("permission", "source", "side_effect"))):
        raise ValueError("frozen_tool_compatibility_changed:" + tool_id)
    schemas = [legacy_input, current["output_schema"]]
    if canonical_tool_metadata(tool_id)["schema_hash"] != hashlib.sha256(
            json.dumps(schemas, sort_keys=True).encode()).hexdigest():
        raise ValueError("frozen_tool_schema_hash_changed:" + tool_id)
    return legacy_input


def upgrade_frozen_input(tool_id, args, input_model):
    """Map fully bound historical inputs to the reviewed current schema only."""
    from evaluation.policy_dataset_v0.validation import validate_bound_args

    expected = reviewed_contract()["tools"][tool_id]
    if input_model.model_json_schema() != expected["input_schema"]:
        raise ValueError("runtime_tool_schema_changed:" + tool_id)
    validate_bound_args(tool_id, args)  # Reject extra keys, including continuation.
    upgraded = copy.deepcopy(args)
    if tool_id == "search_textbook":
        upgraded["continuation"] = None
    bound = input_model.model_validate(upgraded).model_dump()
    if bound != upgraded:
        raise ValueError("runtime_tool_binding_changed:" + tool_id)
    return bound


def downgrade_runtime_input(tool_id, args, input_model):
    """Reject non-null continuations instead of silently discarding new state."""
    bound = input_model.model_validate(args).model_dump()
    legacy = copy.deepcopy(bound)
    if tool_id == "search_textbook":
        if legacy.pop("continuation") is not None:
            raise ValueError("continuation_not_representable_in_frozen_contract")
    if upgrade_frozen_input(tool_id, legacy, input_model) != bound:
        raise ValueError("runtime_tool_binding_changed:" + tool_id)
    return legacy
