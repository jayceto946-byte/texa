# Texa embedding ONNX Runtime Phase 3 report

## 1. Executive Summary

Phase 3 已完成代码迁移、Torch-free Standard 构建、真实 NSIS/ZIP/win-unpacked、现有索引回归、性能门禁、clean install/uninstall、upgrade、offline runtime 与 packaged 故障注入。生产默认已是冻结的 BGE-small ONNX FP32 provider，Standard 产物不含 torch、sentence-transformers、transformers、safetensors。

最终判定为 **PHASE 3 PASS / GO**。固定 GitHub Release tag `embedding-runtime-onnx-fp32-v1` 已发布 manifest 的六个 required assets；逐文件 HEAD/GET、Content-Length、下载字节数和 SHA-256 全部通过。真实 NSIS clean install 中移走 shipped `model.onnx` 后，Electron 正确显示 `MODEL_MISSING` 和“修复模型资源”，从 UI 触发 remote repair，完成临时目录下载、完整哈希、原子安装、provider 自动重试和 Chroma retrieval smoke。

Migration baseline：branch `Refactor-ONNX`（Git ref 不允许冒号，用户给出的 `Refactor:ONNX` 映射为该合法名称），commit `5ea4fb0a3c71fe0b9cbd6ca3034b45e7b6cb3605`。基线依赖、构建脚本、配置、PyInstaller/Electron/warmup/repair 状态与 smoke 保存在 `migration_baseline.json`、`baseline-requirements-release.txt`。

## 2. Production Backend Migration

- `config.get_embeddings()` 默认 `TEXA_EMBEDDING_BACKEND=onnx`。
- one process → one lazy singleton adapter → one reusable interactive ORT session。
- ingestion ORT session lazy singleton，首次 `embed_documents()` 才创建。
- Standard 无 silent Torch fallback；显式 `torch` 缺失时返回 `TORCH_RUNTIME_UNAVAILABLE`。
- Torch reference provider、export、parity 和 benchmark 源码保留在 development/benchmark 边界。

## 3. ONNX Provider Configuration

- model：`BAAI/bge-small-zh-v1.5`
- model revision：`7999e1d3359715c523056ef9478215996d62a620`
- graph：FP32 `onnx-fp32-v1`
- execution provider：`CPUExecutionProvider`
- tokenizer：BertTokenizerFast-equivalent lowercase，right padding/truncation，max_length=512
- pooling：CLS
- normalization：graph 内双 L2 normalization（按已验证兼容 graph 保留）
- output：FP32 / 512 dims

20-text production/source parity：cosine mean `0.9999999999992996`，minimum `0.9999999999988218`，shape `(20, 512)`。

## 4. Interactive/Ingestion Runtime Strategy

Interactive：batch=1、intra-op=2、inter-op=1、sequential、ORT_ENABLE_ALL。Ingestion：batch=16、intra-op=12 physical cores、inter-op=1、sequential、ORT_ENABLE_ALL，token buckets 为 64/128/256/512，结果恢复原 indexing order。

独立 sessions 的并发 packaged test 为 query median/p95 `6.650/13.287ms`，ingestion `26.865 texts/s`。跨 session 全局锁曾导致 p95 约 582ms，已删除；当前简单资源策略不需要复杂 scheduler。

## 5. Requirements Migration

- `requirements-release.txt`：Torch-free Standard runtime；pin `onnxruntime==1.23.2`、`tokenizers==0.22.2`，暂留 `huggingface_hub`。
- `requirements-dev.txt`：release + CPU Torch、SentenceTransformers、Transformers、safetensors、onnx、pytest。
- `requirements-build.txt`：release + PyInstaller/pyinstaller-hooks-contrib。
- Torch-free Phase 2 venv `pip check` 通过；四类 forbidden modules 均不可导入，ORT/tokenizers/Chroma 可导入。

## 6. CrossEncoder Handling

Standard 不安装 CrossEncoder runtime/model，不因 `RERANKER_MODEL_PATH` 引入 Torch。路径为空继续使用 deterministic reranker；Standard 中手工配置路径而 runtime 缺失时返回清晰的 `CROSS_ENCODER_RUNTIME_UNAVAILABLE_IN_STANDARD` 状态并 deterministic fallback，不下载 Torch，不暴露 ImportError traceback。

## 7. PyInstaller Migration

构建脚本已移除 Torch CPU wheel enforcement、SentenceTransformers/Transformers collection、Torch DLL validation 与 ORT exclusion；加入 ORT、tokenizers、versioned embedding assets，并收集 Chroma submodules/data。final xref 同时含 `chromadb.telemetry.product.posthog` 与 `chromadb.api.rust`。

`validate_standard_release.py` fail-closed 检查 forbidden runtime、ORT/tokenizers、Chroma dynamic imports、manifest/完整哈希及 versioned HTTPS repair mapping。最终 `release/win-unpacked` 静态验证 PASS。

## 8. Asset Manifest & Versioning

资产目录：`assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1/`。manifest 明确 asset/model/model revision/graph/dimension/dtype/pooling/normalization/max length/tokenizer/minimum Texa version、每个文件 size/SHA-256 与 repair source。

`model.onnx`：94,847,144 bytes，SHA-256 `8ffd0a0438704bbd55cab10c65d938df62d159879f59907557b3b09dfcc6fe0a`。正常启动执行 contract+size 快检；repair 与 release validator 完整 hash。

## 9. Asset Repair

Bundled/local/remote repair PASS：manifest → staging → copy/download → full SHA-256 → versioned install → atomic directory promote → atomic `active.json`。不会覆盖 active graph，失败 staging 自动清理。offline remote failure 返回 typed `ASSET_REPAIR_FAILED`。

Production source 为固定 GitHub Release `embedding-runtime-onnx-fp32-v1`。六资产 URL、Content-Length 和 SHA-256 见 `remote_asset_verification.json`，全部 PASS。真实 UI repair 将资源安装到 user-data 下的 versioned install，`active.json` 记录 graph/model/hash/source；`.staging` 最终为空。修复后后端自动重启，warmup total `2.987s`，`embedding_ready=true`、`retrieval_ready=true`，导入两章 smoke PDF 后检索返回 2 个命中片段。

## 10. First-run Asset Handling

Standard 将 ONNX 资产作为 Electron `extraResources` 直接安装到只读 app resources；正常运行不再向每个 user-data 复制 95 MB。standard seed 为空且不含旧模型/用户教材，first run 只创建轻量 metadata。旧版约 33 秒补拷路径已从 Standard 启动链移除，最终 warmup 见第 18 节。

## 11. Typed Failure Contract

稳定字段：`code`、`stage`、`recoverable`、`message`、`repair_action`、`diagnostic_id`。最终 frozen injection：

| Case | Expected/actual | Result |
|---|---|---|
| model missing | MODEL_MISSING | PASS |
| same-size corrupt graph | MODEL_CORRUPT_OR_INCOMPATIBLE | PASS |
| tokenizer missing | TOKENIZER_MISMATCH | PASS |
| tokenizer incompatible | TOKENIZER_MISMATCH | PASS |
| ORT pybind/native module missing | ORT_IMPORT_FAILURE | PASS |
| unsupported OS/arch contract | UNSUPPORTED_ARCHITECTURE | PASS (unit contract) |

Electron 映射用户文案、retry/repair/logs，不解析 Python exception string，不显示普通用户 traceback。

## 12. Existing-index Compatibility

维度、distance metric、collection schema、metadata schema 均未修改；无 automatic rebuild/re-embedding。旧 runtime-data upgrade 后 books、49 collections/vector files、history/progress 与 legacy model assets 保留，教材检索直接成功。打开/查询会正常更新 SQLite/HNSW access metadata 与新会话日志，因此不以整个目录 byte-identical 作为兼容条件。

## 13. Retrieval Regression

100 fixed queries / existing `data/vector_db` / 49 collections：

| Metric | Baseline | Final | Gate | Result |
|---|---:|---:|---:|---|
| Recall@3 | 78% | 78% | drop ≤1pp | PASS |
| Recall@5 | 88% | 88% | drop ≤1pp | PASS |
| Recall@10 | 89% | 89% | drop ≤1pp | PASS |
| Top-5 set overlap | — | 98.8% | ≥95% | PASS |
| Top-10 set overlap | — | 96.4% | diagnostic | PASS |

`第八章 热电式传感器` 的 HNSW `Nothing found on disk` 在 baseline 与 ONNX 均复现，归类为既有 segment 数据问题；未重建全库，需独立修复。

## 14. Clean Install

真实 NSIS silent install 到隔离目录 PASS（exit 0，42s）。用独立 `--user-data-dir`、`HF_HUB_OFFLINE=1` 与只含 Windows system directories 的 PATH（无 Python/Node）启动 installed Electron：process/embedding/retrieval ready、warmup=`ready`、embedding dimension=512、generic route=`ordinary_qa`。silent uninstall PASS，应用文件删除，user-data 按预期保留。

生成式正文未调用付费/外部 LLM；只验证 Standard runtime 与 generic routing/retrieval。clean profile 没有预装教材（发布内容许可门禁要求），教材路径由 upgrade/existing-index fixture 验证。

## 15. Upgrade Test

旧 Phase 2 runtime-data 副本包含 books、progress/conversations、49 collections、legacy models。Phase 3 packaged backend offline 启动 PASS，full-ready `3.259s`，existing textbook retrieval PASS；旧模型资产未删除，无 automatic re-embedding。所有 2,691 个旧文件均仍存在；读取/会话追踪产生预期的数据库/metadata 写入。

## 16. Offline Test

Shipped assets 下设置 HF offline 后，packaged startup、512-dim embedding、existing retrieval、500-text ingestion 均不需要下载并通过。追加 clean-profile 离线验证使用 `HF_HUB_OFFLINE=1`、local-only 与不可达 outbound proxy；同一环境访问 GitHub 明确失败，而 Electron 仍在 `2.104s` full-ready，asset source 直接指向 app resources，没有 user-data active override；教材导入和检索返回 2 个片段。远程 repair 在 offline/network failure 时返回 typed `ASSET_REPAIR_FAILED`，不挂死。未调用依赖网络的 LLM/OCR 服务。管理员权限不足使临时 Windows Firewall 规则创建失败，因此本项证据是进程级 air-gap，不冒充物理拔网线测试。

## 17. Corruption/Repair Test

最终 release frozen backend 的 missing/corrupt/tokenizer/ORT failure injection 全部返回预期 contract。local/bundled/remote source repair 的 full hash、atomic install、reinitialize PASS。真实 packaged test 中 shipped graph 被移到可恢复 backup，启动返回 `MODEL_MISSING`；UI repair 下载六文件，完整 hash 验证后原子安装，后端重启与检索成功。测试结束已恢复原 shipped graph，并再次校验原 SHA-256。

## 18. Packaged Startup

最终 `release/win-unpacked` 后端，5 次 fresh processes：

- first health median/p95：`2403.05 / 2465.33ms`
- full retrieval ready median/p95：`2759.01 / 2782.50ms`
- first textbook retrieval median/p95：`428.02 / 526.75ms`
- health/asset/generic/textbook/offline checks：5/5 PASS

低于 5.5s gate，并明显优于旧 Torch full-ready median 10.21s 与 Phase 2 candidate 4.03s。

## 19. Packaged Interactive Benchmark

20 warm batch=1：median `3.734ms`，p95 `4.297ms`，peak RSS p95 `169.17MiB`。median 低于 5ms 调查线且明显快于旧 Torch `6.762ms`。纯 interactive fresh process RSS 为 `158.36MiB`；companion 同时携带 benchmark orchestration 后测得 169.17MiB。

## 20. Packaged Ingestion Benchmark

固定 500-text fixture、推荐 bucket strategy、5 warm runs：median `18.333s`，`27.273 texts/s`，通过 `>=20 texts/s`；亦高于 Torch baseline 10.59 texts/s 的 90% gate。

## 21. Concurrent Ingestion + Query Test

500 texts ingestion + 20 batch=1 queries：interactive median/p95 `6.650/13.287ms`，ingestion `18.612s / 26.865 texts/s`。查询没有被 ingestion 放大到不可用；不增加复杂 scheduler。

## 22. Windows Package Size

| Artifact | Old Torch | Final Phase 3 | Reduction |
|---|---:|---:|---:|
| NSIS | 401.83 MiB | 254.20 MiB | 147.63 MiB / 36.74% |
| ZIP | 506.04 MiB | 324.96 MiB | 181.08 MiB / 35.78% |
| win-unpacked | 1283.06 MiB | 752.56 MiB | 530.50 MiB / 41.35% |
| backend runtime | 963.59 MiB | 342.10 MiB | 621.49 MiB / 64.50% |

installed reduction `>=400 MiB` 且 relative `>=25%`，双 gate PASS。最大文件依次为 Electron executable 195.05MiB、ONNX graph 90.45MiB、Chroma Rust binding 60.46MiB、backend executable 29.63MiB、Chromium dxcompiler 24.70MiB、PyMuPDF 24.46MiB、NumPy/SciPy OpenBLAS 各约 19MiB。下一阶段最值得单独评估的是 SciPy/OpenBLAS 重复与 Chroma Rust binding；本阶段未继续瘦身。

## 23. Forbidden Dependency Scan

最终 win-unpacked 对 package directories、dist-info、wheels、`torch*.dll`、`c10.dll`、CUDA DLL 扫描：

- torch：absent / PASS
- sentence_transformers：absent / PASS
- transformers：absent / PASS
- safetensors：absent / PASS
- onnxruntime/tokenizers：present / PASS
- model/tokenizer full hashes：PASS
- Chroma posthog/rust dynamic imports：PASS

Backend full regression：`472 passed`，仅保留既有 Starlette/httpx2 弃用警告。Electron Node syntax check、frontend TypeScript/Vite production build 与 `git diff --check` 通过。

## 24. Logging / Diagnostics

记录 backend、ORT/model/graph/tokenizer version、verification mode、runtime session config、warmup stage durations、repair result、typed failure code/diagnostic ID。不记录教材正文、用户 query、embedding vectors。`/health` 分开 process_alive、embedding_ready、retrieval_ready 与 structured warmup stages。

## 25. Rollback

迁移 baseline commit 已记录；上一版 Torch installer 保留在 release archive；development Torch provider、export/parity fixtures 保留；index schema 与 user data 未迁移。严重回归时安装上一版即可继续使用 existing indexes，无需 re-embed。旧模型 assets 第一版不自动删除。

## 26. Remaining Risks

Release blocker：无。非阻塞/后续：既有热电式传感器 HNSW segment 损坏；无目录的一页 PDF 会触发既有 `dict.most_common` 解析缺陷；默认 Electron icon 与 package author metadata；SciPy/OpenBLAS/Chroma Rust 体积；OS 级物理断网仍建议在管理员控制的 release VM 复核；真实外部 LLM 正文未在本次无付费授权的 release runtime 测试中调用。

## 27. Final GO / NO-GO

**PHASE 3 PASS**

| Gate | Verdict |
|---|---|
| A. Production default ONNX | PASS |
| B. Torch-free Standard | PASS |
| C. Existing-index migration | PASS |
| D. Asset repair | PASS — fixed release、六资产验证、真实 UI remote repair/retry/retrieval |
| E. Clean Windows release | PASS — install/start/offline runtime/uninstall；external LLM not asserted |

最终验证矩阵：

| Item | Verdict | Evidence |
|---|---|---|
| A clean install | PASS | NSIS install + isolated user-data Electron |
| B old-version upgrade | PASS | existing books/index/legacy models retained |
| C offline startup | PASS | shipped assets + clean profile + blocked outbound proxy/HF offline |
| D model missing | PASS | typed MODEL_MISSING |
| E model corrupt | PASS | typed MODEL_CORRUPT_OR_INCOMPATIBLE |
| F tokenizer mismatch | PASS | typed TOKENIZER_MISMATCH |
| G ORT failure | PASS | typed ORT_IMPORT_FAILURE |
| H existing Chroma | PASS | 49 collections / 100 queries |
| I generic QA | PASS | ordinary_qa routing; external generation not asserted |
| J textbook QA | PASS | packaged retrieval_status=ok, evidence present |
| K ingestion | PASS | 27.273 texts/s |
| L restart | PASS | 5 fresh packaged processes |
| M Electron smoke | PASS | installed Electron owns isolated backend/user-data |
| N packaged size | PASS | 752.56MiB, -530.50MiB / -41.35% |
| O forbidden dependency scan | PASS | zero forbidden runtime hits |

Release readiness：固定资产 Release 与 rollback installer 必须保留；发布 CI 继续执行 Standard validator、六资产远程校验、forbidden dependency scan 和现有索引回归。此次 ONNX migration 到此冻结，不继续扩展性能或检索架构改动。
