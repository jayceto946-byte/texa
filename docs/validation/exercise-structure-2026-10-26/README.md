# 教材例题、讲义与习题册结构提取

2026-10-26 开始，2026-10-27 完成；主目录 `Texa_MacOS`。提交前的干净副本复验见 [commit-verification.md](commit-verification.md)。

## 先核实的事实

- “教材例题完全不能抽解答”不准确。10 月 18 日的 v1 合同已经支持独立、明确解答块；冻结的 14 条带解例题中有 9 条分离提案，另 5 条 unresolved。表格、图片和边界问题独立存在，分离不代表整题可交付。
- 本轮修复前，直接文件导入默认规则会把 `题干\n解：原过程` 整体放进 question_text，answer/explanation 均空，已在 Python 3.10 实际复现。
- 同块题解对应冻结 R12；原 v1 会保留 unresolved。无标记解答、原文跨节和缺必要图片也有独立缺口。
- 原独立答案匹配只用题号，字典最后一次覆盖相同号码。题号重复会误配；没有章节、编排号的唯一性合同。

## 实施方案与范围

通过共享来源投影完成识别、校对和入库，继续保留全局 Canonical / LearningUnit 的阅读与检索合同。没有新增每书 Python 适配器，没有数据库迁移、生产重导或索引切换。

1. `memory/exercise_structure.py` 识别通用编号、编排栏、显式考点、分类标题和明确解答标记。编排号优先于条目内的原卷题号；允许重复、跳号，不用题号做系统主键。标题栏被拆成相邻块时，利用文字和可用的同排位置继续组合；原始层级只是候选信号。
2. `exercise_candidate_projection.py` 以 Unicode span 分配题干、答案、解析、旁文。支持同块内明确分界、独立解答块及 bracket/colon 标签。`解`归解析，不凭空生成最终简答。已知分离可与未解决边界共存：显示源解提案，同时保留 unresolved 和准入门槛。
3. `exercise_file_analysis.py` 为新文件分析保存独立、带完整性摘要的来源快照。MinerU 的公式、表格、图片块不再先全部展平成纯文本；文本 PDF 保留物理页与块位置，行投影记录原块及字符位置，不能把粗块框当成精确行框。DOCX 页码不可得时保持未知。
4. 题后答案、同文档集中答案区及独立答案文件共享投影。分离答案表按分类范围与编排号/原卷号的唯一身份匹配；重号歧义、缺对应身份或已有源解时不覆盖。未匹配答案保留在整批原文对照中，供人工核对。
5. 候选合同增加编排号、原卷号、编者考点、出处、分类路径、样例版本和文件来源身份。服务端重放来源，拒绝伪造字段、跨题库来源及过期确认。不同明确编排号或不同编者考点不合并。
6. 新入库题在既有 JSON 扩展字段中保留 source_structure，可按考点、编排号或分类路径搜索。重复题的本次来源关联保存在 skipped_candidate_receipts；旧题正文与确认状态不修改。批次回执仍与入库原子提交。
7. 校对工作区允许在原文中放置光标，把本块后缀分配为题干、答案、解析或旁文。保留源字符覆盖，重新生成正文并使旧确认失效；缺图与前例输入门槛继续执行。
8. 明确确认后可“记住本题分离方式”。服务端先验证候选及原文对齐，再保存受限字面标签样例；原子发布版本化本地配置。后续资料复用时仍需核对，不自动成为已确认题或数学金标。旧分析绑定旧配置，后续保存不改变旧回放结果。

## 学习能力的实际边界

本轮实现的是**显式确认的分离标签样例复用**，例如把“演算过程：”确认为解析标题后，在另一份资料中提出分离建议。没有训练模型，没有开放式 Agent，也没有实现任意版式的端到端语义学习。普通“分析：”可能是作答要求，基础规则不自动把它当作源解，可在校对后另存样例。

编号和层级仍依赖可见文字、原始类型与位置。未知标题、没有明确标记的解答、复杂多栏/跨页和错误 OCR 仍可能需要人工调整。没有为本书加入专属适配层，也不承诺新资料零校对。图中 #047 的版式和标签被用于合成结构样例，题干与答案不是原卷 OCR 金标。

新 UI 的文件导入使用来源合同，文字自由重写修复不再作为此流程的开关；旧 API 的 legacy 模型修复入口保留，不能声称拥有新来源保证。默认流程没有新增模型费用或外发。

## 验证

| 范围 | 结果与口径 |
|---|---|
| 修复前基线 | 相关旧后端 59 项通过；另实际复现直接文件路径题解混排，不能用通过数掩盖功能缺口 |
| Python 3.10.21 / venv310 | 137 项通过：新结构/文件 API、原候选合同、题库、知识关联、教材抽题、工作流、DocumentAdapter 与原生 MinerU 合同 |
| 前端 | 55 文件、256 项通过；本轮修改文件 ESLint、TypeScript/Vite 构建通过；既有大 chunk 提示仍在 |
| 冻结 108 条教材候选 | 原 92 条结构可用题均保留；16 条重复题干身份保留；96 条无需额外内容处理的候选通过服务端重放。源 IR、源数据及旧审计文件 hash 不变 |
| 带解例题的当前输出 | 13/14 有非空源解提案，其中 C091/C092/C093/C096 仍 unresolved；9 条明确分离、5 条未解决的状态分布保持。原必要输入与边界门槛未取消，不能把 13 当成功率 |
| 新文件流程实际 Electron | 三尺寸 1280×820、1024×768、760×820；37 检查、10 图、0 renderer 异常。真实 DOCX 上传/解析、#047 与原卷 (12)、原文光标分界、显式确认、保存样例、另一份资料复用、准入与临时 SQLite 回执 |
| 原教材流程实际 Electron | 三尺寸；65 检查、21 图、0 renderer 异常。来源、长式/表格、编辑失效、缺图/跨节、子集入库、旧接口拒绝、回执不完整、断线无自动重发与历史正文变化 |

结构回归：[corpus-regression.json](corpus-regression.json)。桌面脱敏结果与截图身份见 `verification.json`。截图已实际查看，属于工程视觉核对，未声称新的独立设计批准。

**未验证：** 本次没有从真实扫描习题册重新跑 MinerU OCR，没有完整原 PDF 的逐题人工金标，没有真实答案正确性评估、Windows 实测或安装包升级恢复。已有 MinerU 结果回归与合成结构测试不能替代这些验证。本机 venv310 未发现 MinerU 可执行入口，本轮未调用外部 OCR/模型服务。

## 数据与兼容

- 来源快照：`PROGRESS_PATH/exercise_import_sources/`；校对样例、不可变配置版本和确认记录：`PROGRESS_PATH/exercise_structure_examples/`。均为新增本地 JSON，不迁移旧数据库。既有备份的 progress 根覆盖这些文件。
- 确认针对当前正文、来源映射及版本；教材或文件来源丢失/变化时拒绝静默重绑。重分析不会自动写题库，保存样例不改旧候选或生产索引。
- 若回退源码，新 JSON 为可选扩展；不要删除其来源文件。旧题不会自动补出新的分类或题解，需要用户主动重新分析并校对。
- 验证时保留其他任务的未提交差异，未调整本地提交保护。本次提交仅包含习题结构提取及其校对、测试与验收材料。

## 复跑

```sh
venv310/bin/python -m pytest -q tests/test_exercise_structure_import.py tests/test_exercise_candidate_contract.py tests/test_exercise_importer.py tests/test_exercise_file_importer.py tests/test_textbook_exercise_importer.py tests/test_textbook_workflow_repairs.py tests/test_exercise_bank.py tests/test_exercise_knowledge_structure.py tests/test_document_adapters.py tests/test_mineru_structured_content.py
venv310/bin/python scripts/evaluate_exercise_structure.py
cd frontend
npm test
npm run build
```

Electron 在仓库根执行 `node scripts/qa-exercise-structure-electron.mjs` 与 `node scripts/qa-question-candidate-electron.mjs`，需要已存在的 Playwright 依赖和本机回环监听权限；使用独立 userData、来源副本和临时数据库。
