"""Bounded offline production through the pinned matcher, resolver and binder.

The registry uses the already approved canonical schema snapshot. No tool handler,
learning store, model client or production index is opened. These are harness
projections, not evidence that a synthetic state occurred in production.
"""
from __future__ import annotations

import copy
import ast
import hashlib
from pathlib import Path
from .baseline import DEFAULT_DATASET
from typing import Literal
from pydantic import Field

from backend.services.decision.policy_contracts import StrictV0, canonical_json, PolicyObservationV0
from backend.services.decision.policy_projection import matched_tool_refs, project_observation, digest
from backend.tools.registry import ToolContext, ToolRegistry, ToolSpec
from .contracts import EvaluationSampleV0, SourceV0, ActionJudgmentV0
from .serialization import observation_hash, policy_input, strict_loads, write_samples
from .validation import validate_manifest, validate_bound_args, canonical_tool_metadata
from .splits import assign_splits, write_manifest

VERSION = "seed-production/v0"
EVIDENCE_FUNCTION_HASH = "cdf2ce44cd54939b3f770c16f981bcf57b64463496c801947064bd950efbd270"


def _import_free_projection():
    """Run the pinned production function without importing the model stack.

    The only removed node is its local import of has_textbook_evidence; that
    exact pure function is loaded from reviewed source instead. No binder/gate
    logic is replaced. Fail closed on either source pin changing.
    """
    from .validation import validate_manifest
    root = Path(__file__).resolve().parents[2]
    baseline = strict_loads((DEFAULT_DATASET / "manifest.json").read_text())
    _, errors = validate_manifest(baseline)
    if errors:
        raise ValueError(",".join(errors))
    generator = ast.parse((root / "graph/generator.py").read_text())
    helper = next(n for n in generator.body if isinstance(n, ast.FunctionDef) and n.name == "has_textbook_evidence")
    if hashlib.sha256(ast.dump(helper, include_attributes=False).encode()).hexdigest() != EVIDENCE_FUNCTION_HASH:
        raise ValueError("reviewed evidence helper changed")
    globals_ = dict(project_observation.__globals__)
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "<pinned evidence helper>", "exec"), globals_)
    module = ast.parse((root / "backend/services/decision/policy_projection.py").read_text())
    function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "project_observation")
    class RemoveModelImport(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            if node.module == "graph.generator" and len(node.names) == 1 and node.names[0].name == "has_textbook_evidence":
                return ast.copy_location(ast.Pass(), node)
            return node
    function = RemoveModelImport().visit(function)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), "<pinned offline projection>", "exec"), globals_)
    return globals_["project_observation"]


class PriorCallV0(StrictV0):
    tool_id: Literal["get_recent_progress", "search_exercises", "search_textbook"]
    status: Literal["succeeded", "failed", "unknown"]
    error_code: str | None = None
    # Only the bounded structural facts consumed by previous_result are accepted.
    counts: dict[str, int] = Field(default_factory=dict)
    coverage_incomplete: bool = False
    evidence_insufficient: bool = False


class SeedRecipeV0(StrictV0):
    sample_id: str = Field(min_length=1)
    source_family_id: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    related_refs: list[str] = Field(default_factory=list)
    request: str = Field(max_length=10000)
    resolved_query: str = Field(max_length=2000)
    book_name: str = Field(default="", max_length=120)
    subject: str = Field(default="", max_length=120)
    answer_mode: Literal["global_general", "subject_general", "textbook_grounded"] = "global_general"
    goal: str | None = Field(default=None, max_length=2000)
    goal_origin_ref: str | None = None
    prior_calls: list[PriorCallV0] = Field(default_factory=list, max_length=3)
    budget_calls: int = Field(default=3, ge=0, le=8)
    consumed_model_calls: int = Field(default=0, ge=0, le=8)
    budget_model_calls: int = Field(default=3, ge=0, le=8)
    missing_inputs: list[dict] = Field(default_factory=list, max_length=20)
    position: Literal["sql_next_action", "pre_sql_input_gate"] = "sql_next_action"
    scenario_tags: list[str] = Field(default_factory=list)
    used_for_tuning: bool = False
    # Always separately emitted, with the legal baseline and exact mutation.
    fault: Literal["wrong_book", "drop_tools"] | None = None


class _SnapshotSchema:
    def __init__(self, tool_id, schema, *, input_schema=False, value=None):
        self.tool_id, self.schema, self.input_schema, self.value = tool_id, schema, input_schema, value

    def model_json_schema(self):
        return copy.deepcopy(self.schema)

    def model_validate(self, args):
        args = copy.deepcopy(args)
        if not isinstance(args, dict) or set(args) - set(self.schema["properties"]):
            raise ValueError("noncanonical_bound_args")
        for key, rule in self.schema["properties"].items():
            if key not in args and "default" in rule:
                args[key] = copy.deepcopy(rule["default"])
        validate_bound_args(self.tool_id, args)
        return _SnapshotSchema(self.tool_id, self.schema, value=args)

    def model_dump(self):
        return copy.deepcopy(self.value)


def offline_registry(recipe):
    snapshot = strict_loads(Path(__file__).with_name("canonical-tools-v0.json").read_text())
    registry = ToolRegistry()
    def no_execution(*_):
        raise RuntimeError("offline generation cannot execute tools")
    for name, meta in snapshot.items():
        canonical_tool_metadata(name)  # Recompute schema hash before registration.
        registry.register(ToolSpec(name=name, description="Pinned offline schema", parameters=meta["input_schema"],
            read_only=True, handler=no_execution,
            runtime_input=_SnapshotSchema(name, meta["input_schema"], input_schema=True),
            runtime_output=_SnapshotSchema(name, meta["output_schema"]),
            version=meta["version"], permission=meta["permission"], source=meta["source"],
            side_effect=meta["side_effect"]))
    return registry


def project_recipe(recipe: SeedRecipeV0):
    recipe = SeedRecipeV0.model_validate(recipe.model_dump())
    if recipe.goal and not recipe.goal_origin_ref:
        raise ValueError("goal requires a frozen origin ref")
    if len({c.tool_id for c in recipe.prior_calls}) != len(recipe.prior_calls):
        raise ValueError("V0 does not retry tools")
    if len(recipe.prior_calls) > recipe.budget_calls:
        raise ValueError("prior calls exceed budget")
    if recipe.consumed_model_calls > recipe.budget_model_calls:
        raise ValueError("prior model calls exceed budget")
    calls = []
    for call in recipe.prior_calls:
        data = {}
        for field, count in call.counts.items():
            if field not in {"recent_events", "exercises", "evidence_items"} or type(count) is not int or not 0 <= count <= 50:
                raise ValueError("unsupported or unbounded structural result")
            if field == "evidence_items" and count:
                raise ValueError("synthetic evidence cannot enable a grounded answer")
            data[field] = [{} for _ in range(count)]
        if call.coverage_incomplete:
            data["window_complete"] = False
        if call.evidence_insufficient:
            data["evidence_support"] = {"status": "insufficient"}
        calls.append({"tool_id": call.tool_id, "status": call.status,
            "error_code": call.error_code, "result": {"data": data}})
    registry = offline_registry(recipe)
    grounded = recipe.answer_mode == "textbook_grounded"
    refs, matcher_exclusions = matched_tool_refs(recipe.resolved_query, registry, grounded=grounded)
    # Frozen synthetic scope; it is explicitly NOT an active production index pin.
    scope = {"book_name": recipe.book_name, "subject": recipe.subject,
             "index_versions": {}, "scope_policy": "synthetic-harness/v0"}
    state = {"use_textbook_context": grounded, "answer_mode": recipe.answer_mode}
    if grounded:
        state["_runtime_textbook_scope"] = scope
    snapshot = {"task": {"status": "running"}, "run": {"status": "running"},
        "tool_calls": calls, "consumed_calls": len(calls), "budget_calls": recipe.budget_calls,
        "consumed_model_calls": recipe.consumed_model_calls, "budget_model_calls": recipe.budget_model_calls}
    # A true pre-SQL gate uses an empty registry/context, as input_gate_observation does.
    gate = recipe.position == "pre_sql_input_gate"
    if gate and not recipe.missing_inputs:
        raise ValueError("pre-SQL gate requires missing inputs")
    if gate and (recipe.prior_calls or recipe.goal):
        raise ValueError("pre-SQL gate has no SQL calls or goal context")
    projection = _import_free_projection() if grounded else project_observation
    frozen = projection(request=recipe.request, resolved_query=recipe.resolved_query,
        registry=ToolRegistry() if gate else registry,
        context=ToolContext() if gate else ToolContext(recipe.book_name, recipe.subject),
        identity={"position": recipe.position}, candidate_tools=() if gate else refs,
        snapshot=None if gate else snapshot, answer_state=None if gate else state,
        missing_inputs=recipe.missing_inputs, gate=gate, goal=recipe.goal)
    observation = policy_input(frozen.envelope.payload)
    trace = {"version": VERSION, "recipe": recipe.model_dump(), "recipe_hash": digest(recipe.model_dump()),
        "scope": "harness", "production_entry_verified": False,
        "evidence_helper_hash": EVIDENCE_FUNCTION_HASH if grounded else None,
        "matched_tool_refs": list(refs), "matcher_exclusions": matcher_exclusions,
        "projection_exclusions": frozen.exclusions,
        "legal_observation": observation.model_dump(), "legal_observation_hash": observation_hash(observation),
        "goal_origin_ref": recipe.goal_origin_ref}
    if recipe.fault:
        value = observation.model_dump()
        if recipe.fault == "wrong_book":
            action = next((a for a in value["admissible_actions"] if a["kind"] == "call_tool" and "book_name" in a["args"]["input"]), None)
            if action is None:
                raise ValueError("wrong_book injection requires a scoped tool")
            action["args"]["input"]["book_name"] = "other-book"
        else:
            if not any(a["kind"] == "call_tool" for a in value["admissible_actions"]):
                raise ValueError("drop_tools requires an original legal tool")
            value["admissible_actions"] = [a for a in value["admissible_actions"] if a["kind"] != "call_tool"]
            for index, action in enumerate(value["admissible_actions"]):
                action["id"] = f"a{index}"
        observation = policy_input(PolicyObservationV0.model_validate(value))
    trace["observation_hash"] = observation_hash(observation)
    return observation, trace


def generate_sample(recipe):
    observation, trace = project_recipe(recipe)
    # Reproduction is not independent review or semantic gold.
    sample = EvaluationSampleV0(sample_id=recipe.sample_id, observation=observation,
        observation_hash=observation_hash(observation), source=SourceV0(
            type="fault_injection" if recipe.fault else "deterministic_fixture",
            source_family_id=recipe.source_family_id, ref=recipe.source_ref,
            projection_version="texa.runtime-policy/v0", decision_position=recipe.position,
            related_refs=recipe.related_refs, used_for_tuning=recipe.used_for_tuning),
        scenario_tags=recipe.scenario_tags, candidate_generation_valid=None, candidate_generation_errors=[],
        ambiguity_status="insufficient_information", acceptable_action_ids=None, preferred_action_id=None,
        action_judgments=[ActionJudgmentV0(action_id=a.id, judgment="undetermined", reason_tags=[])
                          for a in observation.admissible_actions], input_requirement="undetermined",
        label_source=[], adjudication_reason="Await independent candidate and semantic review.")
    return sample, trace


def verify_trace(sample, trace):
    recipe = SeedRecipeV0.model_validate(trace["recipe"])
    observation, expected = project_recipe(recipe)
    if trace != expected or sample.observation_hash != observation_hash(observation) or sample.observation != observation:
        raise ValueError("projection trace mismatch")
    # Label-only versions keep the same immutable source ref and evaluation view.
    # The final review chain separately binds their base and new sample IDs.
    if (sample.source.source_family_id, sample.source.ref, sample.source.related_refs,
            sample.source.decision_position, sample.source.type, sample.source.used_for_tuning) != (
            recipe.source_family_id, recipe.source_ref, recipe.related_refs, recipe.position,
            "fault_injection" if recipe.fault else "deterministic_fixture", recipe.used_for_tuning):
        raise ValueError("projection source mismatch")
    return True


def load_dataset(directory):
    from .serialization import read_samples
    from .labels import AdjudicationRecordV0
    root = Path(directory).resolve()
    manifest, errors = validate_manifest(strict_loads((root / "manifest.json").read_text()))
    if errors:
        raise ValueError(",".join(errors))
    samples = read_samples(root / "samples.jsonl")
    if len({s.sample_id for s in samples}) != len(samples):
        raise ValueError("duplicate sample_id")
    evidence_files = strict_loads((root / "evidence-files.json").read_text())
    evidence = {}
    for ref, relative in evidence_files.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError("evidence outside dataset")
        evidence[ref] = path.read_bytes()
        if hashlib.sha256(evidence[ref]).hexdigest() != manifest.evidence_digests.get(ref):
            raise ValueError("evidence digest mismatch")
    records = [AdjudicationRecordV0.model_validate(strict_loads(line)) for line in
        (root / "adjudications.jsonl").read_text().splitlines() if line.strip()]
    return samples, manifest, records, evidence


def write_bundle(output, samples, manifest, evidence, *, records=(), traces=None, splits=None):
    """Exclusive new artifact directory; input refs retain exact frozen bytes."""
    from .serialization import serialize_sample
    from .seed_report import assert_public_artifact
    samples = list(samples)
    if len({s.sample_id for s in samples}) != len(samples):
        raise ValueError("duplicate sample_id")
    for sample in samples:
        assert_public_artifact(strict_loads(serialize_sample(sample)))
    assert_public_artifact(manifest.model_dump())
    for ref, content in evidence.items():
        if hashlib.sha256(content).hexdigest() != manifest.evidence_digests.get(ref):
            raise ValueError("unbound evidence")
        assert_public_artifact(content.decode("utf-8"))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_samples(output / "samples.jsonl", samples)
    (output / "manifest.json").write_text(canonical_json(manifest.model_dump()) + "\n")
    (output / "adjudications.jsonl").write_text("".join(canonical_json(r.model_dump()) + "\n" for r in records))
    files = {}
    (output / "evidence").mkdir()
    for ref, content in sorted(evidence.items()):
        name = f"evidence/{hashlib.sha256(content).hexdigest()}.bin"
        if not (output / name).exists():
            (output / name).write_bytes(content)
        files[ref] = name
    (output / "evidence-files.json").write_text(canonical_json(files) + "\n")
    (output / "projections.json").write_text(canonical_json(traces or {}) + "\n")
    write_manifest(output / "split.json", splits or assign_splits(samples))


def produce(recipes, baseline_manifest, output, *, seed="seed-v0"):
    manifest, errors = validate_manifest(baseline_manifest)
    if errors:
        raise ValueError(",".join(errors))
    recipes = [SeedRecipeV0.model_validate(r) for r in recipes]
    if not 1 <= len(recipes) <= 50:
        raise ValueError("produce 1..50 decision points per batch")
    samples, traces, evidence = [], {}, {}
    for recipe in recipes:
        sample, trace = generate_sample(recipe)
        content = canonical_json(trace).encode()
        if sample.source.ref in evidence:
            raise ValueError("source ref must identify a unique frozen decision point")
        evidence[sample.source.ref] = content
        samples.append(sample)
        traces[sample.sample_id] = trace
    # Relationships/goal origins need their own frozen, caller-supplied evidence.
    # A batch ref is an explicit synthetic template relation, not a production ref.
    for recipe in recipes:
        for ref in [*recipe.related_refs, *([recipe.goal_origin_ref] if recipe.goal_origin_ref else [])]:
            if ref not in evidence:
                evidence[ref] = canonical_json({"kind": "synthetic_relation", "ref": ref,
                    "members": sorted(r.sample_id for r in recipes if ref in r.related_refs or r.goal_origin_ref == ref)}).encode()
    manifest = manifest.model_copy(update={"reviews": {}, "approved_rules": {},
        "evidence_digests": {ref: hashlib.sha256(data).hexdigest() for ref, data in evidence.items()}})
    from .seed import calibration_safe_splits
    splits = calibration_safe_splits(samples, seed=seed)
    natural = [s for s in samples if s.source.type != "fault_injection"]
    faults = [s for s in samples if s.source.type == "fault_injection"]
    write_bundle(output, samples, manifest, evidence, traces=traces, splits=splits)
    write_samples(Path(output) / "natural-samples.jsonl", natural)
    write_samples(Path(output) / "fault-controls.jsonl", faults)
    return samples
