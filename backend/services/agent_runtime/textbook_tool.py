"""Canonical search bound to a frozen UI retrieval scope and index versions."""
import hashlib
import json
from pydantic import BaseModel, ConfigDict, Field

from backend.services.agent_runtime.contracts import RuntimeDenied
from backend.tools.registry import ToolRegistry, ToolSpec, ToolResult


class TextbookContinuation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    book_name: str = Field(min_length=1, max_length=200)
    index_version: str = Field(min_length=1, max_length=200)
    canonical_hash: str = Field(min_length=64, max_length=64)
    unit_id: str = Field(min_length=1, max_length=200)
    block_id: str = Field(min_length=1, max_length=200)
    anchor_chunk_id: str = Field(min_length=1, max_length=200)
    anchor_content_fingerprint: str = Field(default="", max_length=24, pattern=r"^(?:[0-9a-f]{24})?$")


class TextbookSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=2000)
    chapter: str = Field(default="", max_length=200)
    continuation: TextbookContinuation | None = None


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
    def scope_check(context, args):
        if context.book_name != scope["book_name"] or context.subject != scope["subject"]:
            raise RuntimeDenied("textbook scope changed")
        from backend.services.context_versions import current_context_versions
        version_reader = versions or (lambda name: current_context_versions(name)["corpus_version"])
        if any(version_reader(name) != version for name, version in scope["index_versions"].items()):
            raise RuntimeDenied("textbook index version changed; start a new task")
    def handler(context, args):
        scope_check(context, args)
        from backend.services.context_versions import current_context_versions
        version_reader = versions or (lambda name: current_context_versions(name)["corpus_version"])
        from graph.retrieval_node import retrieve_node
        from graph.evidence_pack import build_evidence_pack
        from graph.intent_classifier import classify_intent_local
        intent = classify_intent_local(args["query"]).get("intent", "qa")
        pointer = args.get("continuation")
        if pointer:
            if (pointer["book_name"] not in scope["index_versions"]
                    or pointer["index_version"] != scope["index_versions"][pointer["book_name"]]):
                raise RuntimeDenied("textbook continuation escaped frozen scope")
            from graph.textbook_context import read_textbook_continuation
            try:
                continued = read_textbook_continuation(pointer)
            except (OSError, ValueError, KeyError) as exc:
                raise RuntimeDenied("textbook continuation unavailable or version changed") from exc
            result = {"evidence_items": continued, "evidence_support": {"status": "supported"},
                      "retrieval_status": "versioned_canonical_continuation"}
        else:
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
        from graph.textbook_context import expand_textbook_context
        items = expand_textbook_context(items, intent=intent, query=args["query"])
        if any(version_reader(name) != version for name, version in scope["index_versions"].items()):
            raise RuntimeDenied("textbook index version changed during expansion")
        pack = build_evidence_pack(items, intent=intent)
        selected = pack["verification_items"]
        support = result.get("evidence_support") or {}
        success = bool(selected) and support.get("status") not in {"insufficient", "unavailable"}
        return ToolResult(success, data={"query_scope": scope, "evidence_items": selected,
            "evidence_support": support, "retrieval_status": str(result.get("retrieval_status") or "")},
            evidence=pack["items"], message="Scoped production EvidencePack" if success else "Scoped evidence unavailable")
    registry.register(ToolSpec(name="search_textbook", description="Search only the frozen UI textbook scope, or read a returned versioned continuation; preserve EvidencePack provenance",
        parameters=TextbookSearchInput.model_json_schema(), read_only=True, handler=handler,
        runtime_input=TextbookSearchInput, runtime_output=TextbookSearchOutput, permission="READ", version="3",
        side_effect="derived_cache", source="builtin", provenance="scoped_production_evidence_pack",
        idempotency="read_retryable", timeout_seconds=8, runtime_scope_check=scope_check))
