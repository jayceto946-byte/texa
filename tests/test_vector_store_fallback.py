from types import SimpleNamespace

from langchain_core.documents import Document

from ingestion.vector_store import ChapterVectorStore, MAX_CHAPTER_FANOUT


class _Embeddings:
    def embed_query(self, _query):
        return [0.1, 0.2]


class _Client:
    def __init__(self, names):
        self.collections = [SimpleNamespace(name=name) for name in names]

    def list_collections(self):
        return self.collections


class _Store:
    def __init__(self, chapter, *, broken=False):
        self.chapter = chapter
        self.broken = broken
        self.calls = 0

    def similarity_search_by_vector_with_relevance_scores(self, _query, **_kwargs):
        self.calls += 1
        if self.broken:
            raise RuntimeError("broken hnsw")
        return [(Document(page_content=self.chapter, metadata={"chapter": self.chapter}), 0.1)]

    def similarity_search_by_vector(self, _query, **_kwargs):
        self.calls += 1
        if self.broken:
            raise RuntimeError("broken hnsw")
        return [Document(page_content=self.chapter, metadata={"chapter": self.chapter})]


def _store(chapter_count=20, *, aggregate=False, broken_aggregate=False):
    store = ChapterVectorStore.__new__(ChapterVectorStore)
    store.available = True
    store.embeddings = _Embeddings()
    store.db_path = "."
    store._broken_aggregates = set()
    names = [f"c{index}" for index in range(chapter_count)]
    store._map = {
        name: {"chapter": f"chapter-{index}", "book_name": "book", "kind": "chapter"}
        for index, name in enumerate(names)
    }
    if aggregate:
        names.append("book-aggregate")
        store._map["book-aggregate"] = {
            "chapter": "book (aggregate)", "book_name": "book", "kind": "book_aggregate",
        }
    store._client = _Client(names)
    store._stores = {
        store._store_key(entry["chapter"], "book"): _Store(
            entry["chapter"], broken=broken_aggregate and entry.get("kind") == "book_aggregate"
        )
        for entry in store._map.values()
    }
    return store


def test_search_all_limits_fallback_to_bm25_shortlist():
    store = _store()

    result = store.search_all(
        "query", book_name="book", fallback_chapters=["chapter-7", "chapter-3"], k=1, top_n=2,
    )

    assert result.status == "ok"
    assert list(result.items) == ["chapter-7", "chapter-3"]
    called = {
        chapter for chapter, backend in (
            (entry["chapter"], store._stores[store._store_key(entry["chapter"], "book")])
            for entry in store._map.values()
        ) if backend.calls
    }
    assert called == {"chapter-7", "chapter-3"}


def test_search_all_distinguishes_healthy_empty_index():
    store = _store(chapter_count=0)

    outcome = store.search_all("query", book_name="book")

    assert outcome.status == "ok"
    assert outcome.empty is True
    assert outcome.items == {}
    assert outcome.failures == []


def test_search_all_reports_all_collection_failures():
    store = _store(chapter_count=2)
    for backend in store._stores.values():
        backend.broken = True

    outcome = store.search_all(
        "query",
        book_name="book",
        fallback_chapters=["chapter-0", "chapter-1"],
    )

    assert outcome.status == "failed"
    assert outcome.empty is False
    assert {failure.scope for failure in outcome.failures} == {"c0", "c1"}
    assert {failure.error_code for failure in outcome.failures} == {"chapter_query_failed"}


def test_search_all_blocks_unbounded_fanout_without_shortlist():
    store = _store(chapter_count=MAX_CHAPTER_FANOUT + 1)

    outcome = store.search_all("query", book_name="book")
    assert outcome.status == "failed"
    assert outcome.failures[0].error_code == "chapter_fanout_blocked"
    assert all(backend.calls == 0 for backend in store._stores.values())


def test_broken_aggregate_is_quarantined_and_uses_shortlist():
    store = _store(aggregate=True, broken_aggregate=True)
    aggregate = store._stores[store._store_key("book (aggregate)", "book")]

    first = store.search_all("query", book_name="book", fallback_chapters=["chapter-2"], k=1, top_n=1)
    first_calls = aggregate.calls
    second = store.search_all("query", book_name="book", fallback_chapters=["chapter-2"], k=1, top_n=1)

    assert first.status == "partial"
    assert second.status == "partial"
    assert list(first.items) == ["chapter-2"]
    assert list(second.items) == ["chapter-2"]
    assert "book-aggregate" in store._broken_aggregates
    assert aggregate.calls == first_calls
