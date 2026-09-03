"""Downloadable desktop resources: embedding model and optional vector/example bundle."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from fastapi import APIRouter

from config import DATA_DIR, VECTOR_DB_PATH
from ingestion.embedding_assets import embedding_asset_status, repair_embedding_assets
from ingestion.embedding_errors import EmbeddingRuntimeError, classify_embedding_error
from ingestion.index_pipeline import (
    VectorScopeInvariantError,
    require_scoped_vector_snapshot,
)

router = APIRouter(prefix="/assets", tags=["assets"])

ASSET_MANIFEST_VERSION = 1
EMBEDDING_REPO_ID = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh-v1.5")
EMBEDDING_REVISION = os.getenv("EMBEDDING_MODEL_REVISION", "main")
HF_ENDPOINT = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
VECTOR_BUNDLE_URL = os.getenv("KAOYAN_VECTOR_BUNDLE_URL", "")
VECTOR_BUNDLE_SHA256 = os.getenv("KAOYAN_VECTOR_BUNDLE_SHA256", "")
VECTOR_BUNDLE_VERSION = os.getenv("KAOYAN_VECTOR_BUNDLE_VERSION", "demo-v1")

MANIFEST_PATH = Path(DATA_DIR) / "desktop_assets.json"
DOWNLOAD_DIR = Path(DATA_DIR) / "downloads"
MODEL_CACHE_DIR = Path(DATA_DIR) / "models"


def _safe_public_text(value: str, fallback: str = "") -> str:
    value = str(value or "")
    if re.search(r"sk-[A-Za-z0-9_\-]{8,}", value):
        return fallback
    if re.search(r"(?i)api[_-]?key\s*[=:]", value):
        return fallback
    return value


def _safe_repo_id(value: str) -> str:
    value = _safe_public_text(value, "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        return "BAAI/bge-small-zh-v1.5"
    return value


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _read_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"schema_version": ASSET_MANIFEST_VERSION, "assets": {}}
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("schema_version", ASSET_MANIFEST_VERSION)
            data.setdefault("assets", {})
            return data
    except Exception:
        pass
    return {"schema_version": ASSET_MANIFEST_VERSION, "assets": {}}


def _write_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _embedding_snapshot_path() -> Path | None:
    safe_repo_id = _safe_repo_id(EMBEDDING_REPO_ID)
    snapshots = MODEL_CACHE_DIR / f"models--{safe_repo_id.replace('/', '--')}" / "snapshots"
    if not snapshots.exists():
        return None
    candidates = [item for item in snapshots.iterdir() if item.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime)


def _embedding_status(manifest: dict) -> dict:
    status = embedding_asset_status(full_hash=False)
    return {
        "id": "embedding_model",
        "label": "ONNX embedding runtime",
        "installed": status.get("present", False),
        "version_match": status.get("compatible", False),
        **status,
    }


def _vector_status(manifest: dict) -> dict:
    item = manifest.get("assets", {}).get("vector_bundle", {})
    db_path = Path(VECTOR_DB_PATH) / "chroma.sqlite3"
    installed = db_path.exists()
    version_match = installed and (not item or item.get("version") == VECTOR_BUNDLE_VERSION)
    result = {
        "id": "vector_bundle",
        "label": "Example vector database",
        "installed": installed,
        "version_match": version_match,
        "status": "ready" if version_match else "missing" if not installed else "version_mismatch",
        "version": VECTOR_BUNDLE_VERSION,
        "url_configured": bool(VECTOR_BUNDLE_URL),
        "path": str(VECTOR_DB_PATH),
        "installed_at": item.get("installed_at", ""),
    }
    if installed:
        try:
            require_scoped_vector_snapshot(Path(VECTOR_DB_PATH))
        except VectorScopeInvariantError as exc:
            result.update({
                "healthy": False,
                "vector_ready": False,
                "status": "missing",
                "error_code": exc.error_code,
                "reindex_required": True,
            })
    return result


def _safe_extract(zip_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_root = target_dir.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            dest = (target_dir / member.filename).resolve()
            if not str(dest).startswith(str(target_root)):
                raise ValueError(f"Archive contains an unsafe path: {member.filename}")
        zf.extractall(target_dir)


def _download_file(url: str, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with requests.get(url, stream=True, timeout=(10, 120)) as response:
        response.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                digest.update(chunk)
                fh.write(chunk)
    return digest.hexdigest()


@router.get("/status")
def assets_status():
    manifest = _read_manifest()
    embedding = _embedding_status(manifest)
    vector = _vector_status(manifest)
    needs_setup = embedding["status"] != "ready" or vector["status"] != "ready"
    return {
        "success": True,
        "data": {
            "needs_setup": needs_setup,
            "manifest_path": str(MANIFEST_PATH),
            "assets": {
                "embedding_model": embedding,
                "vector_bundle": vector,
            },
        },
    }


@router.post("/download/embedding")
def download_embedding():
    """Compatibility alias for the versioned ONNX repair operation."""
    return repair_embedding()


@router.post("/repair/embedding")
def repair_embedding():
    try:
        result = repair_embedding_assets()
        from config import get_embeddings, reset_embeddings
        from ingestion.vector_store import reset_vector_store

        reset_vector_store()
        reset_embeddings()
        get_embeddings()
        return {
            "success": True,
            "message": "ONNX embedding runtime repaired and reinitialized.",
            "data": {**result, "runtime": embedding_asset_status(full_hash=False)},
        }
    except EmbeddingRuntimeError as exc:
        return {
            "success": False,
            "message": "ONNX embedding runtime repair failed.",
            "error": exc.as_dict(),
        }
    except Exception as exc:
        diagnosed = classify_embedding_error(exc, stage="asset_repair")
        return {
            "success": False,
            "message": "ONNX embedding runtime repair failed.",
            "error": diagnosed.as_dict(),
        }


@router.post("/download/vector-bundle")
def download_vector_bundle():
    if not VECTOR_BUNDLE_URL:
        return {"success": False, "message": "KAOYAN_VECTOR_BUNDLE_URL is not configured."}
    try:
        parsed = urlparse(VECTOR_BUNDLE_URL)
        suffix = Path(parsed.path).suffix or ".zip"
        archive = DOWNLOAD_DIR / f"vector_bundle_{VECTOR_BUNDLE_VERSION}{suffix}"
        digest = _download_file(VECTOR_BUNDLE_URL, archive)
        if VECTOR_BUNDLE_SHA256 and digest.lower() != VECTOR_BUNDLE_SHA256.lower():
            archive.unlink(missing_ok=True)
            return {"success": False, "message": "Vector bundle checksum mismatch."}

        staging = DOWNLOAD_DIR / f"vector_bundle_{VECTOR_BUNDLE_VERSION}_staging"
        if staging.exists():
            shutil.rmtree(staging)
        _safe_extract(archive, staging)

        candidates = [staging / "vector_db", staging / "data" / "vector_db"]
        source = next((item for item in candidates if item.exists()), None)
        if not source:
            return {"success": False, "message": "vector_db directory was not found in the archive."}

        require_scoped_vector_snapshot(source)
        vector_target = Path(VECTOR_DB_PATH)
        if vector_target.exists():
            backup = vector_target.with_name(f"{vector_target.name}.backup-{int(time.time())}")
            shutil.move(str(vector_target), str(backup))
        shutil.copytree(source, vector_target)
        try:
            from ingestion.vector_store import reset_vector_store
            reset_vector_store()
        except Exception as reset_exc:
            print(f"[assets] vector store cache reset failed: {reset_exc}", flush=True)

        manifest = _read_manifest()
        manifest.setdefault("assets", {})["vector_bundle"] = {
            "version": VECTOR_BUNDLE_VERSION,
            "url": VECTOR_BUNDLE_URL,
            "sha256": digest,
            "path": str(vector_target),
            "installed_at": _now(),
        }
        _write_manifest(manifest)
        return {"success": True, "message": "Vector bundle installed.", "data": _vector_status(manifest)}
    except VectorScopeInvariantError as exc:
        return {
            "success": False,
            "message": "Vector bundle requires a scoped index rebuild.",
            "error_code": exc.error_code,
        }
    except Exception as exc:
        return {"success": False, "message": f"Vector bundle download failed: {exc}"}
