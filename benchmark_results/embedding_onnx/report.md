# Texa embedding ONNX Runtime FP32 feasibility report

Decision: **NO-GO** — The ONNX embedding path is numerically/retrieval compatible and greatly improves cold start/RAM, but batch-100 warm inference regresses by more than the allowed 10%. More importantly, the required Torch fallback and optional CrossEncoder reranker retain SentenceTransformers, Transformers, Torch, and the safetensors model. No dependency or old model asset can be removed, while ONNX adds about 90.5 MB. Performance and distribution gates therefore fail. Keep PyTorch as the production default.

## 1. Current embedding baseline

- Model: `BAAI/bge-small-zh-v1.5`, local snapshot, CPU, float32, 512 dimensions.
- Tokenizer: snapshot `BertTokenizerFast`; 512 tokens; right padding/truncation; SentenceTransformers adds lowercase normalization.
- Graph: BERT -> CLS pooling -> L2 Normalize; project encode also requests normalization; no query/document prompt.
- Production provider remains the lazy singleton in `config.py`; FastAPI startup normally triggers it in background warmup.

## 2. ONNX implementation

- Isolated experiment-only provider; production default and existing indexes are unchanged.
- ONNX graph includes the BERT backbone, CLS pooling, and both L2 normalization passes.
- Runtime uses only ONNX Runtime CPUExecutionProvider, raw tokenizers runtime, NumPy, FP32, and two intra-op threads.
- Tokenization exact matches: 340/340.

## 3. Parity test

- Dataset: 340 fixed texts; fixture SHA-256 `7c221b3d9497ba8b63c97e2cae9f294ef999cbd02286c4157617dd153fa758d4`.
- Cosine mean/median/p95/min: 1.0000000000 / 1.0000000000 / 1.0000001192 / 0.9999998808.
- Element max/mean absolute error: 3.576e-07 / 4.055e-08.

## 4. Retrieval quality

- Fixed corpus/query counts: 500 / 100; 40 human-curated queries.
- Top-1/3/5/10 set overlap: 100.00% / 100.00% / 100.00% / 100.00%.
- Torch Recall@1/3/5, MRR@10: 80.00% / 92.50% / 95.00% / 0.8646.
- ONNX Recall@1/3/5, MRR@10: 80.00% / 92.50% / 95.00% / 0.8646.
- ONNX minus Torch: Recall@5 +0.00 pp; MRR +0.000% relative.
- With only 40 human queries, this detects large/systematic regressions but cannot establish statistical equivalence.

## 5. Cold-start benchmark

- Fresh-process runs per backend: 5.
- Torch process total median/p95: 8446.0 / 8981.2 ms.
- ONNX process total median/p95: 599.8 / 838.8 ms.
- Times include interpreter startup, runtime import, tokenizer/model load, and first embedding. Local model files are fixed; OS disk cache was not forcibly flushed.

## 6. Warm inference benchmark

- Input profile: batch 1 is a short query; batch 8/32/100 use a fixed mix of 75% formula/medium chunks (at most 900 characters) and 25% normal 50-300-character paragraphs. Both backends receive identical texts.

| batch | Torch median / p95 | ONNX median / p95 | Torch texts/s | ONNX texts/s |
|---:|---:|---:|---:|---:|
| 1 | 7.6 / 9.6 ms | 2.3 / 2.9 ms | 131.1 | 439.7 |
| 8 | 870.5 / 880.1 ms | 871.5 / 882.7 ms | 9.2 | 9.2 |
| 32 | 3324.9 / 3347.2 ms | 3309.8 / 3489.8 ms | 9.6 | 9.7 |
| 100 | 8431.1 / 8535.2 ms | 10248.0 / 10414.4 ms | 11.9 | 9.8 |

## 7. RAM benchmark

- Torch median model-load RSS delta / inference peak delta: 313.1 / 366.6 MB.
- ONNX median model-load RSS delta / inference peak delta: 120.4 / 160.9 MB.

## 8. Distribution size

- Gross Torch embedding stack: 846.7 MB.
- Gross ONNX embedding stack: 187.0 MB.
- Future candidate reduction only if fallback, CrossEncoder, and all other Torch consumers are removed/replaced: 695.3 MB.
- Real removable dependency size while preserving the current optional reranker: 0.0 MB.
- Because the Torch fallback must remain, its safetensors asset cannot be removed; adding ONNX grows the release by about 90.5 MB.
- These are installed-distribution bytes, not only wheel/model sizes; PyInstaller collection still requires a separate release build measurement before migration.

## 9. Removable dependencies

- Completely delete torch: **NO** — production fallback, optional CrossEncoder, legacy tooling, and release build checks still use it.
- Completely delete sentence-transformers: **NO** — production fallback, optional CrossEncoder, and legacy tooling still use it.
- Completely delete transformers: **NO** — production fallback imports it and SentenceTransformers/CrossEncoder retains it transitively.

## 10. Problems found

- Raw `tokenizer.json` alone was not equivalent: SentenceTransformers prepends lowercase normalization from `sentence_bert_config.json`. The provider now reproduces it and the fixture verifies every token sequence.
- Some source chunks split headings from following content; one human label was corrected during review. The final fixture targets text that actually supports each query.

## 11. Risks

- Existing Chroma vectors remain numerically compatible in this experiment, but no production index was changed or rebuilt.
- The 500-chunk isolated dense benchmark does not exercise BM25, KG, reranking, Chroma HNSW approximation, or full production fan-out; those variables were intentionally held out.
- Windows results on this machine do not generalize to all CPUs or packaged Electron/PyInstaller cold starts.

## 12. GO / NO-GO

**NO-GO**

The ONNX embedding path is numerically/retrieval compatible and greatly improves cold start/RAM, but batch-100 warm inference regresses by more than the allowed 10%. More importantly, the required Torch fallback and optional CrossEncoder reranker retain SentenceTransformers, Transformers, Torch, and the safetensors model. No dependency or old model asset can be removed, while ONNX adds about 90.5 MB. Performance and distribution gates therefore fail. Keep PyTorch as the production default.

The experimental ONNX provider and benchmark should be retained. The old backend has not been removed or changed.
