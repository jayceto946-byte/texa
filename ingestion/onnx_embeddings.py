"""Frozen BGE-small FP32 ONNX provider used by Texa Standard.

The graph owns CLS pooling and the two L2-normalization passes validated in
Phases 0-2.  This module imports neither Torch nor Transformers.
"""
from __future__ import annotations

import ctypes
import os
import threading
from collections import defaultdict
from pathlib import Path
from typing import Sequence

import numpy as np


EMBEDDING_DIMENSION = 512
MAX_LENGTH = 512
BUCKET_EDGES = (64, 128, 256, 512)


def physical_core_count() -> int:
    if os.name != "nt":
        return max(1, (os.cpu_count() or 1) // 2)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_info = kernel32.GetLogicalProcessorInformationEx
    needed = ctypes.c_ulong(0)
    get_info(0xFFFF, None, ctypes.byref(needed))
    if not needed.value:
        return max(1, (os.cpu_count() or 1) // 2)
    buffer = ctypes.create_string_buffer(needed.value)
    if not get_info(0xFFFF, buffer, ctypes.byref(needed)):
        return max(1, (os.cpu_count() or 1) // 2)
    offset = cores = 0
    while offset + 8 <= needed.value:
        relationship = ctypes.c_uint32.from_buffer(buffer, offset).value
        size = ctypes.c_uint32.from_buffer(buffer, offset + 4).value
        if not size:
            break
        if relationship == 0:
            cores += 1
        offset += size
    return cores or max(1, (os.cpu_count() or 1) // 2)


class ONNXEmbeddingProvider:
    """Exact Phase 1 FP32 provider: lowercase parity, CLS and double L2."""

    backend_name = "onnxruntime_fp32"

    def __init__(
        self,
        onnx_path: Path | str,
        tokenizer_path: Path | str,
        *,
        batch_size: int,
        intra_op_threads: int,
        inter_op_threads: int = 1,
        execution_mode: str = "sequential",
        graph_optimization_level: str = "all",
    ) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer
        from tokenizers.normalizers import Lowercase, Sequence as NormalizerSequence

        self.onnx_path = Path(onnx_path).resolve()
        self.tokenizer_path = Path(tokenizer_path).resolve()
        self.batch_size = int(batch_size)
        self.max_length = MAX_LENGTH
        self.tokenizer = Tokenizer.from_file(str(self.tokenizer_path))
        self.tokenizer.normalizer = NormalizerSequence([Lowercase(), self.tokenizer.normalizer])
        self.tokenizer.enable_truncation(max_length=MAX_LENGTH, direction="right")
        self.tokenizer.enable_padding(
            direction="right", pad_id=0, pad_type_id=0, pad_token="[PAD]"
        )

        options = ort.SessionOptions()
        options.intra_op_num_threads = int(intra_op_threads)
        options.inter_op_num_threads = int(inter_op_threads)
        execution_modes = {
            "sequential": ort.ExecutionMode.ORT_SEQUENTIAL,
            "parallel": ort.ExecutionMode.ORT_PARALLEL,
        }
        optimization_levels = {
            "disable": ort.GraphOptimizationLevel.ORT_DISABLE_ALL,
            "basic": ort.GraphOptimizationLevel.ORT_ENABLE_BASIC,
            "extended": ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED,
            "all": ort.GraphOptimizationLevel.ORT_ENABLE_ALL,
        }
        if execution_mode not in execution_modes or graph_optimization_level not in optimization_levels:
            raise ValueError(
                f"Unknown ORT configuration: execution={execution_mode}, optimization={graph_optimization_level}"
            )
        options.execution_mode = execution_modes[execution_mode]
        options.graph_optimization_level = optimization_levels[graph_optimization_level]
        self.session_options = {
            "intra_op_num_threads": int(intra_op_threads),
            "inter_op_num_threads": int(inter_op_threads),
            "execution_mode": execution_mode,
            "graph_optimization_level": graph_optimization_level,
        }
        self.session = ort.InferenceSession(
            str(self.onnx_path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        providers = self.session.get_providers()
        if providers != ["CPUExecutionProvider"]:
            raise RuntimeError(f"Unexpected ONNX providers: {providers}")
        inputs = {item.name for item in self.session.get_inputs()}
        required = {"input_ids", "attention_mask", "token_type_ids"}
        if inputs != required:
            raise RuntimeError(f"Unexpected ONNX inputs: {sorted(inputs)}")
        outputs = self.session.get_outputs()
        if len(outputs) != 1 or outputs[0].name != "sentence_embedding":
            raise RuntimeError(f"Unexpected ONNX outputs: {[item.name for item in outputs]}")

    def tokenize_batch(self, texts: list[str]) -> dict[str, np.ndarray]:
        encoded = self.tokenizer.encode_batch(texts)
        return {
            "input_ids": np.asarray([item.ids for item in encoded], dtype=np.int64),
            "attention_mask": np.asarray([item.attention_mask for item in encoded], dtype=np.int64),
            "token_type_ids": np.asarray([item.type_ids for item in encoded], dtype=np.int64),
        }

    def run_inputs(self, inputs: dict[str, np.ndarray]) -> np.ndarray:
        output = self.session.run(["sentence_embedding"], inputs)[0]
        output = output.astype(np.float32, copy=False)
        if output.ndim != 2 or output.shape[1] != EMBEDDING_DIMENSION:
            raise RuntimeError(f"Unexpected embedding shape: {output.shape}")
        return output

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        return self.run_inputs(self.tokenize_batch(texts))

    def encode(self, texts: str | Sequence[str]) -> np.ndarray:
        single = isinstance(texts, str)
        values = [str(texts)] if single else [str(text) for text in texts]
        if not values:
            return np.empty((0, EMBEDDING_DIMENSION), dtype=np.float32)
        batches = [
            self.encode_batch(values[start:start + self.batch_size])
            for start in range(0, len(values), self.batch_size)
        ]
        result = np.concatenate(batches, axis=0)
        return result[0] if single else result


class TexaONNXEmbeddings:
    """Chroma adapter with separate reusable interactive/ingestion sessions."""

    backend_name = "onnxruntime_fp32"

    def __init__(self, asset_dir: Path | str) -> None:
        self.asset_dir = Path(asset_dir).resolve()
        onnx_path = self.asset_dir / "model.onnx"
        tokenizer_path = self.asset_dir / "tokenizer.json"
        interactive_threads = max(1, int(os.getenv("TEXA_ONNX_INTERACTIVE_THREADS", "2")))
        ingestion_threads = max(
            1, int(os.getenv("TEXA_ONNX_INGESTION_THREADS", str(physical_core_count())))
        )
        self._onnx_path = onnx_path
        self._tokenizer_path = tokenizer_path
        self._ingestion_threads = ingestion_threads
        self._ingestion_lock = threading.Lock()
        self._ingestion_provider: ONNXEmbeddingProvider | None = None
        self.interactive_provider = ONNXEmbeddingProvider(
            onnx_path,
            tokenizer_path,
            batch_size=1,
            intra_op_threads=interactive_threads,
            inter_op_threads=1,
        )
        self.runtime_config = {
            "interactive": self.interactive_provider.session_options,
            "ingestion": {
                "intra_op_num_threads": ingestion_threads,
                "inter_op_num_threads": 1,
                "execution_mode": "sequential",
                "graph_optimization_level": "all",
                "load": "lazy_singleton",
            },
            "batch_size": 16,
            "bucket_edges": list(BUCKET_EDGES),
        }

    def _get_ingestion_provider(self) -> ONNXEmbeddingProvider:
        if self._ingestion_provider is not None:
            return self._ingestion_provider
        with self._ingestion_lock:
            if self._ingestion_provider is None:
                self._ingestion_provider = ONNXEmbeddingProvider(
                    self._onnx_path,
                    self._tokenizer_path,
                    batch_size=16,
                    intra_op_threads=self._ingestion_threads,
                    inter_op_threads=1,
                )
        return self._ingestion_provider

    @staticmethod
    def _bucket(length: int) -> int:
        for edge in BUCKET_EDGES:
            if length <= edge:
                return edge
        return BUCKET_EDGES[-1]

    def embed_query(self, text: str) -> list[float]:
        return self.interactive_provider.encode(str(text)).tolist()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        values = [str(text) for text in texts]
        if not values:
            return []
        ingestion_provider = self._get_ingestion_provider()
        encoded = ingestion_provider.tokenizer.encode_batch(values)
        buckets: dict[int, list[int]] = defaultdict(list)
        for index, item in enumerate(encoded):
            length = min(sum(item.attention_mask), MAX_LENGTH)
            buckets[self._bucket(length)].append(index)
        result = np.empty((len(values), EMBEDDING_DIMENSION), dtype=np.float32)
        for edge in BUCKET_EDGES:
            indices = buckets[edge]
            for start in range(0, len(indices), 16):
                batch_indices = indices[start:start + 16]
                batch = [values[index] for index in batch_indices]
                vectors = ingestion_provider.encode_batch(batch)
                result[batch_indices] = vectors
        return result.tolist()
