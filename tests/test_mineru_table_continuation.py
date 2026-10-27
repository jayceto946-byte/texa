"""Synthetic table fragments covering provenance and unchanged release gates."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from ingestion.acceptance_probes import generate_acceptance_probes
from ingestion.chapter_splitter import ChapterSplitter
from ingestion.document_adapters import MinerUAdapter
from ingestion.document_ir import canonical_book_fingerprint, load_canonical_book, persist_canonical_book


FIXTURE = Path(__file__).parent / "fixtures/mineru/table_continuation.synthetic.json"


def synthetic_payload():
    source = json.loads(FIXTURE.read_text())
    return deepcopy(source["payload"]), source["book_name"]


def synthetic_book(payload=None):
    original, name = synthetic_payload()
    return MinerUAdapter.from_structured_content(payload or original, book_name=name)


def test_table_probe_identity_is_deterministic():
    first = generate_acceptance_probes(synthetic_book())
    second = generate_acceptance_probes(synthetic_book())
    assert first == second
    assert len({case["id"] for case in first["cases"]}) == 2


def test_native_continuation_keeps_raw_caption_source_coordinates_and_cell_images(tmp_path):
    payload, name = synthetic_payload()
    before = deepcopy(payload)
    book = synthetic_book(payload)
    first, continuation = book.blocks
    assert payload == before
    assert continuation.table_title == "(续)"
    assert continuation.attributes["source_continues_prev"] is True
    assert continuation.attributes["table_continuation_of"] == first.block_id
    assert continuation.attributes["table_title_source_block_id"] == first.block_id
    assert continuation.retrieval_table_title == "表 2-3 合成元件类型及参数 (续)"
    assert first.table_header == continuation.table_header == ["类型", "曲线图", "长度/μm", "宽度/μm", "标定值"]
    assert [len(r) for r in first.table_rows + continuation.table_rows] == [5, 5, 5, 5]
    assert first.table_rows[0][2:] == ["11~17", "31~43", "1.7"]
    assert continuation.table_rows[-1] == ["示例丁", '<img src="images/sample_d.png"/>', "41~47", "91~103", "4.7"]
    for table, expected in zip(book.blocks, [before["pages"][1]["blocks"][2], before["pages"][2]["blocks"][1]]):
        assert table.bbox == expected["bbox"]
        assert table.attributes["source_markdown"] == expected["content"]
        assert table.attributes["captions"] == [c["content"] for c in expected["captions"]]
        assert table.attributes["original_visual_asset"]["source_relpath"] == expected["image_source"]
    assert [(b.page_start, b.attributes["source_page_index"], b.attributes["source_block_index"]) for b in book.blocks] == [(2, 1, 2), (3, 2, 1)]
    persist_canonical_book(book, progress_root=tmp_path)
    loaded = load_canonical_book(name, progress_root=tmp_path)
    assert canonical_book_fingerprint(loaded) == canonical_book_fingerprint(book)
    assert loaded.blocks[1].attributes["table_continuation_of"] == first.block_id
    without_relation = deepcopy(payload)
    without_relation["pages"][2]["blocks"][1].pop("continues_prev")
    assert [b.block_id for b in synthetic_book(without_relation).blocks] == [b.block_id for b in book.blocks]


def test_row_splitting_keeps_every_image_value_header_and_individual_page():
    book = synthetic_book()
    chunks = ChapterSplitter(chunk_size=200, chunk_overlap=0).split_canonical_book(book)
    rows = [c for c in chunks if c["block_type"] == "table"]
    assert len(rows) == 4
    for block in book.blocks:
        fragments = [c for c in rows if c["source_block_ids"] == [block.block_id]]
        assert [r for c in fragments for r in c["table_rows"]] == block.table_rows
        for fragment in fragments:
            assert fragment["table_header"] == block.table_header
            assert fragment["table_title"] == block.retrieval_table_title
            assert fragment["page_start"] == fragment["page_end"] == block.page_start
            assert fragment["source_locations"][0]["bbox"] == block.bbox
            assert "长度/μm" in fragment["content"]
            for row in fragment["table_rows"]:
                assert all(cell in fragment["content"] for cell in row)


@pytest.mark.parametrize("mutation", ["no_flag", "string_flag", "page_gap", "header_mismatch", "own_title", "chapter_change"])
def test_continuation_is_not_inferred_across_ambiguous_or_unrelated_tables(mutation):
    payload, _ = synthetic_payload()
    last = payload["pages"][2]["blocks"][1]
    if mutation == "no_flag":
        last.pop("continues_prev")
    elif mutation == "string_flag":
        last["continues_prev"] = "true"
    elif mutation == "page_gap":
        payload["pages"][2]["page_idx"] = 3
    elif mutation == "header_mismatch":
        last["content"] = last["content"].replace("标定值", "不同字段")
    elif mutation == "own_title":
        last["captions"][0]["content"] = "表 2-4 另一张合成表"
    elif mutation == "chapter_change":
        payload["pages"][2]["blocks"][0] = dict(type="paragraph_title", content="第3章 合成章节")
    table = next(b for b in reversed(synthetic_book(payload).blocks) if b.block_type == "table")
    assert not table.attributes.get("table_continuation_of")


def test_three_page_chain_uses_one_root_title_without_concatenating_bodies():
    payload, _ = synthetic_payload()
    last = deepcopy(payload['pages'][2]['blocks'][1])
    last['captions'][0]['content'] = '（续）'
    payload['pages'].append(dict(page_idx=3, blocks=[last]))
    first, second, third = synthetic_book(payload).blocks
    assert third.attributes['table_continuation_of'] == second.block_id
    assert third.attributes['table_title_source_block_id'] == first.block_id
    assert third.retrieval_table_title == '表 2-3 合成元件类型及参数 （续）'
    assert third.table_rows == second.table_rows
    assert '示例甲' not in third.text


def test_image_only_row_survives_html_projection():
    payload, _ = synthetic_payload()
    payload['pages'][1]['blocks'][2]['content'] = '<table><tr><td>图形</td><td>曲线</td></tr><tr><td><img src="images/a.jpg"/></td><td><img src="images/b.jpg"/></td></tr></table>'
    table = synthetic_book(payload).blocks[0]
    assert table.table_rows == [['<img src="images/a.jpg"/>', '<img src="images/b.jpg"/>']]


def test_synthetic_fragments_pass_original_production_lexical_gate(monkeypatch):
    from graph import retrieval_node
    from graph.safe_retrieval import SafeKG
    from ingestion.index_pipeline import _validate_staged_production_retrieval, RELEASE_MIN_RECALL, RELEASE_MIN_POINT_RECALL
    from ingestion.vector_store import RetrievalOutcome

    book = synthetic_book()
    probes = generate_acceptance_probes(book)
    cases = [c for c in probes["cases"] if c["specialty"] == "table"]
    assert len(cases) == 2
    continuation = next(c for c in cases if c["provenance"]["page_start"] == 3)
    assert continuation["question"] == "表 2-3 合成元件类型及参数 (续)中列出了哪些字段或数据？"
    # Keep all six continuation anchors; no point or case is skipped.
    assert continuation["required_points"] == ["(续)", "类型", "曲线图", "长度/μm", "宽度/μm", "标定值"]
    assert continuation['provenance']['source_block_ids'] == [book.blocks[0].block_id, book.blocks[1].block_id]
    assert RELEASE_MIN_RECALL == RELEASE_MIN_POINT_RECALL == 1.0
    class LexicalStore:
        _map = {}
        _stores = {}
        _broken_aggregates = set()
        def search_chapter(self, *args, **kwargs): return RetrievalOutcome(items=[])
        def search_all(self, *args, **kwargs): return RetrievalOutcome(items={})
    monkeypatch.setattr(retrieval_node, "get_safe_kg", lambda _: (SafeKG(), ""))
    monkeypatch.setattr(retrieval_node, "_load_history", lambda *_: [])
    monkeypatch.setattr(retrieval_node, "cross_encoder_scores", lambda *_: None)
    chunks = ChapterSplitter().split_canonical_book(book)
    summary = _validate_staged_production_retrieval(LexicalStore(), book.book_name,
        {"isolated": dict(book_name=book.book_name, kind="book_aggregate")}, chunks,
        acceptance_probes=cases, specialty_inventory=probes["source_inventory"])
    assert summary["recall_at_k"] == summary["point_recall"] == 1.0
    assert summary["specialty_gates"]["table"]["passed"]
