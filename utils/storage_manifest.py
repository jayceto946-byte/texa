"""Version registry for persistent application data."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DATA_DIR
from utils.json_io import atomic_write_json


DATA_SCHEMA_VERSION = 1
STORAGE_MANIFEST_NAME = "storage_manifest.json"
COMPONENT_VERSIONS: dict[str, int] = {
    "book_registry": 1,
    "exercise_bank": 1,
    "mistake_book": 1,
    "study_memory": 1,
    "spaced_repetition": 1,
    "concept_memory": 1,
    "learning_events": 1,
    "job_manager": 1,
    "rag_trace": 1,
    "backup": 2,
    "vector_index": 4,
    "lexical_index": 2,
}
DATA_CLASSES: dict[str, list[str]] = {
    "authoritative": [
        "books",
        "uploads",
        "progress/*.db",
        "progress/*/progress.json",
        "progress/*/quiz_history.json",
        "progress/*/weakness.json",
        "progress/*/chat_history.json",
        "progress/*/spaced_repetition.json",
        "progress/*/concept_memory.json",
    ],
    "expensive_derived": ["mineru_output", "knowledge_graph", "chapter_highlights"],
    "rebuildable_index": ["vector_db", "vector_db/_lexical"],
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def storage_manifest_path(data_root: str | Path | None = None) -> Path:
    return Path(data_root or DATA_DIR) / STORAGE_MANIFEST_NAME


def _normalized_manifest(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    version = int(raw.get("schema_version") or 0)
    if version > DATA_SCHEMA_VERSION:
        raise RuntimeError(
            f"data schema {version} is newer than supported schema {DATA_SCHEMA_VERSION}"
        )
    created_at = str(raw.get("created_at") or _utc_now())
    components = dict(raw.get("components") or {})
    for name, component_version in COMPONENT_VERSIONS.items():
        components[name] = max(int(components.get(name) or 0), component_version)
    return {
        "schema_version": DATA_SCHEMA_VERSION,
        "created_at": created_at,
        "updated_at": _utc_now(),
        "components": components,
        "data_classes": DATA_CLASSES,
    }


def ensure_storage_manifest(data_root: str | Path | None = None) -> dict:
    """Create or upgrade the storage manifest using an atomic replace."""
    path = storage_manifest_path(data_root)
    raw: Any = {}
    if path.exists():
        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
    manifest = _normalized_manifest(raw)
    if raw != manifest:
        atomic_write_json(path, manifest)
    return manifest


def read_storage_manifest(data_root: str | Path | None = None) -> dict:
    return ensure_storage_manifest(data_root)
