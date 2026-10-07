"""Two-store candidate publication. Job completion CAS adjudicates cancellation."""
import threading

from backend.job_manager import JobCancelled
from memory.session_notes import NoteError
from .generation import generate

_START_LOCK = threading.Lock()
_WORKERS = set()


def start_generation(service, receipt, *, generator=generate, threaded=True):
    draft_id, job_id = receipt["draft_id"], receipt["job_id"]
    jobs = service.jobs()
    with _START_LOCK:
        job = jobs.get_job(job_id)
        if job is None:
            jobs.create_job("session_note_generate", job_id=job_id, input_data=receipt, message="准备整理会话")
        elif job["status"] != "queued" or job_id in _WORKERS:
            return
        _WORKERS.add(job_id)
    def worker():
        try:
            jobs.raise_if_cancelled(job_id)
            # Do not revive a terminal attempt.
            if not jobs.claim_queued_job(job_id):
                jobs.raise_if_cancelled(job_id)
                return
            jobs.update_job(job_id, stage="note_generate", message="正在读取冻结来源")
            jobs.raise_if_cancelled(job_id)
            draft = service.store.get("note_drafts", draft_id)
            snapshot = service.store.get("note_source_snapshots", receipt["snapshot_id"])
            service.audit("note_generate", draft_id, "running", (draft_id, receipt["snapshot_id"]))
            def progress(stage, message):
                jobs.raise_if_cancelled(job_id)
                jobs.update_job(job_id, stage=stage, message=message)
            document = generator(snapshot, check_cancel=lambda: jobs.raise_if_cancelled(job_id), progress=progress, structure_hint=draft.get("structure_hint", "auto"))
            jobs.raise_if_cancelled(job_id)
            candidate_hash = service.store.candidate(draft_id, document)
            completed = jobs.complete_job(job_id, result={"draft_id": draft_id, "candidate_hash": candidate_hash}, message="草稿已生成，请审阅并保存")
            service.store.publish_candidate(draft_id, completed)
            service.audit("note_validate", draft_id, "editable", (draft_id, receipt["snapshot_id"]))
        except JobCancelled:
            jobs.fail_or_cancel_job(job_id, error="cancelled", message="已取消，来源已保留")
        except Exception as exc:
            # Never persist transport errors containing endpoints, keys or prompt text.
            code = exc.code if isinstance(exc, NoteError) else "generation_failed"
            if isinstance(exc, NoteError):
                jobs.update_job(job_id, result={"diagnostic": {"phase": "note_generate", "reason": exc.reason or code, "path": exc.path, **getattr(exc, "generation_metadata", {})}})
            reason = exc.reason if isinstance(exc, NoteError) else ""
            message = {
                "invalid_latex_escape": "模型返回的公式转义已损坏，未发布草稿",
                "json_syntax": "模型返回的笔记 JSON 格式无效，未发布草稿",
                "output_truncated": "模型输出被截断，未发布草稿",
                "output_too_large": "模型输出超过笔记长度限制，未发布草稿",
                "content_type": "模型未返回可用的笔记文字，未发布草稿",
                "invalid_source_ref": "模型引用了选区之外的来源，未发布草稿",
                "generation_timeout": "笔记整理超时，未发布草稿",
                "model_unavailable": "回答模型尚未配置，未开始整理",
            }.get(reason or code, "模型返回的笔记结构不符合格式要求，未发布草稿" if code == "invalid_document" else "笔记整理未完成")
            jobs.fail_or_cancel_job(job_id, error=code, message=message + "；来源已保留，可重试或手动整理")
        finally:
            # A completed-but-unpublished candidate remains recoverable.
            service.store.release_generation(draft_id)
            with _START_LOCK:
                _WORKERS.discard(job_id)
    if threaded:
        threading.Thread(target=worker, name=f"note-{job_id}", daemon=True).start()
    else:
        worker()


def reconcile(service):
    """Never restart paid calls. Only repair already-completed publications."""
    cursor = ""
    repaired = 0
    while True:
        page = service.store.list(drafts=True, cursor=cursor, limit=100)
        for summary in page["items"]:
            draft = service.store.get("note_drafts", summary["id"])
            if draft["status"] != "preparing":
                continue
            job = service.jobs().get_job(draft["job_id"])
            if job is None:
                service.jobs().create_job("session_note_generate", job_id=draft["job_id"], input_data={"draft_id": draft["id"], "snapshot_id": draft["source_snapshot_ids"][0]}, status="interrupted", stage="interrupted", message="申请未完成启动；来源保留，请手动重试")
            elif job["status"] == "completed":
                try:
                    service.store.publish_candidate(draft["id"], job)
                    repaired += 1
                except NoteError:
                    # Preserve the completed job receipt for diagnosis; expose a note-specific error.
                    with service.store.transaction() as conn:
                        broken = service.store._get(conn, "note_drafts", draft["id"])
                        broken.update(recovery_error="candidate_receipt_mismatch")
                        service.store.put_draft(conn, broken)
            elif job["status"] in {"queued", "running", "cancelling"}:
                service.jobs().update_job(job["id"], status="interrupted", stage="interrupted", error="server_restarted", message="生成中断；不会自动重跑模型")
            service.store.release_generation(draft["id"])
        if not page["next_cursor"]:
            return repaired
        cursor = page["next_cursor"]
