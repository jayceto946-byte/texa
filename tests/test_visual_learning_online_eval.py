from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import evaluation.visual_learning_online_eval as online_eval


class _Context:
    figure = {"figure_id": "figure-1", "book_name": "传感器测试", "page_idx": 0}
    nearby_blocks = [{"block_id": "block-1", "text": "转换元件把被测量转换为电信号。"}]
    related_chunk_ids = ["chunk-1"]

    def to_dict(self):
        return {
            "figure": dict(self.figure),
            "nearby_blocks": list(self.nearby_blocks),
            "related_chunk_ids": list(self.related_chunk_ids),
        }


class _Service:
    def __init__(self, _progress_root):
        pass

    def list_figures(self, _book_name, *, query, limit):
        assert query and limit == 3
        return {"items": [{"figure_id": "figure-1"}]}

    def build_context(self, _book_name, _figure_id):
        return _Context()

    def evidence_sources(self, _context):
        return [
            {"id": "E1", "figure_id": "figure-1", "book_name": "传感器测试", "page_idx": 0},
            {"id": "E2", "block_id": "block-1", "chunk_id": "chunk-1", "text": "转换元件把被测量转换为电信号。"},
        ]

    def asset_path(self, _book_name, _figure_id):
        return Path("unused.jpg")


class _Bridge:
    config = SimpleNamespace(provider=SimpleNamespace(provider_id="qwen"))
    model = "qwen-test"

    def __init__(self, answer="图中包含敏感元件和转换元件。[[cite:E1]] 教材说明转换元件输出电信号。[[cite:E2]]"):
        self.answer = answer

    def iter_figure_answer(self, *_args, **_kwargs):
        yield self.answer


def _gold(*, consistency_mode=""):
    case = {
        "id": "case-1",
        "category": "structure",
        "query": "基本组成",
        "figure_id": "figure-1",
        "page": 1,
        "question": "说明组成。",
        "expected_points": [
            {"label": "敏感元件", "keywords": ["敏感元件"]},
            {"label": "转换元件", "keywords": ["转换元件"]},
        ],
    }
    if consistency_mode:
        case["consistency_mode"] = consistency_mode
    return {
        "schema_version": "visual-learning-gold/v1",
        "book_name": "传感器测试",
        "review": {"human_signoff": False},
        "release_thresholds": {
            "minimum_cases": 1,
            "minimum_retrieval_top3_rate": 1,
            "minimum_model_completion_rate": 1,
            "minimum_source_citation_rate": 1,
            "minimum_verification_pass_rate": 1,
            "minimum_key_point_coverage": 1,
            "maximum_serious_unsupported_claims": 0,
        },
        "cases": [case],
    }


def test_sensor_gold_set_is_review_ready():
    path = Path("evaluation/datasets/visual_learning_sensor_gold.json")
    gold = online_eval.load_visual_gold(path)
    assert len(gold["cases"]) == 24
    assert len({case["id"] for case in gold["cases"]}) == 24
    assert gold["review"]["human_signoff"] is False
    assert any(case["id"] == "sensor-saw-telemetry" for case in gold["cases"])


def test_online_evaluator_scores_sources_points_and_verification(monkeypatch, tmp_path):
    monkeypatch.setattr(online_eval, "FigureLearningService", _Service)
    result = online_eval.evaluate_visual_learning_online(
        _gold(), progress_root=tmp_path, bridge_factory=_Bridge,
    )
    assert result.passed is True
    assert result.report["summary"]["source_citation_rate"] == 1
    assert result.report["summary"]["key_point_coverage"] == 1
    assert result.report["failure_buckets"] == {
        "ingestion": [], "retrieval": [], "model": [], "verification": [],
    }


def test_conflict_case_fails_when_model_does_not_disclose_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(online_eval, "FigureLearningService", _Service)
    result = online_eval.evaluate_visual_learning_online(
        _gold(consistency_mode="expect_conflict_disclosure"),
        progress_root=tmp_path,
        bridge_factory=lambda: _Bridge("图中包含敏感元件和转换元件。[[cite:E1]] [[cite:E2]]"),
    )
    assert result.passed is False
    assert result.report["summary"]["serious_unsupported_claims"] == 1
    assert result.report["failure_buckets"]["model"] == ["case-1"]
