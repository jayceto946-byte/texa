from types import SimpleNamespace

import graph.planner as planner
import graph.safe_retrieval as safe_retrieval
from ingestion.vector_store import RetrievalOutcome


class _VectorStore:
    def get_chapter_names(self, book_name=""):
        return ["第一章", "第二章"]

    def search_all(self, question, k=1, book_name=""):
        return RetrievalOutcome(items={"第一章": ["content"]})


class _PlannerLlm:
    model_name = "planner-model"

    def invoke(self, prompt, config=None):
        for callback in (config or {}).get("callbacks", []):
            callback.on_llm_new_token("{")
        return SimpleNamespace(
            content='{"intent":"comparison","target_chapters":["第一章"],"sub_tasks":[]}',
            usage_metadata={
                "input_tokens": 120,
                "output_tokens": 18,
                "total_tokens": 138,
                "output_token_details": {"reasoning": 7},
            },
            response_metadata={
                "model_name": "planner-model",
                "finish_reason": "stop",
                "headers": {
                    "x-stainless-retry-count": "1",
                    "x-request-id": "req-test",
                },
            },
        )


def test_plan_node_records_bounded_internal_telemetry(monkeypatch):
    monkeypatch.setattr(safe_retrieval, "get_safe_vector_store", lambda: (_VectorStore(), ""))
    monkeypatch.setattr(planner, "get_llm", lambda **kwargs: _PlannerLlm())

    result = planner.plan_node({
        "user_input": "比较甲和乙",
        "book_name": "demo",
        "use_textbook_context": True,
        "_local_intent": "comparison",
        "_local_intent_hint": "comparison",
        "retrieval_status": "ok",
        "retrieval_error": "",
    })

    trace = result["planner_trace"]
    assert result["intent"] == "comparison"
    assert trace["mode"] == "llm"
    assert trace["model"] == "planner-model"
    assert trace["input_tokens"] == 120
    assert trace["reasoning_tokens"] == 7
    assert trace["finish_reason"] == "stop"
    assert trace["retry_count"] == 1
    assert trace["request_id"] == "req-test"
    assert trace["first_token_ms"] is not None
    assert trace["api_response_elapsed_ms"] is not None
    assert trace["plan_total_ms"] >= trace["api_response_elapsed_ms"]


def test_plan_node_general_qa_bypass_does_not_create_llm(monkeypatch):
    monkeypatch.setattr(planner, "get_llm", lambda **kwargs: (_ for _ in ()).throw(AssertionError("LLM called")))
    result = planner.plan_node({
        "user_input": "Transformer 的 QKV 是什么？",
        "use_textbook_context": False,
        "_local_intent": "qa",
    })
    assert result["intent"] == "qa"
    assert result["planner_trace"]["mode"] == "general_qa_bypass"


def test_plan_node_cannot_override_locked_explicit_intent(monkeypatch):
    class WrongIntentLlm(_PlannerLlm):
        def invoke(self, prompt, config=None):
            response = super().invoke(prompt, config=config)
            response.content = '{"intent":"factual_recall","target_chapters":["第一章"],"sub_tasks":[]}'
            return response

    monkeypatch.setattr(safe_retrieval, "get_safe_vector_store", lambda: (_VectorStore(), ""))
    monkeypatch.setattr(planner, "get_llm", lambda **kwargs: WrongIntentLlm())

    result = planner.plan_node({
        "user_input": "比较甲、乙和丙，并分别说明性质。",
        "book_name": "demo",
        "use_textbook_context": True,
        "_local_intent": "comparison",
        "_local_intent_hint": "explicit comparison",
        "_local_intent_locked": True,
    })

    assert result["intent"] == "comparison"
    assert result["planner_trace"]["intent_locked"] is True
