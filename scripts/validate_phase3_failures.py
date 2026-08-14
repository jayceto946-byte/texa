"""Exercise packaged Texa Standard embedding failure contracts.

The fixture directories live only for the duration of the run.  A hard link is
used for the valid 95 MB graph so tokenizer cases do not duplicate the model.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_SOURCE = ROOT / "assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1"


def request_json(url: str, payload: dict | None = None, timeout: float = 1.0) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method="POST" if body else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def copy_asset_fixture(destination: Path, case: str) -> None:
    destination.mkdir(parents=True)
    for source in ASSET_SOURCE.iterdir():
        if source.name == "model.onnx":
            continue
        shutil.copy2(source, destination / source.name)
    model = destination / "model.onnx"
    if case in {"valid", "tokenizer_missing", "tokenizer_mismatch"}:
        os.link(ASSET_SOURCE / "model.onnx", model)
    elif case == "model_corrupt":
        with model.open("wb") as stream:
            stream.truncate((ASSET_SOURCE / "model.onnx").stat().st_size)
    if case == "tokenizer_missing":
        (destination / "tokenizer.json").unlink()
    elif case == "tokenizer_mismatch":
        path = destination / "tokenizer_config.json"
        content = path.read_text(encoding="utf-8")
        if '"model_max_length": 512' not in content:
            raise RuntimeError("tokenizer fixture no longer has model_max_length=512")
        path.write_text(content.replace('"model_max_length": 512', '"model_max_length": 511', 1), encoding="utf-8")


def run_failure(executable: Path, asset_dir: Path, data_dir: Path, port: int) -> dict:
    env = dict(os.environ)
    env.update({
        "DATA_DIR": str(data_dir),
        "VECTOR_DB_PATH": str(data_dir / "vector_db"),
        "TEXA_EMBEDDING_BACKEND": "onnx",
        "TEXA_EMBEDDING_ASSET_DIR": str(asset_dir),
        "TEXA_REQUIRE_WINDOWS_X64": "1",
        "HF_HUB_OFFLINE": "1",
        "KAOYAN_BACKEND_PORT": str(port),
        "KAOYAN_BACKEND_HOST": "127.0.0.1",
        "KAOYAN_REQUIRE_API_TOKEN": "0",
        "KAOYAN_INSTANCE_ID": f"phase3-failure-{uuid.uuid4().hex}",
        "RERANKER_MODEL_PATH": "",
    })
    process = subprocess.Popen(
        [str(executable)],
        cwd=str(executable.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    health = None
    try:
        deadline = time.perf_counter() + 30
        while time.perf_counter() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"backend exited before health contract: {process.returncode}")
            try:
                health = request_json(f"http://127.0.0.1:{port}/health")
                if health.get("warmup", {}).get("status") in {"error", "degraded", "ready"}:
                    break
            except (OSError, urllib.error.URLError, TimeoutError):
                pass
            time.sleep(0.05)
        if not health:
            raise RuntimeError("backend did not expose health")
        return health
    finally:
        try:
            request_json(f"http://127.0.0.1:{port}/api/system/shutdown", {}, timeout=2)
        except Exception:
            pass
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, default=ROOT / "build/backend/backend_server/backend_server.exe")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark_results/embedding_onnx_phase3/failure_contracts.json")
    args = parser.parse_args()
    expected = {
        "model_missing": "MODEL_MISSING",
        "model_corrupt": "MODEL_CORRUPT_OR_INCOMPATIBLE",
        "tokenizer_missing": "TOKENIZER_MISMATCH",
        "tokenizer_mismatch": "TOKENIZER_MISMATCH",
    }
    rows: list[dict] = []
    temp_parent = ROOT / "benchmark_results/embedding_onnx_phase3"
    with tempfile.TemporaryDirectory(prefix="failure-fixtures-", dir=temp_parent) as raw_temp:
        temp = Path(raw_temp)
        # Detach the frozen backend from an adjacent packaged asset directory so
        # a missing/corrupt shipped asset cannot be masked by candidate fallback.
        standalone_runtime = temp / "standalone-backend"
        shutil.copytree(args.executable.resolve().parent, standalone_runtime)
        standalone_executable = standalone_runtime / args.executable.name
        for index, (case, code) in enumerate(expected.items()):
            asset_dir = temp / case
            copy_asset_fixture(asset_dir, case)
            health = run_failure(standalone_executable, asset_dir, temp / f"data-{case}", 9170 + index)
            failure = health.get("warmup", {}).get("failure") or {}
            rows.append({
                "case": case,
                "expected_code": code,
                "actual_code": failure.get("code"),
                "recoverable": failure.get("recoverable"),
                "repair_action": failure.get("repair_action"),
                "diagnostic_id_present": bool(failure.get("diagnostic_id")),
                "status": "PASS" if failure.get("code") == code and bool(failure.get("diagnostic_id")) else "FAIL",
            })

        pybind = next(standalone_runtime.rglob("onnxruntime_pybind11_state.pyd"))
        pybind.unlink()
        health = run_failure(standalone_executable, ASSET_SOURCE, temp / "data-ort", 9179)
        failure = health.get("warmup", {}).get("failure") or {}
        rows.append({
            "case": "ort_runtime_dll_missing",
            "expected_code": "ORT_IMPORT_FAILURE",
            "actual_code": failure.get("code"),
            "recoverable": failure.get("recoverable"),
            "repair_action": failure.get("repair_action"),
            "diagnostic_id_present": bool(failure.get("diagnostic_id")),
            "status": "PASS" if failure.get("code") == "ORT_IMPORT_FAILURE" else "FAIL",
        })

    result = {"status": "PASS" if all(row["status"] == "PASS" for row in rows) else "FAIL", "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
