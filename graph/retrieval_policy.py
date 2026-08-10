"""Explicit retrieval-action boundary used by runtime traces and context evals."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Literal


RetrievalAction = Literal["none", "reuse", "delta", "full"]


def decide_retrieval_action(context: Mapping | None = None) -> RetrievalAction:
    """Choose a conservative evidence-continuity action for the current turn."""
    values = context or {}
    if not bool(values.get("use_textbook_context", True)):
        return "none"
    if scope_changed(values):
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
