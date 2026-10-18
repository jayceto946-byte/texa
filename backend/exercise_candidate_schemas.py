"""Bounded transport types for the optional textbook candidate v1 contract."""
from typing import Literal
from typing_extensions import Annotated
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator


def _version(value):
    if type(value) is not int or value != 1:
        raise ValueError('未知候选合同版本')
    return value


CandidateContractVersion = Annotated[Literal[1], BeforeValidator(_version)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CandidateSpan(ContractModel):
    block_id: str = Field(min_length=1, max_length=256)
    start: int = Field(ge=0)
    end: int | None = Field(default=None, ge=0)


class CandidateParts(ContractModel):
    question: list[CandidateSpan] = Field(max_length=160)
    answer: list[CandidateSpan] = Field(max_length=160)
    explanation: list[CandidateSpan] = Field(max_length=160)
    context: list[CandidateSpan] = Field(max_length=160)
    unassigned: list[CandidateSpan] = Field(max_length=160)


class CandidateScope(ContractModel):
    chapter: str = Field(max_length=1000)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    source_mode: Literal['exercise_sections', 'examples', 'all_pages']


class CandidateDependency(ContractModel):
    id: str = Field(min_length=1, max_length=512)
    kind: Literal['figure', 'table', 'formula', 'prior_context']
    label: str = Field(max_length=1000)
    requirement: Literal['required', 'reference', 'uncertain']
    block_ids: list[str] = Field(max_length=160)
    asset_ids: list[str] = Field(max_length=160)
    resolution: Literal['embedded', 'identified', 'unresolved']


class CandidateProjection(ContractModel):
    version: CandidateContractVersion
    canonical_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    unit_ids: list[str] = Field(min_length=1, max_length=200)
    scope: CandidateScope
    method: Literal['whole_unit', 'block_boundary', 'unresolved', 'user_edited']
    parts: CandidateParts
    dependencies: list[CandidateDependency] = Field(max_length=160)


class CandidateIssue(ContractModel):
    key: str
    category: Literal['content', 'metadata']
    code: str
    block_ids: list[str]
    dependency_id: str | None = None


class CandidateResolution(ContractModel):
    issue_key: str = Field(max_length=2000)
    decision: Literal['corrected', 'not_applicable', 'source_checked']


class CandidateReview(ContractModel):
    content_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    resolutions: list[CandidateResolution] = Field(max_length=200)


class CandidateContext(ContractModel):
    projection: CandidateProjection
    review: CandidateReview | None = None
