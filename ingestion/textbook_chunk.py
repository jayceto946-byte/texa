"""Canonical textbook chunk model shared by import, retrieval and KG jobs."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any


@dataclass
class TextbookChunk:
    book_name: str
    chapter: str
    section_title: str
    content: str
    chunk_id: str
    chunk_index: int
    page_idx: int = -1
    bbox: list[float] = field(default_factory=list)
    role: str = "reference"
    equations: list[str] = field(default_factory=list)
    source_markdown: str = ""
    block_type: str = "text"
    section_path: list[str] = field(default_factory=list)
    parent_id: str = ""
    parent_content: str = ""
    prev_chunk_id: str = ""
    next_chunk_id: str = ""
    subject: str = ""
    book_role: str = ""
    rag_priority: float = 1.0
    review_status: str = ""

    @classmethod
    def from_source(
        cls,
        source: dict[str, Any],
        *,
        book_name: str,
        chapter: str,
        chunk_index: int,
    ) -> "TextbookChunk | None":
        content = str(source.get("content") or source.get("text") or "").strip()
        if not content:
            return None
        section_title = str(source.get("section_title") or source.get("title") or chapter).strip() or chapter
        page_idx = _int_or(source.get("page_idx"), -1)
        bbox = _bbox(source.get("bbox"))
        equations = _strings(source.get("equations"))
        if not equations:
            equations = _strings(source.get("formula_candidates"))
        role = str(source.get("role") or source.get("semantic_role") or "reference").strip() or "reference"
        block_type = str(source.get("block_type") or source.get("type") or "text").strip() or "text"
        chunk_id = str(source.get("chunk_id") or "").strip()
        if not chunk_id:
            digest_source = json.dumps(
                [book_name, chapter, section_title, page_idx, chunk_index, content[:240]],
                ensure_ascii=False,
            )
            chunk_id = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:20]
        section_path = source.get("section_path")
        if not isinstance(section_path, list):
            section_path = [chapter] if section_title == chapter else [chapter, section_title]
        parent_id = str(source.get("parent_id") or "").strip()
        if not parent_id:
            parent_id = hashlib.sha1(f"{book_name}|{chapter}|{section_title}".encode("utf-8")).hexdigest()[:16]
        return cls(
            book_name=book_name,
            chapter=chapter,
            section_title=section_title,
            content=content,
            chunk_id=chunk_id,
            chunk_index=chunk_index,
            page_idx=page_idx,
            bbox=bbox,
            role=role,
            equations=equations,
            source_markdown=str(source.get("source_markdown") or ""),
            block_type=block_type,
            section_path=[str(value) for value in section_path if str(value).strip()],
            parent_id=parent_id,
            parent_content=str(source.get("parent_content") or content)[:4000],
            prev_chunk_id=str(source.get("prev_chunk_id") or ""),
            next_chunk_id=str(source.get("next_chunk_id") or ""),
            subject=str(source.get("subject") or ""),
            book_role=str(source.get("book_role") or ""),
            rag_priority=_float_or(source.get("rag_priority"), 1.0),
            review_status=str(source.get("review_status") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        path = " > ".join(self.section_path or [self.chapter])
        row["retrieval_text"] = f"Textbook: {self.book_name}\nSection: {path}\nContent: {self.content}"
        return row


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _bbox(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for item in value[:4]:
        try:
            result.append(float(item))
        except (TypeError, ValueError):
            return []
    return result if len(result) == 4 else []


def _int_or(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
