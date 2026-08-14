"""Development/parity providers for the frozen production ONNX graph."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

import numpy as np

from ingestion.onnx_embeddings import ONNXEmbeddingProvider as _ProductionONNXProvider


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_CACHE = ROOT / "data" / "models"
DEFAULT_REPO_ID = "BAAI/bge-small-zh-v1.5"


def resolve_model_snapshot(model_cache: Path | str = DEFAULT_MODEL_CACHE) -> Path:
    cache = Path(model_cache)
    snapshots = cache / "models--BAAI--bge-small-zh-v1.5" / "snapshots"
    candidates = sorted(path for path in snapshots.iterdir() if path.is_dir()) if snapshots.exists() else []
    if not candidates:
        raise FileNotFoundError(f"Local embedding snapshot not found under {snapshots}")
    return candidates[0].resolve()


def _as_text_list(texts: str | Sequence[str]) -> tuple[list[str], bool]:
    if isinstance(texts, str):
        return [texts], True
    return [str(text) for text in texts], False


class TorchEmbeddingProvider:
    """Development-only SentenceTransformers parity reference."""

    backend_name = "torch_sentence_transformers"

    def __init__(self, model_path: Path | str | None = None, *, batch_size: int = 32, num_threads: int = 2):
        import importlib.util
        import torch

        torch.set_num_threads(int(num_threads))
        original_find_spec = importlib.util.find_spec
        importlib.util.find_spec = lambda name, *args, **kwargs: (
            None if name == "torchvision" or name.startswith("torchvision.")
            else original_find_spec(name, *args, **kwargs)
        )
        try:
            import transformers.utils.import_utils as transformers_import_utils

            transformers_import_utils._torchvision_available = False
            from sentence_transformers import SentenceTransformer
        finally:
            importlib.util.find_spec = original_find_spec
        self.model_path = Path(model_path or resolve_model_snapshot()).resolve()
        self.batch_size = int(batch_size)
        self.model = SentenceTransformer(str(self.model_path), device="cpu", local_files_only=True)

    def encode(self, texts: str | Sequence[str]) -> np.ndarray:
        values, single = _as_text_list(texts)
        embeddings = self.model.encode(
            values,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).astype(np.float32, copy=False)
        return embeddings[0] if single else embeddings

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self.encode(texts).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.encode(text).tolist()


class ONNXEmbeddingProvider(_ProductionONNXProvider):
    """Compatibility adapter around the single production implementation."""

    def __init__(
        self,
        onnx_path: Path | str,
        model_path: Path | str | None = None,
        *,
        batch_size: int = 32,
        intra_op_threads: int = 2,
        inter_op_threads: int = 1,
        execution_mode: str = "sequential",
        graph_optimization_level: str = "all",
    ):
        self.model_path = Path(model_path or resolve_model_snapshot()).resolve()
        super().__init__(
            onnx_path,
            self.model_path / "tokenizer.json",
            batch_size=batch_size,
            intra_op_threads=intra_op_threads,
            inter_op_threads=inter_op_threads,
            execution_mode=execution_mode,
            graph_optimization_level=graph_optimization_level,
        )

    def _encode_batch(self, texts: list[str]) -> np.ndarray:
        return self.encode_batch(texts)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self.encode(texts).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.encode(text).tolist()


def production_backend_selected() -> str:
    return os.getenv("TEXA_EMBEDDING_BACKEND", "onnx").strip().lower()
