"""Canonical proposals for the two receipt-backed local writes enabled in P2b."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.tools.registry import ToolContext, ToolRegistry, ToolResult, ToolSpec


class SaveMistakeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    book_name: str = Field(min_length=1, max_length=120)
    question_text: str = Field(min_length=1, max_length=12000)
    user_answer: str = Field(default="", max_length=6000)
    correct_answer: str = Field(default="", max_length=6000)
    subject: str = Field(default="", max_length=120)
    chapter: str = Field(default="", max_length=200)


class CreatePracticeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    book_name: str = Field(min_length=1, max_length=120)
    exercise_ids: list[str] = Field(min_length=1, max_length=20)
    subject: str = Field(default="", max_length=120)


class ProposalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: str
    payload: dict


class RecordResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    book_name: str = Field(min_length=1, max_length=120)
    session_id: str = Field(min_length=1, max_length=160)
    exercise_id: str = Field(min_length=1, max_length=160)
    user_answer: str = Field(max_length=6000)
    quality: int = Field(ge=0, le=5, strict=True)
    note: str = Field(default="", max_length=2000)


class UpdateMistakeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    book_name: str = Field(min_length=1, max_length=120)
    mistake_id: str = Field(min_length=1, max_length=160)
    expected_revision: int = Field(ge=1, strict=True)
    notes: str = Field(max_length=6000)


def register_receipt_backed_write_tools(registry: ToolRegistry) -> None:
    def save_mistake(context: ToolContext, args: dict) -> ToolResult:
        parsed = SaveMistakeInput.model_validate(args)
        return ToolResult(True, pending_action={"type": "add_mistake", "payload": parsed.model_dump()})

    def create_practice(context: ToolContext, args: dict) -> ToolResult:
        parsed = CreatePracticeInput.model_validate(args)
        return ToolResult(True, pending_action={"type": "create_practice_session", "payload": parsed.model_dump()})

    def record_result(context: ToolContext, args: dict) -> ToolResult:
        return ToolResult(True, pending_action={"type": "record_practice_result", "payload": RecordResultInput.model_validate(args).model_dump()})

    def update_mistake(context: ToolContext, args: dict) -> ToolResult:
        return ToolResult(True, pending_action={"type": "update_mistake", "payload": UpdateMistakeInput.model_validate(args).model_dump()})

    for name, description, input_model, handler in (
        ("save_mistake", "Propose adding a corrected mistake", SaveMistakeInput, save_mistake),
        ("create_exercise_set", "Propose a session from existing exercises", CreatePracticeInput, create_practice),
        ("record_result", "Propose recording the user's answer in an existing session", RecordResultInput, record_result),
        ("update_mistake", "Propose editing notes at a specific mistake revision", UpdateMistakeInput, update_mistake),
    ):
        registry.register(ToolSpec(name=name, description=description,
            parameters=input_model.model_json_schema(), read_only=False, handler=handler,
            runtime_input=input_model, runtime_output=ProposalOutput,
            permission="LOCAL_WRITE", side_effect="domain_write", source="builtin",
            idempotency="domain_operation_key", provenance="user_confirmed_domain_receipt"))
