"""Read-only collector contracts using synthetic inputs only."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import zipfile

import pytest

from scripts.diagnose_mineru_tables import collect, inspect_chroma, raw_tables
from scripts import diagnose_mineru_tables as diagnostic


BOOK = "表格结构测试"
PROBE = "auto_table_synthetic"


def write_json(path, payload, *, lines=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in payload) if lines else
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def synthetic_payload():
    fixture = Path(__file__).parent / "fixtures/mineru/table_continuation.synthetic.json"
    return json.loads(fixture.read_text())["payload"]


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_zip_collection_preserves_continuation_repeated_headers_images_and_numbers(tmp_path):
    source = tmp_path / "original.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("output/structured_content.json", json.dumps(synthetic_payload(), ensure_ascii=False))
        # Untrusted archive paths must never be extracted by diagnostics.
        archive.writestr("../not-extracted.txt", "untrusted")
    before = source.read_bytes()
    report = raw_tables(source, [1, 2])
    assert [t["page_idx"] for t in report["tables"]] == [1, 2]
    assert report["tables"][1]["raw"]["captions"] == [dict(content="(续)")]
    for table in report["tables"]:
        assert "长度/μm" in table["raw"]["content"]
        assert table["image_references"]
    assert "91~103" in report["tables"][1]["raw"]["content"]
    assert source.read_bytes() == before
    assert not (tmp_path / "not-extracted.txt").exists()


def test_existing_ir_and_lexical_are_traced_without_mutation_or_cross_book_export(tmp_path):
    user = tmp_path / "userData"
    progress = user / "data/progress" / BOOK
    table = dict(record_type="document_block", block_id="table-a", block_type="table", page_start=2,
                 text="表2-3", bbox=[.1, .2, .9, .4], attributes=dict(source_page_idx=1, source_block_index=2))
    write_json(progress / "canonical_document.jsonl", [dict(record_type="canonical_book", book_name=BOOK), table], lines=True)
    probe = dict(id=PROBE, specialty="table", question="表2-3中列出了哪些字段或数据？", required_points=["μm"],
                 provenance=dict(page_start=2, source_block_ids=["table-a"]))
    write_json(progress / "acceptance_probes.generated.jsonl", [probe], lines=True)
    write_json(progress / "canonical_versions/old/canonical_document.jsonl", [dict(record_type="canonical_book", book_name=BOOK)], lines=True)
    chunk = dict(book_name=BOOK, chunk_id="c1", block_type="table", page_start=2,
                 source_block_ids=["table-a"], content="| 长度/μm | 11~17 |")
    write_json(user / "data/vector_db/_lexical" / (BOOK + ".json"), [chunk, dict(chunk, book_name="other-book", content="PRIVATE")])
    write_json(user / "data/vector_db/_chapter_map.json", {"target": dict(book_name=BOOK), "other": dict(book_name="other-book")})
    (user / "logs").mkdir()
    (user / "logs/backend.log").write_text("API_KEY=DO_NOT_EXPORT\n" + f"ERROR staged production retrieval release gate failed: failed=['{PROBE}'], missing={{'x': ['μm']}}\n", encoding="utf-8")
    before = snapshot(user)
    result = collect(user, BOOK, [1, 2], PROBE)
    assert snapshot(user) == before
    assert not result["errors"]
    assert len(result["canonical_snapshots"]) == 2
    active = next(s for s in result["canonical_snapshots"] if s["directory"] == str(progress))
    assert active["probe_id_found"]
    assert active["blocks"][0]["attributes"]["source_block_index"] == 2
    assert result["lexical_snapshots"][0]["rows"] == [chunk]
    assert set(result["collection_map"]) == {"target"}
    assert len(result["release_errors"]) == 1
    assert "PRIVATE" not in json.dumps(result)
    assert "DO_NOT_EXPORT" not in json.dumps(result)
    assert result["chroma"]["status"] == "missing"
    assert result["unresolved"]


def test_chroma_sqlite_is_read_only_and_reports_collection_membership(tmp_path):
    db = tmp_path / "chroma.sqlite3"
    connection = sqlite3.connect(db)
    connection.executescript("""
        CREATE TABLE collections(id TEXT, name TEXT);
        CREATE TABLE segments(id TEXT, collection TEXT);
        CREATE TABLE embeddings(id INTEGER, embedding_id TEXT, segment_id TEXT);
        CREATE TABLE embedding_metadata(id INTEGER, key TEXT, string_value TEXT, int_value INTEGER, float_value REAL);
        INSERT INTO collections VALUES('col', 'staged-table');
        INSERT INTO segments VALUES('seg', 'col');
        INSERT INTO embeddings VALUES(1, 'embedding-a', 'seg');
        INSERT INTO embeddings VALUES(2, 'embedding-private', 'seg');
    """)
    for row_id, book in [(1, BOOK), (2, "other-book")]:
        for key, value in dict(book_name=book, block_type="table", chunk_id="c1", source_block_ids='["table-a"]').items():
            connection.execute("INSERT INTO embedding_metadata VALUES(?,?,?,NULL,NULL)", (row_id, key, value))
        connection.execute("INSERT INTO embedding_metadata VALUES(?, 'page_start', NULL, 2, NULL)", (row_id,))
    connection.commit()
    connection.close()
    before = db.read_bytes()
    result = inspect_chroma(db, BOOK, [1, 2], {"table-a"})
    assert result["book_embedding_records"] == 1
    assert result["matches"][0]["collection"] == "staged-table"
    assert result["matches"][0]["metadata"]["source_block_ids"] == ["table-a"]
    assert db.read_bytes() == before
    assert not Path(str(db) + "-journal").exists()


def test_missing_candidate_is_unknown_and_bad_input_is_isolated(tmp_path):
    (tmp_path / "user").mkdir()
    source = tmp_path / "broken.zip"
    source.write_bytes(b"invalid")
    report = collect(tmp_path / "user", BOOK, [1, 2], PROBE, source)
    assert report["errors"][0]["component"] == "structured_content"
    assert report["chroma"]["status"] == "missing"
    assert not report["canonical_snapshots"][0]["probe_id_found"]
    assert "do not prove ingestion loss" in " ".join(report["unresolved"])


def test_committed_wal_is_read_on_disposable_copy_without_source_changes(tmp_path):
    db = tmp_path / "chroma.sqlite3"
    connection = sqlite3.connect(db)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript("""
            CREATE TABLE collections(id TEXT, name TEXT);
            CREATE TABLE segments(id TEXT, collection TEXT);
            CREATE TABLE embeddings(id INTEGER, embedding_id TEXT, segment_id TEXT);
            CREATE TABLE embedding_metadata(id INTEGER, key TEXT, string_value TEXT, int_value INTEGER, float_value REAL);
        """)
        before = snapshot(tmp_path)
        result = inspect_chroma(db, BOOK, [1, 2], set())
        assert result["snapshot"]["wal_included"]
        assert result["status"] == "read_only_sqlite_metadata"
        assert snapshot(tmp_path) == before  # Includes the live WAL and SHM.
    finally:
        connection.close()


def test_changing_sqlite_snapshot_is_rejected_instead_of_misreported(monkeypatch, tmp_path):
    db = tmp_path / "chroma.sqlite3"
    db.write_bytes(b"first-state")
    copyfile = diagnostic.shutil.copyfile
    def concurrent_write(source, destination):
        copyfile(source, destination)
        Path(source).write_bytes(b"concurrent-change")
    monkeypatch.setattr(diagnostic.shutil, "copyfile", concurrent_write)
    with pytest.raises(RuntimeError, match="changed during snapshot"):
        inspect_chroma(db, BOOK, [1, 2], set())


@pytest.mark.parametrize("name", ["../book", "..", "x/y", "x\\y"])
def test_book_name_cannot_escape_user_data(tmp_path, name):
    with pytest.raises(ValueError, match="book_name"):
        collect(tmp_path, name, [1], PROBE)


def test_standalone_cli_runs_without_site_packages_and_cannot_overwrite_inputs(tmp_path):
    user = tmp_path / "user"
    user.mkdir()
    script = Path(__file__).resolve().parents[1] / "scripts/diagnose_mineru_tables.py"
    output = tmp_path / "report.json"
    command = [sys.executable, "-I", "-S", str(script), "--user-data", str(user), "--book-name", BOOK, "--page-idx", "1", "2", "--probe-id", PROBE, "--output"]
    result = subprocess.run(command + [str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text())["schema"] == "texa.table-diagnostic/v1"
    assert subprocess.run(command + [str(output)], capture_output=True).returncode != 0
    assert subprocess.run(command + [str(user / "report.json")], capture_output=True).returncode != 0
