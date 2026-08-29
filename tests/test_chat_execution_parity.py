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


def test_stream_adapter_preserves_compiled_graph_semantics(monkeypatch):
    import graph.main_graph as main_graph

    updates = [
        {"plan": {"intent": "definition", "target_chapters": ["chapter-1"], "planner_trace": {"mode": "fast_path"}}},
        {"retrieve": {
            "chapter_contents": {"chapter-1": ["context"]},
            "evidence_items": [{"chunk_id": "chunk-1", "text": "context"}],
            "evidence_sources": [{"id": "E1", "chunk_id": "chunk-1"}],
            "evidence_support": {"status": "supported"},
            "retrieval_status": "ok",
        }},
        {"generate": {
            "final_output": "canonical answer",
            "citation_trace": {"status": "model_aligned"},
            "answer_verification": {"status": "passed"},
        }},
        {"feedback": {"linked_concepts": [{"name": "压阻效应"}]}},
    ]

    class FakeCompiledGraph:
        def invoke(self, initial_state):
            state = dict(initial_state)
            for update in updates:
                state.update(next(iter(update.values())))
            return state

        def stream(self, initial_state, *, stream_mode):
            assert stream_mode == ["messages", "updates"]
            for update in updates:
                yield "updates", update

    graph = FakeCompiledGraph()
    monkeypatch.setattr(main_graph, "get_graph", lambda: graph)

    sync = main_graph.run_graph("解释压阻效应。", book_name="demo-book")
    events = list(main_graph.run_graph_stream("解释压阻效应。", book_name="demo-book"))
    streamed = events[-1]["state"]
    semantic_keys = (
        "intent", "target_chapters", "retrieval_status", "evidence_support",
        "evidence_sources", "final_output", "citation_trace", "answer_verification",
        "linked_concepts",
    )

    assert {key: streamed.get(key) for key in semantic_keys} == {
        key: sync.get(key) for key in semantic_keys
    }
