"""Stable, source-neutral textbook document intermediate representation.

This module sits *before* chunking and indexing.  Parsers may differ in how
they obtain text, but they must emit the same ``CanonicalBook`` contract before
the downstream splitter is allowed to make retrieval chunks.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path, PurePosixPath
import re
import uuid
from typing import Any

from config import PROGRESS_PATH


DOCUMENT_IR_SCHEMA_VERSION = 1
PROVENANCE_SCHEMA_VERSION = "texa.provenance/v1"
CANONICAL_DOCUMENT_FILENAME = "canonical_document.jsonl"
INGESTION_REPORT_FILENAME = "ingestion_report.json"
BLOCK_TYPES = frozenset({
    "heading", "paragraph", "formula", "table", "figure", "example", "exercise",
})
BODY_BLOCK_TYPES = frozenset({"paragraph", "formula", "table", "example", "exercise"})
OCR_SOURCE_KINDS = frozenset({"ocr", "mineru"})


def chunk_provenance_errors(chunk: dict[str, Any], *, require_index_version: bool = False) -> list[str]:
    """Validate the minimum stable provenance carried by an indexed chunk."""
    errors: list[str] = []
    if str(chunk.get("provenance_schema") or "") != PROVENANCE_SCHEMA_VERSION:
        errors.append("invalid_provenance_schema")
    if not str(chunk.get("chunk_id") or "").strip():
        errors.append("missing_chunk_id")
    if require_index_version and not str(chunk.get("index_version") or "").strip():
        errors.append("missing_index_version")

    source_ids = chunk.get("source_block_ids")
    if not isinstance(source_ids, list) or not source_ids or any(not str(value or "").strip() for value in source_ids):
        errors.append("missing_source_block_ids")
        source_ids = []
    elif len(set(str(value) for value in source_ids)) != len(source_ids):
        errors.append("duplicate_source_block_ids")

    locations = chunk.get("source_locations")
    if not isinstance(locations, list) or not locations:
        errors.append("missing_source_locations")
        locations = []
    location_ids: list[str] = []
    required_location_keys = {
        "block_id", "source_kind", "source_file", "page_start", "page_end",
        "bbox", "bbox_space", "bbox_format", "bbox_units",
    }
    for location in locations:
        if not isinstance(location, dict):
            errors.append("invalid_source_location")
            continue
        if not required_location_keys.issubset(location):
            errors.append("incomplete_source_location")
        block_id = str(location.get("block_id") or "").strip()
        if not block_id:
            errors.append("source_location_missing_block_id")
        else:
            location_ids.append(block_id)
        bbox = location.get("bbox")
        if bbox and (not isinstance(bbox, list) or len(bbox) != 4):
            errors.append("invalid_source_location_bbox")
    if source_ids and location_ids != [str(value) for value in source_ids]:
        errors.append("source_location_block_mismatch")

    if str(chunk.get("block_type") or "") == "figure":
        figure_id = str(chunk.get("figure_id") or "").strip()
        if not figure_id:
            errors.append("missing_figure_id")
        elif source_ids and figure_id not in {str(value) for value in source_ids}:
            errors.append("figure_id_not_in_source_blocks")
    return list(dict.fromkeys(errors))


@dataclass
class DocumentBlock:
    """One source-faithful textbook unit before retrieval-oriented chunking."""

    block_id: str
    block_type: str
    text: str
    section_path: list[str]
    page_start: int | None = None
    page_end: int | None = None
    bbox: list[float] | None = None
    equations: list[str] = field(default_factory=list)
    source_file: str = ""
    source_kind: str = ""
    ocr_confidence: float | None = None
    review_status: str = ""
    table_title: str = ""
    table_header: list[str] = field(default_factory=list)
    table_rows: list[list[str]] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DocumentBlock":
        """Read a persisted record while ignoring future optional fields."""
        if not isinstance(value, dict):
            raise ValueError("DocumentBlock record must be an object")
        bbox = value.get("bbox")
        return cls(
            block_id=str(value.get("block_id") or ""),
            block_type=str(value.get("block_type") or ""),
            text=str(value.get("text") or ""),
            section_path=[str(item).strip() for item in value.get("section_path", []) if str(item).strip()]
            if isinstance(value.get("section_path"), list) else [],
            page_start=_optional_int(value.get("page_start")),
            page_end=_optional_int(value.get("page_end")),
            bbox=list(bbox) if isinstance(bbox, (list, tuple)) else None,
            equations=[str(item).strip() for item in value.get("equations", []) if str(item).strip()]
            if isinstance(value.get("equations"), list) else [],
            source_file=str(value.get("source_file") or ""),
            source_kind=str(value.get("source_kind") or ""),
            ocr_confidence=_optional_float(value.get("ocr_confidence")),
            review_status=str(value.get("review_status") or ""),
            table_title=str(value.get("table_title") or ""),
            table_header=_string_list(value.get("table_header")),
            table_rows=_string_matrix(value.get("table_rows")),
            attributes=dict(value.get("attributes") or {}) if isinstance(value.get("attributes"), dict) else {},
        )


@dataclass
class CanonicalBook:
    """A complete textbook represented by source-neutral blocks."""

    book_name: str
    source_kind: str
    blocks: list[DocumentBlock]
    parser_version: str
    warnings: list[str] = field(default_factory=list)
    source_page_count: int | None = None
    schema_version: int = DOCUMENT_IR_SCHEMA_VERSION

    def header_dict(self) -> dict[str, Any]:
        return {
            "record_type": "canonical_book",
            "schema_version": self.schema_version,
            "book_name": self.book_name,
            "source_kind": self.source_kind,
            "parser_version": self.parser_version,
            "warnings": list(self.warnings),
            "source_page_count": self.source_page_count,
        }


@dataclass(frozen=True)
class IngestionIssue:
    severity: str
    code: str
    message: str
    block_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class IngestionReport:
    book_name: str
    schema_version: int
    block_count: int
    issues: list[IngestionIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        errors = sum(issue.severity == "error" for issue in self.issues)
        warnings = sum(issue.severity == "warning" for issue in self.issues)
        return {
            "schema_version": self.schema_version,
            "book_name": self.book_name,
            "block_count": self.block_count,
            "valid": self.valid,
            "summary": {"errors": errors, "warnings": warnings},
            "issues": [issue.to_dict() for issue in self.issues],
        }


def validate_canonical_book(book: CanonicalBook) -> IngestionReport:
    """Run deterministic intake checks and attach non-destructive review labels.

    Most source-quality findings are warnings: they are persisted so a future
    adapter or UI can repair the affected pages without discarding a usable
    book.  Errors are reserved for an unusable IR contract (for example,
    duplicate IDs or no indexable body).
    """
    issues: list[IngestionIssue] = []
    if not str(book.book_name or "").strip():
        issues.append(_issue("error", "missing_book_name", "book_name is required"))
    if not str(book.source_kind or "").strip():
        issues.append(_issue("error", "missing_source_kind", "book source_kind is required"))
    if not str(book.parser_version or "").strip():
        issues.append(_issue("error", "missing_parser_version", "parser_version is required"))
    if book.schema_version != DOCUMENT_IR_SCHEMA_VERSION:
        issues.append(_issue(
            "error", "unsupported_schema_version",
            f"expected schema {DOCUMENT_IR_SCHEMA_VERSION}, got {book.schema_version}",
        ))
    if not book.blocks:
        issues.append(_issue("error", "empty_book", "at least one document block is required"))
    if book.source_page_count is not None and book.source_page_count < 1:
        issues.append(_issue("error", "invalid_source_page_count", "source_page_count must be positive"))

    seen_ids: set[str] = set()
    usable_body_blocks = 0
    body_without_paths = 0
    heading_paths: list[tuple[str, list[str], int | None]] = []
    ocr_seen = False
    ocr_pages_with_body: dict[int, bool] = {}
    for block in book.blocks:
        block_id = str(block.block_id or "").strip()
        if not block_id:
            issues.append(_issue("error", "missing_block_id", "block_id is required"))
        elif block_id in seen_ids:
            issues.append(_issue("error", "duplicate_block_id", "block_id must be unique", block_id))
        else:
            seen_ids.add(block_id)
        if block.block_type not in BLOCK_TYPES:
            issues.append(_issue(
                "error", "unsupported_block_type",
                f"block_type must be one of {', '.join(sorted(BLOCK_TYPES))}", block_id,
            ))
        if not str(block.text or "").strip():
            issues.append(_issue("warning", "empty_text", "block text is empty", block_id))
        if not block.section_path or any(not str(part or "").strip() for part in block.section_path):
            issues.append(_issue("warning", "missing_section_path", "section_path has no usable heading", block_id))
        if not str(block.source_kind or "").strip():
            issues.append(_issue("warning", "missing_block_source_kind", "block source_kind is missing", block_id))
        if block.page_start is not None and block.page_start < 1:
            issues.append(_issue("warning", "invalid_page_start", "page_start must be positive", block_id))
        if block.page_end is not None and block.page_end < 1:
            issues.append(_issue("warning", "invalid_page_end", "page_end must be positive", block_id))
        if block.page_start is not None and block.page_end is not None and block.page_end < block.page_start:
            issues.append(_issue("warning", "invalid_page_range", "page_end cannot precede page_start", block_id))
        if book.source_page_count and _page_outside_source(book.source_page_count, block):
            issues.append(_issue(
                "warning", "page_outside_source", "block page range exceeds source_page_count", block_id,
            ))
        if block.bbox is not None:
            if len(block.bbox) != 4 or not all(_is_finite_number(value) for value in block.bbox):
                issues.append(_issue("warning", "invalid_bbox", "bbox must contain four finite numbers", block_id))
        if block.ocr_confidence is not None and not 0.0 <= block.ocr_confidence <= 1.0:
            issues.append(_issue("warning", "invalid_ocr_confidence", "ocr_confidence must be within [0, 1]", block_id))
        if block.block_type == "formula" and not block.equations:
            issues.append(_issue("warning", "formula_without_equations", "formula block has no extracted equations", block_id))
        if _has_unbalanced_math_delimiters(block.text):
            _add_review_status(block, "needs_formula_review")
            issues.append(_issue(
                "warning", "unbalanced_formula_delimiters",
                "formula delimiters are unbalanced; block marked needs_formula_review", block_id,
            ))
        if block.block_type == "table":
            if not block.table_title.strip():
                issues.append(_issue("warning", "table_without_title", "table has no table_title", block_id))
            if not block.table_header:
                issues.append(_issue("warning", "table_without_header", "table has no table_header", block_id))
            if not block.table_rows:
                issues.append(_issue("warning", "table_without_rows", "table has no table_rows", block_id))
        if block.block_type == "figure":
            attributes = block.attributes or {}
            figure_id = str(attributes.get("figure_id") or "").strip()
            if not figure_id:
                issues.append(_issue("warning", "missing_figure_id", "figure_id is missing", block_id))
            elif figure_id != block_id:
                issues.append(_issue(
                    "error", "figure_id_mismatch", "figure_id must reuse the Canonical block_id", block_id,
                ))
            asset_relpath = str(attributes.get("asset_relpath") or "").strip().replace("\\", "/")
            if asset_relpath:
                asset_path = PurePosixPath(asset_relpath)
                if asset_path.is_absolute() or ".." in asset_path.parts or not asset_relpath.startswith("figures/"):
                    issues.append(_issue(
                        "error", "invalid_figure_asset_relpath",
                        "asset_relpath must be a controlled path below figures/", block_id,
                    ))
            asset_status = str(attributes.get("asset_status") or "").strip()
            if asset_status == "ready":
                if not asset_relpath:
                    issues.append(_issue("error", "missing_figure_asset_relpath", "ready figure has no asset_relpath", block_id))
                content_hash = str(attributes.get("content_hash") or "").strip()
                if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
                    issues.append(_issue("error", "invalid_figure_content_hash", "ready figure needs a SHA-256 content_hash", block_id))
                width = _optional_int(attributes.get("image_width"))
                height = _optional_int(attributes.get("image_height"))
                if width is None or height is None or width < 1 or height < 1:
                    issues.append(_issue("error", "invalid_figure_dimensions", "ready figure dimensions must be positive", block_id))
            elif asset_status in {"missing", "invalid"}:
                issues.append(_issue(
                    "warning", f"figure_asset_{asset_status}", f"figure asset is {asset_status}", block_id,
                ))
            if block.bbox and not str(attributes.get("bbox_space") or "").strip():
                issues.append(_issue("warning", "missing_figure_bbox_space", "figure bbox coordinate space is missing", block_id))
        if block.block_type == "heading" and block.section_path:
            heading_paths.append((
                block_id,
                list(block.section_path),
                _optional_int((block.attributes or {}).get("heading_level")),
            ))
        source_kind = str(block.source_kind or book.source_kind or "").strip().lower()
        if source_kind in OCR_SOURCE_KINDS:
            ocr_seen = True
        if source_kind in OCR_SOURCE_KINDS and block.ocr_confidence is None:
            issues.append(_issue("warning", "missing_ocr_confidence", "OCR-derived block has no confidence score", block_id))
        if source_kind in OCR_SOURCE_KINDS and block.block_type in BODY_BLOCK_TYPES:
            body_text = _compact_text(block.text)
            if 0 < len(body_text) < 12:
                issues.append(_issue("warning", "short_ocr_text", "OCR body block is unusually short", block_id))
            if _garbled_ratio(block.text) >= 0.02:
                issues.append(_issue("warning", "high_garbled_text_ratio", "OCR body block contains excessive garbled text", block_id))
            if block.page_start is not None and block.page_end is not None and block.page_end >= block.page_start:
                for page in range(max(block.page_start, 1), block.page_end + 1):
                    ocr_pages_with_body[page] = ocr_pages_with_body.get(page, False) or bool(body_text)
        if block.block_type in BODY_BLOCK_TYPES and _compact_text(block.text):
            if block.section_path and all(str(part).strip() for part in block.section_path):
                usable_body_blocks += 1
            else:
                body_without_paths += 1

    _validate_heading_paths(heading_paths, issues)
    if not usable_body_blocks:
        if body_without_paths:
            issues.append(_issue(
                "error", "no_usable_section_hierarchy",
                "body text exists but no usable section path; add a single-chapter fallback before indexing",
            ))
        else:
            issues.append(_issue("error", "no_usable_body", "book has no indexable body block"))
    if ocr_seen and book.source_page_count is None:
        issues.append(_issue(
            "warning", "missing_source_page_count",
            "cannot check OCR pages without source_page_count",
        ))
    if ocr_seen and book.source_page_count:
        for page in range(1, book.source_page_count + 1):
            if not ocr_pages_with_body.get(page, False):
                issues.append(_issue(
                    "warning", "ocr_page_without_body", "OCR source page has no body text", f"page:{page}",
                ))
    return IngestionReport(
        book_name=str(book.book_name or ""),
        schema_version=book.schema_version,
        block_count=len(book.blocks),
        issues=issues,
    )


def canonical_paths(book_name: str, *, progress_root: str | Path = PROGRESS_PATH) -> tuple[Path, Path]:
    """Return the canonical JSONL and validation-report paths for a book."""
    directory = Path(progress_root) / _safe_book_directory(book_name)
    return directory / CANONICAL_DOCUMENT_FILENAME, directory / INGESTION_REPORT_FILENAME


def persist_canonical_book(
    book: CanonicalBook,
    *,
    progress_root: str | Path = PROGRESS_PATH,
) -> IngestionReport:
    """Persist the IR and its validation report atomically per file.

    Invalid IR is deliberately persisted too: it is a diagnostic artifact, not
    an active index.  Callers must use ``report.valid`` before passing it to a
    splitter or index pipeline.
    """
    document_path, report_path = canonical_paths(book.book_name, progress_root=progress_root)
    document_path.parent.mkdir(parents=True, exist_ok=True)
    report = validate_canonical_book(book)
    records = [book.header_dict()] + [
        {"record_type": "document_block", **block.to_dict()} for block in book.blocks
    ]
    _atomic_write_text(
        document_path,
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records),
    )
    _atomic_write_text(
        report_path,
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return report


def load_canonical_book(
    book_name: str,
    *,
    progress_root: str | Path = PROGRESS_PATH,
) -> CanonicalBook:
    """Load a persisted CanonicalBook; reject malformed or incompatible files."""
    document_path, _ = canonical_paths(book_name, progress_root=progress_root)
    try:
        lines = [line for line in document_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except FileNotFoundError:
        raise FileNotFoundError(f"canonical document not found for {book_name}") from None
    if not lines:
        raise ValueError(f"canonical document is empty: {document_path}")
    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid canonical document header: {document_path}") from exc
    if header.get("record_type") != "canonical_book":
        raise ValueError("first JSONL record must be canonical_book")
    if int(header.get("schema_version") or 0) != DOCUMENT_IR_SCHEMA_VERSION:
        raise ValueError(f"unsupported canonical document schema: {header.get('schema_version')}")
    blocks: list[DocumentBlock] = []
    for line_number, line in enumerate(lines[1:], 2):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL record at line {line_number}") from exc
        if record.get("record_type") != "document_block":
            raise ValueError(f"unexpected JSONL record at line {line_number}")
        blocks.append(DocumentBlock.from_dict(record))
    return CanonicalBook(
        book_name=str(header.get("book_name") or ""),
        source_kind=str(header.get("source_kind") or ""),
        blocks=blocks,
        parser_version=str(header.get("parser_version") or ""),
        warnings=[str(item) for item in header.get("warnings", []) if str(item).strip()]
        if isinstance(header.get("warnings"), list) else [],
        source_page_count=_optional_int(header.get("source_page_count")),
        schema_version=int(header.get("schema_version") or DOCUMENT_IR_SCHEMA_VERSION),
    )


def _issue(severity: str, code: str, message: str, block_id: str = "") -> IngestionIssue:
    return IngestionIssue(severity=severity, code=code, message=message, block_id=block_id)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _string_matrix(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    rows: list[list[str]] = []
    for row in value:
        if not isinstance(row, (list, tuple)):
            continue
        cells = [str(cell).strip() for cell in row]
        if any(cells):
            rows.append(cells)
    return rows


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _page_outside_source(source_page_count: int, block: DocumentBlock) -> bool:
    return bool(
        (block.page_start is not None and block.page_start > source_page_count)
        or (block.page_end is not None and block.page_end > source_page_count)
    )


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _garbled_ratio(value: str) -> float:
    compact = _compact_text(value)
    if not compact:
        return 0.0
    garbled = sum(
        character == "\ufffd" or (ord(character) < 32 and character not in "\t\n\r")
        for character in compact
    )
    return garbled / len(compact)


def _has_unbalanced_math_delimiters(value: str) -> bool:
    text = str(value or "")
    display_count = len(re.findall(r"(?<!\\)\$\$", text))
    if display_count % 2:
        return True
    without_display = re.sub(r"(?<!\\)\$\$", "", text)
    inline_count = len(re.findall(r"(?<!\\)\$(?!\$)", without_display))
    if inline_count % 2:
        return True
    return text.count("\\[") != text.count("\\]") or text.count("\\(") != text.count("\\)")


def _add_review_status(block: DocumentBlock, status: str) -> None:
    current = [part.strip() for part in str(block.review_status or "").split(",") if part.strip()]
    if status not in current:
        current.append(status)
    block.review_status = ",".join(current)


def _validate_heading_paths(
    heading_paths: list[tuple[str, list[str], int | None]],
    issues: list[IngestionIssue],
) -> None:
    previous: list[str] | None = None
    previous_level: int | None = None
    for block_id, path, declared_level in heading_paths:
        if len(set(path)) != len(path):
            issues.append(_issue(
                "warning", "heading_cycle", "heading path repeats an ancestor title", block_id,
            ))
        current_level = declared_level or len(path)
        prior_level = previous_level or (len(previous) if previous is not None else None)
        if prior_level is not None and current_level > prior_level + 1:
            issues.append(_issue(
                "warning", "heading_depth_jump", "heading depth skips one or more levels", block_id,
            ))
        previous = path
        previous_level = current_level


def _safe_book_directory(book_name: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(book_name or "")).strip(". ")
    if not value or value in {".", ".."}:
        raise ValueError("book_name must contain a filesystem-safe name")
    return value


def _atomic_write_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
