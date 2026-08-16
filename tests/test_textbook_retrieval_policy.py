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

