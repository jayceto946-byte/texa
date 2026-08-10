"""Fail a desktop release when bundled sample files lack an auditable license manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


IGNORED = {"README.md", ".gitkeep", "content-manifest.json"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(sample_dir: Path) -> list[str]:
    sample_dir = sample_dir.resolve()
    files = sorted(
        path for path in sample_dir.rglob("*")
        if path.is_file() and path.name not in IGNORED
    ) if sample_dir.exists() else []
    if not files:
        return []

    manifest_path = sample_dir / "content-manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("Bundled sample files exist but content-manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(entries, list):
        raise RuntimeError("content-manifest.json must contain a files array")

    declared: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("Every content manifest entry must be an object")
        relative = str(entry.get("path") or "").replace("\\", "/").strip("/")
        if not relative or relative in declared:
            raise RuntimeError(f"Invalid or duplicate content path: {relative!r}")
        target = (sample_dir / relative).resolve()
        if sample_dir not in target.parents or not target.is_file():
            raise RuntimeError(f"Declared content file does not exist: {relative}")
        if entry.get("redistributable") is not True:
            raise RuntimeError(f"Content is not explicitly redistributable: {relative}")
        if not str(entry.get("source") or "").strip() or not str(entry.get("license") or "").strip():
            raise RuntimeError(f"Content source/license is incomplete: {relative}")
        expected = str(entry.get("sha256") or "").lower()
        actual = _sha256(target)
        if expected != actual:
            raise RuntimeError(f"Content checksum mismatch: {relative}")
        declared[relative] = entry

    actual_paths = {path.relative_to(sample_dir).as_posix() for path in files}
    undeclared = sorted(actual_paths - set(declared))
    extra = sorted(set(declared) - actual_paths)
    if undeclared or extra:
        raise RuntimeError(
            f"Content manifest mismatch; undeclared={undeclared[:8]}, missing={extra[:8]}"
        )
    return sorted(actual_paths)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-dir", default="desktop/sample_data")
    args = parser.parse_args()
    files = check(Path(args.sample_dir))
    print(f"Release content gate passed: {len(files)} distributable sample files")


if __name__ == "__main__":
    main()
