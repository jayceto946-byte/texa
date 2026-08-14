"""Download and verify every file in the versioned embedding release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1/embedding-runtime.json"
DEFAULT_TAG = "embedding-runtime-onnx-fp32-v1"
DEFAULT_BASE = "https://github.com/jayceto946-byte/kaoyan-assistant/releases/download"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmark_results/embedding_onnx_phase3/remote_asset_verification.json",
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected = manifest.get("expected_files")
    if not isinstance(expected, list) or len(expected) != 6:
        raise SystemExit(f"Expected exactly six assets, found {len(expected or [])}")

    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="texa-onnx-release-verify-") as raw_temp:
        temp = Path(raw_temp)
        for item in expected:
            name = str(item["path"])
            url = f"{args.base_url.rstrip('/')}/{args.tag}/{name}"
            head_request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Texa-release-validator"})
            with urllib.request.urlopen(head_request, timeout=60) as response:
                status = int(response.status)
                resolved = urllib.parse.urlsplit(response.geturl())
                final_url = urllib.parse.urlunsplit((resolved.scheme, resolved.netloc, resolved.path, "", ""))
                content_length = int(response.headers.get("Content-Length") or -1)

            destination = temp / name
            get_request = urllib.request.Request(url, method="GET", headers={"User-Agent": "Texa-release-validator"})
            started = time.perf_counter()
            with urllib.request.urlopen(get_request, timeout=180) as response, destination.open("wb") as stream:
                get_status = int(response.status)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    stream.write(chunk)
            actual_size = destination.stat().st_size
            actual_hash = sha256(destination)
            passed = (
                status == 200
                and get_status == 200
                and content_length == int(item["size"])
                and actual_size == int(item["size"])
                and actual_hash == str(item["sha256"]).lower()
            )
            rows.append(
                {
                    "name": name,
                    "url": url,
                    "final_url": final_url,
                    "head_status": status,
                    "get_status": get_status,
                    "content_length": content_length,
                    "expected_size": int(item["size"]),
                    "downloaded_size": actual_size,
                    "sha256": actual_hash,
                    "expected_sha256": str(item["sha256"]).lower(),
                    "download_ms": round((time.perf_counter() - started) * 1000, 2),
                    "status": "PASS" if passed else "FAIL",
                }
            )

    result = {
        "status": "PASS" if len(rows) == 6 and all(row["status"] == "PASS" for row in rows) else "FAIL",
        "tag": args.tag,
        "asset_count": len(rows),
        "temporary_download_removed": True,
        "assets": rows,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, args.output)
    print(payload)
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
