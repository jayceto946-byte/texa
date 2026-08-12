import json
import sys

from evaluation import context_eval_v3
from evaluation.context_eval_v3 import evaluate


def _dataset(tmp_path):
    path = tmp_path / "context-production.jsonl"
    path.write_text(json.dumps({
        "schema_version": 1,
        "id": "production-1",
        "status": "approved",
        "history": [
            {"role": "user", "content": "什么是压阻效应？", "turn_id": "t1"},
            {"role": "assistant", "content": "压阻效应与电阻率变化有关。", "turn_id": "t1"},
        ],
        "query": "再简要解释一下",
        "book_name": "测试教材",
        "intent": "definition",
        "expected": {
            "resolved_query_contains": ["压阻效应"],
            "required_evidence_points": ["受力", "电阻率"],
            "retrieval_action": "full",
            "context_turn_ids": ["t1"],
            "required_answer_points": ["受力", "电阻率"],
            "forbidden_answer_terms": ["霍尔效应"],
            "require_citations": True,
        },
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _retrieval(_state):
    return {
        "evidence_items": [{
            "chunk_id": "chunk-1", "chapter": "第一章", "section_title": "定义",
            "text": "压阻效应是材料受力后电阻率发生变化的现象。",
        }],
        "chapter_contents": {},
        "retrieval_action": "full",
        "retrieval_status": "ok",
        "retrieval_error": "",
        "evidence_support": {"status": "supported"},
        "new_evidence_ids": ["chunk-1"],
        "reused_evidence_ids": [],
        "dropped_evidence_ids": [],
        "evidence_gate_applied": True,
    }


def test_context_eval_v3_uses_production_state_without_live_model(tmp_path):
    report = evaluate(_dataset(tmp_path), retrieval_runner=_retrieval)
    assert report["modes"]["answer"] == "disabled_no_model_call"
    assert report["layers"]["retrieval"]["passed"] == 1
    assert report["release_gates"]["passed"] is True


def test_context_eval_v3_scores_opt_in_live_answer(tmp_path):
    report = evaluate(
        _dataset(tmp_path), online=True, retrieval_runner=_retrieval,
        answer_runner=lambda _state: "材料受力后电阻率变化。[[cite:E1]]",
    )
    assert report["layers"]["answer"]["passed"] == 1
    assert report["release_gates"]["passed"] is True


def test_context_eval_v3_accepts_answer_alternatives_and_list_punctuation(tmp_path):
    path = _dataset(tmp_path)
    case = json.loads(path.read_text(encoding="utf-8"))
    case["expected"]["required_answer_points"] = [
        ["静电引力很小", "静电引力极小"], "高低温",
    ]
    path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")

    report = evaluate(
        path, online=True, retrieval_runner=_retrieval,
        answer_runner=lambda _state: "静电引力极小，可用于高、低温环境。[[cite:E1]]",
    )
    assert report["layers"]["answer"]["passed"] == 1


def test_context_eval_v3_does_not_treat_negated_forbidden_term_as_drift(tmp_path):
    path = _dataset(tmp_path)
    case = json.loads(path.read_text(encoding="utf-8"))
    case["expected"]["required_answer_points"] = ["响应频率低"]
    case["expected"]["forbidden_answer_terms"] = ["适合高频动态测量"]
    path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")

    report = evaluate(
        path, online=True, retrieval_runner=_retrieval,
        answer_runner=lambda _state: "响应频率低，不适合高频动态测量。[[cite:E1]]",
    )
    assert report["answer_details"][0]["checks"]["no_drift"] is True
    assert report["layers"]["answer"]["passed"] == 1


def test_context_eval_v3_records_live_model_failure_without_losing_report(tmp_path):
    def fail(_state):
        raise ConnectionError("offline")

    report = evaluate(
        _dataset(tmp_path), online=True, retrieval_runner=_retrieval,
        answer_runner=fail,
    )
    assert report["layers"]["retrieval"]["passed"] == 1
    assert report["layers"]["answer"]["failed"] == 1
    assert "ConnectionError" in report["answer_details"][0]["error"]
    assert report["release_gates"]["passed"] is False


def test_context_eval_v3_persists_report_before_console_encoding_failure(
    tmp_path, monkeypatch,
):
    report = {
        "release_gates": {"passed": True},
        "answer_details": [{"answer": "x²"}],
    }
    target = tmp_path / "report.json"
    calls = []

    def flaky_print(value):
        calls.append(value)
        if len(calls) == 1:
            raise UnicodeEncodeError("gbk", "²", 0, 1, "unsupported")

    monkeypatch.setattr(context_eval_v3, "evaluate", lambda *_args, **_kwargs: report)
    monkeypatch.setattr("builtins.print", flaky_print)
    monkeypatch.setattr(sys, "argv", [
        "context_eval_v3", "unused.jsonl", "--output", str(target),
    ])

    assert context_eval_v3.main() == 0
    assert json.loads(target.read_text(encoding="utf-8")) == report
    assert len(calls) == 2
