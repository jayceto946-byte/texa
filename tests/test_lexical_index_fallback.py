import json

import ingestion.lexical_index as lexical


def test_missing_persisted_index_searches_imported_source_chunks(monkeypatch, tmp_path):
    progress = tmp_path / "progress"
    vector_db = tmp_path / "vector"
    book_name = "\u8bef\u5dee\u7406\u8bba\u4e0e\u6570\u636e\u5904\u7406"
    source_dir = progress / book_name / "hybrid"
    source_dir.mkdir(parents=True)
    source_path = source_dir / f"{book_name}_middle_chunks.json"
    source_path.write_text(
        json.dumps(
            [
                {
                    "chunk_id": "rounding",
                    "section_title": "\u4e8c\u3001\u6570\u5b57\u820d\u5165\u89c4\u5219",
                    "role": "definition",
                    "content": (
                        "\u820d\u53bb\u90e8\u5206\u5927\u4e8e\u672b\u4f4d\u7684\u534a\u4e2a\u5355\u4f4d\u65f6\u672b\u4f4d\u52a01\uff1b"
                        "\u5c0f\u4e8e\u534a\u4e2a\u5355\u4f4d\u65f6\u672b\u4f4d\u4e0d\u53d8\uff1b"
                        "\u7b49\u4e8e\u534a\u4e2a\u5355\u4f4d\u65f6\u672b\u4f4d\u51d1\u6210\u5076\u6570\u3002"
                    ),
                },
                {
                    "chunk_id": "other",
                    "section_title": "\u8bef\u5dee\u5b9a\u4e49",
                    "role": "definition",
                    "content": "\u8bef\u5dee\u662f\u6d4b\u5f97\u503c\u4e0e\u771f\u503c\u4e4b\u5dee\u3002",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(lexical, "PROGRESS_PATH", progress)
    monkeypatch.setattr(lexical, "VECTOR_DB_PATH", vector_db)
    monkeypatch.setattr(lexical, "_cache", {})

    assert not lexical.index_path(book_name).exists()
    hits = lexical.search_book(book_name, "\u8bef\u5dee\u8ba1\u7b97\u7ed3\u679c\u600e\u4e48\u820d\u5165", k=2)

    assert hits
    rounding = next(item for item in hits if item["chunk_id"] == "rounding")
    assert rounding["source"] == "bm25"
    assert rounding["chapter"] == "\u4e8c\u3001\u6570\u5b57\u820d\u5165\u89c4\u5219"
    assert rounding["is_direct_hit"] is True
    assert not lexical.index_path(book_name).exists()


def test_vector_health_accepts_lexical_only_retrieval(monkeypatch):
    import ingestion.vector_store as vector_store

    class EmptyClient:
        def list_collections(self):
            return []

    store = vector_store.ChapterVectorStore.__new__(vector_store.ChapterVectorStore)
    store._client = EmptyClient()
    store._map = {}
    monkeypatch.setattr(lexical, "load_book_index", lambda book_name: [{"chunk_id": "source"}])

    stats = store.get_book_index_stats("source-only-book")

    assert stats["collection_count"] == 0
    assert stats["lexical_chunk_count"] == 1
    assert stats["healthy"] is True
