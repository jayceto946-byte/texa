"""Adjudication is separate from prediction and bound to immutable sample bytes."""
from __future__ import annotations

from typing import Literal
from backend.services.decision.policy_contracts import StrictV0
from backend.services.decision.policy_projection import digest
from .contracts import LabelSourceV0, EvaluationSampleV0


def label_hash(sample):
    fields = ("candidate_generation_valid", "candidate_generation_errors", "ambiguity_status",
              "acceptable_action_ids", "preferred_action_id", "action_judgments", "input_requirement",
              "label_source", "adjudication_reason", "evidence_refs")
    data = sample.model_dump()
    return digest({key: data[key] for key in fields})


class AdjudicationRecordV0(StrictV0):
    sample_id: str
    observation_hash: str
    label_hash: str
    disposition: Literal["confirmed", "pending"]
    source: LabelSourceV0
    reason: str


def record_adjudication(sample: EvaluationSampleV0, source, *, confirmed=False):
    return AdjudicationRecordV0(sample_id=sample.sample_id, observation_hash=sample.observation_hash,
        label_hash=label_hash(sample), disposition="confirmed" if confirmed else "pending",
        source=source, reason=sample.adjudication_reason)


def adjudicated(sample, records, manifest, *, locked=False):
    for record in records:
        if (record.sample_id, record.observation_hash, record.label_hash, record.disposition) != (
                sample.sample_id, sample.observation_hash, label_hash(sample), "confirmed"):
            continue
        source = record.source
        approved = source.kind == "approved_rule" and manifest.approved_rules.get(source.ref) == source.version
        independent = source.kind == "human" or approved or (not locked and source.kind == "fixture_review")
        if (independent and source in sample.label_source and record.reason and source.basis_refs
                and all(ref in manifest.evidence_digests for ref in source.basis_refs)):
            return True
    return False
