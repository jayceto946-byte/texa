"""P0 contracts for an isolated, bounded runtime. No provider is enabled here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class RunCommand:
    request_key: str
    request_id: str
    task_id: str
    conversation_id: str
    turn_id: str
    goal: str
    owner_token: str
    budget_calls: int = 1
    budget_model_calls: int = 0
    required_outputs: list[dict[str, Any]] = field(default_factory=list)
    trigger_kind: Literal["user", "ui_action", "goal", "schedule"] = "user"
    trigger_id: str = ""


@dataclass(frozen=True)
class FixedAction:
    kind: Literal["finish", "call"]
    answer: str = ""
    tool_id: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    operation_key: str = ""


@dataclass(frozen=True)
class ModelCapabilities:
    tool_calling: Literal["supported", "unsupported", "unknown"] = "unknown"
    structured_output: Literal["supported", "unsupported", "unknown"] = "unknown"
    streaming: Literal["supported", "unsupported", "unknown"] = "unknown"
    parallel_tool_calls: Literal["supported", "unsupported", "unknown"] = "unknown"
    context_window: int | None = None
    contract_version: str = "p0"


class ModelAdapter(Protocol):
    def capabilities(self) -> ModelCapabilities: ...
    def next_action(self, transcript: list[dict], candidate_tools: tuple[dict, ...]): ...


class RuntimeConflict(RuntimeError):
    pass


class RuntimeDenied(ValueError):
    pass
