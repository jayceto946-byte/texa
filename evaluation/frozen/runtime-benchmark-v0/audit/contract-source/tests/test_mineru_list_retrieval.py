"""Isolated list regressions; all retrieval runs against offline synthetic rows."""
import pytest
from graph import retrieval_node as retrieval
from graph.evidence_pack import build_evidence_pack
from graph.safe_retrieval import SafeKG
from ingestion.vector_store import RetrievalOutcome


def row(key, index, text, section='1.1 特点', book='demo', chapter='第一章', **extra):
    return dict(chunk_id=key, chunk_index=index, text=text, content=text,
                section_title=section, section_path=[chapter, section], chapter=chapter,
                book_name=book, block_type='paragraph', source='bm25', retrieval_rank=1,
                bm25_score=2, query_coverage=.8, **extra)


def test_same_section_precedes_nearby_siblings():
    anchor = row('a', 10, '测量模块的特点主要有以下几项。')
    good = [row('g1', 18, '（1）结构简单。'), row('g2', 19, '（2）温度稳定。')]
    bad = [row(f'b{i}', 11+i, f'（{i+1}）相邻节内容。', section='1.2 其他') for i in range(7)]
    assert [r['chunk_id'] for r in retrieval._list_group_neighbors(anchor, [anchor, *bad, *good])] == ['a', 'g1', 'g2']


def test_fallback_rejects_previous_other_parent_other_chapter():
    anchor = row('a', 10, '测量模块的特点主要有以下几项。')
    good = row('g', 11, '（1）结构简单。', section='1.2 特点')
    bad = [row('prev', 9, '（1）前一列表。'), row('chapter', 12, '（1）另一章。', chapter='第二章'),
           dict(row('parent', 13, '（1）另一父路径。', section='其他条目'), section_path=['第一章', '其他', '条目']),
           dict(row('formula', 14, '（1）x=1'), block_type='formula')]
    assert [r['chunk_id'] for r in retrieval._list_group_neighbors(anchor, [anchor, good, *bad])] == ['a', 'g']


class Store:
    def search_all(self, *_args, **_kwargs):
        return RetrievalOutcome(items={})
    def search_chapter(self, *_args, **_kwargs):
        return RetrievalOutcome(items=[])


def run(monkeypatch, anchor, neighbors, query):
    monkeypatch.setattr(retrieval, 'get_safe_kg', lambda _book: (SafeKG(), ''))
    monkeypatch.setattr(retrieval, '_load_history', lambda *_args: [])
    result = retrieval.retrieve_node(
        dict(user_input=query, book_name='demo', intent='factual_recall', use_textbook_context=True),
        vector_store=Store(), lexical_search=lambda *_args, **_kwargs: [dict(anchor)],
        neighbor_expander=lambda *_args, **_kwargs: [dict(r) for r in neighbors],
        index_stats_override={'demo': {'healthy': True}},
        retrieval_resources_override=[dict(book_name='demo', is_primary=True, is_selected=True, role='core', priority=1)],
    )
    return result, build_evidence_pack(result['evidence_items'], intent='factual_recall')


def test_pollution_cannot_consume_final_pack_quota(monkeypatch):
    a = row('a', 10, '测量模块的特点主要有以下几项。')
    good = [row(f'g{i}', 20+i, f'（{i+1}）模块特点：目标性能{i}。') for i in range(4)]
    bad = [row(f'b{i}', 11+i, f'（{i+1}）相邻污染{i}。', section='1.2 无关') for i in range(7)]
    result, pack = run(monkeypatch, a, [a, *bad, *good], '测量模块的特点有哪些？')
    assert result['evidence_support']['status'] in {'supported', 'partial'}
    assert {r['chunk_id'] for r in pack['items']} >= {'a', *(r['chunk_id'] for r in good)}
    assert '污染' not in pack['text']


def test_literals_apply_to_assembled_list_including_order_zero(monkeypatch):
    a = row('a', 10, '测量模块的特点主要有以下几项。')
    members = [row('g1', 11, '（1）结构简单。'), row('g2', 12, '（2）型号 DEMO-X1 支持温度补偿。')]
    result, pack = run(monkeypatch, a, [a, *members], 'DEMO-X1 测量模块的特点有哪些？')
    assert {r['chunk_id'] for r in pack['items']} == {'a', 'g1', 'g2'}
    assert result['evidence_items'][0]['list_group_order'] == 0


@pytest.mark.parametrize('query', ['WRONG-X9 测量模块的特点有哪些？'])
def test_wrong_model_cannot_release_list(monkeypatch, query):
    a = row('a', 10, '测量模块的特点主要有以下几项。')
    _, pack = run(monkeypatch, a, [a, row('g', 11, '（1）型号 DEMO-X1 结构简单。')], query)
    assert not pack['items']


def test_plain_literal_gate_still_rejects_missing_model(monkeypatch):
    a = row('a', 10, '测量模块结构简单。')
    _, pack = run(monkeypatch, a, [], 'DEMO-X1 测量模块是什么？')
    assert not pack['items']


def test_other_book_same_section_cannot_join_list():
    a = row('a', 10, '测量模块主要有以下特点。')
    bad = row('b', 11, '（1）另一书的特点。', book='other')
    good = row('g', 12, '（1）本书特点。')
    assert [r['chunk_id'] for r in retrieval._list_group_neighbors(a, [a,bad,good])] == ['a','g']


def test_untrusted_list_marker_cannot_bypass_literal_gate(monkeypatch):
    a = row('a', 10, '测量模块结构简单。', list_group_order=0, list_group_part='header')
    fake = row('f', 11, '（1）测量模块使用其他型号。', list_group_order=1, list_group_part='member')
    _, pack = run(monkeypatch, a, [fake], 'DEMO-X1 测量模块是什么？')
    assert not pack['items']


def test_wrong_section_model_cannot_authorize_a_list(monkeypatch):
    a = row('a', 10, '测量模块主要有以下特点。')
    good = row('g', 11, '（1）结构简单。')
    wrong = row('wrong', 12, '（1）DEMO-X1 无关设备。', section='1.2 另一列表')
    _, pack = run(monkeypatch, a, [a,good,wrong], 'DEMO-X1 测量模块的特点有哪些？')
    assert not pack['items']


def real_rows():
    import json
    from pathlib import Path
    rows = json.loads((Path(__file__).parent / 'fixtures/mineru4/list_failures.json').read_text())
    return [dict(r, text=r['content'], source='bm25', retrieval_rank=1,
                 bm25_score=2, query_coverage=.8, book_name='demo',
                 title_match_quality=1.0, enumeration_match_quality=.5) for r in rows]


def test_frozen_mac_fragment_keeps_target_member_in_final_pack(monkeypatch):
    rows = [r for r in real_rows() if r['chunk_index'] >= 2445]
    anchor = next(r for r in rows if r['chunk_index'] == 2453)
    result, pack = run(monkeypatch, anchor, rows, '无线传感器网络有哪些关键技术？')
    assert result['evidence_support']['status'] in {'supported','partial'}
    assert 'MAC 协议' in pack['text']
    assert all(item['section_title'] == anchor['section_title'] for item in pack['items'])


def test_frozen_humirel_fragment_retains_both_members(monkeypatch):
    rows = [r for r in real_rows() if r['chunk_index'] < 2445]
    anchor = next(r for r in rows if r['chunk_index'] == 1848)
    _, pack = run(monkeypatch, anchor, rows, 'NK-Humirel 高分子电容式湿度传感器包括哪些内容？')
    assert '感湿电容及其特性' in pack['text']
    assert 'NK-Humirel' in pack['text']


def test_model_in_other_book_same_section_cannot_authorize_final_pack(monkeypatch):
    a = row('a', 10, '测量模块主要有以下特点。')
    good = row('g', 11, '（1）结构简单。')
    wrong = row('wrong', 12, '（1）DEMO-X1 无关设备。', book='other')
    _, pack = run(monkeypatch, a, [a,good,wrong], 'DEMO-X1 测量模块的特点有哪些？')
    assert not pack['items']
