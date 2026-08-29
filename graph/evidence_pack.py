"""Build one bounded, deduplicated evidence block for answer generation."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


DEFAULT_CHAR_BUDGET = 9000
MAX_ITEM_CHARS = 1800
_PER_CHAPTER_LIMITS = {
    "factual_recall": 6,
    "derivation": 4,
    "calculation": 4,
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


def _section_path(item: dict) -> list[str]:
    """Return the location hierarchy already present in the index metadata."""
    raw_path = item.get("section_path")
    if isinstance(raw_path, str):
        try:
            decoded = json.loads(raw_path)
            raw_path = decoded if isinstance(decoded, list) else []
        except (TypeError, ValueError):
            raw_path = []
    if not isinstance(raw_path, (list, tuple)):
        raw_path = []

    parts: list[str] = []
    for value in raw_path:
        part = _normalized_text(str(value or ""))
        if part and part not in parts:
            parts.append(part)

    chapter = _normalized_text(str(item.get("chapter") or ""))
    section = _normalized_text(str(item.get("section_title") or ""))
    if chapter and chapter not in parts:
        parts.insert(0, chapter)
    if section and section not in parts:
        parts.append(section)
    return parts


def _heading_level(path: list[str]) -> int:
    """Expose a best-effort level without inventing missing parent headings."""
    if not path:
        return 0
    title = path[-1]
    if len(path) == 1 or re.match(r"^第.+章(?:\s|$)", title):
        return 1
    if re.match(r"^第.+节(?:\s|$)", title):
        return 2
    if re.match(r"^[一二三四五六七八九十百]+[、．.]", title):
        return 3
    if re.match(r"^[（(][一二三四五六七八九十百]+[）)]", title):
        return 4
    return len(path)


def _source_label(item: dict) -> str:
    page = item.get("page_idx", -1)
    role = str(item.get("book_role") or "")
    book_label = str(item.get("book_name") or "").strip()
    if not book_label:
        book_label = "\u4e3b\u8981\u6559\u6750" if role == "core" else ("\u8f85\u52a9\u6559\u6750" if role == "reference" else "\u6559\u6750")
    path = _section_path(item)
    location = " / ".join(path)
    parts = [f"{book_label}\u00b7{location}" if location else book_label]
    if isinstance(page, (int, float)) and page >= 0:
        parts.append(f"p.{int(page) + 1}")
    return " / ".join(part for part in parts if part)


def _content_fingerprint(text: str) -> str:
    normalized = _normalized_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24] if normalized else ""


def _selected_candidates(
    evidence_items: list[dict],
    intent: str,
) -> tuple[list[dict], int]:
    per_chapter_limit = _PER_CHAPTER_LIMITS.get(intent, 2)
    return list(evidence_items or []), per_chapter_limit


def build_evidence_pack(
    evidence_items: list[dict],
    chapter_contents: dict[str, list[str]],
    *,
    intent: str = "",
    char_budget: int = DEFAULT_CHAR_BUDGET,
) -> dict[str, Any]:
    """Purely format ranked evidence with intent-aware chapter and character limits."""
    budget = max(3000, min(int(char_budget), 20000))
    candidates, per_chapter_limit = _selected_candidates(evidence_items, intent)
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
        evidence_id = f"E{len(included) + 1}"
        # LLM 只看到稳定的证据编号；human-readable 元数据只保留在 included 中供 UI/程序使用。
        separator_cost = 9 if lines else 0
        remaining = budget - used - len(evidence_id) - 3 - separator_cost
        if remaining <= 120:
            break
        clipped = text[: min(MAX_ITEM_CHARS, remaining)]
        line = f"[{evidence_id}]\n{clipped}"
        lines.append(line)
        used += len(line) + separator_cost
        included.append({
            "id": evidence_id,
            "chunk_id": chunk_id,
            "book_name": str(item.get("book_name") or ""),
            "book_id": str(item.get("book_id") or ""),
            "corpus_version": str(item.get("corpus_version") or ""),
            "provenance_schema": str(item.get("provenance_schema") or ""),
            "index_version": str(item.get("index_version") or ""),
            "content_fingerprint": _content_fingerprint(text),
            "chapter": chapter,
            "section_title": str(item.get("section_title") or ""),
            "section_path": _section_path(item),
            "chunk_index": item.get("chunk_index", -1),
            "heading_level": _heading_level(_section_path(item)),
            "page_idx": item.get("page_idx", -1),
            "page_start": item.get("page_start"),
            "page_end": item.get("page_end"),
            "source_block_ids": list(item.get("source_block_ids") or []),
            "source_locations": list(item.get("source_locations") or []),
            "source_kind": str(item.get("source_kind") or ""),
            "source_file": str(item.get("source_file") or ""),
            "bbox": list(item.get("bbox") or []),
            "figure_id": str(item.get("figure_id") or ""),
            "label": label,
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
