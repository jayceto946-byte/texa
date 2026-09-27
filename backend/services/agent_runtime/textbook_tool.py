"""Canonical search bound to a frozen UI retrieval scope and index versions."""
import hashlib
import json
from pydantic import BaseModel, ConfigDict, Field

from backend.services.agent_runtime.contracts import RuntimeDenied
from backend.tools.registry import ToolRegistry, ToolSpec, ToolResult


class TextbookSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=2000)
    chapter: str = Field(default="", max_length=200)


class TextbookSearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query_scope: dict
    evidence_items: list[dict]
    evidence_support: dict
    retrieval_status: str


def freeze_textbook_scope(book_name: str, subject: str) -> dict:
    from utils.resource_groups import resolve_retrieval_resources
    from backend.services.context_versions import current_context_versions
    resources = resolve_retrieval_resources(book_name, subject)
    versions = {item["book_name"]: current_context_versions(item["book_name"])["corpus_version"] for item in resources}
    scope = {"book_name": book_name, "subject": subject, "resources": resources,
             "index_versions": versions, "scope_policy": "ui-resource-group/v1"}
    scope["id"] = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
    return scope


def register_textbook_search_runtime(registry: ToolRegistry, scope: dict, *, retrieve=None, versions=None):
    def handler(context, args):
        if context.book_name != scope["book_name"] or context.subject != scope["subject"]:
            raise RuntimeDenied("textbook scope changed")
        from backend.services.context_versions import current_context_versions
        version_reader = versions or (lambda name: current_context_versions(name)["corpus_version"])
        if any(version_reader(name) != version for name, version in scope["index_versions"].items()):
            raise RuntimeDenied("textbook index version changed; start a new task")
        from graph.retrieval_node import retrieve_node
        from graph.evidence_pack import build_evidence_pack
        from graph.intent_classifier import classify_intent_local
        intent = classify_intent_local(args["query"]).get("intent", "qa")
        result = (retrieve or retrieve_node)({"user_input": args["query"], "book_name": scope["book_name"],
            "subject": scope["subject"], "intent": intent, "use_textbook_context": True,
            "answer_mode": "textbook_grounded", "target_chapters": [args["chapter"]] if args["chapter"] else []},
            retrieval_resources_override=scope["resources"])
        if any(version_reader(name) != version for name, version in scope["index_versions"].items()):
            raise RuntimeDenied("textbook index version changed during retrieval")
        items = result.get("evidence_items") or []
        allowed = set(scope["index_versions"])
        if any(item.get("book_name") not in allowed for item in items):
            raise RuntimeDenied("retrieval escaped the frozen textbook scope")
        pack = build_evidence_pack(items, intent=intent)
        selected = []
        for source in pack["items"]:
            raw = next(item for item in items if item.get("chunk_id") == source["chunk_id"] and item.get("book_name") == source["book_name"])
            selected.append({**raw, "text": str(raw.get("text") or "")[:source["chars"]]})
        support = result.get("evidence_support") or {}
        success = bool(selected) and support.get("status") not in {"insufficient", "unavailable"}
        return ToolResult(success, data={"query_scope": scope, "evidence_items": selected,
            "evidence_support": support, "retrieval_status": str(result.get("retrieval_status") or "")},
            evidence=pack["items"], message="Scoped production EvidencePack" if success else "Scoped evidence unavailable")
    registry.register(ToolSpec(name="search_textbook", description="Search only the frozen UI textbook scope; preserve EvidencePack provenance",
        parameters=TextbookSearchInput.model_json_schema(), read_only=True, handler=handler,
        runtime_input=TextbookSearchInput, runtime_output=TextbookSearchOutput, permission="READ",
        side_effect="derived_cache", source="builtin", provenance="scoped_production_evidence_pack",
        idempotency="read_retryable", timeout_seconds=8))
