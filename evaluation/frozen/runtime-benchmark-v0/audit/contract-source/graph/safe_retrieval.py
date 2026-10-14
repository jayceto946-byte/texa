"""Safe adapters for retrieval dependencies.

The chat path should degrade to plain generation when Chroma or KG state is
missing/corrupt instead of turning the whole SSE stream into an error.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SafeKG:
    error: str = ""
    _is_local: bool = False

    def graph(self) -> dict:
        return {}

    def search_concept(self, *args, **kwargs) -> list:
        return []

    def get_concept_chunks(self, *args, **kwargs) -> list:
        return []

    def find_path(self, *args, **kwargs) -> list[str]:
        return []

    def get_concept_detail(self, *args, **kwargs):
        return None


def get_safe_vector_store():
    try:
        from ingestion.vector_store import get_vector_store

        vs = get_vector_store()
    except Exception as exc:
        error = str(exc)
        return None, error

    if not getattr(vs, "available", True):
        return None, "vector store unavailable"
    return vs, ""


def get_safe_kg(book_name: str):
    try:
        from knowledge.knowledge_graph import get_kg

        return get_kg(book_name), ""
    except Exception as exc:
        error = str(exc)
        return SafeKG(error=error), error
