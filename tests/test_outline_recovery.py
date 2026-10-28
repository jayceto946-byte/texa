"""Independent expectations for source-neutral chapter/TOC/calibration behavior."""
from copy import deepcopy

import pytest

from ingestion.document_adapters import MinerUAdapter
from ingestion.document_ir import CanonicalBook, DocumentBlock, canonical_retrieval_paths
from ingestion.document_workflows import canonical_outline, learning_units
from ingestion.outline_recovery import recover_outline
from ingestion.chapter_splitter import ChapterSplitter
from ingestion.structure_quality import validate_index_structure


def book(lines):
    return CanonicalBook('通用教材', 'mineru', [DocumentBlock(str(i), 'paragraph', text, ['通用教材'],
        page_start=page, page_end=page) for i, (text, page) in enumerate(lines)], 'fixture')


@pytest.mark.parametrize('chapters,sections', [
    (['第一章 基础', '第二章 方法'], ['第一节 定义', '第一节 计算']),
    (['Chapter 1 Foundations', 'Chapter 2 Methods'], ['1.1 Definition', '2.1 Computation']),
    (['1 Foundations', '2 Methods'], ['1.1 Definition', '2.1 Computation']),
])
def test_missing_producer_titles_recover_chapter_and_section_without_book_rules(chapters, sections):
    source = book([(chapters[0], 1), (sections[0], 1), ('这是第一章的完整正文，不能丢失。', 1),
                   (chapters[1], 5), (sections[1], 5), ('这是第二章的完整正文，不能串章。', 5)])
    result = recover_outline(source)
    paths = canonical_retrieval_paths(result.blocks)
    assert paths['2'] == [chapters[0], sections[0]]
    assert paths['5'] == [chapters[1], sections[1]]
    assert [c['title'] for c in canonical_outline(result)] == chapters
    validate_index_structure(result, ChapterSplitter().split_canonical_book(result))


def test_real_toc_is_confirmed_by_ordered_body_matches_with_printed_page_offset():
    source = book([('目录\n第一章 基础……1\n第一节 定义……2\n第二章 方法……8\n第一节 计算……9', 2),
        ('第一章 基础', 7), ('第一节 定义', 8), ('第一章正文。', 8),
        ('第二章 方法', 14), ('第一节 计算', 15), ('第二章正文。', 15)])
    before = deepcopy(source)
    result = recover_outline(source)
    assert source == before
    assert result.blocks[0].attributes['outline_toc']
    assert result.source_metadata['outline_recovery']['toc'][0]['matched'] == 4
    assert result.blocks[5].section_path == ['第二章 方法', '第一节 计算']
    assert result.blocks[5].attributes['outline_method'] == 'toc_body_match'
    assert len(canonical_outline(result)) == 2
    chunks = ChapterSplitter().split_canonical_book(result)
    assert not any('目录' in c['content'] for c in chunks)
    validate_index_structure(result, chunks)


def test_dense_numbers_alone_never_prove_a_toc_or_delete_prose():
    source = book([('目录\n第一章 不存在……1\n第二章 也不存在……9\n第三章 仍不存在……20', 1),
                   ('这里是实际正文。', 2)])
    result = recover_outline(source)
    assert not any(b.attributes.get('outline_toc') for b in result.blocks)
    assert result.source_metadata['outline_recovery']['toc'][0]['accepted'] is False
    validate_index_structure(result, ChapterSplitter().split_canonical_book(result))


def test_one_chapter_examples_generalize_roles_and_demote_small_items_without_losing_text():
    source = book([('第一章 基础', 1), ('第一节 概念', 1), ('（1）这是正文小项', 1),
        ('自测训练', 2), ('1. 求出结果并说明理由。', 2), ('第二章 方法', 3), ('第一节 应用', 3),
        ('（2）另一个正文小项', 3), ('自测训练', 4), ('1. 计算所给参数。', 4)])
    examples = [dict(block_id='0', level=1), dict(block_id='1', level=2),
                dict(block_id='2', level=0), dict(block_id='3', level=2, role='exercise')]
    result = recover_outline(source, examples, max_depth=2)
    assert result.blocks[6].section_path == ['第二章 方法', '第一节 应用']
    assert result.blocks[7].block_type == 'paragraph'
    assert result.blocks[8].attributes['outline_role'] == 'exercise'
    assert [unit.unit_id for unit in learning_units(result) if unit.kind == 'exercise'] == ['4', '9']
    assert [b.block_id for b in result.blocks] == [b.block_id for b in source.blocks]
    assert [b.text for b in result.blocks] == [b.text for b in source.blocks]
    validate_index_structure(result, ChapterSplitter().split_canonical_book(result))
    assert recover_outline(result, force=True) == result


def test_conflicting_examples_are_explained_instead_of_silently_reordered():
    source = book([('第一章 基础', 1), ('第二章 方法', 3)])
    with pytest.raises(ValueError, match='同一种编号'):
        recover_outline(source, [dict(block_id='0', level=1), dict(block_id='1', level=2)])


def test_native_index_text_is_retained_and_used_in_shared_recovery():
    payload = dict(metadata=dict(producer=dict(name='mineru', version='4.0.12')),
        pages=[dict(page_idx=0, blocks=[dict(type='index', content='目录\nChapter 1 Basics……1\nChapter 2 Methods……4')]),
               dict(page_idx=4, blocks=[dict(type='text', content='Chapter 1 Basics'), dict(type='text', content='Actual body one.')]),
               dict(page_idx=7, blocks=[dict(type='text', content='Chapter 2 Methods'), dict(type='text', content='Actual body two.')])])
    result = MinerUAdapter.from_structured_content(payload, book_name='新教材')
    assert result.blocks[0].attributes['outline_toc']
    assert result.blocks[-1].section_path == ['Chapter 2 Methods']


def test_pdf_bookmarks_keep_all_levels_and_physical_pages_without_vision(tmp_path):
    import fitz
    from ingestion.document_adapters import PdfTextAdapter
    path = tmp_path/'source.pdf'
    with fitz.open() as doc:
        for title in ['Foundations', 'Definitions', 'Methods', 'Applications']:
            page = doc.new_page()
            page.insert_text((50, 60), title, fontsize=18)
            page.insert_text((50, 90), 'This is the complete original body paragraph.', fontsize=11)
        doc.set_toc([[1, 'Foundations', 1], [2, 'Definitions', 2], [1, 'Methods', 3], [2, 'Applications', 4]])
        doc.save(path)
    result = PdfTextAdapter.from_pdf(path, book_name='Unseen textbook')
    assert result.source_metadata['outline_recovery']['matched_bookmarks'] == 4
    assert result.blocks[-1].section_path == ['Methods', 'Applications']
    assert result.blocks[-1].page_start == 4
    validate_index_structure(result, ChapterSplitter().split_canonical_book(result))


def test_document_font_patterns_and_user_style_example_never_promote_long_prose():
    source = book([('Foundations', 1), ('a complete paragraph, preserved. ' * 20, 1),
                   ('Methods', 2), ('another complete paragraph, preserved. ' * 20, 2)])
    for i, block in enumerate(source.blocks):
        block.attributes['font_size'] = 18 if i % 2 == 0 else 11
    result = recover_outline(source)
    assert [c['title'] for c in canonical_outline(result)] == ['Foundations', 'Methods']
    result = recover_outline(result, [dict(block_id='0', level=1)], force=True)
    assert result.blocks[2].attributes['outline_method'] == 'user_example'
    assert result.blocks[-1].block_type == 'paragraph'


def test_front_matter_is_searchable_without_becoming_a_fake_chapter():
    source = book([('Preface and acknowledgements.', 1), ('Chapter 1: Foundations', 3),
                   ('1.1 Definitions', 3), ('Body text preserved.', 3), ('Chapter 2: Methods', 8),
                   ('2.1 Applications', 8), ('Another body paragraph.', 8)])
    result = recover_outline(source)
    assert [c['title'] for c in canonical_outline(result)] == ['Chapter 1: Foundations', 'Chapter 2: Methods']
    chunks = ChapterSplitter().split_canonical_book(result)
    assert any('Preface' in c['content'] for c in chunks)
    validate_index_structure(result, chunks)


def test_navigation_depth_never_erases_exercise_semantics():
    source = book([('第一章 基础', 1), ('第一节 原理', 1), ('习题', 2), ('1. 计算结果。', 2)])
    result = recover_outline(source, max_depth=1)
    assert canonical_outline(result)[0]['subsections'] == []
    assert [u.unit_id for u in learning_units(result) if u.kind == 'exercise'] == ['3']
    assert result.blocks[2].attributes['outline_visible'] is False


def test_preview_rejects_changed_index_before_loading_or_editing_source(monkeypatch):
    from backend.services import book_outline
    from ingestion import index_pipeline
    monkeypatch.setattr(index_pipeline, 'load_index_manifest', lambda _: dict(index_version='new'))
    monkeypatch.setattr(book_outline, 'load_canonical_book', lambda *a, **k: pytest.fail('stale preview must stop before reading source'))
    with pytest.raises(book_outline.OutlineConflict, match='教材已更新'):
        book_outline.preview_outline('any textbook', progress_root='unused', base_version='old')
