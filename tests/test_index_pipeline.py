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
    assert "old" in store._client.collections
    assert store._map["old"]["active"] is False
    assert len(manifest["versions"]) == 2
    assert manifest["versions"][1]["collections"] == ["old"]
    assert all(
        entry.get("index_version") == manifest["index_version"]
        for entry in store._map.values() if entry.get("active", True)
    )
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


def test_release_gate_runs_production_retrieval_with_staged_bindings(monkeypatch, tmp_path):
    from evaluation.rag_eval import load_cases
    from graph import retrieval_node
    from ingestion import index_pipeline

    dataset = Path(__file__).resolve().parents[1] / "evaluation" / "datasets" / "error_theory_recall.jsonl"
    cases = load_cases(dataset)
    by_question = {case["question"]: case for case in cases}
    calls = []

    def fake_retrieve(state, **bindings):
        calls.append(bindings)
        case = by_question[state["user_input"]]
        if not case.get("answerable", True):
            return {
                "evidence_items": [],
                "chapter_contents": {},
                "evidence_support": {"status": "insufficient"},
            }
        text = "\n".join(case.get("required_points") or [])
        return {
            "evidence_items": [{
                "chunk_id": case["id"], "chapter": "测试章", "section_title": "测试节",
                "text": text, "score": 1.0, "query_coverage": 1.0,
            }],
            "chapter_contents": {},
            "evidence_support": {"status": "supported"},
        }

    monkeypatch.setattr(retrieval_node, "retrieve_node", fake_retrieve)
    store = FakeStore(tmp_path / "vector")
    summary = index_pipeline._validate_staged_production_retrieval(
        store,
        "误差理论与数据处理",
        {"staged": {"book_name": "误差理论与数据处理", "kind": "book_aggregate"}},
        _chunks(),
    )

    assert summary["cases"] == len(cases)
    assert summary["recall_at_k"] == 1.0
    assert calls and calls[0]["vector_store"] is not store
    assert callable(calls[0]["lexical_search"])
    assert callable(calls[0]["neighbor_expander"])


def test_failed_production_gate_keeps_previous_active_index(monkeypatch, tmp_path):
    import pytest
    from ingestion import index_pipeline, lexical_index

    vector_root = tmp_path / "vector"
    monkeypatch.setattr(index_pipeline, "VECTOR_DB_PATH", vector_root)
    monkeypatch.setattr(lexical_index, "VECTOR_DB_PATH", vector_root)
    store = FakeStore(vector_root)
    lexical = lexical_index.index_path("demo")
    lexical.parent.mkdir(parents=True, exist_ok=True)
    lexical.write_text('[{"chunk_id":"old"}]', encoding="utf-8")

    def reject(*_args, **_kwargs):
        raise RuntimeError("production gate rejected candidate")

    monkeypatch.setattr(index_pipeline, "_validate_staged_production_retrieval", reject)
    with pytest.raises(RuntimeError, match="production gate rejected"):
        index_pipeline.build_and_activate_book_index(store, "demo", [("chapter-one", _chunks())], _chunks())

    assert store._map == {"old": {"chapter": "old", "book_name": "demo", "kind": "chapter"}}
    assert set(store._client.collections) == {"old"}
    assert json.loads(lexical.read_text(encoding="utf-8")) == [{"chunk_id": "old"}]


def test_version_retention_keeps_active_plus_two_previous_versions(monkeypatch, tmp_path):
    from ingestion import index_pipeline, lexical_index

    vector_root = tmp_path / "vector"
    monkeypatch.setattr(index_pipeline, "VECTOR_DB_PATH", vector_root)
    monkeypatch.setattr(lexical_index, "VECTOR_DB_PATH", vector_root)
    monkeypatch.setattr(
        index_pipeline,
        "_validate_staged_production_retrieval",
        lambda *_args, **_kwargs: {"cases": 0, "status": "not_configured"},
    )
    store = FakeStore(vector_root)

    manifests = []
    for revision in range(3):
        chunks = [{
            "chunk_id": f"c{revision}", "chapter": "chapter-one",
            "section_title": "definition", "content": f"definition revision {revision}",
            "role": "definition",
        }]
        manifests.append(index_pipeline.build_and_activate_book_index(
            store, "demo", [("chapter-one", chunks)], chunks,
        ))

    latest = manifests[-1]
    assert len(latest["versions"]) == 3
    assert [item["index_version"] for item in latest["versions"]] == [
        manifests[2]["index_version"], manifests[1]["index_version"], manifests[0]["index_version"],
    ]
    assert "old" not in store._client.collections
    assert sum(bool(entry.get("active", True)) for entry in store._map.values()) == 2


def test_retained_version_can_be_reactivated_without_deleting_current(monkeypatch, tmp_path):
    from ingestion import index_pipeline, lexical_index

    vector_root = tmp_path / "vector"
    monkeypatch.setattr(index_pipeline, "VECTOR_DB_PATH", vector_root)
    monkeypatch.setattr(lexical_index, "VECTOR_DB_PATH", vector_root)
    monkeypatch.setattr(
        index_pipeline,
        "_validate_staged_production_retrieval",
        lambda *_args, **_kwargs: {"cases": 0, "status": "not_configured"},
    )
    store = FakeStore(vector_root)
    first = index_pipeline.build_and_activate_book_index(
        store, "demo", [("chapter-one", _chunks())], _chunks(),
    )
    second_chunks = [{
        "chunk_id": "c-new", "chapter": "chapter-one",
        "section_title": "definition", "content": "new definition", "role": "definition",
    }]
    second = index_pipeline.build_and_activate_book_index(
        store, "demo", [("chapter-one", second_chunks)], second_chunks,
    )

    rolled_back = index_pipeline.activate_retained_index_version(
        store, "demo", first["index_version"],
    )

    assert rolled_back["index_version"] == first["index_version"]
    assert rolled_back["schema_version"] == index_pipeline.INDEX_SCHEMA_VERSION
    assert json.loads(lexical_index.index_path("demo").read_text(encoding="utf-8"))[0]["chunk_id"] == "c1"
    assert all(store._map[name]["active"] for name in rolled_back["versions"][0]["collections"])
    assert all(name in store._client.collections for name in second["versions"][0]["collections"])


def test_specialty_gate_failure_blocks_activation_and_preserves_old_version(monkeypatch, tmp_path):
    import pytest
    from graph import retrieval_node
    from ingestion import index_pipeline, lexical_index

    vector_root = tmp_path / "vector"
    monkeypatch.setattr(index_pipeline, "VECTOR_DB_PATH", vector_root)
    monkeypatch.setattr(lexical_index, "VECTOR_DB_PATH", vector_root)
    store = FakeStore(vector_root)
    probes = [
        {
            "id": f"probe-{specialty}", "book_name": "demo",
            "question": f"{specialty} probe", "intent": "formula" if specialty == "formula" else "factual_recall",
            "required_points": [f"{specialty}-anchor"], "answerable": True,
            "specialty": specialty, "tags": ["generated_probe", specialty],
        }
        for specialty in ("formula", "list", "example", "table")
    ]
    by_question = {case["question"]: case for case in probes}

    def fake_retrieve(state, **_bindings):
        case = by_question[state["user_input"]]
        text = "" if case["specialty"] == "table" else case["required_points"][0]
        return {
            "evidence_items": ([{
                "chunk_id": case["id"], "chapter": "chapter-one", "section_title": case["specialty"],
                "text": text, "score": 1.0, "query_coverage": 1.0,
            }] if text else []),
            "chapter_contents": {},
            "evidence_support": {"status": "supported" if text else "insufficient"},
        }

    monkeypatch.setattr(retrieval_node, "retrieve_node", fake_retrieve)
    with pytest.raises(RuntimeError, match="specialty_gates=.*table"):
        index_pipeline.build_and_activate_book_index(
            store,
            "demo",
            [("chapter-one", _chunks())],
            _chunks(),
            acceptance_probes=probes,
            specialty_inventory={name: 1 for name in ("formula", "list", "example", "table")},
        )

    assert store._map == {"old": {"chapter": "old", "book_name": "demo", "kind": "chapter"}}
    assert set(store._client.collections) == {"old"}
