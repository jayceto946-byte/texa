import json
import sqlite3
from types import SimpleNamespace

import pytest

from ingestion.index_pipeline import (
    LEGACY_UNSCOPED_INDEX_ERROR_CODE,
    VectorScopeInvariantError,
    require_scoped_vector_snapshot,
)
from ingestion.vector_store import ChapterVectorStore


def _write_inventory(root, names):
    root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(root / "chroma.sqlite3") as connection:
        connection.execute("CREATE TABLE collections (name TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO collections(name) VALUES (?)",
            [(name,) for name in names],
        )


@pytest.mark.parametrize(
    "mapping",
    [
        {"legacy": "chapter one"},
        {"legacy": {"chapter": "chapter one", "book_name": ""}},
    ],
)
def test_legacy_or_empty_scope_map_is_rejected(mapping):
    with pytest.raises(VectorScopeInvariantError) as caught:
        require_scoped_vector_snapshot(mapping=mapping, collection_names=["legacy"])

    assert caught.value.error_code == LEGACY_UNSCOPED_INDEX_ERROR_CODE
    assert str(caught.value).startswith(LEGACY_UNSCOPED_INDEX_ERROR_CODE)


def test_sqlite_collection_without_map_entry_is_rejected(tmp_path):
    root = tmp_path / "vector_db"
    _write_inventory(root, ["scoped", "rogue"])
    (root / "_chapter_map.json").write_text(
        json.dumps({"scoped": {"chapter": "one", "book_name": "book-a"}}),
        encoding="utf-8",
    )

    with pytest.raises(VectorScopeInvariantError, match=LEGACY_UNSCOPED_INDEX_ERROR_CODE):
        require_scoped_vector_snapshot(root)


def test_startup_guard_runs_before_collection_map_recovery(monkeypatch, tmp_path):
    import chromadb
    import ingestion.vector_store as vector_store_module

    root = tmp_path / "vector_db"
    root.mkdir()
    original_map = {"scoped": {"chapter": "one", "book_name": "book-a"}}
    map_file = root / "_chapter_map.json"
    map_file.write_text(json.dumps(original_map), encoding="utf-8")

    class RecoverableCollection:
        name = "rogue"

        def peek(self, limit=1):
            return {"metadatas": [{"chapter": "one", "book_name": "book-a"}]}

    class Client:
        def list_collections(self):
            return [SimpleNamespace(name="scoped"), RecoverableCollection()]

    monkeypatch.setattr(vector_store_module, "VECTOR_DB_PATH", root)
    monkeypatch.setattr(vector_store_module, "get_embeddings", lambda: object())
    monkeypatch.setattr(chromadb, "PersistentClient", lambda **_kwargs: Client())

    store = ChapterVectorStore()

    assert store.available is False
    assert isinstance(store.scope_error, VectorScopeInvariantError)
    assert json.loads(map_file.read_text(encoding="utf-8")) == original_map


@pytest.mark.parametrize("failure", ["missing", "wrong_scope"])
def test_manifest_collection_reference_must_exist_with_matching_book_scope(failure):
    mapping = {
        "active": {"chapter": "one", "book_name": "book-a", "active": True},
        "retained": {"chapter": "one", "book_name": "book-b", "active": False},
    }
    reference = "absent" if failure == "missing" else "retained"
    manifest = {
        "book_name": "book-a",
        "aggregate_collection": "active",
        "versions": [{"index_version": "old", "collections": [reference]}],
    }

    with pytest.raises(VectorScopeInvariantError, match=LEGACY_UNSCOPED_INDEX_ERROR_CODE):
        require_scoped_vector_snapshot(
            mapping=mapping,
            collection_names=list(mapping),
            manifests=[manifest],
        )


def test_scoped_active_and_retained_versions_are_accepted():
    mapping = {
        "active": {"chapter": "same", "book_name": "book-a", "active": True},
        "retained": {"chapter": "same", "book_name": "book-a", "active": False},
    }
    require_scoped_vector_snapshot(
        mapping=mapping,
        collection_names=list(mapping),
        manifests=[{
            "book_name": "book-a",
            "aggregate_collection": "active",
            "versions": [
                {"index_version": "new", "collections": ["active"]},
                {"index_version": "old", "collections": ["retained"]},
            ],
        }],
    )


def test_same_named_chapters_remain_isolated_by_explicit_book_scope():
    store = ChapterVectorStore.__new__(ChapterVectorStore)
    store._map = {
        "scoped-a-chapter": {
            "chapter": "chapter one", "book_name": "book-a", "kind": "chapter", "active": True,
        },
        "scoped-b-chapter": {
            "chapter": "chapter one", "book_name": "book-b", "kind": "chapter", "active": True,
        },
    }
    collections = [SimpleNamespace(name=name) for name in store._map]

    selected = store._iter_collections_for_book(collections, "book-a")

    assert [item.name for item in selected] == ["scoped-a-chapter"]


def test_fast_readiness_does_not_let_lexical_assets_mask_invalid_vector_scope(monkeypatch, tmp_path):
    from backend.api import books
    from ingestion import lexical_index

    root = tmp_path / "vector_db"
    _write_inventory(root, ["scoped", "rogue"])
    (root / "_chapter_map.json").write_text(
        json.dumps({"scoped": {"chapter": "one", "book_name": "book-a"}}),
        encoding="utf-8",
    )
    lexical_path = tmp_path / "book-a.json"
    lexical_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(books, "VECTOR_DB_PATH", root)
    monkeypatch.setattr(lexical_index, "load_book_index", lambda _book: [{"content": "ready"}])
    monkeypatch.setattr(lexical_index, "index_path", lambda _book: lexical_path)

    stats = books._compute_fast_book_index_stats("book-a")

    assert stats["lexical_ready"] is True
    assert stats["healthy"] is False
    assert stats["vector_ready"] is False
    assert stats["error_code"] == LEGACY_UNSCOPED_INDEX_ERROR_CODE
    assert stats["reindex_required"] is True


def test_book_index_stats_does_not_let_lexical_assets_mask_invalid_vector_scope(monkeypatch, tmp_path):
    from ingestion import lexical_index

    lexical_path = tmp_path / "book-a.json"
    lexical_path.write_text("[]", encoding="utf-8")
    store = ChapterVectorStore.__new__(ChapterVectorStore)
    store._client = SimpleNamespace(
        list_collections=lambda: [SimpleNamespace(name="legacy")],
    )
    store._map = {"legacy": "chapter one"}
    store.scope_error = None
    monkeypatch.setattr(lexical_index, "load_book_index", lambda _book: [{"content": "ready"}])
    monkeypatch.setattr(lexical_index, "index_path", lambda _book: lexical_path)

    stats = store.get_book_index_stats("book-a")

    assert stats["lexical_ready"] is True
    assert stats["healthy"] is False
    assert stats["vector_ready"] is False
    assert stats["error_code"] == LEGACY_UNSCOPED_INDEX_ERROR_CODE
    assert stats["reindex_required"] is True


def test_vector_asset_readiness_reports_stable_scope_error(monkeypatch, tmp_path):
    from backend.api import assets

    root = tmp_path / "vector_db"
    _write_inventory(root, ["legacy"])
    (root / "_chapter_map.json").write_text(
        json.dumps({"legacy": "chapter one"}), encoding="utf-8",
    )
    monkeypatch.setattr(assets, "VECTOR_DB_PATH", root)

    status = assets._vector_status({"assets": {}})

    assert status["healthy"] is False
    assert status["vector_ready"] is False
    assert status["error_code"] == LEGACY_UNSCOPED_INDEX_ERROR_CODE
    assert status["reindex_required"] is True


def test_sample_seed_rejects_invalid_vector_before_creating_user_data(monkeypatch, tmp_path):
    from desktop import backend_server

    sample = tmp_path / "sample"
    vector = sample / "vector_db"
    vector.mkdir(parents=True)
    (vector / "_chapter_map.json").write_text(
        json.dumps({"legacy": "chapter one"}), encoding="utf-8",
    )
    target = tmp_path / "user-data"
    monkeypatch.setenv("KAOYAN_SEED_DATA_DIR", str(sample))

    with pytest.raises(VectorScopeInvariantError, match=LEGACY_UNSCOPED_INDEX_ERROR_CODE):
        backend_server._seed_sample_data(target)

    assert not target.exists()


def test_vector_bundle_rejects_invalid_staging_before_moving_active_data(monkeypatch, tmp_path):
    from backend.api import assets

    target = tmp_path / "active-vector"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("current", encoding="utf-8")
    downloads = tmp_path / "downloads"
    monkeypatch.setattr(assets, "VECTOR_DB_PATH", target)
    monkeypatch.setattr(assets, "DOWNLOAD_DIR", downloads)
    monkeypatch.setattr(assets, "VECTOR_BUNDLE_URL", "https://example.invalid/vector.zip")
    monkeypatch.setattr(assets, "VECTOR_BUNDLE_SHA256", "")
    monkeypatch.setattr(assets, "_download_file", lambda _url, _dest: "digest")

    def fake_extract(_archive, staging):
        source = staging / "vector_db"
        source.mkdir(parents=True)
        (source / "_chapter_map.json").write_text(
            json.dumps({"legacy": "chapter one"}), encoding="utf-8",
        )

    monkeypatch.setattr(assets, "_safe_extract", fake_extract)

    result = assets.download_vector_bundle()

    assert result["success"] is False
    assert result["error_code"] == LEGACY_UNSCOPED_INDEX_ERROR_CODE
    assert marker.read_text(encoding="utf-8") == "current"
    assert not list(tmp_path.glob("active-vector.backup-*"))
