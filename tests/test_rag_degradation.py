class DummyChunk:
    def __init__(self, content: str):
        self.content = content


class DummyLLM:
    def stream(self, prompt: str):
        yield DummyChunk("answer")


class EmptyVectorStore:
    available = True

    def get_chapter_names(self):
        return []

    def search_all(self, *args, **kwargs):
        from ingestion.vector_store import RetrievalOutcome
        return RetrievalOutcome(items={})

    def search_chapter(self, *args, **kwargs):
        from ingestion.vector_store import RetrievalOutcome
        return RetrievalOutcome(items=[])


class FailedVectorStore:
    available = True

    def search_all(self, *args, **kwargs):
        from ingestion.vector_store import RetrievalFailure, RetrievalOutcome
        return RetrievalOutcome.failed({}, RetrievalFailure(
            backend="chroma",
            operation="search_all",
            scope="demo-book",
            error_code="collection_listing_failed",
        ))


class BrokenKG:
    def search_concept(self, *args, **kwargs):
        raise RuntimeError("kg query failed")


def _use_fast_path(monkeypatch):
    import config
    import graph.feedback_node as feedback_module
    import graph.intent_classifier as intent_module

    monkeypatch.setattr(intent_module, "classify_intent_local", lambda text: {"intent": "definition", "hint": "local"})
    monkeypatch.setattr(intent_module, "is_fast_path_eligible", lambda text, result: True)
    monkeypatch.setattr(config, "get_llm", lambda: DummyLLM())
    monkeypatch.setattr(feedback_module, "feedback_node", lambda state: {})


def _assert_degraded_stream(events, expected_error: str):
    stages = [event["stage"] for event in events]
    assert stages[0] == "plan"
    assert stages[1] == "retrieve"
    assert "generate" in stages
    assert stages[-1] == "done"
    retrieve = events[1]
    assert retrieve["retrieval_status"] == "degraded"
    assert expected_error in retrieve["retrieval_error"]


def test_stream_degrades_when_vector_store_initialization_fails(monkeypatch):
    import ingestion.vector_store as vector_module
    import graph.retrieval_node as retrieval_module
    import graph.safe_retrieval as safe_retrieval
    from graph.main_graph import run_graph_stream

    _use_fast_path(monkeypatch)
    monkeypatch.setattr(vector_module, "get_vector_store", lambda: (_ for _ in ()).throw(RuntimeError("vector boom")))
    monkeypatch.setattr(retrieval_module, "get_safe_kg", lambda book_name: (safe_retrieval.SafeKG(), ""))

    events = list(run_graph_stream("what is derivative", book_name="demo-book"))

    _assert_degraded_stream(events, "vector boom")


def test_stream_degrades_when_kg_loading_fails(monkeypatch):
    import ingestion.vector_store as vector_module
    import knowledge.knowledge_graph as kg_module
    from graph.main_graph import run_graph_stream

    _use_fast_path(monkeypatch)
    monkeypatch.setattr(vector_module, "get_vector_store", lambda: EmptyVectorStore())
    monkeypatch.setattr(kg_module, "get_kg", lambda book_name: (_ for _ in ()).throw(ValueError("kg json corrupt")))

    events = list(run_graph_stream("what is derivative", book_name="demo-book"))

    _assert_degraded_stream(events, "kg json corrupt")


def test_retrieval_distinguishes_healthy_empty_result(monkeypatch):
    import graph.retrieval_node as retrieval_module
    import graph.safe_retrieval as safe_retrieval

    monkeypatch.setattr(retrieval_module, "get_safe_kg", lambda _book: (safe_retrieval.SafeKG(), ""))
    result = retrieval_module.retrieve_node(
        {
            "user_input": "no matching evidence",
            "book_name": "demo-book",
            "intent": "qa",
            "use_textbook_context": True,
        },
        vector_store=EmptyVectorStore(),
        lexical_search=lambda *_args, **_kwargs: [],
        neighbor_expander=lambda *_args, **_kwargs: [],
    )

    assert result["retrieval_status"] == "ok"
    assert result["evidence_support"]["status"] == "insufficient"
    assert result["retrieval_error"] == ""


def test_retrieval_keeps_healthy_lexical_results_when_dense_fails(monkeypatch):
    import graph.retrieval_node as retrieval_module

    monkeypatch.setattr(
        retrieval_module,
        "get_safe_kg",
        lambda _book: (BrokenKG(), "knowledge graph unavailable"),
    )
    lexical_item = {
        "chunk_id": "lexical-1",
        "chapter": "第一章",
        "section_title": "定义",
        "text": "导数描述函数的瞬时变化率。",
        "source": "bm25",
        "score": 1.0,
    }
    result = retrieval_module.retrieve_node(
        {
            "user_input": "导数是什么",
            "book_name": "demo-book",
            "intent": "definition",
            "use_textbook_context": True,
        },
        vector_store=FailedVectorStore(),
        lexical_search=lambda *_args, **_kwargs: [dict(lexical_item)],
        neighbor_expander=lambda *_args, **_kwargs: [],
    )

    assert result["retrieval_status"] == "degraded"
    assert "collection_listing_failed" in result["retrieval_error"]


def test_retrieval_marks_actual_all_backend_failure_unavailable(monkeypatch):
    import graph.retrieval_node as retrieval_module

    monkeypatch.setattr(
        retrieval_module,
        "get_safe_kg",
        lambda _book: (BrokenKG(), "knowledge graph unavailable"),
    )

    def fail_lexical(*_args, **_kwargs):
        raise OSError("lexical index unreadable")

    result = retrieval_module.retrieve_node(
        {
            "user_input": "导数是什么",
            "book_name": "demo-book",
            "intent": "definition",
            "use_textbook_context": True,
        },
        vector_store=FailedVectorStore(),
        lexical_search=fail_lexical,
        neighbor_expander=lambda *_args, **_kwargs: [],
    )

    assert result["retrieval_status"] == "unavailable"
    assert result["evidence_support"] == {
        "status": "unavailable",
        "reason": "retrieval_backends_failed",
    }
    assert "lexical index unreadable" in result["retrieval_error"]
