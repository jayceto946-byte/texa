"""Bounded source contract for the existing verify_math_result tool.

Only a user-authored, leading structured block is interpreted as mathematical
premises. Prose/OCR/assistant assertions never acquire authority by substring.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Statement(StrictModel):
    left: str = Field(min_length=1, max_length=300)
    right: str | None = Field(default=None, max_length=300)


DomainPredicate = Literal['real', 'positive', 'nonnegative', 'negative', 'nonpositive', 'nonzero', 'integer']


class Problem(StrictModel):
    variable: str = Field(max_length=32)
    domain: DomainPredicate
    parameters: dict[str, DomainPredicate] = Field(default_factory=dict, max_length=8)
    conditions: list[str] = Field(default_factory=list, max_length=8)
    premise: Statement

    @field_validator('variable')
    @classmethod
    def symbol(cls, value):
        from backend.tools.math_tools import _symbol_name
        return _symbol_name(value)

    @field_validator('parameters')
    @classmethod
    def parameter_symbols(cls, value):
        from backend.tools.math_tools import _symbol_name
        normalized = {_symbol_name(name): predicate for name, predicate in value.items()}
        if len(normalized) != len(value):
            raise ValueError('duplicate parameter aliases')
        return normalized

    @model_validator(mode='after')
    def separate_variable(self):
        if self.variable in self.parameters:
            raise ValueError('variable cannot also be a parameter')
        return self


StepRelation = Literal['identity', 'implication', 'equation_equivalence', 'candidate_solution', 'solution_set']


class MathStep(StrictModel):
    id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,23}$')
    depends_on: list[str] = Field(default_factory=list, max_length=4)
    before: Statement
    after: Statement | None = None
    relation: StepRelation
    candidates: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode='after')
    def shape(self):
        if self.relation in {'candidate_solution', 'solution_set'}:
            if self.before.right is None or self.after is not None:
                raise ValueError('solution checks require one source equation and candidates')
        elif self.after is None or self.candidates:
            raise ValueError('transformation requires before/after, without candidates')
        if self.relation == 'identity' and (self.before.right is not None or self.after.right is not None):
            raise ValueError('identity checks expressions; use equation_equivalence for equations')
        if self.relation in {'implication', 'equation_equivalence'} and (self.before.right is None or self.after.right is None):
            raise ValueError('equation relation requires two equations')
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError('duplicate dependencies')
        return self


class StepBatch(StrictModel):
    source_ref: str = Field(min_length=1, max_length=80)
    steps: list[MathStep] = Field(min_length=1, max_length=4)

    @model_validator(mode='after')
    def unique_ids(self):
        if len({s.id for s in self.steps}) != len(self.steps):
            raise ValueError('duplicate step ids')
        return self


class StepReceipt(StrictModel):
    id: str
    verdict: Literal['valid', 'invalid', 'unknown']
    relation: StepRelation
    depends_on: list[str]
    before: Statement
    after: Statement | None
    candidates: list[str]
    checked: list[str]
    not_checked: list[str]
    counterexample: str | None
    scope: str
    applicable_conditions: list[str]


def freeze_problem(question: str) -> dict:
    """Runtime-only projection of the frozen user request, never tool arguments.

    A version change is a different SHA. The current user-confirmed request is
    the sole source; older ledger/assistant/model assumptions cannot override it.
    """
    ref = 'request:' + hashlib.sha256(question.encode()).hexdigest()
    result = {'source_ref': ref, 'source_kind': 'frozen_user_request', 'problem': None}
    match = re.match(r'\A<math-context>\s*([\s\S]{1,4000}?)\s*</math-context>(?:\s|$)', question)
    # A prose tail may change/negate a condition. Until there is a trusted
    # condition-confirmation UI, accept only a bare verification request tail.
    # Never pick a convenient structured subset of a conflicting user question.
    safe_requests = {'', '验算', '验算。', '核验。', '验证。', '求解。', '化简。',
                     '解释。', '解释化简步骤。', '核验关键步骤并解释。'}
    if match and question[match.end():].strip() in safe_requests:
        try:
            def unique(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError('duplicate source key')
                    value[key] = item
                return value
            result['problem'] = Problem.model_validate(json.loads(match[1], object_pairs_hook=unique)).model_dump()
        except (ValueError, TypeError):
            pass  # Unknown source, never interpret a partial malformed block.
    return result
