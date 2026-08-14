"""ONNX-only 100-query regression against the frozen existing Chroma index."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _recall(rows: list[dict], fixture_queries: dict[str, dict], k: int) -> float:
    values = []
    for row in rows:
        expected = {str(value) for value in fixture_queries[row["id"]].get("expected_chunk_ids") or []}
        values.append(1.0 if expected.intersection(row["ids"][:k]) else 0.0)
    return sum(values) / len(values) if values else 0.0


def _overlap(current: list[dict], baseline: list[dict], k: int) -> float:
    baseline_by_id = {row["id"]: row for row in baseline}
    values = []
    for row in current:
        reference = baseline_by_id.get(row["id"])
        if not reference:
            continue
        left, right = set(row["ids"][:k]), set(reference["ids"][:k])
        values.append(len(left & right) / max(1, k))
    return statistics.mean(values) if values else 0.0


def run(fixture_path: Path, baseline_path: Path) -> dict:
    from config import embedding_backend_name, get_embeddings
    from graph.retrieval_node import retrieve_node
    from ingestion.vector_store import get_vector_store

    if embedding_backend_name() != "onnx":
        raise RuntimeError("Existing-index Standard regression must run with the ONNX backend")
    provider = get_embeddings()
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    queries = fixture["queries"][:100]
    query_by_id = {str(item["id"]): item for item in queries}
    corpus_books = {
        str(item.get("id") or ""): str(item.get("book_name") or "")
        for item in fixture.get("corpus") or []
    }
    store = get_vector_store()
    rows = []
    started = time.perf_counter()
    for query in queries:
        expected = [str(value) for value in query.get("expected_chunk_ids") or []]
        book_name = next((corpus_books.get(value, "") for value in expected if corpus_books.get(value)), "")
        result = retrieve_node({
            "user_input": str(query["query"]),
            "target_chapters": [],
            "book_name": book_name or "default",
            "subject": "",
            "intent": "qa",
            "use_textbook_context": True,
            "retrieval_action": "full",
        })
        items = result.get("retrieval_debug_items") or []
        rows.append({
            "id": str(query["id"]),
            "book_name": book_name,
            "ids": [str(item.get("chunk_id") or item.get("preview") or "") for item in items[:10]],
            "retrieval_status": result.get("retrieval_status"),
            "retrieval_error": result.get("retrieval_error"),
        })
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_rows = baseline["rows"]
    quality = {}
    for k in (3, 5, 10):
        quality[f"recall_at_{k}"] = _recall(rows, query_by_id, k)
        quality[f"baseline_recall_at_{k}"] = _recall(baseline_rows, query_by_id, k)
        quality[f"set_overlap_at_{k}"] = _overlap(rows, baseline_rows, k)
    gates = {
        "recall_at_5_drop_lte_1pp": quality["recall_at_5"] >= quality["baseline_recall_at_5"] - 0.01,
        "recall_at_10_drop_lte_1pp": quality["recall_at_10"] >= quality["baseline_recall_at_10"] - 0.01,
        "top5_set_overlap_gte_95pct": quality["set_overlap_at_5"] >= 0.95,
    }
    known_data_issue = [
        row for row in rows
        if "nothing found on disk" in str(row.get("retrieval_error") or "").lower()
        or "热电式传感器" in str(row.get("retrieval_error") or "")
    ]
    if not known_data_issue:
        for collection_name, metadata in getattr(store, "_map", {}).items():
            chapter = str(metadata.get("chapter") or "")
            if "热电式传感器" not in chapter:
                continue
            try:
                collection = store._client.get_collection(collection_name)
                collection.query(
                    query_embeddings=[provider.embed_query("热电式传感器")],
                    n_results=1,
                )
            except Exception as exc:
                known_data_issue.append({
                    "chapter": chapter,
                    "collection": collection_name,
                    "error": str(exc),
                    "classification": "pre_existing_hnsw_segment_issue_not_onnx_regression",
                    "automatic_rebuild": False,
                })
    return {
        "status": "PASS" if all(gates.values()) else "FAIL",
        "backend": getattr(provider, "backend_name", type(provider).__name__),
        "query_count": len(rows),
        "collection_count": len(store._client.list_collections()),
        "automatic_rebuild": False,
        "index_schema_changed": False,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
        "quality": quality,
        "gates": gates,
        "known_hnsw_data_issue": known_data_issue,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=ROOT / "evaluation/datasets/embedding_retrieval.json")
    parser.add_argument("--baseline", type=Path, default=ROOT / "benchmark_results/embedding_onnx_phase2/retrieval_onnx.json")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark_results/embedding_onnx_phase3/existing_index_regression.json")
    args = parser.parse_args()
    result = run(args.fixture, args.baseline)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(payload, encoding="utf-8")
    os.replace(temp, args.output)
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
