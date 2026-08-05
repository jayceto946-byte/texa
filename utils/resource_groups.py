"""Resolve configurable multi-textbook retrieval groups from book metadata."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import PROGRESS_PATH
from utils.path_safety import safe_book_name

GROUP_ROLES = {"core", "reference"}


def read_book_resource_meta(book_name: str) -> dict[str, Any]:
    safe = safe_book_name(book_name)
    path = Path(PROGRESS_PATH) / safe / "metadata.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def resolve_retrieval_resources(book_name: str, subject: str = "") -> list[dict[str, Any]]:
    """Return the selected book or its explicitly configured core/reference group."""
    selected = safe_book_name(book_name)
    if not selected or selected == "default":
        return [{"book_name": book_name, "role": "", "priority": 1.0, "is_primary": True, "is_selected": True}]
    selected_meta = read_book_resource_meta(selected)
    selected_role = str(selected_meta.get("book_role") or "standalone").strip().lower()
    selected_group = str(selected_meta.get("resource_group") or "").strip()
    selected_subject = str(selected_meta.get("subject") or subject or "").strip()
    if selected_role not in GROUP_ROLES:
        return [_resource(selected, selected_meta, True, True)]

    candidates: list[tuple[str, dict[str, Any]]] = []
    root = Path(PROGRESS_PATH)
    if root.exists():
        for child in root.iterdir():
            if not child.is_dir() or not (child / "metadata.json").exists():
                continue
            meta = read_book_resource_meta(child.name)
            role = str(meta.get("book_role") or "").strip().lower()
            if role not in GROUP_ROLES:
                continue
            group = str(meta.get("resource_group") or "").strip()
            same_group = bool(selected_group and group == selected_group)
            same_subject_group = bool(not selected_group and selected_subject and str(meta.get("subject") or "").strip() == selected_subject)
            if same_group or same_subject_group:
                candidates.append((child.name, meta))
    if not any(name == selected for name, _ in candidates):
        candidates.append((selected, selected_meta))
    candidates.sort(key=lambda item: (0 if str(item[1].get("book_role") or "") == "core" else 1, -_priority(item[1]), item[0]))
    primary_name = next((name for name, meta in candidates if str(meta.get("book_role") or "") == "core"), selected)
    return [_resource(name, meta, name == primary_name, name == selected) for name, meta in candidates]


def _resource(book_name: str, meta: dict[str, Any], is_primary: bool, is_selected: bool) -> dict[str, Any]:
    role = str(meta.get("book_role") or "").strip().lower()
    return {
        "book_name": safe_book_name(book_name),
        "role": role if role in GROUP_ROLES else "",
        "priority": _priority(meta),
        "is_primary": is_primary,
        "is_selected": is_selected,
        "resource_group": str(meta.get("resource_group") or "").strip(),
    }


def _priority(meta: dict[str, Any]) -> float:
    try:
        return max(0.05, min(2.0, float(meta.get("rag_priority") or (0.55 if meta.get("book_role") == "reference" else 1.0))))
    except (TypeError, ValueError):
        return 1.0
