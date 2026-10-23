"""Real isolated Chroma baseline; synthetic seeded vectors, not recall quality."""
import json
import os
from pathlib import Path
import statistics
import tempfile
import time

os.environ["ANONYMIZED_TELEMETRY"] = "False"
import chromadb
from chromadb.config import Settings
import numpy as np


def main():
    vectors = np.random.default_rng(42).normal(size=(500, 512)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    with tempfile.TemporaryDirectory(prefix="texa-audit-chroma-") as directory:
        started = time.perf_counter()
        client = chromadb.PersistentClient(path=directory, settings=Settings(anonymized_telemetry=False))
        collection = client.create_collection("audit_synthetic")
        initialize_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        collection.add(ids=[str(i) for i in range(500)], embeddings=vectors.tolist())
        insert_ms = (time.perf_counter() - started) * 1000
        samples = []
        for index in range(25):
            started = time.perf_counter()
            result = collection.query(query_embeddings=[vectors[index].tolist()], n_results=10)
            assert result["ids"][0][0] == str(index)
            if index >= 5:
                samples.append((time.perf_counter() - started) * 1000)
        report = {"kind": "real isolated Chroma, 500 seeded synthetic 512D vectors, top10; no embedding or textbook recall included", "version": chromadb.__version__, "initialize_ms": initialize_ms, "insert_ms": insert_ms,
                  "query_median_ms": statistics.median(samples), "query_p95_ms": sorted(samples)[18], "query_samples_ms": samples}
        # This subprocess owns the only client; never stop a shared production client.
        client._system.stop()
    path = Path("docs/qa/performance-reliability-2026-10-23/chroma-baseline.json")
    path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
