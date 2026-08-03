from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import chromadb

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEFAULT_DELIVERABLES = DATA / "imports" / "kaoyan_ocr_20260704" / "deliverables"
DEFAULT_VECTOR_DB = Path(os.getenv("VECTOR_DB_PATH") or r"C:\tmp\chroma_smoke_test")
MODEL_SNAPSHOTS = DATA / "models" / "models--BAAI--bge-small-zh-v1.5" / "snapshots"

BOOKS = {
    "sensor_core": {"book_name": "传感器短书", "subject": "传感器", "book_role": "core", "rag_priority": 1.0},
    "sensor_reference": {"book_name": "传感器长书", "subject": "传感器", "book_role": "reference", "rag_priority": 0.55},
    "error_theory": {"book_name": "误差理论与数据处理", "subject": "误差理论与数据处理", "book_role": "core", "rag_priority": 1.0},
}


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value)).strip(" ._")
    return value or "book"


def role(value: Any) -> str:
    value = str(value or "reference").strip()
    if value == "formula":
        return "derivation"
    if value == "text":
        return "reference"
    return value or "reference"


def book_collection_name(book_name: str) -> str:
    h = hashlib.md5(safe_name(book_name).encode("utf-8")).hexdigest()[:24]
    return f"book{h}"


def write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_rows(path: Path, meta: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            if not line.strip():
                continue
            row = json.loads(line)
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            title = re.sub(r"\s+", " ", str(row.get("title") or "")).strip() or f"{meta['book_name']} (全文)"
            rows.append({
                "id": str(row.get("chunk_id") or f"chunk_{idx}"),
                "text": text,
                "metadata": {
                    "chapter": title[:120],
                    "book_name": safe_name(meta["book_name"]),
                    "chunk_index": idx,
                    "chunk_id": str(row.get("chunk_id") or f"chunk_{idx}"),
                    "section_title": title[:120],
                    "page_idx": int(row.get("page_idx", -1) or -1),
                    "role": role(row.get("semantic_role")),
                    "subject": str(row.get("subject") or meta["subject"]),
                    "book_role": str(row.get("book_role") or meta["book_role"]),
                    "rag_priority": float(row.get("rag_priority") or meta["rag_priority"]),
                    "review_status": str(row.get("review_status") or "machine_generated"),
                    "source_markdown": str(row.get("source_markdown") or ""),
                    "collection_schema": 2,
                },
            })
    return rows


def load_model():
    import torch
    torch.set_num_threads(2)
    snapshots = list(MODEL_SNAPSHOTS.iterdir()) if MODEL_SNAPSHOTS.exists() else []
    model_path = str(snapshots[0]) if snapshots else "BAAI/bge-small-zh-v1.5"
    print(f"[embedding] {model_path}", flush=True)
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_path, device="cpu", cache_folder=str(DATA / "models"), local_files_only=bool(snapshots))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build one aggregate Chroma collection per OCR textbook.")
    parser.add_argument("--deliverables", type=Path, default=DEFAULT_DELIVERABLES)
    parser.add_argument("--vector-db", type=Path, default=DEFAULT_VECTOR_DB)
    parser.add_argument("--book", choices=sorted(BOOKS), action="append")
    args = parser.parse_args()

    vector_db = args.vector_db.resolve()
    deliverables = args.deliverables.resolve()
    if not deliverables.exists():
        raise SystemExit(f"Deliverables not found: {deliverables}")

    print(f"[chroma] {vector_db}", flush=True)
    client = chromadb.PersistentClient(path=str(vector_db))
    model = load_model()
    map_file = vector_db / "_chapter_map.json"
    try:
        chapter_map = json.loads(map_file.read_text(encoding="utf-8")) if map_file.exists() else {}
    except Exception:
        chapter_map = {}

    selected = args.book or list(BOOKS)
    summaries = []
    for book_id in selected:
        meta = BOOKS[book_id]
        source = deliverables / f"{book_id}_chunks.jsonl"
        rows = load_rows(source, meta)
        col_name = book_collection_name(meta["book_name"])
        try:
            client.delete_collection(col_name)
        except Exception:
            pass
        col = client.get_or_create_collection(col_name)
        for start in range(0, len(rows), 64):
            batch = rows[start:start + 64]
            texts = [item["text"] for item in batch]
            vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()
            ids = [f"{book_id}_{item['id']}_{start + i}" for i, item in enumerate(batch)]
            col.add(ids=ids, documents=texts, embeddings=vectors, metadatas=[item["metadata"] for item in batch])
        chapter_map[col_name] = {
            "chapter": f"{meta['book_name']} (aggregate)",
            "book_name": safe_name(meta["book_name"]),
            "schema_version": "2",
            "kind": "book_aggregate",
        }
        summaries.append({"book_id": book_id, "book_name": meta["book_name"], "collection": col_name, "chunks": len(rows)})
        print(f"[aggregate] {meta['book_name']}: {len(rows)} chunks -> {col_name}", flush=True)

    write_json(map_file, chapter_map)
    print(json.dumps({"success": True, "vector_db_path": str(vector_db), "books": summaries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit("Legacy direct Chroma writer disabled. Use scripts/reindex_book.py instead.")
