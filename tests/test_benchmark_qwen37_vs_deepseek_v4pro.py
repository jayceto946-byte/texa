import json

from scripts.benchmark_qwen37_vs_deepseek_v4pro import (
    _result_log_path,
    rebuild_report_from_log,
)


def test_rebuild_keeps_same_case_id_in_different_groups(tmp_path):
    output = tmp_path / "benchmark.json"
    fixture = {
        "controls": {"repeats": 1},
        "cases": [
            {"id": "same-id", "group": "A_textbook_rag", "model_call": True},
            {"id": "same-id", "group": "B_conversation", "model_call": True},
        ],
    }
    rows = [
        {
            "case_id": "same-id", "group": group, "model": model,
            "repeat": 1, "elapsed_seconds": 1.0, "ttft_seconds": 0.1,
            "usage": {}, "cost": {}, "answer": "ok", "score": {"answer_chars": 2},
        }
        for group in ("A_textbook_rag", "B_conversation")
        for model in ("deepseek-v4-pro", "qwen3.7-plus")
    ]
    output.write_text(json.dumps({
        "status": "running", "fixture": fixture, "results": [], "vision_results": [],
    }), encoding="utf-8")
    _result_log_path(output).write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8",
    )

    report = rebuild_report_from_log(output)

    assert report["status"] == "complete"
    assert len(report["results"]) == 4
    assert report["rebuild"]["missing"] == []
