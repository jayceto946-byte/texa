"""Orchestrate the isolated ONNX Runtime FP32 Phase 1 benchmark.

Results are checkpointed after every worker, so long CPU experiments can be
resumed by rerunning only the requested section. Production configuration and
indexes are never imported or modified.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.embedding_backend.benchmark_metrics import overlap_metrics, top_indices
from evaluation.embedding_backend.phase1_worker import physical_core_count
from evaluation.embedding_backend.providers import ONNXEmbeddingProvider, TorchEmbeddingProvider

DEFAULT_DIR = ROOT / "benchmark_results" / "embedding_onnx_phase1"
DEFAULT_ONNX = ROOT / "benchmark_results" / "embedding_onnx" / "bge-small-zh-v1.5-fp32.onnx"
PARITY_PATH = ROOT / "evaluation" / "datasets" / "embedding_parity.json"
RETRIEVAL_PATH = ROOT / "evaluation" / "datasets" / "embedding_retrieval.json"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run_worker(args, *, task: str, backend: str, repeats: int, extra: list[str] | None = None) -> dict:
    command = [
        sys.executable, "-B", "-m", "evaluation.embedding_backend.phase1_worker",
        "--task", task, "--backend", backend, "--onnx-path", str(args.onnx_path),
        "--repeats", str(repeats),
    ]
    command.extend(extra or [])
    print(f"RUN {' '.join(command[5:])}", flush=True)
    completed = subprocess.run(
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=None,
        text=True, encoding="utf-8", check=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def graph_audit(path: Path) -> dict:
    import onnx

    model = onnx.load(str(path), load_external_data=False)

    def value_info(item) -> dict:
        tensor = item.type.tensor_type
        shape = []
        for dim in tensor.shape.dim:
            shape.append(dim.dim_param or (int(dim.dim_value) if dim.dim_value else None))
        return {"name": item.name, "element_type": int(tensor.elem_type), "shape": shape}

    nodes = Counter(node.op_type for node in model.graph.node)
    casts = []
    for node in model.graph.node:
        if node.op_type == "Cast":
            casts.append({"name": node.name, "inputs": list(node.input), "outputs": list(node.output)})
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "opsets": [{"domain": item.domain, "version": item.version} for item in model.opset_import],
        "inputs": [value_info(item) for item in model.graph.input],
        "outputs": [value_info(item) for item in model.graph.output],
        "node_count": len(model.graph.node),
        "node_types": dict(sorted(nodes.items())),
        "cast_nodes": casts,
        "reshape_count": nodes["Reshape"],
        "reduce_l2_count": nodes["ReduceL2"],
        "div_count": nodes["Div"],
        "dynamic_batch": all(item["shape"][0] == "batch" for item in [value_info(x) for x in model.graph.input]),
        "dynamic_sequence": all(item["shape"][1] == "sequence" for item in [value_info(x) for x in model.graph.input]),
    }


def cosine_summary(left: np.ndarray, right: np.ndarray) -> dict:
    cosine = np.sum(left * right, axis=1) / (np.linalg.norm(left, axis=1) * np.linalg.norm(right, axis=1))
    return {
        "count": len(cosine), "mean": float(np.mean(cosine)),
        "minimum": float(np.min(cosine)), "maximum": float(np.max(cosine)),
    }


def quality_checks(args, single_path: Path, best_intra: int) -> dict:
    parity = json.loads(PARITY_PATH.read_text(encoding="utf-8"))
    all_texts = [item["text"] for item in parity["texts"]]
    spot_texts = all_texts[:50]
    torch = TorchEmbeddingProvider(batch_size=32, num_threads=2)
    torch_spot = torch.encode(spot_texts)
    del torch
    baseline = ONNXEmbeddingProvider(
        args.onnx_path, batch_size=32, intra_op_threads=best_intra,
        graph_optimization_level="all",
    )
    baseline_spot = baseline.encode(spot_texts)
    spot = cosine_summary(torch_spot, baseline_spot)
    single = ONNXEmbeddingProvider(
        single_path, batch_size=32, intra_op_threads=best_intra,
        graph_optimization_level="all",
    )
    single_spot = single.encode(spot_texts)
    single_vs_baseline_spot = cosine_summary(baseline_spot, single_spot)

    # A graph simplification is only called compatible after full fixture and
    # retrieval ranking parity, not from the 50-text spot-check alone.
    baseline_all = baseline.encode(all_texts)
    single_all = single.encode(all_texts)
    full_embedding = cosine_summary(baseline_all, single_all)
    retrieval = json.loads(RETRIEVAL_PATH.read_text(encoding="utf-8"))
    corpus = [item["text"] for item in retrieval["corpus"]]
    queries = [item["query"] for item in retrieval["queries"]]
    baseline_ranks = top_indices(baseline.encode(queries), baseline.encode(corpus), 10)
    single_ranks = top_indices(single.encode(queries), single.encode(corpus), 10)
    return {
        "optimized_baseline_vs_torch_50": spot,
        "single_vs_baseline_50": single_vs_baseline_spot,
        "single_vs_baseline_all_340": full_embedding,
        "single_vs_baseline_retrieval": overlap_metrics(baseline_ranks, single_ranks),
    }


def save_section(result_path: Path, result: dict, section: str, payload) -> None:
    result["sections"][section] = payload
    result["updated_at"] = datetime.now().astimezone().isoformat()
    write_json(result_path, result)
    print(f"SAVED {section}", flush=True)


def best_intra_from(result: dict) -> int:
    tuning = result.get("sections", {}).get("threading", {}).get("intra_op", {})
    if not tuning:
        return 2
    # Offline choice: minimum batch-100 median. Interactive recommendation is
    # evaluated independently in the report.
    return min(
        ((int(key), value["cases"]["100"]["median_ms"]) for key, value in tuning.items()),
        key=lambda item: item[1],
    )[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--section", action="append",
        choices=("audit", "scaling", "profiles", "micro", "strategies", "threading", "graph", "breakdown", "quality", "ingestion"),
        required=True,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--onnx-path", type=Path, default=DEFAULT_ONNX)
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.onnx_path = args.onnx_path.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result_path = args.output_dir / "phase1.json"
    if result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8"))
    else:
        result = {
            "schema_version": 1,
            "created_at": datetime.now().astimezone().isoformat(),
            "production_backend_changed": False,
            "sections": {},
        }

    for section in args.section:
        if section == "audit":
            payload = {
                "logical_cpu_count": os.cpu_count(),
                "physical_cpu_core_count": physical_core_count(),
                "baseline_graph": graph_audit(args.onnx_path),
                "phase0_metadata": json.loads(args.onnx_path.with_suffix(".metadata.json").read_text(encoding="utf-8")),
            }
        elif section == "scaling":
            payload = result.get("sections", {}).get("scaling", {})
            sizes = (1, 4, 8, 16, 24, 32, 48, 64, 96, 100, 128)
            for backend in ("torch", "onnx"):
                backend_payload = payload.setdefault(backend, {"task": "scaling", "backend": backend, "cases": {}})
                for size in sizes:
                    if str(size) in backend_payload["cases"]:
                        continue
                    item = run_worker(
                        args, task="scaling", backend=backend, repeats=10,
                        extra=["--sizes", str(size)],
                    )
                    backend_payload["cases"][str(size)] = item["cases"][str(size)]
                    backend_payload["environment"] = item["environment"]
                    save_section(result_path, result, section, payload)
        elif section == "profiles":
            payload = result.get("sections", {}).get("profiles", {})
            for backend in ("torch", "onnx"):
                backend_payload = payload.setdefault(
                    backend,
                    {"task": "profiles", "backend": backend, "cases": {}, "profile_definition": {}},
                )
                for size in (8, 16, 32, 64, 100):
                    if all(str(size) in backend_payload["cases"].get(name, {}) for name in ("short", "normal", "long")):
                        continue
                    item = run_worker(
                        args, task="profiles", backend=backend, repeats=10,
                        extra=["--profile-sizes", str(size)],
                    )
                    backend_payload["profile_definition"] = item["profile_definition"]
                    backend_payload["source_counts"] = item["source_counts"]
                    backend_payload["environment"] = item["environment"]
                    for name in ("short", "normal", "long"):
                        backend_payload["cases"].setdefault(name, {})[str(size)] = item["cases"][name][str(size)]
                    save_section(result_path, result, section, payload)
        elif section == "micro":
            payload = run_worker(args, task="micro", backend="onnx", repeats=10)
        elif section == "strategies":
            payload = {
                str(batch): run_worker(
                    args, task="strategies", backend="onnx", repeats=3,
                    extra=["--batch-size", str(batch)],
                )
                for batch in (16, 32, 64)
            }
        elif section == "threading":
            physical = physical_core_count()
            intra_values = sorted({1, 2, 4, 8, physical})
            payload = result.get("sections", {}).get(
                "threading", {"intra_op": {}, "inter_op": {}, "execution_mode": {}}
            )
            for value in intra_values:
                if str(value) in payload["intra_op"]:
                    continue
                payload["intra_op"][str(value)] = run_worker(
                    args, task="scaling", backend="onnx", repeats=5,
                    extra=["--sizes", "1", "32", "100", "--intra", str(value)],
                )
                save_section(result_path, result, section, payload)
            for value in (1, 2, 4):
                if str(value) in payload["inter_op"]:
                    continue
                payload["inter_op"][str(value)] = run_worker(
                    args, task="scaling", backend="onnx", repeats=5,
                    extra=["--sizes", "1", "32", "100", "--inter", str(value)],
                )
                save_section(result_path, result, section, payload)
            for value in ("sequential", "parallel"):
                if value in payload["execution_mode"]:
                    continue
                payload["execution_mode"][value] = run_worker(
                    args, task="scaling", backend="onnx", repeats=5,
                    extra=["--sizes", "1", "32", "100", "--execution-mode", value],
                )
                save_section(result_path, result, section, payload)
        elif section == "graph":
            payload = result.get("sections", {}).get("graph", {"optimization_levels": {}})
            for value in ("disable", "basic", "extended", "all"):
                if value in payload["optimization_levels"]:
                    continue
                payload["optimization_levels"][value] = run_worker(
                    args, task="scaling", backend="onnx", repeats=5,
                    extra=["--sizes", "1", "32", "100", "--graph-optimization", value],
                )
                save_section(result_path, result, section, payload)
            single_path = args.output_dir / "bge-small-zh-v1.5-fp32-single-normalization.onnx"
            if "single_normalization_performance" not in payload:
                subprocess.run([
                    sys.executable, "-B", "-m", "scripts.export_bge_onnx",
                    "--output", str(single_path), "--normalization-passes", "1",
                ], cwd=ROOT, check=True)
                payload["single_normalization_graph"] = graph_audit(single_path)
                payload["single_normalization_performance"] = run_worker(
                    args, task="scaling", backend="onnx", repeats=5,
                    extra=["--sizes", "1", "32", "100", "--onnx-path", str(single_path)],
                )
                save_section(result_path, result, section, payload)
        elif section == "breakdown":
            payload = run_worker(args, task="breakdown", backend="onnx", repeats=10)
        elif section == "quality":
            single_path = args.output_dir / "bge-small-zh-v1.5-fp32-single-normalization.onnx"
            if not single_path.is_file():
                raise SystemExit("Run --section graph before quality")
            payload = quality_checks(args, single_path, best_intra_from(result))
        elif section == "ingestion":
            best_intra = best_intra_from(result)
            payload = result.get("sections", {}).get("ingestion", {})
            candidates = {
                "torch_current_batch32": ("torch", ["--batch-size", "32", "--strategy", "naive"]),
                "onnx_naive_batch100": ("onnx", ["--batch-size", "100", "--strategy", "naive", "--intra", "2"]),
                "onnx_bucket_batch16_intra12": ("onnx", ["--batch-size", "16", "--strategy", "length_bucket", "--intra", str(best_intra)]),
                "onnx_sorted_batch16_intra12": ("onnx", ["--batch-size", "16", "--strategy", "length_sorted", "--intra", str(best_intra)]),
                "onnx_bucket_batch32_intra12": ("onnx", ["--batch-size", "32", "--strategy", "length_bucket", "--intra", str(best_intra)]),
                "onnx_sorted_batch32_intra12": ("onnx", ["--batch-size", "32", "--strategy", "length_sorted", "--intra", str(best_intra)]),
            }
            # Preserve the original key from an earlier checkpoint.
            if "onnx_optimized_bucket32" in payload and "onnx_bucket_batch32_intra12" not in payload:
                payload["onnx_bucket_batch32_intra12"] = payload.pop("onnx_optimized_bucket32")
            for name, (backend, extra) in candidates.items():
                if name in payload:
                    continue
                payload[name] = run_worker(
                    args, task="ingestion", backend=backend, repeats=3,
                    extra=extra,
                )
                payload["selected_intra_op_threads"] = best_intra
                save_section(result_path, result, section, payload)
        else:
            raise AssertionError(section)
        save_section(result_path, result, section, payload)

    print(f"RESULT={result_path}", flush=True)


if __name__ == "__main__":
    main()
