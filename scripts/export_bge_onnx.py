"""Export the current local BGE snapshot to an experimental FP32 ONNX graph."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.embedding_backend.providers import resolve_model_snapshot


DEFAULT_OUTPUT = ROOT / "benchmark_results" / "embedding_onnx" / "bge-small-zh-v1.5-fp32.onnx"


def load_sentence_transformer(model_path: Path):
    import torch

    torch.set_num_threads(2)
    original_find_spec = importlib.util.find_spec
    importlib.util.find_spec = lambda name, *args, **kwargs: (
        None if name == "torchvision" or name.startswith("torchvision.") else original_find_spec(name, *args, **kwargs)
    )
    try:
        import transformers.utils.import_utils as transformers_import_utils

        transformers_import_utils._torchvision_available = False
        from sentence_transformers import SentenceTransformer
    finally:
        importlib.util.find_spec = original_find_spec
    return SentenceTransformer(str(model_path), device="cpu", local_files_only=True)


def export_model(model_path: Path, output_path: Path, *, normalization_passes: int = 2) -> dict:
    import onnx
    import torch
    import torch.nn.functional as functional

    sentence_model = load_sentence_transformer(model_path)
    auto_model = sentence_model[0].auto_model.eval()

    class ExactEmbeddingGraph(torch.nn.Module):
        def __init__(self, backbone, passes: int):
            super().__init__()
            self.backbone = backbone
            self.passes = passes

        def forward(self, input_ids, attention_mask, token_type_ids):
            output = self.backbone(
                input_ids=input_ids,
                attention_mask=attention_mask,
                token_type_ids=token_type_ids,
                return_dict=False,
            )[0]
            pooled = output[:, 0]
            normalized = functional.normalize(pooled, p=2, dim=1)
            if self.passes == 1:
                return normalized
            # Baseline-compatible graph: snapshot module 2_Normalize followed
            # by encode(normalize_embeddings=True).
            return functional.normalize(normalized, p=2, dim=1)

    if normalization_passes not in {1, 2}:
        raise ValueError("normalization_passes must be 1 or 2")
    graph = ExactEmbeddingGraph(auto_model, normalization_passes).eval()
    sample = sentence_model.tokenizer(
        ["压阻效应", "灵敏度 $S=\\Delta y/\\Delta x$"],
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with torch.inference_mode():
        torch.onnx.export(
            graph,
            (sample["input_ids"], sample["attention_mask"], sample["token_type_ids"]),
            str(output_path),
            input_names=["input_ids", "attention_mask", "token_type_ids"],
            output_names=["sentence_embedding"],
            dynamic_axes={
                "input_ids": {0: "batch", 1: "sequence"},
                "attention_mask": {0: "batch", 1: "sequence"},
                "token_type_ids": {0: "batch", 1: "sequence"},
                "sentence_embedding": {0: "batch"},
            },
            opset_version=17,
            do_constant_folding=True,
            dynamo=False,
        )
    model = onnx.load(str(output_path))
    onnx.checker.check_model(model)
    info = {
        "model_path": str(model_path),
        "onnx_path": str(output_path.resolve()),
        "bytes": output_path.stat().st_size,
        "opset": 17,
        "dtype": "float32",
        "pooling": "cls",
        "normalization_passes": normalization_passes,
        "max_length": 512,
        "inputs": ["input_ids", "attention_mask", "token_type_ids"],
        "output": "sentence_embedding",
    }
    output_path.with_suffix(".metadata.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return info


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--normalization-passes", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    model_path = (args.model_path or resolve_model_snapshot()).resolve()
    print(json.dumps(
        export_model(model_path, args.output.resolve(), normalization_passes=args.normalization_passes),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
