"""Pure metric helpers for the embedding backend experiment."""
from __future__ import annotations

import numpy as np


TOP_K = (1, 3, 5, 10)


def top_indices(query_embeddings: np.ndarray, corpus_embeddings: np.ndarray, k: int = 10) -> np.ndarray:
    scores = np.asarray(query_embeddings, dtype=np.float32) @ np.asarray(corpus_embeddings, dtype=np.float32).T
    # Stable full ordering makes ties deterministic across repeated runs.
    return np.argsort(-scores, axis=1, kind="stable")[:, :k]


def overlap_metrics(torch_ranks: np.ndarray, onnx_ranks: np.ndarray) -> dict:
    result = {}
    for k in TOP_K:
        overlaps = [
            len(set(left[:k].tolist()) & set(right[:k].tolist())) / k
            for left, right in zip(torch_ranks, onnx_ranks)
        ]
        exact_order = [bool(np.array_equal(left[:k], right[:k])) for left, right in zip(torch_ranks, onnx_ranks)]
        result[f"top_{k}"] = {
            "mean_set_overlap": float(np.mean(overlaps)),
            "queries_with_identical_order": int(sum(exact_order)),
            "query_count": len(overlaps),
        }
    return result


def relevance_metrics(ranks: np.ndarray, corpus_ids: list[str], queries: list[dict]) -> dict:
    recalls = {k: [] for k in (1, 3, 5)}
    reciprocal_ranks = []
    for row, query in zip(ranks, queries):
        expected = set(query["expected_chunk_ids"])
        ranked_ids = [corpus_ids[int(index)] for index in row]
        for k in recalls:
            recalls[k].append(float(bool(expected.intersection(ranked_ids[:k]))))
        first = next((index + 1 for index, value in enumerate(ranked_ids) if value in expected), None)
        reciprocal_ranks.append(0.0 if first is None else 1.0 / first)
    return {
        **{f"recall_at_{k}": float(np.mean(values)) for k, values in recalls.items()},
        "mrr_at_10": float(np.mean(reciprocal_ranks)),
        "query_count": len(queries),
    }


def percentile(values: list[float] | np.ndarray, q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), q, method="linear"))
