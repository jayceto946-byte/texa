"""Retained old IR must be republished before consumers use repaired scopes."""
import json

import pytest

from test_index_pipeline import FakeStore
from test_outline_recovery import omitted_chapter_source

from ingestion.document_ir import persist_canonical_book, load_canonical_book
from ingestion.document_workflows import canonical_outline
from ingestion.outline_recovery import recover_outline


def retained_legacy_book():
    book = recover_outline(omitted_chapter_source())
    # The v3 reader had no body occurrence for the second chapter label.
    for block in book.blocks[4:6]:
        block.section_path[0] = '第一章 基础'
        block.attributes['outline_root_id'] = '1'
        block.attributes.pop('outline_boundary', None)
    book.source_metadata['outline_recovery'].update(version=3, roots=2, stable_scope_ids=False,
                                                   recovered_chapters=0)
    return book


def test_current_policy_stamp_does_not_hide_a_missing_retained_source_chapter(tmp_path):
    from backend.services.book_outline import outline_refresh_status
    from ingestion.outline_recovery import POLICY_VERSION
    book = retained_legacy_book()
    book.source_metadata['outline_recovery']['version'] = POLICY_VERSION
    book.source_metadata['document_titles'] = [dict(text='第二章 方法', page_idx=16, source_block_index=0)]
    persist_canonical_book(book, progress_root=tmp_path)
    assert outline_refresh_status(book.book_name, progress_root=tmp_path)['status'] == 'outdated'


@pytest.mark.parametrize('publication_succeeds', [True, False])
def test_retained_outline_rebuild_publishes_all_scopes_or_preserves_old_version(monkeypatch, tmp_path, publication_succeeds):
    from backend.job_manager import JobManager
    from backend.services.book_outline import apply_outline, outline_refresh_status
    from ingestion import index_pipeline, lexical_index, document_workflows, mineru_importer
    from knowledge.chapter_highlights import ChapterHighlightService

    vector = tmp_path / 'vector'
    progress = tmp_path / 'progress'
    store = FakeStore(vector)
    for module in (index_pipeline, lexical_index, document_workflows):
        monkeypatch.setattr(module, 'VECTOR_DB_PATH', vector)
    # load_workflow_book's default root is bound at import time.
    monkeypatch.setattr(document_workflows.load_workflow_book, '__kwdefaults__', {'vector_root': vector})
    monkeypatch.setattr(mineru_importer, 'get_vector_store', lambda: store)
    legacy = retained_legacy_book()
    persist_canonical_book(legacy, progress_root=progress)
    directory = progress / legacy.book_name
    (directory / '_chapters.json').write_text(json.dumps(canonical_outline(legacy)), encoding='utf-8')
    mineru_importer.build_index_from_chapters(legacy.book_name, [], directory, canonical_book=legacy)
    original_version = index_pipeline.load_index_manifest(legacy.book_name)['index_version']
    old_document = load_canonical_book(legacy.book_name, progress_root=progress)
    highlights = ChapterHighlightService(progress, tmp_path / 'no-ocr')
    old_artifact = highlights.chapter_dir(legacy.book_name, 'chapter_002') / 'highlight.html'
    old_artifact.parent.mkdir(parents=True)
    old_artifact.write_text('第三章原有重点', encoding='utf-8')

    status = outline_refresh_status(legacy.book_name, progress_root=progress)
    assert status['status'] == 'outdated'
    assert (status['chapter_count'], status['updated_chapter_count']) == (2, 3)
    assert load_canonical_book(legacy.book_name, progress_root=progress) == old_document
    jobs = JobManager(progress / 'jobs.sqlite3')
    job = jobs.create_job('textbook_outline', {'book_name': legacy.book_name}, status='running')
    store._client.query_ok = publication_succeeds
    published = []
    apply_outline(legacy.book_name, progress_root=progress, base_version=original_version,
                  examples=None, max_depth=None, jobs=jobs, job_id=job['id'], on_published=lambda: published.append(True))
    final = jobs.get_job(job['id'])
    if not publication_succeeds:
        assert final['status'] == 'failed'
        assert index_pipeline.load_index_manifest(legacy.book_name)['index_version'] == original_version
        assert load_canonical_book(legacy.book_name, progress_root=progress) == old_document
        assert not published
    else:
        assert final['status'] == 'completed', final
        assert published
        assert outline_refresh_status(legacy.book_name, progress_root=progress)['status'] == 'current'
        refs = highlights._load_chapter_refs(legacy.book_name)
        assert [ref.title for ref in refs] == ['第一章 基础', '第二章 方法', '第三章 应用']
        assert all(ref.id not in {'chapter_001', 'chapter_002'} for ref in refs)
        packages = [highlights.build_source_package(legacy.book_name, ref.id) for ref in refs]
        for i, marker in enumerate(['前章独有内容', '中章独有内容', '后章独有内容']):
            assert marker in str(packages[i])
            assert all(marker not in str(package) for j, package in enumerate(packages) if j != i)
        active = [entry for entry in store._map.values() if entry.get('active', True) and entry.get('book_name') == legacy.book_name]
        assert {entry['chapter'] for entry in active if entry['kind'] == 'chapter'} == {ref.title for ref in refs}
    assert old_artifact.read_text(encoding='utf-8') == '第三章原有重点'
    assert highlights.get_highlight(legacy.book_name, 'chapter_002')['html_path'] == str(old_artifact)
