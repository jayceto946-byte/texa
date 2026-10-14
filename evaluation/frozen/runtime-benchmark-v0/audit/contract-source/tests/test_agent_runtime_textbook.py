import pytest

from backend.services.agent_runtime.contracts import RuntimeDenied
from backend.services.agent_runtime.textbook_tool import register_textbook_search_runtime
from backend.tools.registry import ToolContext, ToolRegistry


def scope():
    return {"id": "scope", "book_name": "main", "subject": "数学", "resources": [
        {"book_name": "main", "is_primary": True, "is_selected": True},
        {"book_name": "reference", "is_primary": False, "is_selected": False}],
        "index_versions": {"main": "v1", "reference": "v2"}}


def test_canonical_search_preserves_multi_book_scope_and_pack(tmp_path):
    registry = ToolRegistry()
    observed = []
    def retrieve(state, **kwargs):
        observed.append(kwargs["retrieval_resources_override"])
        return {"evidence_items": [{"book_name": "main", "chunk_id": "a", "text": "定义及性质"},
            {"book_name": "reference", "chunk_id": "b", "text": "补充的适用条件"}],
            "evidence_support": {"status": "sufficient"}, "retrieval_status": "ok"}
    frozen = scope()
    register_textbook_search_runtime(registry, frozen, retrieve=retrieve, versions=lambda name: frozen["index_versions"][name])
    spec = registry.runtime_tool("search_textbook")
    result = spec.handler(ToolContext(book_name="main", subject="数学"), {"query": "定义与性质", "chapter": ""})
    spec.runtime_output.model_validate(result.data)
    assert result.success
    assert {item["book_name"] for item in result.data["evidence_items"]} == {"main", "reference"}
    assert observed == [frozen["resources"]]
    assert len(result.evidence) == 2
    with pytest.raises(RuntimeDenied, match="scope changed"):
        spec.handler(ToolContext(book_name="different", subject="数学"), {"query": "x", "chapter": ""})


def test_changed_index_and_out_of_scope_evidence_are_rejected():
    registry = ToolRegistry()
    frozen = scope()
    register_textbook_search_runtime(registry, frozen, retrieve=lambda *args, **kw: {}, versions=lambda name: "changed")
    with pytest.raises(RuntimeDenied, match="index version changed"):
        registry.runtime_tool("search_textbook").handler(ToolContext(book_name="main", subject="数学"), {"query": "x", "chapter": ""})
    registry = ToolRegistry()
    register_textbook_search_runtime(registry, frozen, versions=lambda name: frozen["index_versions"][name],
        retrieve=lambda *args, **kw: {"evidence_items": [{"book_name": "outside", "chunk_id": "c", "text": "不允许"}]})
    with pytest.raises(RuntimeDenied, match="escaped"):
        registry.runtime_tool("search_textbook").handler(ToolContext(book_name="main", subject="数学"), {"query": "x", "chapter": ""})
