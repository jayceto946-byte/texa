import json

from backend.services.book_read_cache import BookReadCache


def test_json_cache_reuses_disk_read_without_sharing_mutable_results(tmp_path, monkeypatch):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"subject": "数学"}), encoding="utf-8")
    calls = 0
    original = type(path).read_text

    def counted_read_text(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "read_text", counted_read_text)
    cache = BookReadCache()

    first = cache.read_json(path, {})
    first["subject"] = "polluted"
    second = cache.read_json(path, {})

    assert calls == 1
    assert second is not first
    assert second == {"subject": "数学"}


def test_json_cache_refreshes_when_file_signature_changes(tmp_path):
    path = tmp_path / "chapters.json"
    path.write_text('[{"title":"第一章"}]', encoding="utf-8")
    cache = BookReadCache()
    assert cache.read_json(path, []) == [{"title": "第一章"}]

    path.write_text('[{"title":"第二章","extra":"changes-size"}]', encoding="utf-8")

    assert cache.read_json(path, []) == [{"title": "第二章", "extra": "changes-size"}]


def test_index_stats_loader_runs_once_per_file_snapshot(tmp_path):
    chapter_map = tmp_path / "_chapter_map.json"
    lexical = tmp_path / "book.json"
    chapter_map.write_text("{}", encoding="utf-8")
    lexical.write_text("[]", encoding="utf-8")
    cache = BookReadCache()
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        return {"healthy": True, "calls": calls}

    first = cache.index_stats("book", chapter_map, lexical, loader)
    first["healthy"] = False
    assert cache.index_stats("book", chapter_map, lexical, loader) == {
        "healthy": True,
        "calls": 1,
    }
    lexical.write_text('[{"id":1}]', encoding="utf-8")
    assert cache.index_stats("book", chapter_map, lexical, loader)["calls"] == 2


def test_index_stats_cache_tracks_vector_inventory_dependencies(tmp_path):
    cache = BookReadCache()
    chapter_map = tmp_path / "map.json"
    lexical = tmp_path / "lexical.json"
    sqlite = tmp_path / "chroma.sqlite3"
    chapter_map.write_text("{}", encoding="utf-8")
    lexical.write_text("[]", encoding="utf-8")
    sqlite.write_bytes(b"one")
    calls = 0

    def loader():
        nonlocal calls
        calls += 1
        return {"calls": calls}

    assert cache.index_stats(
        "book", chapter_map, lexical, loader, dependency_paths=(sqlite,),
    )["calls"] == 1
    sqlite.write_bytes(b"changed")
    assert cache.index_stats(
        "book", chapter_map, lexical, loader, dependency_paths=(sqlite,),
    )["calls"] == 2


def test_json_cache_refreshes_after_same_size_overwrite(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text('{"value":"one"}', encoding="utf-8")
    cache = BookReadCache()

    assert cache.read_json(path, {}) == {"value": "one"}
    path.write_text('{"value":"two"}', encoding="utf-8")

    assert cache.read_json(path, {}) == {"value": "two"}
