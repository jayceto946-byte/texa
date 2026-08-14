"""Versioned ONNX asset discovery, verification and atomic repair."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shutil
import sys
import time
import uuid
from pathlib import Path

import requests

from ingestion.embedding_errors import EmbeddingRuntimeError


logger = logging.getLogger(__name__)
MODEL_SLUG = "bge-small-zh-v1.5"
GRAPH_VERSION = "onnx-fp32-v1"
MANIFEST_NAME = "embedding-runtime.json"
EXPECTED_MODEL = "BAAI/bge-small-zh-v1.5"
EXPECTED_MODEL_VERSION = "7999e1d3359715c523056ef9478215996d62a620"
EXPECTED_DIMENSION = 512
ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise EmbeddingRuntimeError(
            "MODEL_CORRUPT_OR_INCOMPATIBLE",
            f"Cannot read embedding manifest {path}: {exc}",
            stage="asset_verify",
        ) from exc
    if not isinstance(value, dict):
        raise EmbeddingRuntimeError(
            "MODEL_CORRUPT_OR_INCOMPATIBLE",
            f"Embedding manifest is not an object: {path}",
            stage="asset_verify",
        )
    return value


def ensure_supported_architecture() -> None:
    strict = getattr(sys, "frozen", False) or os.getenv("TEXA_REQUIRE_WINDOWS_X64", "0") == "1"
    if not strict:
        return
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system != "windows" or machine not in {"amd64", "x86_64"}:
        raise EmbeddingRuntimeError(
            "UNSUPPORTED_ARCHITECTURE",
            f"Texa Standard ONNX runtime supports Windows x64; detected {system}/{machine}",
            stage="runtime_check",
            recoverable=False,
            repair_action="install_supported_windows_x64_release",
        )


def _validate_contract(manifest: dict) -> None:
    expected = {
        "asset_type": "embedding_runtime",
        "model_name": EXPECTED_MODEL,
        "model_version": EXPECTED_MODEL_VERSION,
        "onnx_graph_version": GRAPH_VERSION,
        "embedding_dimension": EXPECTED_DIMENSION,
        "dtype": "float32",
        "pooling": "cls",
        "normalization": "l2_in_graph_twice",
        "max_length": 512,
        "padding": "right",
        "truncation": "right",
    }
    mismatches = [
        f"{key}={manifest.get(key)!r} (expected {value!r})"
        for key, value in expected.items()
        if manifest.get(key) != value
    ]
    if mismatches:
        raise EmbeddingRuntimeError(
            "MODEL_CORRUPT_OR_INCOMPATIBLE",
            "Embedding asset contract mismatch: " + "; ".join(mismatches),
            stage="asset_verify",
        )


def _is_tokenizer_asset(relative: str) -> bool:
    name = Path(relative).name.lower()
    return (
        "token" in name
        or "vocab" in name
        or name in {"sentence_bert_config.json", "special_tokens_map.json"}
    )


def validate_asset_dir(asset_dir: Path | str, *, full_hash: bool = False) -> dict:
    directory = Path(asset_dir).resolve()
    manifest_path = directory / MANIFEST_NAME
    if not manifest_path.is_file():
        raise EmbeddingRuntimeError(
            "MODEL_MISSING",
            f"Embedding manifest is missing: {manifest_path}",
            stage="asset_verify",
        )
    manifest = _load_json(manifest_path)
    _validate_contract(manifest)
    expected_files = manifest.get("expected_files")
    if not isinstance(expected_files, list) or not expected_files:
        raise EmbeddingRuntimeError(
            "MODEL_CORRUPT_OR_INCOMPATIBLE",
            "Embedding manifest has no expected_files",
            stage="asset_verify",
        )
    for item in expected_files:
        relative = str(item.get("path") or "")
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise EmbeddingRuntimeError(
                "MODEL_CORRUPT_OR_INCOMPATIBLE",
                f"Unsafe embedding asset path: {relative!r}",
                stage="asset_verify",
            )
        path = directory / relative
        if not path.is_file():
            code = "TOKENIZER_MISMATCH" if _is_tokenizer_asset(relative) else "MODEL_MISSING"
            raise EmbeddingRuntimeError(code, f"Embedding asset is missing: {path}", stage="asset_verify")
        expected_size = int(item.get("size") or -1)
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            code = "TOKENIZER_MISMATCH" if _is_tokenizer_asset(relative) else "MODEL_CORRUPT_OR_INCOMPATIBLE"
            raise EmbeddingRuntimeError(
                code,
                f"Embedding asset size mismatch for {relative}: {actual_size} != {expected_size}",
                stage="asset_verify",
            )
        if full_hash:
            actual_hash = _sha256(path)
            expected_hash = str(item.get("sha256") or "").lower()
            if actual_hash.lower() != expected_hash:
                code = "TOKENIZER_MISMATCH" if _is_tokenizer_asset(relative) else "MODEL_CORRUPT_OR_INCOMPATIBLE"
                raise EmbeddingRuntimeError(
                    code,
                    f"Embedding asset SHA-256 mismatch for {relative}",
                    stage="asset_verify",
                )
    sentence_config = _load_json(directory / "sentence_bert_config.json")
    tokenizer_config = _load_json(directory / "tokenizer_config.json")
    if sentence_config.get("do_lower_case") is not True or int(sentence_config.get("max_seq_length") or 0) != 512:
        raise EmbeddingRuntimeError(
            "TOKENIZER_MISMATCH",
            "sentence_bert_config.json does not preserve lowercase/max_length parity",
            stage="asset_verify",
        )
    if int(tokenizer_config.get("model_max_length") or 0) != 512:
        raise EmbeddingRuntimeError(
            "TOKENIZER_MISMATCH",
            "tokenizer_config.json model_max_length is not 512",
            stage="asset_verify",
        )
    return manifest


def _active_override() -> Path | None:
    from config import DATA_DIR

    pointer = Path(DATA_DIR) / "embedding_runtime" / "active.json"
    if not pointer.is_file():
        return None
    try:
        relative = str(json.loads(pointer.read_text(encoding="utf-8")).get("asset_dir") or "")
        root = pointer.parent.resolve()
        candidate = (root / relative).resolve()
        if relative and (candidate == root or root in candidate.parents):
            return candidate
    except Exception:
        logger.warning("Ignoring invalid embedding active pointer: %s", pointer, exc_info=True)
    return None


def bundled_asset_candidates() -> list[Path]:
    configured = os.getenv("TEXA_EMBEDDING_ASSET_DIR", "").strip()
    values: list[Path] = []
    if configured:
        values.append(Path(configured))
    values.append(ROOT / "assets" / "embedding-runtime" / MODEL_SLUG / GRAPH_VERSION)
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        values.extend([
            executable.parent / "embedding-runtime" / MODEL_SLUG / GRAPH_VERSION,
            executable.parents[2] / "embedding-runtime" / MODEL_SLUG / GRAPH_VERSION,
            Path(getattr(sys, "_MEIPASS", executable.parent)) / "embedding-runtime" / MODEL_SLUG / GRAPH_VERSION,
        ])
    seen: set[Path] = set()
    return [value for value in values if not (value.resolve() in seen or seen.add(value.resolve()))]


def resolve_embedding_assets(*, full_hash: bool = False) -> tuple[Path, dict]:
    ensure_supported_architecture()
    configured_graph = os.getenv("EMBEDDING_ONNX_PATH", "").strip()
    candidates: list[Path] = []
    active = _active_override()
    if active:
        candidates.append(active)
    if configured_graph:
        graph = Path(configured_graph)
        candidates.append(graph.parent if graph.name == "model.onnx" else graph)
    candidates.extend(bundled_asset_candidates())
    failures: list[EmbeddingRuntimeError] = []
    for candidate in candidates:
        try:
            manifest = validate_asset_dir(candidate, full_hash=full_hash)
            return candidate.resolve(), manifest
        except EmbeddingRuntimeError as exc:
            failures.append(exc)
    if failures and any(error.code != "MODEL_MISSING" for error in failures):
        raise next(error for error in failures if error.code != "MODEL_MISSING")
    searched = ", ".join(str(path) for path in candidates)
    raise EmbeddingRuntimeError(
        "MODEL_MISSING",
        f"Versioned ONNX embedding runtime was not found; searched: {searched}",
        stage="asset_verify",
    )


def embedding_asset_status(*, full_hash: bool = False) -> dict:
    try:
        asset_dir, manifest = resolve_embedding_assets(full_hash=full_hash)
        return {
            "status": "ready",
            "present": True,
            "compatible": True,
            "asset_dir": str(asset_dir),
            "model_name": manifest["model_name"],
            "model_version": manifest["model_version"],
            "onnx_graph_version": manifest["onnx_graph_version"],
            "embedding_dimension": manifest["embedding_dimension"],
            "verification": "sha256" if full_hash else "contract_and_size",
        }
    except EmbeddingRuntimeError as exc:
        return {"status": "error", "present": exc.code != "MODEL_MISSING", "compatible": False, "failure": exc.as_dict()}


def _copy_source(source: Path, staging: Path, manifest: dict) -> None:
    for item in manifest["expected_files"]:
        relative = str(item["path"])
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
    shutil.copy2(source / MANIFEST_NAME, staging / MANIFEST_NAME)


def _download_source(staging: Path, manifest: dict) -> None:
    sources = [item for item in manifest.get("repair_sources", []) if item.get("type") == "http_files"]
    if not sources:
        raise EmbeddingRuntimeError(
            "MODEL_MISSING", "No HTTP repair source is configured", stage="asset_repair"
        )
    base_url = str(sources[0].get("base_url") or "").rstrip("/")
    if not base_url.startswith("https://"):
        raise EmbeddingRuntimeError(
            "MODEL_CORRUPT_OR_INCOMPATIBLE", "Repair source must use HTTPS", stage="asset_repair"
        )
    for item in manifest["expected_files"]:
        relative = str(item["path"])
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with requests.get(f"{base_url}/{relative}", stream=True, timeout=(10, 120)) as response:
                response.raise_for_status()
                with destination.open("wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            stream.write(chunk)
        except Exception as exc:
            raise EmbeddingRuntimeError(
                "ASSET_REPAIR_FAILED",
                f"Could not download {relative}: {exc}",
                stage="asset_repair",
            ) from exc
    (staging / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def repair_embedding_assets(source_dir: Path | str | None = None) -> dict:
    """Install a verified user override without replacing files in active use."""
    from config import DATA_DIR

    runtime_root = Path(DATA_DIR) / "embedding_runtime"
    staging = runtime_root / ".staging" / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=False)
    selected_source: Path | None = Path(source_dir).resolve() if source_dir else None
    trusted_manifest: dict | None = None
    try:
        if selected_source:
            trusted_manifest = validate_asset_dir(selected_source, full_hash=True)
        else:
            for candidate in bundled_asset_candidates():
                try:
                    trusted_manifest = validate_asset_dir(candidate, full_hash=True)
                    selected_source = candidate.resolve()
                    break
                except EmbeddingRuntimeError:
                    manifest_path = candidate / MANIFEST_NAME
                    if trusted_manifest is None and manifest_path.is_file():
                        candidate_manifest = _load_json(manifest_path)
                        _validate_contract(candidate_manifest)
                        trusted_manifest = candidate_manifest
                    continue
            if trusted_manifest is None:
                project_manifest = ROOT / "assets" / "embedding-runtime" / MODEL_SLUG / GRAPH_VERSION / MANIFEST_NAME
                if not project_manifest.is_file():
                    raise EmbeddingRuntimeError(
                        "MODEL_MISSING", "Trusted embedding manifest is unavailable", stage="asset_repair"
                    )
                trusted_manifest = _load_json(project_manifest)
                _validate_contract(trusted_manifest)
        if selected_source:
            _copy_source(selected_source, staging, trusted_manifest)
            source_label = f"bundled:{selected_source}"
        else:
            _download_source(staging, trusted_manifest)
            source_label = "http_files"
        validate_asset_dir(staging, full_hash=True)
        installs = runtime_root / MODEL_SLUG / "installs"
        installs.mkdir(parents=True, exist_ok=True)
        graph_hash = next(
            item["sha256"] for item in trusted_manifest["expected_files"] if item["path"] == "model.onnx"
        )
        target = installs / f"{GRAPH_VERSION}-{graph_hash[:12]}-{int(time.time())}"
        os.replace(staging, target)
        pointer = runtime_root / "active.json"
        pointer_tmp = pointer.with_name(f".{pointer.name}.{uuid.uuid4().hex}.tmp")
        pointer_tmp.write_text(
            json.dumps({
                "asset_dir": target.relative_to(runtime_root).as_posix(),
                "model_name": EXPECTED_MODEL,
                "model_version": EXPECTED_MODEL_VERSION,
                "onnx_graph_version": GRAPH_VERSION,
                "verified_sha256": graph_hash,
                "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "source": source_label,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(pointer_tmp, pointer)
        logger.info("embedding asset repair completed source=%s target=%s", source_label, target)
        return {"status": "repaired", "asset_dir": str(target), "source": source_label, "sha256": graph_hash}
    except EmbeddingRuntimeError:
        raise
    except Exception as exc:
        raise EmbeddingRuntimeError(
            "ASSET_REPAIR_FAILED", str(exc) or type(exc).__name__, stage="asset_repair"
        ) from exc
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
