# Runtime Benchmark V0.1

Purpose: foundation_screening; status: complete; scope: secondary_semantic; planned N=39.
Untouched: True; tuned_on_v0: False; author-frozen gold, human_adjudicated=false, semantic_test_locked=false.
This is internal foundation screening, not held-out accuracy or production acceptance.

| Set / task | S / N | Strict | Exact | Recoverable | F | T | U | Format / schema | Critical |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| secondary_semantic / question_understanding | 0/19 | 0.0% | 0.0% | 0.0% | 0 | 0 | 19 | 4 / 13 | 0 |
| secondary_semantic / reference_resolve | 0/20 | 0.0% | 0.0% | 0.0% | 0 | 0 | 20 | 0 / 20 | 0 |
| secondary_semantic | 0/39 | 0.0% | 0.0% | 0.0% | 0 | 0 | 39 | 4 / 33 | 0 |
| secondary_semantic / train | 0/21 | 0.0% | 0.0% | 0.0% | 0 | 0 | 21 | 2 / 17 | 0 |
| secondary_semantic / dev | 0/8 | 0.0% | 0.0% | 0.0% | 0 | 0 | 8 | 0 / 8 | 0 |
| secondary_semantic / test | 0/6 | 0.0% | 0.0% | 0.0% | 0 | 0 | 6 | 0 / 6 | 0 |
| secondary_semantic / hidden_test | 0/4 | 0.0% | 0.0% | 0.0% | 0 | 0 | 4 | 2 / 2 | 0 |

secondary_semantic task macro strict: 0.0%; severity: {'S2': 39}

| Set / task | S / N | Strict | Exact | Recoverable | F | T | U | Format / schema | Critical |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| semantic_all / question_understanding | 0/19 | 0.0% | 0.0% | 0.0% | 0 | 0 | 19 | 4 / 13 | 0 |
| semantic_all / reference_resolve | 0/20 | 0.0% | 0.0% | 0.0% | 0 | 0 | 20 | 0 / 20 | 0 |
| semantic_all | 0/39 | 0.0% | 0.0% | 0.0% | 0 | 0 | 39 | 4 / 33 | 0 |
| semantic_all / train | 0/21 | 0.0% | 0.0% | 0.0% | 0 | 0 | 21 | 2 / 17 | 0 |
| semantic_all / dev | 0/8 | 0.0% | 0.0% | 0.0% | 0 | 0 | 8 | 0 / 8 | 0 |
| semantic_all / test | 0/6 | 0.0% | 0.0% | 0.0% | 0 | 0 | 6 | 0 / 6 | 0 |
| semantic_all / hidden_test | 0/4 | 0.0% | 0.0% | 0.0% | 0 | 0 | 4 | 2 / 2 | 0 |

semantic_all task macro strict: 0.0%; severity: {'S2': 39}


S/F/T/U are mutually exclusive; U is unresolved, not proven semantic error. S1 may be successful.

Official severity/taxonomy: {"contract_rejected:'intent' is a required property": 13, "contract_rejected:invalid_span": 2, "invalid_json:Expecting ',' delimiter: line 1 column 242 (char 241)": 1, "invalid_json:Unterminated string starting at: line 1 column 947 (char 946)": 1, "invalid_json:Expecting ',' delimiter: line 1 column 436 (char 435)": 1, "invalid_json:Unterminated string starting at: line 1 column 878 (char 877)": 1, "contract_rejected:{'operation': 'clarify', 'value': '压阻效应'} is not valid under any of the given schemas": 2, "contract_rejected:{'operation': 'clarify', 'value': '压电效应'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '比值判别法'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '根值判别法'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '热电偶'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '热电阻'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '霍尔效应'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '行列式'} is not valid under any of the given schemas": 2, "contract_rejected:{'operation': 'clarify', 'value': '开环系统'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '闭环系统'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '拉普拉斯变换'} is not valid under any of the given schemas": 2, "contract_rejected:{'operation': 'clarify', 'value': '积分中值定理'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '中值定理'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '量化误差'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '采样误差'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '条件概率'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '全概率'} is not valid under any of the given schemas": 1}

Performance (warmup excluded; request includes prefill):
```json
{
  "successful_latency_n": 39,
  "p50_ms": 971.5510839996568,
  "p95_ms": 8155.76583300026,
  "percentile_method": "nearest-rank ceil(p*n)",
  "tail_sample_insufficient": false,
  "token_rate_n": 39,
  "generated_tokens_per_request_second": 33.22246353422445,
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
    "run_id": "p3-secondary-2026-10-06T13:53:03.780778+00:00",
    "model_load_ms": 1526.9004169995242,
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
        "bytes": 850771968,
        "api": "resource.getrusage(RUSAGE_SELF).ru_maxrss",
        "scope": "inference process lifetime, includes load and warmup"
      },
      "peak_mlx_allocator": {
        "bytes": 1163384782,
        "reason": null,
        "api": "mlx.core.get_peak_memory",
        "scope": "run includes load and warmup"
      },
      "peaks_are_not_additive": true
    }
  }
]
```
