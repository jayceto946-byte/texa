import json

from langchain_core.documents import Document

from graph import retrieval_node
from graph.retrieval_node import _doc_to_item, _looks_like_toc_chunk
from graph.safe_retrieval import SafeKG
from ingestion.lexical_index import search_rows
from ingestion.vector_store import RetrievalOutcome


def _table_row(*, book_name="Book A", chapter="本章学习要点"):
    return {
        "chunk_id": "table-9-1",
        "book_name": book_name,
        "chapter": chapter,
        "section_title": chapter,
        "block_type": "table",
        "table_title": "表9-1",
        "table_header": ["字段", "数据"],
        "table_rows": [["x", "1"]],
        "content": "表9-1\n| 字段 | 数据 |\n|---|---|\n| x | 1 |",
        "provenance_schema": "texa.provenance/v1",
        "index_version": "index-v1",
        "canonical_hash": "a" * 64,
        "source_block_ids": ["block-table"],
        "source_locations": [{"block_id": "block-table", "page_start": 9}],
        "page_idx": 8,
        "source_kind": "mineru",
        "source_file": "book_content_list.json",
        "bbox": [1, 2, 3, 4],
        "role": "reference",
    }


def _table_document():
    row = _table_row()
    return Document(
        page_content=row["content"],
        metadata={
            **{key: value for key, value in row.items() if key not in {
                "content", "table_header", "table_rows", "source_block_ids",
                "source_locations", "bbox",
            }},
            "raw_content": row["content"],
            "table_header": json.dumps(row["table_header"], ensure_ascii=False),
            "table_rows": json.dumps(row["table_rows"], ensure_ascii=False),
            "source_block_ids": json.dumps(row["source_block_ids"], ensure_ascii=False),
            "source_locations": json.dumps(row["source_locations"], ensure_ascii=False),
            "bbox": json.dumps(row["bbox"]),
        },
    )


class _TableStore:
    def __init__(self, document=None):
        self.document = document
        self.chapter_calls = []
        self.all_calls = []

    def search_chapter(self, chapter, query, *, k, book_name):
        self.chapter_calls.append((book_name, chapter, query, k))
        return RetrievalOutcome(items=[self.document] if self.document else [])

    def search_all(self, query, **kwargs):
        self.all_calls.append((query, kwargs))
        return RetrievalOutcome(items={})


def _standalone_book(monkeypatch):
    monkeypatch.setattr(retrieval_node, "resolve_retrieval_resources", lambda *_args: [{
        "book_name": "Book A", "is_primary": True, "is_selected": True,
        "role": "core", "priority": 1.0,
    }])
    monkeypatch.setattr(retrieval_node, "get_safe_kg", lambda _book: (SafeKG(), ""))


def test_dense_projection_preserves_table_metadata_and_provenance():
    item = _doc_to_item(_table_document(), "本章学习要点", "vector")

    assert item["block_type"] == "table"
    assert item["table_title"] == "表9-1"
    assert item["table_header"] == ["字段", "数据"]
    assert item["table_rows"] == [["x", "1"]]
    assert item["provenance_schema"] == "texa.provenance/v1"
    assert item["canonical_hash"] == "a" * 64
    assert item["source_block_ids"] == ["block-table"]
    assert item["source_locations"][0]["block_id"] == "block-table"


def test_exact_table_title_is_a_direct_hit_and_captioned_table_is_not_toc():
    result = search_rows([_table_row()], "表 9－1 中列出了哪些字段或数据？", k=1)

    assert result[0]["is_direct_hit"] is True
    assert result[0]["is_table_direct_hit"] is True
    assert _looks_like_toc_chunk(result[0]) is False


def test_table_query_keeps_low_coverage_dense_bm25_hit_and_skips_list_anchor(monkeypatch):
    _standalone_book(monkeypatch)
    monkeypatch.setattr(
        retrieval_node,
        "_select_enumeration_anchor",
        lambda _items: (_ for _ in ()).throw(AssertionError("table query entered enumeration routing")),
    )
    store = _TableStore(_table_document())

    def lexical(book_name, _query, *, k, chapters):
        assert book_name == "Book A"
        assert chapters == ["本章学习要点"]
        row = _table_row()
        row.update({
            "source": "bm25", "retrieval_rank": 1, "bm25_score": 1.0,
            "is_direct_hit": False, "query_coverage": 0.01,
            "text": row["content"],
        })
        return [row]

    result = retrieval_node.retrieve_node(
        {
            "user_input": "表9-1中列出了哪些字段或数据？",
            "book_name": "Book A",
            "intent": "factual_recall",
            "target_chapters": ["本章学习要点"],
            "use_textbook_context": True,
        },
        vector_store=store,
        lexical_search=lexical,
        neighbor_expander=lambda *_args, **_kwargs: [],
    )

    debug = result["retrieval_debug_items"][0]
    evidence = result["evidence_items"][0]
    assert debug["chunk_id"] == evidence["chunk_id"] == "table-9-1"
    assert debug["fusion_sources"] == ["dense", "bm25"]
    assert debug["is_table_direct_hit"] is True
    assert debug["block_type"] == evidence["block_type"] == "table"
    assert evidence["table_title"] == "表9-1"
    assert evidence["table_header"] == ["字段", "数据"]
    assert evidence["table_rows"] == [["x", "1"]]
    assert evidence["source_block_ids"] == ["block-table"]
    assert all(call[0] == "Book A" for call in store.chapter_calls)


def test_target_chapter_search_excludes_other_chapters_from_first_pass():
    target = _table_row(chapter="目标章")
    target["content"] = "字段 数据"
    other = _table_row(book_name="Book A", chapter="其他章") | {
        "chunk_id": "other", "content": "表9-1 字段 数据 " * 20,
    }

    result = search_rows([other, target], "字段 数据", k=5, chapters=["目标章"])

    assert [item["chunk_id"] for item in result] == ["table-9-1"]


def test_same_book_fallback_occurs_only_after_empty_target_scope(monkeypatch):
    _standalone_book(monkeypatch)
    calls = []

    def lexical(book_name, _query, *, k, chapters):
        calls.append((book_name, chapters))
        if chapters:
            return []
        row = _table_row(chapter="其他章")
        row.update({
            "source": "bm25", "retrieval_rank": 1, "is_direct_hit": True,
            "text": row["content"],
        })
        return [row]

    result = retrieval_node.retrieve_node(
        {
            "user_input": "表9-1中列出了哪些字段或数据？",
            "book_name": "Book A",
            "intent": "factual_recall",
            "target_chapters": ["缺失章"],
            "use_textbook_context": True,
        },
        vector_store=_TableStore(),
        lexical_search=lexical,
        neighbor_expander=lambda *_args, **_kwargs: [],
    )

    assert calls == [("Book A", ["缺失章"]), ("Book A", None)]
    assert result["retrieval_debug_items"][0]["retrieval_scope"] == "same_book_fallback"
    assert result["retrieval_debug_items"][0]["book_name"] == "Book A"


def test_dense_target_hit_prevents_same_book_fallback(monkeypatch):
    _standalone_book(monkeypatch)
    calls = []

    def lexical(book_name, _query, *, k, chapters):
        calls.append((book_name, chapters))
        return []

    store = _TableStore(_table_document())
    result = retrieval_node.retrieve_node(
        {
            "user_input": "表9-1中列出了哪些字段或数据？",
            "book_name": "Book A",
            "intent": "factual_recall",
            "target_chapters": ["本章学习要点"],
            "use_textbook_context": True,
        },
        vector_store=store,
        lexical_search=lexical,
        neighbor_expander=lambda *_args, **_kwargs: [],
    )

    assert calls == [("Book A", ["本章学习要点"])]
    assert store.all_calls == []
    assert result["retrieval_debug_items"][0]["retrieval_scope"] == "target_chapters"
    assert result["retrieval_debug_items"][0]["book_name"] == "Book A"


def test_same_named_chapter_and_table_do_not_cross_books(monkeypatch):
    monkeypatch.setattr(retrieval_node, "resolve_retrieval_resources", lambda *_args: [
        {
            "book_name": "Book A", "is_primary": True, "is_selected": True,
            "role": "core", "priority": 1.0,
        },
        {
            "book_name": "Book B", "is_primary": False, "is_selected": False,
            "role": "reference", "priority": 1.0,
        },
    ])
    monkeypatch.setattr(retrieval_node, "get_safe_kg", lambda _book: (SafeKG(), ""))
    calls = []

    def lexical(book_name, _query, *, k, chapters):
        calls.append((book_name, chapters))
        row = _table_row(book_name=book_name)
        row.update({"source": "bm25", "retrieval_rank": 1, "text": row["content"]})
        return [row]

    result = retrieval_node.retrieve_node(
        {
            "user_input": "表9-1中列出了哪些字段或数据？",
            "book_name": "Book A",
            "intent": "factual_recall",
            "target_chapters": ["本章学习要点"],
            "use_textbook_context": True,
        },
        vector_store=_TableStore(_table_document()),
        lexical_search=lexical,
        neighbor_expander=lambda *_args, **_kwargs: [],
    )

    assert calls == [("Book A", ["本章学习要点"])]
    assert {item["book_name"] for item in result["retrieval_debug_items"]} == {"Book A"}


def test_source_grounded_table_reference_promotes_its_adjacent_table(monkeypatch):
    _standalone_book(monkeypatch)
    context = {
        "chunk_id": "table-context",
        "book_name": "Book A",
        "chapter": "本章学习要点",
        "section_title": "本章学习要点",
        "block_type": "paragraph",
        "content": "（3）以 a22 为主元构造初始单纯形表",
        "text": "（3）以 a22 为主元构造初始单纯形表",
        "chunk_index": 10,
        "source": "bm25",
        "retrieval_rank": 1,
    }
    table = _table_row()
    table.update({"text": table["content"], "source": "neighbor", "chunk_index": 11})

    result = retrieval_node.retrieve_node(
        {
            "user_input": "（3）以 a22 为主元构造初始单纯形表的内容有哪些？",
            "book_name": "Book A",
            "intent": "factual_recall",
            "target_chapters": ["本章学习要点"],
            "use_textbook_context": True,
        },
        vector_store=_TableStore(),
        lexical_search=lambda *_args, **_kwargs: [dict(context)],
        neighbor_expander=lambda *_args, **_kwargs: [dict(context, source="neighbor"), dict(table)],
    )

    table_debug = next(item for item in result["retrieval_debug_items"] if item["chunk_id"] == "table-9-1")
    assert table_debug["rank"] == 1
    assert table_debug["is_table_neighbor"] is True
    assert table_debug["table_anchor_chunk_id"] == "table-context"
    assert any(item["chunk_id"] == "table-9-1" for item in result["evidence_items"])
