# Runtime Benchmark V0.1

Purpose: foundation_screening; status: complete; scope: semantic_all; planned N=200.
Untouched: True; tuned_on_v0: False; author-frozen gold, human_adjudicated=false, semantic_test_locked=false.
This is internal foundation screening, not held-out accuracy or production acceptance.

| Set / task | S / N | Strict | Exact | Recoverable | F | T | U | Format / schema | Critical |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| primary_semantic / goal_summary | 0/40 | 0.0% | 0.0% | 0.0% | 0 | 0 | 40 | 0 / 40 | 0 |
| primary_semantic / policy_select | 40/80 | 50.0% | 50.0% | 50.0% | 0 | 40 | 0 | 0 / 0 | 0 |
| primary_semantic / question_understanding | 0/41 | 0.0% | 0.0% | 0.0% | 0 | 0 | 41 | 8 / 30 | 0 |
| primary_semantic | 40/161 | 24.8% | 24.8% | 24.8% | 0 | 40 | 81 | 8 / 70 | 0 |
| primary_semantic / train | 18/77 | 23.4% | 23.4% | 23.4% | 0 | 22 | 37 | 1 / 36 | 0 |
| primary_semantic / dev | 9/32 | 28.1% | 28.1% | 28.1% | 0 | 7 | 16 | 2 / 12 | 0 |
| primary_semantic / test | 9/36 | 25.0% | 25.0% | 25.0% | 0 | 7 | 20 | 5 / 15 | 0 |
| primary_semantic / hidden_test | 4/16 | 25.0% | 25.0% | 25.0% | 0 | 4 | 8 | 0 / 7 | 0 |

primary_semantic task macro strict: 16.7%; severity: {'S2': 121, 'S0': 40}

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
| semantic_all / goal_summary | 0/40 | 0.0% | 0.0% | 0.0% | 0 | 0 | 40 | 0 / 40 | 0 |
| semantic_all / policy_select | 40/80 | 50.0% | 50.0% | 50.0% | 0 | 40 | 0 | 0 / 0 | 0 |
| semantic_all / question_understanding | 0/60 | 0.0% | 0.0% | 0.0% | 0 | 0 | 60 | 12 / 43 | 0 |
| semantic_all / reference_resolve | 0/20 | 0.0% | 0.0% | 0.0% | 0 | 0 | 20 | 0 / 20 | 0 |
| semantic_all | 40/200 | 20.0% | 20.0% | 20.0% | 0 | 40 | 120 | 12 / 103 | 0 |
| semantic_all / train | 18/98 | 18.4% | 18.4% | 18.4% | 0 | 22 | 58 | 3 / 53 | 0 |
| semantic_all / dev | 9/40 | 22.5% | 22.5% | 22.5% | 0 | 7 | 24 | 2 / 20 | 0 |
| semantic_all / test | 9/42 | 21.4% | 21.4% | 21.4% | 0 | 7 | 26 | 5 / 21 | 0 |
| semantic_all / hidden_test | 4/20 | 20.0% | 20.0% | 20.0% | 0 | 4 | 12 | 2 / 9 | 0 |

semantic_all task macro strict: 12.5%; severity: {'S2': 160, 'S0': 40}


S/F/T/U are mutually exclusive; U is unresolved, not proven semantic error. S1 may be successful.

Official severity/taxonomy: {"decision_mismatch": 40, "contract_rejected:Additional properties are not allowed ('$defs', '$schema', 'additionalProperties', 'description', 'properties', 'required', 'type' were unex": 39, "contract_rejected:'暂不修改错题本' is not of type 'object'": 1, "invalid_json:Unterminated string starting at: line 1 column 904 (char 903)": 2, "contract_rejected:{'calculation': True} is not one of ['calculation', 'classification', 'comparison', 'definition', 'derivation', 'examples', 'exercises', 'fe": 1, "contract_rejected:'intent' is a required property": 41, "invalid_json:Expecting ',' delimiter: line 1 column 842 (char 841)": 1, "invalid_json:Expecting value: line 1 column 815 (char 814)": 1, "contract_rejected:invalid_span": 5, "contract_rejected:'classification' is not one of ['application', 'calculation', 'comparison', 'cross_chapter', 'definition', 'derivation', 'factual_recall', '": 1, "invalid_json:Expecting ',' delimiter: line 1 column 892 (char 891)": 1, "invalid_json:Expecting value: line 1 column 924 (char 923)": 1, "invalid_json:Unterminated string starting at: line 1 column 844 (char 843)": 1, "invalid_json:Expecting ',' delimiter: line 1 column 242 (char 241)": 1, "invalid_json:Unterminated string starting at: line 1 column 947 (char 946)": 1, "invalid_json:Expecting ',' delimiter: line 1 column 436 (char 435)": 1, "invalid_json:Unterminated string starting at: line 1 column 878 (char 877)": 1, "invalid_json:Expecting ',' delimiter: line 1 column 803 (char 802)": 1, "contract_rejected:{'operation': 'clarify', 'value': '压阻效应'} is not valid under any of the given schemas": 2, "contract_rejected:{'operation': 'clarify', 'value': '压电效应'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '比值判别法'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '根值判别法'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '热电偶'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '热电阻'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '霍尔效应'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '行列式'} is not valid under any of the given schemas": 2, "contract_rejected:{'operation': 'clarify', 'value': '开环系统'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '闭环系统'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '拉普拉斯变换'} is not valid under any of the given schemas": 2, "contract_rejected:{'operation': 'clarify', 'value': '积分中值定理'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '中值定理'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '量化误差'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '采样误差'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '条件概率'} is not valid under any of the given schemas": 1, "contract_rejected:{'operation': 'clarify', 'value': '全概率'} is not valid under any of the given schemas": 1}

Performance (warmup excluded; request includes prefill):
```json
{
  "successful_latency_n": 200,
  "p50_ms": 971.5510839996568,
  "p95_ms": 7871.458042000086,
  "percentile_method": "nearest-rank ceil(p*n)",
  "tail_sample_insufficient": false,
  "token_rate_n": 200,
  "generated_tokens_per_request_second": 37.30224032842037,
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
    "run_id": "p2-primary-2026-10-06T13:47:07.525412+00:00",
    "model_load_ms": 1318.9040829993246,
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
        "bytes": 831815680,
        "api": "resource.getrusage(RUSAGE_SELF).ru_maxrss",
        "scope": "inference process lifetime, includes load and warmup"
      },
      "peak_mlx_allocator": {
        "bytes": 1160565198,
        "reason": null,
        "api": "mlx.core.get_peak_memory",
        "scope": "run includes load and warmup"
      },
      "peaks_are_not_additive": true
    }
  },
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
