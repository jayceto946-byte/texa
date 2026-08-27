from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = "/app/assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1"


def test_docker_image_bundles_and_verifies_the_standard_embedding_runtime():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY requirements-release.txt ./" in dockerfile
    assert "python -m pip install -r requirements-release.txt" in dockerfile
    assert "COPY assets/embedding-runtime/ ./assets/embedding-runtime/" in dockerfile
    assert "TEXA_EMBEDDING_BACKEND=onnx" in dockerfile
    assert f"TEXA_EMBEDDING_ASSET_DIR={ASSET_DIR}" in dockerfile
    assert "validate_asset_dir" in dockerfile
    assert f"validate_asset_dir('{ASSET_DIR}', full_hash=True)" in dockerfile


def test_compose_preserves_the_bundled_offline_embedding_contract():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert 'EMBEDDING_LOCAL_FILES_ONLY: "1"' in compose
    assert "TEXA_EMBEDDING_BACKEND: onnx" in compose
    assert f"TEXA_EMBEDDING_ASSET_DIR: {ASSET_DIR}" in compose
