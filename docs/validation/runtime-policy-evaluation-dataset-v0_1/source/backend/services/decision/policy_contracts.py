"""Frozen V0 selection wire contract. No execution authority lives here."""
from __future__ import annotations

import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

CONTRACT_VERSION = "texa.runtime-policy/v0"
ActionKind = Literal["generate_answer", "call_tool", "request_input"]


class StrictV0(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    def canonical_json(self) -> str:
        return canonical_json(self.model_dump(exclude_none=True))


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class CallToolArgsV0(StrictV0):
    tool_id: str = Field(min_length=1, max_length=120)
    input: dict[str, JsonValue]


class PolicyActionV0(StrictV0):
    id: str = Field(min_length=1, max_length=80)
    kind: ActionKind
    args: CallToolArgsV0 | dict[str, JsonValue]

    @model_validator(mode="after")
    def check_args(self):
        if self.kind == "call_tool":
            if not isinstance(self.args, CallToolArgsV0):
                self.args = CallToolArgsV0.model_validate(self.args)
        elif self.args != {}:
            raise ValueError("non-tool actions require empty args")
        return self


class PreviousResultV0(StrictV0):
    action_kind: ActionKind
    tool_id: str | None = Field(default=None, min_length=1, max_length=120)
    status: Literal["succeeded", "failed", "unknown"]
    summary: str = Field(max_length=600)

    @model_validator(mode="after")
    def check_tool(self):
        if (self.action_kind == "call_tool" and self.tool_id is None) or (self.action_kind != "call_tool" and self.tool_id is not None):
            raise ValueError("tool_id is required only for call_tool")
        return self


class PolicyContextV0(StrictV0):
    resolved_query: str = Field(max_length=2000)
    goal: str | None = Field(default=None, max_length=2000)
    constraints: dict[str, JsonValue]


class PolicyObservationV0(StrictV0):
    request: str = Field(max_length=2000)
    context: PolicyContextV0
    previous_result: PreviousResultV0 | None = None
    missing_inputs: list[dict[str, JsonValue]] = Field(max_length=20)
    admissible_actions: list[PolicyActionV0] = Field(max_length=4)

    @model_validator(mode="after")
    def unique_actions(self):
        if self.context.goal == self.request:
            raise ValueError("goal must not repeat request")
        ids = [item.id for item in self.admissible_actions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate candidate ID")
        return self


class PolicyDecisionV0(StrictV0):
    action_id: str = Field(min_length=1, max_length=80)


def parse_decision(value) -> PolicyDecisionV0:
    """Reject duplicate keys, protocol prose, coercion and extra fields."""
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate decision key")
            result[key] = item
        return result
    if isinstance(value, PolicyDecisionV0):
        value = value.model_dump()
    if isinstance(value, str):
        value = json.loads(value, object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    return PolicyDecisionV0.model_validate(value)


class PolicyValidationV0(StrictV0):
    status: Literal["accepted", "rejected"]
    code: str = Field(min_length=1, max_length=80)


class PolicyOutcomeV0(StrictV0):
    decision_ref: str = Field(min_length=1)
    validation: PolicyValidationV0
    execution: Literal["not_started", "succeeded", "failed", "unknown"]
    result_refs: list[str] = Field(default_factory=list, max_length=20)
    continuation: Literal["next_observation", "waiting", "terminal"]
    task_status: Literal["pending", "running", "interrupted", "waiting_for_input", "waiting_for_confirmation", "completed", "degraded", "failed", "cancelled"]
    user_feedback: Literal["positive", "negative", "unknown"] = "unknown"
    goal_completion: Literal["met", "not_met", "unknown"] = "unknown"

    @model_validator(mode="after")
    def rejected_cannot_execute(self):
        if self.validation.status == "rejected" and self.execution != "not_started":
            raise ValueError("rejected decisions cannot execute")
        return self


class PolicyObservationEnvelope(StrictV0):
    observation_id: str = Field(min_length=1)
    policy_contract_version: Literal["texa.runtime-policy/v0"] = CONTRACT_VERSION
    payload: PolicyObservationV0
