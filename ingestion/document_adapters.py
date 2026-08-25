"""Adapters that turn existing textbook-source outputs into CanonicalBook.

The adapters deliberately do not build an index.  They preserve source
structure and provenance first; a later chunking stage can consume the common
``CanonicalBook`` contract without knowing whether the input was a PDF, MinerU,
PaddleOCR layout result, or Word document.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any, Iterable
import zipfile
from xml.etree import ElementTree as ET

from ingestion.document_ir import CanonicalBook, DocumentBlock
from utils.resource_limits import (
    MAX_DOCX_EXPANDED_BYTES,
    MAX_DOCX_FILES,
    MAX_DOCX_MEMBER_BYTES,
    inspect_zip_limits,
)


class PdfTextAdapter:
    """Adapt the existing ``PDFParser.extract_chapters`` output."""

    @staticmethod
    def from_chapters(
        chapters: Iterable[dict[str, Any]],
        *,
        book_name: str,
        source_file: str = "",
        source_page_count: int | None = None,
    ) -> CanonicalBook:
        builder = _BlockBuilder(book_name, source_kind="pdf_text", source_file=source_file)
        for index, chapter in enumerate(chapters):
            title = _clean_text(chapter.get("title")) or f"{book_name}（第 {index + 1} 节）"
            start = _page_number(chapter.get("page_number") or chapter.get("page"))
            end = _page_number(chapter.get("end_page")) or start
            builder.heading(title, level=1, page_start=start, page_end=end)
            text = _clean_text(chapter.get("text"))
            if text:
                _append_markdown(
                    builder,
                    _strip_duplicate_leading_heading(text, title),
                    page_start=start,
                    page_end=end,
                    attributes={"chapter_index": index},
                    min_heading_level=2,
                )
        return builder.book(
            parser_version="pdf-parser-chapters-v1",
            source_page_count=source_page_count,
        )

    @classmethod
    def from_pdf(cls, pdf_path: str | Path, *, book_name: str, toc_page_range: str = "") -> CanonicalBook:
        """Convenience adapter for text-layer PDFs; scanned pages stay empty by design."""
        from ingestion.pdf_parser import PDFParser

        parser = PDFParser(pdf_path)
        try:
            chapters = parser.extract_chapters(toc_page_range)
            return cls.from_chapters(
                chapters,
                book_name=book_name,
                source_file=Path(pdf_path).name,
                source_page_count=parser.total_pages,
            )
        finally:
            parser.close()


class MinerUAdapter:
    """Adapt MinerU content-list, middle JSON, or Markdown output without re-OCR."""

    @staticmethod
    def from_chapters(
        chapters: Iterable[dict[str, Any]],
        *,
        book_name: str,
        source_file: str = "",
        source_page_count: int | None = None,
    ) -> CanonicalBook:
        """Preserve existing ``chapters_from_mineru_output`` native blocks when present."""
        builder = _BlockBuilder(book_name, source_kind="mineru", source_file=source_file)
        for chapter_index, chapter in enumerate(chapters):
            title = _clean_text(chapter.get("title")) or f"{book_name}（第 {chapter_index + 1} 节）"
            start = _page_number(chapter.get("page_number") or chapter.get("page"))
            end = _page_number(chapter.get("end_page")) or start
            builder.heading(title, level=1, page_start=start, page_end=end)
            native_rows = chapter.get("chunks") if isinstance(chapter.get("chunks"), list) else []
            if native_rows:
                for source_index, row in enumerate(native_rows):
                    _append_mineru_item(builder, row, fallback_page=start, source_index=source_index)
            else:
                text = _clean_text(chapter.get("text"))
                if text:
                    builder.add(
                        "paragraph", text, page_start=start, page_end=end,
                        attributes={"chapter_index": chapter_index},
                    )
        return builder.book(
            parser_version="mineru-chapters-v1",
            source_page_count=source_page_count,
        )

    @staticmethod
    def from_content_list(
        items: Iterable[dict[str, Any]],
        *,
        book_name: str,
        source_file: str = "",
        source_page_count: int | None = None,
    ) -> CanonicalBook:
        builder = _BlockBuilder(book_name, source_kind="mineru", source_file=source_file)
        for source_index, item in enumerate(items):
            _append_mineru_item(builder, item, source_index=source_index)
        return builder.book(
            parser_version="mineru-content-list-v1",
            source_page_count=source_page_count,
        )

    @classmethod
    def from_output_dir(cls, output_dir: str | Path, *, book_name: str) -> CanonicalBook:
        """Read the same MinerU formats already accepted by ``mineru_importer``."""
        root = Path(output_dir)
        content_path = _find_first_json(root, ("*content_list*.json", "*content-list*.json"))
        if content_path is not None:
            payload = _read_json(content_path)
            if isinstance(payload, list):
                page_count = _mineru_page_count(payload)
                return cls.from_content_list(
                    payload, book_name=book_name, source_file=content_path.name, source_page_count=page_count,
                )
        middle_path = _find_first_json(root, ("*middle*.json",))
        if middle_path is not None:
            payload = _read_json(middle_path)
            if isinstance(payload, dict):
                items, page_count = _items_from_middle_json(payload)
                if items:
                    return cls.from_content_list(
                        items, book_name=book_name, source_file=middle_path.name, source_page_count=page_count,
                    )
        markdown_paths = sorted(root.rglob("*.md"), key=lambda path: str(path).lower())
        if markdown_paths:
            builder = _BlockBuilder(book_name, source_kind="mineru", source_file="")
            for markdown_path in markdown_paths:
                try:
                    builder.source_file = markdown_path.name
                    _append_markdown(builder, markdown_path.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
            builder.source_files = [path.name for path in markdown_paths]
            return builder.book(parser_version="mineru-markdown-v1")
        return CanonicalBook(
            book_name=book_name,
            source_kind="mineru",
            parser_version="mineru-empty-v1",
            blocks=[],
            warnings=["No MinerU content-list, middle JSON, or Markdown file was found."],
        )


class OcrAdapter:
    """Adapt page-layout output from PaddleOCR/PPStructure or another OCR engine.

    ``pages`` is intentionally a small public protocol: each item has a 1-based
    ``page_number`` (or 0-based ``page_idx``) and a ``blocks``/``regions`` list
    with ``type``, ``text``, optional ``bbox`` and optional ``confidence``.
    """

    @staticmethod
    def from_layout_pages(
        pages: Iterable[dict[str, Any]],
        *,
        book_name: str,
        source_file: str = "",
        source_page_count: int | None = None,
    ) -> CanonicalBook:
        builder = _BlockBuilder(book_name, source_kind="ocr", source_file=source_file)
        observed_pages: list[int] = []
        for page_index, page in enumerate(pages):
            page_number = _page_number(page.get("page_number")) or _page_number(page.get("page"))
            if page_number is None:
                raw_index = _zero_based_index(page.get("page_idx"))
                page_number = raw_index + 1 if raw_index is not None else page_index + 1
            observed_pages.append(page_number)
            regions = page.get("blocks") or page.get("regions") or []
            if not isinstance(regions, list):
                continue
            for source_index, region in enumerate(regions):
                raw_type = str(region.get("type") or "text").lower()
                text = _clean_text(region.get("text"))
                confidence = _float_or_none(region.get("confidence") or region.get("score"))
                bbox = _bbox(region.get("bbox"))
                if raw_type in {"title", "heading", "header"}:
                    level = _heading_level(region.get("level") or region.get("text_level")) or 1
                    builder.heading(
                        text or f"第 {page_number} 页标题", level=level,
                        page_start=page_number, page_end=page_number, bbox=bbox,
                        confidence=confidence, attributes={"source_block_index": source_index},
                    )
                    continue
                block_type = _block_type(raw_type)
                table_title, table_header, table_rows = _table_parts(region)
                equations = _equations(region, text)
                builder.add(
                    block_type, text, page_start=page_number, page_end=page_number, bbox=bbox,
                    confidence=confidence, equations=equations, table_title=table_title,
                    table_header=table_header, table_rows=table_rows,
                    attributes={"source_block_index": source_index, "ocr_type": raw_type},
                )
        return builder.book(
            parser_version="ocr-layout-v1",
            source_page_count=source_page_count or max(observed_pages, default=None),
        )


class DocxAdapter:
    """Read standard .docx paragraphs, headings, tables, and basic OMML equations."""

    @staticmethod
    def from_docx(path: str | Path, *, book_name: str) -> CanonicalBook:
        docx_path = Path(path)
        builder = _BlockBuilder(book_name, source_kind="docx", source_file=docx_path.name)
        try:
            with zipfile.ZipFile(docx_path) as archive:
                inspect_zip_limits(
                    archive,
                    max_files=MAX_DOCX_FILES,
                    max_expanded_bytes=MAX_DOCX_EXPANDED_BYTES,
                    max_member_bytes=MAX_DOCX_MEMBER_BYTES,
                )
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("Word document.xml is missing")
                root = ET.fromstring(archive.read("word/document.xml"))
        except zipfile.BadZipFile as exc:
            raise ValueError("Word file is invalid or corrupted") from exc
        except ET.ParseError as exc:
            raise ValueError("Word XML cannot be parsed") from exc

        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        body = root.find(f"{namespace}body")
        if body is None:
            return builder.book(parser_version="docx-xml-v1", warnings=["Word document has no body."])
        previous_paragraph = ""
        active_learning_group = ""
        active_learning_type = ""
        for source_index, child in enumerate(list(body)):
            tag = _local_name(child.tag)
            if tag == "p":
                text = _word_text(child)
                if not text:
                    continue
                level = _word_heading_level(child, namespace)
                if level is not None:
                    builder.heading(text, level=level, attributes={"source_block_index": source_index})
                    active_learning_group = ""
                    active_learning_type = ""
                elif _contains_omml(child):
                    builder.add(
                        "formula", text, equations=[text], review_status="needs_formula_review",
                        attributes={"source_block_index": source_index, "omml_plain_text": True},
                    )
                else:
                    labeled_type = _labeled_learning_block_type(text)
                    if labeled_type:
                        active_learning_type = labeled_type
                        active_learning_group = f"docx-learning-{source_index}"
                    elif active_learning_type and not _is_learning_continuation(text):
                        active_learning_type = ""
                        active_learning_group = ""
                    attributes = {"source_block_index": source_index}
                    if active_learning_group:
                        attributes["group_id"] = active_learning_group
                    builder.add(active_learning_type or "paragraph", text, attributes=attributes)
                    previous_paragraph = text
            elif tag == "tbl":
                rows = _word_table_rows(child)
                if not rows:
                    continue
                title = previous_paragraph if re.match(r"^\s*表\s*\d", previous_paragraph) else ""
                builder.add(
                    "table", _table_text(rows), table_title=title, table_header=rows[0], table_rows=rows[1:],
                    attributes={"source_block_index": source_index},
                )
        return builder.book(parser_version="docx-xml-v1")


class _BlockBuilder:
    def __init__(self, book_name: str, *, source_kind: str, source_file: str):
        self.book_name = str(book_name or "").strip()
        self.source_kind = source_kind
        self.source_file = source_file
        self.path: list[str] = []
        self.blocks: list[DocumentBlock] = []
        self.source_files: list[str] = []

    def heading(
        self,
        text: str,
        *,
        level: int,
        page_start: int | None = None,
        page_end: int | None = None,
        bbox: list[float] | None = None,
        confidence: float | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        title = _clean_text(text)
        if not title:
            return
        normalized_level = max(1, min(int(level or 1), 6))
        self.path = self.path[:normalized_level - 1]
        self.path.append(title)
        self.add(
            "heading", title, page_start=page_start, page_end=page_end, bbox=bbox,
            confidence=confidence, attributes={**(attributes or {}), "heading_level": normalized_level},
        )

    def add(
        self,
        block_type: str,
        text: str,
        *,
        page_start: int | None = None,
        page_end: int | None = None,
        bbox: list[float] | None = None,
        confidence: float | None = None,
        equations: list[str] | None = None,
        review_status: str = "",
        table_title: str = "",
        table_header: list[str] | None = None,
        table_rows: list[list[str]] | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        cleaned = _clean_text(text)
        path = list(self.path) or [self.book_name or "未分章正文"]
        source_position = len(self.blocks)
        digest = hashlib.sha1(
            f"{self.book_name}|{self.source_kind}|{self.source_file}|{source_position}|{block_type}|{cleaned[:240]}".encode("utf-8")
        ).hexdigest()[:20]
        self.blocks.append(DocumentBlock(
            block_id=digest,
            block_type=block_type,
            text=cleaned,
            section_path=path,
            page_start=page_start,
            page_end=page_end,
            bbox=bbox,
            equations=list(equations or []),
            source_file=self.source_file,
            source_kind=self.source_kind,
            ocr_confidence=confidence,
            review_status=review_status,
            table_title=table_title,
            table_header=list(table_header or []),
            table_rows=[list(row) for row in table_rows or []],
            attributes=dict(attributes or {}),
        ))

    def book(self, *, parser_version: str, source_page_count: int | None = None, warnings: list[str] | None = None) -> CanonicalBook:
        source_files = sorted(set(self.source_files))
        extra_warnings = list(warnings or [])
        if source_files:
            extra_warnings.append(f"Source Markdown files: {', '.join(source_files)}")
        return CanonicalBook(
            book_name=self.book_name,
            source_kind=self.source_kind,
            blocks=self.blocks,
            parser_version=parser_version,
            source_page_count=source_page_count,
            warnings=extra_warnings,
        )


def _append_mineru_item(
    builder: _BlockBuilder,
    item: dict[str, Any],
    *,
    fallback_page: int | None = None,
    source_index: int,
) -> None:
    if not isinstance(item, dict):
        return
    raw_type = str(item.get("type") or item.get("block_type") or "text").lower()
    text = _item_text(item)
    page = _page_number(item.get("page_number")) or _page_number(item.get("page"))
    if page is None:
        page_idx = _zero_based_index(item.get("page_idx"))
        page = page_idx + 1 if page_idx is not None else fallback_page
    bbox = _bbox(item.get("bbox"))
    confidence = _float_or_none(item.get("confidence") or item.get("score"))
    level = _heading_level(item.get("text_level") or item.get("level"))
    if raw_type in {"title", "heading"} or (raw_type == "text" and level is not None):
        builder.heading(
            text, level=level or 1, page_start=page, page_end=page, bbox=bbox,
            confidence=confidence, attributes={"source_block_index": source_index, "mineru_type": raw_type},
        )
        return
    block_type = _block_type(raw_type)
    table_title, table_header, table_rows = _table_parts(item)
    equations = _equations(item, text)
    review_status = "needs_formula_review" if block_type == "formula" and not equations else ""
    builder.add(
        block_type, text, page_start=page, page_end=page, bbox=bbox, confidence=confidence,
        equations=equations, review_status=review_status, table_title=table_title,
        table_header=table_header, table_rows=table_rows,
        attributes={
            "source_block_index": source_index,
            "mineru_type": raw_type,
            "source_markdown": _clean_text(item.get("source_markdown")),
            "semantic_role": _clean_text(item.get("semantic_role") or item.get("role")),
        },
    )


def _append_markdown(
    builder: _BlockBuilder,
    markdown: str,
    *,
    page_start: int | None = None,
    page_end: int | None = None,
    attributes: dict[str, Any] | None = None,
    min_heading_level: int = 1,
) -> None:
    lines = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    paragraph: list[str] = []
    index = 0
    active_learning_type = ""
    active_learning_group = ""

    def flush_paragraph() -> None:
        nonlocal paragraph, active_learning_type, active_learning_group
        text = "\n".join(paragraph).strip()
        if text:
            labeled_type = _labeled_learning_block_type(text)
            if labeled_type:
                active_learning_type = labeled_type
                active_learning_group = f"markdown-learning-{len(builder.blocks)}"
            elif active_learning_type and not _is_learning_continuation(text):
                active_learning_type = ""
                active_learning_group = ""
            block_attributes = dict(attributes or {})
            if active_learning_group:
                block_attributes["group_id"] = active_learning_group
            builder.add(
                active_learning_type or "paragraph",
                text,
                page_start=page_start,
                page_end=page_end,
                attributes=block_attributes,
            )
        paragraph = []

    while index < len(lines):
        line = lines[index]
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            flush_paragraph()
            builder.heading(
                heading.group(2).strip(" #"),
                level=max(int(min_heading_level), len(heading.group(1))),
                page_start=page_start, page_end=page_end, attributes=attributes,
            )
            active_learning_type = ""
            active_learning_group = ""
            index += 1
            continue
        if line.strip().startswith("$$"):
            flush_paragraph()
            formula_lines = [line]
            index += 1
            while index < len(lines) and "$$" not in lines[index]:
                formula_lines.append(lines[index])
                index += 1
            if index < len(lines):
                formula_lines.append(lines[index])
                index += 1
            formula = "\n".join(formula_lines)
            builder.add(
                "formula", formula, equations=[formula],
                page_start=page_start, page_end=page_end, attributes=attributes,
            )
            continue
        if "|" in line and index + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1]):
            flush_paragraph()
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index]:
                table_lines.append(lines[index])
                index += 1
            header, rows = _markdown_table_rows(table_lines)
            builder.add(
                "table", "\n".join(table_lines), table_header=header, table_rows=rows,
                page_start=page_start, page_end=page_end, attributes=attributes,
            )
            continue
        if not line.strip():
            flush_paragraph()
        else:
            paragraph.append(line)
        index += 1
    flush_paragraph()


def _strip_duplicate_leading_heading(text: str, title: str) -> str:
    lines = str(text or "").splitlines()
    if not lines:
        return ""
    match = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", lines[0])
    if match and re.sub(r"\s+", "", match.group(1)) == re.sub(r"\s+", "", str(title or "")):
        return "\n".join(lines[1:]).lstrip()
    return str(text or "")


def _block_type(raw_type: str) -> str:
    normalized = str(raw_type or "text").lower()
    if normalized in {"equation", "formula", "math", "display_formula"}:
        return "formula"
    if normalized in {"table", "html_table"}:
        return "table"
    if normalized in {"image", "figure", "img"}:
        return "figure"
    if normalized in {"example", "case"}:
        return "example"
    if normalized in {"exercise", "problem", "question"}:
        return "exercise"
    return "paragraph"


def _labeled_learning_block_type(text: str) -> str:
    compact = str(text or "").strip()
    if re.match(r"^(?:例题|例\s*\d+|示例)\s*[：:、.]?", compact):
        return "example"
    if re.match(r"^(?:习题|练习|作业题|问题)\s*\d*\s*[：:、.]?", compact):
        return "exercise"
    return ""


def _is_learning_continuation(text: str) -> bool:
    return bool(re.match(r"^(?:题干|条件|已知|求|解|解答|答案|证明|分析)\s*[：:]?", str(text or "").strip()))


def _item_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("text", "content", "code_body", "latex", "table_body", "html"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    for key in ("table_caption", "table_footnote", "image_caption", "image_footnote"):
        value = item.get(key)
        if isinstance(value, list):
            parts.extend(_clean_text(part) for part in value if _clean_text(part))
        elif _clean_text(value):
            parts.append(_clean_text(value))
    return "\n".join(parts)


def _equations(item: dict[str, Any], text: str) -> list[str]:
    values = item.get("equations")
    equations = [str(value).strip() for value in values if str(value).strip()] if isinstance(values, list) else []
    latex = _clean_text(item.get("latex"))
    if latex and latex not in equations:
        equations.append(latex)
    if not equations and _block_type(str(item.get("type") or item.get("block_type") or "")) == "formula" and text:
        equations.append(text)
    return equations


def _table_parts(item: dict[str, Any]) -> tuple[str, list[str], list[list[str]]]:
    title = _joined_text(item.get("table_title") or item.get("table_caption"))
    header = _string_list(item.get("table_header"))
    rows = _string_matrix(item.get("table_rows"))
    raw = _clean_text(item.get("table_body") or item.get("html"))
    if not header and raw.startswith("|"):
        header, rows = _markdown_table_rows(raw.splitlines())
    elif not header and "<table" in raw.lower():
        parsed = _parse_html_table(raw)
        if parsed:
            header, rows = parsed[0], parsed[1:]
    return title, header, rows


def _markdown_table_rows(lines: Iterable[str]) -> tuple[list[str], list[list[str]]]:
    parsed = []
    for line in lines:
        compact = line.strip()
        if not compact or re.fullmatch(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?", compact):
            continue
        cells = [cell.strip() for cell in compact.strip("|").split("|")]
        if cells:
            parsed.append(cells)
    return (parsed[0], parsed[1:]) if parsed else ([], [])


class _HtmlTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs):
        if tag == "tr":
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str):
        if tag in {"th", "td"} and self._row is not None and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None


def _parse_html_table(value: str) -> list[list[str]]:
    parser = _HtmlTableParser()
    parser.feed(value)
    parser.close()
    return parser.rows


def _items_from_middle_json(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    items: list[dict[str, Any]] = []
    pages = payload.get("pdf_info") if isinstance(payload.get("pdf_info"), list) else []
    for page_index, page in enumerate(pages):
        page_idx = _zero_based_index(page.get("page_idx"))
        for block in page.get("para_blocks", []) or []:
            text = _middle_block_text(block)
            if text:
                items.append({
                    "type": block.get("type") or "text",
                    "text": text,
                    "page_idx": page_idx if page_idx is not None else page_index,
                    "bbox": block.get("bbox") or [],
                    "equations": block.get("equations") or [],
                })
    return items, len(pages) or None


def _middle_block_text(block: dict[str, Any]) -> str:
    parts: list[str] = []
    for line in block.get("lines", []) or []:
        for span in line.get("spans", []) or []:
            if _clean_text(span.get("content")):
                parts.append(_clean_text(span.get("content")))
    for child in block.get("blocks", []) or []:
        text = _middle_block_text(child)
        if text:
            parts.append(text)
    return " ".join(parts)


def _mineru_page_count(items: Iterable[dict[str, Any]]) -> int | None:
    pages = []
    for item in items:
        page_idx = _zero_based_index(item.get("page_idx"))
        if page_idx is not None:
            pages.append(page_idx + 1)
    return max(pages, default=None)


def _find_first_json(root: Path, patterns: Iterable[str]) -> Path | None:
    for pattern in patterns:
        for path in root.rglob(pattern):
            return path
    return None


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _word_text(element: ET.Element) -> str:
    parts: list[str] = []
    for node in element.iter():
        tag = _local_name(node.tag)
        if tag in {"t", "instrText"} and node.text:
            parts.append(node.text)
        elif tag == "tab":
            parts.append("\t")
        elif tag in {"br", "cr"}:
            parts.append("\n")
    return _clean_text("".join(parts))


def _word_heading_level(element: ET.Element, namespace: str) -> int | None:
    style = element.find(f"{namespace}pPr/{namespace}pStyle")
    style_value = str(style.get(f"{namespace}val") or style.get("val") or "") if style is not None else ""
    match = re.search(r"(?:heading|标题)\s*([1-6])", style_value, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _contains_omml(element: ET.Element) -> bool:
    return any(_local_name(node.tag) in {"oMath", "oMathPara"} for node in element.iter())


def _word_table_rows(table: ET.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.iter():
        if _local_name(row.tag) != "tr":
            continue
        cells = [_word_text(cell) for cell in list(row) if _local_name(cell.tag) == "tc"]
        if any(cells):
            rows.append(cells)
    return rows


def _table_text(rows: list[list[str]]) -> str:
    return "\n".join(" | ".join(row) for row in rows)


def _heading_level(value: Any) -> int | None:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return None
    return level if 1 <= level <= 6 else None


def _page_number(value: Any) -> int | None:
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None
    return page if page >= 1 else None


def _zero_based_index(value: Any) -> int | None:
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None
    return index if index >= 0 else None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    return [_clean_text(item) for item in value if _clean_text(item)] if isinstance(value, list) else []


def _string_matrix(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    result = []
    for row in value:
        if isinstance(row, (list, tuple)):
            cells = [_clean_text(cell) for cell in row]
            if any(cells):
                result.append(cells)
    return result


def _clean_text(value: Any) -> str:
    return re.sub(r"[ \t]+", " ", str(value or "")).strip()


def _joined_text(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " ".join(_clean_text(item) for item in value if _clean_text(item))
    return _clean_text(value)


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]
