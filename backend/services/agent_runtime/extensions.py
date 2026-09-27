"""P4 contract harnesses; no scheduler loop, plugin loader, or MCP connection."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from pydantic import BaseModel

from backend.services.agent_runtime.contracts import RunCommand, RuntimeDenied
from backend.services.agent_runtime.store import RuntimeStore
from backend.tools.registry import ToolContext, ToolRegistry, ToolResult, ToolSpec


@dataclass(frozen=True)
class TriggerCommand:
    trigger_id: str
    goal: str
    owner_token: str
    budget_calls: int = 0


class TriggerIngress:
    def __init__(self, store: RuntimeStore):
        self.store = store

    def submit_fake_schedule(self, command: TriggerCommand) -> dict:
        if not command.trigger_id or len(command.trigger_id) > 160:
            raise ValueError("trigger id is required")
        task_id = f"task_{uuid.uuid5(uuid.NAMESPACE_URL, 'texa-trigger:' + command.trigger_id).hex}"
        return self.store.create(RunCommand(
            request_key=f"schedule:{command.trigger_id}",
            request_id=f"request_{uuid.uuid5(uuid.NAMESPACE_URL, 'texa-request:' + command.trigger_id).hex}",
            task_id=task_id, conversation_id="", turn_id="", goal=command.goal,
            owner_token=command.owner_token, budget_calls=command.budget_calls,
            trigger_kind="schedule", trigger_id=command.trigger_id,
        ))


class ExternalSourceAdapter(Protocol):
    source_id: str
    source_version: str
    def execute(self, tool_id: str, args: dict[str, Any]) -> dict[str, Any]: ...


def register_fake_mcp_read_tool(registry: ToolRegistry, *, adapter: ExternalSourceAdapter,
                                tool_id: str, input_model: type[BaseModel],
                                output_model: type[BaseModel],
                                timeout_seconds: float = 2.0) -> None:
    if not tool_id.startswith("mcp_") or not adapter.source_id or not adapter.source_version:
        raise RuntimeDenied("invalid external tool identity")
    if timeout_seconds <= 0 or timeout_seconds > 8:
        raise RuntimeDenied("external tool timeout exceeds policy")
    def handler(context: ToolContext, args: dict[str, Any]) -> ToolResult:
        if adapter.source_id != source_id or adapter.source_version != source_version:
            raise RuntimeDenied("external source identity changed; registration required")
        availability = getattr(adapter, "is_available", None)
        if availability is not None and not availability():
            raise RuntimeDenied("external source is unavailable")
        data = adapter.execute(tool_id, args)
        return ToolResult(True, data=data, evidence=[{
            "source": adapter.source_id, "version": adapter.source_version,
        }])
    source_id, source_version = adapter.source_id, adapter.source_version
    registry.register(ToolSpec(name=tool_id,
        description="Read from a fake, explicitly bound external source",
        parameters=input_model.model_json_schema(), read_only=True,
        handler=handler, runtime_input=input_model, runtime_output=output_model,
        permission="READ", side_effect="none", source="mcp",
        provenance=f"{adapter.source_id}@{adapter.source_version}",
        idempotency="read_retryable", timeout_seconds=timeout_seconds))
