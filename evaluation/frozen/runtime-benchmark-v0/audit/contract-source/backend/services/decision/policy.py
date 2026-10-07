"""Pure baseline selection, strict binding validation and fact-only outcomes."""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from backend.services.decision.policy_contracts import (
    PolicyDecisionV0, PolicyOutcomeV0, PolicyValidationV0, parse_decision, canonical_json,
)
from backend.services.decision.policy_projection import digest
from backend.services.decision.router import matching_capabilities

_TOOL_CAPABILITIES = {"search_textbook": "textbook.search", "get_recent_progress": "learning.inspect",
                      "search_exercises": "exercise.inspect"}


def RulePolicyV0(observation) -> PolicyDecisionV0:
    if not observation.admissible_actions:
        raise ValueError("empty candidate set must stay with Runtime")
    ranked = [cap for cap, _ in matching_capabilities(observation.context.resolved_query or observation.request,
                textbook_grounded=observation.context.constraints.get("answer_mode") == "textbook_grounded",
                understanding=observation.context.constraints.get("question_understanding"))]
    def rank(action):
        if action.kind == "request_input":
            return (-1, action.id)
        if action.kind == "call_tool":
            capability = _TOOL_CAPABILITIES.get(action.args.tool_id)
            return (ranked.index(capability) if capability in ranked else len(ranked), action.id)
        return (len(ranked) + 1, action.id)
    return PolicyDecisionV0(action_id=min(observation.admissible_actions, key=rank).id)


class PolicyRejected(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class PolicyValidator:
    @staticmethod
    def validate(frozen, value, current):
        # Changes in identity, payload or frozen binding invalidate even malformed decisions.
        if frozen.envelope.observation_id != current.envelope.observation_id:
            raise PolicyRejected("stale_observation")
        try:
            decision = parse_decision(value)
        except (ValueError, TypeError):
            raise PolicyRejected("invalid_format") from None
        if decision.action_id not in frozen.bindings:
            raise PolicyRejected("unknown_action_id")
        return decision, frozen.bindings[decision.action_id]


@dataclass(frozen=True)
class PolicyAttempt:
    observation_id: str
    decision_ref: str
    source: str
    fallback_of: str | None
    decision: PolicyDecisionV0 | None
    validation: PolicyValidationV0
    duration_ms: float = 0.0
    raw_output: str | None = None  # Test capture only; never included in persisted metadata.

    def metadata(self):
        return {"observation_id": self.observation_id, "decision_ref": self.decision_ref,
                "source": self.source, "fallback_of": self.fallback_of,
                "action_id": self.decision.action_id if self.decision else None,
                "validation": self.validation.model_dump(), "duration_ms": self.duration_ms}


def decision_ref(observation_id, slot):
    return "dec_" + digest([observation_id, slot])


def select_decision(frozen, *, selector=RulePolicyV0, source="rules", current, record):
    """One primary attempt, at most one rules fallback; singleton calls no Policy."""
    observation = frozen.envelope.payload
    if not observation.admissible_actions:
        raise ValueError("empty candidate set must stay with Runtime")
    forced = len(observation.admissible_actions) == 1
    attempts = []
    for slot in ("primary", "fallback"):
        selected_source = "forced" if forced else source if slot == "primary" else "rules"
        started = perf_counter()
        try:
            if forced:
                value = PolicyDecisionV0(action_id=observation.admissible_actions[0].id)
            else:
                # Independent payload for each attempt, never a live binding or envelope.
                value = (selector if slot == "primary" else RulePolicyV0)(frozen.envelope.payload)
        except Exception:
            value = None
        duration_ms = 0.0 if forced else (perf_counter() - started) * 1000
        try:
            raw_output = value if isinstance(value, str) else canonical_json(value.model_dump() if isinstance(value, PolicyDecisionV0) else value)
        except (ValueError, TypeError):
            raw_output = "<invalid non-JSON type>"
        try:
            decision, binding = PolicyValidator.validate(frozen, value, current())
            validation = PolicyValidationV0(status="accepted", code="accepted")
        except PolicyRejected as exc:
            if exc.code == "stale_observation":
                raise  # No old-run trace writes or fallback.
            decision, binding = None, None
            validation = PolicyValidationV0(status="rejected", code=exc.code)
        attempt = PolicyAttempt(frozen.envelope.observation_id,
            decision_ref(frozen.envelope.observation_id, slot), selected_source,
            attempts[0].decision_ref if slot == "fallback" else None, decision, validation, duration_ms, raw_output)
        record(attempt)
        attempts.append(attempt)
        if binding is not None:
            return binding, attempt, attempts
        if forced:
            break
    raise PolicyRejected("fallback_rejected")


def project_outcome(attempt, *, task_status, execution="not_started", result_refs=()):
    return PolicyOutcomeV0(decision_ref=attempt.decision_ref, validation=attempt.validation,
        execution=execution, result_refs=list(result_refs), task_status=task_status,
        continuation="waiting" if task_status in {"waiting_for_input", "waiting_for_confirmation", "interrupted"}
        else "next_observation" if task_status in {"running", "pending"} else "terminal")
