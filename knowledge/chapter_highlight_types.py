"""Shared chapter highlight types and constants."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


ProgressCallback = Callable[[str, str, int | None], None]

PROMPT_VERSION = "chapter_highlights_v6_review_friendly"
MAX_SECTION_INPUT_CHARS = 14000
MAX_COMBINE_INPUT_CHARS = 80000


@dataclass
class ChapterRef:
    id: str
    index: int
    title: str
    page: int
    end_page: int | None = None


@dataclass
class SectionRef:
    id: str
    index: int
    title: str
    page: int
    end_page: int | None = None
    is_auxiliary: bool = False
    heading_block_id: str = ''
    level: int = 2
    source_block_ids: list[str] = field(default_factory=list)


class ChapterHighlightError(RuntimeError):
    """Raised when highlight generation cannot continue."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _url_quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")
