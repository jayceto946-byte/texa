"""Reviewed V0.1 source baseline; V0 JSON contracts and provisional gold remain unchanged.

Fixed repository paths only. An input manifest cannot choose its own approval
record or approve changed source bytes by recomputing hashes.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_VERSION = "runtime-source/v0.1"
DEFAULT_DATASET = REPO_ROOT / "evaluation/fixtures/policy_dataset_v0_1"
APPROVED_SOURCE_MANIFEST = REPO_ROOT / "docs/validation/runtime-policy-evaluation-dataset-v0_1/source-manifest.json"
APPROVED_RUNTIME_VERSION = 'sha256:d6b75d38d73aa04d157bde32b7a7602e20073c35c8438fb90c1d3d984b8d834a'
APPROVED_REGISTRY_VERSION = 'sha256:468a8259856e03d4f63f8e478eebf058467dd05395fae044de2d20aa95ec7013'
RUNTIME_SOURCES = (
    'backend/services/agent_runtime/exercise_tool.py',
    'backend/services/agent_runtime/progress_tool.py',
    'backend/services/agent_runtime/textbook_tool.py',
    'backend/services/decision/policy.py',
    'backend/services/decision/policy_contracts.py',
    'backend/services/decision/policy_projection.py',
    'backend/services/decision/router.py',
    'backend/tools/registry.py',
    'backend/services/decision/contracts.py',
    'backend/services/decision/resolver.py',
    'graph/question_understanding.py',
)
SOURCE_PATHS = (*RUNTIME_SOURCES, "evaluation/policy_dataset_v0/canonical-tools-v0.json")
