"""Fail a Texa Standard artifact that violates the Torch-free ONNX contract."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion.embedding_assets import validate_asset_dir


FORBIDDEN_PARTS = {"torch", "sentence_transformers", "transformers", "safetensors"}
FORBIDDEN_DLLS = {"c10.dll", "torch_cpu.dll", "torch_python.dll"}


def _relative_parts(path: Path, root: Path) -> tuple[str, ...]:
    return tuple(part.lower() for part in path.relative_to(root).parts)


def scan_forbidden(root: Path) -> list[str]:
    violations: list[str] = []
    for path in root.rglob("*"):
        parts = _relative_parts(path, root)
        name = path.name.lower()
        package_hit = any(
            part in FORBIDDEN_PARTS
            or any(part.startswith(f"{package}-") and ".dist-info" in part for package in FORBIDDEN_PARTS)
            for part in parts
        )
        dll_hit = (
            name in FORBIDDEN_DLLS
            or (name.startswith("torch") and name.endswith(".dll"))
            or ("cuda" in name and name.endswith(".dll"))
            or (name.startswith("cu") and name.endswith(".dll") and "onnxruntime" not in "/".join(parts))
        )
        if package_hit or dll_hit:
            violations.append(path.relative_to(root).as_posix())
    compact: list[str] = []
    for violation in sorted(set(violations), key=lambda value: (value.count("/"), value)):
        if any(violation == parent or violation.startswith(parent + "/") for parent in compact):
            continue
        compact.append(violation)
    return sorted(compact)


def _find_asset_dir(root: Path, configured: Path | None) -> Path:
    if configured:
        return configured.resolve()
    manifests = list(root.rglob("embedding-runtime.json"))
    if len(manifests) != 1:
        raise RuntimeError(f"Expected exactly one embedding-runtime.json, found {len(manifests)}")
    return manifests[0].parent


def _has_fragment(root: Path, fragments: tuple[str, ...]) -> bool:
    normalized = tuple(fragment.lower() for fragment in fragments)
    for path in root.rglob("*"):
        joined = "/".join(_relative_parts(path, root))
        if all(fragment in joined for fragment in normalized):
            return True
    return False


def _xref_has_module(xref: Path | None, module: str) -> bool:
    return bool(xref and xref.is_file() and module in xref.read_text(encoding="utf-8", errors="ignore"))


def validate(root: Path, asset_dir: Path | None = None, pyinstaller_xref: Path | None = None) -> dict:
    root = root.resolve()
    if not root.exists():
        raise RuntimeError(f"Artifact root does not exist: {root}")
    forbidden = scan_forbidden(root)
    if forbidden:
        raise RuntimeError(f"Forbidden Standard runtime dependencies found: {forbidden[:20]}")
    if not _has_fragment(root, ("onnxruntime",)):
        raise RuntimeError("onnxruntime was not packaged")
    if not _has_fragment(root, ("tokenizers",)):
        raise RuntimeError("tokenizers was not packaged")
    if not _has_fragment(root, ("chromadb", "telemetry", "product", "posthog")) and not _xref_has_module(
        pyinstaller_xref, "chromadb.telemetry.product.posthog"
    ):
        raise RuntimeError("chromadb.telemetry.product.posthog was not packaged")
    if not _has_fragment(root, ("chromadb", "api", "rust")) and not _xref_has_module(
        pyinstaller_xref, "chromadb.api.rust"
    ):
        raise RuntimeError("chromadb.api.rust was not packaged")
    resolved_assets = _find_asset_dir(root, asset_dir)
    manifest = validate_asset_dir(resolved_assets, full_hash=True)
    http_sources = [
        source for source in manifest.get("repair_sources", [])
        if source.get("type") == "http_files"
        and str(source.get("base_url") or "").startswith("https://")
    ]
    if not http_sources:
        raise RuntimeError("manifest has no versioned HTTPS repair source mapping")
    result = {
        "status": "PASS",
        "artifact_root": str(root),
        "forbidden_dependencies": [],
        "onnxruntime_present": True,
        "tokenizers_present": True,
        "chromadb_dynamic_imports_present": True,
        "pyinstaller_xref": str(pyinstaller_xref.resolve()) if pyinstaller_xref else "",
        "asset_dir": str(resolved_assets),
        "model_name": manifest["model_name"],
        "model_version": manifest["model_version"],
        "onnx_graph_version": manifest["onnx_graph_version"],
        "embedding_dimension": manifest["embedding_dimension"],
        "asset_sha256_valid": True,
        "repair_source_mapping_valid": True,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--asset-dir", type=Path)
    parser.add_argument("--pyinstaller-xref", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    result = validate(args.root, args.asset_dir, args.pyinstaller_xref)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        temp = args.json_output.with_suffix(args.json_output.suffix + ".tmp")
        temp.write_text(payload, encoding="utf-8")
        os.replace(temp, args.json_output)


if __name__ == "__main__":
    main()
