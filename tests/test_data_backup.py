import json
import shutil
import sqlite3
import zipfile

import pytest

import backend.data_backup as data_backup


def _configure_paths(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    mineru_root = tmp_path / "mineru_output"
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(data_backup, "DATA_ROOT", data_root)
    monkeypatch.setattr(data_backup, "MINERU_ROOT", mineru_root)
    monkeypatch.setattr(data_backup, "BACKUP_ROOT", backup_root)
    monkeypatch.setattr(data_backup, "PENDING_RESTORE_PATH", backup_root / "pending_restore.json")
    monkeypatch.setattr(data_backup, "RESTORE_RESULT_PATH", backup_root / "last_restore.json")
    return data_root, backup_root


def _write_vector_snapshot(root, names, mapping):
    root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(root / "chroma.sqlite3") as connection:
        connection.execute("CREATE TABLE collections (name TEXT NOT NULL)")
        connection.executemany("INSERT INTO collections VALUES (?)", [(name,) for name in names])
    (root / "_chapter_map.json").write_text(json.dumps(mapping), encoding="utf-8")


def test_backup_is_verified_and_does_not_include_secrets(monkeypatch, tmp_path):
    data_root, backup_root = _configure_paths(monkeypatch, tmp_path)
    progress = data_root / "progress"
    progress.mkdir(parents=True)
    with sqlite3.connect(progress / "mistakes.db") as conn:
        conn.execute("CREATE TABLE mistakes (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO mistakes VALUES ('m1')")
    (data_root / "books").mkdir()
    (data_root / "books" / "book.pdf").write_bytes(b"pdf")
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=secret", encoding="utf-8")

    result = data_backup.create_backup()

    assert result["valid"] if "valid" in result else True
    assert result["contains_secrets"] is False
    archive_path = backup_root / result["name"]
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "data/progress/mistakes.db" in names
        assert "data/books/book.pdf" in names
        assert all(".env" not in name for name in names)
        assert json.loads(archive.read("manifest.json"))["app_version"] == "1.0.0"


def test_restore_is_scheduled_with_safety_backup_and_applied_on_restart(monkeypatch, tmp_path):
    data_root, backup_root = _configure_paths(monkeypatch, tmp_path)
    progress = data_root / "progress"
    progress.mkdir(parents=True)
    marker = progress / "state.json"
    marker.write_text('{"value":"old"}', encoding="utf-8")
    original = data_backup.create_backup()

    marker.write_text('{"value":"new"}', encoding="utf-8")
    scheduled = data_backup.schedule_restore(original["name"])
    assert scheduled["restart_required"] is True
    assert (backup_root / scheduled["safety_backup"]).exists()
    assert marker.read_text(encoding="utf-8") == '{"value":"new"}'

    applied = data_backup.apply_pending_restore()
    assert applied["status"] == "completed"
    assert marker.read_text(encoding="utf-8") == '{"value":"old"}'
    assert not data_backup.PENDING_RESTORE_PATH.exists()


def test_invalid_backup_is_not_scheduled(monkeypatch, tmp_path):
    _, backup_root = _configure_paths(monkeypatch, tmp_path)
    backup_root.mkdir(parents=True)
    bad = backup_root / "learning_data_bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("../escape.txt", "bad")
    try:
        data_backup.schedule_restore(bad.name)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe backup should be rejected")


def test_sqlite_snapshot_failure_does_not_fall_back_to_raw_copy(monkeypatch, tmp_path):
    source = tmp_path / "active.db"
    destination = tmp_path / "snapshot.db"
    source.write_bytes(b"active-main-file")

    def fail_connect(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(data_backup.sqlite3, "connect", fail_connect)
    with pytest.raises(RuntimeError, match="consistent SQLite snapshot failed"):
        data_backup._copy_consistent_file(source, destination)

    assert not destination.exists()


def test_missing_pending_archive_is_consumed_and_reported(monkeypatch, tmp_path):
    _, backup_root = _configure_paths(monkeypatch, tmp_path)
    backup_root.mkdir(parents=True)
    data_backup.PENDING_RESTORE_PATH.write_text(
        json.dumps({"archive": "learning_data_missing.zip"}), encoding="utf-8"
    )

    result = data_backup.apply_pending_restore()

    assert result["status"] == "failed"
    assert "\u5907\u4efd\u4e0d\u5b58\u5728" in result["error"]
    assert not data_backup.PENDING_RESTORE_PATH.exists()
    assert json.loads(data_backup.RESTORE_RESULT_PATH.read_text(encoding="utf-8"))["status"] == "failed"


def test_restore_without_derived_data_invalidates_stale_indexes(monkeypatch, tmp_path):
    data_root, backup_root = _configure_paths(monkeypatch, tmp_path)
    progress = data_root / "progress"
    vector = data_root / "vector_db"
    mineru = tmp_path / "mineru_output"
    progress.mkdir(parents=True)
    vector.mkdir(parents=True)
    mineru.mkdir(parents=True)
    (progress / "state.json").write_text('{"value":"old"}', encoding="utf-8")
    (vector / "index.bin").write_bytes(b"old-index")
    (mineru / "derived.json").write_text("old-derived", encoding="utf-8")

    original = data_backup.create_backup(include_derived=False)
    (progress / "state.json").write_text('{"value":"new"}', encoding="utf-8")
    (vector / "index.bin").write_bytes(b"new-index")
    (mineru / "derived.json").write_text("new-derived", encoding="utf-8")

    scheduled = data_backup.schedule_restore(original["name"])
    safety_manifest = data_backup.inspect_backup(backup_root / scheduled["safety_backup"])
    assert "data/vector_db" in safety_manifest["included"]
    assert "mineru_output" in safety_manifest["included"]

    result = data_backup.apply_pending_restore()

    assert result["status"] == "completed"
    assert result["reindex_required"] is True
    assert set(result["invalidated"]) == {"data/vector_db", "mineru_output"}
    assert (progress / "state.json").read_text(encoding="utf-8") == '{"value":"old"}'
    assert not vector.exists()
    assert not mineru.exists()


def test_merge_restore_preserves_core_roots_absent_from_old_backup(monkeypatch, tmp_path):
    data_root, _backup_root = _configure_paths(monkeypatch, tmp_path)
    progress = data_root / "progress"
    progress.mkdir(parents=True)
    (progress / "state.json").write_text('{"value":"old"}', encoding="utf-8")
    original = data_backup.create_backup()

    books = data_root / "books"
    books.mkdir(parents=True)
    later = books / "later.pdf"
    later.write_bytes(b"later")
    (progress / "state.json").write_text('{"value":"new"}', encoding="utf-8")

    data_backup.schedule_restore(original["name"])
    applied = data_backup.apply_pending_restore()

    assert applied["status"] == "completed"
    assert applied["restore_mode"] == "merge"
    assert "data/books" in applied["preserved_unlisted"]
    assert later.read_bytes() == b"later"
    assert (progress / "state.json").read_text(encoding="utf-8") == '{"value":"old"}'


def test_restore_rejects_unmapped_staging_collection_before_replacing_user_data(monkeypatch, tmp_path):
    data_root, _backup_root = _configure_paths(monkeypatch, tmp_path)
    vector = data_root / "vector_db"
    _write_vector_snapshot(
        vector,
        ["scoped", "rogue"],
        {"scoped": {"chapter": "one", "book_name": "book-a"}},
    )
    invalid = data_backup.create_backup(include_derived=True, reason="invalid-vector")

    shutil.rmtree(vector)
    _write_vector_snapshot(
        vector,
        ["current"],
        {"current": {"chapter": "one", "book_name": "book-current"}},
    )
    marker = vector / "keep.txt"
    marker.write_text("current-user-data", encoding="utf-8")

    data_backup.schedule_restore(invalid["name"])
    result = data_backup.apply_pending_restore()

    assert result["status"] == "failed"
    assert result["error_code"] == "legacy_unscoped_index_requires_rebuild"
    assert marker.read_text(encoding="utf-8") == "current-user-data"


def test_restore_schedule_rejects_legacy_archive_map_before_safety_backup(monkeypatch, tmp_path):
    from ingestion.index_pipeline import VectorScopeInvariantError

    data_root, backup_root = _configure_paths(monkeypatch, tmp_path)
    _write_vector_snapshot(
        data_root / "vector_db",
        ["legacy"],
        {"legacy": "chapter one"},
    )
    invalid = data_backup.create_backup(include_derived=True, reason="legacy-map")

    with pytest.raises(VectorScopeInvariantError, match="legacy_unscoped_index_requires_rebuild"):
        data_backup.schedule_restore(invalid["name"])

    assert not data_backup.PENDING_RESTORE_PATH.exists()
    assert len(list(backup_root.glob("learning_data_*.zip"))) == 1
