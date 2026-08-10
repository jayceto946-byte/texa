"""Build bounded per-turn evidence continuity input from persisted chat history."""
from __future__ import annotations

import re
from typing import Any


_REPHRASE_PATTERNS = (
    r"再(?:简要|简单|重新)?(?:解释|说明|讲|说)",
    r"换(?:个|一种)?说法",
    r"重新(?:解释|说明|计算|算)",
    r"再(?:计算|算)(?:一遍|一次)",
)


def _bounded_sources(values: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list) else []:
        if not isinstance(value, dict):
            continue
        chunk_id = str(value.get("chunk_id") or "").strip()[:160]
        if not chunk_id or chunk_id in seen:
            continue
        raw_path = value.get("section_path")
        section_path = list(raw_path)[:8] if isinstance(raw_path, (list, tuple)) else []
        result.append({
            "chunk_id": chunk_id,
            "book_name": str(value.get("book_name") or "").strip()[:200],
            "chapter": str(value.get("chapter") or "").strip()[:300],
            "section_title": str(value.get("section_title") or "").strip()[:300],
            "section_path": section_path,
            "chunk_index": value.get("chunk_index", -1),
            "page_idx": value.get("page_idx", -1),
        })
        seen.add(chunk_id)
        if len(result) >= 12:
            break
    return result


def _requires_new_facet(raw_query: str, previous_intent: str, current_intent: str) -> bool:
    compact = re.sub(r"\s+", "", raw_query or "")
    if any(re.search(pattern, compact) for pattern in _REPHRASE_PATTERNS):
        return False
    if previous_intent and current_intent and previous_intent == current_intent:
        return False
    return current_intent not in {"", "qa", "explanation"} or (
        bool(previous_intent) and bool(current_intent) and previous_intent != current_intent
    )


def build_evidence_continuity_context(
    history: list[dict],
    resolution_trace: dict,
    *,
    book_name: str = "",
    subject: str = "",
) -> dict[str, Any]:
    """Describe whether the previous answer evidence can safely carry forward."""
    # Only the immediately preceding assistant answer may donate evidence.
    # Skipping over an ungrounded answer would silently resurrect stale chunks.
    latest_assistant = next((
        item for item in reversed(history) if item.get("role") == "assistant"
    ), None)
    sources = _bounded_sources((latest_assistant or {}).get("sources"))
    before = resolution_trace.get("state_before") if isinstance(resolution_trace, dict) else {}
    after = resolution_trace.get("state_after") if isinstance(resolution_trace, dict) else {}
    before = before if isinstance(before, dict) else {}
    after = after if isinstance(after, dict) else {}
    previous_book = str((latest_assistant or {}).get("book_name") or "").strip()
    previous_subject = str((latest_assistant or {}).get("subject") or "").strip()
    same_scope = (
        (not previous_book or not book_name or previous_book == book_name)
        and (not previous_subject or not subject or previous_subject == subject)
    )
    before_topic = str(before.get("topic") or "").strip()
    after_topic = str(after.get("topic") or "").strip()
    same_topic = (
        bool(resolution_trace.get("is_followup"))
        and same_scope
        and bool(before_topic)
        and before_topic == after_topic
    )
    previous_intent = str(before.get("intent") or "")
    current_intent = str(after.get("intent") or "")
    return {
        "active_evidence_sources": sources,
        "active_evidence_ids": [item["chunk_id"] for item in sources],
        "active_evidence_support": (
            str((latest_assistant or {}).get("evidence_support_status") or "supported")
            if sources else ""
        ),
        "same_topic": same_topic,
        "requires_new_facet": _requires_new_facet(
            str(resolution_trace.get("raw_query") or ""),
            previous_intent,
            current_intent,
        ),
        "previous_intent": previous_intent,
        "previous_book_name": previous_book,
        "previous_subject": previous_subject,
        "book_name": book_name,
        "subject": subject,
    }
