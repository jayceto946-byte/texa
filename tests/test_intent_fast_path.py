import pytest

from graph.intent_classifier import classify_intent_local, is_fast_path_eligible


@pytest.mark.parametrize("query,intent,shape", [
    ("压阻式和压电式有什么区别？", "comparison", "simple_comparison"),
    ("矩阵的秩怎么算？", "calculation", "simple_calculation"),
    ("解释压阻效应。", "definition", "simple_explanation"),
    ("根据教材解释压阻效应。", "definition", "simple_explanation"),
])
def test_bounded_explicit_queries_use_deterministic_fast_path(query, intent, shape):
    result = classify_intent_local(query)
    assert result["intent"] == intent
    assert result["deterministic_shape"] == shape
    assert is_fast_path_eligible(query, result) is True


def test_multi_constraint_comparison_still_uses_planner():
    query = "比较压阻式和压电式传感器在低频动态测量、长期稳定性和灵敏度方面的差异，并说明选型。"
    result = classify_intent_local(query)
    assert result["intent"] == "comparison"
    assert is_fast_path_eligible(query, result) is False


def test_explicit_multi_entity_comparison_keeps_comparison_intent():
    query = "比较压阻式、压电式和电容式传感器，并分别说明灵敏度、频响、静态测量能力和典型误差来源。"
    result = classify_intent_local(query)
    assert result["intent"] == "comparison"
    assert result["intent_locked"] is True
    assert is_fast_path_eligible(query, result) is False


def test_explanation_with_derivation_still_uses_planner():
    query = "详细解释压阻效应为什么会导致电阻率变化并推导公式。"
    result = classify_intent_local(query)
    assert is_fast_path_eligible(query, result) is False


def test_fast_path_skips_pre_retrieve_vector_chapter_lookup(monkeypatch):
    import graph.main_graph as main_graph
    import graph.safe_retrieval as safe_retrieval

    retrieve_calls = []
    monkeypatch.setattr(
        safe_retrieval,
        "get_safe_vector_store",
        lambda: (_ for _ in ()).throw(AssertionError("duplicate chapter lookup")),
    )
    monkeypatch.setattr(
        main_graph,
        "retrieve_node",
        lambda state: retrieve_calls.append(state["user_input"]) or {
            "chapter_contents": {},
            "retrieval_status": "ok",
            "retrieval_error": "",
        },
    )
    monkeypatch.setattr(main_graph, "_main_graph", None)

    stream = main_graph.run_graph_stream("解释压阻效应。", book_name="传感器短书")
    plan_event = next(stream)
    retrieve_event = next(stream)
    stream.close()

    assert plan_event["fast_path"] is True
    assert plan_event["planner_trace"]["chapter_lookup_skipped"] is True
    assert retrieve_event["stage"] == "retrieve"
    assert retrieve_calls == ["解释压阻效应。"]
