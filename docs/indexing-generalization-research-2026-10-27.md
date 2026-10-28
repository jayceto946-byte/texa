# Texa 通用教材建库调查

日期：2026-10-27；实施状态更新于 2026-10-28。P0 输入保全与模型身份、P1 共享目录恢复及示例校准已实施；独立整书金标和 P2 持久差量更新待继续。**不代表任意教材准确率承诺**。见 [P0 验收](validation/index-input-p0-2026-10-27/README.md)与 [P1 实现及验证边界](validation/outline-p1-2026-10-28/README.md)。

目标是新教材通过统一流程完成导入、结构恢复、检索及题目来源准备；不以用户提供日志、反复 OCR/全量重建或添加按书名分支作为常规流程。格式 adapter 只处理 PDF、Word、MinerU 等来源协议，教材差异由共享结构恢复处理。

## 1. 结论

调查时反复修教材，原因不止标题识别。**来源保全、结构推断、学习单元、检索切块、嵌入输入与验收之间缺少共同依据。** P0 已补字符/span 与嵌入输入合同；P1 现在将目录/正文有序匹配、书签、编号与可用字体信号收敛为共享结构，并提供少量示例校准。独立整书语义验收仍需积累，不能由自身生成探针代替。

本轮 v5 修复了正文残句变标题后不进索引、中文层级、复合习题标题及 ZIP 习题入口。它没有解决通用建库的全部问题。继续追加标题关键词、换向量库或只换一个 OCR 模型，都不足以解决下面已经复现的跨教材缺陷。

保留现有 Canonical、混合检索、Final EvidencePack、暂存发布与回滚框架。P0 保证完整输入进入有界编码表示；P1 让章节视图、检索及抽题共用结构恢复结果。接下来补独立整书评测并做持久增量重算。无需推翻 FastAPI/React/Chroma 或安装另一套 RAG 框架。

“不再反复重建”应落实为：来源长期保留，系统自动重算受影响派生资产，用户不反复操作。来源文字或结构改变时，相关检索块/向量仍需要内部更新；不能靠继续使用旧向量声称避免重建。

## 2. 本地已经复现的通用缺口

本节是 P0/P1 实施前的调查快照。嵌入截断、实际输入/模型指纹与字符 span 检查已由 P0 修复；上游漏标标题及目录/正文统一处理由 P1 补齐。来源范围、解析阶段 ID 与类别耦合、独立整书金标仍有缺口，不把历史结果改写成现状。

证据为 [合成复现](validation/index-generalization-2026-10-27/synthetic-findings.json) 和 [本地 tokenizer 审计](validation/index-generalization-2026-10-27/token-audit.json)。合成复现不依赖任何书名/教材内容；351 页材料是本机既有回归来源，不是截图用户的书。没有调用 OCR、回答模型、外部嵌入服务或修改 active 索引。

| 问题 | 实际证据 | 影响 |
| --- | --- | --- |
| 字符切块与模型 token 上限脱节 | `ChapterSplitter` 默认 700 字符；ONNX provider 明确右截断至 512 token。640 个合成汉字形成一块，连同上下文前缀为 664 token，provider 只保留 512 | 原文和词法索引还在，但向量表示缺少尾部；“块已入库”不代表全块参与检索 |
| 标题恢复仍依赖上游类别 | 将合成章节标题标为普通 `text`，有完整可读正文但没有检测到编号章，IR 仍有效 | 分类漏报会使目录退到整书，单改 `paragraph_title` 规则补不回来 |
| 部分来源与整书范围未形成合同 | 合成 `is_full_document=false` 可进入 Adapter；标志未保留为来源范围状态，未产生对应范围提示 | 包格式合法与整本书完整不是同一个结论；有意选择的页范围也需要明确标识 |
| 来源身份和语义分类耦合 | `_BlockBuilder.add` 的 ID 包含 `block_type`；同来源定位、同文字，paragraph 改成 heading 会换 ID | 修结构时连来源引用身份也变化，影响学习资产关联及差量计算 |
| 索引版本未标识全部嵌入输入 | 仅改 chunk 的 `retrieval_text`，`index_pipeline._fingerprint` 不变；该函数也未纳入模型/tokenizer/归一化身份 | 无法由版本身份完整说明向量怎样生成；这不是“当前已经错误复用缓存”的证据，因为当前构建仍会重算 |
| 新增保全检查仍只到块成员覆盖 | 保留所有 `source_block_ids`，将 chunk 正文替换成其他文字，`validate_index_structure` 仍通过 | 它能抓漏块/错章，不能证明字符/span 全覆盖；本轮修复不得被称为无损解析证明 |
| 验收主要来自同一份 IR | 自动 probe 与 source inventory 均由已解析 IR 产生，专项为 formula/list/example/table；没有独立的章节树与习题边界专项 | 上游没有识别出的对象，可能同时不在索引和考题中，形成共同漏检；少量 probe 的 1.0 不能代表整本教材准确 |

### 嵌入超限的规模

按真实运行时 `Sequence([Lowercase(), original_normalizer])` 复核，本地 351 页来源的 1922 个可检索块中，**242 个超过 512 token，约 12.6%**，最长 854 token。分别为正文 238、例题 2、公式 1、表格 1。初次未额外应用运行时 Lowercase 的计数为 237；本报告以复核后的 242 为准。

这是嵌入输入覆盖问题，不是 12.6% 的问题必然回答错误。BM25/词法仍可能召回完整文本；此次没有测量回答准确率。1922 不包含 `retrieval_excluded` 的图片目录项，也不应与全部 chunk 数混用。

相关实现位置：

| 位置 | 需要核查的责任 |
| --- | --- |
| `ingestion/chapter_splitter.py` / `ChapterSplitter.__init__`、`_append_chunk` | 字符预算、完整 embedding 前缀、父子块及 source span |
| `ingestion/onnx_embeddings.py` / `MAX_LENGTH`、`ONNXEmbeddingProvider.__init__` | tokenizer、归一化及截断 |
| `ingestion/mineru_structured.py` / `from_structured_content` | 来源范围、原始类别、版面元数据、结构信号 |
| `ingestion/document_adapters.py` / `_BlockBuilder.add` | 来源身份与派生分类分离 |
| `ingestion/index_pipeline.py` / `_fingerprint`、`_add_collection` | 嵌入输入/模型身份；章节与 aggregate 重复计算同一向量 |
| `ingestion/acceptance_probes.py`、`_validate_staged_production_retrieval` | 自动保真探针与独立金标的分工 |

## 3. 一手资料给出的共同方向

以下是资料支持的事实；对 Texa 的方案是本报告的工程判断，没有在本机安装或对比运行这些系统。

- **布局模型给出“标题类别”不等于给出正确层级。** Docling 的层级恢复会结合书签、编号及视觉样式；扫描件缺少字体元数据时，部分样式信号不可用。它把这一过程放在阅读顺序之后的单独阶段。Texa 应借鉴多信号恢复，不能把 `raw_level` 或短字符串直接当权威。[Docling 官方标题层级说明](https://docling-project.github.io/docling/usage/heading_levels/)
- **结构分组后还要按真实 tokenizer 调整。** Docling 的 HybridChunker 在结构切块上按 token 约束拆分/合并，并保留标题、caption 等上下文。Texa 应对最终送进 embedder 的完整字符串计数，而不是只看正文字符数。[Docling 官方切块说明](https://docling-project.github.io/docling/concepts/chunking/)
- **标题误报是普遍问题。** Unstructured 的官方文档明确讨论短段落/列表项被误判成 Title 后产生碎块。它不能证明某个现成 chunker 适合考研教材，但说明仅按上游 Title 强切存在通用风险。[Unstructured 官方切块说明](https://docs.unstructured.io/api-reference/legacy-api/partition/chunking)
- **文档应保留内容、阅读顺序、树结构和来源位置。** DoclingDocument 将正文与页眉页脚等 furniture 分开表达，而不要求先扁平化为 Markdown。Texa 的 Canonical 方向是合理基础，应补原始信号与关系。[DoclingDocument 官方结构](https://docling-project.github.io/docling/concepts/docling_document/)
- **MinerU 的输出包不只是文字。** 官方协议区分消费侧 structured content、中间协议及导出形式，完整保存包包含共享图片资源；历史包应跟随实际资源引用。应长期保存原包并保留真实引用，不从文件名猜图，也不因换结构规则重新 OCR。[MinerU 官方输出合同](https://github.com/opendatalab/MinerU/blob/master/docs/en/reference/output_files.md)
- **多页结构需要单独测。** OmniDocBench 分别评估文字、公式、表格及阅读顺序；MPDocBench-Parse 进一步覆盖跨页连续性和标题层级恢复。Texa 需要按任务分层评测，不能把单页 OCR 分数或自身 probe 的总均分当整书可用性。[OmniDocBench 作者仓库](https://github.com/opendatalab/OmniDocBench)、[MPDocBench-Parse 论文](https://arxiv.org/abs/2605.22100)

BAAI 官方模型配置也标明 `max_position_embeddings=512`。提高本地 tokenizer 上限不会自动扩大模型能力。[BGE-small-zh-v1.5 官方配置](https://huggingface.co/BAAI/bge-small-zh-v1.5/raw/main/config.json)

## 4. 建议的共享建库过程

```mermaid
flowchart LR
    A[来源包与原页] --> B[保全来源块与真实定位]
    B --> C[共享结构恢复与关系核验]
    C --> D[章节视图与完整学习单元]
    D --> E[按实际 tokenizer 生成检索子块]
    E --> F[向量与词法候选索引]
    F --> G[来源保真与独立任务验收]
    G --> H[原子发布或保留旧版]
```

### 来源保全

来源 adapter 只做协议解释、物理页/坐标/原始文本/资产转入 Canonical；保存源类型、原始标题级别、阅读顺序及原始关系。原文与结构推断分开，排除页眉/目录页等对象需要保留理由和源定位，不能从来源清单中静默消失。

来源范围明确为整书、用户指定页集、部分结果或未知。不得把 `is_full_document=false` 与“整书完成”混用；也不能一律拒绝合法的指定页导入。

### 一套共享结构恢复

从书签/目录项、正文重复标题、编号序列、跨页位置、字号或行高、缩进和样式一致性形成候选树。书签和目录也要核对正文锚点，旧目录/附录/印刷页偏移不能直接覆盖物理页定位。

各信号记录来源和冲突；同书重复“习题”“小结”以稳定节点与范围区分。利用整份文档的样式统计消歧，不给每本书写 Python 分支，也不为每本书手工配置规则。局部不确定保留 unknown 与连续正文，不强造完整目录。

层级未知不应让整本书正文无法检索。用户选定整书时可以在同书可证明的范围内检索；用户明确限定某章时仍须遵守该范围，不能用“目录不准”静默扩成全书。

已有 `PDFParser` 含书签/文本目录/字体分析路径，但这些信号未统一进入原生 MinerU 的结构恢复。应先复用、对齐现有能力，不再添加一个只服务某本书的 adapter。

### 学习单元与检索子块分工

完整题干、子问、源解、公式、图表组成有来源关系的学习单元，供候选校对及上下文恢复使用。检索块可以更小，命中后恢复同单元必要条件；“一题保持完整”不要求把整题塞进单个 512-token embedding。

对最终 `embedding_input = 上下文前缀 + 子块正文 + 特殊 token` 校验长度。长公式/宽表格不能靠任意切字符串凑长度；保留原子原文/原图，并生成可追溯的安全检索表示或明确退化。模型不支持的长度必须被发现，不能静默截断。

### 独立身份与差量更新

来源节点身份依赖来源内容身份与稳定 locator，不依赖“当前认为它是标题还是正文”。结构、学习单元、检索子块分别版本化，通过兼容映射保留旧笔记/题目引用，不强制迁移全部旧资产。

向量缓存键应包含实际 embedding 输入、模型/权重、tokenizer、归一化、pooling 与长度策略；章节索引和 aggregate 可以复用同一向量。仅变展示目录时不重新 OCR；确实改变嵌入输入时只更新相关块。继续暂存、验收、原子激活和回滚。

## 5. “准确”的验收方式

| 层 | 检查内容 | 适用方式 |
| --- | --- | --- |
| 来源 | 页范围/阅读顺序/原始资源闭包；文字、公式、表格识别 | 每次自动完整性检查；分层人工金标测 OCR，不能由 OCR 自己证明自己 |
| 结构 | 标题 precision/recall、父子边/范围、重复标题、跨页连续性 | 全文一致性检查 + 留出整本书的金标 |
| 保真 | 来源 span 覆盖、排除理由、无错章、必要图表/条件关联 | 可确定的机械合同要求零静默丢失；P0 已从块 ID 覆盖推进到字符/span 检查，语义关联仍需独立验收 |
| 嵌入 | 完整输入 token 数、零静默截断、模型身份绑定 | 每个块自动检查，不靠抽样 |
| 检索与证据 | 定义/列举/比较/推导/应用/跨章、同书同名、负例，最终 EvidencePack 覆盖 | 独立问题与证据锚点；保留已有门槛，新增指标先离线观测再决定阈值 |
| 习题 | 题目边界、子问完整、源解归属、跨页图表/前例 | 单独验证，不能用 RAG 总分代替；无习题教材标 not_applicable |

跨教材验证按**整本书留出**，避免同书不同页泄漏版式规律。材料覆盖文字 PDF/扫描件/混合 PDF、单栏/双栏、中文/中英混排、数学/专业课、题解集中或随题、目录缺失和重复标题、多种来源版本。

人工标注用于一次性建立、复用评测基线，不要求每本用户新书都先人工制作金标。每次普通导入运行通用自动检查，只有真正的局部异常才展示可定位的缺口；不向用户要求理解向量库或执行诊断脚本。

严重缺页、不可辨字和未提供的附图不能被算法补成正确内容。产品应尽量自动恢复、保留可用范围并明确局部缺口；不能用全书成功提示掩盖缺失，也不能让少数不确定对象挡住全部可读内容。

## 6. 实施顺序与本轮状态

| 顺序 | 可独立审阅的工作 | 完成判据 |
| --- | --- | --- |
| P0（已实施） | tokenizer 对齐的编码窗口和嵌入输入预检；来源 span 保全合同；绑定实际模型/输入身份 | 249 项后端、56 项桌面、真实 ONNX/Chroma 与 Electron 导入通过；范围见专项验收 |
| P1（已实施功能） | 共享目录/正文匹配、书签/编号/实际字体恢复；示例校准与正常发布 | 中英文与不同编号场景及真实 Electron 校准—发布—按章检索/抽题通过；没有单书分支，尚不能量化绝大多数教材准确率 |
| P1 并行 | 补跨教材独立结构/习题/检索金标与发布观测 | 按文档类型和关键任务分别报告，不用总体分数掩盖失效 |
| P2 | 差量重算与嵌入复用、导入内自动局部恢复 | 用户无需反复上传/OCR；实际变更只影响必要派生资产，旧版本可回滚 |

前序修复见 [MinerU 习题验收](validation/mineru-exercises-2026-10-27/README.md)：v5 结构保全、自动空习题提示、机械漏块/错章检测及 MinerU 习题 ZIP 直导；相关 245 项后端、256 项前端及真实 Electron 检查通过。随后 P0 的输入保全、模型身份与正常教材导入验证见[独立记录](validation/index-input-p0-2026-10-27/README.md)，不将前序测试冒充 P0 或 P1 验收。

P0 已实施 token 预检/编码窗口、span 合同与实际模型/输入身份。P1 现在从保留的来源信息重建章节解释，在该过程内保持 block ID 与文字，示例保存在教材元数据中，不生成单书 adapter；原始 adapter 创建 ID 的方式尚未整体迁移。来源范围、独立整书金标及持久差量更新仍待继续。没有重装依赖、替换 OCR/嵌入模型、迁移旧 schema/学习资产或批量重建索引。新导入自动使用共享恢复；旧教材只有用户应用校准时才发布新索引。

可重复运行只读合成调查：

```sh
venv310/bin/python docs/validation/index-generalization-2026-10-27/reproduce_contract_findings.py --output /tmp/index-contract-findings.json
```

该脚本是开发验收材料，不是要求终端用户执行的诊断步骤。
