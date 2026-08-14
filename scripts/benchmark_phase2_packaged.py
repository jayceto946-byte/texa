"""Benchmark the real Phase 2 packaged backend executables."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE = ROOT / "benchmark_results" / "embedding_onnx_phase2"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))]


def request_json(url: str, payload: dict | None = None, timeout: float = 2.0):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def stream_to_retrieval(url: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
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
                    "stage_ms": float(event.get("stage_ms") or 0),
                    "content_count": int(event.get("content_count") or 0),
                    "retrieval_status": event.get("retrieval_status"),
                    "retrieval_error": event.get("retrieval_error"),
                }
            if event.get("stage") == "error":
                raise RuntimeError(str(event.get("message") or event))
    raise RuntimeError("chat stream ended before retrieve stage")


def ensure_runtime_data(variant: str) -> Path:
    target = PHASE / f"packaged_runtime_data_{variant}"
    if target.exists():
        return target
    source = ROOT / "desktop" / "sample_data" if variant == "baseline" else PHASE / "candidate_sample_data"
    shutil.copytree(source, target)
    return target


def backend_executable(variant: str) -> Path:
    return (
        PHASE / variant / "release" / "win-unpacked" / "resources" /
        "backend" / "backend_server" / "backend_server.exe"
    )


def one_run(variant: str, index: int, runtime_data: Path) -> dict:
    executable = backend_executable(variant)
    port = 8920 + (0 if variant == "baseline" else 20) + index
    env = dict(os.environ)
    env.update({
        "DATA_DIR": str(runtime_data),
        "VECTOR_DB_PATH": str(runtime_data / "vector_db"),
        "MINERU_OUTPUT_PATH": str(PHASE / f"packaged_mineru_{variant}"),
        "EMBEDDING_LOCAL_FILES_ONLY": "1",
        "HF_HUB_OFFLINE": "1",
        "KAOYAN_BACKEND_PORT": str(port),
        "KAOYAN_BACKEND_HOST": "127.0.0.1",
        "KAOYAN_REQUIRE_API_TOKEN": "0",
        "KAOYAN_INSTANCE_ID": f"phase2-{variant}-{index}",
        "RERANKER_MODEL_PATH": "",
    })
    stdout_path = PHASE / f"packaged_{variant}_run{index + 1}_stdout.log"
    stderr_path = PHASE / f"packaged_{variant}_run{index + 1}_stderr.log"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    started = time.perf_counter()
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            [str(executable)],
            cwd=str(executable.parent),
            env=env,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
        )
        first_health_ms = None
        warmup_ready_ms = None
        health = None
        try:
            deadline = time.perf_counter() + 90
            while time.perf_counter() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"backend exited early with {process.returncode}")
                try:
                    health = request_json(f"http://127.0.0.1:{port}/health", timeout=0.5)
                    elapsed = (time.perf_counter() - started) * 1000
                    if first_health_ms is None:
                        first_health_ms = elapsed
                    if health.get("warmup", {}).get("status") in {"ready", "degraded"}:
                        warmup_ready_ms = elapsed
                        break
                except (OSError, urllib.error.URLError, TimeoutError):
                    pass
                time.sleep(0.05)
            if first_health_ms is None or warmup_ready_ms is None:
                raise RuntimeError(f"health/warmup timeout: {health}")
            if health.get("warmup", {}).get("status") != "ready":
                raise RuntimeError(f"warmup was not ready: {health.get('warmup')}")
            retrieval = stream_to_retrieval(
                f"http://127.0.0.1:{port}/api/chat/stream",
                {
                    "question": "什么是优化设计？",
                    "book_name": "default",
                    "target_chapters": ["第一章 优化设计的基本概念"],
                    "conversation_id": f"phase2-{variant}-{uuid.uuid4().hex}",
                    "answer_mode": "textbook_grounded",
                },
            )
            if retrieval.get("retrieval_status") != "ok" or retrieval.get("content_count", 0) <= 0:
                raise RuntimeError(f"packaged retrieval was not functional: {retrieval}")
            return {
                "run": index + 1,
                "pid": process.pid,
                "first_health_ms": first_health_ms,
                "warmup_ready_ms": warmup_ready_ms,
                "warmup": health.get("warmup"),
                "retrieval": retrieval,
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


def summarize(rows: list[dict]) -> dict:
    def stats(values: list[float]) -> dict:
        return {"median": percentile(values, 0.5), "p95": percentile(values, 0.95)}

    return {
        "runs": len(rows),
        "first_health_ms": stats([row["first_health_ms"] for row in rows]),
        "warmup_ready_ms": stats([row["warmup_ready_ms"] for row in rows]),
        "retrieval_wall_ms": stats([row["retrieval"]["wall_ms"] for row in rows]),
        "retrieval_stage_ms": stats([row["retrieval"]["stage_ms"] for row in rows]),
        "rows": rows,
    }


def main() -> None:
    collected = {"baseline": [], "candidate": []}
    runtime = {variant: ensure_runtime_data(variant) for variant in collected}
    for index in range(5):
        order = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
        for variant in order:
            collected[variant].append(one_run(variant, index, runtime[variant]))
    result = {}
    for variant in ("baseline", "candidate"):
        result[variant] = summarize(collected[variant])
        print(variant, json.dumps({key: value for key, value in result[variant].items() if key != "rows"}))
    (PHASE / "packaged_startup.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
