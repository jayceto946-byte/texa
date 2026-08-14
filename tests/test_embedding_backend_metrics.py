import numpy as np

from evaluation.embedding_backend.benchmark_metrics import overlap_metrics, relevance_metrics


def test_overlap_metrics_uses_set_overlap_and_tracks_order():
    left = np.array([[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]])
    right = np.array([[0, 2, 1, 3, 4, 5, 6, 7, 8, 9]])
    result = overlap_metrics(left, right)
    assert result["top_1"]["mean_set_overlap"] == 1.0
    assert result["top_3"]["mean_set_overlap"] == 1.0
    assert result["top_3"]["queries_with_identical_order"] == 0


def test_relevance_metrics_accepts_any_annotated_relevant_chunk():
    ranks = np.array([[2, 1, 0, 3, 4, 5, 6, 7, 8, 9]])
    query = {"expected_chunk_ids": ["b", "z"]}
    result = relevance_metrics(ranks, ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"], [query])
    assert result["recall_at_1"] == 0.0
    assert result["recall_at_3"] == 1.0
    assert result["mrr_at_10"] == 0.5
