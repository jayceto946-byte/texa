"""Helpers for keeping user-facing names safe when used in local paths."""
from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath
from threading import RLock

_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Python 3.10 Windows realpath opens the leaf with share mode 0, before a
# per-file state lock can be acquired. Keep that handle away from JSON replace.
path_resolution_lock = RLock()


def safe_book_name(book_name: str, default: str = "default") -> str:
    name = Path(str(book_name or default)).name.strip()
    name = _INVALID_PATH_CHARS.sub("_", name).strip(". ")
    return (name or default)[:120]


def safe_child_path(root: str | Path, *parts: str | Path) -> Path:
    with path_resolution_lock:
        root_path = Path(root).resolve()
        path = root_path.joinpath(*parts).resolve()
    if not _resolved_within_root(root_path, path):
        raise ValueError(f"resolved path escapes root: {path}")
    return path


def _comparison_path(path):
    if not isinstance(path, PureWindowsPath):
        return path
    text = str(path)
    # Windows realpath can retain the extended prefix during concurrent creation.
    # Normalize only equivalent DOS/UNC spellings for the containment comparison;
    # the caller has already resolved symlinks and keeps the original IO path.
    if text[:8].casefold() == '\\\\?\\UNC\\'.casefold():
        text = '\\\\' + text[8:]
    elif path.drive.startswith('\\\\?\\') and re.fullmatch(r'[A-Za-z]:', path.drive[4:]):
        text = text[4:]
    return PureWindowsPath(text)


def _resolved_within_root(root, path):
    root_key, path_key = _comparison_path(root), _comparison_path(path)
    return path_key == root_key or root_key in path_key.parents


def canonical_path_key(path: str | Path) -> str:
    """Use one process-local identity for resolved Windows path aliases."""
    with path_resolution_lock:
        return str(_comparison_path(Path(path).resolve())).casefold()
