"""Experimental packaged backend entrypoint for the Phase 2 candidate only."""
from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from desktop.backend_server import _bundle_root, _seed_sample_data


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

    from evaluation.embedding_backend.phase2_runtime import install_candidate_provider

    install_candidate_provider()
    from backend.main import app

    config = uvicorn.Config(
        app,
        host=os.getenv("KAOYAN_BACKEND_HOST", "127.0.0.1"),
        port=int(os.getenv("KAOYAN_BACKEND_PORT", "8000")),
        reload=False,
        access_log=False,
    )
    server = uvicorn.Server(config)
    app.state.desktop_server = server
    server.run()


if __name__ == "__main__":
    main()
