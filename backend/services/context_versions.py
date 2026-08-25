"""Version identifiers attached to context decisions and answer feedback."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _legacy_corpus_version(book_name: str) -> str:
    if not book_name:
        return ""
    try:
        from ingestion.lexical_index import index_path

        path = Path(index_path(book_name))
        stat = path.stat()
        return f"legacy-{stat.st_size:x}-{stat.st_mtime_ns:x}"
    except OSError:
        return ""


def current_context_versions(book_name: str = "") -> dict[str, Any]:
    from config import get_model_role_config
    from graph.conversation_context import CONVERSATION_CONTEXT_POLICY_VERSION
    from graph.teaching_prompts import active_teaching_prompt_version
    from graph.retrieval_policy import RETRIEVAL_POLICY_VERSION
    from ingestion.index_pipeline import load_index_manifest

    manifest = load_index_manifest(book_name) if book_name else {}
    corpus_version = str(manifest.get("index_version") or "") or _legacy_corpus_version(book_name)
    model = get_model_role_config("reasoning")
    return {
        "model_backend": model.provider.provider_id,
        "model_name": model.model,
        "prompt_version": active_teaching_prompt_version(),
        "context_policy_version": CONVERSATION_CONTEXT_POLICY_VERSION,
        "retrieval_policy_version": RETRIEVAL_POLICY_VERSION,
        "corpus_version": corpus_version,
        "corpus_schema": int(manifest.get("schema_version") or 0),
    }
