"""Durable background orchestration for optional textbook concept extraction."""
from __future__ import annotations

import threading

from backend.job_manager import JobCancelled, get_job_manager
from knowledge.kg_enhancement import enhance_book, estimate_enhancement
from utils.path_safety import safe_book_name

KG_ENHANCEMENT_JOB_TYPE = "textbook_kg_enhancement"


def _run_job(job_id: str, book_name: str) -> None:
    manager = get_job_manager()

    def progress(stage: str, message: str, percent: int) -> None:
        manager.raise_if_cancelled(job_id)
        manager.update_job(job_id, status="running", stage=stage, message=message, progress=percent)

    try:
        manager.update_job(job_id, status="running", stage="prepare", progress=3, message="\u51c6\u5907\u63d0\u53d6\u6559\u6750\u6982\u5ff5\u7d22\u5f15")
        result = enhance_book(
            book_name,
            progress=progress,
            check_cancelled=lambda: manager.raise_if_cancelled(job_id),
        )
        manager.update_job(job_id, status="completed", stage="completed", progress=100, message="\u6559\u6750\u6982\u5ff5\u7d22\u5f15\u63d0\u53d6\u5b8c\u6210", result=result)
    except JobCancelled as exc:
        manager.update_job(job_id, status="cancelled", stage="cancelled", progress=100, message=str(exc) or "\u6982\u5ff5\u63d0\u53d6\u5df2\u53d6\u6d88", error=str(exc))
    except Exception as exc:
        manager.update_job(job_id, status="failed", stage="failed", progress=100, message=f"\u6559\u6750\u6982\u5ff5\u7d22\u5f15\u63d0\u53d6\u5931\u8d25\uff1a{exc}", error=str(exc))


def start_kg_enhancement_job(book_name: str, *, allow_external_llm: bool) -> tuple[dict, bool]:
    if not allow_external_llm:
        raise PermissionError("\u53d1\u9001\u7b5b\u9009\u540e\u7684\u6559\u6750\u7247\u6bb5\u5230\u5916\u90e8 LLM \u524d\u9700\u8981\u660e\u786e\u540c\u610f")
    normalized = safe_book_name(book_name)
    estimate = estimate_enhancement(normalized)
    if not estimate.get("total_chunks"):
        raise ValueError("\u6ca1\u6709\u53ef\u7528\u4e8e\u6982\u5ff5\u63d0\u53d6\u7684\u6559\u6750\u7247\u6bb5")
    manager = get_job_manager()
    for existing in manager.list_jobs(job_type=KG_ENHANCEMENT_JOB_TYPE, limit=100):
        if existing.get("book_name") == normalized and existing.get("status") in {"queued", "running", "cancelling"}:
            return existing, False
    job = manager.create_job(
        KG_ENHANCEMENT_JOB_TYPE,
        {"book_name": normalized, "allow_external_llm": True, "estimate": estimate},
        status="queued", stage="queued", progress=0, message="\u6559\u6750\u6982\u5ff5\u7d22\u5f15\u63d0\u53d6\u5df2\u6392\u961f",
    )
    threading.Thread(target=_run_job, args=(job["id"], normalized), daemon=True).start()
    return job, True
