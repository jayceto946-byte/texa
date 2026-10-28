"""Read/preview outline calibration and publish through the existing index job."""
from pathlib import Path

from ingestion.document_ir import load_canonical_book
from ingestion.document_workflows import canonical_outline
from ingestion.outline_recovery import recover_outline, family


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
    nodes = []
    for block in candidate.blocks:
        if block.attributes.get('outline_toc') or block.block_type not in {'heading', 'paragraph', 'exercise', 'example'}:
            continue
        if len(block.text) > 140 or '\n' in block.text:
            continue
        nodes.append(dict(block_id=block.block_id, text=block.text, page=block.page_start,
                          chapter=block.section_path[0], level=block.attributes.get('outline_level', 0),
                          role=block.attributes.get('outline_role', 'section'), family=family(block.text)[0],
                          method=block.attributes.get('outline_method', 'body')))
    return candidate, dict(base_version=version, candidates=nodes, chapters=canonical_outline(candidate),
        recovery=candidate.source_metadata['outline_recovery'])


def apply_outline(name, *, progress_root, base_version, examples, max_depth, jobs, job_id, on_published=None):
    from ingestion.index_pipeline import load_index_manifest
    from ingestion.mineru_importer import build_index_from_chapters
    try:
        def check_current():
            jobs.raise_if_cancelled(job_id)
            if load_index_manifest(name).get('index_version', '') != base_version:
                raise OutlineConflict('教材已更新，请重新打开目录校准后预览')
        check_current()
        jobs.update_job(job_id, stage='structure', progress=10, message='根据示例整理全书目录')
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
