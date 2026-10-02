"""Machine checks, frozen-basis checks and semantic adjudication stay distinct."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from pathlib import Path
from pydantic import ValidationError
from backend.services.decision.policy_projection import digest
from .contracts import DatasetManifestV0
from .serialization import validate_sample_schema, action_hash, policy_input, PolicyInputRejected, strict_loads
from .labels import adjudicated

APPROVED_RUNTIME_VERSION = "sha256:aead87f0f65b76f4c6cfc49ff099761cf34cd7ac8fc6307d19a2b0ad6a94c3c6"
APPROVED_REGISTRY_VERSION = "sha256:468a8259856e03d4f63f8e478eebf058467dd05395fae044de2d20aa95ec7013"
_RUNTIME_SOURCES = (
    "backend/services/agent_runtime/exercise_tool.py", "backend/services/agent_runtime/progress_tool.py",
    "backend/services/agent_runtime/textbook_tool.py", "backend/services/decision/policy.py",
    "backend/services/decision/policy_contracts.py", "backend/services/decision/policy_projection.py",
    "backend/services/decision/router.py", "backend/tools/registry.py",
)
_SOURCE_PATHS = (*_RUNTIME_SOURCES, "evaluation/policy_dataset_v0/canonical-tools-v0.json")


@dataclass
class QualityV0:
    machine_errors: list[str] = field(default_factory=list)
    frozen_errors: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    selection_eligible: bool = False
    diagnostic_eligible: bool = False
    candidate_reviewed: bool = False
    semantic_adjudicated: bool = False
    locked_checked: bool = False

    def to_dict(self):
        return vars(self).copy()


def validate_manifest(value):
    """Check declared versions against the approved baseline AND actual local bytes.

    Reuse the existing source-manifest artifact; never trust sample-supplied paths
    or let a caller's recomputed version approve a changed source tree.
    """
    try:
        manifest = DatasetManifestV0.model_validate(value.model_dump() if isinstance(value, DatasetManifestV0) else value)
    except ValidationError as exc:
        errors = []
        for issue in exc.errors():
            field = issue["loc"][0] if issue["loc"] else "schema"
            suffix = "missing" if issue["type"] == "missing" else "invalid"
            errors.append(f"manifest_{field}_{suffix}")
        return None, sorted(set(errors))
    errors = []
    if manifest.runtime_version != APPROVED_RUNTIME_VERSION:
        errors.append("manifest_runtime_version_mismatch")
    if manifest.registry_version != APPROVED_REGISTRY_VERSION:
        errors.append("manifest_registry_version_mismatch")
    if set(manifest.source_digests) != set(_SOURCE_PATHS):
        errors.append("manifest_source_digest_set_mismatch")
    root = Path(__file__).resolve().parents[2]
    try:
        approved = strict_loads((root / "docs/validation/runtime-policy-evaluation-dataset-v0/source-manifest.json").read_text())
        pins = {path: approved[path] for path in _SOURCE_PATHS}
        if any(not isinstance(d, str) or re.fullmatch(r"[a-f0-9]{64}", d) is None or d == "0" * 64 for d in pins.values()):
            raise ValueError("invalid approved digest")
        if "sha256:" + digest({path: pins[path] for path in _RUNTIME_SOURCES}) != APPROVED_RUNTIME_VERSION:
            raise ValueError("approved runtime digest mismatch")
    except (OSError, ValueError, KeyError, TypeError):
        return manifest, [*errors, "approved_source_digests_unavailable"]
    for path in _SOURCE_PATHS:
        declared = manifest.source_digests.get(path)
        if declared == "0" * 64:
            errors.append("manifest_source_digest_zero")
        elif declared != pins[path]:
            errors.append("manifest_source_digest_mismatch")
        try:
            actual = hashlib.sha256((root / path).read_bytes()).hexdigest()
            if actual != pins[path]:
                errors.append("source_content_digest_mismatch")
        except OSError:
            errors.append("source_content_unavailable")
    try:
        registry = {name: canonical_tool_metadata(name) for name in ("search_textbook", "search_exercises", "get_recent_progress")}
        if "sha256:" + digest(registry) != APPROVED_REGISTRY_VERSION:
            errors.append("registry_content_digest_mismatch")
    except (OSError, ValueError, KeyError, TypeError):
        errors.append("registry_content_unavailable")
    return manifest, sorted(set(errors))


def _canonical_tool(tool_id):
    from .serialization import strict_loads
    snapshot = strict_loads(Path(__file__).with_name("canonical-tools-v0.json").read_text())
    if tool_id not in snapshot:
        raise ValueError("unsupported_v0_tool")
    return snapshot[tool_id]


def canonical_tool_metadata(tool_id):
    import json
    snapshot = _canonical_tool(tool_id)
    schemas = [snapshot["input_schema"], snapshot["output_schema"]]
    calculated = hashlib.sha256(json.dumps(schemas, sort_keys=True).encode()).hexdigest()
    if calculated != snapshot["schema_hash"]:
        raise ValueError("damaged_canonical_schema_snapshot")
    return {key: snapshot[key] for key in ("version", "schema_hash", "permission", "source", "side_effect")}


def validate_bound_args(tool_id, args):
    """Fixed V0 canonical scalar inputs only; not a general JSON Schema engine.

    Snapshot exported from existing canonical models/Registry. Importing those
    models also imports config/learning stores, which an offline entry must avoid.
    Unknown types/keywords fail closed; new schemas require a reviewed snapshot.
    """
    canonical_tool_metadata(tool_id)
    schema = _canonical_tool(tool_id)["input_schema"]
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise ValueError("unsupported_canonical_schema")
    properties = schema["properties"]
    if set(args) != set(properties):
        raise ValueError("noncanonical_bound_args")
    for name, rule in properties.items():
        if set(rule) - {"type", "title", "description", "default", "minLength", "maxLength", "minimum", "maximum"}:
            raise ValueError("unsupported_canonical_schema")
        value = args[name]
        if rule["type"] == "string":
            if type(value) is not str or not rule.get("minLength", 0) <= len(value) <= rule.get("maxLength", float("inf")):
                raise ValueError("invalid_bound_args")
        elif rule["type"] == "integer":
            if type(value) is not int or not rule.get("minimum", -float("inf")) <= value <= rule.get("maximum", float("inf")):
                raise ValueError("invalid_bound_args")
        else:
            raise ValueError("unsupported_canonical_schema")


def validate_sample(sample, *, manifest=None, records=(), evidence=None, locked=False):
    quality = QualityV0(locked_checked=locked)
    try:
        sample = validate_sample_schema(sample)
    except (ValueError, TypeError):
        quality.machine_errors.append("invalid_schema_or_hash")
        return quality
    ids = {action.id for action in sample.observation.admissible_actions}
    acceptable = sample.acceptable_action_ids
    judgments = sample.action_judgments
    if acceptable is not None and (len(acceptable) != len(set(acceptable)) or not set(acceptable) <= ids):
        quality.machine_errors.append("acceptable_ids")
    if sample.preferred_action_id is not None and sample.preferred_action_id not in (acceptable or []):
        quality.machine_errors.append("preferred_id")
    if len(judgments) != len(ids) or {j.action_id for j in judgments} != ids:
        quality.machine_errors.append("judgment_coverage")
    if acceptable is not None and {j.action_id for j in judgments if j.judgment == "acceptable"} != set(acceptable):
        quality.machine_errors.append("judgment_consistency")
    if acceptable is None and any(j.judgment == "acceptable" for j in judgments):
        quality.machine_errors.append("unknown_gold_consistency")
    if acceptable is not None and any(j.judgment == "undetermined" for j in judgments):
        quality.machine_errors.append("partially_undetermined_gold")
    for error in sample.candidate_generation_errors:
        if len(error.action_ids) != len(set(error.action_ids)) or not set(error.action_ids) <= ids:
            quality.machine_errors.append("candidate_error_reference")
    ambiguity = sample.ambiguity_status
    if ambiguity == "single_correct" and (acceptable is None or len(acceptable) != 1):
        quality.machine_errors.append("single_correct_cardinality")
    if ambiguity == "multiple_acceptable" and (acceptable is None or len(acceptable) < 2):
        quality.machine_errors.append("multiple_acceptable_cardinality")
    if ambiguity == "runtime_only" and (ids or acceptable != [] or sample.candidate_generation_valid is not True):
        quality.machine_errors.append("runtime_only_consistency")
    if ambiguity in {"single_correct", "multiple_acceptable"} and sample.candidate_generation_valid is not True:
        quality.machine_errors.append("selection_candidate_consistency")
    if ambiguity == "candidate_generation_error" and (sample.candidate_generation_valid is not False or not sample.candidate_generation_errors):
        quality.machine_errors.append("candidate_error_consistency")
    if ambiguity == "insufficient_information" and acceptable is not None:
        quality.machine_errors.append("insufficient_information_gold")
    if ambiguity == "invalid_sample":
        quality.machine_errors.append("declared_invalid_sample")
    if sample.candidate_generation_valid is True and sample.candidate_generation_errors:
        quality.machine_errors.append("valid_with_errors")
    try:
        policy_input(sample)
    except PolicyInputRejected as exc:
        quality.machine_errors.append(exc.code)
    # Ref-only artifacts must not expose private file paths or credential strings.
    from .serialization import serialize_sample
    raw = serialize_sample(sample)
    if re.search(r"(?:sk-[A-Za-z0-9_-]{16,}|/Users/|[A-Za-z]:\\\\|Bearer\s+\S+)", raw):
        quality.machine_errors.append("sensitive_content")
    candidate_issues = []
    for action in sample.observation.admissible_actions:
        if action.kind != "call_tool":
            continue
        try:
            validate_bound_args(action.args.tool_id, action.args.input)
        except (ValueError, TypeError):
            candidate_issues.append("invalid_bound_args")
    if manifest is None:
        quality.unverified.extend(["frozen_candidate_basis", "semantic_adjudication"])
        return quality
    manifest, errors = validate_manifest(manifest)
    if errors:
        quality.frozen_errors.extend(errors)
        return quality
    evidence = evidence or {}
    refs = {sample.source.ref, *sample.source.related_refs, *sample.evidence_refs}
    if sample.source.projection_version != manifest.policy_version:
        quality.frozen_errors.append("projection_version_mismatch")
    for source in sample.label_source:
        refs.update(source.basis_refs)
    review = manifest.reviews.get(sample.sample_id)
    if review:
        refs.update(review.basis_refs)
        refs.update(review.reviewer.basis_refs)
    if not refs:
        quality.unverified.append("frozen_evidence")
    for ref in sorted(refs):
        content = evidence.get(ref)
        if content is None or hashlib.sha256(content).hexdigest() != manifest.evidence_digests.get(ref):
            quality.unverified.append("unavailable_or_changed_evidence")
    if review is None or review.observation_hash != sample.observation_hash:
        quality.unverified.append("frozen_candidate_basis")
    else:
        if sorted(review.expected_action_hashes) != sorted(action_hash(a) for a in sample.observation.admissible_actions):
            quality.frozen_errors.append("frozen_candidate_mismatch")
        if (review.candidate_generation_valid != sample.candidate_generation_valid
                or sorted(review.candidate_error_codes) != sorted(e.code for e in sample.candidate_generation_errors)):
            quality.frozen_errors.append("candidate_review_mismatch")
        reviewer = review.reviewer
        review_approved = reviewer.kind == "human" or (
            reviewer.kind == "approved_rule" and manifest.approved_rules.get(reviewer.ref) == reviewer.version)
        if not review_approved and not (not locked and reviewer.kind == "fixture_review"):
            quality.unverified.append("candidate_review_authority")
        if not review.basis_refs or not reviewer.basis_refs:
            quality.unverified.append("candidate_review_basis")
        for field in ("book_name", "subject"):
            if review.scope.get(field) != sample.observation.context.constraints.get(field):
                candidate_issues.append("scope_binding")
        for action in sample.observation.admissible_actions:
            if action.kind == "request_input" and (sample.source.decision_position != "pre_sql_input_gate"
                    or len(ids) != 1 or not sample.observation.missing_inputs):
                candidate_issues.append("missing_input_gate_error")
            if action.kind != "call_tool":
                continue
            tool_id = action.args.tool_id
            try:
                current = canonical_tool_metadata(tool_id)
                frozen = review.tool_metadata.get(tool_id, {})
                if any(frozen.get(key) != value for key, value in current.items()):
                    quality.unverified.append("registry_version_or_schema")
            except ValueError:
                quality.unverified.append("unsupported_tool_schema")
            for field in ("book_name", "subject"):
                if field in action.args.input and action.args.input[field] != review.scope.get(field):
                    candidate_issues.append("scope_binding")
            if tool_id == "get_recent_progress":
                expected = {**review.scope, "days": 7, "limit": 12}
            elif tool_id == "search_exercises":
                expected = {**review.scope, "query": sample.observation.context.resolved_query[:300],
                            "chapter": "", "tag": "", "status": "", "limit": 8}
            elif tool_id == "search_textbook":
                expected = {"query": sample.observation.context.resolved_query, "chapter": ""}
            else:
                expected = None
            if expected is not None and action.args.input != expected:
                candidate_issues.append("invalid_bound_args")
        if candidate_issues:
            if sample.candidate_generation_valid is True:
                quality.frozen_errors.extend(candidate_issues)
            elif any(("missing_input_gate_error" if issue == "missing_input_gate_error" else "invalid_bound_args")
                     not in review.candidate_error_codes for issue in candidate_issues):
                quality.frozen_errors.append("unrecorded_candidate_defect")
    quality.candidate_reviewed = (sample.candidate_generation_valid is not None
        and not (quality.machine_errors or quality.frozen_errors or quality.unverified))
    quality.semantic_adjudicated = adjudicated(sample, records, manifest, locked=locked)
    if not quality.semantic_adjudicated:
        quality.unverified.append("semantic_adjudication")
    if ambiguity == "insufficient_information":
        quality.unverified.append("insufficient_information")
    ready = not (quality.machine_errors or quality.frozen_errors or quality.unverified)
    quality.selection_eligible = ready and ambiguity in {"single_correct", "multiple_acceptable"}
    quality.diagnostic_eligible = ready and ambiguity in {"candidate_generation_error", "runtime_only"}
    return quality
