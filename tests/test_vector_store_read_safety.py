import sys
import types

import ingestion.vector_store as vector_store


def test_get_chapter_store_does_not_create_missing_collection(monkeypatch, tmp_path):
    class MissingCollectionClient:
        def get_collection(self, name):
            raise RuntimeError(f"missing collection: {name}")

    fake_chromadb = types.SimpleNamespace(PersistentClient=lambda path: MissingCollectionClient())
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)

    created = []
    monkeypatch.setattr(vector_store, "Chroma", lambda **kwargs: created.append(kwargs))

    store = vector_store.ChapterVectorStore.__new__(vector_store.ChapterVectorStore)
    store.available = True
    store.embeddings = object()
    store.db_path = tmp_path
    store._stores = {}
    store._map = {}

    assert store.get_chapter_store("unknown subsection", book_name="sensor-book") is None
    assert created == []
    assert store._stores == {}
