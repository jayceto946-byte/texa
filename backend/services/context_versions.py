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
    from config import DEEPSEEK_MODEL_NAME, LLM_BACKEND, LLM_MODEL_NAME
    from graph.conversation_context import CONVERSATION_CONTEXT_POLICY_VERSION
    from graph.generator import GENERATION_PROMPT_VERSION
    from graph.retrieval_policy import RETRIEVAL_POLICY_VERSION
    from ingestion.index_pipeline import load_index_manifest

    manifest = load_index_manifest(book_name) if book_name else {}
    corpus_version = str(manifest.get("index_version") or "") or _legacy_corpus_version(book_name)
    return {
        "model_backend": str(LLM_BACKEND),
        "model_name": str(DEEPSEEK_MODEL_NAME if LLM_BACKEND == "deepseek" else LLM_MODEL_NAME),
        "prompt_version": GENERATION_PROMPT_VERSION,
        "context_policy_version": CONVERSATION_CONTEXT_POLICY_VERSION,
        "retrieval_policy_version": RETRIEVAL_POLICY_VERSION,
        "corpus_version": corpus_version,
        "corpus_schema": int(manifest.get("schema_version") or 0),
    }
