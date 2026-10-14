"""One original prediction per view. Never execute, repair or fall back."""
from __future__ import annotations

from backend.services.decision.policy import RulePolicyV0
from backend.services.decision.policy_contracts import canonical_json, parse_decision
from .contracts import PredictionV0
from .serialization import policy_input, permute_sample, validate_sample_schema, invoke_policy
from .validation import validate_sample
from .teacher_adapter import DisabledTeacherV0, NotRun


def rule_policy_adapter(observation):
    return invoke_policy(RulePolicyV0, observation)


def evaluate(sample, *, selector=rule_policy_adapter, selector_name="rule", view="main", seed="dataset-v0"):
    sample = validate_sample_schema(sample)
    result = dict(sample_id=sample.sample_id, observation_hash=sample.observation_hash,
                  selector=selector_name, view=view)
    quality = validate_sample(sample)
    if quality.machine_errors or sample.ambiguity_status == "invalid_sample":
        return PredictionV0(**result, status="invalid_sample")
    transform = None
    if view != "original":
        sample, transform = permute_sample(sample, seed=seed, mode=view)
    result.update(observation_hash=sample.observation_hash, transform=transform)
    if getattr(selector, "enabled", True) is False:
        return PredictionV0(**result, status="disabled/not_run")
    observation = policy_input(sample)
    ids = {action.id for action in observation.admissible_actions}
    if not ids:
        return PredictionV0(**result, status="runtime_only")
    if len(ids) == 1:
        return PredictionV0(**result, status="forced", action_id=next(iter(ids)), validation="membership_only")
    try:
        # Detached nested objects, no sample ID, labels, path or manifest.
        value = invoke_policy(selector, observation)
    except TimeoutError as exc:
        return PredictionV0(**result, status="timeout", exception_type=type(exc).__name__)
    except Exception as exc:
        return PredictionV0(**result, status="selector_exception", exception_type=type(exc).__name__)
    if isinstance(value, NotRun):
        return PredictionV0(**result, status="disabled/not_run")
    try:
        raw = value if isinstance(value, str) else canonical_json(value.model_dump() if hasattr(value, "model_dump") else value)
    except (ValueError, TypeError):
        raw = "<non-JSON output>"
    try:
        decision = parse_decision(value)
    except (ValueError, TypeError):
        return PredictionV0(**result, status="invalid_format", raw_output=raw, validation="rejected_format")
    if decision.action_id not in ids:
        return PredictionV0(**result, status="unknown_action_id", raw_output=raw,
                            action_id=decision.action_id, validation="rejected_membership")
    return PredictionV0(**result, status="accepted", raw_output=raw,
                        action_id=decision.action_id, validation="membership_only")


def original_action_id(prediction):
    if prediction.status not in {"accepted", "forced"}:
        return None
    if prediction.transform is None:
        return prediction.action_id
    reverse = {local: original for original, local in prediction.transform.action_mapping.items()}
    return reverse.get(prediction.action_id)


def evaluate_views(samples, *, seed="dataset-v0", control_families=(), teacher=None):
    teacher = teacher if teacher is not None else DisabledTeacherV0()
    results = []
    for sample in sorted(samples, key=lambda s: s.sample_id):
        views = ["main", "original"]
        if sample.source.source_family_id in control_families and len(sample.observation.admissible_actions) > 1:
            views += ["position_only", "position_and_id"]
        for view in views:
            results.append(evaluate(sample, view=view, seed=seed))
            results.append(evaluate(sample, selector=teacher, selector_name="fake_teacher" if teacher.test_only else "teacher",
                                    view=view, seed=seed))
    return results
