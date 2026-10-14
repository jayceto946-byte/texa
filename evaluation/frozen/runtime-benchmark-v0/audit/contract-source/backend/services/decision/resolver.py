"""Map a capability to a small, validated candidate set from the one registry."""
from __future__ import annotations

from backend.services.decision.contracts import CandidateToolSet, DecisionResult
from backend.tools.registry import ToolRegistry

_CAPABILITY_TO_TOOLS = {
    "textbook.search": ("search_textbook",),
    "learning.inspect": ("get_recent_progress",),
    "exercise.inspect": ("search_exercises",),
    "exercise.create_set": ("get_recent_progress", "search_exercises", "create_exercise_set"),
    "mistake.manage": ("save_mistake", "update_mistake"),
    "exercise.record_result": ("record_result",),
}


def resolve_candidate_tools(decision: DecisionResult, registry: ToolRegistry,
                            *, allowed_permissions: frozenset[str] = frozenset({"READ"}),
                            max_tools: int = 3) -> CandidateToolSet:
    if decision.mode != "capability":
        return CandidateToolSet(decision.selected_capability)
    refs, exclusions = [], []
    for name in _CAPABILITY_TO_TOOLS.get(decision.selected_capability, ()):
        try:
            meta = registry.runtime_tool(name).runtime_metadata()
        except (KeyError, ValueError):
            exclusions.append({"tool_id": name, "reason": "unavailable_or_noncanonical"})
            continue
        if meta["permission"] not in allowed_permissions or meta["source"] != "builtin":
            exclusions.append({"tool_id": name, "reason": "permission_or_source"})
            continue
        refs.append({"id": meta["id"], "version": meta["version"],
                     "schema_hash": meta["schema_hash"]})
    if len(refs) > max_tools:
        exclusions.extend({"tool_id": item["id"], "reason": "candidate_budget"} for item in refs[max_tools:])
        refs = refs[:max_tools]
    return CandidateToolSet(decision.selected_capability, tuple(refs), tuple(exclusions), max_tools)
