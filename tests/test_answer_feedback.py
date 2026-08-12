import pytest

from backend import conversation_memory
from backend.services import answer_feedback


def test_answer_feedback_binds_versions_and_updates_message_projection(monkeypatch, tmp_path):
    monkeypatch.setattr(conversation_memory, "CONV_DIR", tmp_path / "conversations")
    monkeypatch.setattr(answer_feedback, "ANSWER_FEEDBACK_DB_PATH", tmp_path / "feedback.db")
    message = conversation_memory.append_message(
        "conv-feedback",
        "assistant",
        "回答正文",
        turn_id="t1",
        request_id="req-1",
        context_versions={
            "model_name": "deepseek-v4-pro",
            "prompt_version": "prompt-v3",
            "corpus_version": "book-v1",
        },
    )
    result = answer_feedback.record_answer_feedback(
        conversation_id="conv-feedback",
        message_id=message["id"],
        rating="unhelpful",
        reasons=["forgot_context"],
    )
    assert result["request_id"] == "req-1"
    assert result["versions"]["corpus_version"] == "book-v1"
    assert result["projection_updated"] is True
    stored = conversation_memory.get_message("conv-feedback", message["id"])
    assert stored["answer_feedback"]["rating"] == "unhelpful"
    assert stored["answer_feedback"]["reasons"] == ["forgot_context"]


def test_helpful_feedback_clears_negative_reasons(monkeypatch, tmp_path):
    monkeypatch.setattr(conversation_memory, "CONV_DIR", tmp_path / "conversations")
    monkeypatch.setattr(answer_feedback, "ANSWER_FEEDBACK_DB_PATH", tmp_path / "feedback.db")
    message = conversation_memory.append_message("conv-helpful", "assistant", "回答", turn_id="t1")
    result = answer_feedback.record_answer_feedback(
        conversation_id="conv-helpful",
        message_id=message["id"],
        rating="helpful",
        reasons=["wrong_object"],
    )
    assert result["reasons"] == []


def test_answer_feedback_rejects_unknown_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(conversation_memory, "CONV_DIR", tmp_path / "conversations")
    monkeypatch.setattr(answer_feedback, "ANSWER_FEEDBACK_DB_PATH", tmp_path / "feedback.db")
    message = conversation_memory.append_message("conv-invalid", "assistant", "回答", turn_id="t1")
    with pytest.raises(ValueError, match="unsupported"):
        answer_feedback.record_answer_feedback(
            conversation_id="conv-invalid",
            message_id=message["id"],
            rating="unhelpful",
            reasons=["anything"],
        )


def test_resolver_method_stats_are_feedback_proxies_not_accuracy(monkeypatch):
    monkeypatch.setattr(answer_feedback, "list_answer_feedback", lambda **_kwargs: [
        {"request_id": "r1", "rating": "helpful", "reasons": []},
        {"request_id": "r2", "rating": "unhelpful", "reasons": ["wrong_object"]},
    ])
    import backend.rag_trace as rag_trace
    monkeypatch.setattr(rag_trace, "get_trace_resolver_methods", lambda _ids: {
        "r1": "deterministic_anaphora", "r2": "deterministic_anaphora",
    })

    result = answer_feedback.resolver_method_feedback_stats()

    assert result["metric_kind"] == "user_feedback_proxy_not_calibrated_accuracy"
    assert result["methods"][0]["helpful_rate"] == 0.5
    assert result["methods"][0]["resolver_negative_rate"] == 0.5
    assert result["methods"][0]["routing_decision_ready"] is False
