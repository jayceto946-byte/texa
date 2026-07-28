"""Build one bounded, deduplicated evidence block for answer generation."""
from __future__ import annotations

import re
from typing import Any


DEFAULT_CHAR_BUDGET = 9000
MAX_ITEM_CHARS = 1800
_PER_CHAPTER_LIMITS = {
    "factual_recall": 6,
    "derivation": 4,
    "application": 4,
    "comparison": 4,
    "teach": 4,
    "summarize": 4,
    "quiz": 4,
    "qa": 4,
    "definition": 3,
    "formula": 3,
    "property": 3,
    "cross_chapter": 3,
}


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _source_label(item: dict) -> str:
    page = item.get("page_idx", -1)
    role = str(item.get("book_role") or "")
    book_label = str(item.get("book_name") or "").strip()
    if not book_label:
        book_label = "\u4e3b\u8981\u6559\u6750" if role == "core" else ("\u8f85\u52a9\u6559\u6750" if role == "reference" else "\u6559\u6750")
    parts = [
        f"{book_label}\u00b7{item.get('chapter') or ''}",
        str(item.get("section_title") or ""),
    ]
    if isinstance(page, (int, float)) and page >= 0:
        parts.append(f"p.{int(page) + 1}")
    return " / ".join(part for part in parts if part)


def _selected_candidates(
    evidence_items: list[dict],
    chapter_contents: dict[str, list[str]],
    intent: str,
) -> tuple[list[dict], int]:
    per_chapter_limit = _PER_CHAPTER_LIMITS.get(intent, 2)
    selected = list(evidence_items or [])
    if selected:
        return selected, per_chapter_limit

    # Backward-compatible fallback for old indexes and unit-level callers.
    fallback = []
    for chapter, docs in list((chapter_contents or {}).items())[:3]:
        for index, text in enumerate(list(docs or [])[:4]):
            fallback.append({
                "chunk_id": "",
                "chapter": chapter,
                "section_title": "",
                "page_idx": -1,
                "text": text,
                "_fallback_index": index,
            })
    return fallback, max(4, per_chapter_limit)


def build_evidence_pack(
    evidence_items: list[dict],
    chapter_contents: dict[str, list[str]],
    *,
    intent: str = "",
    char_budget: int = DEFAULT_CHAR_BUDGET,
) -> dict[str, Any]:
    """Purely format ranked evidence with intent-aware chapter and character limits."""
    budget = max(3000, min(int(char_budget), 20000))
    candidates, per_chapter_limit = _selected_candidates(evidence_items, chapter_contents, intent)
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    chapter_counts: dict[str, int] = {}
    lines: list[str] = []
    included: list[dict] = []
    used = 0

    for item in candidates:
        text = str(item.get("text") or "")
        normalized = _normalized_text(text)
        if not normalized:
            continue
        chunk_id = str(item.get("chunk_id") or "")
        if chunk_id and chunk_id in seen_ids:
            continue
        if normalized in seen_texts:
            continue
        chapter = str(item.get("chapter") or "")
        if chapter_counts.get(chapter, 0) >= per_chapter_limit:
            continue

        label = _source_label(item)
        separator_cost = 9 if lines else 0
        remaining = budget - used - len(label) - 3 - separator_cost
        if remaining <= 120:
            break
        clipped = text[: min(MAX_ITEM_CHARS, remaining)]
        line = f"[{label}]\n{clipped}"
        lines.append(line)
        used += len(line) + separator_cost
        included.append({
            "chunk_id": chunk_id,
            "chapter": chapter,
            "section_title": str(item.get("section_title") or ""),
            "chars": len(clipped),
        })
        if chunk_id:
            seen_ids.add(chunk_id)
        seen_texts.add(normalized)
        chapter_counts[chapter] = chapter_counts.get(chapter, 0) + 1

    return {
        "text": "\n\n---\n\n".join(lines),
        "items": included,
        "char_count": used,
        "candidate_count": len(candidates),
        "dropped_count": max(0, len(candidates) - len(included)),
        "budget": budget,
    }
