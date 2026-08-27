"""Books API: textbook management and asynchronous MinerU import jobs."""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.job_manager import JobCancelled, get_job_manager
from backend.services.kg_enhancement_jobs import start_kg_enhancement_job
from backend.book_lifecycle import BookLifecycleService
from backend.services.book_read_cache import BookReadCache
from backend.services.book_readiness import derive_book_readiness
from backend.services.book_chapters import (
    chapters_from_embedded_toc,
    chapters_from_ocr_headings,
    format_chapter,
    looks_like_external_ocr_chunk_titles,
)
from backend.schemas import PreReadStatusOut
from config import BOOKS_PATH, DATA_DIR, MINERU_OUTPUT_PATH, PROGRESS_PATH, VECTOR_DB_PATH
from ingestion.background_reader import BackgroundReader
from ingestion.document_ir import load_canonical_book, validate_canonical_book
from ingestion.vector_store import get_vector_store
from ingestion.mineru_importer import build_index_from_chapters, import_textbook, import_textbook_from_mineru_output, import_textbook_local
from ingestion.mineru_runtime import inspect_mineru_runtime
from ingestion.pdf_parser import PDFParser
from utils.json_io import atomic_write_json
from utils.path_safety import safe_book_name, safe_child_path
from utils.resource_limits import (
    MAX_BOOK_PDF_BYTES,
    MAX_OUTPUT_ZIP_BYTES,
    copy_stream_limited,
    ensure_disk_space,
    inspect_zip_limits,
    validate_zip_paths,
)
from utils.subject_catalog import normalize_subject_value

router = APIRouter(prefix="/books", tags=["books"])


class BookUpdateRequest(BaseModel):
    subject: str | None = None
    display_name: str | None = None

    book_role: str | None = None
    rag_priority: float | None = None
    resource_group: str | None = None

_book_state: dict = {
    "current_book": None,
    "chapters": [],
    "book_pdf_path": None,
    "bg_reader": None,
}

IMPORT_JOB_TYPE = "textbook_import"
OUTPUT_UPLOAD_DIR = DATA_DIR / "uploads" / "mineru_outputs"
BOOK_UPLOAD_DIR = DATA_DIR / "uploads" / "book_imports"
_book_read_cache = BookReadCache()
_job_manager = get_job_manager()
_lifecycle = BookLifecycleService(PROGRESS_PATH)
_job_manager.import_legacy_json_jobs(
    IMPORT_JOB_TYPE,
    Path(PROGRESS_PATH) / "import_jobs",
    input_keys=("book_name", "file_path", "toc_pages", "pre_read", "require_mineru", "parse_method", "subject", "extract_concepts"),
)


def _get_books() -> list[Path]:
    return _book_read_cache.list_pdfs(Path(BOOKS_PATH))


def _invalidate_book_read_cache() -> None:
    _book_read_cache.clear()

def _known_book_names(include_archived: bool = False) -> list[str]:
    names = {p.stem for p in _get_books()}
    progress_root = Path(PROGRESS_PATH)
    if progress_root.exists():
        for child in progress_root.iterdir():
            if child.is_dir() and (child / "_chapters.json").exists():
                names.add(child.name)
    if not include_archived:
        names = {name for name in names if not _read_book_meta(name).get("archived")}
    return sorted(names)

def _compute_fast_book_index_stats(book_name: str) -> dict:
    normalized = safe_book_name(book_name)
    stats = {"book_name": normalized, "collection_count": 0, "chunk_count": 0, "healthy": False}

    map_path = Path(VECTOR_DB_PATH) / "_chapter_map.json"
    try:
        raw = _book_read_cache.read_json(map_path, {})
        if isinstance(raw, dict):
            for value in raw.values():
                if not isinstance(value, dict):
                    continue
                if value.get("book_name") == normalized and value.get("kind") != "book_aggregate":
                    stats["collection_count"] += 1
    except Exception as exc:
        stats["error"] = str(exc)

    try:
        from ingestion.index_pipeline import load_index_manifest
        from ingestion.lexical_index import index_path, load_book_index

        stats["lexical_chunk_count"] = len(load_book_index(normalized))
        stats["lexical_ready"] = index_path(normalized).exists() and stats["lexical_chunk_count"] > 0
        stats["source_fallback_active"] = not stats["lexical_ready"] and stats["lexical_chunk_count"] > 0
        manifest = load_index_manifest(normalized)
        stats["index_version"] = str(manifest.get("index_version") or "")
        stats["index_schema"] = int(manifest.get("schema_version", 0) or 0)
    except Exception:
        stats["lexical_chunk_count"] = 0
        stats["lexical_ready"] = False
        stats["source_fallback_active"] = False
        stats["index_version"] = ""
        stats["index_schema"] = 0

    stats["chunk_count"] = stats["lexical_chunk_count"]
    stats["vector_ready"] = stats["collection_count"] > 0
    stats["healthy"] = stats["vector_ready"] or stats["lexical_ready"] or stats["source_fallback_active"]
    stats["status"] = "ready" if stats["vector_ready"] and stats["lexical_ready"] else ("degraded" if stats["healthy"] else "missing")
    return stats


def _fast_book_index_stats(book_name: str) -> dict:
    normalized = safe_book_name(book_name)
    map_path = Path(VECTOR_DB_PATH) / "_chapter_map.json"
    lexical_path = Path(VECTOR_DB_PATH) / "_lexical" / f"{normalized}.json"
    return _book_read_cache.index_stats(
        normalized,
        map_path,
        lexical_path,
        lambda: _compute_fast_book_index_stats(normalized),
    )

def _book_pdf_path(name: str) -> Path | None:
    candidate = BOOKS_PATH / f"{Path(name).name}.pdf"
    return candidate if candidate.exists() else None

def _load_raw_chapters(name: str) -> list[dict]:
    """Load persisted OCR units without UI-only TOC normalization."""
    path = safe_child_path(PROGRESS_PATH, safe_book_name(name), "_chapters.json")
    data = _book_read_cache.read_json(path, [])
    return data if isinstance(data, list) else []

def _load_chapters(name: str) -> list[dict]:
    path = safe_child_path(PROGRESS_PATH, safe_book_name(name), "_chapters.json")
    data = _book_read_cache.read_json(path, [])
    return _normalize_loaded_chapters(data if isinstance(data, list) else [])

def _normalize_loaded_chapters(chapters: list[dict]) -> list[dict]:
    if not looks_like_external_ocr_chunk_titles(chapters):
        return chapters
    toc = chapters_from_embedded_toc(chapters)
    return toc or chapters_from_ocr_headings(chapters) or chapters

def _save_chapters(name: str, chapters: list[dict]) -> None:
    path = safe_child_path(PROGRESS_PATH, safe_book_name(name), "_chapters.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    # External OCR produces one record per heading/chunk. Persist the real TOC
    # instead so highlight/exercise UIs never mistake hundreds of chunks for chapters.
    atomic_write_json(path, _normalize_loaded_chapters(chapters))
    _invalidate_book_read_cache()


def _book_meta_path(name: str) -> Path:
    return safe_child_path(PROGRESS_PATH, safe_book_name(name), "metadata.json")


def _read_book_meta(name: str) -> dict:
    data = _book_read_cache.read_json(_book_meta_path(name), {})
    return data if isinstance(data, dict) else {}

def _write_book_meta(name: str, **updates) -> dict:
    _, meta = _lifecycle.update_metadata(name, **updates)
    _invalidate_book_read_cache()
    return meta


def _ensure_book_identity(name: str) -> tuple[dict, dict]:
    return _lifecycle.ensure_identity(name, _read_book_meta(name))


def migrate_book_identities() -> list[dict]:
    """Assign stable IDs to existing textbooks without moving their assets."""
    migrated = []
    for name in _known_book_names(include_archived=True):
        meta_path = _book_meta_path(name)
        if meta_path.exists():
            try:
                raw = json.loads(meta_path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("metadata must be an object")
            except Exception as exc:
                migrated.append({"storage_name": name, "status": "skipped", "error": str(exc)})
                continue
        identity, _ = _ensure_book_identity(name)
        migrated.append({**identity, "migration_status": "ready"})
    return migrated

def _resolve_book_reference(reference: str, *, include_archived: bool = False) -> str | None:
    record = _lifecycle.resolve(reference, include_archived=include_archived)
    if record:
        storage_name = str(record.get("storage_name") or "")
        if storage_name in _known_book_names(include_archived=include_archived):
            return storage_name
    candidate = safe_book_name(reference)
    return candidate if candidate in _known_book_names(include_archived=include_archived) else None


def _book_subject(name: str) -> str:
    return str(_read_book_meta(name).get("subject", "")).strip()


def _safe_pdf_name(filename: str) -> str:
    raw = Path(filename or "textbook.pdf").name
    stem = re.sub(r"[^\w\-.\u4e00-\u9fff]+", "_", Path(raw).stem).strip("._") or "textbook"
    return f"{stem[:90]}.pdf"


def _save_upload(file: UploadFile) -> Path:
    """Save a new PDF in staging; it becomes a library book only after import."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise ValueError("\u8bf7\u4e0a\u4f20 PDF \u6559\u6750")
    BOOKS_PATH.mkdir(parents=True, exist_ok=True)
    BOOK_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = BOOK_UPLOAD_DIR / _safe_pdf_name(file.filename)
    base = dest.with_suffix("")
    suffix = dest.suffix
    counter = 1
    reserved = set(_known_book_names(include_archived=True))
    while dest.exists() or (BOOKS_PATH / dest.name).exists() or dest.stem in reserved:
        dest = Path(f"{base}_{counter}{suffix}")
        counter += 1
    copy_stream_limited(file.file, dest, max_bytes=MAX_BOOK_PDF_BYTES)
    return dest


def _promote_uploaded_pdf(staged_path: Path) -> Path:
    BOOKS_PATH.mkdir(parents=True, exist_ok=True)
    final_path = BOOKS_PATH / staged_path.name
    if final_path.exists():
        raise RuntimeError(f"教材文件已存在：{final_path.name}")
    shutil.move(str(staged_path), str(final_path))
    return final_path


def _cleanup_new_book_import(book_name: str, *uploaded_paths: Path | None) -> None:
    """Remove only artifacts belonging to a not-yet-committed, uniquely named import."""
    safe = safe_book_name(book_name)
    for path in uploaded_paths:
        if path and path.exists():
            try:
                path.unlink() if path.is_file() else shutil.rmtree(path)
            except OSError:
                pass
    for path in (
        safe_child_path(PROGRESS_PATH, safe),
        safe_child_path(MINERU_OUTPUT_PATH, safe),
    ):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    safe_child_path(VECTOR_DB_PATH, "_lexical", f"{safe}.json").unlink(missing_ok=True)
    try:
        _lifecycle._delete_vector_assets(safe)
    except Exception:
        pass
    if _book_state.get("current_book") == safe:
        _book_state.update(current_book=None, chapters=[], book_pdf_path=None)


def _read_job(job_id: str) -> dict | None:
    return _job_manager.get_job(job_id, job_type=IMPORT_JOB_TYPE)


def _update_job(job_id: str, **updates) -> dict:
    return _job_manager.update_job(job_id, **updates)


def _set_current_book(book_name: str, chapters: list[dict], pdf_path: Path | None) -> None:
    _book_state["current_book"] = book_name
    _book_state["chapters"] = chapters
    _book_state["book_pdf_path"] = str(pdf_path) if pdf_path else ""


def _start_optional_concept_extraction(book_name: str, enabled: bool) -> tuple[dict | None, str]:
    if not enabled:
        return None, ""
    try:
        job, _created = start_kg_enhancement_job(book_name, allow_external_llm=True)
        return job, ""
    except Exception as exc:
        # The searchable textbook is already ready; concept extraction is auxiliary.
        return None, str(exc)


def _run_import_job(job_id: str, pdf_path: Path, toc_pages: str, pre_read: bool, require_mineru: bool, subject: str = "", extract_concepts: bool = False, parse_method: str = "") -> None:
    book_name = pdf_path.stem
    final_pdf: Path | None = None

    def progress(stage: str, message: str, percent: int | None = None) -> None:
        _job_manager.raise_if_cancelled(job_id)
        payload = {"stage": stage, "message": message}
        if percent is not None:
            payload["progress"] = max(0, min(100, int(percent)))
        _update_job(job_id, **payload)

    try:
        progress("started", "\u51c6\u5907\u5bfc\u5165\u6559\u6750", 3)
        result = import_textbook(pdf_path, book_name, toc_pages=toc_pages, require_mineru=require_mineru, on_progress=progress, parse_method=parse_method)
        _job_manager.raise_if_cancelled(job_id)
        ingestion_report: dict = {}
        ingestion_warning = ""
        if result.canonical_book is not None:
            try:
                # The importer persists the canonical IR before index I/O. The
                # API only exposes the deterministic report in job metadata.
                report = validate_canonical_book(result.canonical_book)
                ingestion_report = report.to_dict()
            except Exception as exc:
                ingestion_warning = str(exc)
        final_pdf = _promote_uploaded_pdf(pdf_path)
        _save_chapters(book_name, result.chapters)
        _write_book_meta(
            book_name,
            subject=normalize_subject_value(subject),
            import_source="mineru" if result.used_mineru else "local_pdf",
            mineru_output_dir=result.output_dir,
            canonical_ir_status=("ready" if ingestion_report.get("valid") else "needs_review") if ingestion_report else "unavailable",
        )
        _set_current_book(book_name, result.chapters, final_pdf)
        if pre_read and result.chapters and not result.used_mineru:
            _start_pre_read(book_name, result.chapters, final_pdf)
        index_status = get_vector_store().get_book_index_stats(book_name)
        concept_job, concept_warning = _start_optional_concept_extraction(book_name, extract_concepts)
        _job_manager.complete_job(
            job_id,
            stage="completed",
            progress=100,
            message=result.message or "教材导入完成",
            result={
                "name": book_name,
                "chapter_count": len(result.chapters),
                "used_mineru": result.used_mineru,
                "indexed_chunks": result.indexed_chunks,
                "index_status": index_status,
                "output_dir": result.output_dir,
                "subject": _book_subject(book_name),
                "concept_job_id": concept_job.get("id", "") if concept_job else "",
                "concept_extraction_warning": concept_warning,
                "ingestion_report": ingestion_report,
                "ingestion_report_warning": ingestion_warning,
            },
        )
    except JobCancelled as exc:
        _cleanup_new_book_import(book_name, pdf_path, final_pdf)
        _update_job(job_id, status="cancelled", stage="cancelled", progress=100, message=str(exc) or "\u6559\u6750\u5bfc\u5165\u5df2\u53d6\u6d88", error=str(exc))
    except Exception as exc:
        _cleanup_new_book_import(book_name, pdf_path, final_pdf)
        _update_job(job_id, status="failed", stage="failed", progress=100, message=f"\u6559\u6750\u5bfc\u5165\u5931\u8d25\uff1a{exc}", error=str(exc))


@router.get("/list")
def list_books(include_archived: bool = False):
    data = []
    for name in _known_book_names(include_archived=include_archived):
        pdf_path = _book_pdf_path(name)
        index_status = _fast_book_index_stats(name)
        identity, meta = _ensure_book_identity(name)
        readiness = derive_book_readiness(
            name,
            index_status=index_status,
            progress_root=PROGRESS_PATH,
            vector_db_root=VECTOR_DB_PATH,
        )
        data.append({
            "book_id": identity["book_id"],
            "name": name,
            "storage_name": name,
            "display_name": identity["display_name"],
            "displayName": identity["display_name"],
            "lifecycle_status": identity["status"],
            "path": str(pdf_path) if pdf_path else "",
            "size": pdf_path.stat().st_size if pdf_path else 0,
            "book_role": str(meta.get("book_role", "standalone")),
            "rag_priority": float(meta.get("rag_priority", 1.0) or 1.0),
            "resource_group": str(meta.get("resource_group", "")),
            "subject": str(meta.get("subject", "")).strip(),
            "has_pdf": bool(pdf_path or _source_pdf_path(name)),
            "chapter_count": len(_load_chapters(name)),
            "index_status": index_status,
            "readiness": readiness,
        })
    return {"success": True, "data": data}


@router.get("/import-capabilities")
def import_capabilities():
    import config as config_module

    return {
        "success": True,
        "data": {
            "mineru": inspect_mineru_runtime(
                config_module.MINERU_API_URL,
                config_module.MINERU_CLI_COMMAND,
            ),
            "local_pdf": {"available": True, "limitation": "text_layer_only"},
            "output_bundle": {"available": True},
        },
    }


@router.post("/{book_name}/reindex")
def reindex_book(book_name: str):
    """Rebuild derived retrieval assets while preserving OCR/source data."""
    name = _resolve_book_reference(book_name)
    if not name:
        return {"success": False, "message": f"Textbook not found: {book_name}"}
    chapters = _load_raw_chapters(name)
    if not chapters:
        return {"success": False, "message": "No persisted textbook content found"}
    output_dir = safe_child_path(PROGRESS_PATH, name)
    try:
        try:
            canonical_book = load_canonical_book(name, progress_root=PROGRESS_PATH)
        except FileNotFoundError:
            canonical_book = None
        indexed = build_index_from_chapters(
            name,
            chapters,
            output_dir,
            canonical_book=canonical_book,
            canonical_progress_root=PROGRESS_PATH,
        )
        stats = get_vector_store().get_book_index_stats(name)
    except Exception as exc:
        return {"success": False, "message": f"Reindex failed: {exc}"}
    _write_book_meta(name, indexed_chunks=indexed, index_schema=5)
    return {
        "success": True,
        "message": f"Indexed {indexed} chunks",
        "data": stats,
    }


@router.get("/current")
def get_current_book():
    name = _book_state.get("current_book")
    if not name:
        return {"success": False, "message": "\u672a\u9009\u62e9\u6559\u6750"}
    chapters = _book_state.get("chapters", [])
    return {"success": True, "data": {"name": name, "subject": _book_subject(name), "chapter_count": len(chapters), "chapters": [format_chapter(c) for c in chapters]}}

def _source_pdf_path(book_name: str) -> Path | None:
    safe = safe_book_name(book_name)
    candidates: list[Path] = []
    direct = _book_pdf_path(safe)
    if direct:
        candidates.append(direct)

    ocr_needed_aliases = {
        "传感器短书": "CGQ_1.pdf",
        "传感器长书": "CGQ_2.pdf",
        "误差理论与数据处理": "WC.pdf",
    }
    alias_file = ocr_needed_aliases.get(safe)
    if alias_file:
        candidates.append(Path("D:/OCR_NEEDED") / alias_file)

    meta = _read_book_meta(safe)
    output_dir = meta.get("mineru_output_dir")
    if output_dir:
        root = Path(str(output_dir))
        candidates.extend(sorted(root.rglob("origin.pdf"), key=lambda item: len(str(item))))
        candidates.extend(sorted(root.rglob("*.pdf"), key=lambda item: ("origin" not in item.name.lower(), len(str(item)))))
    candidates.extend(sorted((MINERU_OUTPUT_PATH / safe).rglob("origin.pdf")) if (MINERU_OUTPUT_PATH / safe).exists() else [])
    for path in candidates:
        try:
            if path.exists() and path.is_file() and path.suffix.lower() == ".pdf":
                return path
        except Exception:
            continue
    return None


@router.get("/{book_name}/source-pdf")
def source_pdf(book_name: str):
    name = _resolve_book_reference(book_name, include_archived=True)
    pdf_path = _source_pdf_path(name) if name else None
    if not pdf_path:
        return {"success": False, "message": "未找到该教材对应的 origin.pdf 或源 PDF"}
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(pdf_path.name)}"},
    )


@router.patch("/{book_name}")
def update_book(book_name: str, req: BookUpdateRequest):
    name = _resolve_book_reference(book_name)
    if not name:
        return {"success": False, "message": f"Textbook not found: {book_name}"}

    if req.display_name is not None:
        try:
            _lifecycle.rename_display(name, req.display_name)
        except ValueError as exc:
            return {"success": False, "message": str(exc)}

    updates = {}
    if req.subject is not None:
        updates["subject"] = normalize_subject_value(req.subject)
    if req.book_role is not None:
        role = req.book_role.strip().lower()
        if role not in {"standalone", "core", "reference"}:
            return {"success": False, "message": "book_role must be standalone, core, or reference"}
        updates["book_role"] = role
        if req.rag_priority is None:
            # A role change resets any legacy auto-generated weight to neutral.
            # Callers that intentionally manage a per-book override can submit
            # role and rag_priority together in the same request.
            updates["rag_priority"] = 1.0
    if req.rag_priority is not None:
        updates["rag_priority"] = max(0.05, min(2.0, float(req.rag_priority)))
    if req.resource_group is not None:
        updates["resource_group"] = req.resource_group.strip()[:100]
    meta = _write_book_meta(name, **updates) if updates else _read_book_meta(name)
    identity, meta = _ensure_book_identity(name)
    pdf_path = _book_pdf_path(name)
    chapters = _load_chapters(name)
    return {
        "success": True,
        "message": "教材信息已更新",
        "data": {
            "book_id": identity["book_id"],
            "name": name,
            "storage_name": name,
            "display_name": identity["display_name"],
            "displayName": identity["display_name"],
            "lifecycle_status": identity["status"],
            "path": str(pdf_path) if pdf_path else "",
            "size": pdf_path.stat().st_size if pdf_path else 0,
            "subject": str(meta.get("subject", "")).strip(),
            "has_pdf": bool(pdf_path or _source_pdf_path(name)),
            "chapter_count": len(chapters),
            "book_role": str(meta.get("book_role", "standalone")),
            "rag_priority": float(meta.get("rag_priority", 1.0) or 1.0),
            "resource_group": str(meta.get("resource_group", "")),
        },
    }


@router.delete("/{book_name}")
def archive_book(book_name: str):
    name = _resolve_book_reference(book_name, include_archived=True)
    if not name:
        return {"success": False, "message": f"Textbook not found: {book_name}"}
    identity, _ = _lifecycle.archive(name)
    if _book_state.get("current_book") == name:
        _book_state["current_book"] = None
        _book_state["chapters"] = []
        _book_state["book_pdf_path"] = None
    return {
        "success": True,
        "message": "教材已归档；本地文件、索引和学习记录均未删除。",
        "data": {**identity, "name": name, "archived": True},
    }


@router.post("/{book_name}/restore")
def restore_book(book_name: str):
    name = _resolve_book_reference(book_name, include_archived=True)
    if not name:
        return {"success": False, "message": f"Textbook not found: {book_name}"}
    identity, _ = _lifecycle.restore(name)
    return {
        "success": True,
        "message": "教材已恢复到资料库。",
        "data": {**identity, "name": name, "archived": False},
    }


@router.get("/{book_name}/lifecycle-preview")
def lifecycle_preview(book_name: str):
    try:
        return {"success": True, "data": _lifecycle.preview_purge(book_name)}
    except KeyError:
        return {"success": False, "message": f"Textbook not found: {book_name}"}


@router.delete("/{book_name}/purge")
def purge_book(book_name: str, confirm_book_id: str = ""):
    try:
        result = _lifecycle.purge(book_name, confirmation=confirm_book_id)
    except (KeyError, ValueError, RuntimeError) as exc:
        return {"success": False, "message": str(exc)}
    if _book_state.get("current_book") == result.get("storage_name"):
        _book_state.update(current_book=None, chapters=[], book_pdf_path=None)
    return {"success": True, "message": "教材及其关联数据已彻底删除。", "data": result}

@router.get("/switch/{book_name}")
def switch_book(book_name: str):
    name = _resolve_book_reference(book_name)
    if not name:
        return {"success": False, "message": f"Textbook not found: {book_name}"}

    pdf_path = _book_pdf_path(name)
    chapters = _load_chapters(name)
    if not chapters and pdf_path and pdf_path.exists():
        parser = PDFParser(pdf_path)
        try:
            chapters = parser.extract_chapters()
        finally:
            parser.close()
        _save_chapters(name, chapters)
    if not chapters:
        return {"success": False, "message": f"Textbook chapters not found: {name}"}

    _set_current_book(name, chapters, pdf_path)
    identity, _ = _ensure_book_identity(name)
    return {"success": True, "data": {"book_id": identity["book_id"], "name": name, "display_name": identity["display_name"], "displayName": identity["display_name"], "subject": _book_subject(name), "chapter_count": len(chapters), "chapters": [format_chapter(c) for c in chapters]}}



def _safe_output_book_name(value: str) -> str:
    raw = Path(value or "external_textbook").name
    stem = re.sub(r"[^\w\-.\u4e00-\u9fff]+", "_", Path(raw).stem).strip("._") or "external_textbook"
    return stem[:90]


def _unique_new_book_name(value: str) -> str:
    base = _safe_output_book_name(value)
    reserved = set(_known_book_names(include_archived=True))
    if BOOK_UPLOAD_DIR.exists():
        reserved.update(path.stem for path in BOOK_UPLOAD_DIR.glob("*.pdf"))
    candidate = base
    counter = 1
    while candidate in reserved:
        candidate = f"{base[:84]}_{counter}"
        counter += 1
    return candidate


def _save_output_upload(file: UploadFile, book_name: str) -> Path:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise ValueError("Please upload a .zip file containing MinerU or Markdown output")
    OUTPUT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_book = _safe_output_book_name(book_name or file.filename)
    dest = OUTPUT_UPLOAD_DIR / f"{safe_book}_{int(time.time())}.zip"
    copy_stream_limited(file.file, dest, max_bytes=MAX_OUTPUT_ZIP_BYTES)
    return dest


def _unique_output_dir(book_name: str) -> Path:
    base = MINERU_OUTPUT_PATH / _safe_output_book_name(book_name) / "hybrid_auto_external"
    dest = base
    counter = 1
    while dest.exists():
        dest = base.with_name(f"{base.name}_{counter}")
        counter += 1
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _extract_zip_safe(zip_path: Path, target_dir: Path) -> Path:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            infos, expanded = inspect_zip_limits(zf)
            validate_zip_paths(infos, target_dir)
            ensure_disk_space(target_dir, expanded)
            zf.extractall(target_dir)
        return _detect_output_root(target_dir)
    except Exception:
        # target_dir is a freshly-created, job-specific extraction directory.
        shutil.rmtree(target_dir, ignore_errors=True)
        raise


def _detect_output_root(target_dir: Path) -> Path:

    patterns = ["*content_list*.json", "*content-list*.json", "*middle*.json", "*.md"]
    for pattern in patterns:
        if list(target_dir.rglob(pattern)):
            break
    else:
        return target_dir

    direct_has = any(list(target_dir.glob(pattern)) for pattern in patterns)
    if direct_has:
        return target_dir
    children = [child for child in target_dir.iterdir() if child.is_dir()]
    if len(children) == 1:
        child = children[0]
        if any(list(child.rglob(pattern)) for pattern in patterns):
            return child
    return target_dir


def _copy_origin_pdf_if_present(output_dir: Path, book_name: str) -> Path | None:
    pdfs = sorted(output_dir.rglob("*.pdf"), key=lambda item: ("layout" in item.name.lower(), len(item.name)))
    if not pdfs:
        return None
    source = next((p for p in pdfs if "origin" in p.name.lower()), pdfs[0])
    BOOKS_PATH.mkdir(parents=True, exist_ok=True)
    dest = BOOKS_PATH / f"{_safe_output_book_name(book_name)}.pdf"
    if not dest.exists():
        shutil.copy2(source, dest)
    return dest


def _run_output_import_job(job_id: str, archive_path: Path, book_name: str, subject: str = "", extract_concepts: bool = False) -> None:
    pdf_path: Path | None = None

    def progress(stage: str, message: str, percent: int | None = None) -> None:
        _job_manager.raise_if_cancelled(job_id)
        payload = {"stage": stage, "message": message}
        if percent is not None:
            payload["progress"] = max(0, min(100, int(percent)))
        _update_job(job_id, **payload)

    try:
        progress("extract", "Extracting OCR output package", 10)
        output_dir = _extract_zip_safe(archive_path, _unique_output_dir(book_name))
        result = import_textbook_from_mineru_output(output_dir, book_name, on_progress=progress)
        _job_manager.raise_if_cancelled(job_id)
        _save_chapters(book_name, result.chapters)
        pdf_path = _copy_origin_pdf_if_present(output_dir, book_name)
        _write_book_meta(
            book_name,
            subject=normalize_subject_value(subject),
            import_source="external_mineru_output",
            mineru_output_dir=str(output_dir),
            source_archive=str(archive_path),
        )
        _set_current_book(book_name, result.chapters, pdf_path)
        concept_job, concept_warning = _start_optional_concept_extraction(book_name, extract_concepts)
        _job_manager.complete_job(
            job_id,
            stage="completed",
            progress=100,
            message=result.message or "OCR output import completed",
            result={
                "name": book_name,
                "chapter_count": len(result.chapters),
                "used_mineru": True,
                "indexed_chunks": result.indexed_chunks,
                "output_dir": result.output_dir,
                "subject": _book_subject(book_name),
                "has_pdf": bool(pdf_path or _source_pdf_path(book_name)),
                "concept_job_id": concept_job.get("id", "") if concept_job else "",
                "concept_extraction_warning": concept_warning,
            },
        )
    except JobCancelled as exc:
        _cleanup_new_book_import(book_name, archive_path, pdf_path)
        _update_job(job_id, status="cancelled", stage="cancelled", progress=100, message=str(exc) or "OCR output import cancelled", error=str(exc))
    except Exception as exc:
        _cleanup_new_book_import(book_name, archive_path, pdf_path)
        _update_job(job_id, status="failed", stage="failed", progress=100, message=f"OCR output import failed: {exc}", error=str(exc))

@router.post("/import-job")
def create_import_job(
    file: UploadFile = File(...),
    toc_pages: str = Form(""),
    pre_read: bool = Form(False),
    require_mineru: bool = Form(True),
    parse_method: str = Form(""),
    subject: str = Form(""),
    extract_concepts: bool = Form(False),
):
    resolved_parse_method = (parse_method or "").strip().lower()
    if resolved_parse_method not in {"", "auto", "mineru", "local"}:
        return {"success": False, "message": f"Unsupported textbook parse method: {parse_method}"}
    if not resolved_parse_method:
        resolved_parse_method = "mineru" if require_mineru else "auto"

    try:
        pdf_path = _save_upload(file)
    except Exception as exc:
        return {"success": False, "message": str(exc)}

    job = _job_manager.create_job(
        IMPORT_JOB_TYPE,
        {
            "book_name": pdf_path.stem,
            "file_path": str(pdf_path),
            "toc_pages": toc_pages,
            "pre_read": pre_read,
            "require_mineru": require_mineru,
            "subject": normalize_subject_value(subject),
            "parse_method": resolved_parse_method,
            "extract_concepts": extract_concepts,
        },
        status="running",
        stage="queued",
        progress=0,
        message="\u5df2\u52a0\u5165\u5bfc\u5165\u961f\u5217",
    )
    job_id = job["id"]
    thread = threading.Thread(target=_run_import_job, args=(job_id, pdf_path, toc_pages, pre_read, require_mineru, subject, extract_concepts, resolved_parse_method), daemon=True)
    thread.start()
    return {"success": True, "message": "\u6559\u6750\u5bfc\u5165\u4efb\u52a1\u5df2\u542f\u52a8", "job_id": job_id, "data": job}


@router.post("/import")
def import_book(
    file: UploadFile = File(...),
    toc_pages: str = Form(""),
    pre_read: bool = Form(False),
    subject: str = Form(""),
    extract_concepts: bool = Form(False),
):
    return create_import_job(
        file=file, toc_pages=toc_pages, pre_read=pre_read, require_mineru=True, parse_method="mineru",
        subject=subject, extract_concepts=extract_concepts,
    )



@router.post("/import-mineru-output")
def import_mineru_output(
    file: UploadFile = File(...),
    book_name: str = Form(""),
    subject: str = Form(""),
    extract_concepts: bool = Form(False),
):
    try:
        resolved_book = _unique_new_book_name(book_name or file.filename or "external_textbook")
        archive_path = _save_output_upload(file, resolved_book)
    except Exception as exc:
        return {"success": False, "message": str(exc)}

    job = _job_manager.create_job(
        IMPORT_JOB_TYPE,
        {
            "book_name": resolved_book,
            "file_path": str(archive_path),
            "require_mineru": False,
            "import_source": "external_mineru_output",
            "subject": normalize_subject_value(subject),
            "extract_concepts": extract_concepts,
        },
        status="running",
        stage="queued",
        progress=0,
        message="External OCR output import queued",
    )
    job_id = job["id"]
    thread = threading.Thread(target=_run_output_import_job, args=(job_id, archive_path, resolved_book, subject, extract_concepts), daemon=True)
    thread.start()
    return {"success": True, "message": "External OCR output import started", "job_id": job_id, "data": job}

@router.get("/import-jobs/{job_id}")
def get_import_job(job_id: str):
    job = _read_job(job_id)
    if not job:
        return {"success": False, "message": "\u672a\u627e\u5230\u5bfc\u5165\u4efb\u52a1"}
    return {"success": True, "data": job}


@router.post("/import-local")
def import_book_local(
    file: UploadFile = File(...),
    toc_pages: str = Form(""),
    subject: str = Form(""),
    extract_concepts: bool = Form(False),
):
    pdf_path: Path | None = None
    final_pdf: Path | None = None
    imported_book_name = ""
    try:
        pdf_path = _save_upload(file)
        imported_book_name = pdf_path.stem
        result = import_textbook_local(pdf_path, imported_book_name, toc_pages=toc_pages)
        final_pdf = _promote_uploaded_pdf(pdf_path)
        _save_chapters(imported_book_name, result.chapters)
        _write_book_meta(
            imported_book_name,
            subject=normalize_subject_value(subject),
            import_source="local_pdf",
            mineru_output_dir=result.output_dir,
        )
        _set_current_book(imported_book_name, result.chapters, final_pdf)
        concept_job, concept_warning = _start_optional_concept_extraction(imported_book_name, extract_concepts)
        return {
            "success": True,
            "message": result.message,
            "data": {
                "name": imported_book_name, "subject": _book_subject(imported_book_name),
                "chapter_count": len(result.chapters), "used_mineru": False,
                "concept_job_id": concept_job.get("id", "") if concept_job else "",
                "concept_extraction_warning": concept_warning,
            },
        }
    except Exception as exc:
        if imported_book_name:
            _cleanup_new_book_import(imported_book_name, pdf_path, final_pdf)
        return {"success": False, "message": f"\u672c\u5730\u5bfc\u5165\u5931\u8d25\uff1a{exc}"}


def _start_pre_read(book_name: str, chapters: list[dict], pdf_path: Path) -> None:
    bg = _book_state.get("bg_reader")
    if bg and getattr(bg, "_running", False):
        return
    reader = BackgroundReader(book_name, chapters, pdf_path)
    reader.start()
    _book_state["bg_reader"] = reader


@router.post("/preread/start")
def start_pre_read():
    name = _book_state.get("current_book")
    chapters = _book_state.get("chapters", [])
    pdf_path = _book_state.get("book_pdf_path")
    if not name or not chapters or not pdf_path:
        return {"success": False, "message": "\u8bf7\u5148\u9009\u62e9\u6559\u6750"}
    if len(chapters) < 2:
        return {"success": False, "message": "\u7ae0\u8282\u6570\u91cf\u4e0d\u8db3\uff0c\u65e0\u9700\u9884\u8bfb"}
    _start_pre_read(name, chapters, Path(pdf_path))
    return {"success": True, "message": f"\u9884\u8bfb\u5df2\u542f\u52a8 ({len(chapters)}\u7ae0)"}


@router.get("/preread/status")
def pre_read_status():
    bg = _book_state.get("bg_reader")
    if bg:
        status = bg.status
        if status.get("running"):
            return PreReadStatusOut(running=True, done=status.get("done", 0), total=status.get("total", 0), status_text=f"\u9884\u8bfb {status['done']}/{status['total']}")
        if status.get("done", 0) > 0:
            return PreReadStatusOut(running=False, done=status.get("done", 0), total=status.get("total", 0), status_text=f"\u5b8c\u6210 {status['done']}/{status['total']}")
    return PreReadStatusOut(status_text="")
