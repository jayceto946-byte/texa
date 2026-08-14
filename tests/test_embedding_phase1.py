from evaluation.embedding_backend.phase1_worker import (
    bucket_plan,
    contiguous_plan,
    plan_padding,
    sorted_plan,
)


def test_length_sorted_plan_reduces_padding_without_losing_indices():
    lengths = [10, 500, 20, 490]
    naive = contiguous_plan(len(lengths), 2)
    ordered = sorted_plan(lengths, 2)

    assert sorted(index for batch in ordered for index in batch) == [0, 1, 2, 3]
    assert plan_padding(lengths, ordered)["padding_ratio"] < plan_padding(lengths, naive)["padding_ratio"]


def test_bucket_plan_uses_expected_token_boundaries_and_preserves_indices():
    lengths = [64, 65, 128, 129, 256, 257, 512]
    plan = bucket_plan(lengths, batch_size=2)

    assert plan == [[0], [1, 2], [3, 4], [5, 6]]
    assert sorted(index for batch in plan for index in batch) == list(range(len(lengths)))


def test_padding_metrics_distinguish_ratio_and_waste_fraction():
    metrics = plan_padding([10, 20], [[0, 1]])

    assert metrics["total_real_tokens"] == 30
    assert metrics["total_padded_tokens"] == 40
    assert metrics["padding_ratio"] == 4 / 3
    assert metrics["padding_waste_fraction"] == 0.25
