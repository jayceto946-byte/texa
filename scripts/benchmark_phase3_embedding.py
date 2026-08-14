"""Benchmark the production ONNX singleton for Phase 3 release gates."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT)) if getattr(sys, "frozen", False) else SOURCE_ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.embedding_backend.phase1_worker import measure, percentile, rss_bytes


def _summary(samples: list[dict], count: int) -> dict:
    latencies = [item["latency_ms"] for item in samples]
    median = statistics.median(latencies)
    return {
        "runs": len(samples),
        "median_ms": median,
        "p95_ms": percentile(latencies, 0.95),
        "texts_per_second": count / (median / 1000) if median else 0.0,
        "peak_rss_mib_p95": percentile([item["peak_rss_bytes"] / 1024 / 1024 for item in samples], 0.95),
        "samples": samples,
    }


def run() -> dict:
    from config import embedding_backend_name, get_embeddings

    if embedding_backend_name() != "onnx":
        raise RuntimeError("Phase 3 release benchmark requires TEXA_EMBEDDING_BACKEND=onnx")
    fixture = json.loads((ROOT / "evaluation/datasets/embedding_retrieval.json").read_text(encoding="utf-8"))
    texts = [str(item["text"]) for item in fixture["corpus"]]
    if len(texts) != 500:
        raise RuntimeError(f"Expected the frozen 500-text fixture, found {len(texts)}")
    query = "什么是压阻效应？"
    provider = get_embeddings()
    if provider is not get_embeddings():
        raise RuntimeError("Embedding provider is not a process singleton")

    for _ in range(5):
        provider.embed_query(query)
    interactive_samples = [measure(lambda: provider.embed_query(query))[1] for _ in range(20)]

    provider.embed_documents(texts)
    ingestion_samples = [measure(lambda: provider.embed_documents(texts))[1] for _ in range(5)]

    ingestion_started = threading.Event()
    ingestion_result: dict = {}

    def ingest() -> None:
        ingestion_started.set()
        started = time.perf_counter()
        provider.embed_documents(texts)
        ingestion_result["latency_ms"] = (time.perf_counter() - started) * 1000

    thread = threading.Thread(target=ingest, name="phase3-ingestion")
    thread.start()
    ingestion_started.wait(2)
    concurrent_samples = []
    while thread.is_alive() and len(concurrent_samples) < 20:
        concurrent_samples.append(measure(lambda: provider.embed_query(query))[1])
    thread.join()
    while len(concurrent_samples) < 20:
        concurrent_samples.append(measure(lambda: provider.embed_query(query))[1])

    interactive = _summary(interactive_samples, 1)
    ingestion = _summary(ingestion_samples, len(texts))
    concurrent = _summary(concurrent_samples, 1)
    gates = {
        "interactive_median_lt_5ms": interactive["median_ms"] < 5.0,
        "interactive_faster_than_torch_6_762ms": interactive["median_ms"] < 6.762,
        "ingestion_gte_20_texts_per_second": ingestion["texts_per_second"] >= 20.0,
        "ingestion_gte_90pct_torch_baseline": ingestion["texts_per_second"] >= 10.59 * 0.9,
        "concurrent_query_not_unusable": concurrent["p95_ms"] < 250.0,
    }
    return {
        "status": "PASS" if all(gates.values()) else "FAIL",
        "backend": getattr(provider, "backend_name", type(provider).__name__),
        "runtime_config": getattr(provider, "runtime_config", {}),
        "fixture_count": len(texts),
        "interactive": interactive,
        "ingestion": ingestion,
        "concurrent": {
            **concurrent,
            "ingestion_latency_ms": ingestion_result.get("latency_ms"),
            "ingestion_texts_per_second": len(texts) / (ingestion_result["latency_ms"] / 1000),
        },
        "process_rss_mib_after": rss_bytes() / 1024 / 1024,
        "gates": gates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark_results/embedding_onnx_phase3/source_embedding_benchmark.json")
    args = parser.parse_args()
    result = run()
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(payload, encoding="utf-8")
    os.replace(temp, args.output)
    print(json.dumps({key: value for key, value in result.items() if key not in {"interactive", "ingestion", "concurrent"}}, ensure_ascii=False, indent=2))
    print(json.dumps({
        "interactive": {key: value for key, value in result["interactive"].items() if key != "samples"},
        "ingestion": {key: value for key, value in result["ingestion"].items() if key != "samples"},
        "concurrent": {key: value for key, value in result["concurrent"].items() if key != "samples"},
    }, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
