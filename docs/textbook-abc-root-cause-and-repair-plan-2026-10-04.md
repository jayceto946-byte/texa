# A / B / C 教材验收：根因分析与修复方案

日期：2026-10-04（北京时间）。教材：传感器原理及应用。依据为用户导出的验收记录、实际 Electron 数据目录、后台日志、任务数据库副本和当前源码。

本文记录最初的诊断与方案；后续代码修复及开发版验证见 [修复验证记录](textbook-abc-repair-validation-2026-10-04.md)。初次诊断没有实施业务修复、修改正式教材/学习数据、重建索引或调用模型。仓库基准 HEAD：`d36767f32690506b3697340bb6eaa948395dbcf0`。当前源码分析不能证明用户安装包采用同一提交；日志与实际数据结论独立成立。

## 1. 数据与时间定位

- 实际桌面数据根：`/Users/jichengqian/Library/Application Support/kaoyan-assistant-desktop`，不是仓库的 `data/`。
- 原始输出：`mineru_output/传感器原理及应用/hybrid_auto_external/CGQ/structured_content.json`；生产者 MinerU 4.0.8，351 个物理页。
- 导入任务 `2cd4887fc8824e8fb49a0bcaa7d72cea`：12:26:45 创建，12:31:23 完成。导入索引 1826 个文本 chunks，完整目录 catalog 为 2489 项，含 663 个 figure。
- 活跃 index：`c8b6947edb7858f2`；Canonical hash：`89dd1ed5d647ad563a49fe6c132ed7ebff8f34e6ff8c3b91d185c9625603dda3`。manifest 已于 12:31:22 激活并记录生产混合检索与 EvidencePack 门槛结果。
- 后台日志为 UTC；下文时间已转换为北京时间。SQLite 诊断在临时副本上完成，未直接写入原数据库。

最小结构化证据：[evidence.json](validation/textbook-abc-2026-10-04/evidence.json)。现有回归：[existing-regression.log](validation/textbook-abc-2026-10-04/existing-regression.log)。没有把完整教材、凭证或原数据库复制进仓库。

## 2. A 阶段：导入成功，但概念抽取记录与事实不一致

**已确认事实：**正文导入成功且没有要求原 PDF；任务结果 `has_pdf=false`。原始包和教材库确实均无 PDF。

**验收记录需要纠正：**A04 勾选“没有意外启动概念抽取”，实际导入任务输入是 `extract_concepts=true`，结果关联概念任务 `1515a3fb7a404840b5c95d6efd313685`。该任务于 12:31:23 创建，12:47:09 失败，错误为连接被对端关闭、响应体未完整接收。

**根因边界：**`backend/api/books.py::_run_output_import_job` 在索引完成后按参数启动可选概念抽取；前端 `BooksPage.tsx` 默认 false，但会提交勾选状态。因此能证明本次请求启用了抽取，不能据此断定前端自行开启，也不能确定是供应商、代理、网络还是进程关闭导致断流。导入成功与后续概念任务失败是两个状态，正文可用性不应随 KG 失败而被否定。

**修复方案：**导入完成结果显式展示本次是否启动概念抽取及关联任务状态；KG 失败保留正文成功结果和明确失败入口。每次打开导入流程核对勾选状态，不自动付费重试。验收重新分别记录导入、索引、概念任务。

## 3. B01：层级没有在 OCR 或 Canonical 中丢失，而是在目录投影中丢失

**已确认事实：**Canonical 有 270 个 heading：一级 12、二级 79、三级 177、四级 2；`1.1 传感器的概念`、`1.1.1 传感器的基本组成` 及路径均存在。但 `_chapters.json` 只有 13 条顶层记录，`subsections` 总数为 0；13 条包含前置材料及正文 12 章。

**代码因果链：**

1. `ingestion/mineru_structured.py::from_structured_content` 已识别编号章节与小节。
2. `ingestion/mineru_importer.py::chapters_from_canonical` 按 `canonical_retrieval_paths(...)[0]` 聚合，仅生成顶层章节和正文，未生成小节元数据。
3. `backend/services/book_chapters.py::format_chapter` 只能输出记录中已有的 `subsections`。
4. 实际用户调用过的 `/chapter-highlights` 由 `knowledge/chapter_highlight_source.py::_load_section_refs` 读取同一字段；字段缺失则返回空列表。`HighlightRepositoryDialog.tsx` 的选择项也依赖它。

**结论：**这是 Canonical 到目录/重点范围的共享投影缺口，单纯改标题正则或重新 OCR 无法解决。

**修复方案：**从活跃版本 Canonical heading 生成共享的有层级目录投影，保留 `heading_block_id`、父节点、level、路径、物理页和起止 block；供目录、重点范围和练习范围复用。旧教材缺少 `subsections` 时使用只读补全，已有重点/笔记标识保留兼容，不能按标题静默重绑。新导入同步写兼容投影。

**页码关联缺口：**原始物理第 29 页的 `page_number` block 是印刷页 19；当前 structured adapter 排除该 block，只在 page 对象自带 `page_number` 时写印刷页属性。本语料的 page 对象未提供该字段。修复应保留原始印刷页标签及映射来源，明确区分物理页与印刷页；不能统一猜测减 10。同页小节边界应使用 block 范围，不能仅靠下一标题页减一。

## 4. B04：两张子图都存在，缺少组合图关系

**已确认事实：**物理第 29 页（印刷页 19）：

| 子图 | Canonical block ID | 图注 | 状态 |
|---|---|---|---|
| a | `1d626f2debe0b25f6381` | `(a)` | 图片 ready |
| b | `87aa1723025bc7745fd3` | `(b)` 及图 1.21 完整图名 | 图片 ready |

13:01:47 日志记录用户打开 b 图图片接口，HTTP 200。这与反馈中只能把单张图当成整张频率响应曲线的现象吻合。

**根因：**MinerU 将两个裁切块分开，把公共图注挂在 b 图；structured adapter 每个 image/chart 都生成独立 figure，`FigureLearningService` 按单 block 输出和打开图片，没有共同图号、组 ID、成员顺序或组合图完整性信息。两张资产未丢失，但语义关联未建立。即使搜索偶尔召回 a 图，也不能保证阅读或视觉推理同时得到两图。

**修复方案：**保留原 block 和图片，增加可追溯的组合图投影。基于同页布局、连续子图标号和公共图注做保守分组；有歧义标记人工复核，不能把同页所有图合并。列表呈现一条公共图，详情按 a/b 顺序展示成员，单子图链接仍可用。检索和视觉输入携带成员 block IDs、各自 bbox、共同图注及缺失状态；不能把 b 图 bbox 当作整组 bbox。若问题依赖整图而成员缺失，进入输入门槛。

优先通过服务读取时派生分组改善已导入教材；若把关系写入 Canonical/索引属性，必须生成新候选版本并验收后激活，不原地改活跃版本。

## 5. B05：PDF 是入口表象，抽题有四个实际缺口

### 5.1 无 PDF 仍显示入口，输入页码还会自动弹窗

`ExercisesPage.tsx:79` 只根据教材名拼接 `sourcePdfPath`；页面没有使用 `/books/list` 已提供的 `has_pdf`。起始页 `onBlur` 又直接设置 `pdfOpen=true`。本次教材根本没有 PDF，`source-pdf` 缺文件时返回 HTTP 200 加 `success=false` JSON；日志 13:05:50 的 200 不能证明源 PDF 可用。

**修复：**使用真实 `has_pdf` 显示 PDF 按钮；手填范围直接生效，预览通过显式点击打开。有 Canonical 时可从章节/页/block 选范围。缺 PDF 返回明确的资源缺失响应，前端校验内容类型与业务结果，避免把 JSON 当 PDF。抽题不因缺 PDF 阻断。

### 5.2 原生 structured 路径与旧抽题器未共享学习单元

`memory/textbook_exercise_importer.py` 读取重点 source package、`middle_chunks`、旧 OCR JSONL、PDF/OCR 回退，没有从活跃 Canonical 读取完整例题单元。本次导入确实由 `ingestion/mineru_importer.py` 生成了兼容 `middle_chunks`，所以不能说“抽题完全无数据”，也不能说后端硬性要求 PDF。

原始语料可识别到 14 个 `【例 …】` 起始块，Canonical 中却没有一个 `example` 类型。structured adapter 把它们当普通 paragraph；通用标签识别、抽题 `_looks_like_example` 和 probe 正则也不接受前面的 `【`。普通段落经过切块后，题干、解答、表格、公式分属不同 chunks，角色又被 derivation/formula/reference 等覆盖。只筛 role=example 或文本题号会漏题，也会抽到半题。

**本地无模型复现：**限定“第1章 绪论”时，抽题器返回 provider=`mineru-middle-chunks`、3 chunks、720 字；实际是同一个 `325e2ddadf91011dd1fc` chunk 三次，内容从例 1.5 的后半段开始。该章实际存在 6 个编号例题起始块。全书不填章节则读到 6 chunks、802 字，但 `resolved_chapter=''`，API 会因无法确定所属章节拒绝。日志没有保存两次历史 POST 的请求体/响应体，所以不能确定当时使用了哪种参数。

**修复：**在摄取公共能力中统一题号/学习单元识别，涵盖 `【例 1.1】`、`例1.1`、`例题` 等格式，并让 structured adapter、chunking、抽题和 probes 复用。按明确边界为题干—条件—解答—公式—附表/图建立同一学习单元，遇下题/新主题及时终止，不能无限合并。抽题优先读取 manifest 绑定的 Canonical 版本和单元来源，不以角色分类代替完整题目。可先对现有 IR 做只读分组恢复，无需重新 OCR。

### 5.3 同一个兼容文件被扫描三次

`_candidate_output_dirs` 返回 CGQ、本级父目录、教材根；`_text_from_middle_chunks` 对每个路径递归搜索，三次找到同一个文件，没有按解析后的路径或 chunk 身份去重。

**修复：**文件按 resolved path 去重，候选按 book/index/chunk 或 learning-unit 身份去重；备用目录只在主源不足时使用，不重复读取同一文件。

### 5.4 章节归属要求被留空流程掩盖

API 要求抽到的候选具有明确章节；当前 UI 却把章节输入标为“可留空”，未在无页码/跨章时说明需要归属。现有全书抽取无法给每题独立归章。

**修复：**短期提供真实章节选择，使用已有物理页范围自动归章；跨章/不明归属返回清晰状态。后续按学习单元逐题保留来源章节，避免把全书所有题强制归入同一个手填章节。

## 6. C 阶段：存在历史检索通过证据，也存在明确的覆盖漏洞

**已确认：**本次活跃 manifest 的 24 项自动探针（formula/list/table 各 8 项）通过生产混合检索和最终 EvidencePack 门槛，不是只有初始检索命中。另有本教材 12:51:40、12:59:41 两条完成的 RAG trace。

**不能推出：**这些证据不等于 C01 已人工验收，也不覆盖 C02 完整列表/精确型号、C03 范围边界、C04 错误前提。用户报告没有 C01 受阻说明，日志也没有对应的完整用例输入/预期/最终结果，无法给 C01 的受阻指定一个已证实根因。

**已证实的门槛漏洞：**probe 的例题 inventory=0，manifest 对例题给出 `not_applicable`、`passed=true`。前述 14 个带括号编号例题因为识别缺口没有进入探针，构成假阴性覆盖。这说明本轮“例题不适用”不可靠，不能依此放行例题链路。

**修复：**源端学习单元清点与生成的测试数交叉核对。源中存在编号例题而分类/探针为 0 时，标为覆盖不足，拒绝例题类别放行；只有源清点确认为不存在才允许不适用。既有门槛保持，补充例题题干、解答、表格和跨页支持点及禁止混入内容。以真实教材 ID 和 active manifest 重跑无模型生产检索，保存最终 EvidencePack 和分类型结果；C02–C04 单独建人工预期，不能只问两条普通 QA 就宣称通过。

## 7. 新发现：OCR 可疑内容进入活跃索引，合同合法不代表内容正确

原始 `structured_content.json` 的物理第 5 页含经济指标叙述及长串重复的科研表述，和教材主题/前言上下文显著不符。对应 Canonical 块 `a48e1ff53f4d8c6f6c2d`、`e707d791d035c6ed9407` 被保留；活跃 lexical catalog 的 `b8e9968ee96b92d45ca3`、`e5ec4f79665ca8317a42` 可检索，未标 retrieval_excluded。

**根因边界：**可疑文本在服务器原始输出中已经存在，不能归因于客户端回答生成。最终是否识别错误需要对照原页；本轮没有源 PDF，未完成原页人工确认。客户端摄取报告是 `valid=true`、errors=0、warnings=5529，其中缺置信度 4925 项；既有检查主要验证结构合同、短文本和资产完整性，未覆盖这些重复/离题信号。既有规定允许可修复 warning 后继续索引，本身不能把 valid 解读为 OCR 正确。

**修复：**建立有定位的内容质量审阅项，对异常重复、解析器拒识叙述、明显前置材料污染给出 review status；不要把所有缺置信度块统一挡住，也不要自动删掉原文。保留原 IR/crop，人工确认后只修复或隔离明确问题块，并生成候选索引验收。结构合格、检索合格、OCR 审阅分别呈现；自动探针只能证明结构传递，不能证明原文语义正确。

## 8. 实施顺序与验收合同

| 顺序 | 工作包 | 关键验收 |
|---|---|---|
| 1 | 修复无 PDF 入口、目录只读投影、旧文件去重、明确章节归属 | 无 PDF 能选择真实章节并抽题；起始页不自动弹窗；1.1/1.1.1 可定位；同文件只读一次 |
| 2 | 公共学习单元识别与完整抽题；修正例题覆盖判定 | 本语料 14 个已清点例题起始块不漏；第1章 6 题逐题匹配；例 1.3 包含表 1.1 和解答；无关键条件/附图/公式截断；人工校对后才入题库 |
| 3 | 组合图及来源页码投影 | 图 1.21 同时显示 a/b，完整图名和顺序正确；旧子图链接可用；物理页29与印刷页19分别可追溯；相邻不同图不误合并 |
| 4 | OCR 内容审阅及候选索引发布 | 可疑块有明确待审状态和来源，不从原文直接删除；例题类别不再错误不适用；候选通过生产检索/EvidencePack 后原子激活，旧版本可回滚 |
| 5 | 重跑 A/B/C 桌面验收，补诊断状态 | 导入/KG 状态分开；列表/型号/章节边界/错误前提分别记录；无模型评测可由本地脚本执行并导出证据，不要求用户触发付费生成 |

第 1–3 包优先利用现有 Canonical/资产完成，无需重新提交 OCR、重装依赖或修改数据库结构。第 4 包涉及正式教材纠正和活跃索引变更，实施时按 AGENTS.md 的数据安全和候选发布要求执行，先呈现具体候选与验证结果，再进入正式变更审批。不要为目录显示问题先破坏现有索引。

回归需补：无 PDF、纯 structured 输出无兼容文件、带括号例题、半题与同页/跨页附表、三层目录、同页多个标题、重叠输入目录、组合图/独立图/缺子图、零探针假阴性和 OCR 可疑块。UI 修改后优先验证 macOS Electron 的实际入口、重启及 1280×820 / 1024×768 / 760×820；分发包和 Windows 另验。

## 9. 本轮验证结果和边界

Python 3.10.21 / venv310，在临时 DATA_DIR/PROGRESS_PATH/VECTOR_DB_PATH 中运行五组现有相关测试：`test_mineru_structured_content`、`test_textbook_exercise_importer`、`test_book_chapter_service`、`test_figure_learning`、`test_acceptance_probes`，57 passed，6 条既有弃用警告。现有测试通过不代表上述问题已修复；本轮真实语料诊断复现了缺口。

本轮没有运行新的付费模型、人工 OCR 原页核对、新的全量 C02–C04 用例、原生 Windows 或安装包验收。没有修复业务源码或修改正式索引，报告仅给出可执行的修复方案。
