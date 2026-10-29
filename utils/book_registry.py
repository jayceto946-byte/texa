"""Stable textbook identities independent from display names and file paths."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import PROGRESS_PATH
from utils.json_io import atomic_write_json
from utils.path_safety import safe_book_name


BOOK_REGISTRY_SCHEMA_VERSION = 1
_lock = threading.RLock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_display_name(value: str) -> str:
    name = " ".join(str(value or "").strip().split())
    if not name or len(name) > 120 or any(char in name for char in "\r\n\0"):
        raise ValueError("invalid textbook display name")
    return name


class BookRegistry:
    def __init__(self, progress_root: str | Path = PROGRESS_PATH):
        self.progress_root = Path(progress_root)
        self.path = self.progress_root / "book_registry.json"

    def _load(self) -> dict:
        if not self.path.exists():
            return {"schema_version": BOOK_REGISTRY_SCHEMA_VERSION, "books": {}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"book registry is unreadable: {exc}") from exc
        if not isinstance(raw, dict):
            raise RuntimeError("book registry must be an object")
        version = int(raw.get("schema_version") or 0)
        if version > BOOK_REGISTRY_SCHEMA_VERSION:
            raise RuntimeError(f"book registry schema {version} is not supported")
        books = raw.get("books") if isinstance(raw.get("books"), dict) else {}
        return {"schema_version": BOOK_REGISTRY_SCHEMA_VERSION, "books": books}

    def _save(self, registry: dict) -> None:
        self.progress_root.mkdir(parents=True, exist_ok=True)
        registry["schema_version"] = BOOK_REGISTRY_SCHEMA_VERSION
        registry["updated_at"] = _utc_now()
        atomic_write_json(self.path, registry)

    def ensure(
        self,
        storage_name: str,
        *,
        preferred_id: str = "",
        display_name: str = "",
        archived: bool = False,
    ) -> dict:
        storage = safe_book_name(storage_name)
        display = _clean_display_name(display_name or storage)
        with _lock:
            registry = self._load()
            books: dict[str, dict] = registry["books"]
            record = books.get(preferred_id) if preferred_id else None
            if record and record.get('status') == 'purged':
                record = None
            if not record:
                record = next(
                    (
                        value
                        for value in books.values()
                        if value.get('status') != 'purged' and (value.get("storage_name") == storage
                        or storage in (value.get("aliases") or []))
                    ),
                    None,
                )
            if record:
                book_id = str(record.get("book_id") or preferred_id)
                if not book_id:
                    book_id = str(uuid.uuid4())
                aliases = list(dict.fromkeys([*(record.get("aliases") or []), storage]))
                record.update(
                    book_id=book_id,
                    storage_name=storage,
                    display_name=display,
                    aliases=aliases,
                    status="archived" if archived else "active",
                    updated_at=_utc_now(),
                )
            else:
                try:
                    book_id = str(uuid.UUID(preferred_id)) if preferred_id else str(uuid.uuid4())
                except ValueError:
                    book_id = str(uuid.uuid4())
                record = {
                    "book_id": book_id,
                    "storage_name": storage,
                    "display_name": display,
                    "aliases": [storage],
                    "status": "archived" if archived else "active",
                    "created_at": _utc_now(),
                    "updated_at": _utc_now(),
                }
            books[book_id] = record
            self._save(registry)
            return dict(record)

    def resolve(self, reference: str, *, include_archived: bool = True) -> dict | None:
        ref = str(reference or "").strip()
        if not ref:
            return None
        with _lock:
            books = self._load()["books"]
            record = books.get(ref)
            if not record:
                matches = [
                    value
                    for value in books.values()
                    if value.get('status') != 'purged' and (ref == value.get("storage_name")
                    or ref == value.get("display_name")
                    or ref in (value.get("aliases") or []))
                ]
                record = matches[0] if len(matches) == 1 else None
            status = str(record.get("status") or "active") if record else ""
            if not record or status == "purged" or (not include_archived and status != "active"):
                return None
            return dict(record)

    def rename_display(self, reference: str, display_name: str) -> dict:
        display = _clean_display_name(display_name)
        with _lock:
            registry = self._load()
            current = self.resolve(reference)
            if not current:
                raise KeyError(reference)
            for book_id, other in registry["books"].items():
                identifiers = {
                    str(other.get("storage_name") or "").casefold(),
                    str(other.get("display_name") or "").casefold(),
                    *(str(alias).casefold() for alias in (other.get("aliases") or [])),
                }
                if book_id != current["book_id"] and display.casefold() in identifiers:
                    raise ValueError("textbook display name conflicts with an existing identity")
            record = registry["books"][current["book_id"]]
            previous = str(record.get("display_name") or "")
            aliases = list(dict.fromkeys([*(record.get("aliases") or []), previous]))
            record.update(display_name=display, aliases=[item for item in aliases if item], updated_at=_utc_now())
            self._save(registry)
            return dict(record)

    def set_status(self, reference: str, status: str) -> dict:
        if status not in {"active", "archived", "purged"}:
            raise ValueError("invalid textbook lifecycle status")
        with _lock:
            registry = self._load()
            current = self.resolve(reference)
            if not current:
                raise KeyError(reference)
            record = registry["books"][current["book_id"]]
            record.update(status=status, updated_at=_utc_now())
            self._save(registry)
            return dict(record)

    def list(self, *, include_archived: bool = True) -> list[dict]:
        with _lock:
            records = [dict(item) for item in self._load()["books"].values()]
        if not include_archived:
            records = [item for item in records if item.get("status") == "active"]
        return sorted(records, key=lambda item: str(item.get("display_name") or item.get("storage_name")))
