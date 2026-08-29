import pytest
from chromadb.errors import NotFoundError

import ingestion.vector_store as vector_store


def test_get_chapter_store_does_not_create_missing_collection(monkeypatch, tmp_path):
    class MissingCollectionClient:
        def get_collection(self, name):
            raise NotFoundError(f"missing collection: {name}")

    created = []
    monkeypatch.setattr(vector_store, "Chroma", lambda **kwargs: created.append(kwargs))

    store = vector_store.ChapterVectorStore.__new__(vector_store.ChapterVectorStore)
    store.available = True
    store.embeddings = object()
    store.db_path = tmp_path
    store._stores = {}
    store._map = {}
    store._client = MissingCollectionClient()

    assert store.get_chapter_store("unknown subsection", book_name="sensor-book") is None
    assert created == []
    assert store._stores == {}


def test_get_chapter_store_does_not_treat_internal_error_as_a_miss(tmp_path):
    class BrokenClient:
        def get_collection(self, name):
            raise OSError(f"database unreadable: {name}")

    store = vector_store.ChapterVectorStore.__new__(vector_store.ChapterVectorStore)
    store.available = True
    store.embeddings = object()
    store.db_path = tmp_path
    store._stores = {}
    store._map = {}
    store._client = BrokenClient()

    with pytest.raises(RuntimeError, match="failed to open chapter collection"):
        store.get_chapter_store("broken chapter", book_name="sensor-book")
