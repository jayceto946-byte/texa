from __future__ import annotations


def test_canonical_planner_owns_deterministic_fast_path(monkeypatch):
    import graph.safe_retrieval as safe_retrieval
    from graph.planner import plan_node

    monkeypatch.setattr(
        safe_retrieval,
        "get_safe_vector_store",
        lambda: (_ for _ in ()).throw(AssertionError("fast path queried vector store")),
    )

    result = plan_node({
        "user_input": "解释压阻效应。",
        "target_chapters": [],
        "use_textbook_context": True,
        "retrieval_status": "ok",
        "retrieval_error": "",
    })

    assert result["intent"] == "definition"
    assert result["planner_trace"]["mode"] == "fast_path"
    assert result["planner_trace"]["chapter_lookup_skipped"] is True


def test_canonical_planner_uses_local_intent_for_general_qa(monkeypatch):
    import graph.safe_retrieval as safe_retrieval
    from graph.planner import plan_node

    monkeypatch.setattr(
        safe_retrieval,
        "get_safe_vector_store",
        lambda: (_ for _ in ()).throw(AssertionError("general QA queried vector store")),
    )

    result = plan_node({
        "user_input": "矩阵的秩怎么算？",
        "target_chapters": [],
        "use_textbook_context": False,
        "retrieval_status": "ordinary_qa",
        "retrieval_error": "",
    })

    assert result["intent"] == "calculation"
    assert result["planner_trace"]["mode"] == "fast_path"
