"""Packaged FastAPI entrypoint for the Electron desktop shell."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import uvicorn


ASSET_MANIFEST_VERSION = 1
VECTOR_BUNDLE_VERSION = "demo-v1"


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]


def _iter_seed_files(sample_dir: Path, *, exclude_roots: set[str] | None = None) -> list[Path]:
    ignored = {".gitkeep", "README.md"}
    excluded = exclude_roots or set()
    return [
        p for p in sample_dir.rglob("*")
        if p.is_file()
        and p.name not in ignored
        and p.relative_to(sample_dir).parts[0] not in excluded
    ]


def _copy_missing_seed_files(sample_dir: Path, data_dir: Path, *, exclude_roots: set[str] | None = None) -> int:
    copied = 0
    for src in _iter_seed_files(sample_dir, exclude_roots=exclude_roots):
        rel = src.relative_to(sample_dir)
        dest = data_dir / rel
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    return copied


def _write_asset_manifest(data_dir: Path) -> None:
    manifest_path = data_dir / "desktop_assets.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    except Exception:
        manifest = {}

    manifest.setdefault("schema_version", ASSET_MANIFEST_VERSION)
    assets = manifest.setdefault("assets", {})
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    vector_db = data_dir / "vector_db"
    if (vector_db / "chroma.sqlite3").exists():
        assets.setdefault("vector_bundle", {
            "version": VECTOR_BUNDLE_VERSION,
            "url": "bundled://desktop/sample_data/vector_db",
            "sha256": "",
            "path": str(vector_db),
            "installed_at": now,
        })

    if assets:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_sample_data(data_dir: Path) -> None:
    sample_dir_str = os.getenv("KAOYAN_SEED_DATA_DIR", "")
    sample_dir = Path(sample_dir_str) if sample_dir_str else (_bundle_root() / "sample_data")
    if not sample_dir.exists():
        return

    real_files = _iter_seed_files(sample_dir)
    if not real_files:
        return

    data_dir.mkdir(parents=True, exist_ok=True)
    copied = _copy_missing_seed_files(sample_dir, data_dir, exclude_roots={"mineru_output"})
    mineru_seed = sample_dir / "mineru_output"
    if mineru_seed.exists():
        copied += _copy_missing_seed_files(mineru_seed, data_dir.parent / "mineru_output")
    marker = data_dir / ".sample_data_seeded"
    marker.write_text(f"seeded_at={time.strftime('%Y-%m-%dT%H:%M:%S')}\ncopied={copied}\nsource={sample_dir}\n", encoding="utf-8")
    _write_asset_manifest(data_dir)


def main() -> None:
    root = _bundle_root()
    os.chdir(root)

    data_dir = Path(os.getenv("DATA_DIR", root / "data"))
    os.environ.setdefault("DATA_DIR", str(data_dir))
    os.environ.setdefault("ENV_PATH", str(data_dir.parent / ".env"))
    os.environ.setdefault("MINERU_OUTPUT_PATH", str(data_dir.parent / "mineru_output"))
    os.environ.setdefault("SKIP_VECTOR_WARMUP", "0")
    os.environ.setdefault("SKIP_EMBEDDING_WARMUP", "0")
    os.environ.setdefault("EMBEDDING_LOCAL_FILES_ONLY", "1")

    _seed_sample_data(data_dir)

    port = int(os.getenv("KAOYAN_BACKEND_PORT", "8000"))
    from backend.main import app

    config = uvicorn.Config(
        app,
        host=os.getenv("KAOYAN_BACKEND_HOST", "127.0.0.1"),
        port=port,
        reload=False,
        access_log=False,
    )
    server = uvicorn.Server(config)
    app.state.desktop_server = server
    server.run()


if __name__ == "__main__":
    main()
