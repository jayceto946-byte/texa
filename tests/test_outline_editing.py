from ingestion.document_ir import CanonicalBook, DocumentBlock
from ingestion.document_workflows import canonical_outline
from ingestion.outline_recovery import recover_outline


def source():
    rows = [('第一章 基础', 1), ('第一节 定义', 1), ('前半章正文。', 2),
            ('同页前段正文。', 3), ('同页后段正文。', 3), ('下一页正文。', 4),
            ('第三章 应用', 5), ('后章正文。', 5)]
    return recover_outline(CanonicalBook('校正样本', 'test', [DocumentBlock(str(i), 'paragraph', text,
        ['校正样本'], page_start=page, page_end=page, source_kind='test', source_file='source')
        for i, (text, page) in enumerate(rows)], 'test'))


def test_create_missing_chapter_splits_inside_a_page_and_preserves_original_nodes():
    original = source()
    edit = dict(node_id='new-middle', created=True, title='第二章 方法', level=1, page=3,
                anchor_block_id='4', role='section')
    result = recover_outline(original, force=True, edits=[edit])
    assert result.blocks[3].section_path[0] == '第一章 基础'
    assert next(b for b in result.blocks if b.block_id == '4').section_path[0] == '第二章 方法'
    assert [(c['title'], c['page_number']) for c in canonical_outline(result)] == [
        ('第一章 基础',1), ('第二章 方法',3), ('第三章 应用',5)]
    assert [(b.block_id,b.text) for b in result.blocks if b.source_kind=='test'] == [(b.block_id,b.text) for b in original.blocks]
    assert recover_outline(result, force=True) == result
    assert canonical_outline(result)[0]['subsections'][0]['source_block_ids'] == ['1','2','3']


def test_move_and_rename_existing_chapter_then_restore_recognized_outline():
    original = source()
    edits = [dict(node_id='6', title='第二章 新方法', level=1, page=4, anchor_block_id='5', role='section')]
    result = recover_outline(original, force=True, edits=edits)
    assert next(b for b in result.blocks if b.block_id=='5').section_path == ['第二章 新方法']
    assert next(b for b in result.blocks if b.block_id=='6').block_type == 'paragraph'
    assert [c['title'] for c in canonical_outline(result)] == ['第一章 基础','第二章 新方法']
    moved = recover_outline(result, force=True, edits=[{**edits[0], 'page':3, 'anchor_block_id':'4'}])
    assert canonical_outline(result)[1]['heading_block_id'] != canonical_outline(moved)[1]['heading_block_id']
    restored = recover_outline(result, force=True, edits=[])
    assert [(b.block_id, b.section_path) for b in restored.blocks] == [(b.block_id, b.section_path) for b in original.blocks]
    assert [c['title'] for c in canonical_outline(restored)] == [c['title'] for c in canonical_outline(original)]


def test_bad_page_anchor_is_rejected_instead_of_silently_moving_the_boundary():
    import pytest
    with pytest.raises(ValueError,match='起点与物理页'):
        recover_outline(source(), force=True, edits=[dict(node_id='new',created=True,title='第二章',level=1,page=4,anchor_block_id='4')])
    with pytest.raises(ValueError,match='一级标题.*已存在'):
        recover_outline(source(), force=True, edits=[dict(node_id='new',created=True,title='第一章 基础',level=1,page=3,anchor_block_id='4')])


def test_unrelated_edit_keeps_a_chapter_recovered_only_from_toc_pages():
    from test_outline_recovery import omitted_chapter_source
    original = recover_outline(omitted_chapter_source())
    result = recover_outline(original, force=True, edits=[dict(node_id='1', title='第一章 新基础',
        level=1, page=8, anchor_block_id='1', role='section')])
    assert [c['title'] for c in canonical_outline(result)] == ['第一章 新基础','第二章 方法','第三章 应用']


def test_whole_chapter_highlights_retain_introduction_without_absorbing_exercises(tmp_path):
    from knowledge.chapter_highlights import ChapterHighlightService
    from knowledge.chapter_highlight_types import ChapterRef,SectionRef
    service=ChapterHighlightService(tmp_path,tmp_path/'no-ocr')
    chunks=[dict(chunk_id=k,block_id=k,text=k,page=1) for k in ['intro','body','exercise']]
    refs=[SectionRef('section',0,'第一节 方法',1,source_block_ids=['body']),
          SectionRef('exercises',1,'习题',1,is_auxiliary=True,source_block_ids=['exercise'])]
    sections,_,_=service._apply_scope([dict(title='章',chunks=chunks)],refs,ChapterRef('chapter',0,'章',1),'all')
    assert [c['block_id'] for s in sections for c in s['chunks']]==['intro','body']
