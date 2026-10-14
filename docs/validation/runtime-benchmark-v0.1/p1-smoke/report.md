# Runtime Benchmark V0.1

Purpose: synthetic_smoke; status: complete; scope: primary_semantic; planned N=0.
Untouched: True; tuned_on_v0: False; author-frozen gold, human_adjudicated=false, semantic_test_locked=false.
This is internal foundation screening, not held-out accuracy or production acceptance.

| Set / task | S / N | Strict | Exact | Recoverable | F | T | U | Critical |
|---|---:|---:|---:|---:|---:|---:|---:|---:|

S/F/T/U are mutually exclusive; U is unresolved, not proven semantic error. S1 may be successful.

Official severity/taxonomy: {}

Performance (warmup excluded; request includes prefill):
```json
{
  "successful_latency_n": 0,
  "p50_ms": null,
  "p95_ms": null,
  "percentile_method": "nearest-rank ceil(p*n)",
  "tail_sample_insufficient": true,
  "token_rate_n": 0,
  "generated_tokens_per_request_second": null,
  "token_rate_reason": "no successful requests with reliable tokens/time",
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
