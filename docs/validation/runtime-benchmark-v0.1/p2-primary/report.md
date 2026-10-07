# Runtime Benchmark V0.1

Purpose: foundation_screening; status: complete; scope: primary_semantic; planned N=161.
Untouched: True; tuned_on_v0: False; author-frozen gold, human_adjudicated=false, semantic_test_locked=false.
This is internal foundation screening, not held-out accuracy or production acceptance.

| Set / task | S / N | Strict | Exact | Recoverable | F | T | U | Critical |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| primary_semantic / goal_summary | 0/40 | 0.0% | 0.0% | 0.0% | 0 | 0 | 40 | 0 |
| primary_semantic / policy_select | 40/80 | 50.0% | 50.0% | 50.0% | 0 | 40 | 0 | 0 |
| primary_semantic / question_understanding | 0/41 | 0.0% | 0.0% | 0.0% | 0 | 0 | 41 | 0 |
| primary_semantic | 40/161 | 24.8% | 24.8% | 24.8% | 0 | 40 | 81 | 0 |

primary_semantic task macro strict: 16.7%

| primary_semantic / train | 18/77 | 23.4% | 23.4% | 23.4% | 0 | 22 | 37 | 0 |
| primary_semantic / dev | 9/32 | 28.1% | 28.1% | 28.1% | 0 | 7 | 16 | 0 |
| primary_semantic / test | 9/36 | 25.0% | 25.0% | 25.0% | 0 | 7 | 20 | 0 |
| primary_semantic / hidden_test | 4/16 | 25.0% | 25.0% | 25.0% | 0 | 4 | 8 | 0 |
| semantic_all / goal_summary | 0/40 | 0.0% | 0.0% | 0.0% | 0 | 0 | 40 | 0 |
| semantic_all / policy_select | 40/80 | 50.0% | 50.0% | 50.0% | 0 | 40 | 0 | 0 |
| semantic_all / question_understanding | 0/41 | 0.0% | 0.0% | 0.0% | 0 | 0 | 41 | 0 |
| semantic_all | 40/161 | 24.8% | 24.8% | 24.8% | 0 | 40 | 81 | 0 |

semantic_all task macro strict: 16.7%

| semantic_all / train | 18/77 | 23.4% | 23.4% | 23.4% | 0 | 22 | 37 | 0 |
| semantic_all / dev | 9/32 | 28.1% | 28.1% | 28.1% | 0 | 7 | 16 | 0 |
| semantic_all / test | 9/36 | 25.0% | 25.0% | 25.0% | 0 | 7 | 20 | 0 |
| semantic_all / hidden_test | 4/16 | 25.0% | 25.0% | 25.0% | 0 | 4 | 8 | 0 |

S/F/T/U are mutually exclusive; U is unresolved, not proven semantic error. S1 may be successful.

Official severity/taxonomy: {"decision_mismatch": 40, "contract_rejected:Additional properties are not allowed ('$defs', '$schema', 'additionalProperties', 'description', 'properties', 'required', 'type' were unex": 39, "contract_rejected:'暂不修改错题本' is not of type 'object'": 1, "invalid_json:Unterminated string starting at: line 1 column 904 (char 903)": 2, "contract_rejected:{'calculation': True} is not one of ['calculation', 'classification', 'comparison', 'definition', 'derivation', 'examples', 'exercises', 'fe": 1, "invalid_json:Expecting ',' delimiter: line 1 column 842 (char 841)": 1, "contract_rejected:'intent' is a required property": 28, "invalid_json:Expecting value: line 1 column 815 (char 814)": 1, "contract_rejected:invalid_span": 3, "contract_rejected:'classification' is not one of ['application', 'calculation', 'comparison', 'cross_chapter', 'definition', 'derivation', 'factual_recall', '": 1, "invalid_json:Expecting ',' delimiter: line 1 column 892 (char 891)": 1, "invalid_json:Expecting value: line 1 column 924 (char 923)": 1, "invalid_json:Unterminated string starting at: line 1 column 844 (char 843)": 1, "invalid_json:Expecting ',' delimiter: line 1 column 803 (char 802)": 1}

Performance (warmup excluded; request includes prefill):
```json
{
  "successful_latency_n": 161,
  "p50_ms": 1184.0789580001,
  "p95_ms": 4491.013916999691,
  "percentile_method": "nearest-rank ceil(p*n)",
  "tail_sample_insufficient": false,
  "token_rate_n": 161,
  "generated_tokens_per_request_second": 38.14751212294418,
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
