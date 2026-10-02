"""Runtime-owned deterministic projection and immutable execution bindings."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from backend.services.decision.contracts import DecisionResult
from backend.services.decision.resolver import resolve_candidate_tools
from backend.services.decision.router import matching_capabilities
from backend.services.decision.policy_contracts import (
    canonical_json, PolicyObservationV0, PolicyObservationEnvelope, PreviousResultV0,
)


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True)
class FrozenObservation:
    # JSON strings recursively detach *both* public payload and internal bindings.
    envelope_json: str
    bindings_json: str
    exclusions_json: str

    @property
    def envelope(self):
        return PolicyObservationEnvelope.model_validate(json.loads(self.envelope_json))

    @property
    def bindings(self):
        return json.loads(self.bindings_json)

    @property
    def exclusions(self):
        return json.loads(self.exclusions_json)


def matched_tool_refs(request, registry, *, grounded=False):
    refs, exclusions = [], []
    for capability, _ in matching_capabilities(request, textbook_grounded=grounded):
        result = resolve_candidate_tools(DecisionResult("capability", selected_capability=capability), registry)
        exclusions.extend(result.exclusions)
        for ref in result.tool_refs:
            if ref not in refs:
                refs.append(ref)
    return tuple(refs), exclusions


def tool_binding_signature(refs, registry):
    bindings = []
    for ref in refs:
        try:
            meta = registry.runtime_tool(ref["id"]).runtime_metadata()
            current = {key: meta[key] for key in ("version", "schema_hash", "permission", "source", "side_effect")}
        except (KeyError, ValueError):
            current = "unavailable_or_noncanonical"
        bindings.append({"ref": ref, "current": current})
    return bindings


def previous_result(calls) -> PreviousResultV0 | None:
    completed = [call for call in calls if call["status"] in {"succeeded", "failed", "unknown"}]
    if not completed:
        return None
    call = completed[-1]
    result = call.get("result") or {}
    data = result.get("data") or {}
    flags = []
    if call["status"] != "succeeded":
        flags.append("execution_failed_or_unknown:" + str(call.get("error_code") or "unknown"))
    for field in ("exercises", "evidence_items", "recent_events"):
        if field in data:
            flags.append(f"{field}_count={len(data[field])}")
            if not data[field]:
                flags.append("empty_result")
    if data.get("window_complete") is False or data.get("results_may_be_incomplete"):
        flags.append("coverage_incomplete")
    if data.get("evidence_support", {}).get("status") in {"insufficient", "unavailable"}:
        flags.append("evidence_insufficient")
    return PreviousResultV0(action_kind="call_tool", tool_id=call["tool_id"], status=call["status"],
                            summary=(";".join(flags) or "bounded_result_available")[:600])


def project_observation(*, request, resolved_query, registry, context, identity,
                        candidate_tools=(), snapshot=None, answer_state=None,
                        missing_inputs=(), gate=False, goal=None, constraints=None) -> FrozenObservation:
    """Only Runtime gates, canonical binders and facts generate candidates."""
    state = answer_state or {}
    calls = (snapshot or {}).get("tool_calls", [])
    constraints = {**(constraints or {}), "book_name": context.book_name, "subject": context.subject,
                   **({"answer_mode": state["answer_mode"]} if "answer_mode" in state else {})}
    actions, bindings, exclusions = [], {}, []
    blocking = [item for item in missing_inputs if item.get("blocking", True) and item.get("status", "missing") == "missing"]
    def add(kind, args, internal):
        action_id = f"a{len(actions)}"
        actions.append({"id": action_id, "kind": kind, "args": args})
        bindings[action_id] = {"kind": kind, "args": args, **internal}
    if snapshot and (snapshot["run"]["status"] != "running" or snapshot["task"]["status"] != "running"):
        exclusions.append({"reason": "inactive_execution_boundary"})
    elif blocking:
        if gate:
            add("request_input", {}, {"missing_inputs": blocking})
        else:
            exclusions.append({"reason": "sql_input_gate_unsupported"})
    else:
        scope = state.get("_runtime_textbook_scope")
        scope_valid = True
        if scope:
            try:
                check = registry.runtime_tool("search_textbook").runtime_scope_check
                if check:
                    check(context, {"query": resolved_query, "chapter": ""})
            except (KeyError, ValueError):
                scope_valid = False
                exclusions.append({"reason": "textbook_scope_or_index_changed"})
        for ref in candidate_tools:
            tool_id = ref["id"]
            try:
                if scope and not scope_valid:
                    raise ValueError("scope_conflict")
                spec = registry.runtime_tool(tool_id)
                meta = spec.runtime_metadata()
                if not spec.read_only or meta["permission"] != "READ" or meta["source"] != "builtin" or meta["side_effect"] not in {"none", "derived_cache"}:
                    raise ValueError("permission_or_source")
                if (meta["version"], meta["schema_hash"]) != (ref["version"], ref["schema_hash"]):
                    raise ValueError("version_or_schema_changed")
                if snapshot and snapshot["consumed_calls"] >= snapshot["budget_calls"]:
                    raise ValueError("tool_budget")
                # This V0 never retries, including calls interrupted on an older run.
                if any(call["tool_id"] == tool_id for call in calls) or any(b.get("args", {}).get("tool_id") == tool_id for b in bindings.values()):
                    raise ValueError("duplicate_or_retry")
                if tool_id == "get_recent_progress":
                    args = {"book_name": context.book_name, "subject": context.subject, "days": 7, "limit": 12}
                elif tool_id == "search_exercises" and context.book_name:
                    args = {"book_name": context.book_name, "subject": context.subject, "query": resolved_query[:300], "limit": 8}
                elif tool_id == "search_textbook" and scope:
                    if scope["book_name"] != context.book_name or scope["subject"] != context.subject:
                        raise ValueError("scope_conflict")
                    args = {"query": resolved_query, "chapter": ""}
                else:
                    raise ValueError("parameters_not_bindable")
                args = spec.runtime_input.model_validate(args).model_dump()
                if spec.runtime_scope_check:
                    spec.runtime_scope_check(context, args)
                for field in ("book_name", "subject"):
                    if args.get(field) and args[field] != getattr(context, field):
                        raise ValueError("scope_conflict")
                add("call_tool", {"tool_id": tool_id, "input": args}, {"tool_ref": ref, "scope": scope})
            except (KeyError, ValueError) as exc:
                exclusions.append({"tool_id": tool_id, "reason": str(exc)[:120]})
        can_answer = not state.get("use_textbook_context", False)
        if not can_answer:
            from graph.generator import has_textbook_evidence
            can_answer = has_textbook_evidence(state) or any(
                call["tool_id"] == "search_textbook" and call["status"] == "succeeded"
                and (call.get("result") or {}).get("data", {}).get("query_scope") == scope
                and has_textbook_evidence({**state,
                    "evidence_items": call["result"]["data"].get("evidence_items", []),
                    "evidence_support": call["result"]["data"].get("evidence_support", {})}) for call in calls)
        if snapshot and snapshot["consumed_model_calls"] >= snapshot["budget_model_calls"]:
            can_answer = False
            exclusions.append({"reason": "answer_model_budget"})
        if can_answer and scope_valid:
            add("generate_answer", {}, {"scope": scope,
                "tool_bindings": tool_binding_signature(candidate_tools, registry)})
        else:
            exclusions.append({"reason": "answer_evidence_missing"})
    payload = PolicyObservationV0.model_validate({"request": request[:2000],
        "context": {"resolved_query": resolved_query[:2000], "constraints": constraints,
                    **({"goal": goal[:2000]} if goal and goal != request else {})},
        "previous_result": previous_result(calls), "missing_inputs": blocking[:20], "admissible_actions": actions})
    observation_id = "obs_" + digest({"identity": identity, "payload": payload.model_dump(exclude_none=True), "bindings": bindings})
    envelope = PolicyObservationEnvelope(observation_id=observation_id, payload=payload)
    return FrozenObservation(envelope.canonical_json(), canonical_json(bindings), canonical_json(exclusions))


def runtime_identity(snapshot):
    run = snapshot["run"]
    return {"task_id": snapshot["task"]["id"], "run_id": run["id"], "request_id": run["request_id"],
            "task_revision": snapshot["task_revision"], "run_revision": run["revision"],
            "position": {"tool_calls": [(c["id"], c["status"]) for c in snapshot["tool_calls"]],
                         "model_calls": snapshot["consumed_model_calls"], "run_status": run["status"]}}
