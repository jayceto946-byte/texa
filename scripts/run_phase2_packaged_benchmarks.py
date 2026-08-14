"""Run the frozen Phase 1 worker from the two PyInstaller environments."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE = ROOT / "benchmark_results" / "embedding_onnx_phase2"
ONNX = PHASE / "candidate_sample_data" / "models" / "models--BAAI--bge-small-zh-v1.5" / "snapshots"
ONNX = next(ONNX.iterdir()) / "bge-small-zh-v1.5-fp32.onnx"


def run(variant: str, *arguments: str) -> dict:
    executable = PHASE / variant / "benchmark_companion" / "phase2_benchmark" / "phase2_benchmark.exe"
    command = [str(executable), *arguments, "--onnx-path", str(ONNX)]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    (PHASE / f"packaged_{variant}_{arguments[1]}_stderr.log").write_text(
        completed.stderr, encoding="utf-8"
    )
    return json.loads(completed.stdout)


def main() -> None:
    results = {
        "method": "same Phase 1 benchmark worker frozen by PyInstaller in each release environment",
        "interactive": {
            "baseline": run("baseline", "--task", "scaling", "--backend", "torch", "--sizes", "1", "--repeats", "20", "--batch-size", "1", "--torch-threads", "2"),
            "candidate": run("candidate", "--task", "scaling", "--backend", "onnx", "--sizes", "1", "--repeats", "20", "--batch-size", "1", "--intra", "2", "--inter", "1", "--execution-mode", "sequential", "--graph-optimization", "all"),
        },
        "ingestion": {
            "baseline": run("baseline", "--task", "ingestion", "--backend", "torch", "--repeats", "5", "--batch-size", "32", "--torch-threads", "2", "--strategy", "naive"),
            "candidate": run("candidate", "--task", "ingestion", "--backend", "onnx", "--repeats", "5", "--batch-size", "16", "--intra", "12", "--inter", "1", "--execution-mode", "sequential", "--graph-optimization", "all", "--strategy", "length_bucket"),
        },
    }
    (PHASE / "packaged_embedding_ingestion.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "output": str(PHASE / "packaged_embedding_ingestion.json")}))


if __name__ == "__main__":
    main()
