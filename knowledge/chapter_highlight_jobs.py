"""Background job management for chapter highlight generation."""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from backend.job_manager import JobCancelled, JobManager, TERMINAL_STATUSES, get_job_manager

if TYPE_CHECKING:
    from .chapter_highlights import ChapterHighlightService


HIGHLIGHT_JOB_TYPE = "chapter_highlight"
ACTIVE_JOB_STATUSES = {"queued", "running", "cancelling"}


class HighlightJobStore:
    """JobManager-backed store for queued background highlight generation."""

    _worker_lock = threading.Lock()

    def __init__(
        self,
        service: "ChapterHighlightService | None" = None,
        job_manager: JobManager | None = None,
    ) -> None:
        if service is None:
            from .chapter_highlights import ChapterHighlightService

            service = ChapterHighlightService()
        self.service = service
        self.job_dir = self.service.progress_path / "highlight_jobs"
        self.jobs = job_manager or get_job_manager()
        self.jobs.import_legacy_json_jobs(
            HIGHLIGHT_JOB_TYPE,
            self.job_dir,
            input_keys=("book_name", "chapter_id", "section_id", "force"),
        )

    def create_job(self, book_name: str, chapter_id: str, section_id: str | None = None, force: bool = False) -> dict:
        scope_id = self.service._scope_id(section_id)
        active = self._find_active_job(book_name, chapter_id, scope_id)
        if active:
            return active

        job = self.jobs.create_job(
            HIGHLIGHT_JOB_TYPE,
            {
                "book_name": book_name,
                "chapter_id": chapter_id,
                "section_id": scope_id,
                "force": force,
            },
            status="queued",
            stage="queued",
            progress=0,
            message="已加入章节重点生成队列",
        )
        thread = threading.Thread(target=self._run_job, args=(job["id"],), daemon=True)
        thread.start()
        return job

    def read_job(self, job_id: str) -> dict | None:
        return self.jobs.get_job(job_id, job_type=HIGHLIGHT_JOB_TYPE)

    def reconcile_book(self, book_name: str) -> None:
        """Repair stale running metadata from jobs interrupted outside the worker."""
        seen_scopes: set[tuple[str, str]] = set()
        for job in self.jobs.list_jobs(job_type=HIGHLIGHT_JOB_TYPE, limit=500):
            if str(job.get("book_name") or "") != str(book_name or ""):
                continue
            chapter_id = str(job.get("chapter_id") or "")
            scope_id = self.service._scope_id(str(job.get("section_id") or "all"))
            key = (chapter_id, scope_id)
            if not chapter_id or key in seen_scopes:
                continue
            seen_scopes.add(key)
            status = str(job.get("status") or "")
            if status not in TERMINAL_STATUSES or status == "completed":
                continue
            try:
                self.service.mark_generation_terminal(
                    book_name,
                    chapter_id,
                    scope_id,
                    status=status,
                    message=str(job.get("message") or job.get("error") or "章节重点生成已终止"),
                    create_if_missing=False,
                    only_if_transient=True,
                )
            except Exception:
                # Status repair must never make the chapter list unavailable.
                continue

    def _find_active_job(self, book_name: str, chapter_id: str, scope_id: str) -> dict | None:
        for job in self.jobs.list_jobs(job_type=HIGHLIGHT_JOB_TYPE, limit=200):
            if job.get("status") not in ACTIVE_JOB_STATUSES:
                continue
            if str(job.get("book_name") or "") != str(book_name or ""):
                continue
            if str(job.get("chapter_id") or "") != str(chapter_id or ""):
                continue
            if self.service._scope_id(str(job.get("section_id") or "all")) != scope_id:
                continue
            return job
        return None

    def _run_job(self, job_id: str) -> None:
        job = self.read_job(job_id)
        if not job:
            return

        acquired = self._worker_lock.acquire(blocking=False)
        if not acquired:
            self._update_job(job_id, status="queued", stage="queued", message="等待已有章节重点任务完成", progress=0)
            self._worker_lock.acquire()

        try:
            job = self.read_job(job_id)
            if not job:
                return
            self.jobs.raise_if_cancelled(job_id)
            self._update_job(job_id, status="running", stage="started", message="开始生成章节重点", progress=max(1, int(job.get("progress") or 0)))

            def progress(stage: str, message: str, percent: int | None = None) -> None:
                self.jobs.raise_if_cancelled(job_id)
                updates = {"status": "running", "stage": stage, "message": message}
                if percent is not None:
                    updates["progress"] = max(0, min(100, int(percent)))
                self._update_job(job_id, **updates)

            result = self.service.generate_highlight(
                job["book_name"],
                job["chapter_id"],
                section_id=job.get("section_id"),
                force=bool(job.get("force")),
                on_progress=progress,
            )
            metadata = result.get("metadata", {})
            self.jobs.complete_job(
                job_id,
                stage="completed",
                progress=100,
                message="章节重点生成完成",
                result={
                    "book_name": job["book_name"],
                    "chapter_id": metadata.get("chapter_id") or job["chapter_id"],
                    "chapter_title": metadata.get("chapter_title", ""),
                    "section_id": metadata.get("section_id") or job.get("section_id") or "all",
                    "scope_id": metadata.get("scope_id") or job.get("section_id") or "all",
                    "scope_type": metadata.get("scope_type", "chapter"),
                    "scope_title": metadata.get("scope_title", ""),
                    "html_url": metadata.get("html_url", ""),
                },
            )
        except JobCancelled as exc:
            message = str(exc) or "章节重点生成已取消"
            try:
                self.service.mark_generation_terminal(
                    job["book_name"], job["chapter_id"], job.get("section_id"),
                    status="cancelled", message=message,
                )
            except Exception:
                pass
            self._update_job(job_id, status="cancelled", stage="cancelled", progress=100, message=message, error=str(exc))
        except Exception as exc:
            message = f"章节重点生成失败：{exc}"
            try:
                self.service.mark_generation_terminal(
                    job["book_name"], job["chapter_id"], job.get("section_id"),
                    status="failed", message=message,
                )
            except Exception:
                pass
            self._update_job(job_id, status="failed", stage="failed", progress=100, message=message, error=str(exc))
        finally:
            self._worker_lock.release()

    def _update_job(self, job_id: str, **updates: Any) -> dict:
        return self.jobs.update_job(job_id, **updates)
