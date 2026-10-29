"""Centralized, guarded lifecycle operations for textbooks."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from config import BOOKS_PATH, DATA_DIR, MINERU_OUTPUT_PATH, PROGRESS_PATH, VECTOR_DB_PATH
from utils.book_registry import BookRegistry
from utils.json_io import atomic_write_json
from utils.path_safety import safe_book_name, safe_child_path


class BookLifecycleService:
    def __init__(self, progress_root: str | Path = PROGRESS_PATH):
        self.progress_root = Path(progress_root)
        self.registry = BookRegistry(self.progress_root)

    def _metadata_path(self, storage_name: str) -> Path:
        return safe_child_path(self.progress_root, safe_book_name(storage_name), "metadata.json")

    def read_metadata(self, storage_name: str) -> dict:
        path = self._metadata_path(storage_name)
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def ensure_identity(self, storage_name: str, metadata: dict | None = None) -> tuple[dict, dict]:
        meta = dict(metadata if metadata is not None else self.read_metadata(storage_name))
        record = self.registry.ensure(
            storage_name,
            preferred_id=str(meta.get("book_id") or ""),
            display_name=str(meta.get("display_name") or storage_name),
            archived=bool(meta.get("archived")),
        )
        changed = any(
            meta.get(key) != value
            for key, value in {
                "book_id": record["book_id"],
                "storage_name": record["storage_name"],
                "display_name": record["display_name"],
            }.items()
        )
        meta.update(
            book_id=record["book_id"],
            storage_name=record["storage_name"],
            display_name=record["display_name"],
        )
        if changed:
            atomic_write_json(self._metadata_path(storage_name), meta)
        return record, meta

    def resolve(self, reference: str, *, include_archived: bool = True) -> dict | None:
        return self.registry.resolve(reference, include_archived=include_archived)

    def update_metadata(self, storage_name: str, **updates) -> tuple[dict, dict]:
        meta = self.read_metadata(storage_name)
        meta.update({key: value for key, value in updates.items() if value is not None})
        display_name = str(meta.get("display_name") or storage_name)
        existing = self.registry.resolve(str(meta.get("book_id") or storage_name))
        if existing and display_name != existing.get("display_name"):
            record = self.registry.rename_display(existing["book_id"], display_name)
        else:
            record = self.registry.ensure(
                storage_name,
                preferred_id=str(meta.get("book_id") or ""),
                display_name=display_name,
                archived=bool(meta.get("archived")),
            )
        meta.update(
            book_id=record["book_id"],
            storage_name=record["storage_name"],
            display_name=record["display_name"],
        )
        atomic_write_json(self._metadata_path(storage_name), meta)
        return record, meta

    def archive(self, reference: str) -> tuple[dict, dict]:
        record = self._require(reference)
        record = self.registry.set_status(record["book_id"], "archived")
        return self.update_metadata(record["storage_name"], archived=True)

    def restore(self, reference: str) -> tuple[dict, dict]:
        record = self._require(reference)
        record = self.registry.set_status(record["book_id"], "active")
        return self.update_metadata(record["storage_name"], archived=False)

    def rename_display(self, reference: str, display_name: str) -> tuple[dict, dict]:
        record = self._require(reference)
        renamed = self.registry.rename_display(record["book_id"], display_name)
        return self.update_metadata(renamed["storage_name"], display_name=renamed["display_name"])

    def preview_purge(self, reference: str) -> dict:
        record = self._require(reference)
        storage = record["storage_name"]
        paths = self._candidate_paths(storage)
        return {
            "book_id": record["book_id"],
            "storage_name": storage,
            "display_name": record["display_name"],
            "paths": [str(path) for path in paths if path.exists()],
            "vector_collections": self._vector_collection_names(storage),
            "requires_confirmation": record["book_id"],
            "active_jobs": self._active_jobs(storage),
        }

    def _active_jobs(self, storage_name: str) -> list[dict]:
        from backend.job_manager import JobManager, RUNNING_STATUSES
        path = self.progress_root / 'jobs.sqlite3'
        if not path.exists():
            return []
        return [job for job in JobManager(path).list_jobs(book_name=storage_name, limit=500)
                if job['status'] in RUNNING_STATUSES]

    def purge(self, reference: str, *, confirmation: str, confirmed_name: str = '') -> dict:
        record = self._require(reference)
        if confirmation != record["book_id"]:
            raise ValueError("purge confirmation must exactly match book_id")
        if confirmed_name != record['display_name']:
            raise ValueError('请输入完整教材名称，再确认删除')
        if self._active_jobs(record['storage_name']):
            raise ValueError('教材任务尚未停止，请等待停止确认后再删除')
        deleted: list[str] = []
        errors: list[str] = []
        # Remove live and retained collections before their ownership manifests.
        deleted.extend(self._delete_vector_assets(record['storage_name']))
        for path in self._candidate_paths(record["storage_name"]):
            if not path.exists():
                continue
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                deleted.append(str(path))
            except OSError as exc:
                errors.append(f"{path}: {exc}")
        if errors:
            raise RuntimeError('部分教材资料未能删除，请重试：' + '; '.join(errors))
        from backend.job_manager import JobManager
        if (self.progress_root / 'jobs.sqlite3').exists():
            JobManager(self.progress_root / 'jobs.sqlite3').delete_book_jobs(record['storage_name'])
        for module_name, cache_name in [('knowledge.knowledge_graph', '_kg_cache'),
                                        ('ingestion.lexical_index', '_cache')]:
            module = sys.modules.get(module_name)
            if module is not None:
                getattr(module, cache_name).pop(record['storage_name'], None)
        self.registry.set_status(record["book_id"], "purged")
        return {
            "book_id": record["book_id"],
            "storage_name": record["storage_name"],
            "display_name": record["display_name"],
            "deleted": deleted,
            "status": "purged",
        }

    def _require(self, reference: str) -> dict:
        record = self.registry.resolve(reference, include_archived=True)
        if not record:
            raise KeyError(reference)
        return record

    def _candidate_paths(self, storage_name: str) -> list[Path]:
        safe = safe_book_name(storage_name)
        paths = [
            safe_child_path(self.progress_root, safe),
            Path(BOOKS_PATH) / f"{safe}.pdf",
            safe_child_path(MINERU_OUTPUT_PATH, safe),
            Path(VECTOR_DB_PATH) / "_lexical" / f"{safe}.json",
            Path(VECTOR_DB_PATH) / '_lexical_versions' / safe,
            Path(VECTOR_DB_PATH) / '_index_manifests' / f'{safe}.json',
        ]
        for prefix in ("mistake_book_", "exercise_bank_"):
            base = safe_child_path(self.progress_root, f"{prefix}{safe}.db")
            paths.extend([base, Path(f"{base}-wal"), Path(f"{base}-shm"), Path(f"{base}-journal")])
        metadata = self.read_metadata(storage_name)
        managed_roots = [
            Path(MINERU_OUTPUT_PATH).resolve(),
            (Path(DATA_DIR) / "uploads").resolve(),
            (Path(DATA_DIR) / "imports").resolve(),
        ]
        for key in ("mineru_output_dir", "source_archive"):
            raw = str(metadata.get(key) or "").strip()
            if not raw:
                continue
            candidate = Path(raw).resolve()
            if any(root in candidate.parents for root in managed_roots):
                paths.append(candidate)
        return list(dict.fromkeys(paths))

    def _vector_collection_names(self, storage_name: str) -> list[str]:
        map_path = Path(VECTOR_DB_PATH) / "_chapter_map.json"
        try:
            mapping = json.loads(map_path.read_text(encoding="utf-8")) if map_path.exists() else {}
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError('无法读取教材索引目录，请修复后再删除') from exc
        names = {
            name
            for name, value in mapping.items()
            if isinstance(value, dict) and value.get("book_name") == safe_book_name(storage_name)
        }
        manifest = Path(VECTOR_DB_PATH) / '_index_manifests' / f'{safe_book_name(storage_name)}.json'
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding='utf-8'))
            for version in data.get('versions', []):
                names.update(version.get('collections', []))
        return sorted(names)

    def _delete_vector_assets(self, storage_name: str) -> list[str]:
        names = self._vector_collection_names(storage_name)
        if not names:
            return []
        import chromadb

        client = chromadb.PersistentClient(path=str(VECTOR_DB_PATH))
        deleted = []
        for name in names:
            try:
                client.delete_collection(name)
            except chromadb.errors.NotFoundError:
                # A stale mapping is still safe to remove.
                pass
            deleted.append(f"chroma:{name}")
        map_path = Path(VECTOR_DB_PATH) / "_chapter_map.json"
        mapping = json.loads(map_path.read_text(encoding="utf-8")) if map_path.exists() else {}
        for name in names:
            mapping.pop(name, None)
        atomic_write_json(map_path, mapping)
        from ingestion.vector_store import reset_vector_store

        reset_vector_store()
        return deleted
