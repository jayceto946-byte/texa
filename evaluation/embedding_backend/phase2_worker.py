"""Subprocess worker for Phase 2 runtime and existing-index experiments."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_backend(name: str):
    import config

    if name == "torch":
        from evaluation.embedding_backend.providers import TorchEmbeddingProvider

        provider = TorchEmbeddingProvider(batch_size=32, num_threads=2)
    else:
        from evaluation.embedding_backend.phase2_runtime import Phase2StandardEmbeddings

        provider = Phase2StandardEmbeddings()
    config._embeddings_instance = provider
    config.get_embeddings = lambda: provider
    return provider


def _component_counts(items: list[dict]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        for source in item.get("fusion_sources") or []:
            counts[str(source)] += 1
        if item.get("source") == "neighbor":
            counts["neighbor"] += 1
    return dict(counts)


def run_retrieval(backend: str, fixture: Path) -> dict:
    started = time.perf_counter()
    provider = _install_backend(backend)
    from graph.retrieval_node import retrieve_node
    from ingestion.vector_store import get_vector_store

    vector_started = time.perf_counter()
    store = get_vector_store()
    vector_load_ms = (time.perf_counter() - vector_started) * 1000
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    corpus_books = {
        str(item.get("id") or ""): str(item.get("book_name") or "")
        for item in payload.get("corpus") or []
    }
    rows = []
    component_totals: Counter[str] = Counter()
    retrieval_started = time.perf_counter()
    for query in payload["queries"][:100]:
        expected_ids = [str(value) for value in query.get("expected_chunk_ids") or []]
        query_book = next((corpus_books.get(value, "") for value in expected_ids if corpus_books.get(value)), "")
        result = retrieve_node({
            "user_input": str(query["query"]),
            "target_chapters": [],
            "book_name": query_book or "default",
            "subject": "",
            "intent": "qa",
            "use_textbook_context": True,
            "retrieval_action": "full",
        })
        items = result.get("retrieval_debug_items") or []
        ids = [str(item.get("chunk_id") or item.get("preview") or "") for item in items[:10]]
        counts = _component_counts(items)
        component_totals.update(counts)
        rows.append({
            "id": query["id"],
            "query": query["query"],
            "book_name": query_book,
            "ids": ids,
            "retrieval_status": result.get("retrieval_status"),
            "retrieval_error": result.get("retrieval_error"),
            "component_counts": counts,
        })
    retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
    return {
        "backend": backend,
        "provider": getattr(provider, "backend_name", type(provider).__name__),
        "query_count": len(rows),
        "vector_store_path": str(store.db_path.resolve()),
        "collection_count": len(store._client.list_collections()),
        "vector_load_ms": vector_load_ms,
        "retrieval_total_ms": retrieval_ms,
        "retrieval_mean_ms": retrieval_ms / max(1, len(rows)),
        "component_totals": dict(component_totals),
        "rows": rows,
        "process_total_ms": (time.perf_counter() - started) * 1000,
    }


def run_runtime() -> dict:
    banned = ["torch", "sentence_transformers", "transformers", "safetensors"]
    absence = {name: importlib.util.find_spec(name) is None for name in banned}
    provider = _install_backend("onnx")
    query_started = time.perf_counter()
    vector = provider.embed_query("最小二乘法的基本思想是什么？")
    query_ms = (time.perf_counter() - query_started) * 1000

    import backend.main as backend_main
    from ingestion.vector_store import get_vector_store
    from graph.retrieval_node import retrieve_node
    from utils.book_registry import BookRegistry

    store = get_vector_store()
    search_started = time.perf_counter()
    test_book = os.getenv("PHASE2_TEST_BOOK", "误差理论与数据处理")
    search = store.search_all("最小二乘法", k=3, top_n=2, book_name=test_book)
    search_ms = (time.perf_counter() - search_started) * 1000
    textbook = retrieve_node({
        "user_input": "最小二乘法的基本思想是什么？",
        "target_chapters": [],
        "book_name": test_book,
        "subject": "",
        "intent": "qa",
        "use_textbook_context": True,
        "retrieval_action": "full",
    })
    generic = retrieve_node({
        "user_input": "你好",
        "target_chapters": [],
        "book_name": "default",
        "subject": "",
        "intent": "qa",
        "use_textbook_context": False,
        "retrieval_action": "none",
    })
    registry = BookRegistry()
    book_method = next((name for name in ("list", "list_books", "all", "get_all") if hasattr(registry, name)), "")
    books = getattr(registry, book_method)() if book_method else []
    from fastapi.testclient import TestClient

    health_started = time.perf_counter()
    with TestClient(backend_main.app) as client:
        health = client.get("/health").json()
        for _ in range(120):
            if health.get("warmup", {}).get("status") in {"ready", "degraded"}:
                break
            time.sleep(0.1)
            health = client.get("/health").json()
    health_ms = (time.perf_counter() - health_started) * 1000
    return {
        "banned_packages_absent": absence,
        "backend_import": backend_main.app.title,
        "embedding_dimensions": len(vector),
        "embedding_query_ms": query_ms,
        "chroma_available": store.available,
        "collection_count": len(store._client.list_collections()),
        "search_chapter_count": len(search.items),
        "search_status": search.status,
        "search_ms": search_ms,
        "textbook_retrieval_status": textbook.get("retrieval_status"),
        "textbook_evidence_count": len(textbook.get("retrieval_debug_items") or []),
        "textbook_retrieval_error": textbook.get("retrieval_error"),
        "generic_retrieval_status": generic.get("retrieval_status"),
        "book_discovery_method": book_method,
        "book_count": len(books),
        "health_status": health.get("status"),
        "warmup": health.get("warmup"),
        "lifespan_health_ms": health_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=("runtime", "retrieval"), required=True)
    parser.add_argument("--backend", choices=("torch", "onnx"), default="onnx")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=ROOT / "evaluation" / "datasets" / "embedding_retrieval.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_runtime() if args.action == "runtime" else run_retrieval(args.backend, args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
