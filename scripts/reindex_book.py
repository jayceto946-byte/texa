"""Supported maintenance entry point for rebuilding one textbook index."""
from __future__ import annotations

import argparse
from bisect import bisect_right
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import PROGRESS_PATH
from ingestion.document_ir import load_canonical_book
from ingestion.mineru_importer import build_index_from_chapters
from ingestion.vector_store import get_vector_store
from utils.json_io import atomic_write_json
from utils.path_safety import safe_book_name


def _read_list(path: Path) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _best_middle_chunks(book_name: str) -> tuple[Path | None, list[dict]]:
    root = Path(PROGRESS_PATH) / book_name
    candidates = []
    for path in root.rglob("*_middle_chunks.json") if root.exists() else []:
        try:
            rows = _read_list(path)
        except Exception:
            continue
        if rows:
            candidates.append((len(rows), path, rows))
    if not candidates:
        return None, []
    _count, path, rows = max(candidates, key=lambda item: item[0])
    return path, rows


def _chapter_heading_positions(chapters: list[dict], rows: list[dict]) -> list[int]:
    """Locate chapter starts when persisted chapter records contain no body text."""
    positions: list[int] = []
    for chapter in chapters:
        title = _normalized(chapter.get("title", ""))
        if not title:
            return []
        position = next((
            index for index, row in enumerate(rows)
            if _normalized(row.get("section_title", "")) == title
        ), None)
        if position is None or (positions and position <= positions[-1]):
            return []
        positions.append(position)
    return positions


def hydrate_chapters(chapters: list[dict], rows: list[dict]) -> tuple[list[dict], int]:
    """Attach persisted chunks to their source chapter without changing chunk IDs."""
    chapter_texts = [_normalized(item.get("text", "")) for item in chapters]
    grouped = [[] for _ in chapters]
    heading_positions = _chapter_heading_positions(chapters, rows) if not any(chapter_texts) else []
    unmatched = 0
    last_index = 0
    for offset, source in enumerate(rows):
        content = str(source.get("content") or source.get("text") or "").strip()
        if not content:
            continue
        needle = _normalized(content)[:240]
        match = max(0, bisect_right(heading_positions, offset) - 1) if heading_positions else None
        if match is None and needle:
            order = list(range(last_index, len(chapters))) + list(range(0, last_index))
            match = next((idx for idx in order if needle in chapter_texts[idx]), None)
        if match is None:
            unmatched += 1
            match = min(last_index, max(len(chapters) - 1, 0))
        else:
            last_index = match
        item = dict(source)
        item["content"] = content
        item["chapter"] = str(chapters[match].get("title") or "")
        item["section_title"] = str(item.get("section_title") or item["chapter"])
        item["chunk_index"] = int(item.get("chunk_index", offset) or offset)
        grouped[match].append(item)
    hydrated = []
    for chapter, chunks in zip(chapters, grouped):
        if not chunks:
            continue
        item = dict(chapter)
        item["chunks"] = chunks
        item["text"] = str(item.get("text") or "\n\n".join(chunk["content"] for chunk in chunks))
        hydrated.append(item)
    return hydrated, unmatched


def rebuild(book_name: str, *, prefer_middle: bool = False) -> dict:
    safe = safe_book_name(book_name)
    root = Path(PROGRESS_PATH) / safe
    chapters_path = root / "_chapters.json"
    if not chapters_path.exists():
        raise FileNotFoundError(f"persisted chapters not found: {chapters_path}")
    chapters = _read_list(chapters_path)
    source_path = None
    unmatched = 0
    if prefer_middle:
        source_path, rows = _best_middle_chunks(safe)
        if rows:
            chapters, unmatched = hydrate_chapters(chapters, rows)
            if unmatched > max(5, int(len(rows) * 0.05)):
                raise RuntimeError(f"too many source chunks could not be mapped to chapters: {unmatched}/{len(rows)}")
    try:
        canonical_book = load_canonical_book(safe, progress_root=PROGRESS_PATH)
    except FileNotFoundError:
        canonical_book = None
    indexed = build_index_from_chapters(
        safe,
        chapters,
        root,
        canonical_book=canonical_book,
        canonical_progress_root=PROGRESS_PATH,
    )
    stats = get_vector_store().get_book_index_stats(safe)
    if stats.get("status") != "ready" or int(stats.get("chunk_count", 0)) != indexed:
        raise RuntimeError(f"activated index did not pass final health check: {stats}")
    metadata_path = root / "metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    except Exception:
        metadata = {}
    metadata.update({
        "indexed_chunks": indexed,
        "index_schema": int(stats.get("index_schema", 0) or 0),
        "index_version": stats.get("index_version", ""),
    })
    atomic_write_json(metadata_path, metadata)
    return {"book_name": safe, "indexed_chunks": indexed, "source_chunks": str(source_path or ""), "unmatched_chunks": unmatched, "index_status": stats}


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild one textbook through the supported versioned index pipeline.")
    parser.add_argument("--book-name", required=True)
    parser.add_argument("--prefer-middle-chunks", action="store_true")
    args = parser.parse_args()
    print(json.dumps(rebuild(args.book_name, prefer_middle=args.prefer_middle_chunks), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
