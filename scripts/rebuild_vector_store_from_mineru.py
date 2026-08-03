"""Rebuild Chroma vector DB from MinerU middle chunks with a recoverable backup."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import defaultdict
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import VECTOR_DB_PATH  # noqa: E402
from ingestion.chunk_roles import assign_chunk_roles, load_kg_chunk_roles  # noqa: E402
from ingestion.vector_store import ChapterVectorStore, reset_vector_store  # noqa: E402

DEFAULT_BOOK = "\u4f18\u5316\u8bbe\u8ba1"


def load_chunks(book_name: str) -> list[dict]:
    path = ROOT / "mineru_output" / book_name / "hybrid_auto" / f"{book_name}_middle_chunks.json"
    if not path.exists():
        raise FileNotFoundError(f"middle_chunks not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def backup_vector_db() -> Path | None:
    target = Path(VECTOR_DB_PATH)
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)
        return None
    backup = target.with_name(f"{target.name}.backup-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.move(str(target), str(backup))
    target.mkdir(parents=True, exist_ok=True)
    return backup


CHAPTER_RE = re.compile(r"^\u7b2c[\u4e00-\u9fff0-9]+\u7ae0")


def normalize_title(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"\s+\d+\s*$", "", value).strip()
    if not value or value == "(no title)":
        return "unsectioned"
    return value


def group_title(section_title: str, current_chapter: str) -> tuple[str, str]:
    title = normalize_title(section_title)
    if CHAPTER_RE.match(title):
        return title, title
    if current_chapter:
        return current_chapter, current_chapter
    return title, current_chapter


def rebuild(book_name: str, *, backup: bool = True) -> dict:
    chunks = load_chunks(book_name)
    roles = load_kg_chunk_roles(book_name)
    backup_path = backup_vector_db() if backup else None
    reset_vector_store()
    vs = ChapterVectorStore()

    grouped: dict[str, list[dict]] = defaultdict(list)
    current_chapter = ""
    for index, chunk in enumerate(chunks):
        section_title = normalize_title(chunk.get("section_title", ""))
        title, current_chapter = group_title(section_title, current_chapter)
        chunk_id = str(chunk.get("chunk_id") or "")
        grouped[title].append({
            "content": chunk.get("text", ""),
            "chunk_id": chunk_id,
            "chapter": title,
            "chunk_index": index,
            "page_idx": chunk.get("page_idx", -1),
            "section_title": section_title,
        })

    built = 0
    for title, group in grouped.items():
        chunk_roles = assign_chunk_roles(group, roles)
        vs.build_chapter_store(title, group, chunk_roles=chunk_roles, book_name=book_name)
        built += len(group)
        print(f"[BUILD] {title}: {len(group)} chunks", flush=True)

    return {
        "book_name": book_name,
        "chunks": len(chunks),
        "collections": len(grouped),
        "built_chunks": built,
        "backup": str(backup_path) if backup_path else "",
        "vector_db": str(VECTOR_DB_PATH),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely rebuild Chroma vector DB from MinerU middle chunks.")
    parser.add_argument("--book-name", default=DEFAULT_BOOK)
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--output", default=str(ROOT / "data" / "eval" / "vector_rebuild_report.json"))
    args = parser.parse_args()
    result = rebuild(args.book_name, backup=not args.no_backup)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit("Legacy direct Chroma writer disabled. Use scripts/reindex_book.py instead.")
