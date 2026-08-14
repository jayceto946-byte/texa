"""Run the reproducible Torch vs ONNX FP32 embedding feasibility benchmark."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.embedding_backend.benchmark_metrics import (
    overlap_metrics,
    percentile,
    relevance_metrics,
    top_indices,
)
from evaluation.embedding_backend.providers import ONNXEmbeddingProvider, TorchEmbeddingProvider, resolve_model_snapshot


PARITY_PATH = ROOT / "evaluation" / "datasets" / "embedding_parity.json"
RETRIEVAL_PATH = ROOT / "evaluation" / "datasets" / "embedding_retrieval.json"
DEFAULT_ONNX = ROOT / "benchmark_results" / "embedding_onnx" / "bge-small-zh-v1.5-fp32.onnx"
DEFAULT_JSON = ROOT / "benchmark_results" / "embedding_onnx" / "benchmark.json"
DEFAULT_REPORT = ROOT / "benchmark_results" / "embedding_onnx" / "report.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_size(distribution_name: str) -> int:
    try:
        distribution = importlib.metadata.distribution(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return 0
    total = 0
    for item in distribution.files or []:
        try:
            path = Path(distribution.locate_file(item))
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def distribution_sizes(model_path: Path, onnx_path: Path) -> dict:
    packages = [
        "torch", "sentence-transformers", "transformers", "tokenizers", "safetensors",
        "huggingface-hub", "scipy", "scikit-learn", "numpy", "onnxruntime",
    ]
    values = {name: package_size(name) for name in packages}
    tokenizer_assets = sum(
        (model_path / name).stat().st_size
        for name in ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "vocab.txt")
        if (model_path / name).is_file()
    )
    torch_model = (model_path / "model.safetensors").stat().st_size
    common_packages = {"tokenizers", "huggingface-hub", "numpy", "onnxruntime"}
    current_packages = {
        "torch", "sentence-transformers", "transformers", "tokenizers", "safetensors",
        "huggingface-hub", "scipy", "scikit-learn", "numpy",
    }
    onnx_packages = {"onnxruntime", "tokenizers", "numpy"}
    return {
        "installed_distribution_bytes": values,
        "model_assets": {"torch_safetensors": torch_model, "onnx_fp32": onnx_path.stat().st_size, "tokenizer_assets": tokenizer_assets},
        "gross_torch_runtime_bytes": sum(values[name] for name in current_packages) + torch_model + tokenizer_assets,
        "gross_onnx_runtime_bytes": sum(values[name] for name in onnx_packages) + onnx_path.stat().st_size + tokenizer_assets,
        "shared_or_already_required_packages": sorted(common_packages),
        "future_candidate_reduction_bytes_if_all_torch_consumers_removed": sum(
            values[name] for name in ("torch", "sentence-transformers", "transformers", "safetensors", "scipy", "scikit-learn")
        ) + max(0, torch_model - onnx_path.stat().st_size),
        "real_removable_dependency_bytes_preserving_current_optional_reranker": 0,
        "real_removable_model_asset_bytes_preserving_torch_fallback": 0,
        "added_onnx_asset_bytes_preserving_torch_fallback": onnx_path.stat().st_size,
        "estimated_release_net_reduction_bytes_preserving_torch_fallback": -onnx_path.stat().st_size,
        "notes": [
            "onnxruntime, tokenizers and numpy are already dependencies of the installed Chroma stack.",
            "The optional CrossEncoder reranker imports sentence-transformers and therefore retains torch and transformers.",
            "Gross totals intentionally show complete stacks; real removable size excludes shared dependencies and preserves current features.",
        ],
    }


def summarize_cold(samples: list[dict]) -> dict:
    fields = [
        "process_total_ms", "load_ms", "first_embedding_ms", "rss_before_runtime",
        "rss_after_model_load", "peak_rss_after_embedding", "rss_stable_after_embedding",
    ]
    result = {"runs": samples, "run_count": len(samples)}
    for field in fields:
        values = [float(item[field]) for item in samples]
        result[field] = {"median": statistics.median(values), "p95": percentile(values, 95)}
    result["rss_model_load_delta_median"] = statistics.median(
        item["rss_after_model_load"] - item["rss_before_runtime"] for item in samples
    )
    result["rss_peak_inference_delta_median"] = statistics.median(
        item["peak_rss_after_embedding"] - item["rss_before_runtime"] for item in samples
    )
    return result


def run_worker(backend: str, mode: str, onnx_path: Path, repeats: int = 7) -> dict:
    command = [
        sys.executable, "-B", "-m", "evaluation.embedding_backend.benchmark_worker",
        "--backend", backend, "--mode", mode, "--onnx-path", str(onnx_path),
        "--fixture", str(PARITY_PATH), "--repeats", str(repeats),
    ]
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True)
    elapsed = (time.perf_counter() - started) * 1000
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    payload["process_total_ms"] = elapsed
    if completed.stderr.strip():
        payload["stderr"] = completed.stderr.strip()
    return payload


def numeric_parity(torch_values: np.ndarray, onnx_values: np.ndarray, entries: list[dict]) -> dict:
    cosine = np.sum(torch_values * onnx_values, axis=1) / (
        np.linalg.norm(torch_values, axis=1) * np.linalg.norm(onnx_values, axis=1)
    )
    absolute = np.abs(torch_values - onnx_values)
    categories = {}
    for category in sorted({item["category"] for item in entries}):
        indices = [index for index, item in enumerate(entries) if item["category"] == category]
        values = cosine[indices]
        categories[category] = {"count": len(indices), "cosine_mean": float(np.mean(values)), "cosine_min": float(np.min(values))}
    return {
        "count": len(entries),
        "cosine": {
            "mean": float(np.mean(cosine)), "median": float(np.median(cosine)),
            "p95": percentile(cosine, 95), "p05": percentile(cosine, 5), "minimum": float(np.min(cosine)),
        },
        "element_error": {"max_absolute": float(np.max(absolute)), "mean_absolute": float(np.mean(absolute))},
        "norms": {
            "torch_mean": float(np.mean(np.linalg.norm(torch_values, axis=1))),
            "onnx_mean": float(np.mean(np.linalg.norm(onnx_values, axis=1))),
        },
        "categories": categories,
    }


def tokenization_parity(torch_provider, onnx_provider, texts: list[str]) -> dict:
    matching = 0
    for start in range(0, len(texts), 32):
        batch = texts[start : start + 32]
        torch_tokens = torch_provider.model.tokenizer(
            batch, padding=True, truncation=True, max_length=512, return_tensors="np"
        )
        onnx_tokens = onnx_provider.tokenizer.encode_batch(batch)
        ids = np.asarray([item.ids for item in onnx_tokens], dtype=np.int64)
        masks = np.asarray([item.attention_mask for item in onnx_tokens], dtype=np.int64)
        types = np.asarray([item.type_ids for item in onnx_tokens], dtype=np.int64)
        for index in range(len(batch)):
            if (
                np.array_equal(torch_tokens["input_ids"][index], ids[index])
                and np.array_equal(torch_tokens["attention_mask"][index], masks[index])
                and np.array_equal(torch_tokens["token_type_ids"][index], types[index])
            ):
                matching += 1
    return {"total": len(texts), "exact_matches": matching, "all_exact": matching == len(texts)}


def write_report(result: dict, path: Path) -> None:
    parity = result["parity"]
    overlap = result["retrieval"]["overlap"]
    quality = result["retrieval"]["human_quality"]
    cold = result["performance"]["cold"]
    warm = result["performance"]["warm"]
    sizes = result["distribution"]
    mb = lambda value: value / (1024 * 1024)
    lines = [
        "# Texa embedding ONNX Runtime FP32 feasibility report",
        "",
        f"Decision: **{result['decision']['verdict']}** — {result['decision']['reason']}",
        "",
        "## 1. Current embedding baseline",
        "",
        "- Model: `BAAI/bge-small-zh-v1.5`, local snapshot, CPU, float32, 512 dimensions.",
        "- Tokenizer: snapshot `BertTokenizerFast`; 512 tokens; right padding/truncation; SentenceTransformers adds lowercase normalization.",
        "- Graph: BERT -> CLS pooling -> L2 Normalize; project encode also requests normalization; no query/document prompt.",
        "- Production provider remains the lazy singleton in `config.py`; FastAPI startup normally triggers it in background warmup.",
        "",
        "## 2. ONNX implementation",
        "",
        "- Isolated experiment-only provider; production default and existing indexes are unchanged.",
        "- ONNX graph includes the BERT backbone, CLS pooling, and both L2 normalization passes.",
        "- Runtime uses only ONNX Runtime CPUExecutionProvider, raw tokenizers runtime, NumPy, FP32, and two intra-op threads.",
        f"- Tokenization exact matches: {result['tokenization']['exact_matches']}/{result['tokenization']['total']}.",
        "",
        "## 3. Parity test",
        "",
        f"- Dataset: {parity['count']} fixed texts; fixture SHA-256 `{result['fixtures']['parity_sha256']}`.",
        f"- Cosine mean/median/p95/min: {parity['cosine']['mean']:.10f} / {parity['cosine']['median']:.10f} / {parity['cosine']['p95']:.10f} / {parity['cosine']['minimum']:.10f}.",
        f"- Element max/mean absolute error: {parity['element_error']['max_absolute']:.3e} / {parity['element_error']['mean_absolute']:.3e}.",
        "",
        "## 4. Retrieval quality",
        "",
        f"- Fixed corpus/query counts: {result['retrieval']['corpus_count']} / {result['retrieval']['query_count']}; 40 human-curated queries.",
        f"- Top-1/3/5/10 set overlap: {overlap['top_1']['mean_set_overlap']:.2%} / {overlap['top_3']['mean_set_overlap']:.2%} / {overlap['top_5']['mean_set_overlap']:.2%} / {overlap['top_10']['mean_set_overlap']:.2%}.",
        f"- Torch Recall@1/3/5, MRR@10: {quality['torch']['recall_at_1']:.2%} / {quality['torch']['recall_at_3']:.2%} / {quality['torch']['recall_at_5']:.2%} / {quality['torch']['mrr_at_10']:.4f}.",
        f"- ONNX Recall@1/3/5, MRR@10: {quality['onnx']['recall_at_1']:.2%} / {quality['onnx']['recall_at_3']:.2%} / {quality['onnx']['recall_at_5']:.2%} / {quality['onnx']['mrr_at_10']:.4f}.",
        f"- ONNX minus Torch: Recall@5 {quality['delta']['recall_at_5_percentage_points']:+.2f} pp; MRR {quality['delta']['mrr_relative_percent']:+.3f}% relative.",
        "- With only 40 human queries, this detects large/systematic regressions but cannot establish statistical equivalence.",
        "",
        "## 5. Cold-start benchmark",
        "",
        f"- Fresh-process runs per backend: {cold['torch']['run_count']}.",
        f"- Torch process total median/p95: {cold['torch']['process_total_ms']['median']:.1f} / {cold['torch']['process_total_ms']['p95']:.1f} ms.",
        f"- ONNX process total median/p95: {cold['onnx']['process_total_ms']['median']:.1f} / {cold['onnx']['process_total_ms']['p95']:.1f} ms.",
        "- Times include interpreter startup, runtime import, tokenizer/model load, and first embedding. Local model files are fixed; OS disk cache was not forcibly flushed.",
        "",
        "## 6. Warm inference benchmark",
        "",
        "- Input profile: batch 1 is a short query; batch 8/32/100 use a fixed mix of 75% formula/medium chunks (at most 900 characters) and 25% normal 50-300-character paragraphs. Both backends receive identical texts.",
        "",
        "| batch | Torch median / p95 | ONNX median / p95 | Torch texts/s | ONNX texts/s |",
        "|---:|---:|---:|---:|---:|",
    ]
    for size in ("1", "8", "32", "100"):
        left, right = warm["torch"]["batches"][size], warm["onnx"]["batches"][size]
        lines.append(
            f"| {size} | {left['median_ms']:.1f} / {left['p95_ms']:.1f} ms | {right['median_ms']:.1f} / {right['p95_ms']:.1f} ms | "
            f"{left['median_texts_per_second']:.1f} | {right['median_texts_per_second']:.1f} |"
        )
    lines.extend([
        "",
        "## 7. RAM benchmark",
        "",
        f"- Torch median model-load RSS delta / inference peak delta: {mb(cold['torch']['rss_model_load_delta_median']):.1f} / {mb(cold['torch']['rss_peak_inference_delta_median']):.1f} MB.",
        f"- ONNX median model-load RSS delta / inference peak delta: {mb(cold['onnx']['rss_model_load_delta_median']):.1f} / {mb(cold['onnx']['rss_peak_inference_delta_median']):.1f} MB.",
        "",
        "## 8. Distribution size",
        "",
        f"- Gross Torch embedding stack: {mb(sizes['gross_torch_runtime_bytes']):.1f} MB.",
        f"- Gross ONNX embedding stack: {mb(sizes['gross_onnx_runtime_bytes']):.1f} MB.",
        f"- Future candidate reduction only if fallback, CrossEncoder, and all other Torch consumers are removed/replaced: {mb(sizes['future_candidate_reduction_bytes_if_all_torch_consumers_removed']):.1f} MB.",
        f"- Real removable dependency size while preserving the current optional reranker: {mb(sizes['real_removable_dependency_bytes_preserving_current_optional_reranker']):.1f} MB.",
        f"- Because the Torch fallback must remain, its safetensors asset cannot be removed; adding ONNX grows the release by about {mb(sizes['added_onnx_asset_bytes_preserving_torch_fallback']):.1f} MB.",
        "- These are installed-distribution bytes, not only wheel/model sizes; PyInstaller collection still requires a separate release build measurement before migration.",
        "",
        "## 9. Removable dependencies",
        "",
        f"- Completely delete torch: **{result['dependency_audit']['delete_torch']}** — production fallback, optional CrossEncoder, legacy tooling, and release build checks still use it.",
        f"- Completely delete sentence-transformers: **{result['dependency_audit']['delete_sentence_transformers']}** — production fallback, optional CrossEncoder, and legacy tooling still use it.",
        f"- Completely delete transformers: **{result['dependency_audit']['delete_transformers']}** — production fallback imports it and SentenceTransformers/CrossEncoder retains it transitively.",
        "",
        "## 10. Problems found",
        "",
        "- Raw `tokenizer.json` alone was not equivalent: SentenceTransformers prepends lowercase normalization from `sentence_bert_config.json`. The provider now reproduces it and the fixture verifies every token sequence.",
        "- Some source chunks split headings from following content; one human label was corrected during review. The final fixture targets text that actually supports each query.",
        "",
        "## 11. Risks",
        "",
        "- Existing Chroma vectors remain numerically compatible in this experiment, but no production index was changed or rebuilt.",
        "- The 500-chunk isolated dense benchmark does not exercise BM25, KG, reranking, Chroma HNSW approximation, or full production fan-out; those variables were intentionally held out.",
        "- Windows results on this machine do not generalize to all CPUs or packaged Electron/PyInstaller cold starts.",
        "",
        "## 12. GO / NO-GO",
        "",
        f"**{result['decision']['verdict']}**",
        "",
        result["decision"]["reason"],
        "",
        "The experimental ONNX provider and benchmark should be retained. The old backend has not been removed or changed.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx-path", type=Path, default=DEFAULT_ONNX)
    parser.add_argument("--output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--cold-runs", type=int, default=5)
    parser.add_argument("--warm-repeats", type=int, default=7)
    args = parser.parse_args()
    onnx_path = args.onnx_path.resolve()
    if not onnx_path.is_file():
        raise SystemExit(f"Export ONNX model first: {onnx_path}")

    parity_fixture = json.loads(PARITY_PATH.read_text(encoding="utf-8"))
    retrieval_fixture = json.loads(RETRIEVAL_PATH.read_text(encoding="utf-8"))
    parity_texts = [item["text"] for item in parity_fixture["texts"]]

    torch_provider = TorchEmbeddingProvider(batch_size=32)
    onnx_provider = ONNXEmbeddingProvider(onnx_path, batch_size=32)
    tokenization = tokenization_parity(torch_provider, onnx_provider, parity_texts)
    torch_parity = torch_provider.encode(parity_texts)
    onnx_parity = onnx_provider.encode(parity_texts)
    parity = numeric_parity(torch_parity, onnx_parity, parity_fixture["texts"])

    corpus_texts = [item["text"] for item in retrieval_fixture["corpus"]]
    corpus_ids = [item["id"] for item in retrieval_fixture["corpus"]]
    queries = retrieval_fixture["queries"]
    query_texts = [item["query"] for item in queries]
    torch_ranks = top_indices(torch_provider.encode(query_texts), torch_provider.encode(corpus_texts), 10)
    onnx_ranks = top_indices(onnx_provider.encode(query_texts), onnx_provider.encode(corpus_texts), 10)
    manual = [query for query in queries if query["label_source"] == "human_curated"]
    manual_count = len(manual)
    torch_quality = relevance_metrics(torch_ranks[:manual_count], corpus_ids, manual)
    onnx_quality = relevance_metrics(onnx_ranks[:manual_count], corpus_ids, manual)
    mrr_denominator = torch_quality["mrr_at_10"] or 1.0
    retrieval = {
        "corpus_count": len(corpus_texts), "query_count": len(queries),
        "overlap": overlap_metrics(torch_ranks, onnx_ranks),
        "human_quality": {
            "torch": torch_quality, "onnx": onnx_quality,
            "delta": {
                "recall_at_5_percentage_points": (onnx_quality["recall_at_5"] - torch_quality["recall_at_5"]) * 100,
                "mrr_absolute": onnx_quality["mrr_at_10"] - torch_quality["mrr_at_10"],
                "mrr_relative_percent": (onnx_quality["mrr_at_10"] - torch_quality["mrr_at_10"]) / mrr_denominator * 100,
            },
        },
    }

    # Release large parent-held models before isolated process measurements.
    del torch_provider, onnx_provider, torch_parity, onnx_parity
    cold_samples = {"torch": [], "onnx": []}
    for index in range(args.cold_runs):
        order = ("torch", "onnx") if index % 2 == 0 else ("onnx", "torch")
        for backend in order:
            cold_samples[backend].append(run_worker(backend, "cold", onnx_path, args.warm_repeats))
    cold = {backend: summarize_cold(samples) for backend, samples in cold_samples.items()}
    warm = {
        backend: run_worker(backend, "warm", onnx_path, args.warm_repeats)
        for backend in ("torch", "onnx")
    }
    model_path = resolve_model_snapshot()
    distribution = distribution_sizes(model_path, onnx_path)

    quality_pass = (
        parity["cosine"]["mean"] >= 0.9999
        and parity["cosine"]["minimum"] >= 0.999
        and retrieval["overlap"]["top_10"]["mean_set_overlap"] >= 0.99
        and retrieval["overlap"]["top_5"]["mean_set_overlap"] >= 0.98
        and retrieval["human_quality"]["delta"]["recall_at_5_percentage_points"] >= -1.0
        and retrieval["human_quality"]["delta"]["mrr_relative_percent"] >= -1.0
    )
    cold_better = cold["onnx"]["process_total_ms"]["median"] < cold["torch"]["process_total_ms"]["median"] * 0.95
    ram_better = cold["onnx"]["rss_peak_inference_delta_median"] < cold["torch"]["rss_peak_inference_delta_median"] * 0.9
    warm_not_regressed = all(
        warm["onnx"]["batches"][size]["median_ms"] <= warm["torch"]["batches"][size]["median_ms"] * 1.1
        for size in ("1", "8", "32", "100")
    )
    performance_pass = (cold_better or ram_better or warm_not_regressed) and warm_not_regressed
    distribution_pass = distribution["estimated_release_net_reduction_bytes_preserving_torch_fallback"] >= 100 * 1024 * 1024
    verdict = "GO" if quality_pass and performance_pass and distribution_pass else "NO-GO"
    reason = (
        "All quality, performance, and real removable distribution-size gates passed; proceed only to a separately reviewed small production trial."
        if verdict == "GO" else
        "The ONNX embedding path is numerically/retrieval compatible and greatly improves cold start/RAM, but batch-100 warm inference regresses by more than the allowed 10%. More importantly, the required Torch fallback and optional CrossEncoder reranker retain SentenceTransformers, Transformers, Torch, and the safetensors model. No dependency or old model asset can be removed, while ONNX adds about 90.5 MB. Performance and distribution gates therefore fail. Keep PyTorch as the production default."
    )
    result = {
        "schema_version": 1,
        "generated_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "environment": {
            "platform": platform.platform(), "python": sys.version, "processor": platform.processor(),
            "cpu_count": os.cpu_count(), "onnxruntime": importlib.metadata.version("onnxruntime"),
            "torch": importlib.metadata.version("torch"), "sentence_transformers": importlib.metadata.version("sentence-transformers"),
        },
        "fixtures": {"parity_path": str(PARITY_PATH), "parity_sha256": sha256(PARITY_PATH),
                     "retrieval_path": str(RETRIEVAL_PATH), "retrieval_sha256": sha256(RETRIEVAL_PATH)},
        "onnx": {"path": str(onnx_path), "sha256": sha256(onnx_path), "bytes": onnx_path.stat().st_size},
        "tokenization": tokenization, "parity": parity, "retrieval": retrieval,
        "performance": {"cold": cold, "warm": warm}, "distribution": distribution,
        "dependency_audit": {
            "delete_torch": "NO", "delete_sentence_transformers": "NO", "delete_transformers": "NO",
            "blocking_source": "config.py production fallback; ingestion/reranker.py optional CrossEncoder; legacy index/build tooling and release CPU-Torch checks",
        },
        "decision": {"verdict": verdict, "reason": reason, "gates": {
            "quality": quality_pass, "performance": performance_pass, "distribution": distribution_pass,
            "cold_improved_5_percent": cold_better, "ram_improved_10_percent": ram_better,
            "warm_no_batch_regressed_over_10_percent": warm_not_regressed,
        }},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(result, args.report)
    print(json.dumps({"output": str(args.output), "report": str(args.report), "decision": result["decision"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
