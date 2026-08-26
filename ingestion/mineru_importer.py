"""Textbook import helpers backed by MinerU output.

The preferred path is MinerU 3.x API -> content/middle JSON -> chapters ->
chapter vector stores. If MinerU is unavailable, callers can explicitly fall
back to local TOC parsing, but the result is marked as non-OCR.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import config
from ingestion.chapter_splitter import ChapterSplitter
from ingestion.chunk_roles import assign_chunk_roles, load_kg_chunk_roles, role_distribution
from ingestion.document_adapters import MinerUAdapter, PdfTextAdapter, materialize_figure_assets
from ingestion.document_ir import CanonicalBook, persist_canonical_book, validate_canonical_book
from ingestion.lexical_index import write_book_index
from ingestion.index_pipeline import build_and_activate_book_index
from ingestion.acceptance_probes import generate_acceptance_probes, persist_acceptance_probes
from ingestion.mineru_client import MinerUClient
from ingestion.pdf_parser import PDFParser
from ingestion.vector_store import get_vector_store

ProgressCallback = Callable[[str, str, int | None], None]


@dataclass
class BookImportResult:
    book_name: str
    chapters: list[dict]
    used_mineru: bool
    indexed_chunks: int = 0
    output_dir: str = ""
    message: str = ""
    canonical_book: CanonicalBook | None = None


def import_textbook(
    pdf_path: Path,
    book_name: str,
    toc_pages: str = "",
    require_mineru: bool = True,
    on_progress: ProgressCallback | None = None,
    parse_method: str = "",
) -> BookImportResult:
    method = (parse_method or "").strip().lower()
    if method not in {"", "auto", "mineru", "local"}:
        raise ValueError(f"Unsupported textbook parse method: {parse_method}")
    if method == "local":
        return import_textbook_local(pdf_path, book_name, toc_pages, on_progress)

    if config.MINERU_API_URL:
        return _import_with_mineru(pdf_path, book_name, on_progress)
    if config.MINERU_CLI_COMMAND:
        return _import_with_mineru_cli(pdf_path, book_name, on_progress)
    if method == "mineru" or (not method and require_mineru):
        raise RuntimeError("未配置 MINERU_API_URL 或 MINERU_CLI_COMMAND，无法执行 MinerU 教材导入")
    return import_textbook_local(pdf_path, book_name, toc_pages, on_progress)


def import_textbook_local(
    pdf_path: Path,
    book_name: str,
    toc_pages: str = "",
    on_progress: ProgressCallback | None = None,
) -> BookImportResult:
    if on_progress:
        on_progress("local_parse", "使用本地目录解析，扫描件正文不会 OCR", 35)
    chapters = _parse_chapters_locally(pdf_path, book_name, toc_pages)
    canonical_book = PdfTextAdapter.from_chapters(
        chapters, book_name=book_name, source_file=pdf_path.name,
    )
    if on_progress:
        on_progress("indexing", "Building local textbook index", 75)
    output_dir = config.MINERU_OUTPUT_PATH / book_name / "local"
    output_dir.mkdir(parents=True, exist_ok=True)
    indexed = build_index_from_chapters(
        book_name, chapters, output_dir,
        canonical_book=canonical_book, canonical_progress_root=config.PROGRESS_PATH,
    )
    return BookImportResult(
        book_name=book_name,
        chapters=chapters,
        used_mineru=False,
        message="本地目录解析完成；扫描件正文未 OCR",
        indexed_chunks=indexed,
        output_dir=str(output_dir),
        canonical_book=canonical_book,
    )


def import_textbook_from_mineru_output(
    output_dir: Path,
    book_name: str,
    on_progress: ProgressCallback | None = None,
) -> BookImportResult:
    """Import an already-produced MinerU/Markdown output directory.

    This path is for rented GPU or external OCR workflows: the local app does
    not run MinerU, it only validates the produced files and builds the local
    chapter/vector assets.
    """
    output_dir = Path(output_dir)
    if not output_dir.exists() or not output_dir.is_dir():
        raise RuntimeError(f"MinerU output directory not found: {output_dir}")

    if on_progress:
        on_progress("structure", "Reading external OCR output", 35)
    chapters = chapters_from_mineru_output(output_dir, book_name)
    if not chapters:
        raise RuntimeError("No usable content_list, middle JSON, or markdown content found in OCR output")

    if on_progress:
        on_progress("indexing", "Building local chapter vector index", 70)
    canonical_book = _canonical_mineru_book(output_dir, chapters, book_name)
    indexed = build_index_from_chapters(
        book_name, chapters, output_dir,
        canonical_book=canonical_book, canonical_progress_root=config.PROGRESS_PATH,
    )
    return BookImportResult(
        book_name=book_name,
        chapters=chapters,
        used_mineru=True,
        indexed_chunks=indexed,
        output_dir=str(output_dir),
        message=f"External OCR output imported; indexed {indexed} text chunks",
        canonical_book=canonical_book,
    )

def _import_with_mineru(pdf_path: Path, book_name: str, on_progress: ProgressCallback | None) -> BookImportResult:
    output_dir = config.MINERU_OUTPUT_PATH / book_name / "hybrid_auto"
    output_dir.mkdir(parents=True, exist_ok=True)

    if on_progress:
        on_progress("mineru_submit", "提交到 MinerU 服务", 10)
    client = MinerUClient(config.MINERU_API_URL)
    task_id = client.submit_pdf(pdf_path, parse_method="auto")

    if on_progress:
        on_progress("mineru_running", f"MinerU 解析中：{task_id}", 20)

    def status_update(state: str, payload: dict[str, Any]) -> None:
        if on_progress:
            queued = payload.get("queued_ahead") or payload.get("queue_position")
            msg = f"MinerU 状态：{state}"
            if queued is not None:
                msg += f"，队列前方 {queued}"
            on_progress("mineru_running", msg, None)

    client.wait_for_task(task_id, config.MINERU_TASK_TIMEOUT_SECONDS, config.MINERU_TASK_POLL_SECONDS, on_progress=status_update)

    if on_progress:
        on_progress("mineru_download", "下载 MinerU 解析结果", 55)
    client.fetch_result(task_id, output_dir)

    if on_progress:
        on_progress("structure", "整理章节和正文块", 70)
    chapters = chapters_from_mineru_output(output_dir, book_name)
    used_mineru_output = bool(chapters)
    if not chapters:
        chapters = _parse_chapters_locally(pdf_path, book_name, "")

    if on_progress:
        on_progress("indexing", "写入章节向量索引", 84)
    canonical_book = (
        _canonical_mineru_book(output_dir, chapters, book_name)
        if used_mineru_output else PdfTextAdapter.from_chapters(
            chapters, book_name=book_name, source_file=pdf_path.name,
        )
    )
    indexed = build_index_from_chapters(
        book_name, chapters, output_dir,
        canonical_book=canonical_book, canonical_progress_root=config.PROGRESS_PATH,
    )

    return BookImportResult(
        book_name=book_name,
        chapters=chapters,
        used_mineru=True,
        indexed_chunks=indexed,
        output_dir=str(output_dir),
        message=f"MinerU 解析完成，已索引 {indexed} 个文本块",
        canonical_book=canonical_book,
    )


def _import_with_mineru_cli(pdf_path: Path, book_name: str, on_progress: ProgressCallback | None) -> BookImportResult:
    output_dir = config.MINERU_OUTPUT_PATH / book_name / "hybrid_auto"
    output_dir.mkdir(parents=True, exist_ok=True)
    command = config.MINERU_CLI_COMMAND.format(input=str(pdf_path), output=str(output_dir), book=book_name)
    if on_progress:
        on_progress("mineru_cli", "运行 MinerU CLI", 15)
    completed = subprocess.run(shlex.split(command, posix=False), capture_output=True, text=True, timeout=config.MINERU_TASK_TIMEOUT_SECONDS)
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "MinerU CLI failed").strip()
        raise RuntimeError(err[-1000:])
    if on_progress:
        on_progress("structure", "整理章节和正文块", 70)
    chapters = chapters_from_mineru_output(output_dir, book_name)
    if not chapters:
        raise RuntimeError("MinerU CLI 未生成可识别的 content_list/middle 输出")
    if on_progress:
        on_progress("indexing", "写入章节向量索引", 84)
    canonical_book = _canonical_mineru_book(output_dir, chapters, book_name)
    indexed = build_index_from_chapters(
        book_name, chapters, output_dir,
        canonical_book=canonical_book, canonical_progress_root=config.PROGRESS_PATH,
    )
    return BookImportResult(
        book_name=book_name,
        chapters=chapters,
        used_mineru=True,
        indexed_chunks=indexed,
        output_dir=str(output_dir),
        message=f"MinerU CLI 解析完成，已索引 {indexed} 个文本块",
        canonical_book=canonical_book,
    )

def _parse_chapters_locally(pdf_path: Path, book_name: str, toc_pages: str) -> list[dict]:
    parser = PDFParser(pdf_path)
    try:
        chapters = parser.extract_chapters(toc_pages.strip() if toc_pages else "")
    finally:
        parser.close()
    if not chapters:
        chapters = [{"title": f"{book_name} (全文)", "page_number": 1, "end_page": 0, "text": ""}]
    return chapters


def _canonical_mineru_book(output_dir: Path, chapters: list[dict], book_name: str) -> CanonicalBook:
    """Prefer MinerU's source blocks; retain a chapter adapter fallback."""
    canonical = MinerUAdapter.from_output_dir(output_dir, book_name=book_name)
    if canonical.blocks:
        return canonical
    return MinerUAdapter.from_chapters(chapters, book_name=book_name, source_file=Path(output_dir).name)


def chapters_from_mineru_output(output_dir: Path, book_name: str) -> list[dict]:
    content = _load_first_json(output_dir, ["*content_list*.json", "*content-list*.json"])
    if isinstance(content, list):
        chapters = _chapters_from_content_list(content, book_name)
        if chapters:
            return chapters

    middle = _load_first_json(output_dir, ["*middle*.json"])
    if isinstance(middle, dict):
        chapters = _chapters_from_middle_json(middle, book_name)
        if chapters:
            return chapters

    chapters = _chapters_from_markdown_output(output_dir, book_name)
    if chapters:
        return chapters
    return []


def extract_text_from_mineru_output(output_dir: Path) -> str:
    content = _load_first_json(output_dir, ["*content_list*.json", "*content-list*.json"])
    if isinstance(content, list):
        return _normalize_text("\n\n".join(_item_text(item) for item in content if _item_text(item)))
    middle = _load_first_json(output_dir, ["*middle*.json"])
    if isinstance(middle, dict):
        parts: list[str] = []
        for page in middle.get("pdf_info", []) or []:
            for block in page.get("para_blocks", []) or []:
                text = _collect_block_text(block)
                if text:
                    parts.append(text)
        return _normalize_text("\n\n".join(parts))
    markdowns = list(output_dir.rglob("*.md"))
    if markdowns:
        return _normalize_text("\n\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in markdowns))
    return ""



def _chapters_from_markdown_output(output_dir: Path, book_name: str) -> list[dict]:
    markdowns = sorted(output_dir.rglob("*.md"), key=lambda item: str(item).lower())
    parts: list[str] = []
    for md_path in markdowns:
        try:
            text = md_path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            continue
        if text:
            parts.append(text)
    if not parts:
        return []
    return _chapters_from_markdown_text("\n\n".join(parts), book_name)


def _chapters_from_markdown_text(markdown: str, book_name: str) -> list[dict]:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chapters: list[dict] = []
    current = _new_chapter(f"{book_name} (full text)", 1)
    saw_heading = False

    for line in lines:
        heading = re.match(r"^\s{0,3}(#{1,3})\s+(.+?)\s*$", line)
        if heading:
            title = re.sub(r"\s+", " ", heading.group(2)).strip(" #")
            if title and len(title) <= 120:
                if current["text"].strip():
                    chapters.append(current)
                current = _new_chapter(title, len(chapters) + 1)
                saw_heading = True
                continue
        current["text"] += line + "\n"

    if current["text"].strip() or not chapters:
        if not saw_heading:
            current["title"] = f"{book_name} (full text)"
        chapters.append(current)
    return _clean_chapters(chapters)

def _load_first_json(output_dir: Path, patterns: list[str]) -> Any:
    for pattern in patterns:
        for path in output_dir.rglob(pattern):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
    return None


def _chapters_from_content_list(items: list[dict], book_name: str) -> list[dict]:
    chapters: list[dict] = []
    current = _new_chapter(f"{book_name} (全文)", 1)
    saw_heading = False

    for item in items:
        text = _item_text(item)
        if not text:
            continue
        page = int(item.get("page_idx", 0) or 0) + 1
        text_level = item.get("text_level")
        is_heading = item.get("type") == "text" and isinstance(text_level, int) and 1 <= text_level <= 2
        if is_heading and _looks_like_chapter_heading(text):
            if current["text"].strip():
                current["end_page"] = max(int(current.get("end_page") or page), page)
                chapters.append(current)
            current = _new_chapter(text, page)
            saw_heading = True
            continue
        current["text"] += text + "\n\n"
        current["end_page"] = page

        current["chunks"].append({
            "text": text,
            "page_idx": page - 1,
            "bbox": item.get("bbox") or [],
            "block_type": item.get("type") or "text",
            "semantic_role": item.get("semantic_role") or item.get("role") or "reference",
            "equations": item.get("equations") or ([item.get("latex")] if item.get("latex") else []),
            "source_markdown": item.get("source_markdown") or "",
        })
    if current["text"].strip() or not chapters:
        if not saw_heading:
            current["title"] = f"{book_name} (全文)"
        chapters.append(current)
    return _clean_chapters(chapters)


def _chapters_from_middle_json(middle: dict, book_name: str) -> list[dict]:
    items: list[dict] = []
    for page in middle.get("pdf_info", []) or []:
        page_idx = page.get("page_idx", 0)
        for block in page.get("para_blocks", []) or []:
            text = _collect_block_text(block)
            if text:
                items.append({
                    "type": block.get("type") or "text",
                    "text": text,
                    "page_idx": page_idx,
                    "bbox": block.get("bbox") or [],
                    "equations": block.get("equations") or [],
                })
    return _chapters_from_content_list(items, book_name) if items else []


def _new_chapter(title: str, page: int) -> dict:
    return {"title": title.strip(), "page_number": page, "end_page": page, "text": "", "chunks": []}


def _clean_chapters(chapters: list[dict]) -> list[dict]:
    cleaned = []
    for ch in chapters:
        title = re.sub(r"\s+", " ", ch.get("title", "")).strip()
        text = ch.get("text", "").strip()
        if title:
            cleaned.append({**ch, "title": title, "text": text})
    return cleaned


def _looks_like_chapter_heading(text: str) -> bool:
    compact = text.strip()
    if len(compact) > 80:
        return False
    patterns = [
        r"^第[一二三四五六七八九十百\d]+[章节篇讲]",
        r"^\d+(\.\d+){0,2}\s+",
        r"^Chapter\s+\d+",
    ]
    return any(re.search(pattern, compact, re.IGNORECASE) for pattern in patterns)


def _item_text(item: dict) -> str:
    parts: list[str] = []
    for key in ("text", "code_body", "latex"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    for key in ("table_caption", "table_footnote", "image_caption", "image_footnote"):
        value = item.get(key)
        if isinstance(value, list):
            parts.extend(str(v).strip() for v in value if str(v).strip())
        elif isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n".join(parts)


def _collect_block_text(block: dict) -> str:
    parts: list[str] = []
    for line in block.get("lines", []) or []:
        for span in line.get("spans", []) or []:
            content = span.get("content")
            if isinstance(content, str) and content.strip():
                parts.append(content.strip())
    for child in block.get("blocks", []) or []:
        child_text = _collect_block_text(child)
        if child_text:
            parts.append(child_text)
    return " ".join(parts).strip()


def _coalesce_external_ocr_chapters(chapters: list[dict], book_name: str) -> list[dict]:
    """Collapse legacy heading-per-record OCR imports into book chapters."""
    if len(chapters) < 80 or sum(item.get("source") == "external_ocr_jsonl" for item in chapters[:120]) < 20:
        return chapters
    grouped, current, current_number = [], None, ""
    for item in chapters:
        title = str(item.get("title") or "").strip()
        text = str(item.get("text") or "").strip()
        match = re.match(r"^(\d{1,2})(?:\.|\s)", title)
        number = match.group(1) if match else current_number
        if number and number != current_number:
            current_number = number
            current = {
                "title": f"\u7b2c{number}\u7ae0", "text_parts": [],
                "page_number": item.get("page_number") or item.get("page") or 1,
            }
            grouped.append(current)
        if current is None:
            current = {"title": book_name, "text_parts": [], "page_number": 1}
            grouped.append(current)
        if text:
            current["text_parts"].append(f"## {title}\n\n{text}" if title and not text.lstrip().startswith("#") else text)
    return [
        {"title": item["title"], "text": "\n\n".join(item["text_parts"]), "page_number": item["page_number"]}
        for item in grouped if item["text_parts"]
    ]


def build_index_from_chapters(
    book_name: str,
    chapters: list[dict],
    output_dir: Path,
    *,
    canonical_book: CanonicalBook | None = None,
    canonical_progress_root: str | Path | None = None,
) -> int:
    """Build every textbook index from the canonical Document IR contract.

    ``chapters`` remains a compatibility input for maintenance/tests, but it is
    adapted to ``CanonicalBook`` at this boundary. There is no independent
    chapter-string splitter/index path after this point.
    """
    chapters = _coalesce_external_ocr_chapters(chapters, book_name)
    splitter = ChapterSplitter()
    all_chunks: list[dict] = []
    chapter_groups: list[tuple[str, list[dict], dict[str, str]]] = []

    if canonical_book is None:
        has_native_blocks = any(
            isinstance(chapter.get("chunks"), list) and chapter.get("chunks")
            for chapter in chapters
        )
        adapter = MinerUAdapter if has_native_blocks else PdfTextAdapter
        canonical_book = adapter.from_chapters(
            chapters,
            book_name=book_name,
            source_file=str(Path(output_dir).name),
        )
    if canonical_progress_root is not None:
        materialize_figure_assets(
            canonical_book, source_root=output_dir, progress_root=canonical_progress_root,
        )
    report = validate_canonical_book(canonical_book)
    if not report.valid:
        errors = [issue.code for issue in report.issues if issue.severity == "error"]
        raise RuntimeError(f"canonical textbook failed ingestion validation: {errors}")
    if canonical_progress_root is not None:
        # The durable IR and its intake report are the release gate. No vector
        # or lexical asset is touched before both files exist.
        persist_canonical_book(canonical_book, progress_root=canonical_progress_root)
        probe_report = persist_acceptance_probes(
            canonical_book, progress_root=canonical_progress_root,
        )
    else:
        probe_report = generate_acceptance_probes(canonical_book)

    vs = get_vector_store()
    kg_roles = load_kg_chunk_roles(book_name)
    all_chunks = splitter.split_canonical_book(canonical_book)
    indexable_chunks = [
        dict(chunk) for chunk in all_chunks if not bool(chunk.get("retrieval_excluded"))
    ]
    for chunk_index, chunk in enumerate(indexable_chunks):
        chunk["chunk_index"] = chunk_index
        chunk["prev_chunk_id"] = indexable_chunks[chunk_index - 1]["chunk_id"] if chunk_index else ""
        chunk["next_chunk_id"] = (
            indexable_chunks[chunk_index + 1]["chunk_id"]
            if chunk_index + 1 < len(indexable_chunks) else ""
        )

    def add_group(title: str, chunks: list[dict]) -> None:
        if not chunks:
            return
        source_roles = {
            str(chunk.get("chunk_id") or ""): str(chunk.get("role") or "")
            for chunk in chunks if chunk.get("role") not in {None, "", "reference"}
        }
        chunk_roles = assign_chunk_roles(chunks, {**source_roles, **kg_roles})
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id", "")
            chunk["role"] = chunk_roles.get(chunk_id, "reference")
        chapter_groups.append((title, chunks, chunk_roles))
        distribution = role_distribution(chunk_roles)
        if distribution:
            print(f"[index] {title}: roles {distribution}", flush=True)

    grouped: dict[str, list[dict]] = {}
    for chunk in indexable_chunks:
        title = str(chunk.get("chapter") or book_name)
        grouped.setdefault(title, []).append(chunk)
    for title, chunks in grouped.items():
        add_group(title, chunks)

    roles_by_chunk_id = {
        str(chunk.get("chunk_id") or ""): str(chunk.get("role") or "reference")
        for chunk in indexable_chunks
    }
    for chunk in all_chunks:
        chunk_id = str(chunk.get("chunk_id") or "")
        if chunk_id in roles_by_chunk_id:
            chunk["role"] = roles_by_chunk_id[chunk_id]

    if all_chunks:
        (output_dir / f"{book_name}_middle_chunks.json").write_text(
            json.dumps(all_chunks, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if indexable_chunks:
        if hasattr(vs, "_client") and hasattr(vs, "_map_file"):
            manifest = build_and_activate_book_index(
                vs, book_name,
                [(title, group) for title, group, _roles in chapter_groups],
                indexable_chunks,
                acceptance_probes=probe_report["cases"],
                specialty_inventory=probe_report["inventory"],
            )
            if int(manifest.get("chunk_count", 0)) != len(indexable_chunks):
                raise RuntimeError("activated textbook index failed manifest validation")
        else:
            # Lightweight adapters retain the legacy API; production always stages.
            for title, group, roles in chapter_groups:
                vs.build_chapter_store(title, group, chunk_roles=roles, book_name=book_name)
            if hasattr(vs, "get_book_index_stats"):
                write_book_index(book_name, indexable_chunks)
            if hasattr(vs, "build_book_aggregate_store"):
                vs.build_book_aggregate_store(book_name, indexable_chunks)
            stats = vs.get_book_index_stats(book_name) if hasattr(vs, "get_book_index_stats") else {}
            if stats and (not stats.get("healthy") or int(stats.get("chunk_count", 0)) < len(indexable_chunks)):
                raise RuntimeError(
                    f"textbook index validation failed: expected={len(indexable_chunks)}, actual={stats.get('chunk_count', 0)}"
                )
    return len(indexable_chunks)

def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
