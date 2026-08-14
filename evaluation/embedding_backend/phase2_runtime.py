"""Experimental Torch-free Standard adapter for Phase 2 packaging tests.

This module is never imported by the normal application entrypoint. It wraps
the Phase 1 ONNX provider without changing the exported graph or embedding
semantics, and injects the adapter only into an isolated candidate process.
"""
from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
from typing import Sequence

from .providers import ONNXEmbeddingProvider, resolve_model_snapshot


logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ONNX_NAME = "bge-small-zh-v1.5-fp32.onnx"


class EmbeddingRuntimeUnavailable(RuntimeError):
    """A diagnosable Standard-runtime failure that never falls back to Torch."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(
            f"Embedding runtime unavailable [{code}]: {detail}. "
            "Repair Texa runtime/model and retry."
        )


def physical_core_count() -> int:
    """Return the Windows physical core count with a conservative fallback."""
    if os.name != "nt":
        return max(1, (os.cpu_count() or 1) // 2)
    relation_processor_core = 0
    relation_all = 0xFFFF
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    needed = ctypes.c_ulong(0)
    get_info = kernel32.GetLogicalProcessorInformationEx
    get_info(relation_all, None, ctypes.byref(needed))
    if not needed.value:
        return max(1, (os.cpu_count() or 1) // 2)
    buffer = ctypes.create_string_buffer(needed.value)
    if not get_info(relation_all, buffer, ctypes.byref(needed)):
        return max(1, (os.cpu_count() or 1) // 2)
    offset = 0
    cores = 0
    while offset + 8 <= needed.value:
        relationship = ctypes.c_uint32.from_buffer(buffer, offset).value
        size = ctypes.c_uint32.from_buffer(buffer, offset + 4).value
        if not size:
            break
        if relationship == relation_processor_core:
            cores += 1
        offset += size
    return cores or max(1, (os.cpu_count() or 1) // 2)


def _resolve_onnx_path(model_path: Path) -> Path:
    configured = os.getenv("EMBEDDING_ONNX_PATH", "").strip()
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return candidate.resolve()
        raise EmbeddingRuntimeUnavailable("MODEL_MISSING", f"ONNX model not found at {configured}")
    candidates = [
        model_path / DEFAULT_ONNX_NAME,
        ROOT / "benchmark_results" / "embedding_onnx" / DEFAULT_ONNX_NAME,
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    expected = str(model_path / DEFAULT_ONNX_NAME)
    raise EmbeddingRuntimeUnavailable("MODEL_MISSING", f"ONNX model not found at {expected}")


def _classify_init_error(exc: Exception) -> EmbeddingRuntimeUnavailable:
    if isinstance(exc, EmbeddingRuntimeUnavailable):
        return exc
    text = str(exc)
    lowered = text.lower()
    if "tokenizer" in lowered:
        code = "TOKENIZER_MISMATCH"
    elif isinstance(exc, ImportError) or "no module named 'onnxruntime'" in lowered or "onnxruntime import" in lowered:
        code = "ORT_IMPORT_FAILURE"
    elif isinstance(exc, FileNotFoundError) or "not found" in lowered:
        code = "MODEL_MISSING"
    elif "unsupported" in lowered or "architecture" in lowered:
        code = "UNSUPPORTED_ARCHITECTURE"
    else:
        code = "MODEL_CORRUPT_OR_INCOMPATIBLE"
    return EmbeddingRuntimeUnavailable(code, text or type(exc).__name__)


class Phase2StandardEmbeddings:
    """Query/session adapter using the frozen Phase 1 FP32 graph.

    Interactive queries keep a two-thread pool. Document batches use the
    Phase 1 ingestion candidate: length buckets, batch=16, physical cores,
    inter-op=1, sequential execution, and ORT_ENABLE_ALL.
    """

    bucket_edges = (64, 128, 256, 512)

    def __init__(self, model_path: Path | str | None = None):
        try:
            if model_path is None:
                import config

                snapshot = resolve_model_snapshot(Path(config.DATA_DIR) / "models")
            else:
                snapshot = Path(model_path).resolve()
            onnx_path = _resolve_onnx_path(snapshot)
            self.query_provider = ONNXEmbeddingProvider(
                onnx_path,
                snapshot,
                batch_size=1,
                intra_op_threads=2,
                inter_op_threads=1,
                execution_mode="sequential",
                graph_optimization_level="all",
            )
            self.document_provider = ONNXEmbeddingProvider(
                onnx_path,
                snapshot,
                batch_size=16,
                intra_op_threads=physical_core_count(),
                inter_op_threads=1,
                execution_mode="sequential",
                graph_optimization_level="all",
            )
        except Exception as exc:
            diagnosed = _classify_init_error(exc)
            logger.exception("Phase 2 embedding initialization failed: %s", diagnosed.code)
            raise diagnosed from exc

    @staticmethod
    def _token_length(provider: ONNXEmbeddingProvider, text: str) -> int:
        return min(len(provider.tokenizer.encode(str(text)).ids), 512)

    @classmethod
    def _bucket(cls, length: int) -> int:
        for edge in cls.bucket_edges:
            if length <= edge:
                return edge
        return 512

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        values = [str(text) for text in texts]
        if not values:
            return []
        buckets: dict[int, list[tuple[int, str]]] = {edge: [] for edge in self.bucket_edges}
        for index, value in enumerate(values):
            length = self._token_length(self.document_provider, value)
            buckets[self._bucket(length)].append((index, value))
        result: list[list[float] | None] = [None] * len(values)
        for edge in self.bucket_edges:
            items = buckets[edge]
            if not items:
                continue
            vectors = self.document_provider.encode([value for _, value in items]).tolist()
            for (index, _), vector in zip(items, vectors):
                result[index] = vector
        return [vector for vector in result if vector is not None]

    def embed_query(self, text: str) -> list[float]:
        return self.query_provider.embed_query(str(text))


def install_candidate_provider() -> Phase2StandardEmbeddings:
    """Inject ONNX into config before backend/vector-store modules import it."""
    import config

    provider = Phase2StandardEmbeddings()
    config._embeddings_instance = provider
    config.get_embeddings = lambda: provider
    return provider
