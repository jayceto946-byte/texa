# Texa Standard ONNX embedding runtime

Texa Standard 的生产 embedding backend 是 `BAAI/bge-small-zh-v1.5` 的冻结 FP32 ONNX graph。Windows x64 包只携带 `onnxruntime` 和 `tokenizers`，不携带 Torch、SentenceTransformers、Transformers、safetensors 或 CrossEncoder runtime。

## 冻结语义

- model identity：`BAAI/bge-small-zh-v1.5`
- graph version：`onnx-fp32-v1`
- provider：`CPUExecutionProvider`
- tokenizer：BertTokenizerFast 等价 lowercase，右侧 padding/truncation，`max_length=512`
- pooling：CLS
- normalization：保留 parity 已验证 graph 内的双 L2 normalization
- output：FP32、512 维

以上字段也是已有 Chroma index 的兼容合同。Standard 不修改距离度量、collection/metadata schema，不自动 rebuild 或 re-embed。

## 资产与校验

资产位于 `assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1/`，`embedding-runtime.json` 记录模型/graph/tokenizer 版本、Texa 最低版本、期望文件、大小、SHA-256 与 repair source。正常启动执行 manifest/contract/size 快检；repair、首次验证和发布验证执行完整 SHA-256。

Electron 直接从只读 `resources/embedding-runtime` 加载资产，不再在首次启动向每个 user-data 目录复制约 95 MB graph。repair 使用 staging 目录完整下载或复制，校验通过后原子提升为新的 versioned install，再原子更新 `active.json`；不会覆盖正在使用的文件，也不会自动删除旧模型目录。

后端错误合同包含 `code`、`stage`、`recoverable`、`message`、`repair_action`、`diagnostic_id`。正式 code 包括 `MODEL_MISSING`、`MODEL_CORRUPT_OR_INCOMPATIBLE`、`TOKENIZER_MISMATCH`、`ORT_IMPORT_FAILURE`、`UNSUPPORTED_ARCHITECTURE` 与 `ASSET_REPAIR_FAILED`。Electron 只消费这些字段，不解析 Python exception string。

## 运行策略

一个后端进程只有一个 lazy singleton adapter。interactive session 使用 2 个 intra-op threads、batch=1；ingestion session 延迟创建，使用 physical core count、inter-op=1、sequential、ORT_ENABLE_ALL、batch=16，并按 0–64/65–128/129–256/257–512 token 分桶，最后恢复输入顺序。两个 session 独立，避免 ingestion session 的配置污染交互查询。

## 开发与发布

```powershell
# Standard runtime
python -m pip install -r requirements-release.txt

# Torch parity/export/reference（开发环境）
python -m pip install -r requirements-dev.txt
$env:TEXA_EMBEDDING_BACKEND = 'torch'

# Build host / CI
python -m pip install -r requirements-build.txt
.\scripts\build-desktop-backend.ps1
cd desktop
npm.cmd run dist:standard
```

发布前必须运行：

```powershell
python scripts\validate_standard_release.py `
  --root release\win-unpacked `
  --pyinstaller-xref build\pyinstaller\backend_server\xref-backend_server.html
```

完整 ONNX-only release regression 不安装 Torch；ONNX-vs-Torch parity、export 与 benchmark 只在 development/benchmark CI 运行。

## Rollback

保留上一版 Torch installer、迁移前 Git commit/tag 与 development Torch provider。因为 index schema、embedding dimension 和用户数据格式没有变化，严重回归时可直接安装上一版并继续使用已有 indexes，无需 re-embed。第一版迁移只停止使用旧模型资产，不主动递归删除 user-data 中无法明确归属的模型文件。
