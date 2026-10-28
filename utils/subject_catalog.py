"""Shared subject hierarchy helpers.

Subjects are stored as a two-level catalog. Runtime records keep a single string
value so older data remains readable; new second-level values use "一级/二级".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import PROGRESS_PATH
from utils.json_io import atomic_write_json

SUBJECTS_PATH = Path(PROGRESS_PATH) / "subjects.json"

DEFAULT_SUBJECT_TREE = [
    {"name": "数学", "children": ["高数", "线代", "概率论"]},
    {"name": "英语", "children": ["阅读", "写作", "翻译", "词汇"]},
    {"name": "政治", "children": ["马原", "毛中特", "史纲", "思修"]},
    {"name": "专业课", "children": []},
]


def clean_subject_tree(tree: list[dict[str, Any]] | Any) -> list[dict[str, list[str] | str]]:
    if not isinstance(tree, list):
        tree = []
    cleaned: list[dict[str, list[str] | str]] = []
    seen_parent: set[str] = set()
    for item in tree:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip().strip("/")
        if not name or name in seen_parent:
            continue
        seen_parent.add(name)
        children: list[str] = []
        for child in item.get("children", []) or []:
            child_name = str(child).strip().strip("/")
            if child_name and child_name != name and child_name not in children:
                children.append(child_name)
        cleaned.append({"name": name, "children": children})
    return cleaned


def read_subject_tree(path: Path = SUBJECTS_PATH) -> list[dict[str, list[str] | str]]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return clean_subject_tree(data)
    except Exception:
        pass
    return clean_subject_tree(DEFAULT_SUBJECT_TREE)


def write_subject_tree(tree: list[dict[str, Any]], path: Path = SUBJECTS_PATH) -> list[dict[str, list[str] | str]]:
    cleaned = clean_subject_tree(tree)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, cleaned)
    return cleaned


def split_subject(value: str) -> tuple[str, str]:
    raw = str(value or "").strip().strip("/")
    if "/" not in raw:
        return raw, ""
    parent, child = raw.split("/", 1)
    return parent.strip(), child.strip().strip("/")


def normalize_subject_value(value: str, fallback: str = "") -> str:
    raw = str(value or fallback or "").strip().strip("/")
    if not raw:
        return ""
    parent, child = split_subject(raw)
    if child:
        return f"{parent}/{child}" if parent and child else raw

    matches: list[str] = []
    for node in read_subject_tree():
        node_name = str(node.get("name", "")).strip()
        children = [str(item).strip() for item in node.get("children", []) or []]
        if raw == node_name:
            return node_name
        if raw in children:
            matches.append(f"{node_name}/{raw}")
    return matches[0] if len(matches) == 1 else raw


def _children_for_parent(parent: str) -> list[str]:
    for node in read_subject_tree():
        if str(node.get("name", "")).strip() == parent:
            return [str(item).strip() for item in node.get("children", []) or [] if str(item).strip()]
    return []


def subject_matches(record_subject: str, selected: str) -> bool:
    selected = str(selected or "").strip().strip("/")
    if not selected:
        return True
    value = str(record_subject or "").strip().strip("/")
    if not value:
        return False
    if value == selected:
        return True

    selected_parent, selected_child = split_subject(selected)
    value_parent, value_child = split_subject(value)

    if selected_child:
        # New records store parent/child; old records may only store the child.
        return value == selected_child or (value_parent == selected_parent and value_child == selected_child)

    children = _children_for_parent(selected_parent)
    if value_parent == selected_parent:
        return True
    if children and value in children:
        return True

    # If selected itself is a legacy child name, match both legacy and normalized paths.
    return value_child == selected or value == selected
