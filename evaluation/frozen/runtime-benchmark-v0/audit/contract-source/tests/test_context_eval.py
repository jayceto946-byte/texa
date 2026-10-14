import json
from collections import Counter

from evaluation.context_eval import (
    DEFAULT_DATASET,
    DEFAULT_LAYER_DATASET,
    _release_gates,
    _score_answer_layer,
    aggregate,
    evaluate,
    load_cases,
    load_layer_cases,
    score_case,
)


def test_context_eval_scores_resolution_references_and_state():
    case = {
        "id": "property",
        "history": [
            {"role": "user", "content": "讲一下压阻效应。", "turn_id": "t1"},
            {"role": "assistant", "content": "回答", "turn_id": "t1"},
        ],
        "query": "性质呢？",
        "expected": {
            "resolved_query": "压阻效应有什么性质？",
            "is_followup": True,
            "referenced_entities": ["压阻效应"],
            "speech_act": "followup",
            "state_operations": [],
            "state_after": {"topic": "压阻效应", "intent": "property"},
        },
        "tags": ["core"],
    }

    result = score_case(case)

    assert result["passed"] is True
    assert all(result["checks"].values())
    assert result["actual"]["referenced_turn_ids"] == ["t1"]
    assert result["actual"]["speech_act"] == "followup"


def test_context_eval_aggregates_failures_and_tags():
    details = [
        {"passed": True, "checks": {"resolution": True}, "tags": ["core"]},
        {"passed": False, "checks": {"resolution": False}, "tags": ["core", "known_gap"]},
    ]

    summary = aggregate(details)

    assert summary["cases"] == 2
    assert summary["pass_rate"] == 0.5
    assert summary["metrics"]["resolution"] == 0.5
    assert summary["by_tag"]["core"]["pass_rate"] == 0.5
    assert summary["by_tag"]["known_gap"]["pass_rate"] == 0.0


def test_context_eval_loads_starter_multiturn_dataset():
    cases = load_cases(DEFAULT_DATASET)

    assert len(cases) == 100
    tags = {tag for case in cases for tag in case.get("tags", [])}
    assert {
        "standalone", "assistant_artifact", "constraint", "ordinal", "known_gap",
        "long_20", "long_40", "long_80", "book_switch", "subject_switch",
        "evidence_reuse", "evidence_delta", "retrieval_full", "no_retrieval",
        "clarification",
    } <= tags
    counts = Counter(tag for case in cases for tag in case.get("tags", []))
    assert counts["anaphora"] >= 10
    assert counts["ordinal"] >= 10
    assert counts["comparison"] >= 10
    assert counts["constraint"] >= 4
    assert counts["assistant_artifact"] >= 15
    assert counts["topic_return"] >= 5
    assert counts["user_correction"] >= 4
    assert counts["standalone"] >= 9
    assert counts["clarification"] >= 3
    assert counts["scope"] >= 8
    assert counts["retrieval_policy"] >= 10

    by_id = {case["id"]: case for case in cases}
    assert by_id["long20_first_reference"]["history_turn_count"] == 20
    assert by_id["long40_recent_anaphora"]["history_turn_count"] == 40
    assert by_id["long80_standalone"]["history_turn_count"] == 80


def test_context_eval_implements_reuse_policy():
    case = {
        "id": "reuse",
        "history": [
            {"role": "user", "content": "什么是压阻效应？", "turn_id": "t1"},
            {"role": "assistant", "content": "回答", "turn_id": "t1"},
        ],
        "query": "再简要解释一下。",
        "context": {
            "use_textbook_context": True,
            "active_evidence_ids": ["chunk-1"],
            "active_evidence_support": "supported",
            "same_topic": True,
            "requires_new_facet": False,
            "intent": "definition",
        },
        "expected": {"retrieval_action": "reuse"},
        "tags": ["evidence_reuse", "known_gap"],
    }

    result = score_case(case)

    assert result["actual"]["retrieval_action"] == "reuse"
    assert result["checks"]["retrieval_action"] is True
    assert result["passed"] is True


def test_context_eval_implements_clarification_action():
    cases = {case["id"]: case for case in load_cases(DEFAULT_DATASET)}

    result = score_case(cases["ambiguous_former_without_pair"])

    assert result["expected"]["resolution_action"] == "clarify"
    assert result["actual"]["resolution_action"] == "clarify"
    assert result["checks"]["resolution_action"] is True


def test_context_eval_guards_new_context_capabilities():
    report = evaluate(DEFAULT_DATASET)
    by_tag = report["summary"]["by_tag"]

    assert by_tag["assistant_artifact"]["pass_rate"] == 1.0
    assert by_tag["clarification"]["pass_rate"] == 1.0
    assert by_tag["evidence_reuse"]["pass_rate"] == 1.0
    assert by_tag["evidence_delta"]["pass_rate"] == 1.0
    assert report["layers"]["resolver"]["pass_rate"] >= 0.80
    assert report["layers"]["retrieval"] == {
        "cases": 12,
        "passed": 12,
        "failed": 0,
        "pass_rate": 1.0,
        "metrics": report["layers"]["retrieval"]["metrics"],
    }
    assert report["layers"]["answer"]["cases"] == 12
    assert report["layers"]["answer"]["pass_rate"] == 1.0
    assert report["release_gates"]["passed"] is True
    assert all(report["release_gates"]["checks"].values())


def test_context_eval_layer_dataset_has_release_coverage():
    cases = load_layer_cases(DEFAULT_LAYER_DATASET)

    assert len(cases) >= 10
    assert all(isinstance(case.get("retrieval"), dict) for case in cases)
    assert all(isinstance(case.get("answer"), dict) for case in cases)


def test_answer_layer_rejects_wrong_object_constraint_drift_and_repetition():
    base_case = {"id": "correction"}
    layer_case = {
        "id": "bad-answer",
        "answer": {
            "text": "低频测量应选择压阻效应。低频测量应选择压阻效应。",
            "expected": {
                "required_objects": ["压电效应"],
                "required_constraints": ["高频测量"],
                "forbidden_terms": ["低频测量", "压阻效应"],
                "max_sentence_repeats": 1,
            },
        },
    }

    result = _score_answer_layer(base_case, layer_case)

    assert result["passed"] is False
    assert result["evaluation_mode"] == "offline_answer_snapshot_contract"
    assert result["checks"] == {
        "correct_object": False,
        "inherited_constraints": False,
        "no_drift": False,
        "no_repetition": False,
    }


def test_release_gates_do_not_hide_independent_long_session_failure():
    report = evaluate(DEFAULT_DATASET)
    degraded_resolver = dict(report["layers"]["resolver"])
    degraded_resolver["by_tag"] = dict(degraded_resolver["by_tag"])
    degraded_resolver["by_tag"]["long_80"] = {
        "cases": 4, "passed": 3, "pass_rate": 0.75,
    }

    gates = _release_gates(
        degraded_resolver,
        report["layers"]["retrieval"],
        report["layers"]["answer"],
    )

    assert gates["checks"]["resolver_overall"] is True
    assert gates["checks"]["long_80"] is False
    assert gates["passed"] is False


def test_context_eval_scores_no_retrieval_and_scope_change():
    case = {
        "id": "scope",
        "history": [],
        "query": "什么是矩阵的秩？",
        "context": {
            "use_textbook_context": False,
            "previous_book_name": "传感器教材",
            "book_name": "线性代数教材",
            "previous_subject": "专业课",
            "subject": "数学",
            "intent": "definition",
        },
        "expected": {
            "retrieval_action": "none",
            "retrieval_query": "",
            "scope_changed": True,
        },
        "tags": ["no_retrieval", "book_switch"],
    }

    result = score_case(case)

    assert result["passed"] is True
    assert result["actual"]["scope_changed"] is True


def test_context_eval_writes_machine_readable_report_shape(tmp_path):
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(json.dumps({
        "id": "standalone",
        "history": [],
        "query": "什么是导数？",
        "expected": {
            "resolved_query": "什么是导数？",
            "is_followup": False,
            "referenced_entities": [],
        },
        "tags": ["standalone"],
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    report = evaluate(dataset)

    assert report["schema_version"] == 2
    assert report["summary"]["passed"] == 1
    assert report["layers"]["retrieval"]["cases"] == 0
    assert report["layers"]["answer"]["cases"] == 0
    assert report["release_gates"]["passed"] is True
    assert report["failures"] == []
