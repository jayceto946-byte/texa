"""Screenshot-shaped regressions; synthetic stems, no customer textbook data."""
from copy import deepcopy
from dataclasses import asdict
import json

import pytest

from ingestion.document_adapters import MinerUAdapter
from ingestion.document_ir import canonical_book_fingerprint, persist_canonical_book
from ingestion.document_workflows import canonical_outline, enrich_chapters, learning_units
from memory.textbook_exercise_importer import extract_textbook_exercise_text


def source():
    titles = ['第2章 电阻式传感器', '第一节 应变式传感器', '四、转换电路',
              '（一）直流电桥', '（二）直流电桥的非线性误差',
              '为了减小非线性误差，常采用', '的措施为', '（三）交流电桥',
              '五、温度误差及其补偿', '（二）温度补偿',
              '在某些情况下，可以比较巧妙', '地安装应变片而不需补偿件并兼得',
              '第二节 压阻式传感器', '一、基本工作原理', '思考题与习题']
    return dict(metadata=dict(producer=dict(name='mineru', version='4.0.12'), document=dict(page_count=4)), pages=[
        dict(page_idx=0, blocks=[dict(type='paragraph_title', content=t, level=2) for t in titles]),
        dict(page_idx=1, blocks=[dict(type='paragraph_title', content='2-1 解释传感器的工作原理。', level=2),
                               dict(type='text', content='（1）说明转换过程。'),
                               dict(type='equation', content='y=kx')]),
        dict(page_idx=2, blocks=[dict(type='text', content='2-2 已知给定电桥参数，求输出电压。'),
                               dict(type='text', content='解：由原文电桥条件可得结果。')]),
        dict(page_idx=3, blocks=[dict(type='paragraph_title', content='第3章 电容式传感器', level=2),
                               dict(type='paragraph_title', content='思考题与习题', level=2),
                               dict(type='text', content='3-1 解释电容变化的来源。')])])


def test_native_outline_rejects_body_fragments_and_recovers_chinese_hierarchy():
    book = MinerUAdapter.from_structured_content(source(), book_name='合成传感器')
    sections = canonical_outline(book)[0]['subsections']
    by_title = {s['title']: s for s in sections}
    assert '的措施为' not in by_title
    assert not any(s['title'].startswith(('为了', '在某些', '地安装')) for s in sections)
    assert by_title['（二）直流电桥的非线性误差']['parent_heading_block_id'] == by_title['四、转换电路']['heading_block_id']
    assert by_title['四、转换电路']['parent_heading_block_id'] == by_title['第一节 应变式传感器']['heading_block_id']
    assert by_title['思考题与习题']['section_path'] == ['第2章 电阻式传感器', '思考题与习题']
    units = learning_units(book)
    assert len(units) == 3
    assert '（1）说明转换过程' in units[0].text and 'y=kx' in units[0].text
    assert '解：' in units[1].text and '3-1' not in units[1].text


@pytest.mark.parametrize('version', [None, 1])
def test_combined_heading_exact_scope_and_physical_pages(tmp_path, monkeypatch, version):
    book = MinerUAdapter.from_structured_content(source(), book_name='合成传感器')
    persist_canonical_book(book, progress_root=tmp_path)
    # Legacy metadata has printed pages and stale subsections. Canonical IDs and
    # physical pages must win when Canonical is available.
    stale = [dict(title='第2章 电阻式传感器', page_number=91, end_page=99,
                  subsections=[dict(title='的措施为', page=91)])]
    (tmp_path / book.book_name / '_chapters.json').write_text(json.dumps(stale))
    monkeypatch.setattr('memory.textbook_exercise_importer.PROGRESS_PATH', tmp_path)
    section = next(s for s in canonical_outline(book)[0]['subsections'] if s['title'] == '思考题与习题')
    result = extract_textbook_exercise_text(book.book_name, chapter='heading:' + section['heading_block_id'],
                                          candidate_contract_version=version)
    assert len(result.units) == 2 and '3-1' not in result.text
    assert result.page_start == 1 and result.page_end == 3
    chapter = extract_textbook_exercise_text(book.book_name, chapter=stale[0]['title'], candidate_contract_version=version)
    assert len(chapter.units) == 2
    assert all(bid in section['source_block_ids'] for u in result.units for bid in u['source_block_ids'])
    assert not any(s['title'] == '的措施为' for s in enrich_chapters(stale, book)[0]['subsections'])
    from memory.textbook_exercise_importer import analyze_learning_unit_candidates
    candidates = analyze_learning_unit_candidates(result.units, book_name=book.book_name, subject='专业课', limit=20,
        **(dict(source_blocks=result.source_blocks, canonical_hash=result.canonical_hash,
                scope=dict(chapter='heading:' + section['heading_block_id'], page_start=None, page_end=None,
                           source_mode='exercise_sections')) if version == 1 else {}))
    assert len(candidates) == 2


@pytest.mark.parametrize('title', ['思考题与习题', '思考题及习题', '练习题', '习题 2', '本章习题'])
def test_exercise_titles_do_not_match_body_mentions(title):
    data = source()
    data['pages'][0]['blocks'][-1]['content'] = title
    book = MinerUAdapter.from_structured_content(data, book_name='合成传感器')
    assert len(learning_units(book)) == 3
    data['pages'][0]['blocks'][-1]['content'] = '本节介绍思考题与习题的编写方法'
    book = MinerUAdapter.from_structured_content(data, book_name='合成传感器')
    assert len(learning_units(book)) == 1


def test_old_native_projection_keeps_source_and_fingerprint():
    book = MinerUAdapter.from_structured_content(source(), book_name='合成传感器')
    # Recreate v4's already-persisted false heading without reparsing the IR.
    bad = next(b for b in book.blocks if b.text == '的措施为')
    bad.block_type = 'heading'
    bad.attributes['heading_rule'] = 'bounded_unnumbered'
    bad.section_path = ['第2章 电阻式传感器', bad.text]
    original = deepcopy(asdict(book))
    fingerprint = canonical_book_fingerprint(book)
    assert not any(s['title'] == bad.text for s in canonical_outline(book)[0]['subsections'])
    learning_units(book)
    assert canonical_book_fingerprint(book) == fingerprint
    assert asdict(book) == original


def test_weak_title_text_survives_indexing_and_loss_is_detected():
    from ingestion.chapter_splitter import ChapterSplitter
    from ingestion.structure_quality import validate_index_structure
    data = source()
    data['pages'][0]['blocks'].insert(2, dict(type='paragraph_title', content='待核对的短标题', level=2))
    book = MinerUAdapter.from_structured_content(data, book_name='结构保真')
    chunks = ChapterSplitter().split_canonical_book(book)
    assert any('待核对的短标题' in row['content'] for row in chunks)
    assert any('的措施为' in row['content'] for row in chunks)
    validate_index_structure(book, chunks)
    title = next(b for b in book.blocks if b.text == '待核对的短标题')
    with pytest.raises(RuntimeError, match='missing_body_blocks'):
        validate_index_structure(book, [r for r in chunks if title.block_id not in r['source_block_ids']])
    wrong = deepcopy(chunks)
    for row in wrong:
        row['chapter'] = '另一章'
    with pytest.raises(RuntimeError, match='wrong_chapter_blocks'):
        validate_index_structure(book, wrong)


def test_structure_diagnostics_are_generated_by_normal_intake():
    from ingestion.document_ir import validate_canonical_book
    book = MinerUAdapter.from_structured_content(source(), book_name='结构报告')
    report = validate_canonical_book(book).to_dict()
    audit = report['source_metadata']['structure_quality']
    assert audit['chapters'] == 2 and audit['exercise_units'] == 3
    assert audit['title_blocks_retained_as_body'] >= 4
    assert audit['unrecognized_exercise_start_ids'] == []


def test_unrecognized_numbering_is_reported_even_without_any_recognized_start():
    from ingestion.document_ir import validate_canonical_book
    data = dict(metadata=dict(producer=dict(name='mineru', version='4.0.12')), pages=[dict(page_idx=0, blocks=[
        dict(type='paragraph_title', content='第1章 合成练习'),
        dict(type='paragraph_title', content='思考题与习题'),
        dict(type='text', content='第一题：解释给定系统的转换原理。')])])
    book = MinerUAdapter.from_structured_content(data, book_name='未知题号')
    report = validate_canonical_book(book).to_dict()
    quality = report['source_metadata']['structure_quality']
    assert quality['exercise_units'] == quality['exercise_starts'] == 0
    assert len(quality['exercise_sections_without_units']) == 1
    assert any(i['code'] == 'exercise_section_without_units' for i in report['issues'])
    assert report['valid']  # Source-quality review never destroys a usable body.


def test_body_loss_is_rejected_before_vector_io_without_replacing_active_book(tmp_path, monkeypatch):
    from ingestion import mineru_importer
    book = MinerUAdapter.from_structured_content(source(), book_name='结构报告')
    active = tmp_path / 'progress' / book.book_name / 'canonical_document.jsonl'
    active.parent.mkdir(parents=True)
    active.write_bytes(b'untouched-active-version')
    class BrokenSplitter:
        def split_canonical_book(self, book):
            return []
    monkeypatch.setattr(mineru_importer, 'ChapterSplitter', BrokenSplitter)
    monkeypatch.setattr(mineru_importer, 'load_kg_chunk_roles', lambda _: {})
    monkeypatch.setattr(mineru_importer, 'get_vector_store', lambda: pytest.fail('must fail before vector IO'))
    with pytest.raises(RuntimeError, match='missing_body_blocks'):
        mineru_importer.build_index_from_chapters(book.book_name, [], tmp_path,
            canonical_book=book, canonical_progress_root=tmp_path / 'progress')
    assert active.read_bytes() == b'untouched-active-version'
