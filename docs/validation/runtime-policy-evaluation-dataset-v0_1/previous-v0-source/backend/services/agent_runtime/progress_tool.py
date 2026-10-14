"""The sole P0 Runtime tool, backed by an injected learning-event store."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from backend.tools.registry import ToolContext, ToolRegistry, ToolResult, ToolSpec
from backend.tools.learning_tools import get_recent_progress


class RecentProgressInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    book_name: str = Field(default="", max_length=120)
    subject: str = Field(default="", max_length=120)
    days: int = Field(default=7, ge=1, le=31, strict=True)
    limit: int = Field(default=12, ge=1, le=50, strict=True)


class RecentProgressOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    book_name: str
    subject: str
    range_days: int
    summary: dict[str, Any]
    top_concepts: list[dict[str, Any]]
    recent_events: list[dict[str, Any]]
    queried_event_limit: int
    window_complete: bool
    coverage_note: str


def register_recent_progress_runtime(registry: ToolRegistry, event_store: Any) -> None:
    """Register on a caller-owned registry so tests cannot read real progress."""
    def handler(context: ToolContext, args: dict[str, Any]) -> ToolResult:
        result = get_recent_progress(context, args, event_store=event_store)
        if result.success:
            queried = max(200, args.get("limit", 12) * 10)
            result.data = {**result.data, "queried_event_limit": queried,
                           "window_complete": False,
                           "coverage_note": "Counts cover only the bounded queried sample; the full date window may contain more events."}
        return result

    registry.register(ToolSpec(
        name="get_recent_progress", description="Read a bounded sample of learning activity.",
        parameters=RecentProgressInput.model_json_schema(), read_only=True,
        handler=handler, runtime_input=RecentProgressInput,
        runtime_output=RecentProgressOutput, permission="READ",
        side_effect="none", source="builtin", idempotency="read_retryable",
        provenance="learning_events", timeout_seconds=8.0,
    ))
