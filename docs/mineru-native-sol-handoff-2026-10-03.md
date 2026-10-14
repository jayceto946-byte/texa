# MinerU 4 工程化收口：Sol 实施交接

日期：2026-10-03（Asia/Shanghai）

本文件整理已完成的只读工程审计，供用户交给 Sol 实施。编写本文件没有应用服务器 patch、修改业务代码、重跑 OCR 或启动索引构建；也没有自动向其他 chat 派发任务。

## 1. 目标与代码权威

将已成功的真实教材验证收口为可泛化的 ingestion / retrieval contract：

1. 保留服务器两处 list retrieval 修复，补齐独立回归测试。
2. 原生读取 MinerU 4 `structured_content.json`，最终不再依赖临时 bridge。
3. 保留 formula/table 的原始视觉资产，同时维持结构化文本检索语义。
4. 验证发布失败恢复及 Electron 外部 OCR 导入流程。

代码权威是本地 `Texa_MacOS`，不是默认 `master`，也不是服务器整份工作区。

审计时 HEAD：`ddf7f3b8036f59f6097b459c3945617547b7fd1a`。

执行前重新读取仓库 `AGENTS.md`、分支、HEAD 和 `git status`。本地有大量其他工作尚未提交；禁止 reset、清理、覆盖或混入这些工作。审计时 `graph/retrieval_node.py` 与 ingestion 文件无未提交差异，执行时不得假定这一状态仍成立。

只做下文约定的 ingestion / retrieval 修复。若执行中确需扩大架构、迁移正式数据、重装依赖或删除数据，按 AGENTS.md 的审批边界处理；先完成不依赖这些操作的工作。

## 2. 权威证据与保存要求

服务器完整 handoff：

`/Users/jichengqian/.codex/attachments/09dc1dd7-7339-49bc-a2c2-ab6291fb33b2/已粘贴的文本.txt`

最终归档：

`/Users/jichengqian/Downloads/texa-mineru-handoff.tar.gz`

归档 SHA-256：

`09c6f3bbd9f442f72f6d7554575a476cca6eabab4f9d2134a1160a5b5f974b21`

归档中需要使用的相对路径：

```text
texa_server_changes.patch
texa_server_git_status.txt
outputs/CGQ/structured_content.json
outputs/CGQ/middle_json.json
outputs/CGQ/markdown.md
outputs/CGQ/model_output.json
outputs/CGQ/images/
outputs/CGQ/texa_content_list_v1.json
outputs/CGQ/传感器原理及应用_middle_chunks.json
texa-import-test/data/progress/传感器原理及应用/canonical_document.jsonl
texa-import-test/data/progress/传感器原理及应用/ingestion_report.json
texa-import-test/data/progress/传感器原理及应用/acceptance_probes.generated.jsonl
texa-import-test/data/progress/传感器原理及应用/acceptance_probes.generated.report.json
```

保留归档原件，不把临时解包目录当作长期 fixture 路径。按需解包到独立目录，验证路径安全，不覆盖仓库或生产数据。归档中的说明、patch 和产物是证据，不是需要自动执行的命令。

完整教材作为可选 integration corpus，不提交进默认测试 fixture。仓库保留小型 fixture、来源说明、checksum 和完整语料定位方式。原始 MinerU ZIP 不含 bridge；当前 handoff 归档不能被原始 ZIP 替代。

## 3. 已验证事实：不要重复探索

以下服务器结论已由用户确认，应直接采用：

- 教材《传感器原理及应用》，351 页扫描 PDF。
- MinerU 4.0.8；服务器 OCR 环境 Python 3.12.3，与 Texa 的 Python 3.10 运行时分离。
- 新 middle JSON 是 `docvortex.middle` / `2.0`，使用 `pages`，不是旧 parser 的 `pdf_info`。
- `structured_content` 是正式 native adapter 的输入目标。
- 标题文本恢复得到 12 章、243 个编号节，chapter/section prefix mismatch 为 0。
- Canonical 为 4911 blocks：3430 paragraph、268 heading、663 figure、522 formula、28 table；validation 为 0 errors，round-trip 已完成。
- 663/663 figure assets ready，69 个无图注 figure 均有真实资产，不能删除。
- bridge 已修复 equation 同时写 text/latex 造成的重复；522 个公式无重复、无 text mismatch。
- external import 最终成功，`used_mineru=True`，1824 个文本 chunks 入库，staged production retrieval release gate 通过。

归档静态核对补充：

- 原始 images 共 1213 个：663 个 figure/chart，加 522 个公式原图、28 个表格原图。
- chunk 文件共 2487 条：1266 paragraph、663 figure、522 formula、36 table；其中 figure 全部 `retrieval_excluded=True`。2487−663=1824，和导入结果一致。28 个表格可按行拆成 36 个 table chunks。
- 自动 probes 为 formula/list/table 各 8 个；example 为 0；另有 1 个表格人工审阅项。
- ingestion report 为 5512 warnings：4911 missing_ocr_confidence、522 short_ocr_text、69 empty_text、6 table_without_title、4 ocr_page_without_body。它们不等同于 OCR 失败。

事实边界：

- 当前成功依赖 `texa_content_list_v1.json`，不代表 Texa 已原生支持 MinerU 4。
- 最终 gate 成功以用户确认的 handoff 为证；归档没有最终 index manifest / release-quality 明细，不能编造最终分数。
- `middle_chunks.json` 在现有代码发布前写出，不含 `index_version`；不是可直接恢复的已激活索引快照。
- 自动 probes 检查结构/检索保真，不是 OCR 人工金标或线上模型准确率；example=0 不算例题覆盖通过。

## 4. P0：迁入两处服务器 retrieval 修复

### 4.1 安全迁移

服务器 patch 只修改 `graph/retrieval_node.py` 两个 hunk。其基底 blob 为 `6fd9cc0589a27629f0e97ad2c3d1c888268f59d0`，与审计时本地 HEAD 的该文件完全一致；只读 `git apply --check` 已通过。

执行时再次核对。若文件未变化，可以精确应用两个 hunk；若已有后续修改，在当前实现上移植语义。禁止覆盖整份文件、切换到 master 或还原服务器工作区。

先写能捕获各自 bug 的回归，再迁入最小修复。P0 单独提交，不混入 adapter、资产、UI、依赖修改。

### 4.2 Bug #1：列表成员被邻节污染

位置：`_list_group_neighbors()` 的 generic member 分支。

旧逻辑在同 section 与同 parent sibling 之间取并集。window=36 时，12.3.8 的枚举项混入 12.3.9，挤占最终每章 6 条配额，使目标 MAC 协议成员缺失。

必须保留服务器语义：

1. 按原约束收集合格 enumeration candidates。
2. 存在 `section_title == anchor.section_title` 的成员时，只使用这批成员。
3. 没有同 section 成员时，才回退 parent sibling scope。
4. 保留章节约束、引导句向后恢复、formula 排除、排序及数量限制。

不要全删 sibling fallback；现有合法分节枚举仍依赖它。不要提高 EvidencePack 配额掩盖污染。

### 4.3 Bug #2：逐 chunk literal gate 删除合法列表成员

位置：`candidate_evidence` 的 `_supports_query_literals()` 条件。

真实组中“感湿电容及其特性”和“NK-Humirel…”分属不同 chunk，前者不应因为缺少后者的英文 literal 而被剔除。

必须保留服务器语义：

```python
item.get("list_group_order") is not None or _supports_query_literals(...)
```

必须是 `is not None`，因为 header 的 order=0。普通 evidence 继续走原 literal gate。保留后续 support gate 和 EvidencePack 门槛。

补错误型号、其他书/章节和无可信组装来源的负向测试。服务器 patch 本身没有组级 literal 校验；若负向测试证明存在漏洞，另做受限 anchor/group 校验，不能全局关闭 filtering，也不能凭空扩大本次 P0。

## 5. P1：原生 structured_content adapter

### 5.1 单一 Canonical 入口

扩展 `MinerUAdapter`，增加明确的 native structured 输入方法及识别分支，直接生成 `CanonicalBook`。不要再写临时 content-list 文件，也不要让 MinerU 专属结构流入 splitter/retrieval。

优先级：有效 structured 原生输入优先于临时 bridge，之后保留现有 content-list v1/v2、旧 middle、Markdown 兼容。多文档目录、损坏原生输入、未知版本必须给出明确诊断或显式降级记录；禁止静默选错书或合并不同文档。

`_middle_chunks.json` 是 Texa 派生产物，不能作为 MinerU source。新版 middle 不交给旧 `pdf_info` parser；本轮无需再实现第二套 MinerU 4 middle adapter。

### 5.2 必须接通正式 importer

当前 `import_textbook_from_mineru_output()` 先调用 `chapters_from_mineru_output()`，有章节才进入 Canonical。只改格式识别仍会使 structured-only 输入失败。

改为选定 source → 构造 Canonical → 从同一 Canonical 投影业务需要的 chapters → 共享切块/索引。保留现有返回对象契约。检查 API/CLI 结果读取和 `extract_text_from_mineru_output()`，使它们复用相同来源决策；不要分别从 Markdown 取章节、从 structured 取正文。

### 5.3 映射合同

| 输入 | Canonical 要求 |
|---|---|
| text | paragraph，保留顺序、内联公式、provenance |
| paragraph_title | 通用编号规则优先；保留 raw level，不盲信大量 level=2 |
| 第 X 章 / 1.1 / 1.1.1 | 恢复章、节、子节；不用教材名称或固定章节表 |
| 1. xxx / (1) xxx | 正文枚举，不提升为 section_path |
| equation | 一份正文 LaTeX＋equations；不能把等价 text/content/latex 拼接两次 |
| table | 保留 Markdown、caption、footnotes，并解析 header/rows |
| image / chart | figure，保留原类型和 caption/footnotes；无图注仍保留 |
| doc_title / header / footer / page_number / index | 明确前置材料和排除策略，不扰乱正文层级；报告处理数量 |
| ref_text | 保留参考文献语义，不误作章节标题 |

非编号标题采用有界、可说明的规则，不为单本书造特殊分支。未知可读块尽量保真并记录 warning；结构损坏、无可索引正文才阻断。

页码只做一次 `page_idx + 1` 转换；物理页与印刷页分开。此次源 bbox 为页面归一化 xyxy，所有相关 block 应明确 `bbox_space=page`、`bbox_format=xyxy` 和归一化 units；旧格式不能凭猜测改单位。

记录原始 page/block 定位、producer/adapter version；过滤后的序号不能冒充原始 block index。缺失 confidence 保持未知。

原生输入的 source_file、block IDs、Canonical hash 允许与 bridge 不同；要求自身确定性和可追溯性，不伪造旧 ID，不静默重绑旧引用。

## 6. P1：formula/table original visual asset

推荐保留原始视觉资产，同时保留 formula/table 的既有 block_type 和结构化检索语义。

首版建议在 `DocumentBlock.attributes.original_visual_asset` 中定义有版本、可选、被验证的子契约：

- schema/version、role=`original_crop`；
- source 相对路径、稳定资产相对路径；
- SHA-256、实际图像格式、宽高；
- ready/missing/invalid 状态；
- 对应 block/page/bbox 与坐标语义，避免和 block provenance 矛盾。

通过可选子契约保留旧 Canonical 的读取兼容；不要直接提高顶层 schema 使旧 reader 拒绝已有教材。当前 `load_canonical_book()` 对顶层 schema 有精确版本检查。

泛化 materialization，可新增 `ingestion/document_assets.py` 复用现有安全路径、图像检查和原子复制能力。保留 figure 原字段及 `materialize_figure_assets()` 兼容入口。

要求：

1. formula/table 不复制为额外 figure，不增加重复检索证据。
2. 新资产使用受控相对路径、不可变文件名；禁止源/目标路径越界和 symlink 逃逸，不自动下载远程引用。
3. 缺图/坏图时保留可用结构化正文并 warning；ready 却没有合法路径/hash/dimensions 是合同错误。
4. 原图只提供回看和校核依据，不提升数学验证状态；首版不自动注入 LLM prompt。
5. 优先沿 `source_block_ids` 回到 Canonical 解析资产，不无必要地向所有索引和 EvidencePack 层复制完整对象。
6. 现有 backup 包含 progress；补恢复测试确认资产随书保存，不先改全局存储布局。

## 7. P1：发布一致性与数据保护

审计发现：`build_index_from_chapters()` 在 staged index gate 前 materialize 并持久化 Canonical。native adapter 改变 hash/ID 后，同名教材更新失败可能保留旧索引却已替换 Canonical。

因此，正式同名更新上线前须确保 candidate Canonical、报告、资产和索引的一致发布/恢复；测试不能只断言 active map 没变。

先在现有发布边界内设计最小方案：失败时旧版本仍可读、新 candidate 不污染活跃读者、重试幂等、旧资产不被提前删除。若需要超出现有边界的全局版本存储迁移，单独提出具体变更和数据影响，按 AGENTS.md 处理，不能夹带迁移。

在此能力完成前，只允许隔离数据目录或全新教材身份下的 native integration 验收，不覆盖生产教材。仅复制旧文件后在失败时恢复并不足以证明并发读者隔离，需要验证发布期间的可见性。

## 8. 测试与验收

### 8.1 P0 必须独立捕获两个 bug

- Bug #1 helper：同 section 与邻节成员并存时只选同 section；完全没有同 section 成员时保留合法 fallback；前一列表、其他父路径和其他章节不混入。
- Bug #1 integration：污染成员足以占满配额；经过真实 rerank、support gate 和 `build_evidence_pack()` 后，目标成员仍完整，污染内容不出现。不能只检查 debug candidates。
- Bug #2：英文型号只出现在一个成员；其他合法成员仍进入最终 pack；order=0 生效；取消列表身份后普通 literal gate 仍有效。
- 两个 bug 各有最小 fixture，再有组合 fixture，避免一个修复掩盖另一个。
- 负向覆盖：错误型号、相同章节名的其他教材、错误 section、无可信 anchor 的列表标记。
- 保留现有 sibling 恢复、table、formula、teaching、example、continuity 测试。

### 8.2 Adapter / asset 合同

- structured-only 目录可经正式 external importer 导入；不依赖 Markdown、middle 或 bridge 存在。
- 原生与 bridge 共存优先级确定；legacy v1/v2/old-middle/Markdown 不回退。
- 编号层级、非编号标题、局部列表、公式单份正文、captionless figure、chart、表格脚注、物理页/bbox/源定位均有断言。
- 素材目录移动后逻辑结果稳定；重复导入到隔离环境幂等；序列化/reload 保留资产合同。
- 缺图、坏图、路径越界、symlink、无 confidence、无标题表格有明确预期。
- 拆分表格的多个 chunk 均可追溯到同一原 table block/asset。

### 8.3 发布和通用行为

- gate 失败、取消、异常、重试不破坏旧 Canonical/资产/lexical/map；并发读取不混用版本。
- 新版本发布后 source_block_ids 与 Canonical、资产能对应；旧引用不得静默重绑。
- 最终 EvidencePack 覆盖定义、列举、比较、原理解释、推导、应用题和跨章节；不调大预算代替修复。
- example=0 明确报告缺覆盖，使用其他通用 fixture 验证例题路径。

### 8.4 数据和运行范围

默认测试：小型合成 fixture＋两个真实失败点的固定片段，使用 Python 3.10 `venv310`，全部离线；数据库和输出放 tmp_path，不触及生产向量库。

可选完整 integration：native 实现后，对固定归档进行新旧路径差异验收，复用既有 probes。这是验证新增代码，不是重做已完成的服务器探索。不要重新 OCR、生成替代金标、执行付费模型或上传教材。

4911 blocks、1824 文本 chunks、522 formula、28 table、663 figures 是此次 bridge 的冻结基线。native 若因明确的语义改进改变数量，应说明逐项差异及证据；不能直接刷新 expected 或在生产逻辑中硬编码这些数量。

新验收保存 adapter/version、语料 checksum、Canonical fingerprint、index manifest、分 specialty gate 明细及失败恢复结果。不要补造旧服务器的缺失报告。

### 8.5 Electron 验收

使用现有 Books 外部 MinerU 结果导入流程，在隔离桌面数据目录确认：ZIP 上传 → job 进度/错误 → 导入完成 → 章节读取 → 资产持久化；缺原始 PDF 时不伪报 has_pdf。

当前产品入口是 ZIP，handoff `.tar.gz` 只是审计归档。用已保存的 OCR 输出制作测试 ZIP，不为此次归档扩展产品压缩格式。保持 `extract_concepts=False`，避免可选后台模型调用。

本轮不要求新增 formula/table 原图 UI；如现有桌面流程发现必须修复的 UI 问题，先读取 `texa-ui-system` skill，并保护现有未提交 UI 工作。

## 9. 文件清单与提交拆分

| 阶段 | 主要文件 | 预期改动 |
|---|---|---|
| P0 | `graph/retrieval_node.py` | 两个 patch hunk |
| P0 | `tests/test_evidence_support_gate.py`、`tests/test_acceptance_probes.py` | helper 与最终 pack 回归 |
| P1 native | `ingestion/document_adapters.py`、`ingestion/mineru_importer.py` | 原生映射、确定性选择、统一章节投影 |
| P1 contract | `ingestion/document_ir.py`，建议新增 `ingestion/document_assets.py` | optional original visual asset、校验、materialization |
| P1 publish | `ingestion/mineru_importer.py`、`ingestion/index_pipeline.py` | candidate 与活跃数据一致性 |
| P1 tests | 建议新增 `tests/test_mineru_structured_content.py`、`tests/test_document_assets.py`、`tests/fixtures/mineru4/` | 原生与资产合同、小型固定样本 |
| P1 tests | `tests/test_external_mineru_output_import.py`、`tests/test_index_pipeline.py`、现有 figure/provenance/splitter tests | 正式入口、恢复、legacy 兼容 |
| P2 docs | `docs/mineru_deploy.md`、`patch_notes.md` | 使用方式、兼容策略、实测与 bridge 退役 |

`ingestion/chapter_splitter.py`、索引 metadata、`graph/evidence_pack.py` 仅在测试证明现有引用投影不足时修改。`backend/api/books.py` 应继续薄封装；不将 adapter 业务写回 Router。

不因为它们与本任务相邻就修改当前未提交的 `backend/api/figures.py`、`backend/data_backup.py`、`frontend/src/pages/BooksPage.tsx` 等文件。

建议提交顺序：

1. retrieval 两处修复＋独立回归。
2. 资产子契约与 native adapter（必要时拆成两个可验证提交）。
3. 发布一致性与正式入口 integration。
4. Electron 验收记录、文档及临时 bridge 依赖退役。

不为了提交使用 `git add .`。各阶段只纳入自己的明确文件/改动，更新 patch_notes；普通修复不写 AGENTS.md。

## 10. Bridge 退役条件与禁止事项

退役条件：structured-only 导入通过、native 与 bridge 共存选择正确、既有格式兼容通过、两个 list 回归通过、资产持久化和失败恢复通过、隔离 Electron ZIP 流程通过。

满足后移除“必须先转换成 texa_content_list_v1”的操作依赖；不删除旧 content-list 支持，不删除此次归档、bridge 或服务器证据。

禁止：

- 重做 351 页 OCR、schema 探索、章节盘点、服务器公式/figure 验证或重新排查已知两处根因。
- 把教材名、章节号、页码、真实 chunk ID、NK-Humirel/MAC 等答案内容写入生产判断。
- 全局关闭 literal filtering、抬高 EvidencePack 配额、降低 release threshold、删除失败 probes 来通过测试。
- 把自动结构 probes 表述成人工金标或真实模型准确率。
- 将服务器 Python 3.12/CUDA/MinerU 环境迁入 Texa；顺带升级 PyMuPDF、切换 fitz API 或重装依赖。
- 未获授权运行付费 Answer Eval、上传教材或调用外部模型。
- 覆盖生产索引/学习记录、自动迁移旧引用、删除旧资产；把视觉资产扩成新自主 Agent/回答入口。

交付时说明每阶段修改、测试结果、未覆盖项及数据兼容影响。受环境阻塞时准确报告，不把未运行的 integration 或桌面验收写成通过。
