"""Extract exercise-like text from an already imported textbook."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import BOOKS_PATH, DATA_DIR, MINERU_OUTPUT_PATH, PROGRESS_PATH
from utils.path_safety import safe_book_name


@dataclass
class ExtractedTextbookExerciseText:
    text: str
    provider: str
    book_name: str
    chapter: str = ""
    page_start: int | None = None
    page_end: int | None = None
    chunk_count: int = 0
    warnings: list[str] = field(default_factory=list)
    units: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "provider": self.provider,
            "book_name": self.book_name,
            "chapter": self.chapter,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chunk_count": self.chunk_count,
            "warnings": self.warnings,
            "units": self.units,
        }


EXERCISE_MARKERS = ("习题", "练习", "复习题", "思考题", "例题", "例 ")
ON_DEMAND_OCR_MAX_PAGES = 8


def extract_textbook_exercise_text(
    book_name: str,
    *,
    chapter: str = "",
    page_start: int | None = None,
    page_end: int | None = None,
    source_mode: str = "exercise_sections",
) -> ExtractedTextbookExerciseText:
    """Load text for textbook exercise import without mutating existing indexes."""
    clean_book = safe_book_name(book_name)
    if not clean_book:
        raise ValueError("请先选择教材")

    chapters = _load_chapters(clean_book)
    chapter_record = _find_chapter(chapters, chapter)
    resolved_chapter = str(chapter_record.get("title") or chapter or "").strip() if chapter_record else chapter.strip()
    resolved_start, resolved_end = _resolve_page_range(chapter_record, page_start, page_end)
    from ingestion.document_workflows import load_workflow_book, learning_units, canonical_outline
    from ingestion.document_ir import canonical_retrieval_paths, canonical_chapter_title
    canonical = load_workflow_book(clean_book, progress_root=Path(PROGRESS_PATH))
    if canonical is not None:
        paths = canonical_retrieval_paths(canonical.blocks)
        scope_ids = None
        if chapter.startswith('heading:'):
            heading_id = chapter.split(':', 1)[1]
            section = next((section for record in canonical_outline(canonical) for section in record['subsections']
                            if section['heading_block_id'] == heading_id), None)
            if section is None:
                raise ValueError('所选教材小节已不存在，请重新选择范围')
            scope_ids = set(section['source_block_ids'])
            resolved_chapter = section['section_path'][0]
            resolved_start = resolved_start or section['page']
            resolved_end = resolved_end or section['end_page']
        target = canonical_chapter_title(resolved_chapter) or resolved_chapter
        def scoped(path, start, end, block_id):
            return ((scope_ids is None or block_id in scope_ids) and (not target or target in path or any(_compact(target) == _compact(part) for part in path))
                    and (not resolved_start or (end or start or 0) >= resolved_start)
                    and (not resolved_end or (start or 0) <= resolved_end))
        units = []
        if source_mode != 'all_pages':
            for unit in learning_units(canonical):
                if source_mode == 'examples' and unit.kind != 'example':
                    continue
                start = unit.blocks[0].page_start
                end = max((block.page_end or block.page_start or 0 for block in unit.blocks), default=start)
                if not scoped(unit.section_path, start, end, unit.unit_id):
                    continue
                units.append(dict(unit_id=unit.unit_id, kind=unit.kind, text=unit.text, chapter=unit.section_path[0],
                                  page_start=start, page_end=end, source_block_ids=[block.block_id for block in unit.blocks],
                                  truncated=unit.truncated))
            text = '\n\n'.join(unit['text'] for unit in units)
        else:
            selected = [block for block in canonical.blocks if block.block_type not in {'heading', 'figure'}
                        and scoped(paths.get(block.block_id, []), block.page_start, block.page_end, block.block_id)]
            text = '\n\n'.join(block.text for block in selected)
        if not resolved_chapter:
            titles = set(unit['chapter'] for unit in units)
            if len(titles) == 1:
                resolved_chapter = titles.pop()
        return ExtractedTextbookExerciseText(
            text=text, provider='canonical-learning-units', book_name=clean_book, chapter=resolved_chapter,
            page_start=resolved_start, page_end=resolved_end, chunk_count=len(selected) if source_mode == 'all_pages' else len(units), units=units,
            warnings=['部分学习单元超出安全读取范围，请补充原文核对'] if any(unit['truncated'] for unit in units) else [],
        )
    explicit_page_range = _positive_int(page_start) is not None
    if explicit_page_range:
        chunk_start, chunk_end = _pdf_range_to_printed_pages(clean_book, resolved_start, resolved_end)
        pdf_start, pdf_end = resolved_start, resolved_end
    else:
        chunk_start, chunk_end = resolved_start, resolved_end
        pdf_start, pdf_end = _printed_range_to_pdf_pages(clean_book, resolved_start, resolved_end)

    chapter_inferred = False
    chapter_range_ambiguous = False
    if not resolved_chapter and chunk_start:
        inferred_chapter = _find_chapter_by_page_range(chapters, chunk_start, chunk_end)
        if inferred_chapter:
            chapter_record = inferred_chapter
            resolved_chapter = str(inferred_chapter.get("title") or "").strip()
            chapter_inferred = bool(resolved_chapter)
        else:
            chapter_range_ambiguous = True

    warnings: list[str] = []
    if chapter_inferred:
        warnings.append(f"已根据所选页码自动归入章节：{resolved_chapter}")
    elif chapter_range_ambiguous:
        warnings.append("所选页码范围无法唯一对应一个章节，请缩小范围或手动填写章节")
    if explicit_page_range and chunk_start and chunk_start != resolved_start:
        mapped_range = f"教材印刷页 {chunk_start}"
        if chunk_end and chunk_end != chunk_start:
            mapped_range += f"-{chunk_end}"
        warnings.append(f"所选 PDF 页已映射为{mapped_range}，优先读取已有教材 chunk")
    source_text, chunk_count = _text_from_source_packages(
        clean_book,
        resolved_chapter,
        chunk_start,
        chunk_end,
        source_mode=source_mode,
    )
    if source_text.strip():
        return ExtractedTextbookExerciseText(
            text=_normalize_text(source_text),
            provider="chapter-highlight-source-package",
            book_name=clean_book,
            chapter=resolved_chapter,
            page_start=resolved_start,
            page_end=resolved_end,
            chunk_count=chunk_count,
            warnings=warnings,
        )
    if resolved_start:
        selected_range = f"p{resolved_start}"
        if resolved_end and resolved_end != resolved_start:
            selected_range += f"-{resolved_end}"
        warnings.append(
            f"\u672a\u4ece source_package \u5339\u914d\u5230\u6240\u9009\u9875 {selected_range} \u7684\u53ef\u7528\u9898\u76ee\uff0c"
            "\u5df2\u6309\u540c\u4e00\u9875\u7801\u8303\u56f4\u8bfb\u53d6\u6559\u6750\u5bfc\u5165\u4ea7\u7269"
        )
    else:
        warnings.append("\u672a\u627e\u5230\u5df2\u751f\u6210\u91cd\u70b9\u9875\u7684 source_package\uff0c\u5df2\u5c1d\u8bd5\u8bfb\u53d6\u6559\u6750\u5bfc\u5165\u4ea7\u7269")

    chunk_text, chunk_count = _text_from_middle_chunks(clean_book, resolved_chapter, chunk_start, chunk_end, source_mode=source_mode)
    if chunk_text.strip():
        return ExtractedTextbookExerciseText(
            text=_normalize_text(chunk_text),
            provider="mineru-middle-chunks",
            book_name=clean_book,
            chapter=resolved_chapter,
            page_start=resolved_start,
            page_end=resolved_end,
            chunk_count=chunk_count,
            warnings=warnings,
        )
    warnings.append("未找到 MinerU middle_chunks，已尝试读取外部 OCR JSONL 产物")

    ocr_text, chunk_count = _text_from_external_ocr_jsonl(clean_book, resolved_chapter, chunk_start, chunk_end, source_mode=source_mode)
    if ocr_text.strip():
        return ExtractedTextbookExerciseText(
            text=_normalize_text(ocr_text),
            provider="external-ocr-jsonl",
            book_name=clean_book,
            chapter=resolved_chapter,
            page_start=resolved_start,
            page_end=resolved_end,
            chunk_count=chunk_count,
            warnings=warnings,
        )
    warnings.append("未找到可用的外部 OCR JSONL chunk，已降级为 PDF 文本层抽取")

    pdf_text = _text_from_pdf(clean_book, pdf_start, pdf_end)
    if pdf_text.strip():
        return ExtractedTextbookExerciseText(
            text=_normalize_text(pdf_text),
            provider="pdf-text-layer",
            book_name=clean_book,
            chapter=resolved_chapter,
            page_start=resolved_start,
            page_end=resolved_end,
            chunk_count=0,
            warnings=warnings,
        )

    if pdf_start:
        page_count = (pdf_end or pdf_start) - pdf_start + 1
        if page_count <= ON_DEMAND_OCR_MAX_PAGES:
            try:
                vision_text = _text_from_kimi_pdf_pages(clean_book, resolved_chapter, pdf_start, pdf_end)
            except Exception as exc:
                warnings.append(f"所选扫描页的 Kimi Vision OCR 失败：{str(exc)[:240]}")
            else:
                if vision_text.strip():
                    warnings.append("已有切分缺少可用页码映射，已按所选 PDF 页执行 Kimi Vision OCR")
                    return ExtractedTextbookExerciseText(
                        text=_normalize_text(vision_text),
                        provider="kimi-vision-pdf-pages",
                        book_name=clean_book,
                        chapter=resolved_chapter,
                        page_start=resolved_start,
                        page_end=resolved_end,
                        chunk_count=page_count,
                        warnings=warnings,
                    )
                warnings.append("Kimi Vision 未从所选扫描页返回可用文本")
        else:
            warnings.append(f"扫描页即时 OCR 每次最多支持 {ON_DEMAND_OCR_MAX_PAGES} 页，请缩小页码范围")
    else:
        warnings.append("PDF 文本层为空；请选择具体页码，系统才能对扫描页执行按页 OCR")
    return ExtractedTextbookExerciseText(
        text="",
        provider="none",
        book_name=clean_book,
        chapter=resolved_chapter,
        page_start=resolved_start,
        page_end=resolved_end,
        warnings=warnings,
    )


def _load_chapters(book_name: str) -> list[dict]:
    path = Path(PROGRESS_PATH) / book_name / "_chapters.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _find_chapter(chapters: list[dict], key: str) -> dict | None:
    key = str(key or "").strip()
    if not key:
        return None
    compact = _compact(key)
    for index, chapter in enumerate(chapters):
        title = str(chapter.get("title") or "").strip()
        if key in {title, str(index), str(index + 1)}:
            return chapter
        if compact and compact in _compact(title):
            return chapter
    return None


def _find_chapter_by_page_range(
    chapters: list[dict],
    page_start: int,
    page_end: int | None,
) -> dict | None:
    start_record = _find_chapter_by_page(chapters, page_start)
    end_record = _find_chapter_by_page(chapters, page_end or page_start)
    if start_record is None or end_record is None or start_record is not end_record:
        return None
    return start_record


def _find_chapter_by_page(chapters: list[dict], page: int) -> dict | None:
    for index, chapter in enumerate(chapters):
        start = _positive_int(chapter.get("page_number") or chapter.get("page"))
        if start is None:
            continue
        end = _positive_int(chapter.get("end_page"))
        if end is None and index + 1 < len(chapters):
            next_start = _positive_int(chapters[index + 1].get("page_number") or chapters[index + 1].get("page"))
            if next_start and next_start > start:
                end = next_start - 1
        if start <= page <= (end or start):
            return chapter
    return None

def _resolve_page_range(chapter: dict | None, page_start: int | None, page_end: int | None) -> tuple[int | None, int | None]:
    start = _positive_int(page_start)
    end = _positive_int(page_end)
    if not start and chapter:
        start = _positive_int(chapter.get("page_number") or chapter.get("page"))
    if not end and chapter:
        end = _positive_int(chapter.get("end_page")) or start
    if start and end and end < start:
        start, end = end, start
    return start, end


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _pdf_range_to_printed_pages(
    book_name: str,
    page_start: int | None,
    page_end: int | None,
) -> tuple[int | None, int | None]:
    if not page_start:
        return page_start, page_end
    pdf_path = _book_pdf_path(book_name)
    if not pdf_path.exists():
        return page_start, page_end
    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            start = _printed_number_from_pdf_page(doc, page_start) or page_start
            end_page = page_end or page_start
            end = _printed_number_from_pdf_page(doc, end_page) or end_page
    except Exception:
        return page_start, page_end
    return start, end


def _printed_range_to_pdf_pages(
    book_name: str,
    page_start: int | None,
    page_end: int | None,
) -> tuple[int | None, int | None]:
    if not page_start:
        return page_start, page_end
    pdf_path = _book_pdf_path(book_name)
    if not pdf_path.exists():
        return page_start, page_end
    try:
        import fitz

        with fitz.open(pdf_path) as doc:
            start = _pdf_page_from_printed_number(doc, page_start) or page_start
            end_page = page_end or page_start
            end = _pdf_page_from_printed_number(doc, end_page) or end_page
    except Exception:
        return page_start, page_end
    return start, end


def _printed_number_from_pdf_page(doc: Any, pdf_page: int) -> int | None:
    if pdf_page < 1 or pdf_page > doc.page_count:
        return None
    label = str(doc[pdf_page - 1].get_label() or "").strip()
    return _positive_int(label) if label.isdigit() else None


def _pdf_page_from_printed_number(doc: Any, printed_page: int) -> int | None:
    matches = doc.get_page_numbers(str(printed_page), only_one=True)
    return matches[0] + 1 if matches else None


def _text_from_source_packages(book_name: str, chapter: str, page_start: int | None, page_end: int | None, *, source_mode: str) -> tuple[str, int]:
    root = Path(PROGRESS_PATH) / book_name / "chapter_highlights"
    chunks: list[dict] = []
    if not root.exists():
        return "", 0
    for path in root.rglob("source_package.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if book_name and safe_book_name(str(payload.get("book_name") or book_name)) != book_name:
            continue
        source_chapter = str((payload.get("chapter") or {}).get("title") or "")
        if chapter and source_chapter and _compact(chapter) not in _compact(source_chapter):
            continue
        for group_name in ("practice_sections", "sections", "reference_sections"):
            for section in payload.get(group_name) or []:
                chunks.extend(_section_chunks(section, page_start, page_end, source_mode=source_mode))
    return _chunks_to_text(chunks), len(chunks)


def _text_from_middle_chunks(book_name: str, chapter: str, page_start: int | None, page_end: int | None, *, source_mode: str) -> tuple[str, int]:
    chunks: list[dict] = []
    seen_paths: set[Path] = set()
    for output_dir in _candidate_output_dirs(book_name):
        for path in output_dir.rglob("*middle_chunks*.json"):
            if path.resolve() in seen_paths:
                continue
            seen_paths.add(path.resolve())
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or item.get("content") or "").strip()
                if not text:
                    continue
                item_chapter = str(item.get("chapter") or item.get("section_title") or "")
                if source_mode != "all_pages" and _looks_like_toc_or_frontmatter(text, item_chapter):
                    continue
                if chapter and item_chapter and _compact(chapter) not in _compact(item_chapter):
                    continue
                page = _page_from_item(item)
                if not _page_in_range(page, page_start, page_end):
                    continue
                role = str(item.get("role") or "")
                if not _accept_text(text, role, source_mode):
                    continue
                chunks.append({"text": text, "page": page, "source_ref": _source_ref(item, page)})
    return _chunks_to_text(chunks), len(chunks)


def _candidate_output_dirs(book_name: str) -> list[Path]:
    candidates = [
        MINERU_OUTPUT_PATH / book_name,
        MINERU_OUTPUT_PATH / book_name / "hybrid_auto",
        Path("mineru_output") / book_name,
        Path("mineru_output") / book_name / "hybrid_auto",
    ]
    metadata = _load_metadata(book_name)
    configured_output = str(metadata.get("mineru_output_dir") or "").strip()
    if configured_output:
        output_path = Path(configured_output)
        candidates.insert(0, output_path)
        if output_path.parent != output_path:
            candidates.insert(1, output_path.parent)
    return [path for path in candidates if path.exists()]

def _text_from_external_ocr_jsonl(book_name: str, chapter: str, page_start: int | None, page_end: int | None, *, source_mode: str) -> tuple[str, int]:
    chunks: list[dict] = []
    for path in _external_ocr_jsonl_paths(book_name):
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except Exception:
                        continue
                    text = str(item.get("text") or item.get("content") or "").strip()
                    if not text:
                        continue
                    item_chapter = str(item.get("title") or item.get("chapter") or item.get("section_title") or "")
                    if source_mode != "all_pages" and _looks_like_toc_or_frontmatter(text, item_chapter):
                        continue
                    if chapter and item_chapter and _compact(chapter) not in _compact(item_chapter):
                        continue
                    page = _page_from_item(item)
                    if not _page_in_range(page, page_start, page_end):
                        continue
                    role = str(item.get("semantic_role") or item.get("role") or "")
                    if not _accept_text(text, role, source_mode):
                        continue
                    chunks.append({"text": text, "page": page, "source_ref": _source_ref(item, page)})
        except Exception:
            continue
    return _chunks_to_text(chunks), len(chunks)


def _external_ocr_jsonl_paths(book_name: str) -> list[Path]:
    meta = _load_metadata(book_name)
    aliases = {book_name, str(meta.get("book_name") or "").strip()}
    book_id_by_name = {
        "传感器短书": "sensor_core",
        "传感器长书": "sensor_reference",
        "误差理论与数据处理": "error_theory",
    }
    if book_name in book_id_by_name:
        aliases.add(book_id_by_name[book_name])
    paths: list[Path] = []
    configured = meta.get("source_artifacts") or []
    if isinstance(configured, str):
        configured = [configured]
    for value in configured if isinstance(configured, list) else []:
        path = Path(str(value))
        if path.exists() and path.suffix.lower() == ".jsonl":
            paths.append(path)
    configured_chunks = str(meta.get("source_chunks_path") or "").strip()
    if configured_chunks:
        path = Path(configured_chunks)
        if path.exists() and path.suffix.lower() == ".jsonl":
            paths.append(path)

    roots = [DATA_DIR / "imports", Path("data") / "imports"]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*_chunks.jsonl"):
            stem = path.stem.replace("_chunks", "")
            if stem in aliases or book_name in path.name:
                paths.append(path)
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _load_metadata(book_name: str) -> dict:
    path = Path(PROGRESS_PATH) / book_name / "metadata.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _page_from_source_markdown(item: dict) -> int | None:
    value = str(item.get("source_markdown") or "")
    match = re.search(r"(?:^|_)(\d+)(?:\D|$)", value)
    return _positive_int(match.group(1)) if match else None


def _section_chunks(section: dict, page_start: int | None, page_end: int | None, *, source_mode: str) -> list[dict]:
    title = str(section.get("title") or "")
    accepted: list[dict] = []
    for chunk in section.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        text = str(chunk.get("text") or chunk.get("content") or "").strip()
        if not text:
            continue
        page = _page_from_item(chunk)
        if not _page_in_range(page, page_start, page_end):
            continue
        role = str(chunk.get("role") or "")
        if source_mode == "exercise_sections" and _looks_like_exercise_section(title):
            accepted.append(chunk)
        elif _accept_text(text, role, source_mode):
            accepted.append(chunk)
    return accepted


def _accept_text(text: str, role: str, source_mode: str) -> bool:
    if source_mode == "all_pages":
        return True
    lowered_role = role.strip().lower()
    if source_mode == "examples":
        return lowered_role == "example" or _looks_like_example(text)
    if source_mode == "exercise_sections":
        return lowered_role in {"exercise", "example"} or _looks_like_problem(text)
    return _looks_like_problem(text)


def _looks_like_exercise_section(title: str) -> bool:
    compact = _compact(title)
    return any(marker in compact for marker in ("习题", "练习", "复习题", "思考题"))


def _looks_like_example(text: str) -> bool:
    from ingestion.document_workflows import example_label
    return any(example_label(line) for line in text.splitlines())


def _looks_like_problem(text: str) -> bool:
    return bool(re.search(r"(^|\n)\s*(?:例\s*\d|例题|习题|练习|复习题|思考题|\d+[-\.、）)]|\(\d+\)|（\d+）)", text))

def _looks_like_toc_or_frontmatter(text: str, title: str = "") -> bool:
    compact_title = _compact(title)
    if compact_title in {"目录", "目次"} or "目录" in compact_title:
        return True
    head = _compact(text[:600])
    if "目录" in head and ("第一章" in head or "第1章" in head) and ("第二章" in head or "第2章" in head):
        return True
    return any(marker in compact_title for marker in ("前言", "版权", "CIP", "图书在版编目"))


def _page_from_item(item: dict) -> int | None:
    if "page_idx" in item:
        try:
            page_idx = int(item.get("page_idx"))
        except (TypeError, ValueError):
            page_idx = -1
        if page_idx >= 0:
            return page_idx + 1
    for key in ("page", "page_number", "pdf_page", "page_no"):
        page = _positive_int(item.get(key))
        if page is not None:
            return page
    page = _page_from_source_markdown(item)
    if page is not None:
        return page
    source_ref = str(item.get("source_ref") or "")
    match = re.search(r"(?:^|[ /_-])p(?:age)?[ ._-]?(\d+)(?:\D|$)", source_ref, re.IGNORECASE)
    return _positive_int(match.group(1)) if match else None


def _page_in_range(page: int | None, page_start: int | None, page_end: int | None) -> bool:
    if not page_start:
        return True
    if page is None:
        return False
    end = page_end or page_start
    return page_start <= page <= end


def _source_ref(chunk: dict, page: int | None) -> str:
    ref = str(chunk.get("source_ref") or chunk.get("chunk_id") or "").strip()
    if page:
        return f"{ref or 'chunk'} / p{page}"
    return ref or "chunk"


def _chunks_to_text(chunks: list[dict]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        text = str(chunk.get("text") or chunk.get("content") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ref = _source_ref(chunk, _positive_int(chunk.get("page")))
        parts.append(f"[{ref}]\n{text}")
    return "\n\n".join(parts)


def _text_from_pdf(book_name: str, page_start: int | None, page_end: int | None) -> str:
    pdf_path = _book_pdf_path(book_name)
    if not pdf_path.exists():
        return ""
    import fitz

    parts: list[str] = []
    with fitz.open(pdf_path) as doc:
        start = max(1, page_start or 1)
        end = min(doc.page_count, page_end or start)
        for page_no in range(start, end + 1):
            text = doc[page_no - 1].get_text("text").strip()
            if text:
                parts.append(f"[Page {page_no}]\n{text}")
    return "\n\n".join(parts)


def _text_from_kimi_pdf_pages(
    book_name: str,
    chapter: str,
    page_start: int,
    page_end: int | None,
) -> str:
    pdf_path = _book_pdf_path(book_name)
    if not pdf_path.exists():
        return ""

    from ingestion.kimi_reader import KimiReader

    end = page_end or page_start
    text, _ = KimiReader(book_name).read_pages(
        pdf_path,
        page_start - 1,
        end,
        chapter=chapter,
        question="只转写所选页中的题目、条件、选项、公式和图表文字，不要解题",
        extract_keywords=False,
    )
    return text


def _book_pdf_path(book_name: str) -> Path:
    return BOOKS_PATH / f"{book_name}.pdf"


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def analyze_learning_unit_candidates(units: list[dict], *, book_name: str, subject: str, limit: int):
    """Analyze whole source units without resplitting formulas or subquestions."""
    from memory.exercise_importer import analyze_candidates
    candidates = []
    for unit in units[:limit]:
        source = f"{book_name} / {unit['chapter']} p{unit['page_start']}-{unit['page_end']} / {unit['unit_id']}"
        parsed = analyze_candidates([unit['text']], subject=subject, chapter=unit['chapter'], source=source, limit=1)
        if unit['truncated']:
            for candidate in parsed:
                candidate.validation_issues.append('incomplete_learning_unit')
                candidate.needs_review = True
        candidates.extend(parsed)
    return candidates
