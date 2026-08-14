"""Exercise Phase 2's diagnosable Torch-free failure paths.

This worker is experiment-only and is never imported by the application.
"""
from __future__ import annotations

import argparse
import importlib.abc
import json
import os
import tempfile
from pathlib import Path

from evaluation.embedding_backend.phase2_runtime import (
    EmbeddingRuntimeUnavailable,
    Phase2StandardEmbeddings,
    _classify_init_error,
)
from evaluation.embedding_backend.providers import resolve_model_snapshot


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ONNX = ROOT / "benchmark_results" / "embedding_onnx" / "bge-small-zh-v1.5-fp32.onnx"


class _BlockOnnxRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "onnxruntime" or fullname.startswith("onnxruntime."):
            raise ImportError("onnxruntime import deliberately blocked for Phase 2 validation")
        return None


def _capture(callable_, expected_code: str) -> dict:
    try:
        callable_()
    except EmbeddingRuntimeUnavailable as exc:
        return {
            "status": "PASS" if exc.code == expected_code else "FAIL",
            "expected_code": expected_code,
            "code": exc.code,
            "message": str(exc),
        }
    except Exception as exc:  # pragma: no cover - captured as an experiment failure
        return {"status": "FAIL", "type": type(exc).__name__, "message": str(exc)}
    return {"status": "FAIL", "message": "initialization unexpectedly succeeded"}


def run_case(case: str) -> dict:
    snapshot = resolve_model_snapshot()
    previous = os.environ.get("EMBEDDING_ONNX_PATH")
    try:
        if case == "model_missing":
            os.environ["EMBEDDING_ONNX_PATH"] = str(ROOT / "does-not-exist-phase2.onnx")
            return _capture(lambda: Phase2StandardEmbeddings(snapshot), "MODEL_MISSING")
        if case == "model_corrupt":
            with tempfile.TemporaryDirectory(prefix="texa-phase2-corrupt-") as temp:
                corrupt = Path(temp) / "corrupt.onnx"
                corrupt.write_bytes(b"not-an-onnx-model")
                os.environ["EMBEDDING_ONNX_PATH"] = str(corrupt)
                return _capture(lambda: Phase2StandardEmbeddings(snapshot), "MODEL_CORRUPT_OR_INCOMPATIBLE")
        if case == "tokenizer_mismatch":
            with tempfile.TemporaryDirectory(prefix="texa-phase2-tokenizer-") as temp:
                os.environ["EMBEDDING_ONNX_PATH"] = str(DEFAULT_ONNX)
                return _capture(lambda: Phase2StandardEmbeddings(Path(temp)), "TOKENIZER_MISMATCH")
        if case == "ort_import_failure":
            import sys

            for name in list(sys.modules):
                if name == "onnxruntime" or name.startswith("onnxruntime."):
                    del sys.modules[name]
            sys.meta_path.insert(0, _BlockOnnxRuntime())
            os.environ["EMBEDDING_ONNX_PATH"] = str(DEFAULT_ONNX)
            return _capture(lambda: Phase2StandardEmbeddings(snapshot), "ORT_IMPORT_FAILURE")
        if case == "unsupported_architecture":
            error = _classify_init_error(RuntimeError("unsupported architecture: ARM64 provider unavailable"))
            return {
                "status": "PASS" if error.code == "UNSUPPORTED_ARCHITECTURE" else "FAIL",
                "code": error.code,
                "message": str(error),
                "validation": "classifier",
            }
        raise ValueError(case)
    finally:
        if previous is None:
            os.environ.pop("EMBEDDING_ONNX_PATH", None)
        else:
            os.environ["EMBEDDING_ONNX_PATH"] = previous


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        required=True,
        choices=(
            "model_missing",
            "model_corrupt",
            "ort_import_failure",
            "unsupported_architecture",
            "tokenizer_mismatch",
        ),
    )
    args = parser.parse_args()
    print(json.dumps({"case": args.case, **run_case(args.case)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
