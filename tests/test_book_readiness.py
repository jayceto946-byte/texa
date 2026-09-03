import json

from backend.services.book_readiness import derive_book_readiness


def test_readiness_separates_technical_canonical_and_semantic_states(tmp_path):
    progress = tmp_path / "progress"
    vector = tmp_path / "vector"
    book_dir = progress / "demo"
    book_dir.mkdir(parents=True)
    (book_dir / "canonical_document.jsonl").write_text(
        '{"record_type":"canonical_book"}\n',
        encoding="utf-8",
    )
    (book_dir / "ingestion_report.json").write_text(
        json.dumps({
            "valid": True,
            "block_count": 12,
            "summary": {"errors": 0, "warnings": 2},
        }),
        encoding="utf-8",
    )
    manifests = vector / "_index_manifests"
    manifests.mkdir(parents=True)
    (manifests / "demo.json").write_text(
        json.dumps({
            "release_quality": {
                "status": "passed",
                "cases": 4,
                "generated_probe_cases": 4,
            },
        }),
        encoding="utf-8",
    )

    result = derive_book_readiness(
        "demo",
        index_status={
            "status": "ready",
            "vector_ready": True,
            "lexical_ready": True,
            "chunk_count": 20,
        },
        progress_root=progress,
        vector_db_root=vector,
    )

    assert result["technical"]["status"] == "ready"
    assert result["canonical"] == {
        "status": "needs_review",
        "warning_count": 2,
        "error_count": 0,
        "block_count": 12,
    }
    assert result["semantic"]["status"] == "unverified"
    assert result["semantic"]["human_case_count"] == 0


def test_human_release_cases_are_required_for_semantic_verification(tmp_path):
    progress = tmp_path / "progress"
    vector = tmp_path / "vector"
    manifests = vector / "_index_manifests"
    manifests.mkdir(parents=True)
    (manifests / "demo.json").write_text(
        json.dumps({
            "release_quality": {
                "status": "passed",
                "cases": 7,
                "generated_probe_cases": 4,
            },
        }),
        encoding="utf-8",
    )

    result = derive_book_readiness(
        "demo",
        index_status={"status": "degraded", "lexical_ready": True},
        progress_root=progress,
        vector_db_root=vector,
    )

    assert result["technical"]["status"] == "degraded"
    assert result["canonical"]["status"] == "unavailable"
    assert result["semantic"]["status"] == "verified"
    assert result["semantic"]["human_case_count"] == 3


def test_scope_rebuild_requirement_is_preserved_in_readiness_contract(tmp_path):
    result = derive_book_readiness(
        "demo",
        index_status={
            "status": "missing",
            "healthy": False,
            "vector_ready": False,
            "lexical_ready": True,
            "error_code": "legacy_unscoped_index_requires_rebuild",
            "reindex_required": True,
        },
        progress_root=tmp_path / "progress",
        vector_db_root=tmp_path / "vector",
    )

    assert result["technical"]["healthy"] is False
    assert result["technical"]["vector_ready"] is False
    assert result["technical"]["error_code"] == "legacy_unscoped_index_requires_rebuild"
    assert result["technical"]["reindex_required"] is True
