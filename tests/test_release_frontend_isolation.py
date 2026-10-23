"""Exercise the release shell with build-tool stand-ins, without production data."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from backend.static_assets import StaticAssetCompression


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name == "nt", reason="macOS bash entry point")


@pytest.fixture
def release_tree(tmp_path):
    # Spaces also exercise quoting of the staging and PyInstaller source paths.
    root = tmp_path / "release tree"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/build-desktop-backend-macos.sh", root / "scripts")
    (root / "frontend/dist/assets").mkdir(parents=True)
    (root / "frontend/dist/index.html").write_text("old phone shell")
    (root / "frontend/dist/assets/old-abcdefgh.js").write_text("old lazy chunk")
    bin_dir = root / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "build-tool"
    stub.write_text(f"#!{sys.executable}\n" + '''
import json, os, pathlib, shutil, sys
tool, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
root = pathlib.Path.cwd()
version = os.environ.get("FIXTURE_VERSION", "1")
if tool == "uname":
    print("Darwin" if args == ["-s"] else "arm64")
elif tool == "npm":
    source = pathlib.Path(args[args.index("--outDir") + 1])
    assert source.is_dir() and not list(source.iterdir()), "staging must start empty"
    assert "--emptyOutDir" in args
    (source / "assets").mkdir()
    (source / "assets" / f"app-{version}.js").write_text(version)
    (source / "index.html").write_text(f"<script src='/assets/app-{version}.js'></script>")
    if os.environ.get("FAIL_BUILD") == "frontend":
        sys.exit(17)
elif tool == "python" and args[:2] == ["-m", "PyInstaller"]:
    data = [args[i + 1] for i, arg in enumerate(args) if arg == "--add-data"]
    source, target = data[0].rsplit(":", 1)
    assert target == "frontend/dist"
    source = pathlib.Path(source)
    destination = root / "build/backend/backend_server/_internal/frontend/dist"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    with (root / "package-inputs.jsonl").open("a") as stream:
        stream.write(json.dumps({"source": str(source), "files": sorted(
            str(p.relative_to(source)) for p in source.rglob("*") if p.is_file())}) + "\\n")
    if os.environ.get("FAIL_BUILD") == "backend":
        sys.exit(19)
''')
    stub.chmod(0o755)
    for name in ("npm", "python", "uname"):
        (bin_dir / name).symlink_to(stub)
    env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
               TEXA_BUILD_PYTHON=str(bin_dir / "python"))
    return root, env


def run_release(root, env, **settings):
    return subprocess.run(
        ["bash", str(root / "scripts/build-desktop-backend-macos.sh")],
        env=dict(env, **settings), text=True, capture_output=True, timeout=30,
    )


def test_consecutive_releases_package_only_fresh_assets_and_keep_phone_chunks(release_tree):
    root, env = release_tree
    live = root / "frontend/dist"
    before = {str(p.relative_to(live)): p.read_bytes() for p in live.rglob("*") if p.is_file()}
    for version in ("1", "2"):
        result = run_release(root, env, FIXTURE_VERSION=version)
        assert result.returncode == 0, result.stderr
        package = root / "build/backend/backend_server/_internal/frontend/dist"
        assert sorted(str(p.relative_to(package)) for p in package.rglob("*") if p.is_file()) == [
            f"assets/app-{version}.js", "index.html",
        ]
        assert not list((root / "build").glob("frontend-release.*"))
    records = [json.loads(line) for line in (root / "package-inputs.jsonl").read_text().splitlines()]
    assert records[0]["source"] != records[1]["source"]
    assert before == {str(p.relative_to(live)): p.read_bytes() for p in live.rglob("*") if p.is_file()}
    app = FastAPI()
    app.mount("/", StaticAssetCompression(StaticFiles(directory=live)))
    with TestClient(app) as client:
        response = client.get("/assets/old-abcdefgh.js")
        assert response.status_code == 200
        assert response.text == "old lazy chunk"
        assert "immutable" in response.headers["cache-control"]


@pytest.mark.parametrize("stage, code", [("frontend", 17), ("backend", 19)])
def test_failed_release_cleans_only_its_staging_directory(release_tree, stage, code):
    root, env = release_tree
    unrelated = root / "build/frontend-release.other-build"
    unrelated.mkdir(parents=True)
    (unrelated / "keep.js").write_text("another build")
    result = run_release(root, env, FAIL_BUILD=stage)
    assert result.returncode == code, result.stderr
    assert list((root / "build").glob("frontend-release.*")) == [unrelated]
    assert (unrelated / "keep.js").read_text() == "another build"
    assert (root / "frontend/dist/assets/old-abcdefgh.js").read_text() == "old lazy chunk"
    assert (root / "package-inputs.jsonl").exists() is (stage == "backend")
