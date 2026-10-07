"""Typed bounded query over an injected exercise bank."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from backend.tools.learning_tools import search_exercises
from backend.tools.registry import ToolRegistry, ToolSpec


class SearchExercisesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    book_name: str = Field(min_length=1, max_length=120)
    subject: str = Field(default="", max_length=120)
    query: str = Field(default="", max_length=300)
    chapter: str = Field(default="", max_length=200)
    tag: str = Field(default="", max_length=120)
    status: str = Field(default="", max_length=40)
    limit: int = Field(default=8, ge=1, le=30, strict=True)


class SearchExercisesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    book_name: str
    query: str
    filters: dict[str, Any]
    exercises: list[dict[str, Any]]
    solution_fields_omitted: bool
    searched_record_limit: int
    results_may_be_incomplete: bool


def register_search_exercises_runtime(registry: ToolRegistry, exercise_bank: Any) -> None:
    def handler(context, args):
        result = search_exercises(context, args, exercise_bank=exercise_bank)
        if result.success:
            result.data = {**result.data, "searched_record_limit": 2000,
                           "results_may_be_incomplete": True}
        return result
    registry.register(ToolSpec(name="search_exercises", description="Find existing exercises without solutions",
        parameters=SearchExercisesInput.model_json_schema(), read_only=True, handler=handler,
        runtime_input=SearchExercisesInput, runtime_output=SearchExercisesOutput,
        permission="READ", side_effect="none", source="builtin",
        provenance="exercise_bank", idempotency="read_retryable"))
