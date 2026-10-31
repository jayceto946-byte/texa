"""Read/preview outline calibration and publish through the existing index job."""
from pathlib import Path
from threading import Lock, Thread

from ingestion.document_ir import load_canonical_book
from ingestion.document_workflows import canonical_outline
from ingestion.outline_recovery import recover_outline, family

_refresh_lock = Lock()
_refresh_jobs = {}


class OutlineConflict(ValueError):
    pass


def preview_outline(name, *, progress_root, base_version=None, examples=None, max_depth=None):
    from ingestion.index_pipeline import load_index_manifest
    from ingestion.index_snapshot import index_read_snapshot
    with index_read_snapshot():
        version = load_index_manifest(name).get('index_version', '')
        if base_version is not None and base_version != version:
            raise OutlineConflict('教材已更新，请重新打开目录校准后预览')
        book = load_canonical_book(name, progress_root=progress_root)
    candidate = recover_outline(book, examples=examples, max_depth=max_depth, force=True)
    if canonical_outline(candidate) != canonical_outline(book):
        candidate.source_metadata['outline_recovery']['stable_scope_ids'] = True
    nodes = []
    for block in candidate.blocks:
        if block.attributes.get('outline_toc') or block.block_type != 'heading':
            continue
        title = block.attributes.get('outline_title', block.text)
        if len(title) > 140 or '\n' in title:
            continue
        nodes.append(dict(block_id=block.block_id, text=title, page=block.page_start,
                          chapter=block.section_path[0], level=block.attributes.get('outline_level', 0),
                          role=block.attributes.get('outline_role', 'section'), family=family(block.text)[0],
                          visible=block.attributes.get('outline_visible', True),
                          method=block.attributes.get('outline_method', 'body')))
    return candidate, dict(base_version=version, candidates=nodes, chapters=canonical_outline(candidate),
        recovery=candidate.source_metadata['outline_recovery'])


def outline_refresh_status(name, *, progress_root):
    """Inspect retained source without changing the active outline or index."""
    from ingestion.outline_recovery import POLICY_VERSION
    from ingestion.document_workflows import load_workflow_book
    book = load_workflow_book(name, progress_root=Path(progress_root))
    if book is None:
        return {'status': 'current'}
    recovery = book.source_metadata.get('outline_recovery', {})
    if recovery.get('version') == POLICY_VERSION:
        unresolved = [title for report in recovery.get('toc', []) if report.get('accepted')
                      for title in report.get('unmatched', [])
                      if family(title)[0] in {'chapter', 'chapter-en'}
                      and title not in report.get('recovered_chapters', [])
                      and title not in {chapter['title'] for chapter in canonical_outline(book)}]
        return dict(status='current', unresolved_chapters=unresolved)
    _, preview = preview_outline(name, progress_root=progress_root)
    previous = canonical_outline(book)
    changed = preview['chapters'] != previous
    return dict(status='outdated' if changed else 'current', base_version=preview['base_version'],
                chapter_count=len(previous), updated_chapter_count=len(preview['chapters']))


def start_outline_refresh(name, *, progress_root, jobs, on_published=None):
    """Rebuild an outdated derived outline once, through staged index publication."""
    status = outline_refresh_status(name, progress_root=progress_root)
    if status['status'] != 'outdated':
        return status
    key = (str(Path(progress_root).resolve()), name, status['base_version'])
    with _refresh_lock:
        current = jobs.get_job(_refresh_jobs[key]) if key in _refresh_jobs else None
        if current and current['status'] in {'queued', 'running', 'cancelling'}:
            return current
        job = jobs.create_job('textbook_outline', {'book_name': name, 'automatic_refresh': True},
                              status='running', message='正在更新教材目录并同步检索范围')
        _refresh_jobs[key] = job['id']
        Thread(target=apply_outline, kwargs=dict(name=name, progress_root=progress_root,
            base_version=status['base_version'], examples=None, max_depth=None, jobs=jobs,
            job_id=job['id'], on_published=on_published), daemon=True).start()
    return job


def apply_outline(name, *, progress_root, base_version, examples, max_depth, jobs, job_id, on_published=None):
    from ingestion.index_pipeline import load_index_manifest
    from ingestion.mineru_importer import build_index_from_chapters
    try:
        def check_current():
            jobs.raise_if_cancelled(job_id)
            if load_index_manifest(name).get('index_version', '') != base_version:
                raise OutlineConflict('教材已更新，请重新打开目录校准后预览')
        check_current()
        jobs.update_job(job_id, stage='structure', progress=10, message='依据目录整理全书章、节')
        candidate, preview = preview_outline(name, progress_root=progress_root, base_version=base_version,
                                             examples=examples, max_depth=max_depth)
        jobs.update_job(job_id, stage='indexing', progress=30, message='同步章节范围与检索索引')
        count = build_index_from_chapters(name, [], Path(progress_root)/name, canonical_book=candidate,
            canonical_progress_root=progress_root, before_publish=check_current)
        result = dict(chapter_count=len(preview['chapters']), indexed_chunks=count,
                      index_version=load_index_manifest(name).get('index_version', ''))
        jobs.update_job(job_id, status='completed', stage='completed', progress=100,
                        message='目录已应用，检索和习题范围已同步', result=result)
        if on_published:
            on_published()
    except Exception as exc:
        jobs.fail_or_cancel_job(job_id, error=str(exc), message=str(exc))
