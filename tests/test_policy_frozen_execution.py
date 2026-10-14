"""Historical source execution and current production evolution stay separate."""
from pathlib import Path
import json

import pytest

from evaluation.policy_dataset_v0.baseline import DEFAULT_DATASET, FROZEN_SOURCE_ROOT
from evaluation.policy_dataset_v0.frozen_runtime import frozen_module
from evaluation.policy_dataset_v0.validation import validate_manifest


def test_math_capability_exists_only_in_current_resolver():
    from backend.services.decision.contracts import DecisionResult
    from backend.services.decision.resolver import resolve_candidate_tools
    from backend.services.agent_runtime.chat_binding import build_math_registry
    registry = build_math_registry()
    decision = DecisionResult("capability", selected_capability="math.verify")
    current = resolve_candidate_tools(decision, registry)
    historical = frozen_module("backend.services.decision.resolver").resolve_candidate_tools(decision, registry)
    assert [ref["id"] for ref in current.tool_refs] == ["symbolic_math", "verify_math_result"]
    assert historical.tool_refs == ()


def test_registry_defaults_preserve_current_and_historical_interfaces():
    from backend.tools.registry import ToolContext, ToolSpec
    original = frozen_module("backend.tools.registry")
    assert ToolContext("book", "math", "session").timeout_seconds == 5.0
    assert ToolContext().cancelled is None
    assert ToolSpec.__dataclass_fields__["execution_mode"].default == "thread"
    assert "cancelled" not in original.ToolContext.__dataclass_fields__
    assert "execution_mode" not in original.ToolSpec.__dataclass_fields__


def test_seed_execution_never_calls_poisoned_live_resolver_or_projection(monkeypatch):
    from backend.services.decision import resolver, policy_projection
    from evaluation.policy_dataset_v0.seed_production import SeedRecipeV0, project_recipe
    from evaluation.policy_dataset_v0.evaluator import rule_policy_adapter
    from backend.services.decision import policy
    def live_call(*args, **kwargs):
        pytest.fail("historical execution must not use current production functions")
    monkeypatch.setattr(resolver, "resolve_candidate_tools", live_call)
    monkeypatch.setattr(policy_projection, "project_observation", live_call)
    monkeypatch.setattr(policy_projection, "matched_tool_refs", live_call)
    monkeypatch.setattr(policy, "RulePolicyV0", live_call)
    recipe = SeedRecipeV0(sample_id="isolation", source_family_id="isolation", source_ref="synthetic/isolation",
                          request="查询最近学习进度", resolved_query="查询最近学习进度")
    observation, _ = project_recipe(recipe)
    assert observation.admissible_actions[0].args.tool_id == "get_recent_progress"
    assert rule_policy_adapter(observation).action_id == observation.admissible_actions[0].id
    projection = frozen_module("backend.services.decision.policy_projection")
    assert Path(projection.project_observation.__code__.co_filename).is_relative_to(FROZEN_SOURCE_ROOT)


@pytest.mark.parametrize("source", ["backend/services/decision/resolver.py", "backend/tools/registry.py"])
def test_corrupt_frozen_bytes_fail_even_after_module_is_cached(source, monkeypatch):
    frozen_module("backend.services.decision.resolver")
    original = Path.read_bytes
    def corrupt(path):
        raw = original(path)
        return raw + b"corrupt" if path == FROZEN_SOURCE_ROOT / source else raw
    monkeypatch.setattr(Path, "read_bytes", corrupt)
    manifest = json.loads((DEFAULT_DATASET / "manifest.json").read_text())
    assert "source_content_digest_mismatch" in validate_manifest(manifest)[1]
    with pytest.raises(ValueError, match="source_content_digest_mismatch"):
        frozen_module("backend.services.decision.resolver")


def test_grounded_historical_projection_checks_original_evidence_helper(monkeypatch):
    from evaluation.policy_dataset_v0.seed_production import SeedRecipeV0, project_recipe
    original = Path.read_text
    def corrupt(path, *args, **kwargs):
        text = original(path, *args, **kwargs)
        return text.replace("return True", "return False") if path.name == "evidence_helper_v01.py" else text
    monkeypatch.setattr(Path, "read_text", corrupt)
    recipe = SeedRecipeV0(sample_id="grounded", source_family_id="grounded", source_ref="synthetic/grounded",
                          request="解释连续", resolved_query="解释连续", book_name="book", answer_mode="textbook_grounded")
    with pytest.raises(ValueError, match="reviewed evidence helper changed"):
        project_recipe(recipe)
