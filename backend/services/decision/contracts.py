"""Capability decisions are separate from concrete tools and session resolution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

DomainCapability = str


@dataclass(frozen=True)
class DecisionContext:
    request_id: str
    text: str
    resolved_query: str
    answer_mode: str
    route: str = "learning"
    subject: str = ""
    book_ids: tuple[str, ...] = ()
    attachments: tuple[str, ...] = ()
    explicit_action: str = ""
    current_task_status: str = ""
    required_inputs: tuple[str, ...] = ()
    resolution_status: str = "resolved"
    allowed_permissions: frozenset[str] = frozenset({"READ"})
    context_version: str = "1"


@dataclass(frozen=True)
class SemanticCandidate:
    capability_id: DomainCapability
    raw_score: float
    rank: int
    score_kind: str = "similarity"


@dataclass(frozen=True)
class SemanticRanking:
    candidates: tuple[SemanticCandidate, ...]
    backend_id: str
    backend_version: str
    abstained: bool = False


class SemanticRouterBackend(Protocol):
    def rank(self, context: DecisionContext, candidates: tuple[DomainCapability, ...]) -> SemanticRanking: ...


class FallbackRouterBackend(Protocol):
    def choose(self, context: DecisionContext, candidates: tuple[DomainCapability, ...]) -> DomainCapability | None: ...


@dataclass(frozen=True)
class DecisionResult:
    mode: Literal["direct_answer", "capability", "clarify", "unsupported"]
    selected_capability: DomainCapability = ""
    action_intent: str = ""
    reason_codes: tuple[str, ...] = ()
    rule_match: str = ""
    semantic_candidates: tuple[SemanticCandidate, ...] = ()
    confidence_kind: str = "deterministic"
    backend_id: str = "rules"
    backend_version: str = "1"
    fallback_used: bool = False
    shadow_only: bool = False


@dataclass(frozen=True)
class DomainCapabilitySpec:
    id: DomainCapability
    version: str
    action_intents: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    allowed_permissions: frozenset[str] = frozenset({"READ"})
    enabled: bool = True


@dataclass(frozen=True)
class CandidateToolSet:
    capability_id: DomainCapability
    tool_refs: tuple[dict, ...] = ()
    exclusions: tuple[dict, ...] = ()
    budget: int = 0
