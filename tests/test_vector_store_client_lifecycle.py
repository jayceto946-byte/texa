from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time

import chromadb

import ingestion.vector_store as vector_store_module
from ingestion.vector_store import ChapterVectorStore


def test_get_vector_store_initializes_singleton_once_under_concurrency(monkeypatch):
    calls = 0
    calls_lock = threading.Lock()

    class FakeStore:
        def __init__(self):
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.03)

    monkeypatch.setattr(vector_store_module, "_chapter_vs_instance", None)
    monkeypatch.setattr(vector_store_module, "ChapterVectorStore", FakeStore)

    with ThreadPoolExecutor(max_workers=8) as executor:
        stores = list(executor.map(lambda _: vector_store_module.get_vector_store(), range(16)))

    assert calls == 1
    assert all(store is stores[0] for store in stores)


def test_get_vector_store_retries_after_constructor_failure(monkeypatch):
    attempts = 0
    recovered = object()

    def create_store():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary Chroma initialization failure")
        return recovered

    monkeypatch.setattr(vector_store_module, "_chapter_vs_instance", None)
    monkeypatch.setattr(vector_store_module, "ChapterVectorStore", create_store)

    try:
        vector_store_module.get_vector_store()
    except RuntimeError:
        pass
    else:
        raise AssertionError("first initialization should fail")

    assert vector_store_module.get_vector_store() is recovered
    assert attempts == 2


class _Collection:
    name = "chapter-collection"

    def count(self):
        raise AssertionError("health check opened an HNSW segment")


class _Client:
    def __init__(self):
        self.requested = []

    def list_collections(self):
        return [_Collection()]

    def get_collection(self, name):
        self.requested.append(name)
        return _Collection()


def _store(tmp_path: Path) -> ChapterVectorStore:
    store = ChapterVectorStore.__new__(ChapterVectorStore)
    store.available = True
    store.db_path = tmp_path
    store.embeddings = object()
    store._stores = {}
    store._client = _Client()
    store._map = {
        "chapter-collection": {
            "chapter": "chapter",
            "book_name": "book",
            "schema_version": "2",
            "kind": "chapter",
        }
    }
    return store


def test_health_check_reuses_owned_chroma_client(monkeypatch, tmp_path):
    store = _store(tmp_path)
    monkeypatch.setattr("ingestion.lexical_index.load_book_index", lambda book_name: [{}, {}])
    monkeypatch.setattr(
        chromadb,
        "PersistentClient",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("created a temporary client")),
    )

    stats = store.get_book_index_stats("book")

    assert stats["collection_count"] == 1
    assert stats["chunk_count"] == 2
    assert stats["healthy"] is True


def test_chapter_lookup_reuses_owned_chroma_client(monkeypatch, tmp_path):
    store = _store(tmp_path)
    monkeypatch.setattr(
        chromadb,
        "PersistentClient",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("created a temporary client")),
    )

    class FakeChroma:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(vector_store_module, "Chroma", FakeChroma)

    result = store.get_chapter_store("chapter", book_name="book")

    assert isinstance(result, FakeChroma)
    assert store._client.requested == ["chapter-collection"]
