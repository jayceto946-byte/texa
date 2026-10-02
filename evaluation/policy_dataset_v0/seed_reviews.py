"""Independent human review packets, immutable evidence and final label versions."""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
from typing import Literal
from pydantic import Field
from backend.services.decision.policy_contracts import StrictV0, canonical_json
from .contracts import ActionJudgmentV0, LabelSourceV0, FrozenReviewV0
from .labels import label_hash, record_adjudication
from .serialization import action_hash, observation_hash, strict_loads
from .seed_production import verify_trace, SeedRecipeV0, project_recipe
from .validation import canonical_tool_metadata


class HumanReviewV0(StrictV0):
    sample_id: str
    observation_hash: str
    label_hash: str
    reviewer_id: str = Field(min_length=1)
    reviewer_kind: Literal["human"]
    round: Literal["initial", "repeat", "adjudication"]
    predictions_visible: bool
    candidate_generation_valid: bool | None
    candidate_error_codes: list[str]
    candidate_reason: str = Field(min_length=1)
    ambiguity_status: Literal["single_correct", "multiple_acceptable", "candidate_generation_error",
                              "insufficient_information", "invalid_sample", "runtime_only"]
    acceptable_action_ids: list[str] | None
    action_judgments: list[ActionJudgmentV0]
    action_reasons: dict[str, str]
    input_requirement: Literal["required", "not_required", "undetermined"]
    reason: str = Field(min_length=1)
    basis_refs: list[str] = Field(min_length=1)
    elapsed_seconds: float = Field(ge=0)


def validate_review(sample, review):
    review = HumanReviewV0.model_validate(review.model_dump() if isinstance(review, HumanReviewV0) else review)
    if (review.sample_id, review.observation_hash, review.label_hash) != (sample.sample_id, sample.observation_hash, label_hash(sample)):
        raise ValueError("review binding mismatch")
    ids = {a.id for a in sample.observation.admissible_actions}
    if (not review.reviewer_id.strip() or not review.candidate_reason.strip() or not review.reason.strip()
            or set(review.action_reasons) != ids or any(not reason.strip() for reason in review.action_reasons.values())):
        raise ValueError("review requires individual candidate reasons and accountable identity")
    if len(review.action_judgments) != len(ids) or {j.action_id for j in review.action_judgments} != ids:
        raise ValueError("review must judge every candidate")
    if review.acceptable_action_ids is not None:
        acceptable = set(review.acceptable_action_ids)
        if len(acceptable) != len(review.acceptable_action_ids) or not acceptable <= ids:
            raise ValueError("invalid review acceptable set")
        if acceptable != {j.action_id for j in review.action_judgments if j.judgment == "acceptable"} or any(
                j.judgment == "undetermined" for j in review.action_judgments):
            raise ValueError("incomplete candidate judgments")
    elif any(j.judgment == "acceptable" for j in review.action_judgments):
        raise ValueError("unknown gold cannot contain acceptable judgment")
    if review.round in {"initial", "repeat"} and review.predictions_visible:
        raise ValueError("blind review cannot see predictions")
    if review.ambiguity_status == "single_correct" and len(review.acceptable_action_ids or []) != 1:
        raise ValueError("single_correct cardinality")
    if review.ambiguity_status == "multiple_acceptable" and len(review.acceptable_action_ids or []) < 2:
        raise ValueError("multiple_acceptable cardinality")
    if review.ambiguity_status == "insufficient_information" and review.acceptable_action_ids is not None:
        raise ValueError("insufficient_information requires null")
    if review.candidate_generation_valid is False and not review.candidate_error_codes:
        raise ValueError("candidate defect requires reason codes")
    if review.candidate_generation_valid is True and review.candidate_error_codes:
        raise ValueError("valid candidates cannot have defect codes")
    return review


def review_packet(sample):
    """No proposal labels, predictions, tags, split or majority vote in the packet."""
    return {"sample_id": sample.sample_id, "observation_hash": sample.observation_hash,
        "label_hash": label_hash(sample), "observation": sample.observation.model_dump(),
        "source_ref": sample.source.ref, "basis_refs": [sample.source.ref, *sample.evidence_refs],
        "instructions": "Human only. Review provenance and every candidate independently before viewing predictions. Null means unresolved. Do not infer gold from agreement or forced actions.",
        "review_template": {"sample_id": sample.sample_id, "observation_hash": sample.observation_hash,
            "label_hash": label_hash(sample), "reviewer_id": "", "reviewer_kind": "human", "round": "initial",
            "predictions_visible": False, "candidate_generation_valid": None, "candidate_error_codes": [],
            "candidate_reason": "", "ambiguity_status": "insufficient_information", "acceptable_action_ids": None,
            "action_judgments": [{"action_id": a.id, "judgment": "undetermined", "reason_tags": []}
                                 for a in sample.observation.admissible_actions],
            "action_reasons": {a.id: "" for a in sample.observation.admissible_actions},
            "input_requirement": "undetermined", "reason": "", "basis_refs": [sample.source.ref], "elapsed_seconds": 0.0}}


def _signature(review):
    return (review.candidate_generation_valid, tuple(sorted(review.candidate_error_codes)),
            review.ambiguity_status, None if review.acceptable_action_ids is None else tuple(sorted(review.acceptable_action_ids)),
            tuple(sorted((j.action_id, j.judgment, tuple(sorted(j.reason_tags))) for j in review.action_judgments)),
            review.input_requirement)


def review_statistics(samples, reviews):
    by_sample = {s.sample_id: s for s in samples}
    grouped = {}
    keys = set()
    for review in reviews:
        if review.sample_id not in by_sample:
            raise ValueError("review has no sample")
        review = validate_review(by_sample[review.sample_id], review)
        key = (review.sample_id, review.reviewer_id, review.round)
        if key in keys:
            raise ValueError("duplicate reviewer/round")
        keys.add(key)
        grouped.setdefault(review.sample_id, []).append(review)
    return _review_counts(grouped, {s.sample_id: s.source.source_family_id for s in samples})


def _review_counts(grouped, families):
    from .report import rate
    reviews = [r for items in grouped.values() for r in items]
    pairs, repeated = [], []
    for items in grouped.values():
        initial = [r for r in items if r.round == "initial"]
        if len(initial) >= 2:
            pairs.append((initial[0], initial[1]))
        repeated.extend((first, second) for first in initial for second in items
                        if second.round == "repeat" and second.reviewer_id == first.reviewer_id)
    sets_equal = lambda a, b: a.acceptable_action_ids is not None and b.acceptable_action_ids is not None and set(a.acceptable_action_ids) == set(b.acceptable_action_ids)
    determinate_pairs = [(a, b) for a, b in pairs if a.acceptable_action_ids is not None and b.acceptable_action_ids is not None]
    return {"reviewed_samples": len(grouped), "initial_reviews": sum(r.round == "initial" for r in reviews),
        "double_blind_samples": len(pairs), "repeated_samples": len({r.sample_id for _, r in repeated}),
        "double_blind_families": len({families[a.sample_id] for a, _ in pairs}),
        "repeated_families": len({families[a.sample_id] for a, _ in repeated}),
        "candidate_validity_agreement": rate(sum(a.candidate_generation_valid == b.candidate_generation_valid for a, b in pairs), len(pairs)),
        "ambiguity_agreement": rate(sum(a.ambiguity_status == b.ambiguity_status for a, b in pairs), len(pairs)),
        "acceptable_set_agreement": rate(sum(sets_equal(a, b) for a, b in determinate_pairs), len(determinate_pairs)),
        "unresolved_double_reviews": sum(not sets_equal(a, b) for a, b in pairs),
        "repeat_label_changes": sum(_signature(a) != _signature(b) for a, b in repeated),
        "repeat_comparisons": len(repeated),
        "per_candidate_disagreements": sum(x.judgment != y.judgment for a, b in pairs for x in a.action_judgments
                                            for y in b.action_judgments if x.action_id == y.action_id),
        "elapsed_seconds": sum(r.elapsed_seconds for r in reviews)}


def confirm_candidates(sample, review, *, new_sample_id, manifest, evidence, trace):
    """Candidate review precedes teacher prediction; it grants no semantic gold."""
    from .contracts import CandidateErrorV0, EvaluationSampleV0
    verify_trace(sample, trace)
    review = validate_review(sample, review)
    if review.candidate_generation_valid is None or new_sample_id == sample.sample_id:
        raise ValueError("determinate candidate review and new version required")
    if any(ref not in evidence or hashlib.sha256(evidence[ref]).hexdigest() != manifest.evidence_digests.get(ref) for ref in review.basis_refs):
        raise ValueError("candidate review basis unavailable or changed")
    source_ref, obs, new_trace = sample.source.ref, sample.observation, trace
    content = canonical_json(review.model_dump()).encode()
    review_ref = "human-candidate-review/" + hashlib.sha256(content).hexdigest()
    evidence = {**evidence, review_ref: content, source_ref: canonical_json(new_trace).encode()}
    source = LabelSourceV0(kind="human", ref=review.reviewer_id, version="seed-candidate-review/v0",
                          basis_refs=[*review.basis_refs, review_ref])
    value = sample.model_dump()
    value.update(sample_id=new_sample_id, candidate_generation_valid=review.candidate_generation_valid,
        candidate_generation_errors=[CandidateErrorV0(code=code, action_ids=[]).model_dump() for code in review.candidate_error_codes],
        acceptable_action_ids=None, preferred_action_id=None,
        action_judgments=[{"action_id": a.id, "judgment": "undetermined", "reason_tags": []} for a in obs.admissible_actions],
        ambiguity_status="insufficient_information" if review.candidate_generation_valid else "candidate_generation_error",
        label_source=[], adjudication_reason="Candidate review completed; semantic gold remains unresolved.")
    value["evidence_refs"] = list(dict.fromkeys([*sample.evidence_refs, review_ref]))
    result = EvaluationSampleV0.model_validate(value)
    frozen = FrozenReviewV0(observation_hash=result.observation_hash,
        candidate_generation_valid=review.candidate_generation_valid, candidate_error_codes=review.candidate_error_codes,
        expected_action_hashes=[action_hash(a) for a in obs.admissible_actions],
        scope={key: obs.context.constraints.get(key, "") for key in ("book_name", "subject")},
        tool_metadata={a.args.tool_id: canonical_tool_metadata(a.args.tool_id) for a in obs.admissible_actions if a.kind == "call_tool"},
        reviewer=source, basis_refs=[source_ref, review_ref])
    manifest = manifest.model_copy(deep=True)
    manifest.reviews[result.sample_id] = frozen
    manifest.evidence_digests = {ref: hashlib.sha256(data).hexdigest() for ref, data in evidence.items()}
    return result, manifest, evidence, new_trace


def finalize_sample(sample, reviews, final, *, new_sample_id, manifest, evidence, trace):
    """Requires two actual human blind records. AI never supplies a human identity.

    `final` is a human record bound to the same base sample. On disagreement a
    third, separate human must supply an explicit adjudication record.
    """
    verify_trace(sample, trace)
    review_statistics([sample], reviews)
    initial = [validate_review(sample, r) for r in reviews if r.round == "initial"]
    final = validate_review(sample, final)
    if len({r.reviewer_id for r in initial}) < 2:
        raise ValueError("two independent human blind reviews required")
    if any(_signature(r) != _signature(initial[0]) for r in initial):
        if final.round != "adjudication" or final.reviewer_id in {r.reviewer_id for r in initial}:
            raise ValueError("disagreement requires a third human adjudicator")
    elif _signature(final) != _signature(initial[0]):
        raise ValueError("final label changed without adjudication")
    if final.candidate_generation_valid is None or final.acceptable_action_ids is None or final.ambiguity_status in {"insufficient_information", "invalid_sample"}:
        raise ValueError("unresolved sample cannot be finalized")
    if new_sample_id == sample.sample_id:
        raise ValueError("gold changes require a new sample version")
    for review in [*reviews, final]:
        if any(ref not in evidence or hashlib.sha256(evidence[ref]).hexdigest() != manifest.evidence_digests.get(ref) for ref in review.basis_refs):
            raise ValueError("review basis unavailable or changed")
    value = sample.model_dump()
    value.update(sample_id=new_sample_id, candidate_generation_valid=final.candidate_generation_valid,
        ambiguity_status=final.ambiguity_status, acceptable_action_ids=final.acceptable_action_ids,
        preferred_action_id=None, action_judgments=[j.model_dump() for j in final.action_judgments],
        input_requirement=final.input_requirement, adjudication_reason=final.reason)
    from .contracts import CandidateErrorV0, EvaluationSampleV0
    value["candidate_generation_errors"] = [CandidateErrorV0(code=code, action_ids=[]).model_dump() for code in final.candidate_error_codes]
    # Label-only versions retain the frozen source, so the teacher's main view
    # (which hashes source.ref) does not change after blinded adjudication.
    source_ref, new_trace = sample.source.ref, trace
    evidence = dict(evidence)
    review_refs = []
    for review in [*reviews, final]:
        content = canonical_json(review.model_dump()).encode()
        ref = "human-review/" + hashlib.sha256(content).hexdigest()
        evidence[ref] = content
        review_refs.append(ref)
    evidence[source_ref] = canonical_json(new_trace).encode()
    source = LabelSourceV0(kind="human", ref=final.reviewer_id, version="seed-human-review/v0",
        basis_refs=list(dict.fromkeys([*final.basis_refs, *review_refs])))
    value["label_source"] = [source.model_dump()]
    value["evidence_refs"] = list(dict.fromkeys([*sample.evidence_refs, *review_refs]))
    result = EvaluationSampleV0.model_validate(value)
    frozen_review = FrozenReviewV0(observation_hash=result.observation_hash,
        candidate_generation_valid=final.candidate_generation_valid, candidate_error_codes=final.candidate_error_codes,
        expected_action_hashes=[action_hash(a) for a in result.observation.admissible_actions],
        scope={k: result.observation.context.constraints.get(k, "") for k in ("book_name", "subject")},
        tool_metadata={a.args.tool_id: canonical_tool_metadata(a.args.tool_id)
                       for a in result.observation.admissible_actions if a.kind == "call_tool"},
        reviewer=source, basis_refs=[source_ref, *review_refs])
    manifest = manifest.model_copy(deep=True)
    manifest.reviews[result.sample_id] = frozen_review
    manifest.evidence_digests = {ref: hashlib.sha256(data).hexdigest() for ref, data in evidence.items()}
    binding = {"base_sample_id": sample.sample_id, "base_observation_hash": sample.observation_hash,
        "base_label_hash": label_hash(sample), "final_sample_id": result.sample_id,
        "final_observation_hash": result.observation_hash, "final_label_hash": label_hash(result),
        "review_refs": review_refs, "final_review_ref": review_refs[-1]}
    return result, manifest, evidence, record_adjudication(result, source, confirmed=True), new_trace, binding


def verify_final_review(sample, binding, evidence):
    """Recheck exported responsibility chain at release time, not just at import."""
    if (binding["final_sample_id"], binding["final_observation_hash"], binding["final_label_hash"]) != (
            sample.sample_id, sample.observation_hash, label_hash(sample)):
        raise ValueError("final review binding mismatch")
    reviews = [HumanReviewV0.model_validate(strict_loads(evidence[ref])) for ref in set(binding["review_refs"])]
    for review in reviews:
        if (review.sample_id, review.observation_hash, review.label_hash) != (
                binding["base_sample_id"], binding["base_observation_hash"], binding["base_label_hash"]):
            raise ValueError("base review binding mismatch")
        ids = {a.id for a in sample.observation.admissible_actions}
        if set(review.action_reasons) != ids or any(not r.strip() for r in review.action_reasons.values()):
            raise ValueError("frozen review lacks candidate reasons")
    initial = [r for r in reviews if r.round == "initial" and not r.predictions_visible]
    if len(initial) < 2 or len({r.reviewer_id for r in initial}) != len(initial):
        raise ValueError("two distinct blind human reviews required")
    final = HumanReviewV0.model_validate(strict_loads(evidence[binding["final_review_ref"]]))
    if any(_signature(r) != _signature(initial[0]) for r in initial):
        if final.round != "adjudication" or final.reviewer_id in {r.reviewer_id for r in initial}:
            raise ValueError("missing third human adjudication")
    elif _signature(final) != _signature(initial[0]):
        raise ValueError("final label inconsistent with reviews")
    if (final.candidate_generation_valid, final.ambiguity_status, final.acceptable_action_ids,
            final.action_judgments, final.input_requirement, final.reason) != (
            sample.candidate_generation_valid, sample.ambiguity_status, sample.acceptable_action_ids,
            sample.action_judgments, sample.input_requirement, sample.adjudication_reason):
        raise ValueError("final review/label mismatch")
    return True


def bound_review_statistics(samples, bindings, evidence):
    """Compute agreement from hash-bound review bytes, not an editable summary."""
    grouped, families, keys = {}, {}, {}
    for sample in samples:
        binding = bindings.get(sample.sample_id)
        if not binding:
            continue
        verify_final_review(sample, binding, evidence)
        for ref in sorted(set(binding["review_refs"])):
            review = HumanReviewV0.model_validate(strict_loads(evidence[ref]))
            key = (review.sample_id, review.reviewer_id, review.round)
            if key in keys:
                if keys[key] != review:
                    raise ValueError("conflicting frozen human review")
                continue
            keys[key] = review
            grouped.setdefault(review.sample_id, []).append(review)
            families[review.sample_id] = sample.source.source_family_id
    return _review_counts(grouped, families)
