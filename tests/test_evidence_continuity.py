from backend.services.evidence_continuity import build_evidence_continuity_context
from graph.retrieval_node import retrieve_node
from graph.retrieval_policy import decide_retrieval_action


def _history_with_source():
    return [
        {"role": "user", "content": "什么是压阻效应？", "turn_id": "t1"},
        {
            "role": "assistant",
            "content": "回答",
            "turn_id": "t1",
            "book_name": "传感器教材",
            "subject": "专业课/传感器",
            "sources": [{
                "chunk_id": "chunk-definition",
                "book_name": "传感器教材",
                "chapter": "第一章",
                "section_title": "压阻效应",
            }],
        },
    ]


def test_continuity_context_reuses_rephrased_same_facet():
    trace = {
        "raw_query": "再简要解释一下。",
        "is_followup": True,
        "state_before": {"topic": "压阻效应", "intent": "definition"},
        "state_after": {"topic": "压阻效应", "intent": "explanation"},
    }

    context = build_evidence_continuity_context(
        _history_with_source(), trace,
        book_name="传感器教材", subject="专业课/传感器",
    )

    assert context["active_evidence_ids"] == ["chunk-definition"]
    assert context["same_topic"] is True
    assert context["requires_new_facet"] is False
    assert decide_retrieval_action({"use_textbook_context": True, **context}) == "reuse"


def test_continuity_context_uses_delta_for_new_facet():
    trace = {
        "raw_query": "它有哪些缺点？",
        "is_followup": True,
        "state_before": {"topic": "压阻效应", "intent": "definition"},
        "state_after": {"topic": "压阻效应", "intent": "property"},
    }

    context = build_evidence_continuity_context(
        _history_with_source(), trace,
        book_name="传感器教材", subject="专业课/传感器",
    )

    assert context["requires_new_facet"] is True
    assert decide_retrieval_action({"use_textbook_context": True, **context}) == "delta"


def test_partial_previous_support_forces_delta_even_for_same_facet():
    history = _history_with_source()
    history[-1]["evidence_support_status"] = "partial"
    trace = {
        "raw_query": "再解释一次。",
        "is_followup": True,
        "state_before": {"topic": "压阻效应", "intent": "definition"},
        "state_after": {"topic": "压阻效应", "intent": "definition"},
    }

    context = build_evidence_continuity_context(
        history, trace, book_name="传感器教材", subject="专业课/传感器",
    )

    assert context["active_evidence_support"] == "partial"
    assert decide_retrieval_action({"use_textbook_context": True, **context}) == "delta"


def test_changed_corpus_version_invalidates_previous_evidence(monkeypatch):
    import backend.services.context_versions as versions

    history = _history_with_source()
    history[-1]["context_versions"] = {"corpus_version": "book-v1"}
    monkeypatch.setattr(
        versions,
        "current_context_versions",
        lambda _book: {"corpus_version": "book-v2"},
    )
    trace = {
        "raw_query": "再解释一次。",
        "is_followup": True,
        "state_before": {"topic": "压阻效应", "intent": "definition"},
        "state_after": {"topic": "压阻效应", "intent": "definition"},
    }
    context = build_evidence_continuity_context(
        history, trace, book_name="传感器教材", subject="专业课/传感器",
    )
    assert context["corpus_version_matches"] is False
    assert context["same_topic"] is False
    assert context["active_evidence_invalidation_reason"] == "corpus_version_changed"
    assert decide_retrieval_action({"use_textbook_context": True, **context}) == "full"


def test_active_evidence_exposes_version_fingerprint_and_scope(monkeypatch):
    import backend.services.context_versions as versions

    history = _history_with_source()
    history[-1]["context_versions"] = {"corpus_version": "book-v1"}
    history[-1]["sources"][0].update({
        "book_id": "book-id-1",
        "corpus_version": "book-v1",
        "content_fingerprint": "sha256-1",
    })
    monkeypatch.setattr(
        versions, "current_context_versions", lambda _book: {"corpus_version": "book-v1"},
    )
    trace = {
        "raw_query": "再解释一次。", "is_followup": True,
        "state_before": {"topic": "压阻效应", "intent": "definition"},
        "state_after": {"topic": "压阻效应", "intent": "definition"},
    }
    context = build_evidence_continuity_context(
        history, trace, book_name="传感器教材", subject="专业课/传感器",
    )

    source = context["active_evidence_sources"][0]
    assert source["book_id"] == "book-id-1"
    assert source["corpus_version"] == "book-v1"
    assert source["content_fingerprint"] == "sha256-1"
    assert context["active_evidence_scope"]["chapters"] == ["第一章"]
    assert context["active_evidence_invalidation_reason"] == ""


def test_retrieve_node_reuses_hydrated_evidence_without_search(monkeypatch):
    import graph.retrieval_node as module

    monkeypatch.setattr(module, "resolve_retrieval_resources", lambda *args: [{
        "book_name": "传感器教材", "is_primary": True, "role": "core", "priority": 1.0,
    }])
    monkeypatch.setattr(module, "expand_neighbors", lambda book, ids, window=0: [{
        "chunk_id": "chunk-definition", "chapter": "第一章", "content": "压阻效应定义正文。",
    }])
    monkeypatch.setattr(module, "get_safe_vector_store", lambda: (_ for _ in ()).throw(
        AssertionError("reuse must not initialize vector retrieval")
    ))

    result = retrieve_node({
        "user_input": "再简要解释压阻效应。",
        "book_name": "传感器教材",
        "subject": "专业课/传感器",
        "intent": "definition",
        "target_chapters": [],
        "use_textbook_context": True,
        "active_evidence_ids": ["chunk-definition"],
        "active_evidence_sources": [{"chunk_id": "chunk-definition", "book_name": "传感器教材"}],
        "active_evidence_support": "supported",
        "same_topic": True,
        "requires_new_facet": False,
    })

    assert result["retrieval_action"] == "reuse"
    assert result["retrieval_query"] == ""
    assert result["reused_evidence_ids"] == ["chunk-definition"]
    assert result["evidence_items"][0]["text"] == "压阻效应定义正文。"


def test_changed_chunk_fingerprint_blocks_reuse(monkeypatch):
    import graph.retrieval_node as module

    monkeypatch.setattr(module, "resolve_retrieval_resources", lambda *args: [{
        "book_name": "传感器教材", "is_primary": True, "role": "core", "priority": 1.0,
    }])
    monkeypatch.setattr(module, "expand_neighbors", lambda book, ids, window=0: [{
        "chunk_id": "chunk-definition", "chapter": "第一章", "content": "已被替换的新正文。",
    }])
    monkeypatch.setattr(module, "get_safe_vector_store", lambda: (object(), ""))
    monkeypatch.setattr(module, "get_safe_kg", lambda _book: (type("KG", (), {"_is_local": False})(), ""))
    monkeypatch.setattr(module, "_kg_precise_retrieval", lambda *args, **kwargs: ([], []))
    monkeypatch.setattr(module, "search_book", lambda *args, **kwargs: [])
    monkeypatch.setattr(module, "_vector_retrieval", lambda *args, **kwargs: [])
    monkeypatch.setattr(module, "_merge_and_rerank", lambda *args, **kwargs: ({}, []))
    monkeypatch.setattr(module, "_load_history", lambda *args: [])
    monkeypatch.setattr(module, "_assess_evidence_support", lambda *args, **kwargs: {
        "status": "insufficient", "reason": "test",
    })

    result = retrieve_node({
        "user_input": "再解释一次。", "book_name": "传感器教材",
        "subject": "专业课/传感器", "intent": "definition",
        "target_chapters": [], "use_textbook_context": True,
        "active_evidence_ids": ["chunk-definition"],
        "active_evidence_sources": [{
            "chunk_id": "chunk-definition", "book_name": "传感器教材",
            "content_fingerprint": "old-fingerprint",
        }],
        "active_evidence_support": "supported", "same_topic": True,
        "requires_new_facet": False,
    })

    assert result["retrieval_action"] == "full"
    assert result["reused_evidence_ids"] == []
    assert "continuity_fingerprint" in result["retrieval_error"]


def test_retrieve_node_delta_combines_old_and_new_evidence(monkeypatch):
    import graph.retrieval_node as module

    class DummyKG:
        _is_local = True

        def get_concept_detail(self, name):
            return None

    monkeypatch.setattr(module, "resolve_retrieval_resources", lambda *args: [{
        "book_name": "传感器教材", "is_primary": True, "is_selected": True,
        "role": "core", "priority": 1.0,
    }])
    monkeypatch.setattr(module, "expand_neighbors", lambda book, ids, window=0: [{
        "chunk_id": ids[0], "chapter": "第一章",
        "content": "压阻效应定义正文。" if ids[0] == "chunk-definition" else "压阻效应缺点正文。",
    }] if ids else [])
    monkeypatch.setattr(module, "get_safe_vector_store", lambda: (object(), ""))
    monkeypatch.setattr(module, "get_safe_kg", lambda book: (DummyKG(), ""))
    monkeypatch.setattr(module, "_kg_precise_retrieval", lambda *args, **kwargs: ([], []))
    monkeypatch.setattr(module, "search_book", lambda *args, **kwargs: [{
        "chunk_id": "chunk-property", "chapter": "第一章", "text": "压阻效应缺点正文。",
        "content": "压阻效应缺点正文。", "is_direct_hit": True, "query_coverage": 1.0,
    }])
    monkeypatch.setattr(module, "_vector_retrieval", lambda *args, **kwargs: [])
    monkeypatch.setattr(module, "_merge_and_rerank", lambda *args, **kwargs: ({
        "第一章": ["压阻效应缺点正文。"],
    }, [{
        "chunk_id": "chunk-property", "chapter": "第一章", "text": "压阻效应缺点正文。",
        "is_direct_hit": True, "query_coverage": 1.0,
    }]))
    monkeypatch.setattr(module, "_load_history", lambda *args: [])
    monkeypatch.setattr(module, "_assess_evidence_support", lambda *args, **kwargs: {
        "status": "supported", "reason": "test",
    })

    result = retrieve_node({
        "user_input": "压阻效应有哪些缺点？",
        "book_name": "传感器教材",
        "subject": "专业课/传感器",
        "intent": "property",
        "target_chapters": [],
        "use_textbook_context": True,
        "active_evidence_ids": ["chunk-definition"],
        "active_evidence_sources": [{"chunk_id": "chunk-definition", "book_name": "传感器教材"}],
        "active_evidence_support": "supported",
        "same_topic": True,
        "requires_new_facet": True,
    })

    assert result["retrieval_action"] == "delta"
    assert result["reused_evidence_ids"] == ["chunk-definition"]
    assert result["new_evidence_ids"] == ["chunk-property"]
    assert [item["chunk_id"] for item in result["evidence_items"]] == [
        "chunk-definition", "chunk-property",
    ]
