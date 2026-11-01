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


def discard_review_candidate(target, *, progress_root, books_root, jobs):
    if target['kind']=='file':raise ValueError('文件候选请重新解析原文件以恢复')
    resolve_source(target,progress_root=progress_root,books_root=books_root,jobs=jobs)
    metadata=review_directory(progress_root,target['kind'],target['reference'])/'candidate.json'
    if metadata.exists():metadata.replace(metadata.with_name('candidate.previous.json'))


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


def start_review(target, *, mode, max_pages, progress_root, books_root, jobs, budget, purpose=None,retry_failed=False):
    from backend.services.document_structure_review import review_plan
    from config import get_model_role_config
    from llm.factory import ensure_runtime_support
    from llm.types import Capability
    if target['kind']=='file':
        from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
        target={**target,'reference':ExerciseFileAnalysisStore(progress_root).review_reference(target['reference'],target['book_name'])}
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
        if purpose:
            from backend.services.import_semantic_review import semantic_review_plan
            plan=semantic_review_plan(book,purpose)
        else:
            plan = review_plan(book, mode=mode, max_pages=max_pages)
        job = jobs.create_job('document_structure_review', dict(book_name=target['book_name'], target=target,
            mode=mode, max_pages=max_pages, plan=plan, budget=budget, purpose=purpose,retry_failed=retry_failed), status='running', message='正在准备智能整理')
        Thread(target=_run, kwargs=dict(job=job, book=book, assets=assets, pdf=pdf, directory=directory,
            progress_root=progress_root, books_root=books_root, jobs=jobs, resolved=resolved), daemon=True).start()
    return job


def _run(*, job, book, assets, pdf, directory, progress_root, books_root, jobs, resolved):
    from backend.services.document_structure_review import run_review
    from backend.job_manager import JobCancelled
    target = job['input']['target']
    session=None
    try:
        options = dict(directory=directory,asset_root=assets,pdf_path=pdf,resolved=resolved,
            check_cancelled=lambda: jobs.raise_if_cancelled(job['id']),
            on_progress=lambda message,percent: jobs.update_job(job['id'],message=message,progress=percent))
        if job['input'].get('purpose'):
            from backend.services.import_semantic_review import run_semantic_review,create_review_session
            session=create_review_session(book,directory=directory,resolved=resolved,purpose=job['input']['purpose'],
                pdf_path=pdf,max_cost_cny=job['input']['budget']['max_cost_cny'],check_cancelled=options['check_cancelled'],retry_failed=job['input'].get('retry_failed',False))
            reviewed,report=run_semantic_review(book, purpose=job['input']['purpose'],
                session=session,**options)
        else:
            reviewed,report=run_review(book,mode=job['input']['mode'],max_pages=job['input']['max_pages'],budget=job['input']['budget'],**options)
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
            if answer and job['input'].get('purpose') and not report.get('needs_retry'):
                from dataclasses import replace
                from backend.services.exercise_file_analysis import file_book
                answer_book=answer.canonical_book or file_book(answer,name=target['book_name'],prefix='answer')
                answer_book,answer_report=run_semantic_review(answer_book,directory=directory,resolved=resolved,purpose='answer_text',session=session,
                    check_cancelled=options['check_cancelled'],on_progress=lambda message,percent:jobs.update_job(job['id'],message='独立答案：'+message,progress=90+percent//10))
                answer=replace(answer,canonical_book=answer_book,text='\n\n'.join(b.text for b in answer_book.blocks))
                report.update(session.report())
                report['text_corrections']+=answer_report['text_corrections']
                report['unresolved'].extend(answer_report['unresolved'])
                report['needs_retry']=bool(report.get('needs_retry') or answer_report.get('needs_retry'))
                if report['unresolved']:report['status']='partial'
            reviewed.source_metadata['review_origin_source_id']=target['reference']
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
        if target['kind'] != 'file' and report.get('purpose'):
            from backend.services.book_outline import outline_proposal
            if target['kind']=='book':
                from ingestion.index_pipeline import load_index_manifest
                version=load_index_manifest(target['book_name']).get('index_version','')
            else:
                version=target['reference']
            _,result['outline']=outline_proposal(reviewed,version)
        jobs.complete_job(job['id'], result=result,
            message=('题目与答案已整理' if target['kind']=='file' else '下方目录已更新') if report['status']=='reviewed' else '整理结果已更新，部分内容仍需核对')
    except JobCancelled:
        if session:jobs.update_job(job['id'],result=dict(report={**session.report(),'status':'partial'}))
        jobs.fail_or_cancel_job(job['id'], error='', message='已停止，已完成的页面审阅已保留')
    except Exception:
        if session:jobs.update_job(job['id'],result=dict(report={**session.report(),'status':'partial'}))
        jobs.fail_or_cancel_job(job['id'], error='structure_review_failed', message='结构审阅未完成，来源和已完成页面已保留')
