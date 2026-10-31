"""Durable parsed import drafts; no active index is written before confirmation."""
from pathlib import Path
import shutil
from threading import Lock

from ingestion.document_ir import load_canonical_book, persist_canonical_book
from ingestion.mineru_importer import BookImportResult, chapters_from_canonical
from backend.services.book_outline import outline_proposal


def draft_root(progress_root, job_id):
    return Path(progress_root) / '_import_drafts' / job_id


def save_import_draft(job_id, result, *, jobs, progress_root, source_root=None):
    root = draft_root(progress_root, job_id)
    root.mkdir(parents=True, exist_ok=True)
    source = Path(source_root) if source_root is not None else root / 'source'
    source.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(result.output_dir, source)
    result.output_dir = str(source)
    persist_canonical_book(result.canonical_book, progress_root=root)
    return jobs.wait_for_review(job_id, progress=45,
        message='解析完成，请确认教材目录', result=dict(name=result.book_name, chapter_count=len(result.chapters),
            output_dir=result.output_dir, used_mineru=result.used_mineru, review_required=True))


def preview_import_draft(job, *, progress_root, examples=None, max_depth=None, edits=None):
    book = import_source_book(job, progress_root=progress_root)
    return outline_proposal(book, job['id'], examples=examples, max_depth=max_depth, edits=edits)


def confirmed_result(job, request, *, progress_root):
    if request.base_version != job['id']:
        raise ValueError('导入草稿已改变，请重新打开目录')
    book, _ = preview_import_draft(job, progress_root=progress_root,
        examples=[e.model_dump() for e in request.examples], max_depth=request.max_depth,
        edits=[e.model_dump() for e in request.edits] if request.edits is not None else None)
    data = job['result']
    return BookImportResult(book_name=book.book_name, chapters=chapters_from_canonical(book),
        used_mineru=data['used_mineru'], output_dir=data['output_dir'], canonical_book=book)


_confirmation_lock = Lock()


def start_confirmation(job_id, request, *, jobs, progress_root, start_worker):
    with _confirmation_lock:
        job = jobs.get_job(job_id)
        if job is None:
            raise ValueError('导入草稿不存在')
        if job['status'] in {'running', 'queued', 'completed'}:
            return job
        if job['status'] not in {'waiting_for_review', 'failed', 'interrupted'} or not (job.get('result') or {}).get('review_required'):
            raise ValueError('该导入草稿不能确认，请重新选择文件')
        check_import_publication(job_id, job['book_name'], jobs=jobs)
        prepared = confirmed_result(job, request, progress_root=progress_root)
        if not jobs.claim_job(job_id, from_statuses=('waiting_for_review', 'failed', 'interrupted')):
            raise ValueError('导入状态已改变，请重新打开目录')
        job = jobs.update_job(job_id, stage='indexing', progress=50,
                              error='', message='目录已确认，正在建立检索索引')
        start_worker(job, prepared)
        return job


def check_import_publication(job_id, book_name, *, jobs):
    from ingestion.index_pipeline import load_index_manifest
    jobs.raise_if_cancelled(job_id)
    if load_index_manifest(book_name).get('index_version'):
        raise ValueError('同名教材已在本次确认期间导入，请重新选择文件以保留两份教材')


def rollback_failed_confirmation(book_name, published_version, *, cleanup, staged_pdf=None, final_pdf=None):
    from ingestion.index_pipeline import load_index_manifest
    if not published_version or load_index_manifest(book_name).get('index_version') != published_version:
        return
    if staged_pdf and final_pdf and final_pdf.exists():
        staged_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(final_pdf, staged_pdf)
        final_pdf = None
    cleanup(book_name, final_pdf)


def publish_confirmed_import(job_id, result, *, jobs, progress_root):
    from ingestion.index_pipeline import load_index_manifest
    from ingestion.mineru_importer import build_index_from_chapters
    result.indexed_chunks = build_index_from_chapters(result.book_name, result.chapters, Path(result.output_dir),
        canonical_book=result.canonical_book, canonical_progress_root=progress_root,
        before_publish=lambda: check_import_publication(job_id, result.book_name, jobs=jobs))
    return load_index_manifest(result.book_name).get('index_version', '')


def import_source_book(job, *, progress_root):
    root = progress_root if job['status'] == 'completed' else draft_root(progress_root, job['id'])
    return load_canonical_book(job['book_name'], progress_root=root)


def finish_import_draft(job_id, *, progress_root):
    # The active Canonical and retained OCR output now own the confirmed source.
    shutil.rmtree(draft_root(progress_root, job_id), ignore_errors=True)
