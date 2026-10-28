from copy import deepcopy

import pytest

from ingestion.chapter_splitter import ChapterSplitter
from ingestion.document_ir import CanonicalBook, DocumentBlock
from ingestion.structure_quality import validate_index_structure


def fixture():
    blocks = [DocumentBlock('p', 'paragraph', '  中文😀与空格 a b。\n' * 70, ['第一章'], page_start=1, page_end=1),
              DocumentBlock('f', 'formula', '$$\\begin{matrix}' + 'x&y\\\\' * 130 + '\\end{matrix}$$',
                            ['第一章'], page_start=2, page_end=2),
              DocumentBlock('t', 'table', '表1 参数\n<table><tr><th>参数</th><th>值</th></tr>'
                  + ''.join(f'<tr><td>R{i}</td><td>{i}</td></tr>' for i in range(25))
                  + '</table>\n注：所有参数均为原文数据。', ['第一章'], page_start=3, page_end=3,
                  table_title='表1 参数', table_header=['参数', '值'], table_rows=[[f'R{i}', str(i)] for i in range(25)])]
    return CanonicalBook('范围测试', 'mineru', blocks, 'synthetic')


def test_exact_ranges_retain_unicode_whitespace_math_and_table_notes():
    book = fixture()
    before = deepcopy(book)
    chunks = ChapterSplitter(chunk_size=90, chunk_overlap=15).split_canonical_book(book)
    validate_index_structure(book, chunks)
    assert book == before
    assert len([c for c in chunks if c['block_type'] == 'formula']) == 1
    assert any('注：所有参数均为原文数据。' in c['content'] for c in chunks)
    assert all(len(c['source_block_ids']) == 1 for c in chunks)
    assert {c['page_start'] for c in chunks if c['block_type'] == 'paragraph'} == {1}


@pytest.mark.parametrize('corruption', ['body', 'span', 'hash', 'missing', 'extra', 'chapter'])
def test_membership_alone_never_proves_source_coverage(corruption):
    book = fixture()
    chunks = ChapterSplitter(chunk_size=90, chunk_overlap=15).split_canonical_book(book)
    if corruption == 'body':
        chunks[0]['content'] = '原文已被替换'
    elif corruption == 'span':
        chunks[0]['source_spans'][0]['source_start'] += 1
    elif corruption == 'hash':
        chunks[0]['source_spans'][0]['source_sha256'] = '0' * 64
    elif corruption == 'missing':
        chunks = [c for c in chunks if c['block_type'] != 'formula']
    elif corruption == 'extra':
        chunks[0]['content'] += '伪造的教材结论'
    else:
        chunks[0]['chapter'] = '另一章'
    with pytest.raises(RuntimeError, match='结构保真'):
        validate_index_structure(book, chunks)


def test_dropped_table_row_and_annotation_are_detected():
    book = fixture()
    chunks = ChapterSplitter(chunk_size=90, chunk_overlap=0).split_canonical_book(book)
    chunks = [c for c in chunks if 'R12' not in c['content']]
    with pytest.raises(RuntimeError, match='uncovered_source_span:t'):
        validate_index_structure(book, chunks)
