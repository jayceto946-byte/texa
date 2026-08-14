"""Exercise a built Texa Standard backend through its real HTTP boundary."""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def request_json(url: str, payload: dict | None = None, timeout: float = 3.0) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def stream_to_retrieve(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=90) as response:
        for raw in response:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event.get("stage") == "retrieve":
                return {
                    "wall_ms": (time.perf_counter() - started) * 1000,
                    "retrieval_status": event.get("retrieval_status"),
                    "retrieval_error": event.get("retrieval_error"),
                    "content_count": int(event.get("content_count") or 0),
                }
            if event.get("stage") == "error":
                raise RuntimeError(str(event.get("message") or event))
    raise RuntimeError("SSE stream ended before retrieve stage")


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))]


def one_run(executable: Path, asset_dir: Path, data_dir: Path, index: int) -> dict:
    port = 8990 + index
    env = dict(os.environ)
    env.update({
        "DATA_DIR": str(data_dir),
        "VECTOR_DB_PATH": str(data_dir / "vector_db"),
        "TEXA_EMBEDDING_BACKEND": "onnx",
        "TEXA_EMBEDDING_ASSET_DIR": str(asset_dir),
        "TEXA_REQUIRE_WINDOWS_X64": "1",
        "EMBEDDING_LOCAL_FILES_ONLY": "1",
        "HF_HUB_OFFLINE": "1",
        "KAOYAN_BACKEND_PORT": str(port),
        "KAOYAN_BACKEND_HOST": "127.0.0.1",
        "KAOYAN_REQUIRE_API_TOKEN": "0",
        "KAOYAN_INSTANCE_ID": f"phase3-{index}-{uuid.uuid4().hex}",
        "RERANKER_MODEL_PATH": "",
    })
    logs = ROOT / "benchmark_results" / "embedding_onnx_phase3"
    stdout_path = logs / f"packaged_run{index + 1}_stdout.log"
    stderr_path = logs / f"packaged_run{index + 1}_stderr.log"
    started = time.perf_counter()
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            [str(executable)],
            cwd=str(executable.parent),
            env=env,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        first_health_ms = None
        health = None
        try:
            deadline = time.perf_counter() + 90
            while time.perf_counter() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Packaged backend exited with {process.returncode}")
                try:
                    health = request_json(f"http://127.0.0.1:{port}/health", timeout=0.5)
                    if first_health_ms is None:
                        first_health_ms = (time.perf_counter() - started) * 1000
                    if health.get("warmup", {}).get("status") in {"ready", "degraded", "error"}:
                        break
                except (OSError, urllib.error.URLError, TimeoutError):
                    pass
                time.sleep(0.05)
            if not health or health.get("warmup", {}).get("status") != "ready":
                raise RuntimeError(f"Packaged warmup failed: {health}")
            ready_ms = (time.perf_counter() - started) * 1000
            asset_status = request_json(f"http://127.0.0.1:{port}/api/system/assets/status")
            generic = stream_to_retrieve(
                f"http://127.0.0.1:{port}/api/chat/stream",
                {
                    "question": "你好",
                    "book_name": "",
                    "answer_mode": "global_general",
                    "conversation_id": f"generic-{uuid.uuid4().hex}",
                },
            )
            textbook = stream_to_retrieve(
                f"http://127.0.0.1:{port}/api/chat/stream",
                {
                    "question": "什么是优化设计？",
                    "book_name": "default",
                    "target_chapters": ["第一章 优化设计的基本概念"],
                    "conversation_id": f"textbook-{uuid.uuid4().hex}",
                    "answer_mode": "textbook_grounded",
                },
            )
            runtime = asset_status["data"]["assets"]["embedding_model"]
            checks = {
                "health_ready": health["warmup"]["status"] == "ready",
                "embedding_dimension_512": runtime.get("embedding_dimension") == 512,
                "asset_contract_ready": runtime.get("status") == "ready",
                "generic_qa": generic.get("retrieval_status") == "ordinary_qa",
                "textbook_qa": textbook.get("retrieval_status") == "ok" and textbook.get("content_count", 0) > 0,
                "offline_assets": True,
            }
            return {
                "run": index + 1,
                "status": "PASS" if all(checks.values()) else "FAIL",
                "first_health_ms": first_health_ms,
                "full_ready_ms": ready_ms,
                "warmup": health["warmup"],
                "asset_runtime": runtime,
                "generic": generic,
                "textbook": textbook,
                "checks": checks,
            }
        finally:
            try:
                request_json(f"http://127.0.0.1:{port}/api/system/shutdown", {}, timeout=2)
            except Exception:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, default=ROOT / "build/backend/backend_server/backend_server.exe")
    parser.add_argument("--asset-dir", type=Path, default=ROOT / "assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "benchmark_results/embedding_onnx_phase2/packaged_runtime_data_candidate")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark_results/embedding_onnx_phase3/packaged_startup.json")
    args = parser.parse_args()
    rows = [one_run(args.executable.resolve(), args.asset_dir.resolve(), args.data_dir.resolve(), index) for index in range(args.runs)]
    result = {
        "status": "PASS" if all(row["status"] == "PASS" for row in rows) else "FAIL",
        "runs": len(rows),
        "first_health_ms": {"median": statistics.median(row["first_health_ms"] for row in rows), "p95": percentile([row["first_health_ms"] for row in rows], 0.95)},
        "full_ready_ms": {"median": statistics.median(row["full_ready_ms"] for row in rows), "p95": percentile([row["full_ready_ms"] for row in rows], 0.95)},
        "first_textbook_retrieval_ms": {"median": statistics.median(row["textbook"]["wall_ms"] for row in rows), "p95": percentile([row["textbook"]["wall_ms"] for row in rows], 0.95)},
        "rows": rows,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(payload)
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
