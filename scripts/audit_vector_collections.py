"""Read-only Chroma collection health audit with a real vector query."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import chromadb

from config import VECTOR_DB_PATH


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data" / "eval" / "vector_collection_health_20260801.json"


def main() -> None:
    db_path = Path(VECTOR_DB_PATH)
    map_path = db_path / "_chapter_map.json"
    chapter_map = json.loads(map_path.read_text(encoding="utf-8")) if map_path.exists() else {}
    client = chromadb.PersistentClient(path=str(db_path))
    rows = []

    collections = client.list_collections()
    for index, listed in enumerate(collections, 1):
        name = listed.name
        entry = chapter_map.get(name) or {}
        row = {
            "name": name,
            "chapter": entry.get("chapter", name),
            "book_name": entry.get("book_name", ""),
            "kind": entry.get("kind", "chapter"),
            "mapped": bool(entry),
            "status": "unknown",
            "count": 0,
            "error": "",
        }
        try:
            collection = client.get_collection(name)
            row["count"] = int(collection.count())
            if row["count"] <= 0:
                row["status"] = "empty"
            else:
                sample = collection.get(limit=1, include=["embeddings"])
                embeddings = sample.get("embeddings")
                if embeddings is None or len(embeddings) == 0:
                    row["status"] = "missing_embedding"
                else:
                    vector = embeddings[0]
                    result = collection.query(
                        query_embeddings=[vector],
                        n_results=1,
                        include=["distances"],
                    )
                    ids = result.get("ids") or []
                    row["status"] = "healthy" if ids and ids[0] else "query_empty"
        except Exception as exc:
            row["status"] = "broken"
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
        if index % 50 == 0 or index == len(collections):
            print(f"[audit] {index}/{len(collections)}", flush=True)

    by_book = defaultdict(Counter)
    for row in rows:
        by_book[row["book_name"] or "(unmapped)"][row["status"]] += 1
    report = {
        "audited_at": datetime.now().astimezone().isoformat(),
        "vector_db": str(db_path),
        "collection_count": len(rows),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "by_book": {book: dict(counts) for book, counts in sorted(by_book.items())},
        "collections": rows,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "report": str(REPORT),
        "collection_count": report["collection_count"],
        "status_counts": report["status_counts"],
        "by_book": report["by_book"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
