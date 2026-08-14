import hashlib
import json
from pathlib import Path

import pytest

from ingestion.embedding_assets import ensure_supported_architecture, repair_embedding_assets, validate_asset_dir
from ingestion.embedding_errors import EmbeddingRuntimeError, classify_embedding_error


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_assets(root: Path) -> Path:
    root.mkdir(parents=True)
    files = {
        "model.onnx": b"frozen-fp32-graph",
        "tokenizer.json": b"{}",
        "tokenizer_config.json": json.dumps({"model_max_length": 512}).encode(),
        "sentence_bert_config.json": json.dumps({"max_seq_length": 512, "do_lower_case": True}).encode(),
    }
    for name, content in files.items():
        (root / name).write_bytes(content)
    manifest = {
        "manifest_version": 1,
        "asset_type": "embedding_runtime",
        "model_name": "BAAI/bge-small-zh-v1.5",
        "model_version": "7999e1d3359715c523056ef9478215996d62a620",
        "onnx_graph_version": "onnx-fp32-v1",
        "embedding_dimension": 512,
        "dtype": "float32",
        "pooling": "cls",
        "normalization": "l2_in_graph_twice",
        "max_length": 512,
        "padding": "right",
        "truncation": "right",
        "tokenizer_version": "fixture",
        "minimum_texa_version": "1.0.0",
        "expected_files": [
            {"path": name, "size": len(content), "sha256": _sha(root / name)}
            for name, content in files.items()
        ],
        "repair_sources": [{"type": "bundled", "name": "fixture"}],
    }
    (root / "embedding-runtime.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_asset_validation_distinguishes_missing_and_corrupt(tmp_path):
    assets = make_assets(tmp_path / "assets")
    validate_asset_dir(assets, full_hash=True)

    (assets / "model.onnx").write_bytes(b"wrong-size")
    with pytest.raises(EmbeddingRuntimeError) as error:
        validate_asset_dir(assets, full_hash=True)
    assert error.value.code == "MODEL_CORRUPT_OR_INCOMPATIBLE"

    (assets / "model.onnx").unlink()
    with pytest.raises(EmbeddingRuntimeError) as error:
        validate_asset_dir(assets, full_hash=False)
    assert error.value.code == "MODEL_MISSING"


def test_tokenizer_contract_has_a_typed_failure(tmp_path):
    assets = make_assets(tmp_path / "assets")
    config = json.loads((assets / "sentence_bert_config.json").read_text())
    config["do_lower_case"] = False
    content = json.dumps(config).encode()
    (assets / "sentence_bert_config.json").write_bytes(content)
    manifest = json.loads((assets / "embedding-runtime.json").read_text())
    item = next(item for item in manifest["expected_files"] if item["path"] == "sentence_bert_config.json")
    item.update(size=len(content), sha256=_sha(assets / "sentence_bert_config.json"))
    (assets / "embedding-runtime.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(EmbeddingRuntimeError) as error:
        validate_asset_dir(assets, full_hash=True)
    assert error.value.code == "TOKENIZER_MISMATCH"


def test_missing_sentence_transformer_tokenizer_config_is_typed(tmp_path):
    assets = make_assets(tmp_path / "assets")
    (assets / "sentence_bert_config.json").unlink()

    with pytest.raises(EmbeddingRuntimeError) as error:
        validate_asset_dir(assets)
    assert error.value.code == "TOKENIZER_MISMATCH"


def test_ort_import_and_unsupported_architecture_are_typed(monkeypatch):
    classified = classify_embedding_error(
        ImportError("DLL load failed while importing onnxruntime_pybind11_state")
    )
    assert classified.code == "ORT_IMPORT_FAILURE"
    assert classified.failure.recoverable is True

    monkeypatch.setenv("TEXA_REQUIRE_WINDOWS_X64", "1")
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "aarch64")
    with pytest.raises(EmbeddingRuntimeError) as error:
        ensure_supported_architecture()
    assert error.value.code == "UNSUPPORTED_ARCHITECTURE"
    assert error.value.failure.recoverable is False


def test_repair_installs_verified_version_without_overwriting_source(tmp_path, monkeypatch):
    source = make_assets(tmp_path / "source")
    data_dir = tmp_path / "user-data"
    monkeypatch.setattr("config.DATA_DIR", data_dir)

    result = repair_embedding_assets(source)

    pointer = json.loads((data_dir / "embedding_runtime" / "active.json").read_text())
    installed = data_dir / "embedding_runtime" / pointer["asset_dir"]
    assert result["status"] == "repaired"
    assert installed != source
    assert validate_asset_dir(installed, full_hash=True)["embedding_dimension"] == 512
    assert (source / "model.onnx").read_bytes() == b"frozen-fp32-graph"


def test_offline_remote_repair_returns_typed_failure(tmp_path, monkeypatch):
    source = make_assets(tmp_path / "source")
    (source / "model.onnx").write_bytes(b"corrupt")
    manifest = json.loads((source / "embedding-runtime.json").read_text())
    manifest["repair_sources"] = [
        {"type": "http_files", "base_url": "https://assets.example.invalid/onnx-fp32-v1"}
    ]
    (source / "embedding-runtime.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr("config.DATA_DIR", tmp_path / "user-data")
    monkeypatch.setattr("ingestion.embedding_assets.bundled_asset_candidates", lambda: [source])
    monkeypatch.setattr(
        "ingestion.embedding_assets.requests.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("offline")),
    )

    with pytest.raises(EmbeddingRuntimeError) as error:
        repair_embedding_assets()
    assert error.value.code == "ASSET_REPAIR_FAILED"
    assert error.value.failure.recoverable is True
