import json


def test_role_policy_is_soft_configurable_and_preserves_neutral_fallback(monkeypatch):
    from graph.retrieval_policy import textbook_retrieval_policy

    policy = textbook_retrieval_policy()
    assert policy.multiplier("core") > policy.multiplier("") > policy.multiplier("reference")
    assert 0.85 <= policy.multiplier("reference", 0.01) <= 1.15

    monkeypatch.setenv("TEXA_PRIMARY_TEXTBOOK_MULTIPLIER", "1")
    monkeypatch.setenv("TEXA_SUPPLEMENTARY_TEXTBOOK_MULTIPLIER", "1")
    disabled = textbook_retrieval_policy()
    assert disabled.multiplier("core") == 1.0
    assert disabled.multiplier("reference") == 1.0


def test_rerank_keeps_raw_relevance_separate_from_textbook_prior(monkeypatch):
    from graph import retrieval_node

    monkeypatch.setattr(retrieval_node, "cross_encoder_scores", lambda *_args, **_kwargs: None)
    common = {
        "text": "灵敏度定义为输出变化量与输入变化量之比。",
        "section_title": "灵敏度",
        "chapter": "第一章",
        "source": "bm25",
        "retrieval_rank": 1,
        "rag_priority": 1.0,
    }
    _, items = retrieval_node._merge_and_rerank(
        [],
        [
            {**common, "chunk_id": "supplementary", "book_name": "supplementary", "book_role": "reference"},
            {**common, "chunk_id": "primary", "book_name": "primary", "book_role": "core"},
        ],
        include_metadata=True,
        query="灵敏度的定义是什么？",
        intent="definition",
    )

    assert items[0]["chunk_id"] == "primary"
    assert items[0]["relevance_score"] == items[1]["relevance_score"]
    assert items[0]["textbook_role_multiplier"] > items[1]["textbook_role_multiplier"]
    assert items[0]["score"] > items[0]["relevance_score"]


def test_explicit_reference_chapter_does_not_fall_back_to_group_core(monkeypatch):
    from types import SimpleNamespace

    from graph import retrieval_node
    from ingestion.vector_store import RetrievalOutcome

    resources = [
        {"book_name": "core-book", "role": "core", "priority": 1.0, "is_primary": True, "is_selected": False},
        {"book_name": "reference-book", "role": "reference", "priority": 1.0, "is_primary": False, "is_selected": True},
    ]
    searched_books = []

    class EmptyVectorStore:
        def search_chapter(self, _chapter, _query, *, book_name="", **_kwargs):
            searched_books.append(book_name)
            return RetrievalOutcome(items=[])

        def search_all(self, _query, *, book_name="", **_kwargs):
            searched_books.append(book_name)
            return RetrievalOutcome(items={})

    monkeypatch.setattr(retrieval_node, "resolve_retrieval_resources", lambda *_args: resources)
    monkeypatch.setattr(retrieval_node, "get_safe_kg", lambda *_args: (SimpleNamespace(_is_local=False), "unavailable"))
    monkeypatch.setattr(retrieval_node, "_kg_precise_retrieval", lambda *_args, **_kwargs: ([], []))

    retrieval_node.retrieve_node(
        {
            "user_input": "参考书第四章讲了什么？",
            "book_name": "reference-book",
            "intent": "factual_recall",
            "target_chapters": ["第四章"],
            "use_textbook_context": True,
        },
        vector_store=EmptyVectorStore(),
        lexical_search=lambda book, *_args, **_kwargs: searched_books.append(book) or [],
        neighbor_expander=lambda *_args, **_kwargs: [],
        index_stats_override={"reference-book": {"healthy": True}},
    )

    assert searched_books
    assert set(searched_books) == {"reference-book"}


def test_role_change_and_reference_only_group_resolve_without_reindex(monkeypatch, tmp_path):
    from utils import resource_groups

    progress = tmp_path / "progress"
    for name in ("book-a", "book-b"):
        folder = progress / name
        folder.mkdir(parents=True)
        (folder / "metadata.json").write_text(
            json.dumps({"subject": "course-a", "book_role": "reference"}),
            encoding="utf-8",
        )
    monkeypatch.setattr(resource_groups, "PROGRESS_PATH", progress)

    reference_only = resource_groups.resolve_retrieval_resources("book-b", "course-a")
    assert {item["book_name"] for item in reference_only} == {"book-a", "book-b"}
    assert next(item for item in reference_only if item["is_primary"])["book_name"] == "book-b"

    (progress / "book-a" / "metadata.json").write_text(
        json.dumps({"subject": "course-a", "book_role": "core"}),
        encoding="utf-8",
    )
    changed = resource_groups.resolve_retrieval_resources("book-b", "course-a")
    assert next(item for item in changed if item["is_primary"])["book_name"] == "book-a"
