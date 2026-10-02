"""Strict sample IO and a separate observation-only selector boundary."""
from __future__ import annotations

import json
import re
from pathlib import Path
from backend.services.decision.policy_contracts import PolicyObservationV0, canonical_json
from backend.services.decision.policy_projection import digest
from .contracts import EvaluationSampleV0, TransformV0, DatasetManifestV0, PredictionV0


class PolicyInputRejected(ValueError):
    def __init__(self, code="policy_input_metadata"):
        super().__init__(code)
        self.code = code


# Field ownership comes from the Dataset contract; these belong to the evaluator,
# never to a nested Policy value. Action references are owned by candidates/Decision.
_EVALUATION_FIELDS = (set(EvaluationSampleV0.model_fields) | set(DatasetManifestV0.model_fields)
                      | set(TransformV0.model_fields) | (set(PredictionV0.model_fields) - {"status"})) | {
    "gold", "split", "notes", "envelope", "run_id", "task_id", "observation_id",
    "evaluator_result", "evaluation_result", "prediction", "prediction_result", "decision",
    "action_id", "action_ids", "action_mapping", "raw_output", "exception_type",
    "selector", "transform", "validation", "fallback", "runtime_version",
    "registry_version", "label_policy_version", "source_digests",
    "judgment", "reason_tags", "basis_refs",
}
_METADATA_KEYS = {key.casefold() for key in _EVALUATION_FIELDS}


def _check_structured_values(value):
    """Inspect structures, including JSON carried inside strings; no word filtering.

    Natural prose is untouched. Only syntactically valid JSON containers (also
    embedded/fenced) are recursively interpreted as structure, not as instructions.
    """
    if isinstance(value, dict):
        if any(key.casefold() in _METADATA_KEYS for key in value):
            raise PolicyInputRejected()
        for child in value.values():
            _check_structured_values(child)
    elif isinstance(value, list):
        for child in value:
            _check_structured_values(child)
    elif isinstance(value, str):
        # Also unwrap JSON-encoded strings before inspecting their structures.
        # The decoded string is strictly shorter, so nested encodings terminate.
        try:
            decoded = json.loads(value)
        except ValueError:
            decoded = None
        if isinstance(decoded, str) and decoded != value:
            _check_structured_values(decoded)
        # raw_decode recognizes a JSON container even with surrounding prose/fences.
        # Checking structured keys never rejects a mere occurrence of 'gold'.
        decoder = json.JSONDecoder()
        for match in re.finditer(r"[\[{]", value):
            try:
                decoded, _ = decoder.raw_decode(value, match.start())
            except ValueError:
                continue
            if isinstance(decoded, (dict, list)):
                _check_structured_values(decoded)


def strict_loads(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def observation_hash(observation):
    validated = PolicyObservationV0.model_validate(observation.model_dump() if isinstance(observation, PolicyObservationV0) else observation)
    return digest(validated.model_dump(exclude_none=True))


def validate_sample_schema(sample):
    # Revalidate even model_copy/update instances; never trust a constructed model.
    sample = EvaluationSampleV0.model_validate(sample.model_dump() if isinstance(sample, EvaluationSampleV0) else sample)
    if observation_hash(sample.observation) != sample.observation_hash:
        raise ValueError("observation_hash mismatch")
    return sample


def serialize_sample(sample):
    # Preserve null (unknown) and [] (known none), including nested optional fields.
    return canonical_json(validate_sample_schema(sample).model_dump())


def deserialize_sample(raw):
    return validate_sample_schema(strict_loads(raw))


def policy_input(value) -> PolicyObservationV0:
    """The one fail-closed Policy-facing boundary, also safe for direct adapters.

    Read only Observation from a validated sample, or a standalone wire Observation;
    revalidate and detach, then enforce nested field ownership before returning it.
    No gold/manifest/identity is serialized and no invalid input is silently stripped.
    """
    if isinstance(value, EvaluationSampleV0) or isinstance(value, dict) and "observation" in value:
        observation = validate_sample_schema(value).observation
    else:
        observation = PolicyObservationV0.model_validate(value.model_dump() if isinstance(value, PolicyObservationV0) else value)
    observation = PolicyObservationV0.model_validate_json(observation.canonical_json())
    # Top-level and context ownership are already enforced by the wire models.
    # Only recursively inspect their values, not those legal model field names.
    for text in (observation.request, observation.context.resolved_query, observation.context.goal):
        _check_structured_values(text)
    _check_structured_values(observation.context.constraints)
    _check_structured_values(observation.missing_inputs)
    if observation.previous_result:
        _check_structured_values(observation.previous_result.summary)
        _check_structured_values(observation.previous_result.tool_id)
    ids = {a.id for a in observation.admissible_actions}
    if ids != {f"a{i}" for i in range(len(ids))}:
        raise PolicyInputRejected("policy_input_action_id")
    for action in observation.admissible_actions:
        if action.kind == "call_tool":
            _check_structured_values(action.args.tool_id)
            _check_structured_values(action.args.input)
    return observation


def serialize_policy_input(sample):
    return policy_input(sample).canonical_json()


def invoke_policy(selector, observation):
    """All offline selectors/adapters receive the same detached, checked payload."""
    return selector(policy_input(observation))


def read_samples(path):
    return [deserialize_sample(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_samples(path, samples):
    data = "".join(serialize_sample(sample) + "\n" for sample in samples)
    # Exclusive create protects frozen artifacts from silent replacement.
    with Path(path).open("x", encoding="utf-8") as output:
        output.write(data)


def action_hash(action):
    value = action.model_dump() if hasattr(action, "model_dump") else action
    return digest({"kind": value["kind"], "args": value["args"]})


def permute_sample(sample, *, seed="dataset-v0", mode="main"):
    sample = validate_sample_schema(sample)
    value = sample.model_dump()
    original = value["observation"]["admissible_actions"]
    # Neither label nor Rule output participates. Source ref must be stable.
    ordered = sorted(original, key=lambda a: (
        digest(["hash-order/v0", seed, sample.source.ref, {"kind": a["kind"], "args": a["args"]}]), a["id"]))
    if mode != "main" and len(ordered) > 1:
        # One bounded control, guaranteed to change original positions.
        ordered = original[1:] + original[:1]
    if mode not in {"main", "position_only", "position_and_id"}:
        raise ValueError("unknown permutation mode")
    mapping = {a["id"]: a["id"] if mode == "position_only" else f"a{i}" for i, a in enumerate(ordered)}
    value["observation"]["admissible_actions"] = [{**a, "id": mapping[a["id"]]} for a in ordered]
    if value["acceptable_action_ids"] is not None:
        value["acceptable_action_ids"] = [mapping[a] for a in value["acceptable_action_ids"]]
    if value["preferred_action_id"] is not None:
        value["preferred_action_id"] = mapping[value["preferred_action_id"]]
    for judgment in value["action_judgments"]:
        judgment["action_id"] = mapping[judgment["action_id"]]
    for error in value["candidate_generation_errors"]:
        error["action_ids"] = [mapping[a] for a in error["action_ids"]]
    value["observation_hash"] = observation_hash(value["observation"])
    # No Runtime observation_id exists in this artifact.
    transformed = validate_sample_schema(value)
    record = TransformV0(mode=mode, seed=seed, original_sample_id=sample.sample_id,
        original_observation_hash=sample.observation_hash, transformed_observation_hash=transformed.observation_hash,
        action_mapping=mapping, original_order=[a["id"] for a in original],
        transformed_order=[a["id"] for a in value["observation"]["admissible_actions"]])
    return transformed, record
