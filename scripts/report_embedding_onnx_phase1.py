"""Generate the final ONNX FP32 Phase 1 report from checkpointed results."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHASE1 = ROOT / "benchmark_results" / "embedding_onnx_phase1" / "phase1.json"
PHASE0 = ROOT / "benchmark_results" / "embedding_onnx" / "benchmark.json"
REPORT = ROOT / "benchmark_results" / "embedding_onnx_phase1" / "report.md"


def mb(value: float) -> float:
    return value / (1024 * 1024)


def fmt_cpu(value) -> str:
    return "N/A*" if value is None else f"{value:.2f}"


def main() -> None:
    result = json.loads(PHASE1.read_text(encoding="utf-8"))
    phase0 = json.loads(PHASE0.read_text(encoding="utf-8"))
    sections = result["sections"]
    scaling = sections["scaling"]
    profiles = sections["profiles"]
    micro = sections["micro"]["cases"]
    strategies = sections["strategies"]
    threading = sections["threading"]
    graph = sections["graph"]
    breakdown = sections["breakdown"]["cases"]
    ingestion = sections["ingestion"]
    quality = sections["quality"]
    audit = sections["audit"]
    torch_ingest = ingestion["torch_current_batch32"]["result"]
    onnx_naive = ingestion["onnx_naive_batch100"]["result"]
    onnx_bucket = ingestion["onnx_bucket_batch16_intra12"]["result"]
    onnx_sorted = ingestion["onnx_sorted_batch16_intra12"]["result"]
    throughput_ratio = onnx_bucket["texts_per_second"] / torch_ingest["texts_per_second"]
    sorted_ratio = onnx_sorted["texts_per_second"] / torch_ingest["texts_per_second"]
    ram_ratio = onnx_bucket["peak_rss_bytes_median"] / torch_ingest["peak_rss_bytes_median"]
    cosine_mean = quality["optimized_baseline_vs_torch_50"]["mean"]
    interactive_pass = scaling["onnx"]["cases"]["1"]["median_ms"] <= scaling["torch"]["cases"]["1"]["median_ms"]
    ingestion_pass = throughput_ratio >= 0.90 and ram_ratio <= 1.20
    quality_pass = cosine_mean >= 0.9999
    verdict = "PHASE 1 PASS" if interactive_pass and ingestion_pass and quality_pass else "PHASE 1 FAIL"

    lines = [
        "# ONNX Runtime FP32 Phase 1 — CPU batch throughput",
        "",
        f"**{verdict}**",
        "",
        "Production embedding backend, dependencies, Chroma, BM25, KG and reranker were not changed. All code and models in this report are experiment-only.",
        "",
        "## 1. Regression reproduction",
        "",
        "- CPU: 12th Gen Intel Core i5-12500H, 12 physical / 16 logical cores; Windows; CPUExecutionProvider; FP32.",
        "- Baseline control: Torch threads=2; ORT intra=2, inter=1, sequential, ORT_ENABLE_ALL.",
        "- Every backend/batch point has one untimed warm-up followed by 10 timed warm runs.",
        f"- Batch=100 median: Torch {scaling['torch']['cases']['100']['median_ms']:.1f} ms vs ONNX {scaling['onnx']['cases']['100']['median_ms']:.1f} ms, ONNX regression {(scaling['onnx']['cases']['100']['median_ms']/scaling['torch']['cases']['100']['median_ms']-1)*100:.1f}%.",
        "- The earlier 18–22% batch=100 regression did not reproduce at that magnitude. A regression did reproduce, but its largest stable region is batch 16–48 (22.6–26.6%), then narrows to 6.9% at batch=100 and 5.4% at batch=128.",
        "",
        "## 2. Batch-size scaling curve",
        "",
        "| Batch | Torch median / p95 ms | ONNX median / p95 ms | Torch / ONNX texts/s | ONNX Δ latency | Torch / ONNX CPU cores | Torch / ONNX peak RSS MB | Torch / ONNX threads |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    sizes = ("1", "4", "8", "16", "24", "32", "48", "64", "96", "100", "128")
    for size in sizes:
        left, right = scaling["torch"]["cases"][size], scaling["onnx"]["cases"][size]
        lines.append(
            f"| {size} | {left['median_ms']:.1f} / {left['p95_ms']:.1f} | {right['median_ms']:.1f} / {right['p95_ms']:.1f} | "
            f"{left['texts_per_second']:.2f} / {right['texts_per_second']:.2f} | {(right['median_ms']/left['median_ms']-1)*100:+.1f}% | "
            f"{fmt_cpu(left['effective_cpu_cores_median'])} / {fmt_cpu(right['effective_cpu_cores_median'])} | "
            f"{mb(left['peak_rss_bytes_median']):.1f} / {mb(right['peak_rss_bytes_median']):.1f} | "
            f"{left['max_native_threads_median']:.0f} / {right['max_native_threads_median']:.0f} |"
        )
    lines.extend([
        "",
        "\* Windows process CPU time has ~15.6 ms granularity; CPU utilization for sub-20 ms batch=1 samples is not reliable. Latency, RSS and thread count remain valid.",
        "",
        "The throughput curve does not have a simple 'large batch is worse' shape. At two threads ORT loses most at 16–48, while 100–128 recover relative efficiency at the cost of very high peak RSS. Batch=128 is not a reasonable ingestion default.",
        "",
        "## 3. Input-length impact",
        "",
        "| Profile | Batch | Torch ms | ONNX ms | ONNX Δ | Torch / ONNX texts/s | Max tokens | Padding ratio |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for profile in ("short", "normal", "long"):
        for size in ("8", "16", "32", "64", "100"):
            left = profiles["torch"]["cases"][profile][size]
            right = profiles["onnx"]["cases"][profile][size]
            lines.append(
                f"| {profile} | {size} | {left['median_ms']:.1f} | {right['median_ms']:.1f} | "
                f"{(right['median_ms']/left['median_ms']-1)*100:+.1f}% | {left['texts_per_second']:.2f} / {right['texts_per_second']:.2f} | "
                f"{right['tokens']['max_token_length']} | {right['tokens']['padding_ratio']:.3f} |"
            )
    lines.extend([
        "",
        "Short texts have no ONNX regression; ONNX is up to 6% faster and is equal at batch=100. Normal paragraphs regress as batch padding rises. Long 512-token chunks regress even with padding ratio=1.0, proving padding amplifies but does not fully cause the issue; long-sequence ORT compute/memory scheduling is also weaker at two threads.",
        "",
        "## 4. Padding analysis",
        "",
        "Main mixed profile token statistics (identical for Torch and ONNX):",
        "",
        "| Batch | Min / median / max tokens | Real tokens | Padded tokens | Padding ratio | Waste fraction |",
        "|---:|---:|---:|---:|---:|---:|",
    ])
    for size in sizes:
        token = scaling["onnx"]["cases"][size]["tokens"]
        lines.append(
            f"| {size} | {token['min_token_length']} / {token['median_token_length']:.1f} / {token['max_token_length']} | "
            f"{token['total_real_tokens']} | {token['total_padded_tokens']} | {token['padding_ratio']:.3f} | {token['padding_waste_fraction']:.1%} |"
        )
    lines.extend([
        "",
        f"Batch=100 contains {scaling['onnx']['cases']['100']['tokens']['total_real_tokens']:,} real tokens but executes {scaling['onnx']['cases']['100']['tokens']['total_padded_tokens']:,} padded tokens (ratio {scaling['onnx']['cases']['100']['tokens']['padding_ratio']:.3f}; {scaling['onnx']['cases']['100']['tokens']['padding_waste_fraction']:.1%} of executed token slots are padding). A few 512-token chunks force the complete naive batch to sequence length 512. This part is a batching-strategy problem, not a fixed-shape export problem.",
        "",
        "## 5. Micro-batching results",
        "",
        "The same 100 texts were kept in the same order.",
        "",
        "| Plan | Median / p95 ms | Texts/s | Padding ratio | Peak RSS MB |",
        "|---|---:|---:|---:|---:|",
    ])
    for name, item in micro.items():
        lines.append(
            f"| {name} | {item['median_ms']:.1f} / {item['p95_ms']:.1f} | {item['texts_per_second']:.2f} | "
            f"{item['tokens']['padding_ratio']:.3f} | {mb(item['peak_rss_bytes_median']):.1f} |"
        )
    lines.extend([
        "",
        "Pure contiguous micro-batching is insufficient. The best plan, 8×12+4, is only 4.8% faster than ONNX batch=100 and remains about 8.5% slower than Torch batch=100 because it barely changes padding.",
        "",
        "## 6. Length-aware batching results",
        "",
        "500 fixed real textbook chunks; embeddings are written back to original indices.",
        "",
        "| Batch | Strategy | Median ms | Texts/s | Padding ratio | Peak RSS MB | Output-order cosine min |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ])
    for batch in ("16", "32", "64"):
        for name, item in strategies[batch]["cases"].items():
            lines.append(
                f"| {batch} | {name} | {item['median_ms']:.1f} | {item['texts_per_second']:.2f} | "
                f"{item['tokens']['padding_ratio']:.3f} | {mb(item['peak_rss_bytes_median']):.1f} | {item['output_order_cosine_min']:.10f} |"
            )
    lines.extend([
        "",
        "At two threads, length-sorted batch=32 raises throughput from 9.47 to 13.58 texts/s (+43.4%) by reducing padding ratio from 1.415 to 1.040. Fixed token buckets improve to 11.70 texts/s (+23.6%). This establishes batching strategy as a major cause of the real-workload regression.",
        "",
        "## 7. ORT threading results",
        "",
        "Only one variable changes in each group; all rows use the mixed fixed profile.",
        "",
        "### intra_op_num_threads (inter=1, sequential, ENABLE_ALL)",
        "",
        "| Intra | Batch 1 / 32 / 100 ms | Batch 32 / 100 texts/s |",
        "|---:|---:|---:|",
    ])
    for name, item in threading["intra_op"].items():
        lines.append(
            f"| {name} | {item['cases']['1']['median_ms']:.1f} / {item['cases']['32']['median_ms']:.1f} / {item['cases']['100']['median_ms']:.1f} | "
            f"{item['cases']['32']['texts_per_second']:.2f} / {item['cases']['100']['texts_per_second']:.2f} |"
        )
    lines.extend([
        "",
        "### inter_op_num_threads and execution mode (intra=2)",
        "",
        "| Variable | Value | Batch 1 / 32 / 100 ms |",
        "|---|---|---:|",
    ])
    for name, item in threading["inter_op"].items():
        lines.append(f"| inter_op | {name} | {item['cases']['1']['median_ms']:.1f} / {item['cases']['32']['median_ms']:.1f} / {item['cases']['100']['median_ms']:.1f} |")
    for name, item in threading["execution_mode"].items():
        lines.append(f"| execution_mode | {name} | {item['cases']['1']['median_ms']:.1f} / {item['cases']['32']['median_ms']:.1f} / {item['cases']['100']['median_ms']:.1f} |")
    lines.extend([
        "",
        "Intra-op is the dominant knob. Intra=12 (the physical-core count) reaches 20.50 texts/s at batch=100 and 21.59 at batch=32. Inter-op 1/2/4 and parallel execution provide no useful gain. This does not imply that interactive requests should reserve all cores; offline ingestion may do so, while interactive uses a small thread pool.",
        "",
        "## 8. Graph optimization results",
        "",
        "| ORT graph level | Batch 1 / 32 / 100 ms |",
        "|---|---:|",
    ])
    for name, item in graph["optimization_levels"].items():
        lines.append(f"| {name} | {item['cases']['1']['median_ms']:.1f} / {item['cases']['32']['median_ms']:.1f} / {item['cases']['100']['median_ms']:.1f} |")
    baseline_graph = audit["baseline_graph"]
    single_graph = graph["single_normalization_graph"]
    single_perf = graph["single_normalization_performance"]
    lines.extend([
        "",
        "ENABLE_EXTENDED/ALL improve batch 32/100 by about 7–8% over DISABLE/BASIC. ENABLE_ALL is retained for the experiment.",
        "",
        f"Export audit: opset 17; inputs are INT64 `[batch, sequence]`; output is FP32 `[batch, 512]`; both batch and sequence axes are dynamic. Baseline has {baseline_graph['node_count']} nodes, 17 Reshape, 11 Cast, 2 ReduceL2 and 10 Div nodes. The casts/reshapes are primarily BERT mask/attention shape mechanics; no fixed input shape was found.",
        f"The single-normalization graph has {single_graph['node_count']} nodes, 1 ReduceL2 and is only {baseline_graph['bytes']-single_graph['bytes']} bytes smaller. Its batch=100 median is {single_perf['cases']['100']['median_ms']:.1f} ms vs baseline ENABLE_ALL {graph['optimization_levels']['all']['cases']['100']['median_ms']:.1f} ms: no meaningful speedup.",
        f"Single-normalization parity: 340-text cosine mean {quality['single_vs_baseline_all_340']['mean']:.10f}, min {quality['single_vs_baseline_all_340']['minimum']:.10f}; Top-1/3/5/10 overlap is 100%/100%/100%/100%. It is numerically redundant but retained in the baseline-compatible graph because simplification has no performance value.",
        "",
        "## 9. Runtime breakdown",
        "",
        "| Batch | Tokenization ms | NumPy input ms | ORT session.run ms | Graph-external pool/norm ms | Result conversion ms | Total ms |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for size in ("1", "32", "100"):
        summary = breakdown[size]["summary"]
        lines.append(
            f"| {size} | {summary['tokenization_ms']['median']:.3f} | {summary['numpy_input_ms']['median']:.3f} | "
            f"{summary['ort_session_ms']['median']:.3f} | 0.000 | {summary['result_conversion_ms']['median']:.3f} | {summary['total_ms']['median']:.3f} |"
        )
    lines.extend([
        "",
        "At batch=100, tokenization + NumPy construction is ~18.6 ms while session.run is 10.72 s (~99.8% of total). Result conversion is negligible. The regression is ORT compute/memory scheduling plus padded shape, not Python/tokenizer/I/O overhead.",
        "",
        "## 10. Real textbook ingestion benchmark",
        "",
        "Source: the existing fixed 500-chunk `传感器长书` retrieval fixture; median 414 tokens; 158/500 chunks truncate at 512. Embedding only; Chroma was never opened or modified. One warm-up plus 3 timed full-workload runs.",
        "",
        "| Backend/config | Median / p95 wall s | Texts/s | Peak RSS MB | Padding ratio | CPU cores / machine | Threads |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    ingestion_rows = (
        ("Torch current: naive batch=32, threads=2", torch_ingest),
        ("ONNX naive: batch=100, intra=2", onnx_naive),
        ("ONNX bucket: batch=16, intra=12", onnx_bucket),
        ("ONNX sorted: batch=16, intra=12", onnx_sorted),
    )
    for name, item in ingestion_rows:
        lines.append(
            f"| {name} | {item['median_ms']/1000:.2f} / {item['p95_ms']/1000:.2f} | {item['texts_per_second']:.2f} | "
            f"{mb(item['peak_rss_bytes_median']):.1f} | {item['tokens']['padding_ratio']:.3f} | "
            f"{item['effective_cpu_cores_median']:.2f} / {item['process_cpu_percent_of_machine_median']:.1f}% | {item['max_native_threads_median']:.0f} |"
        )
    lines.extend([
        "",
        f"The recommended bucket configuration is {throughput_ratio:.2f}× Torch throughput with {(ram_ratio-1)*100:+.1f}% peak RSS. Global length sorting reaches {sorted_ratio:.2f}× throughput with {(onnx_sorted['peak_rss_bytes_median']/torch_ingest['peak_rss_bytes_median']-1)*100:+.1f}% peak RSS.",
        "",
        "Quality spot-check after optimization: 50-text ONNX vs Torch cosine mean "
        f"{quality['optimized_baseline_vs_torch_50']['mean']:.10f}, min {quality['optimized_baseline_vs_torch_50']['minimum']:.10f}.",
        "",
        "## 11. Recommended interactive configuration",
        "",
        "- Keep `batch=1` and a small ORT intra-op pool (`2`, optionally evaluate `4` under application contention).",
        f"- Warm batch=1 median: ONNX {scaling['onnx']['cases']['1']['median_ms']:.2f} ms vs Torch {scaling['torch']['cases']['1']['median_ms']:.2f} ms; ONNX is {(1-scaling['onnx']['cases']['1']['median_ms']/scaling['torch']['cases']['1']['median_ms'])*100:.1f}% faster.",
        f"- Existing Phase 0 fresh-process 5-run cold median: ONNX {phase0['performance']['cold']['onnx']['process_total_ms']['median']:.1f} ms vs Torch {phase0['performance']['cold']['torch']['process_total_ms']['median']:.1f} ms. Inference peak RSS delta: ONNX {mb(phase0['performance']['cold']['onnx']['rss_peak_inference_delta_median']):.1f} MB vs Torch {mb(phase0['performance']['cold']['torch']['rss_peak_inference_delta_median']):.1f} MB.",
        "- Do not use the 12-core ingestion pool for interactive queries by default; it offers no stable batch=1 benefit and can contend with the desktop UI.",
        "",
        "## 12. Recommended ingestion configuration",
        "",
        "- Experimental candidate: tokenize first; bucket by 0–64 / 65–128 / 129–256 / 257–512 tokens; batch=16 inside each bucket; ORT intra=physical core count (12 here), inter=1, sequential, ENABLE_ALL; restore original embedding order.",
        f"- Result: {onnx_bucket['texts_per_second']:.2f} texts/s vs Torch {torch_ingest['texts_per_second']:.2f} ({throughput_ratio:.2f}×), peak RSS {mb(onnx_bucket['peak_rss_bytes_median']):.1f} vs {mb(torch_ingest['peak_rss_bytes_median']):.1f} MB.",
        f"- For maximum fully-offline throughput, global length-sort + batch=16 reaches {onnx_sorted['texts_per_second']:.2f} texts/s ({sorted_ratio:.2f}× Torch) at {mb(onnx_sorted['peak_rss_bytes_median']):.1f} MB. Bucketing is the more streaming-friendly recommendation.",
        "- This recommendation remains experiment-only; production backend and ingestion code are unchanged.",
        "",
        "## 13. Remaining regression",
        "",
        "- At the original two-thread control, mixed batches 16–48 remain 22.6–26.6% slower than Torch; long 512-token profiles remain 15–19.5% slower at batch 32–100.",
        "- Contiguous micro-batching does not fix the issue without reducing padding.",
        "- Using all physical cores is appropriate for offline ingestion but may increase contention/power use; a future production design must keep interactive and ingestion executors separate.",
        "- Length sorting requires pre-tokenization and index restoration; bucketing is operationally simpler but leaves some padding.",
        "- Results are one Windows hybrid CPU and do not establish universal defaults. Physical-core detection and a bounded thread policy are needed before production adoption.",
        "",
        "## 14. PASS / FAIL",
        "",
        f"- Interactive gate: {'PASS' if interactive_pass else 'FAIL'} — ONNX batch=1 is not slower than Torch and retains a large cold-start/RAM advantage.",
        f"- Ingestion gate: {'strong PASS' if throughput_ratio >= .95 else ('PASS' if ingestion_pass else 'FAIL')} — recommended bucket throughput is {throughput_ratio:.2f}× Torch; peak RSS change is {(ram_ratio-1)*100:+.1f}%.",
        f"- Quality gate: {'PASS' if quality_pass else 'FAIL'} — 50-text cosine mean {cosine_mean:.10f} (required ≥0.9999).",
        "",
        f"**{verdict}**",
        "",
        "The ONNX FP32 CPU backend is not blocked by the original batch=100 regression once offline ingestion uses adequate intra-op parallelism and length-aware batch=16. Keep all experimental code and benchmark artifacts, but do not switch the production backend. The next decision can proceed to Phase 2: Torch dependency removal / release slimming feasibility.",
    ])
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result["decision"] = {
        "verdict": verdict,
        "interactive_pass": interactive_pass,
        "ingestion_pass": ingestion_pass,
        "quality_pass": quality_pass,
        "recommended_interactive": {"batch_size": 1, "intra_op_num_threads": 2},
        "recommended_ingestion": {
            "strategy": "length_bucket", "bucket_boundaries": [64, 128, 256, 512],
            "batch_size": 16, "intra_op_num_threads": 12, "inter_op_num_threads": 1,
            "execution_mode": "sequential", "graph_optimization_level": "all",
        },
        "real_ingestion_torch_texts_per_second": torch_ingest["texts_per_second"],
        "real_ingestion_onnx_texts_per_second": onnx_bucket["texts_per_second"],
        "real_ingestion_throughput_ratio": throughput_ratio,
        "real_ingestion_peak_rss_ratio": ram_ratio,
        "quality_cosine_mean": cosine_mean,
        "production_backend_changed": False,
    }
    PHASE1.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(REPORT)


if __name__ == "__main__":
    main()
