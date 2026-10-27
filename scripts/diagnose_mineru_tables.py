"""Read-only customer-side table evidence collection; Python standard library only.

This deliberately does not import Texa/config/Chroma, load .env, extract ZIPs,
embed text, query a model, rebuild an index, or change a release gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import tempfile
import zipfile
from html.parser import HTMLParser


class ImageReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            source = dict(attrs).get("src")
            if source:
                self.sources.append(source)


def image_references(text):
    parser = ImageReferences()
    parser.feed(str(text or ""))
    return sorted(set(parser.sources))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path):
    with path.open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path), "size": path.stat().st_size, "sha256": digest.hexdigest()}


def table_on_pages(row, pages):
    # Canonical and chunks use one-based physical page_start, not printed pages.
    return row.get("block_type") == "table" and row.get("page_start") in {p + 1 for p in pages}


def target_row(row, pages, block_ids):
    return table_on_pages(row, pages) or bool(block_ids.intersection(row.get("source_block_ids") or []))


def raw_tables(source, pages):
    """Read only structured_content JSON; ZIP member names are never extracted."""
    if source.is_dir():
        names = sorted(source.rglob("structured_content.json"))
        if len(names) != 1:
            raise ValueError(f"expected one structured_content.json, found {len(names)}")
        payload = read_json(names[0])
        identity = fingerprint(names[0])
    elif source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            names = [n for n in archive.namelist() if PurePosixPath(n).name == "structured_content.json"]
            if len(names) != 1:
                raise ValueError(f"expected one structured_content.json in ZIP, found {len(names)}")
            if archive.getinfo(names[0]).file_size > 128 * 1024 * 1024:
                raise ValueError("structured_content.json exceeds diagnostic 128 MiB limit")
            raw = archive.read(names[0])
            payload = json.loads(raw.decode("utf-8-sig"))
            identity = {**fingerprint(source), "member": names[0],
                        "member_sha256": hashlib.sha256(raw).hexdigest()}
    else:
        payload = read_json(source)
        identity = fingerprint(source)
    tables = []
    for page_offset, page in enumerate(payload["pages"]):
        if page.get("page_idx") not in pages:
            continue
        for offset, block in enumerate(page["blocks"]):
            if block.get("type") == "table":
                tables.append({"source_page_index": page_offset, "page_idx": page["page_idx"],
                               "source_block_index": offset, "raw": block,
                               "image_references": image_references(block.get("content"))})
    return {"identity": identity, "metadata": payload.get("metadata"), "tables": tables}


def inspect_canonical(directory, pages, probe_id):
    document = directory / "canonical_document.jsonl"
    records = read_jsonl(document) if document.is_file() else []
    blocks = [r for r in records if r.get("record_type") == "document_block"]
    probes_path = directory / "acceptance_probes.generated.jsonl"
    probes = read_jsonl(probes_path) if probes_path.is_file() else []
    selected_probes = [p for p in probes if p.get("id") == probe_id or (
        p.get("specialty") == "table" and (p.get("provenance") or {}).get("page_start") in {v + 1 for v in pages})]
    block_ids = {b for p in selected_probes for b in (p.get("provenance") or {}).get("source_block_ids", [])}
    selected_blocks = [b for b in blocks if table_on_pages(b, pages) or b.get("block_id") in block_ids]
    return {"directory": str(directory), "header": records[0] if records else None,
            "canonical_identity": fingerprint(document) if document.is_file() else None,
            "probes_identity": fingerprint(probes_path) if probes_path.is_file() else None,
            "blocks": selected_blocks, "probes": selected_probes,
            "probe_id_found": any(p.get("id") == probe_id for p in selected_probes)}


def inspect_chroma(database, book_name, pages, block_ids):
    if not database.is_file():
        return {"status": "missing", "matches": []}
    # Even SQLite mode=ro can create/update WAL shared-memory sidecars. Open
    # only a disposable copy; preserve committed WAL records without touching
    # the customer's DB/SHM. Reject a copy if its inputs changed while reading.
    inputs = [database, Path(str(database) + "-wal")]

    def stamps():
        return [(p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ino) if p.exists() else None for p in inputs]

    with tempfile.TemporaryDirectory(prefix="texa-table-diagnostic-") as temporary:
        target = Path(temporary) / "chroma.sqlite3"
        before = stamps()
        for path, stamp in zip(inputs, before):
            if stamp is not None:
                shutil.copyfile(path, Path(temporary) / path.name)
        if before != stamps():
            raise RuntimeError("Chroma DB/WAL changed during snapshot; retry diagnostics when import is idle")
        result = _inspect_chroma_snapshot(target, book_name, pages, block_ids)
        result["snapshot"] = {"source": str(database), "wal_included": before[1] is not None,
                              "source_stamps_stable_during_copy": True}
        return result


def _inspect_chroma_snapshot(database, book_name, pages, block_ids):
    # Do not use immutable=1: it ignores committed records in the copied WAL.
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        collection_names = dict(connection.execute("SELECT id, name FROM collections"))
        entries = connection.execute("""
            SELECT e.id, e.embedding_id, s.collection
            FROM embeddings e JOIN segments s ON s.id=e.segment_id
            JOIN embedding_metadata b ON b.id=e.id
            WHERE b.key='book_name' AND b.string_value=?
        """, (book_name,)).fetchall()
        matches = []
        metadata_columns = {r[1] for r in connection.execute("PRAGMA table_info(embedding_metadata)")}
        values = [v for v in ("string_value", "int_value", "float_value", "bool_value") if v in metadata_columns]
        for row_id, embedding_id, collection_id in entries:
            metadata = {}
            for key, *raw_values in connection.execute(
                    "SELECT key, " + ", ".join(values) + " FROM embedding_metadata WHERE id=?", (row_id,)):
                metadata[key] = next((v for v in raw_values if v is not None), None)
            for key in ("source_block_ids", "source_locations", "table_header", "table_rows", "section_path", "bbox"):
                if isinstance(metadata.get(key), str):
                    metadata[key] = json.loads(metadata[key])
            if target_row(metadata, pages, block_ids):
                # Only export the known provenance/content fields; never arbitrary
                # metadata from unrelated records or other books.
                keys = ("chunk_id", "book_name", "chapter", "index_version", "canonical_hash", "block_type",
                        "page_start", "page_end", "bbox", "source_block_ids", "source_locations",
                        "table_title", "table_header", "table_rows", "raw_content", "source_markdown")
                matches.append({"embedding_id": embedding_id, "collection": collection_names.get(collection_id),
                                "metadata": {k: metadata[k] for k in keys if k in metadata}})
        return {"status": "read_only_sqlite_metadata", "book_embedding_records": len(entries), "matches": matches,
                "limitation": "Metadata presence does not prove dense search recall or HNSW health."}
    finally:
        connection.close()


def collect(user_data, book_name, pages, probe_id, source=None):
    if not book_name or book_name in {".", ".."} or re.search(r'[<>:"/\\|?*\x00-\x1f]', book_name):
        raise ValueError("book_name must be the actual safe directory name, without path separators")
    report = {"schema": "texa.table-diagnostic/v1", "book_name": book_name, "page_indices": pages,
              "probe_id": probe_id, "errors": [], "canonical_snapshots": [], "lexical_snapshots": [],
              "release_errors": [], "source": None, "manifest": None, "collection_map": {}}

    def attempt(label, operation):
        try:
            return operation()
        except Exception as exc:
            report["errors"].append({"component": label, "error": f"{type(exc).__name__}: {exc}"})
            return None

    if source:
        report["source"] = attempt("structured_content", lambda: raw_tables(source, pages))
    vector = user_data / "data" / "vector_db"
    progress = user_data / "data" / "progress" / book_name
    # Retained versions and active IR are distinct. Never treat an old active
    # snapshot as the failed candidate without its index/hash identity.
    directories = {progress}
    directories.update(p.parent for p in progress.glob("canonical_versions/*/canonical_document.jsonl"))
    for directory in sorted(directories):
        result = attempt("canonical:" + str(directory), lambda d=directory: inspect_canonical(d, pages, probe_id))
        if result:
            report["canonical_snapshots"].append(result)
    block_ids = {b["block_id"] for s in report["canonical_snapshots"] for b in s["blocks"]}
    mapping = vector / "_chapter_map.json"
    if mapping.is_file():
        value = attempt("collection_map", lambda: read_json(mapping))
        if isinstance(value, dict):
            report["collection_map"] = {k: v for k, v in value.items() if isinstance(v, dict) and v.get("book_name") == book_name}
    manifest = vector / "_index_manifests" / (book_name + ".json")
    if manifest.is_file():
        report["manifest"] = attempt("manifest", lambda: read_json(manifest))
    lexical_paths = set((vector / "_lexical_versions" / book_name).glob("*.json"))
    lexical_paths.add(vector / "_lexical" / (book_name + ".json"))
    lexical_paths.update((vector / "_lexical").glob("." + book_name + ".json.*.staging"))
    for path in sorted(lexical_paths):
        if not path.is_file():
            continue
        rows = attempt("lexical:" + str(path), lambda p=path: read_json(p))
        if isinstance(rows, list):
            report["lexical_snapshots"].append({"identity": fingerprint(path), "rows": [
                row for row in rows if row.get("book_name") == book_name and target_row(row, pages, block_ids)]})
    report["chroma"] = attempt("chroma", lambda: inspect_chroma(vector / "chroma.sqlite3", book_name, pages, block_ids))
    for log in sorted((user_data / "logs").glob("backend.log*")):
        def read_release_errors():
            found = []
            with log.open(encoding="utf-8", errors="replace") as stream:
                for number, line in enumerate(stream, 1):
                    marker = "staged production retrieval release gate failed:"
                    if marker in line and (probe_id in line or book_name in line):
                        found.append({"file": log.name, "line": number, "message": line[line.index(marker):].strip()})
            return found
        report["release_errors"].extend(attempt("log:" + log.name, read_release_errors) or [])
    report["unresolved"] = [
        "No recorded candidate ranks or Final EvidencePack were collected; historical retrieval stage is unknown.",
        "Missing failed-candidate files/collections do not prove ingestion loss: failed builds clean candidates.",
        "Snapshots may belong to older successful imports; compare canonical_hash/index_version before attributing them.",
        "No gate was run by this collector; textbook acceptance remains unconfirmed.",
    ]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(os.environ["APPDATA"]) / "考研智能辅助系统" if os.environ.get("APPDATA") else None
    parser.add_argument("--user-data", type=Path, default=default_root)
    parser.add_argument("--book-name", required=True, help="Exact imported book/directory name, without .pdf unless used in Texa")
    parser.add_argument("--mineru-output", type=Path, help="Original ZIP, extracted output directory, or structured_content.json")
    parser.add_argument("--page-idx", type=int, nargs="+", required=True)
    parser.add_argument("--probe-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.user_data is None or not args.user_data.is_dir():
        parser.error("--user-data must point to the installed desktop userData directory")
    protected = [args.user_data.resolve()]
    if args.mineru_output:
        protected.append(args.mineru_output.resolve())
    output = args.output.resolve()
    if any(output == root or root in output.parents for root in protected):
        parser.error("--output must be outside userData and original MinerU input")
    report = collect(args.user_data, args.book_name, args.page_idx, args.probe_id, args.mineru_output)
    # Exclusive creation prevents accidental overwrite, including existing reports.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Diagnostic saved: {output}; component errors: {len(report['errors'])}; release not evaluated")
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
