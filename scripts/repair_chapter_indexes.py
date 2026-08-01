"""Rebuild textbook chapter collections from the persisted lexical source."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import VECTOR_DB_PATH  # noqa: E402
from ingestion.lexical_index import load_book_index  # noqa: E402
from ingestion.vector_store import ChapterVectorStore  # noqa: E402

DEFAULT_BOOKS = ("传感器短书", "传感器长书")


def backup_vector_db() -> Path:
    source = Path(VECTOR_DB_PATH).resolve()
    expected = (ROOT / "data" / "vector_db").resolve()
    if source != expected:
        raise RuntimeError(f"refusing unexpected vector DB path: {source}")
    backup = source.with_name(f"{source.name}.backup-{time.strftime('%Y%m%d-%H%M%S')}-chapter-repair")
    if backup.exists():
        raise FileExistsError(backup)
    shutil.copytree(source, backup)
    return backup


def rebuild_book(vs: ChapterVectorStore, book_name: str) -> dict:
    rows = load_book_index(book_name)
    if not rows:
        raise RuntimeError(f"lexical source is empty for {book_name}")
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        chapter = str(row.get("chapter") or "").strip()
        if not chapter:
            raise RuntimeError(f"chunk without chapter in {book_name}: {row.get('chunk_id', '')}")
        grouped[chapter].append(dict(row))

    built_chunks = 0
    for index, (chapter, chunks) in enumerate(grouped.items(), 1):
        roles = {str(chunk.get("chunk_id") or ""): str(chunk.get("role") or "reference") for chunk in chunks}
        vs.build_chapter_store(chapter, chunks, chunk_roles=roles, book_name=book_name)
        built_chunks += len(chunks)
        if index % 25 == 0 or index == len(grouped):
            print(f"[repair] {book_name}: {index}/{len(grouped)} chapters", flush=True)
    return {"book_name": book_name, "chapters": len(grouped), "chunks": built_chunks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", action="append", dest="books")
    parser.add_argument("--skip-backup", action="store_true")
    args = parser.parse_args()
    books = tuple(args.books or DEFAULT_BOOKS)
    for book in books:
        if not load_book_index(book):
            raise RuntimeError(f"cannot rebuild {book}: lexical source missing")

    backup = None if args.skip_backup else backup_vector_db()
    vs = ChapterVectorStore()
    results = [rebuild_book(vs, book) for book in books]
    report = {
        "repaired_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "backup": str(backup or ""),
        "books": results,
    }
    output = ROOT / "data" / "eval" / "chapter_index_repair_20260801.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
