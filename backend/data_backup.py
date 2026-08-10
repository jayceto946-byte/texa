"""Consistent local backups and restart-safe restore scheduling."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_DIR, MINERU_OUTPUT_PATH
from backend.backup_migrations import BACKUP_SCHEMA_VERSION, migrate_backup_manifest
from utils.storage_manifest import COMPONENT_VERSIONS, DATA_CLASSES, DATA_SCHEMA_VERSION, ensure_storage_manifest
from utils.version import APP_VERSION


DATA_ROOT = Path(DATA_DIR).resolve()
MINERU_ROOT = Path(MINERU_OUTPUT_PATH).resolve()
BACKUP_ROOT = Path(os.getenv("BACKUP_PATH", str(DATA_ROOT.parent / "backups"))).resolve()
PENDING_RESTORE_PATH = BACKUP_ROOT / "pending_restore.json"
RESTORE_RESULT_PATH = BACKUP_ROOT / "last_restore.json"
CORE_ROOTS = ("progress", "images", "books", "chapters", "imports", "uploads")
CORE_FILES = ("storage_manifest.json",)
DERIVED_ROOTS = ("vector_db",)
MAX_ARCHIVE_FILES = 200_000
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024 * 1024
_operation_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _copy_consistent_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    lower = source.name.lower()
    if lower.endswith(("-wal", "-shm", "-journal")):
        return
    is_sqlite = source.suffix.lower() in {".db", ".sqlite", ".sqlite3"} or lower == "chroma.sqlite3"
    if is_sqlite:
        try:
            with sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=10) as src:
                with sqlite3.connect(str(destination), timeout=10) as dst:
                    src.backup(dst)
            with sqlite3.connect(f"file:{destination}?mode=ro", uri=True, timeout=10) as verified:
                check = verified.execute("PRAGMA quick_check").fetchone()
            if not check or check[0] != "ok":
                raise sqlite3.DatabaseError(
                    f"SQLite snapshot integrity check failed for {source}: {check}"
                )
            return
        except sqlite3.DatabaseError as exc:
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"consistent SQLite snapshot failed: {source}: {exc}") from exc
    shutil.copy2(source, destination)


def _snapshot_tree(source: Path, destination: Path) -> tuple[int, int]:
    file_count = 0
    total_bytes = 0
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(source)
        target = destination / relative
        _copy_consistent_file(item, target)
        if target.exists():
            file_count += 1
            total_bytes += target.stat().st_size
    return file_count, total_bytes


def _archive_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_label(value: str) -> str:
    label = re.sub(r"[^0-9A-Za-z_-]+", "_", value.strip()).strip("_")
    return label[:32] or "manual"


def create_backup(*, include_derived: bool = False, reason: str = "manual") -> dict:
    """Create a verified zip backup without copying API keys or environment files."""
    if not _operation_lock.acquire(blocking=False):
        raise RuntimeError("已有备份或恢复操作正在进行")
    try:
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        archive_name = f"learning_data_{timestamp}_{_safe_label(reason)}.zip"
        archive_path = BACKUP_ROOT / archive_name
        with tempfile.TemporaryDirectory(prefix="backup_", dir=str(BACKUP_ROOT)) as temp_name:
            snapshot = Path(temp_name) / "snapshot"
            snapshot.mkdir(parents=True, exist_ok=True)
            included: list[str] = []
            file_count = 0
            total_bytes = 0
            roots = list(CORE_ROOTS) + (list(DERIVED_ROOTS) if include_derived else [])
            for root_name in roots:
                source = DATA_ROOT / root_name
                if not source.exists():
                    continue
                count, size = _snapshot_tree(source, snapshot / "data" / root_name)
                file_count += count
                total_bytes += size
                included.append(f"data/{root_name}")
            ensure_storage_manifest(DATA_ROOT)
            for file_name in CORE_FILES:
                source = DATA_ROOT / file_name
                if not source.exists():
                    continue
                target = snapshot / "data" / file_name
                _copy_consistent_file(source, target)
                if target.exists():
                    file_count += 1
                    total_bytes += target.stat().st_size
                    included.append(f"data/{file_name}")
            if include_derived and MINERU_ROOT.exists():
                count, size = _snapshot_tree(MINERU_ROOT, snapshot / "mineru_output")
                file_count += count
                total_bytes += size
                included.append("mineru_output")
            if not included:
                raise RuntimeError("没有可备份的学习数据")
            manifest = {
                "schema_version": BACKUP_SCHEMA_VERSION,
                "format": "kaoyan-learning-backup",
                "data_schema_version": DATA_SCHEMA_VERSION,
                "component_versions": COMPONENT_VERSIONS,
                "data_classes": DATA_CLASSES,
                "app_version": APP_VERSION,
                "created_at": _utc_now(),
                "reason": reason,
                "included": included,
                "file_count": file_count,
                "uncompressed_bytes": total_bytes,
                "contains_secrets": False,
                # Core data restore is deliberately non-destructive. Roots
                # absent from this archive are preserved instead of deleted.
                "restore_mode": "merge",
            }
            (snapshot / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_archive = archive_path.with_suffix(".zip.tmp")
            with zipfile.ZipFile(temp_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for item in snapshot.rglob("*"):
                    if item.is_file():
                        archive.write(item, item.relative_to(snapshot).as_posix())
            with zipfile.ZipFile(temp_archive) as archive:
                if archive.testzip() is not None:
                    raise RuntimeError("备份压缩包校验失败")
            os.replace(temp_archive, archive_path)
        return {
            **manifest,
            "name": archive_name,
            "size": archive_path.stat().st_size,
            "sha256": _archive_digest(archive_path),
        }
    finally:
        _operation_lock.release()


def _safe_archive(name: str) -> Path:
    safe_name = Path(name).name
    if safe_name != name or not safe_name.endswith(".zip"):
        raise ValueError("无效的备份文件名")
    path = (BACKUP_ROOT / safe_name).resolve()
    if path.parent != BACKUP_ROOT or not path.exists():
        raise FileNotFoundError("备份不存在")
    return path


def inspect_backup(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_FILES:
            raise ValueError("备份文件数量超过安全上限")
        expanded = sum(max(0, info.file_size) for info in infos)
        if expanded > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("备份展开大小超过安全上限")
        names = {info.filename for info in infos}
        if "manifest.json" not in names:
            raise ValueError("备份缺少 manifest.json")
        manifest = migrate_backup_manifest(json.loads(archive.read("manifest.json").decode("utf-8")))
        allowed = {f"data/{name}" for name in CORE_ROOTS + DERIVED_ROOTS + CORE_FILES} | {"mineru_output"}
        included = manifest.get("included") or []
        if not included or any(item not in allowed for item in included):
            raise ValueError("备份包含不支持的数据目录")
        for file_name in CORE_FILES:
            entry = f"data/{file_name}"
            if entry in included and entry not in names:
                raise ValueError(f"备份声明了缺失文件：{entry}")
        for info in infos:
            parts = Path(info.filename.replace("\\", "/")).parts
            if info.filename.startswith("/") or ".." in parts:
                raise ValueError("备份包含不安全路径")
        return manifest


def list_backups() -> list[dict]:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted(BACKUP_ROOT.glob("learning_data_*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            manifest = inspect_backup(path)
            result.append({
                **manifest,
                "name": path.name,
                "size": path.stat().st_size,
                "sha256": _archive_digest(path),
                "valid": True,
            })
        except Exception as exc:
            result.append({"name": path.name, "size": path.stat().st_size, "valid": False, "error": str(exc)})
    return result


def schedule_restore(name: str) -> dict:
    archive = _safe_archive(name)
    manifest = inspect_backup(archive)
    # A restore invalidates any derived data that is absent from the selected
    # archive. Keep a complete pre-restore snapshot so that invalidation is
    # recoverable instead of silently discarding expensive local artifacts.
    safety_backup = create_backup(include_derived=True, reason="pre_restore")
    payload = {
        "schema_version": 1,
        "archive": archive.name,
        "scheduled_at": _utc_now(),
        "safety_backup": safety_backup["name"],
        "restore_mode": "merge",
    }
    _atomic_json(PENDING_RESTORE_PATH, payload)
    return {**payload, "restart_required": True}


def _extract_checked(archive_path: Path, destination: Path) -> dict:
    manifest = inspect_backup(archive_path)
    root = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            target = (destination / info.filename).resolve()
            if target != root and root not in target.parents:
                raise ValueError("备份路径越界")
        archive.extractall(destination)
    return manifest


def apply_pending_restore() -> dict | None:
    """Apply a scheduled restore before warmup opens persistent stores."""
    if not PENDING_RESTORE_PATH.exists():
        return None
    payload: dict = {}
    rollback_root = BACKUP_ROOT / f"restore_rollback_{int(time.time())}"
    moved: list[tuple[Path, Path]] = []
    installed: list[Path] = []
    invalidated: list[str] = []
    preserved_unlisted: list[str] = []
    try:
        payload = json.loads(PENDING_RESTORE_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("pending restore request must be an object")
        archive_path = _safe_archive(str(payload.get("archive") or ""))
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="restore_", dir=str(BACKUP_ROOT)) as temp_name:
            extracted = Path(temp_name) / "extracted"
            manifest = _extract_checked(archive_path, extracted)
            for item in manifest["included"]:
                source = extracted / item
                if not source.exists():
                    source.mkdir(parents=True, exist_ok=True)
                target = MINERU_ROOT if item == "mineru_output" else DATA_ROOT / Path(item).name
                rollback = rollback_root / item
                if target.exists():
                    rollback.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(target), str(rollback))
                    moved.append((rollback, target))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
                installed.append(target)

            included = set(manifest["included"])
            for item in [f"data/{name}" for name in CORE_ROOTS + CORE_FILES]:
                target = DATA_ROOT / Path(item).name
                if item not in included and target.exists():
                    preserved_unlisted.append(item)
            derived_targets = {
                "data/vector_db": DATA_ROOT / "vector_db",
                "mineru_output": MINERU_ROOT,
            }
            for item, target in derived_targets.items():
                if item in included or not target.exists():
                    continue
                rollback = rollback_root / item
                rollback.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(rollback))
                moved.append((rollback, target))
                invalidated.append(item)
        try:
            from ingestion.vector_store import reset_vector_store

            reset_vector_store()
        except Exception:
            pass
        result = {
            **payload,
            "status": "completed",
            "completed_at": _utc_now(),
            "invalidated": invalidated,
            "restore_mode": "merge",
            "preserved_unlisted": preserved_unlisted,
            "reindex_required": "data/vector_db" in invalidated,
        }
        _atomic_json(RESTORE_RESULT_PATH, result)
        shutil.rmtree(rollback_root, ignore_errors=True)
        return result
    except Exception as exc:
        rollback_errors: list[str] = []
        for target in reversed(installed):
            try:
                if target.exists():
                    shutil.rmtree(target) if target.is_dir() else target.unlink()
            except OSError as rollback_exc:
                rollback_errors.append(f"remove {target}: {rollback_exc}")
        for rollback, target in reversed(moved):
            try:
                if rollback.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(rollback), str(target))
            except OSError as rollback_exc:
                rollback_errors.append(f"restore {target}: {rollback_exc}")
        result = {
            **payload,
            "status": "failed",
            "failed_at": _utc_now(),
            "error": str(exc),
            "rollback_errors": rollback_errors,
        }
        try:
            _atomic_json(RESTORE_RESULT_PATH, result)
        except OSError:
            pass
        return result
    finally:
        # A bad or missing archive must not leave a poison-pill request that
        # prevents every subsequent backend start.
        try:
            PENDING_RESTORE_PATH.unlink(missing_ok=True)
        except OSError:
            pass


def restore_status() -> dict:
    pending = json.loads(PENDING_RESTORE_PATH.read_text(encoding="utf-8")) if PENDING_RESTORE_PATH.exists() else None
    last = json.loads(RESTORE_RESULT_PATH.read_text(encoding="utf-8")) if RESTORE_RESULT_PATH.exists() else None
    return {"pending": pending, "last": last, "backup_path": str(BACKUP_ROOT)}
