"""HTTP request DTOs only; domain contracts live in the Notes capability."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Selection(Request):
    conversation_id: str = Field(min_length=1, max_length=80)
    turn_ids: list[str] | None = None
    through_seq: int | None = Field(default=None, ge=1)


class Preflight(Request):
    selection: Selection
    structure_hint: Literal["auto", "concept", "derivation", "problem", "comparison", "review"] = "auto"
    completed_only: bool = False


class Generation(Request):
    operation_id: str = Field(min_length=1, max_length=100)
    selection: Selection | None = None
    preflight_fingerprint: str | None = None
    structure_hint: Literal["auto", "concept", "derivation", "problem", "comparison", "review"] = "auto"
    retry_of_draft_id: str | None = None


class CreateDraft(Request):
    kind: Literal["edit", "manual"]
    note_id: str | None = None
    base_revision: int | None = None
    snapshot_id: str | None = None


class PatchDraft(Request):
    expected_draft_revision: int = Field(ge=1)
    content: dict


class SaveDraft(Request):
    operation_id: str = Field(min_length=1, max_length=100)
    expected_draft_revision: int = Field(ge=1)
    base_note_revision: int | None = None
    acknowledgement: dict | None = None


class Status(Request):
    operation_id: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)
    status: Literal["active", "archived"]
