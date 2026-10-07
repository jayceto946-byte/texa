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
            "book_id": str(value.get("book_id") or "").strip()[:100],
            "book_name": str(value.get("book_name") or "").strip()[:200],
            "corpus_version": str(value.get("corpus_version") or "").strip()[:100],
            "content_fingerprint": str(value.get("content_fingerprint") or "").strip()[:80],
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
    previous_versions = (
        (latest_assistant or {}).get("context_versions")
        if isinstance((latest_assistant or {}).get("context_versions"), dict)
        else {}
    )
    previous_corpus_version = str(previous_versions.get("corpus_version") or "")
    try:
        from backend.services.context_versions import current_context_versions

        current_corpus_version = str(
            current_context_versions(book_name).get("corpus_version") or ""
        )
    except Exception:
        current_corpus_version = ""
    corpus_version_matches = (
        not previous_corpus_version
        or not current_corpus_version
        or previous_corpus_version == current_corpus_version
    )
    source_versions_match = all(
        not item.get("corpus_version")
        or not current_corpus_version
        or item.get("corpus_version") == current_corpus_version
        for item in sources
    )
    same_scope = (
        (not previous_book or not book_name or previous_book == book_name)
        and (not previous_subject or not subject or previous_subject == subject)
    )
    before_topic = str(before.get("topic") or "").strip()
    after_topic = str(after.get("topic") or "").strip()
    same_topic = (
        bool(resolution_trace.get("is_followup"))
        and same_scope
        and corpus_version_matches
        and source_versions_match
        and bool(before_topic)
        and before_topic == after_topic
    )
    previous_intent = str(before.get("intent") or "")
    current_intent = str(after.get("intent") or "")
    invalidation_reason = ""
    if sources and not same_scope:
        invalidation_reason = "scope_changed"
    elif sources and (not corpus_version_matches or not source_versions_match):
        invalidation_reason = "corpus_version_changed"
    elif sources and not bool(before_topic and before_topic == after_topic):
        invalidation_reason = "topic_changed_or_unresolved"
    elif not sources:
        invalidation_reason = "no_active_evidence"
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
        "previous_corpus_version": previous_corpus_version,
        "current_corpus_version": current_corpus_version,
        "corpus_version_matches": corpus_version_matches,
        "source_versions_match": source_versions_match,
        "active_evidence_scope": {
            "book_name": previous_book,
            "subject": previous_subject,
            "chapters": list(dict.fromkeys(
                str(item.get("chapter") or "") for item in sources if item.get("chapter")
            ))[:12],
        },
        "active_evidence_invalidation_reason": invalidation_reason,
        "book_name": book_name,
        "subject": subject,
    }
