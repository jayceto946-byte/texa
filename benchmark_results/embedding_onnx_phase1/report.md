# ONNX Runtime FP32 Phase 1 — CPU batch throughput

**PHASE 1 PASS**

Production embedding backend, dependencies, Chroma, BM25, KG and reranker were not changed. All code and models in this report are experiment-only.

## 1. Regression reproduction

- CPU: 12th Gen Intel Core i5-12500H, 12 physical / 16 logical cores; Windows; CPUExecutionProvider; FP32.
- Baseline control: Torch threads=2; ORT intra=2, inter=1, sequential, ORT_ENABLE_ALL.
- Every backend/batch point has one untimed warm-up followed by 10 timed warm runs.
- Batch=100 median: Torch 10313.6 ms vs ONNX 11029.4 ms, ONNX regression 6.9%.
- The earlier 18–22% batch=100 regression did not reproduce at that magnitude. A regression did reproduce, but its largest stable region is batch 16–48 (22.6–26.6%), then narrows to 6.9% at batch=100 and 5.4% at batch=128.

## 2. Batch-size scaling curve

| Batch | Torch median / p95 ms | ONNX median / p95 ms | Torch / ONNX texts/s | ONNX Δ latency | Torch / ONNX CPU cores | Torch / ONNX peak RSS MB | Torch / ONNX threads |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 6.9 / 7.3 | 3.7 / 5.3 | 145.05 / 269.68 | -46.2% | N/A* / N/A* | 393.5 / 150.7 | 53 / 36 |
| 4 | 380.0 / 382.7 | 437.2 / 503.0 | 10.53 / 9.15 | +15.0% | 1.98 / 1.98 | 474.2 / 339.2 | 53 / 36 |
| 8 | 776.6 / 786.3 | 886.8 / 981.7 | 10.30 / 9.02 | +14.2% | 1.98 / 1.98 | 582.2 / 544.1 | 53 / 36 |
| 16 | 1512.4 / 1540.2 | 1854.7 / 1870.8 | 10.58 / 8.63 | +22.6% | 2.00 / 1.97 | 649.2 / 1072.8 | 53 / 36 |
| 24 | 2268.3 / 2329.7 | 2785.9 / 2820.1 | 10.58 / 8.61 | +22.8% | 2.00 / 1.99 | 775.1 / 1209.4 | 53 / 36 |
| 32 | 3004.2 / 3032.4 | 3790.0 / 3882.1 | 10.65 / 8.44 | +26.2% | 1.99 / 1.99 | 890.8 / 1733.4 | 53 / 36 |
| 48 | 4491.3 / 4786.5 | 5685.4 / 5737.5 | 10.69 / 8.44 | +26.6% | 2.00 / 1.98 | 1136.6 / 2309.0 | 53 / 38 |
| 64 | 6739.7 / 6830.0 | 7562.8 / 7730.5 | 9.50 / 8.46 | +12.2% | 1.98 / 1.99 | 1524.3 / 3307.0 | 53 / 37 |
| 96 | 9815.2 / 10267.5 | 11389.8 / 11571.5 | 9.78 / 8.43 | +16.0% | 2.00 / 1.99 | 2016.7 / 4460.6 | 52 / 36 |
| 100 | 10313.6 / 10651.5 | 11029.4 / 12060.2 | 9.70 / 9.07 | +6.9% | 1.98 / 2.00 | 2051.7 / 4673.5 | 50 / 35 |
| 128 | 13059.2 / 13784.3 | 13770.4 / 14067.8 | 9.80 / 9.30 | +5.4% | 1.98 / 2.00 | 2734.5 / 6422.1 | 50 / 35 |

\* Windows process CPU time has ~15.6 ms granularity; CPU utilization for sub-20 ms batch=1 samples is not reliable. Latency, RSS and thread count remain valid.

The throughput curve does not have a simple 'large batch is worse' shape. At two threads ORT loses most at 16–48, while 100–128 recover relative efficiency at the cost of very high peak RSS. Batch=128 is not a reasonable ingestion default.

## 3. Input-length impact

| Profile | Batch | Torch ms | ONNX ms | ONNX Δ | Torch / ONNX texts/s | Max tokens | Padding ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| short | 8 | 79.1 | 76.8 | -2.9% | 101.17 / 104.20 | 50 | 1.136 |
| short | 16 | 146.9 | 141.2 | -3.9% | 108.92 / 113.28 | 50 | 1.136 |
| short | 32 | 295.7 | 277.9 | -6.0% | 108.21 / 115.15 | 50 | 1.136 |
| short | 64 | 555.6 | 539.9 | -2.8% | 115.19 / 118.53 | 50 | 1.136 |
| short | 100 | 897.3 | 896.8 | -0.1% | 111.44 / 111.51 | 50 | 1.136 |
| normal | 8 | 381.6 | 388.3 | +1.7% | 20.96 / 20.61 | 251 | 1.406 |
| normal | 16 | 749.9 | 755.4 | +0.7% | 21.34 / 21.18 | 251 | 1.718 |
| normal | 32 | 1491.9 | 1558.4 | +4.5% | 21.45 / 20.53 | 251 | 1.785 |
| normal | 64 | 3414.3 | 3787.3 | +10.9% | 18.74 / 16.90 | 289 | 1.940 |
| normal | 100 | 5294.3 | 5992.7 | +13.2% | 18.89 / 16.69 | 289 | 2.055 |
| long | 8 | 829.9 | 887.1 | +6.9% | 9.64 / 9.02 | 512 | 1.000 |
| long | 16 | 1663.3 | 1818.3 | +9.3% | 9.62 / 8.80 | 512 | 1.000 |
| long | 32 | 3192.4 | 3751.7 | +17.5% | 10.02 / 8.53 | 512 | 1.000 |
| long | 64 | 6408.9 | 7660.5 | +19.5% | 9.99 / 8.35 | 512 | 1.000 |
| long | 100 | 10032.4 | 11535.5 | +15.0% | 9.97 / 8.67 | 512 | 1.000 |

Short texts have no ONNX regression; ONNX is up to 6% faster and is equal at batch=100. Normal paragraphs regress as batch padding rises. Long 512-token chunks regress even with padding ratio=1.0, proving padding amplifies but does not fully cause the issue; long-sequence ORT compute/memory scheduling is also weaker at two threads.

## 4. Padding analysis

Main mixed profile token statistics (identical for Torch and ONNX):

| Batch | Min / median / max tokens | Real tokens | Padded tokens | Padding ratio | Waste fraction |
|---:|---:|---:|---:|---:|---:|
| 1 | 6 / 6.0 / 6 | 6 | 6 | 1.000 | 0.0% |
| 4 | 121 / 331.5 / 512 | 1296 | 2048 | 1.580 | 36.7% |
| 8 | 121 / 414.0 / 512 | 2836 | 4096 | 1.444 | 30.8% |
| 16 | 35 / 368.0 / 512 | 5180 | 8192 | 1.581 | 36.8% |
| 24 | 35 / 387.0 / 512 | 8149 | 12288 | 1.508 | 33.7% |
| 32 | 35 / 363.5 / 512 | 10733 | 16384 | 1.527 | 34.5% |
| 48 | 35 / 386.0 / 512 | 16675 | 24576 | 1.474 | 32.1% |
| 64 | 35 / 403.0 / 512 | 22599 | 32768 | 1.450 | 31.0% |
| 96 | 35 / 392.5 / 512 | 33482 | 49152 | 1.468 | 31.9% |
| 100 | 35 / 390.5 / 512 | 34711 | 51200 | 1.475 | 32.2% |
| 128 | 35 / 394.0 / 512 | 45318 | 65536 | 1.446 | 30.9% |

Batch=100 contains 34,711 real tokens but executes 51,200 padded tokens (ratio 1.475; 32.2% of executed token slots are padding). A few 512-token chunks force the complete naive batch to sequence length 512. This part is a batching-strategy problem, not a fixed-shape export problem.

## 5. Micro-batching results

The same 100 texts were kept in the same order.

| Plan | Median / p95 ms | Texts/s | Padding ratio | Peak RSS MB |
|---|---:|---:|---:|---:|
| 100 | 11756.0 / 12213.6 | 8.51 | 1.475 | 4672.6 |
| 64+36 | 11758.2 / 12030.7 | 8.50 | 1.475 | 4817.0 |
| 50+50 | 11711.4 / 12153.5 | 8.54 | 1.475 | 4819.1 |
| 32+32+32+4 | 11647.2 / 11722.1 | 8.59 | 1.465 | 4820.2 |
| 25x4 | 11516.4 / 11765.2 | 8.68 | 1.475 | 4822.6 |
| 16x6+4 | 11640.1 / 16597.5 | 8.59 | 1.465 | 4822.6 |
| 8x12+4 | 11189.6 / 11335.7 | 8.94 | 1.452 | 4824.1 |

Pure contiguous micro-batching is insufficient. The best plan, 8×12+4, is only 4.8% faster than ONNX batch=100 and remains about 8.5% slower than Torch batch=100 because it barely changes padding.

## 6. Length-aware batching results

500 fixed real textbook chunks; embeddings are written back to original indices.

| Batch | Strategy | Median ms | Texts/s | Padding ratio | Peak RSS MB | Output-order cosine min |
|---:|---|---:|---:|---:|---:|---:|
| 16 | naive | 58671.0 | 8.52 | 1.415 | 959.4 | 1.0000000000 |
| 16 | length_sorted | 39559.6 | 12.64 | 1.020 | 1125.2 | 1.0000000000 |
| 16 | length_bucket | 42535.4 | 11.75 | 1.164 | 1132.8 | 1.0000000000 |
| 32 | naive | 52783.7 | 9.47 | 1.415 | 1911.6 | 1.0000000000 |
| 32 | length_sorted | 36809.1 | 13.58 | 1.040 | 2035.0 | 1.0000000000 |
| 32 | length_bucket | 42737.9 | 11.70 | 1.168 | 2048.2 | 1.0000000000 |
| 64 | naive | 53558.7 | 9.34 | 1.415 | 3406.9 | 1.0000000000 |
| 64 | length_sorted | 39094.0 | 12.79 | 1.081 | 3896.8 | 1.0000000000 |
| 64 | length_bucket | 43441.8 | 11.51 | 1.168 | 3912.4 | 1.0000000000 |

At two threads, length-sorted batch=32 raises throughput from 9.47 to 13.58 texts/s (+43.4%) by reducing padding ratio from 1.415 to 1.040. Fixed token buckets improve to 11.70 texts/s (+23.6%). This establishes batching strategy as a major cause of the real-workload regression.

## 7. ORT threading results

Only one variable changes in each group; all rows use the mixed fixed profile.

### intra_op_num_threads (inter=1, sequential, ENABLE_ALL)

| Intra | Batch 1 / 32 / 100 ms | Batch 32 / 100 texts/s |
|---:|---:|---:|
| 1 | 5.5 / 7208.6 / 22418.9 | 4.44 / 4.46 |
| 2 | 3.3 / 3371.5 / 10644.0 | 9.49 / 9.40 |
| 4 | 2.9 / 1899.9 / 6123.1 | 16.84 / 16.33 |
| 8 | 3.5 / 1856.0 / 5447.7 | 17.24 / 18.36 |
| 12 | 3.3 / 1482.3 / 4878.0 | 21.59 / 20.50 |

### inter_op_num_threads and execution mode (intra=2)

| Variable | Value | Batch 1 / 32 / 100 ms |
|---|---|---:|
| inter_op | 1 | 3.3 / 3399.6 / 10690.3 |
| inter_op | 2 | 3.4 / 3380.0 / 10736.4 |
| inter_op | 4 | 3.2 / 3385.9 / 10768.6 |
| execution_mode | sequential | 3.3 / 3387.1 / 10775.7 |
| execution_mode | parallel | 2.8 / 3389.1 / 10803.8 |

Intra-op is the dominant knob. Intra=12 (the physical-core count) reaches 20.50 texts/s at batch=100 and 21.59 at batch=32. Inter-op 1/2/4 and parallel execution provide no useful gain. This does not imply that interactive requests should reserve all cores; offline ingestion may do so, while interactive uses a small thread pool.

## 8. Graph optimization results

| ORT graph level | Batch 1 / 32 / 100 ms |
|---|---:|
| disable | 3.1 / 3684.7 / 11670.3 |
| basic | 2.9 / 3685.4 / 11655.1 |
| extended | 3.2 / 3401.9 / 10701.8 |
| all | 3.2 / 3371.3 / 10734.9 |

ENABLE_EXTENDED/ALL improve batch 32/100 by about 7–8% over DISABLE/BASIC. ENABLE_ALL is retained for the experiment.

Export audit: opset 17; inputs are INT64 `[batch, sequence]`; output is FP32 `[batch, 512]`; both batch and sequence axes are dynamic. Baseline has 380 nodes, 17 Reshape, 11 Cast, 2 ReduceL2 and 10 Div nodes. The casts/reshapes are primarily BERT mask/attention shape mechanics; no fixed input shape was found.
The single-normalization graph has 374 nodes, 1 ReduceL2 and is only 438 bytes smaller. Its batch=100 median is 10713.3 ms vs baseline ENABLE_ALL 10734.9 ms: no meaningful speedup.
Single-normalization parity: 340-text cosine mean 1.0000000000, min 0.9999998808; Top-1/3/5/10 overlap is 100%/100%/100%/100%. It is numerically redundant but retained in the baseline-compatible graph because simplification has no performance value.

## 9. Runtime breakdown

| Batch | Tokenization ms | NumPy input ms | ORT session.run ms | Graph-external pool/norm ms | Result conversion ms | Total ms |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.031 | 0.009 | 2.398 | 0.000 | 0.003 | 2.443 |
| 32 | 5.253 | 1.785 | 3378.231 | 0.000 | 0.009 | 3385.393 |
| 100 | 12.959 | 5.653 | 10722.289 | 0.000 | 0.010 | 10741.690 |

At batch=100, tokenization + NumPy construction is ~18.6 ms while session.run is 10.72 s (~99.8% of total). Result conversion is negligible. The regression is ORT compute/memory scheduling plus padded shape, not Python/tokenizer/I/O overhead.

## 10. Real textbook ingestion benchmark

Source: the existing fixed 500-chunk `传感器长书` retrieval fixture; median 414 tokens; 158/500 chunks truncate at 512. Embedding only; Chroma was never opened or modified. One warm-up plus 3 timed full-workload runs.

| Backend/config | Median / p95 wall s | Texts/s | Peak RSS MB | Padding ratio | CPU cores / machine | Threads |
|---|---:|---:|---:|---:|---:|---:|
| Torch current: naive batch=32, threads=2 | 47.01 / 47.06 | 10.63 | 1022.6 | 1.415 | 2.00 / 12.5% | 50 |
| ONNX naive: batch=100, intra=2 | 53.27 / 53.28 | 9.39 | 4665.8 | 1.415 | 2.00 / 12.5% | 35 |
| ONNX bucket: batch=16, intra=12 | 18.20 / 18.28 | 27.47 | 1011.1 | 1.164 | 11.99 / 74.9% | 48 |
| ONNX sorted: batch=16, intra=12 | 15.39 / 15.62 | 32.49 | 1057.6 | 1.020 | 11.98 / 74.9% | 48 |

The recommended bucket configuration is 2.58× Torch throughput with -1.1% peak RSS. Global length sorting reaches 3.06× throughput with +3.4% peak RSS.

Quality spot-check after optimization: 50-text ONNX vs Torch cosine mean 1.0000000000, min 0.9999998808.

## 11. Recommended interactive configuration

- Keep `batch=1` and a small ORT intra-op pool (`2`, optionally evaluate `4` under application contention).
- Warm batch=1 median: ONNX 3.71 ms vs Torch 6.89 ms; ONNX is 46.2% faster.
- Existing Phase 0 fresh-process 5-run cold median: ONNX 599.8 ms vs Torch 8446.0 ms. Inference peak RSS delta: ONNX 160.9 MB vs Torch 366.6 MB.
- Do not use the 12-core ingestion pool for interactive queries by default; it offers no stable batch=1 benefit and can contend with the desktop UI.

## 12. Recommended ingestion configuration

- Experimental candidate: tokenize first; bucket by 0–64 / 65–128 / 129–256 / 257–512 tokens; batch=16 inside each bucket; ORT intra=physical core count (12 here), inter=1, sequential, ENABLE_ALL; restore original embedding order.
- Result: 27.47 texts/s vs Torch 10.63 (2.58×), peak RSS 1011.1 vs 1022.6 MB.
- For maximum fully-offline throughput, global length-sort + batch=16 reaches 32.49 texts/s (3.06× Torch) at 1057.6 MB. Bucketing is the more streaming-friendly recommendation.
- This recommendation remains experiment-only; production backend and ingestion code are unchanged.

## 13. Remaining regression

- At the original two-thread control, mixed batches 16–48 remain 22.6–26.6% slower than Torch; long 512-token profiles remain 15–19.5% slower at batch 32–100.
- Contiguous micro-batching does not fix the issue without reducing padding.
- Using all physical cores is appropriate for offline ingestion but may increase contention/power use; a future production design must keep interactive and ingestion executors separate.
- Length sorting requires pre-tokenization and index restoration; bucketing is operationally simpler but leaves some padding.
- Results are one Windows hybrid CPU and do not establish universal defaults. Physical-core detection and a bounded thread policy are needed before production adoption.

## 14. PASS / FAIL

- Interactive gate: PASS — ONNX batch=1 is not slower than Torch and retains a large cold-start/RAM advantage.
- Ingestion gate: strong PASS — recommended bucket throughput is 2.58× Torch; peak RSS change is -1.1%.
- Quality gate: PASS — 50-text cosine mean 1.0000000000 (required ≥0.9999).

**PHASE 1 PASS**

The ONNX FP32 CPU backend is not blocked by the original batch=100 regression once offline ingestion uses adequate intra-op parallelism and length-aware batch=16. Keep all experimental code and benchmark artifacts, but do not switch the production backend. The next decision can proceed to Phase 2: Torch dependency removal / release slimming feasibility.
