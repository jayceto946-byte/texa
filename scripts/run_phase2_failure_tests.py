"""Run each failure test in a fresh Torch-free Python process."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PHASE = ROOT / "benchmark_results" / "embedding_onnx_phase2"
PYTHON = PHASE / "venv" / "Scripts" / "python.exe"
CASES = (
    "model_missing",
    "model_corrupt",
    "ort_import_failure",
    "unsupported_architecture",
    "tokenizer_mismatch",
)


def main() -> None:
    results = []
    for case in CASES:
        completed = subprocess.run(
            [str(PYTHON), "-B", "-m", "evaluation.embedding_backend.phase2_failure_worker", "--case", case],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(completed.stdout)
        payload["diagnostic_log_present"] = bool(completed.stderr.strip())
        results.append(payload)
    report = {
        "status": "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL",
        "policy": "no Torch fallback; structured error plus diagnostic log",
        "cases": results,
    }
    output = PHASE / "failure_handling.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
