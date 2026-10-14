"""User-decision readiness derived from persisted textbook artifacts."""
from __future__ import annotations

import json
from pathlib import Path

from ingestion.document_ir import CANONICAL_DOCUMENT_FILENAME, INGESTION_REPORT_FILENAME
from utils.path_safety import safe_book_name


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def derive_book_readiness(
    book_name: str,
    *,
    index_status: dict,
    progress_root: str | Path,
    vector_db_root: str | Path,
) -> dict:
    """Keep technical readiness separate from source and semantic confidence."""
    safe = safe_book_name(book_name)
    progress_dir = Path(progress_root) / safe
    report = _read_json(progress_dir / INGESTION_REPORT_FILENAME)
    canonical_exists = (progress_dir / CANONICAL_DOCUMENT_FILENAME).is_file()

    technical_status = str(index_status.get("status") or "missing")
    if technical_status not in {"ready", "degraded", "missing"}:
        technical_status = "missing"

    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    warning_count = max(0, int(summary.get("warnings", 0) or 0))
    error_count = max(0, int(summary.get("errors", 0) or 0))
    if not canonical_exists or not report:
        canonical_status = "unavailable"
    elif not bool(report.get("valid")) or error_count:
        canonical_status = "invalid"
    elif warning_count:
        canonical_status = "needs_review"
    else:
        canonical_status = "ready"

    manifest = _read_json(
        Path(vector_db_root) / "_index_manifests" / f"{safe}.json"
    )
    quality = manifest.get("release_quality") if isinstance(manifest.get("release_quality"), dict) else {}
    case_count = max(0, int(quality.get("cases", 0) or 0))
    generated_count = max(0, int(quality.get("generated_probe_cases", 0) or 0))
    human_case_count = max(0, case_count - generated_count)
    release_status = str(quality.get("status") or "not_configured")
    semantic_status = (
        "verified"
        if release_status == "passed" and human_case_count > 0
        else "unverified"
    )

    return {
        "technical": {
            "status": technical_status,
            "healthy": bool(index_status.get("healthy")),
            "vector_ready": bool(index_status.get("vector_ready")),
            "lexical_ready": bool(index_status.get("lexical_ready")),
            "chunk_count": max(0, int(index_status.get("chunk_count", 0) or 0)),
            "index_version": str(index_status.get("index_version") or ""),
            "error_code": str(index_status.get("error_code") or ""),
            "reindex_required": bool(index_status.get("reindex_required")),
        },
        "canonical": {
            "status": canonical_status,
            "warning_count": warning_count,
            "error_count": error_count,
            "block_count": max(0, int(report.get("block_count", 0) or 0)),
        },
        "semantic": {
            "status": semantic_status,
            "release_status": release_status,
            "case_count": case_count,
            "human_case_count": human_case_count,
            "generated_probe_cases": generated_count,
        },
    }
