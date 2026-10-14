"""Pure normalization helpers for persisted textbook chapter data."""
from __future__ import annotations

import re


def positive_int(value) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def looks_like_external_ocr_chunk_titles(chapters: list[dict]) -> bool:
    if len(chapters) < 80:
        return False
    external = sum(
        1
        for chapter in chapters[:120]
        if chapter.get("source") == "external_ocr_jsonl"
    )
    one_chunk = sum(
        1
        for chapter in chapters[:120]
        if int(chapter.get("chunk_count") or 0) <= 1
    )
    return external >= 20 and one_chunk >= 60


def chapters_from_ocr_headings(chapters: list[dict]) -> list[dict]:
    result: list[dict] = []
    current: dict | None = None
    chapter_re = re.compile(r"^第\s*[一二三四五六七八九十百千0-9]+\s*章")
    section_re = re.compile(r"^第\s*[一二三四五六七八九十百千0-9]+\s*节")
    for chapter in chapters:
        title = re.sub(r"\s+", " ", str(chapter.get("title") or "")).strip()
        compact = title.replace(" ", "")
        if chapter_re.match(compact):
            current = {
                "title": title,
                "page_number": positive_int(
                    chapter.get("page_number") or chapter.get("page")
                )
                or 1,
                "end_page": chapter.get("end_page"),
                "text": "",
                "subsections": [],
            }
            result.append(current)
            continue
        if current is not None and section_re.match(compact):
            current.setdefault("subsections", []).append({
                "title": title,
                "page": positive_int(
                    chapter.get("page_number") or chapter.get("page")
                )
                or current.get("page_number", 1),
            })
    return result if len(result) >= 2 else []


def chapters_from_embedded_toc(chapters: list[dict]) -> list[dict]:
    toc_index = -1
    for index, chapter in enumerate(chapters[:120]):
        title = str(chapter.get("title") or "")
        text = str(chapter.get("text") or "")
        if "目录" in title.replace(" ", "") or "目录" in text[:80].replace(" ", ""):
            toc_index = index
            break
    if toc_index < 0:
        return []

    toc_parts: list[str] = []
    for chapter in chapters[toc_index:min(len(chapters), toc_index + 18)]:
        title = str(chapter.get("title") or "")
        text = str(chapter.get("text") or "")
        if (
            toc_parts
            and re.match(
                r"^第[一二三四五六七八九十百千0-9]+章",
                title.replace(" ", ""),
            )
            and "目录" not in text[:80].replace(" ", "")
        ):
            break
        toc_parts.append(text or title)
    toc_text = "\n".join(toc_parts)
    if not toc_text:
        return []

    chapter_pattern = re.compile(
        r"^\s*(第\s*[一二三四五六七八九十百千0-9]+\s*章\s*.+?)"
        r"\s*[\.·…\s]*(\d{1,4})?\s*$"
    )
    section_pattern = re.compile(
        r"^\s*(第\s*[一二三四五六七八九十百千0-9]+\s*节\s*.+?)"
        r"\s*[\.·…\s]*(\d{1,4})?\s*$"
    )
    result: list[dict] = []
    current: dict | None = None
    for raw in toc_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[#`*_]+", "", raw).strip()
        if not line or "目录" in line.replace(" ", ""):
            continue
        chapter_match = chapter_pattern.match(line)
        if chapter_match:
            title = re.sub(r"[\.·…\s\d]+$", "", chapter_match.group(1)).strip()
            page = positive_int(chapter_match.group(2)) or 1
            current = {
                "title": title,
                "page_number": page,
                "end_page": None,
                "text": "",
                "subsections": [],
            }
            result.append(current)
            continue
        section_match = section_pattern.match(line)
        if section_match and current is not None:
            title = re.sub(r"[\.·…\s\d]+$", "", section_match.group(1)).strip()
            current.setdefault("subsections", []).append({
                "title": title,
                "page": positive_int(section_match.group(2))
                or current.get("page_number", 1),
            })

    for index, chapter in enumerate(result):
        next_page = (
            positive_int(result[index + 1].get("page_number"))
            if index + 1 < len(result)
            else None
        )
        if next_page:
            chapter["end_page"] = max(
                positive_int(chapter.get("page_number")) or 1,
                next_page - 1,
            )
    return result


def format_chapter(chapter: dict) -> dict:
    return {
        "title": chapter.get("title", ""),
        "page": chapter.get("page_number", chapter.get("page", 1)),
        "end_page": chapter.get("end_page"),
        "subsections": [
            {
                **{key: subsection[key] for key in ('heading_block_id', 'parent_heading_block_id', 'level', 'section_path', 'page_kind', 'printed_page') if key in subsection},
                "title": subsection.get("title", ""),
                "page": subsection.get("page", subsection.get("page_number")),
                "end_page": subsection.get("end_page"),
            }
            for subsection in chapter.get("subsections", [])
        ],
    }
