import pytest
from langchain_core.documents import Document

from graph.evidence_pack import build_evidence_pack
from graph.retrieval_node import _doc_to_item
from ingestion.chapter_splitter import ChapterSplitter
from ingestion.document_ir import (
    CanonicalBook,
    DocumentBlock,
    PROVENANCE_SCHEMA_VERSION,
    chunk_provenance_errors,
)
from ingestion.index_pipeline import _metadata, build_and_activate_book_index
from ingestion.lexical_index import expand_neighbors_rows, search_rows


def _book() -> CanonicalBook:
    return CanonicalBook(
        book_name="provenance-book",
        source_kind="mineru",
        parser_version="test-v1",
        blocks=[
            DocumentBlock(
                block_id="block-text",
                block_type="paragraph",
                text="灵敏度表示输出变化量与输入变化量之比。",
                section_path=["第一章", "灵敏度"],
                page_start=3,
                page_end=3,
                bbox=[10, 20, 100, 60],
                source_file="content_list.json",
                source_kind="mineru",
                attributes={
                    "bbox_space": "page",
                    "bbox_format": "xyxy",
                    "bbox_units": "mineru_source_units",
                },
            ),
            DocumentBlock(
                block_id="figure-1",
                block_type="figure",
                text="图 1 测量系统结构",
                section_path=["第一章", "灵敏度"],
                page_start=3,
                page_end=3,
                bbox=[110, 20, 300, 180],
                source_file="content_list.json",
                source_kind="mineru",
                attributes={
                    "figure_id": "figure-1",
                    "bbox_space": "page",
                    "bbox_format": "xyxy",
                    "bbox_units": "mineru_source_units",
                },
            ),
        ],
    )


def test_canonical_splitter_emits_minimum_stable_provenance():
    rows = ChapterSplitter().split_canonical_book(_book())

    assert len(rows) == 2
    assert all(chunk_provenance_errors(row) == [] for row in rows)
    text_row, figure_row = rows
    assert text_row["source_block_ids"] == ["block-text"]
    assert text_row["source_locations"][0] == {
        "block_id": "block-text",
        "source_kind": "mineru",
        "source_file": "content_list.json",
        "page_start": 3,
        "page_end": 3,
        "bbox": [10, 20, 100, 60],
        "bbox_space": "page",
        "bbox_format": "xyxy",
        "bbox_units": "mineru_source_units",
    }
    assert figure_row["figure_id"] == "figure-1"
    assert figure_row["retrieval_excluded"] is True


def test_figure_catalog_row_is_not_searchable_or_neighbor_evidence():
    rows = ChapterSplitter().split_canonical_book(_book())

    assert search_rows(rows, "测量系统结构", k=5) == []
    expanded = expand_neighbors_rows(rows, [rows[0]["chunk_id"]], window=1)
    assert [row["chunk_id"] for row in expanded] == [rows[0]["chunk_id"]]


def test_vector_metadata_and_retrieval_item_preserve_provenance():
    row = ChapterSplitter().split_canonical_book(_book())[0]
    row["index_version"] = "index-v1"
    metadata = _metadata(row, "provenance-book", "第一章")
    item = _doc_to_item(
        Document(page_content=row["content"], metadata=metadata),
        "第一章",
        "vector",
    )

    assert item["provenance_schema"] == PROVENANCE_SCHEMA_VERSION
    assert item["index_version"] == "index-v1"
    assert item["source_block_ids"] == ["block-text"]
    assert item["source_locations"][0]["bbox"] == [10, 20, 100, 60]
    assert item["bbox"] == [10.0, 20.0, 100.0, 60.0]


def test_evidence_pack_keeps_provenance_and_rejects_text_only_fallback():
    row = ChapterSplitter().split_canonical_book(_book())[0]
    row.update({"index_version": "index-v1", "text": row["content"]})
    pack = build_evidence_pack([row], {"第一章": ["ignored projection"]})

    assert pack["items"][0]["chunk_id"] == row["chunk_id"]
    assert pack["items"][0]["source_block_ids"] == ["block-text"]
    assert pack["items"][0]["source_locations"][0]["page_start"] == 3
    assert build_evidence_pack([], {"第一章": ["legacy text without chunk id"]})["items"] == []


def test_index_activation_fails_fast_on_missing_provenance():
    chunk = {"chunk_id": "legacy", "chapter": "第一章", "content": "legacy text"}

    with pytest.raises(ValueError, match="chunk provenance contract failed"):
        build_and_activate_book_index(object(), "book", [("第一章", [chunk])], [chunk])
