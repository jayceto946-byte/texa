"""Retrieval-action boundary and soft textbook-level retrieval priors.

The policy is applied after relevance fusion and optional cross-encoding. Raw
relevance remains available for debugging, while role changes are read from
book metadata on every request and therefore never require re-indexing.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


RetrievalAction = Literal["none", "reuse", "delta", "full"]
RETRIEVAL_POLICY_VERSION = "evidence-continuity-v2"


def decide_retrieval_action(context: Mapping | None = None) -> RetrievalAction:
    """Choose a conservative evidence-continuity action for the current turn."""
    values = context or {}
    if not bool(values.get("use_textbook_context", True)):
        return "none"
    if scope_changed(values):
        return "full"
    if str(values.get("active_evidence_invalidation_reason") or "") not in {"", "no_active_evidence"}:
        return "full"

    active_ids = [str(value) for value in values.get("active_evidence_ids") or [] if value]
    same_topic = bool(values.get("same_topic"))
    support = str(values.get("active_evidence_support") or "").strip().lower()
    requires_new_facet = bool(values.get("requires_new_facet"))
    if active_ids and same_topic and support in {"supported", "partial"}:
        return "delta" if requires_new_facet or support == "partial" else "reuse"
    return "full"


def scope_changed(context: Mapping | None = None) -> bool:
    values = context or {}
    previous_book = str(values.get("previous_book_name") or "").strip()
    current_book = str(values.get("book_name") or "").strip()
    previous_subject = str(values.get("previous_subject") or "").strip()
    current_subject = str(values.get("subject") or "").strip()
    return bool(
        (previous_book and current_book and previous_book != current_book)
        or (previous_subject and current_subject and previous_subject != current_subject)
    )


def _configured_float(name: str, default: float, *, lower: float, upper: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(lower, min(upper, value))


@dataclass(frozen=True)
class TextbookRetrievalPolicy:
    # These defaults are deliberately mild relative to the existing RRF,
    # literal-coverage and selected-book signals. Set both role multipliers to
    # 1.0 to disable the role prior without touching book metadata or indexes.
    primary_multiplier: float
    supplementary_multiplier: float
    standalone_multiplier: float
    minimum_multiplier: float = 0.85
    maximum_multiplier: float = 1.15
    minimum_book_priority: float = 0.90
    maximum_book_priority: float = 1.10

    def multiplier(self, book_role: str = "", book_priority: object = 1.0) -> float:
        role = str(book_role or "").strip().lower()
        role_multiplier = {
            "core": self.primary_multiplier,
            "reference": self.supplementary_multiplier,
        }.get(role, self.standalone_multiplier)
        try:
            priority = float(book_priority if book_priority not in {None, ""} else 1.0)
        except (TypeError, ValueError):
            priority = 1.0
        priority = max(self.minimum_book_priority, min(self.maximum_book_priority, priority))
        return round(max(self.minimum_multiplier, min(self.maximum_multiplier, role_multiplier * priority)), 6)


def textbook_retrieval_policy() -> TextbookRetrievalPolicy:
    return TextbookRetrievalPolicy(
        primary_multiplier=_configured_float(
            "TEXA_PRIMARY_TEXTBOOK_MULTIPLIER", 1.04, lower=0.85, upper=1.15,
        ),
        supplementary_multiplier=_configured_float(
            "TEXA_SUPPLEMENTARY_TEXTBOOK_MULTIPLIER", 0.98, lower=0.85, upper=1.15,
        ),
        standalone_multiplier=_configured_float(
            "TEXA_STANDALONE_TEXTBOOK_MULTIPLIER", 1.0, lower=0.85, upper=1.15,
        ),
    )
