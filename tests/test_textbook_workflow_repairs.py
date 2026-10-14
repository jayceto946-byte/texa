"""Regression inputs for native chapter, whole-exercise and page projections."""
import json

import pytest

from ingestion.acceptance_probes import generate_acceptance_probes
from ingestion.document_adapters import MinerUAdapter
from ingestion.document_ir import persist_canonical_book
from ingestion.document_workflows import canonical_outline, learning_units, load_workflow_book
from memory.textbook_exercise_importer import extract_textbook_exercise_text, analyze_learning_unit_candidates


def native_book():
    return MinerUAdapter.from_structured_content(dict(
        metadata=dict(producer=dict(name='mineru', version='4.0.8'), document=dict(page_count=2)),
        pages=[dict(page_idx=0, blocks=[
            dict(type='paragraph_title', content='第1章 绪论', level=1),
            dict(type='paragraph_title', content='1.1 特性', level=2),
            dict(type='paragraph_title', content='1.1.1 静态特性', level=3),
            dict(type='text', content='【例 1.1】给定两个测量结果，求均值。'),
            dict(type='table', content='| 测次 | 结果 |\n|---|---|\n| 1 | 2 |\n| 2 | 4 |'),
            dict(type='text', content='解：将两个数相加，再除以测次。'),
            dict(type='equation', content='x=(2+4)/2=3', latex='x=(2+4)/2=3'),
            dict(type='paragraph_title', content='1.1.2 动态特性', level=3),
            dict(type='text', content='另一主题的正文不得混入例题。'),
            dict(type='page_number', content='19'),
        ]), dict(page_idx=1, blocks=[
            dict(type='paragraph_title', content='习题', level=2),
            dict(type='text', content='1. 给定下表，求两组结果。'),
            dict(type='table', content='| 测次 | 结果 |\n|---|---|\n| 1 | 5 |'),
            dict(type='text', content='（1）计算均值。'),
            dict(type='paragraph_title', content='(2) 计算误差。', level=2),
            dict(type='text', content='2. 解释测量不确定性。'),
        ])]), book_name='修复教材')


def test_outline_retains_nested_same_page_block_ranges_and_printed_label():
    book = native_book()
    sections = canonical_outline(book)[0]['subsections']
    static = next(section for section in sections if section['title'] == '1.1.1 静态特性')
    dynamic = next(section for section in sections if section['title'] == '1.1.2 动态特性')
    parent = next(section for section in sections if section['title'] == '1.1 特性')
    assert static['parent_heading_block_id'] == parent['heading_block_id']
    assert static['level'] == 3 and static['printed_page'] == '19'
    assert static['page'] == dynamic['page'] == 1
    assert set(static['source_block_ids']).isdisjoint(dynamic['source_block_ids'])


def test_bracket_example_and_subquestions_stay_whole_without_following_topic():
    book = native_book()
    units = learning_units(book)
    assert [unit.kind for unit in units] == ['example', 'exercise', 'exercise']
    assert '测次' in units[0].text and '解：' in units[0].text and 'x=(2+4)/2=3' in units[0].text
    assert '另一主题' not in units[0].text
    assert '（1）' in units[1].text and '(2)' in units[1].text and '解释测量' not in units[1].text
    assert all(block.attributes.get('example_id') == units[0].unit_id for block in units[0].blocks)
    assert [block.block_type for block in units[0].blocks] == ['example', 'table', 'example', 'formula']
    from ingestion.chapter_splitter import ChapterSplitter
    rows = [row for row in ChapterSplitter().split_canonical_book(book) if set(row['source_block_ids']) & {block.block_id for block in units[0].blocks}]
    assert len({row['parent_id'] for row in rows}) == 1
    probes = generate_acceptance_probes(book)
    assert probes['source_inventory']['example'] == 1
    case = next(case for case in probes['cases'] if case['specialty'] == 'example')
    assert case['provenance']['source_block_ids'] == [block.block_id for block in units[0].blocks]


def test_canonical_import_works_without_pdf_or_compat_outputs(tmp_path, monkeypatch):
    import memory.textbook_exercise_importer as module
    book = native_book()
    persist_canonical_book(book, progress_root=tmp_path)
    monkeypatch.setattr(module, 'PROGRESS_PATH', tmp_path)
    extracted = extract_textbook_exercise_text(book.book_name, chapter='第1章 绪论', source_mode='examples')
    assert extracted.provider == 'canonical-learning-units'
    assert len(extracted.units) == extracted.chunk_count == 1
    candidates = analyze_learning_unit_candidates(extracted.units, book_name=book.book_name, subject='专业课', limit=10)
    assert len(candidates) == 1 and candidates[0].chapter == '第1章 绪论'
    assert '测次' in candidates[0].question_text
    assert extracted.units[0]['unit_id'] in candidates[0].source


def test_active_manifest_mismatch_is_not_silently_used(tmp_path):
    book = native_book()
    persist_canonical_book(book, progress_root=tmp_path / 'progress')
    manifests = tmp_path / 'vector' / '_index_manifests'
    manifests.mkdir(parents=True)
    (manifests / f'{book.book_name}.json').write_text(json.dumps({'canonical_hash': 'stale-version'}))
    with pytest.raises(ValueError, match='版本不一致'):
        load_workflow_book(book.book_name, progress_root=tmp_path / 'progress', vector_root=tmp_path / 'vector')


def test_heading_id_selects_same_page_scope_without_title_rebinding(tmp_path, monkeypatch):
    book = native_book()
    persist_canonical_book(book, progress_root=tmp_path)
    monkeypatch.setattr('memory.textbook_exercise_importer.PROGRESS_PATH', tmp_path)
    static = next(section for section in canonical_outline(book)[0]['subsections'] if section['title'] == '1.1.1 静态特性')
    extracted = extract_textbook_exercise_text(book.book_name, chapter=f"heading:{static['heading_block_id']}", source_mode='all_pages')
    assert '【例 1.1】' in extracted.text and '另一主题' not in extracted.text
    with pytest.raises(ValueError, match='重新选择'):
        extract_textbook_exercise_text(book.book_name, chapter='heading:missing', source_mode='examples')


def test_highlight_scope_uses_canonical_blocks_for_same_page_sections(tmp_path):
    from knowledge.chapter_highlights import ChapterHighlightService
    book = native_book()
    persist_canonical_book(book, progress_root=tmp_path)
    service = ChapterHighlightService(progress_path=tmp_path, mineru_output_path=tmp_path / 'raw')
    chapter = service._load_chapter_refs(book.book_name)[0]
    static = next(section for section in service._load_section_refs(book.book_name, chapter) if section.title == '1.1.1 静态特性')
    package = service.build_source_package(book.book_name, chapter.id, static.id)
    text = '\n'.join(chunk['text'] for section in package['sections'] for chunk in section['chunks'])
    assert '【例 1.1】' in text and '另一主题' not in text
    package = service.build_source_package(book.book_name, chapter.id)
    ids = [chunk['block_id'] for section in package['sections'] for chunk in section['chunks']]
    assert len(ids) == len(set(ids))
