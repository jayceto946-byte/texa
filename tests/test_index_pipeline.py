import json
from pathlib import Path


class FakeEmbeddings:
    def embed_documents(self, texts):
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0]


class FakeCollection:
    def __init__(self, query_ok=True):
        self.rows = {}
        self.query_ok = query_ok

    def add(self, *, ids, documents, embeddings, metadatas):
        for idx, item_id in enumerate(ids):
            self.rows[item_id] = (documents[idx], embeddings[idx], metadatas[idx])

    def count(self):
        return len(self.rows)

    def query(self, **_kwargs):
        return {"ids": [[next(iter(self.rows))]]} if self.rows and self.query_ok else {"ids": [[]]}


class FakeClient:
    def __init__(self, query_ok=True):
        self.collections = {"old": FakeCollection()}
        self.query_ok = query_ok

    def delete_collection(self, name):
        if name not in self.collections:
            raise KeyError(name)
        del self.collections[name]

    def get_or_create_collection(self, name):
        return self.collections.setdefault(name, FakeCollection(self.query_ok))

    def get_collection(self, name):
        return self.collections[name]


class FakeStore:
    def __init__(self, root: Path, query_ok=True):
        self._client = FakeClient(query_ok)
        self.embeddings = FakeEmbeddings()
        self._map_file = root / "_chapter_map.json"
        self._map = {"old": {"chapter": "old", "book_name": "demo", "kind": "chapter"}}
        self._stores = {"demo\0old": object()}
        self._map_file.parent.mkdir(parents=True)
        self._map_file.write_text(json.dumps(self._map), encoding="utf-8")


def _chunks():
    return [
        {"chunk_id": "c1", "chapter": "chapter-one", "section_title": "definition", "content": "absolute error is measured value minus true value", "role": "definition"},
        {"chunk_id": "c2", "chapter": "chapter-one", "section_title": "definition", "content": "absolute error is measured value minus true value", "role": "algorithm"},
    ]


def test_versioned_index_activates_only_after_dense_and_lexical_validation(monkeypatch, tmp_path):
    from ingestion import index_pipeline, lexical_index

    vector_root = tmp_path / "vector"
    monkeypatch.setattr(index_pipeline, "VECTOR_DB_PATH", vector_root)
    monkeypatch.setattr(lexical_index, "VECTOR_DB_PATH", vector_root)
    store = FakeStore(vector_root)
    chunks = _chunks()

    manifest = index_pipeline.build_and_activate_book_index(store, "demo", [("chapter-one", chunks)], chunks)

    assert manifest["status"] == "ready"
    assert manifest["vector_ready"] is True
    assert manifest["lexical_ready"] is True
    assert "old" not in store._client.collections
    assert all(entry.get("index_version") == manifest["index_version"] for entry in store._map.values())
    assert len(json.loads(lexical_index.index_path("demo").read_text(encoding="utf-8"))) == 2
    assert index_pipeline.load_index_manifest("demo")["content_fingerprint"] == manifest["content_fingerprint"]


def test_failed_dense_probe_keeps_previous_active_index(monkeypatch, tmp_path):
    import pytest
    from ingestion import index_pipeline, lexical_index

    vector_root = tmp_path / "vector"
    monkeypatch.setattr(index_pipeline, "VECTOR_DB_PATH", vector_root)
    monkeypatch.setattr(lexical_index, "VECTOR_DB_PATH", vector_root)
    store = FakeStore(vector_root, query_ok=False)
    lexical = lexical_index.index_path("demo")
    lexical.parent.mkdir(parents=True, exist_ok=True)
    lexical.write_text('[{"chunk_id":"old"}]', encoding="utf-8")

    with pytest.raises(RuntimeError, match="dense query validation failed"):
        index_pipeline.build_and_activate_book_index(store, "demo", [("chapter-one", _chunks())], _chunks())

    assert store._map == {"old": {"chapter": "old", "book_name": "demo", "kind": "chapter"}}
    assert "old" in store._client.collections
    assert json.loads(lexical.read_text(encoding="utf-8")) == [{"chunk_id": "old"}]
    assert set(store._client.collections) == {"old"}
