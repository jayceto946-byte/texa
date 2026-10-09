import copy
import json
from pathlib import Path
import shutil

import pytest
from PIL import Image
from ingestion.document_adapters import MinerUAdapter
from ingestion.document_assets import materialize_document_assets
from ingestion.document_ir import canonical_book_fingerprint, persist_canonical_book, load_canonical_book, validate_canonical_book
from ingestion.chapter_splitter import ChapterSplitter


def payload():
    return dict(metadata=dict(producer=dict(name='mineru', version='4.0.8'), document=dict(page_count=2)), pages=[
        dict(page_idx=0, page_number='i', blocks=[
            dict(type='doc_title', content='合成教材', level=1),
            dict(type='header', content='页眉'),
            dict(type='index', content='第1章 ... 1'),
            dict(type='paragraph_title', content='第1章 合成正文', level=2),
            dict(type='paragraph_title', content='1.1 概念', level=2),
            dict(type='paragraph_title', content='1.1.1 定义', level=2),
            dict(type='text', content='定义：模块的响应由输入与参数决定，内联公式 $x+1$。'),
            dict(type='paragraph_title', content='1. 特点', level=2),
            dict(type='text', content='主要有以下特点：结构简单，响应稳定。'),
            dict(type='equation', content=r'y=x+1', text=r'y=x+1', latex=r'y=x+1', image_source='images/e.png', bbox=[.1,.2,.5,.4]),
        ]),
        dict(page_idx=1, page_number='1', blocks=[
            dict(type='paragraph_title', content='非编号标题', level=2),
            dict(type='text', content='这一段属于非编号标题，但不建立额外章节。'),
            dict(type='paragraph_title', content='另一个非编号标题', level=2),
            dict(type='table', content='| 参数 | 数值 |\n| --- | --- |\n| x | 1 |\n| y | 2 |',
                 captions=[dict(content='表1 参数')], footnotes=[dict(content='注：合成数据')],
                 image_source='images/t.png', bbox=[.1,.2,.6,.5]),
            dict(type='image', content='', captions=[], footnotes=[], image_source='images/f.png', bbox=[.2,.3,.7,.8]),
            dict(type='chart', content='', captions=[dict(content='曲线')], image_source='images/f.png'),
            dict(type='ref_text', content='[1] 合成参考文献。'),
            dict(type='future_readable', content='未知类型仍保留可读正文。'),
            dict(type='footer', content='页脚'), dict(type='page_number', content='1'),
        ]),
    ])


def source(tmp_path):
    output = tmp_path / 'output'
    (output / 'images').mkdir(parents=True)
    for name in ['e', 't', 'f']:
        Image.new('RGB', (24, 12), 'white').save(output / 'images' / f'{name}.png')
    (output / 'structured_content.json').write_text(json.dumps(payload(), ensure_ascii=False))
    return output


def test_native_caption_and_footnote_coordinates_survive_as_neutral_nodes():
    sample = payload()
    figure = sample['pages'][1]['blocks'][4]
    figure.update(captions=[dict(content='图 2.15 工艺流程', bbox=[.2,.81,.7,.83])],
                  footnotes=[dict(content='(d) 曝光', bbox=[.3,.8,.4,.81])])
    book = MinerUAdapter.from_structured_content(sample, book_name='coordinates')
    block = next(b for b in book.blocks if b.block_type == 'figure' and b.bbox)
    assert block.attributes['visual_captions'] == [dict(text='图 2.15 工艺流程', bbox=[.2,.81,.7,.83]),
                                                 dict(text='(d) 曝光', bbox=[.3,.8,.4,.81])]


def test_native_mapping_hierarchy_formula_and_provenance(tmp_path):
    output = source(tmp_path)
    book = MinerUAdapter.from_output_dir(output, book_name='demo')
    assert validate_canonical_book(book).valid
    definition = next(b for b in book.blocks if b.text.startswith('定义：'))
    assert definition.section_path == ['第1章 合成正文', '1.1 概念', '1.1.1 定义']
    local = next(b for b in book.blocks if b.text == '1. 特点')
    assert local.block_type == 'paragraph'
    assert local.section_path == definition.section_path
    titles = [b for b in book.blocks if b.text in ['非编号标题', '另一个非编号标题']]
    assert [b.section_path[:-1] for b in titles] == [definition.section_path, definition.section_path]
    equation = next(b for b in book.blocks if b.block_type == 'formula')
    assert equation.text == r'y=x+1' and equation.equations == [r'y=x+1']
    assert equation.attributes['source_block_index'] == 9
    assert equation.attributes['source_page_idx'] == 0 and equation.page_start == 1
    assert equation.attributes['printed_page_number'] == 'i'
    assert equation.attributes['bbox_units'] == 'normalized'
    assert equation.ocr_confidence is None
    assert next(b for b in book.blocks if b.block_type == 'table').table_rows == [['x','1'],['y','2']]
    assert len([b for b in book.blocks if b.block_type == 'figure']) == 2
    assert book.source_metadata['excluded_counts'] == dict(doc_title=1, header=1, index=1, footer=1, page_number=1)
    assert any('Unknown readable' in warning for warning in book.warnings)
    assert next(b for b in book.blocks if b.attributes['mineru_type'] == 'ref_text').attributes['semantic_role'] == 'reference'


def test_native_preferred_and_invalid_native_is_not_silently_bridged(tmp_path):
    output = source(tmp_path)
    (output / 'texa_content_list_v1.json').write_text(json.dumps([dict(type='text', text='bridge should not win')]))
    assert MinerUAdapter.from_output_dir(output, book_name='demo').parser_version == 'mineru-structured-content-v3'
    (output / 'structured_content.json').write_text('{')
    with pytest.raises(ValueError, match='Invalid native'):
        MinerUAdapter.from_output_dir(output, book_name='demo')


@pytest.mark.parametrize('mutation', ['version', 'page', 'blocks', 'content'])
def test_malformed_native_has_explicit_diagnosis(mutation):
    p = payload()
    if mutation == 'version': p['metadata']['producer']['version'] = '5.0.0'
    if mutation == 'page': p['pages'][1]['page_idx'] = 0
    if mutation == 'blocks': p['pages'][0]['blocks'] = {}
    if mutation == 'content': p['pages'][0]['blocks'][0]['content'] = 7
    with pytest.raises(ValueError):
        MinerUAdapter.from_structured_content(p, book_name='demo')


def test_multiple_native_documents_are_ambiguous(tmp_path):
    output = source(tmp_path)
    other = output / 'other'
    other.mkdir()
    (other / 'structured_content.json').write_text(json.dumps(payload()))
    with pytest.raises(ValueError, match='multiple structured'):
        MinerUAdapter.from_output_dir(output, book_name='demo')


def test_derived_chunks_and_v2_middle_are_not_sources(tmp_path):
    (tmp_path / 'demo_middle_chunks.json').write_text(json.dumps([dict(content='derived')]))
    (tmp_path / 'middle_json.json').write_text(json.dumps(dict(schema='docvortex.middle', version='2.0', pages=[])))
    book = MinerUAdapter.from_output_dir(tmp_path, book_name='demo')
    assert not book.blocks
    assert book.warnings


def test_moved_directory_and_serialized_assets_are_deterministic(tmp_path):
    output = source(tmp_path)
    moved = tmp_path / 'moved'
    shutil.copytree(output, moved)
    first = MinerUAdapter.from_output_dir(output, book_name='demo')
    second = MinerUAdapter.from_output_dir(moved, book_name='demo')
    for book, root in [(first, output), (second, moved)]:
        materialize_document_assets(book, source_root=root, progress_root=tmp_path / 'progress')
        validate_canonical_book(book)
    assert canonical_book_fingerprint(first) == canonical_book_fingerprint(second)
    persist_canonical_book(first, progress_root=tmp_path / 'progress')
    loaded = load_canonical_book('demo', progress_root=tmp_path / 'progress')
    assert canonical_book_fingerprint(loaded) == canonical_book_fingerprint(first)
    assets = [b for b in loaded.blocks if b.attributes.get('original_visual_asset')]
    assert len(assets) == 2
    assert all(b.attributes['original_visual_asset']['status'] == 'ready' for b in assets)
    assert len(list((tmp_path / 'progress/demo/original_visuals').iterdir())) == 2
    chunks = ChapterSplitter(chunk_size=32, chunk_overlap=0).split_canonical_book(loaded)
    table = next(b for b in loaded.blocks if b.block_type == 'table')
    table_chunks = [c for c in chunks if c['block_type'] == 'table']
    assert table_chunks and all(c['source_block_ids'] == [table.block_id] for c in table_chunks)
    assert len([b for b in loaded.blocks if b.block_type == 'figure']) == 2


def test_formal_structured_only_importer(monkeypatch, tmp_path):
    from ingestion import mineru_importer
    output = source(tmp_path)
    monkeypatch.setattr(mineru_importer.config, 'PROGRESS_PATH', tmp_path / 'progress')
    monkeypatch.setattr(mineru_importer, 'load_kg_chunk_roles', lambda _: {})
    class Store:
        def build_chapter_store(self, *_args, **_kwargs): pass
    monkeypatch.setattr(mineru_importer, 'get_vector_store', lambda: Store())
    result = mineru_importer.import_textbook_from_mineru_output(output, 'demo')
    assert result.used_mineru and result.indexed_chunks > 0
    assert result.chapters == mineru_importer.chapters_from_mineru_output(output, 'demo')
    assert 'bridge' not in mineru_importer.extract_text_from_mineru_output(output)
    assert result.canonical_book.parser_version == 'mineru-structured-content-v3'


def test_html_table_rows_and_sentence_title_are_preserved_as_body():
    p = payload()
    p['pages'][1]['blocks'].insert(0, dict(type='paragraph_title', content='某总线具有以下特点。', level=2))
    p['pages'][1]['blocks'].insert(1, dict(type='table', content='<table><tr><th>量</th><th>值</th></tr><tr><td>x</td><td>1</td></tr></table>',
                                        footnotes=[dict(content='表脚注')]))
    book = MinerUAdapter.from_structured_content(p, book_name='demo')
    assert next(b for b in book.blocks if b.text == '某总线具有以下特点。').block_type == 'paragraph'
    table = next(b for b in book.blocks if '<table>' in b.text)
    assert table.table_header == ['量', '值'] and table.table_rows == [['x', '1']]
    assert table.text.endswith('表脚注')
    assert 'table_without_title' in {i.code for i in validate_canonical_book(book).issues}


def test_native_with_a_different_legacy_book_is_rejected(tmp_path):
    output = source(tmp_path)
    (output / 'other').mkdir()
    (output / 'other/book_content_list.json').write_text(json.dumps([dict(type='text', text='另一教材')]))
    with pytest.raises(ValueError, match='different directories'):
        MinerUAdapter.from_output_dir(output, book_name='demo')


def test_blank_html_header_cells_survive_fingerprint_roundtrip(tmp_path):
    p = payload()
    table = next(b for b in p['pages'][1]['blocks'] if b['type'] == 'table')
    table['content'] = '<table><tr><th></th><th>量</th><th>值</th></tr><tr><td>A</td><td>x</td><td>1</td></tr></table>'
    book = MinerUAdapter.from_structured_content(p, book_name='blank-header')
    persist_canonical_book(book, progress_root=tmp_path)
    loaded = load_canonical_book(book.book_name, progress_root=tmp_path)
    assert next(b for b in loaded.blocks if b.block_type == 'table').table_header == ['', '量', '值']
    assert canonical_book_fingerprint(book) == canonical_book_fingerprint(loaded)


def test_two_different_flat_legacy_sources_are_ambiguous(tmp_path):
    for name, text in [('a_content_list.json', '甲教材正文'), ('b_content_list.json', '乙教材正文')]:
        (tmp_path / name).write_text(json.dumps([dict(type='text', text=text)]))
    with pytest.raises(ValueError, match='multiple preferred'):
        MinerUAdapter.from_output_dir(tmp_path, book_name='demo')
