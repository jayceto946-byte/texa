# Runtime Benchmark V0.1

Purpose: foundation_screening; status: complete; scope: secondary_semantic; planned N=39.
Untouched: False; tuned_on_v0: False; author-frozen gold, human_adjudicated=false, semantic_test_locked=false.
This is internal foundation screening, not held-out accuracy or production acceptance.

| Set / task | S / N | Strict | Exact | Recoverable | F | T | U | Format / schema | Critical |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| secondary_semantic / question_understanding | 0/19 | 0.0% | 0.0% | 0.0% | 0 | 0 | 19 | 19 / 0 | 0 |
| secondary_semantic / reference_resolve | 0/20 | 0.0% | 0.0% | 0.0% | 0 | 0 | 20 | 20 / 0 | 0 |
| secondary_semantic | 0/39 | 0.0% | 0.0% | 0.0% | 0 | 0 | 39 | 39 / 0 | 0 |
| secondary_semantic / train | 0/21 | 0.0% | 0.0% | 0.0% | 0 | 0 | 21 | 21 / 0 | 0 |
| secondary_semantic / dev | 0/8 | 0.0% | 0.0% | 0.0% | 0 | 0 | 8 | 8 / 0 | 0 |
| secondary_semantic / test | 0/6 | 0.0% | 0.0% | 0.0% | 0 | 0 | 6 | 6 / 0 | 0 |
| secondary_semantic / hidden_test | 0/4 | 0.0% | 0.0% | 0.0% | 0 | 0 | 4 | 4 / 0 | 0 |

secondary_semantic task macro strict: 0.0%; severity: {'S2': 39}

| Set / task | S / N | Strict | Exact | Recoverable | F | T | U | Format / schema | Critical |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| semantic_all / question_understanding | 0/19 | 0.0% | 0.0% | 0.0% | 0 | 0 | 19 | 19 / 0 | 0 |
| semantic_all / reference_resolve | 0/20 | 0.0% | 0.0% | 0.0% | 0 | 0 | 20 | 20 / 0 | 0 |
| semantic_all | 0/39 | 0.0% | 0.0% | 0.0% | 0 | 0 | 39 | 39 / 0 | 0 |
| semantic_all / train | 0/21 | 0.0% | 0.0% | 0.0% | 0 | 0 | 21 | 21 / 0 | 0 |
| semantic_all / dev | 0/8 | 0.0% | 0.0% | 0.0% | 0 | 0 | 8 | 8 / 0 | 0 |
| semantic_all / test | 0/6 | 0.0% | 0.0% | 0.0% | 0 | 0 | 6 | 6 / 0 | 0 |
| semantic_all / hidden_test | 0/4 | 0.0% | 0.0% | 0.0% | 0 | 0 | 4 | 4 / 0 | 0 |

semantic_all task macro strict: 0.0%; severity: {'S2': 39}


S/F/T/U are mutually exclusive; U is unresolved, not proven semantic error. S1 may be successful.

Official severity/taxonomy: {"invalid_json:Expecting value: line 1 column 1 (char 0)": 39}

Performance (warmup excluded; request includes prefill):
```json
{
  "successful_latency_n": 39,
  "p50_ms": 4226.273915999627,
  "p95_ms": 4360.553749998871,
  "percentile_method": "nearest-rank ceil(p*n)",
  "tail_sample_insufficient": false,
  "token_rate_n": 39,
  "generated_tokens_per_request_second": 32.082808051966225,
  "token_rate_reason": null,
  "failed_requests": [],
  "warmup_excluded": true,
  "includes_prefill": true
}
```
Load / peak memory / device: see run.json; RSS and MLX peaks include warmup and must not be added.
Offline single-model measurement does not establish Electron/Chroma/embedding concurrent feasibility.

Training value: insufficient_evidence.
Author-frozen synthetic closed profiles; no primary textbook tool or historical-reference coverage; no training/production permission.
Failures remain analysis-only; no training pairs or automatic training are produced.

Original run load, device and memory measurements:
```json
[
  {
    "run_id": "secondary_semantic-2026-10-06T15:38:25.759597+00:00",
    "model_load_ms": 2440.5737920005777,
    "device": {
      "platform": "macOS-26.5.1-arm64-arm-64bit",
      "machine": "arm64",
      "hardware_model": "Mac17,5",
      "physical_memory_bytes": 8589934592,
      "mlx": {
        "device_name": "Apple A18 Pro",
        "max_recommended_working_set_size": 5726633984,
        "memory_size": 8589934592,
        "architecture": "applegpu_g17p",
        "max_buffer_length": 4294967296,
        "resource_limit": 499000
      }
    },
    "memory": {
      "peak_process_rss": {
        "bytes": 1262911488,
        "api": "resource.getrusage(RUSAGE_SELF).ru_maxrss",
        "scope": "inference process lifetime, includes load and warmup"
      },
      "peak_mlx_allocator": {
        "bytes": 1596019152,
        "reason": null,
        "api": "mlx.core.get_peak_memory",
        "scope": "run includes load and warmup"
      },
      "peaks_are_not_additive": true
    }
  }
]
```
