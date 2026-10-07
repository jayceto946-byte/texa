"""File-signature caches for frequently requested textbook catalog data."""
from __future__ import annotations

import hashlib
import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

_SIGNATURE_HASH_MAX_BYTES = 1024 * 1024
FileSignature = tuple[int, int, bytes | None]


def _signature(path: Path) -> FileSignature | None:
    try:
        stat = path.stat()
        digest = None
        if path.is_file() and stat.st_size <= _SIGNATURE_HASH_MAX_BYTES:
            digest = hashlib.blake2b(
                path.read_bytes(), digest_size=16
            ).digest()
        return stat.st_mtime_ns, stat.st_size, digest
    except OSError:
        return None


class BookReadCache:
    """Thread-safe cache that invalidates automatically when backing files change."""

    def __init__(self):
        self._lock = threading.RLock()
        self._json: dict[str, tuple[FileSignature | None, Any]] = {}
        self._pdfs: dict[str, tuple[FileSignature | None, tuple[Path, ...]]] = {}
        self._index: dict[
            tuple[str, str, str, tuple[str, ...]],
            tuple[tuple[FileSignature | None, ...], dict],
        ] = {}

    def clear(self) -> None:
        with self._lock:
            self._json.clear()
            self._pdfs.clear()
            self._index.clear()

    def read_json(self, path: Path, default: Any) -> Any:
        key = str(path.resolve())
        signature = _signature(path)
        with self._lock:
            cached = self._json.get(key)
            if cached and cached[0] == signature:
                return deepcopy(cached[1])
        try:
            value = json.loads(path.read_text(encoding="utf-8")) if signature else default
        except Exception:
            value = default
        with self._lock:
            self._json[key] = (signature, deepcopy(value))
        return deepcopy(value)

    def list_pdfs(self, root: Path) -> list[Path]:
        root.mkdir(parents=True, exist_ok=True)
        key = str(root.resolve())
        signature = _signature(root)
        with self._lock:
            cached = self._pdfs.get(key)
            if cached and cached[0] == signature:
                return list(cached[1])
        files = tuple(root.glob("*.pdf"))
        with self._lock:
            self._pdfs[key] = (signature, files)
        return list(files)

    def index_stats(
        self,
        book_name: str,
        chapter_map_path: Path,
        lexical_path: Path,
        loader: Callable[[], dict],
        *,
        dependency_paths: tuple[Path, ...] = (),
    ) -> dict:
        resolved_dependencies = tuple(str(path.resolve()) for path in dependency_paths)
        key = (
            book_name,
            str(chapter_map_path.resolve()),
            str(lexical_path.resolve()),
            resolved_dependencies,
        )
        signatures = (
            _signature(chapter_map_path),
            _signature(lexical_path),
            *(_signature(path) for path in dependency_paths),
        )
        with self._lock:
            cached = self._index.get(key)
            if cached and cached[0] == signatures:
                return deepcopy(cached[1])
        value = loader()
        with self._lock:
            self._index[key] = (signatures, deepcopy(value))
        return deepcopy(value)
