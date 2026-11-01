"""Source resolution and durable jobs for shared structure review."""
import json
from pathlib import Path
from threading import Lock, Thread

from ingestion.document_ir import (CanonicalBook, DocumentBlock, canonical_book_fingerprint,
                                   canonical_paths, load_canonical_book, persist_canonical_book)
from utils.json_io import atomic_write_json
from utils.path_safety import safe_child_path

_start_lock = Lock()


def review_directory(progress_root, kind, reference):
    return safe_child_path(Path(progress_root) / '_structure_reviews' / kind, reference)


def load_reviewed_candidate(book, directory):
    meta = Path(directory) / 'candidate.json'
    if not meta.exists():
        return book
    data = json.loads(meta.read_text())
    if data['source_version'] != canonical_book_fingerprint(book):
        return book
    return load_canonical_book(book.book_name, progress_root=Path(directory) / 'candidate')


def _source_with_pdf(book, assets, pdf, target, progress_root):
    directory = review_directory(progress_root, target['kind'], target['reference'])
    metadata = directory / 'source_pdf.json'
    if metadata.exists() and (directory / 'source.pdf').is_file():
        data = json.loads(metadata.read_text())
        if data.get('source_version') == canonical_book_fingerprint(book):
            pdf = directory / 'source.pdf'
    return book, assets, pdf


def resolve_source(target, *, progress_root, books_root, jobs):
    kind, reference, name = target['kind'], target['reference'], target['book_name']
    root = Path(progress_root)
    if kind == 'book' and reference != name:
        raise ValueError('教材审阅身份不一致')
    if kind == 'file':
        from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
        store = ExerciseFileAnalysisStore(root)
        store.load(reference, name)  # ownership and immutable snapshot admission
        data = json.loads((store.root / f'{reference}.json').read_text())
        raw = data.get('canonical_source')
        if not raw:
            raise ValueError('这批候选没有保留完整结构来源，请重新导入解析包')
        book = CanonicalBook(**{**raw, 'blocks': [DocumentBlock.from_dict(b) for b in raw['blocks']]})
        return _source_with_pdf(book, store.root / 'assets', None, target, root)
    if kind == 'import':
        job = jobs.get_job(reference)
        if (not job or job.get('book_name') != name or job['status'] != 'waiting_for_review'
                or not (job.get('result') or {}).get('review_required')):
            raise ValueError('导入草稿已改变，请重新打开目录')
        from backend.services.book_import_review import draft_root
        book = load_canonical_book(name, progress_root=draft_root(root, reference))
        source = Path(job['result']['output_dir'])
        pdfs = list(source.rglob('*.pdf'))
        return _source_with_pdf(book, source, pdfs[0] if len(pdfs) == 1 else None, target, root)
    book = load_canonical_book(name, progress_root=root)
    source = canonical_paths(name, progress_root=root)[0].parent
    pdf = safe_child_path(Path(books_root), name + '.pdf')
    return _source_with_pdf(book, source, pdf if pdf.is_file() else None, target, root)


def start_review(target, *, mode, max_pages, progress_root, books_root, jobs, budget):
    from backend.services.document_structure_review import review_plan
    from config import get_model_role_config
    from llm.factory import ensure_runtime_support
    from llm.types import Capability
    book, assets, pdf = resolve_source(target, progress_root=progress_root, books_root=books_root, jobs=jobs)
    resolved = get_model_role_config('vision')
    ensure_runtime_support(resolved, Capability.VISION)
    if not resolved.credential_configured:
        raise ValueError('请先在设置中配置识图模型和所需凭证')
    directory = review_directory(progress_root, target['kind'], target['reference'])
    with _start_lock:
        for current in jobs.list_jobs(job_type='document_structure_review', book_name=target['book_name']):
            if current['input'].get('target') == target and current['status'] in {'queued', 'running', 'cancelling'}:
                return current
        plan = review_plan(book, mode=mode, max_pages=max_pages)
        job = jobs.create_job('document_structure_review', dict(book_name=target['book_name'], target=target,
            mode=mode, max_pages=max_pages, plan=plan, budget=budget), status='running', message='正在准备结构审阅')
        Thread(target=_run, kwargs=dict(job=job, book=book, assets=assets, pdf=pdf, directory=directory,
            progress_root=progress_root, books_root=books_root, jobs=jobs, resolved=resolved), daemon=True).start()
    return job


def _run(*, job, book, assets, pdf, directory, progress_root, books_root, jobs, resolved):
    from backend.services.document_structure_review import run_review
    from backend.job_manager import JobCancelled
    target = job['input']['target']
    try:
        reviewed, report = run_review(book, directory=directory, mode=job['input']['mode'],
            max_pages=job['input']['max_pages'], asset_root=assets, pdf_path=pdf, resolved=resolved,
            budget=job['input']['budget'],
            check_cancelled=lambda: jobs.raise_if_cancelled(job['id']),
            on_progress=lambda message, percent: jobs.update_job(job['id'], message=message, progress=percent))
        jobs.raise_if_cancelled(job['id'])
        current, _, _ = resolve_source(target, progress_root=progress_root, books_root=books_root, jobs=jobs)
        if canonical_book_fingerprint(current) != canonical_book_fingerprint(book):
            raise ValueError('来源版本已改变，审阅结果未覆盖当前内容')
        result = dict(report=report)
        if target['kind'] == 'file':
            from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
            from memory.exercise_file_importer import ExtractedExerciseText
            store = ExerciseFileAnalysisStore(progress_root)
            extracted = ExtractedExerciseText(text='\n\n'.join(b.text for b in reviewed.blocks), file_type='zip',
                provider='structure-review', canonical_book=reviewed)
            answer = store.answer_source(target['reference'], target['book_name'])
            _, source_id, _ = store.create(extracted, book_name=target['book_name'], answer=answer)
            result['source_id'] = source_id
            if pdf:
                from ingestion.document_adapters import _atomic_copy
                next_directory = review_directory(progress_root, 'file', source_id)
                next_directory.mkdir(parents=True, exist_ok=True)
                _atomic_copy(pdf, next_directory / 'source.pdf')
                atomic_write_json(next_directory / 'source_pdf.json', dict(source_version=canonical_book_fingerprint(reviewed)))
        else:
            persist_canonical_book(reviewed, progress_root=directory / 'candidate')
            atomic_write_json(directory / 'candidate.json', dict(source_version=canonical_book_fingerprint(book)))
        jobs.complete_job(job['id'], result=result,
            message='结构审阅已完成，请核对修正结果' if report['status'] == 'reviewed' else '部分页面未完成，已保留结果和来源，请核对')
    except JobCancelled:
        jobs.fail_or_cancel_job(job['id'], error='', message='已停止，已完成的页面审阅已保留')
    except Exception:
        jobs.fail_or_cancel_job(job['id'], error='structure_review_failed', message='结构审阅未完成，来源和已完成页面已保留')
