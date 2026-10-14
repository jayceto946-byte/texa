"""Dataset fields from the approved Spec; versions and split live in manifests."""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import Field
from backend.services.decision.policy_contracts import StrictV0, PolicyObservationV0

DATASET_VERSION = "texa.policy-dataset/v0"
LABEL_POLICY_VERSION = "evaluation-spec/v0"
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Split = Literal["development", "validation", "locked_test"]
Ambiguity = Literal["single_correct", "multiple_acceptable", "candidate_generation_error",
                    "insufficient_information", "invalid_sample", "runtime_only"]
CandidateErrorCode = Literal["required_action_missing", "forbidden_action_exposed",
                            "invalid_bound_args", "missing_input_gate_error"]


class SourceV0(StrictV0):
    type: Literal["deterministic_fixture", "runtime_capture", "fault_injection"]
    source_family_id: str = Field(min_length=1)
    ref: str = Field(min_length=1)
    projection_version: str = Field(min_length=1)
    decision_position: str = Field(min_length=1)
    # Explicit relationships only; never infer family authority from similarity.
    related_refs: list[str] = Field(default_factory=list)
    used_for_tuning: bool = False


class CandidateErrorV0(StrictV0):
    code: CandidateErrorCode
    action_ids: list[str]


class ActionJudgmentV0(StrictV0):
    action_id: str
    judgment: Literal["acceptable", "unacceptable", "undetermined"]
    reason_tags: list[str]


class LabelSourceV0(StrictV0):
    kind: Literal["human", "approved_rule", "fixture_review", "unadjudicated"]
    ref: str = Field(min_length=1)
    version: str = Field(min_length=1)
    basis_refs: list[str]


class EvaluationSampleV0(StrictV0):
    sample_id: str = Field(min_length=1)
    observation: PolicyObservationV0
    observation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source: SourceV0
    scenario_tags: list[str]
    candidate_generation_valid: bool | None
    candidate_generation_errors: list[CandidateErrorV0]
    ambiguity_status: Ambiguity
    acceptable_action_ids: list[str] | None
    preferred_action_id: str | None
    action_judgments: list[ActionJudgmentV0]
    input_requirement: Literal["required", "not_required", "undetermined"]
    label_source: list[LabelSourceV0]
    adjudication_reason: str = Field(max_length=1200)
    evidence_refs: list[str] = Field(default_factory=list)
    hard_tags: list[str] = Field(default_factory=list)


class FrozenReviewV0(StrictV0):
    """Separate review evidence; a validity flag inside a sample is insufficient."""
    observation_hash: str
    candidate_generation_valid: bool
    candidate_error_codes: list[CandidateErrorCode]
    expected_action_hashes: list[str]
    scope: dict[str, str]
    tool_metadata: dict[str, dict]
    reviewer: LabelSourceV0
    basis_refs: list[str]


class DatasetManifestV0(StrictV0):
    format_version: Literal["texa.policy-dataset/v0"] = DATASET_VERSION
    policy_version: Literal["texa.runtime-policy/v0"] = "texa.runtime-policy/v0"
    label_policy_version: Literal["evaluation-spec/v0"]
    runtime_version: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    registry_version: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source_digests: dict[str, Sha256]
    # Ref -> digest of frozen, locally supplied bytes. Never fetch refs remotely.
    evidence_digests: dict[str, Sha256]
    approved_rules: dict[str, str] = Field(default_factory=dict)
    reviews: dict[str, FrozenReviewV0]


class TransformV0(StrictV0):
    version: Literal["hash-order/v0"] = "hash-order/v0"
    mode: Literal["main", "position_only", "position_and_id"]
    seed: str
    original_sample_id: str
    original_observation_hash: str
    transformed_observation_hash: str
    # original ID -> local transformed ID, including identities for position-only.
    action_mapping: dict[str, str]
    original_order: list[str]
    transformed_order: list[str]


class PredictionV0(StrictV0):
    sample_id: str
    observation_hash: str
    selector: str
    view: str
    status: Literal["accepted", "invalid_format", "unknown_action_id", "selector_exception",
                    "timeout", "forced", "runtime_only", "disabled/not_run", "invalid_sample"]
    raw_output: str | None = None
    action_id: str | None = None
    exception_type: str | None = None
    validation: str = "not_run"
    transform: TransformV0 | None = None
