# 通用建库 P0：输入保全与模型身份

2026-10-27，直接在 `Texa_MacOS` 工作区实施。范围是共享摄取/嵌入管线；没有按书名分支，没有重建现有教材或迁移用户数据。

## 已实施

- 正式摄取在打开向量库之前验证 source spans：正文/公式的每个 Unicode 字符保全、位置与原文 hash、块成员、章节归属、chunk 内未归属内容。保留全部 block ID 但替换正文也会失败。
- 表格使用 `canonical-table/v1` 确定性渲染，验证表头、行与可读注释范围；原始 HTML/Markdown 留在 Canonical 并单独绑定 hash。这不是原始 HTML 字节到 Markdown 的一一映射，也不证明 OCR 单元格识别正确。
- 对最终 `retrieval_text`（含书名、章节前缀）使用实际 tokenizer、normalizer、特殊 token 计数。超限来源块生成多个有重叠、精确 Unicode 范围的编码窗口；每个窗口再次计数并验证完整输入覆盖。任何不能满足合同的输入都在发布前失败。
- 窗口只是编码表示。Chroma 每个命中带完整 `raw_content`；生产检索去重后返回完整来源 chunk。长公式仍是完整的来源/证据对象，切开的编码字符串不会作为独立公式展示；这不保证片段向量拥有完整公式语义。
- manifest、版本指纹、lexical 快照、Chroma metadata 绑定实际输入、窗口及模型合同。ONNX 权重/配套资产 SHA-256、有效 tokenizer、pooling、归一化、长度策略均纳入；延迟加载文档 session 前再验证资产与查询 session 相同。
- 同一构建中按实际输入与模型复用向量，缓存上限 4096；章节与 aggregate 复用不承诺跨构建持久缓存。多窗口适度多取并按来源去重，不改变教材范围。
- 保留原 staged candidate、生产混合检索与 Final EvidencePack 发布门槛。模型身份不符时拒绝向量命中，走已有同范围降级；回滚恢复对应模型/输入合同。

## 验证结果

| 验证 | 结果与范围 |
| --- | --- |
| Python 3.10.21，相关后端回归 | [249 passed](backend-tests.log)，6 条现有依赖弃用 warning；覆盖摄取、span、token、模型身份、检索去重、公式/表格、发布/回滚与角色元数据 |
| 桌面运行与语法 | [56 passed + npm run check](desktop-tests.log) |
| 本地既有 351 页来源只读检查 | [1922 个可检索块、2176 编码窗口](corpus-tokenizer-result.json)，所有窗口 ≤512 token；3966 个 verbatim 块与 28 个渲染表格通过范围校验；零静默截断 |
| 真实 ONNX FP32 + Chroma | [合成来源结果](hybrid-result.json)：3 个来源 chunk / 7 个向量；尾部条件召回、完整公式回填、候选失败保留 active、回滚合同恢复均通过 |
| 原生产检索/Final EvidencePack 门槛 | 上述合成材料自动生成 formula/table 各 1 个探针，均通过；list/example 无来源而为 not_applicable。2 个自身生成探针不是独立准确率金标 |
| 真实 macOS Electron 教材 ZIP 导入 | [23 检查、3 图、0 renderer errors](electron-result.json)；1280×820、1024×768、760×820。正常上传、books API/JobManager、ONNX/Chroma、保存的发布 manifest 均为真实链路；其他辅助 API 是 UI 夹具。已逐图检查完成页 |

351 页材料不是截图用户教材。当前固定书名为“本地351页回归材料”，有 254 个原始输入超限；历史调查的 242 使用旧切块/表格投影及不同书名前缀，不能据此计算改善率。窗口覆盖和 span 通过不等于目录语义、OCR 或回答正确。

## 兼容与未覆盖边界

- 保持 index schema 6，新增独立版本合同 `texa.index-source-spans/v1`、`texa.embedding-views/v1`。新输入/模型会产生新 index_version；未改 SQL、依赖或 Canonical schema。旧索引兼容读取、合同状态未知，不因读取自动重算，既有静默截断不会凭代码更新自行修好。
- 查询端原有右截断策略未变。旧直接写 collection 的开发入口先拒绝超限，避免删除后才发现问题；桌面正式导入使用暂存多窗口管线。
- Torch 开发后端增加输入预检与实际权重/配置身份；本环境没有 sentence-transformers，只有提示前缀/小写协议测试，未做真实 Torch 模型运行验收。
- 未调用付费 LLM/OCR，未安装依赖，未发布 Windows 安装包。本轮未完成多信号通用章节恢复、独立跨教材结构/习题金标、持久差量重算；这些仍属研究计划 P1/P2。

## 复现

需要仓库现有 Python 3.10 环境与本地 ONNX 资产，无需下载模型：

```sh
venv310/bin/python docs/validation/index-input-p0-2026-10-27/validate_corpus.py --output /tmp/texa-p0-corpus.json
venv310/bin/python docs/validation/index-input-p0-2026-10-27/validate_hybrid.py --output /tmp/texa-p0-hybrid.json
TEXA_INDEX_QA_WORK=/tmp/texa-p0-electron node scripts/qa-index-input-electron.mjs
```

Electron 脚本需要已有 `frontend/dist`、Electron/Playwright 与本地端口权限；本次 Playwright 来自系统工作运行时，通过 `NODE_PATH` 指定。数据均写临时隔离根，不加载真实工作目录索引；不要把脚本作为用户诊断要求。

截图：[1280](screenshots/1280-real-import-completed.png)、[1024](screenshots/1024-real-import-completed.png)、[760](screenshots/760-real-import-completed.png)。
