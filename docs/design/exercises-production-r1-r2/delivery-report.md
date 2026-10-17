# R1/R2 正式集成交付报告

2026-10-17 · `Texa_MacOS` · HEAD `1824fcc7d7f33c7a08faef9cd285d566f5b3ac79` · 未提交工作区

| 状态 | 结论 |
|---|---|
| IMPLEMENTED | 工程实现完成，含 Astra 明确接受的三项有界能力降级 |
| ENGINEERING VERIFIED | 本轮隔离测试与必要回归通过；不代表真实模型或生产数据验证 |
| DESIGN REVIEW PENDING | 否；Astra 已完成最后稳定截图的独立复核 |
| DESIGN APPROVED | **是**；Astra 直接对照真实 Electron 截图，关闭 E1，本轮视觉阻断全部关闭；范围及例外见复审报告 |

## 完成范围与主要文件

- `frontend/src/pages/ExercisesPage.tsx`：R1 有界准备画布、单一来源表单、高级项、真实回执/精确批次回滚/未知结果栅栏；冻结分析与候选的来源范围，避免跨页全局教材变化后误写。
- `frontend/src/features/exercises/components/CandidateReviewWorkspace.tsx`：索引＋单题正文、选择与导航分开、完整字段编辑、过滤/相邻合并/空行拆分、原文对照、独立滚动与返回保留。
- `frontend/src/features/exercises/components/ExerciseReader.tsx`、`hooks/useExerciseAnswerJob.ts`：题库阅读、练习作答、AI queued/running/completed/failed/unavailable；正式答案与草稿分离，明确保存，失败保稿，断线先查任务，迟到响应隔离，保存成功转入正式答案继续阅读。
- `frontend/src/features/reading/QuestionReadingLayout.tsx`：居中题目最大810px；实际工作区≥992px时40/60；窄窗单层切换并保留输入/滚动。题库无固定空底栏，练习保留自评/继续。
- `frontend/src/pages/MistakesPage.tsx`：只调整详情阅读，保留原图/附件、当时作答、参考答案、错因/修正、来源/标签、历史记录、编辑/CAS、归档恢复/校对/暂缓/手动掌握及既有 ReviewSession 入口。
- `ReadingMarkdown`、`readingMath`、`useUnsavedWorkGuard`、`HelpHint`、本域 CSS：复用正式 Markdown/KaTeX 管线；共享 SimpleMarkdown 仅新增可选 className，默认消费者不改字号。帮助支持悬停/点击/焦点/Escape和边界定位；警告直接可见。草稿退出接现有 Electron 关闭握手。
- `scripts/qa-r1-r2-*.mjs`：隔离内存API、真实 Electron 与可复跑的状态/跨页/范围测试。

未改数据库、解析后端、Provider、复习Runtime、全局壳或UI技能。开始时已有的 AppRail、MainLayout、共享CSS等用户修改保留；本轮未回退、覆盖或提交它们。

## 验证

- 前端：50个文件、222项测试通过；本轮文件 ESLint、TypeScript、Vite生产构建通过。Vite仍提示既有大chunk警告。
- Python：`venv310` / Python3.10.21，exercise bank、mistake lifecycle、mistakes API共42项通过。
- 桌面壳：24项测试通过；临时本机端口测试在允许本机监听后复跑成功。
- 整改后真实 macOS Electron37.10.3：133项检查、86张截图，`review-fixes/results.json`无错误。1280×820、1024×768完整状态，760×820冒烟。
- 追加跨页稳定验证：聊天激活导航为“学习”、主panel opacity=1、双rAF及有限动画结束后截图；默认正文16px/30.4px前后一致。笔记A→B→A、错题编辑/归档恢复、ReviewSession四结果与提交通过。
- 追加范围验证：分析请求中跨页更改全局教材后，候选与最终batch-add仍绑定原教材；通过。

长题、长AI推导、矩阵、缺答案、图片、生成中、明确失败、断线、保存未确认、未保存稿、跨题/跨页、200候选、零候选、未知入库结果、真实batch_id与回滚均有对应固定样例证据。文件选择/解析界面使用合成夹具；未把它称为真实Word/PDF解析或真实模型验证。

## 设计闭环与明确例外

[Astra复审](./astra-review-2026-10-17.md)已独立检查初审76张Electron图及9张R1/R2基准，并完成整改复核及最后两张稳定聊天图的直接对照。其阻断已按指定方向整改：文件页首屏、空答案、零候选、未知回执、保存后阅读连续性、长练习草稿/自评及状态文案。保存失败仍保留编辑；主操作不遮正文。额度恢复后的最终复核确认导航与正文正常，E1正式关闭，由Astra给出本轮 DESIGN APPROVED。

Astra 已接受本轮三个例外，**不是这些能力已完成**：

1. 错题AI暂不接入不具CAS/幂等合同的直接写入接口；保留AI状态页签和已保存解析，移除不可执行生成按钮。
2. 题库题干只读，保留题目管理与答案编辑；未伪造题干修改端点。
3. 题库path-only原图明确提示不可读取并保留来源；不把它计为图片支持。Markdown图片、错题原图/附件既有能力保留。

Windows、真实付费模型/OCR、用户生产数据、完整打包升级/恢复及真实使用者验证未运行。非阻断草稿文案合并、未配置模型下一步等保留在复审报告，不扩大本轮范围。

## 证据与资产

- [视觉复审交接](./visual-design-review-handoff.md)
- [页面状态截图索引](./screenshots.md)与[证据登记](./evidence-register.json)：每组截图、代码/构建身份、SHA256及阶段结论
- [R1/R2参考登记](./reference-register.json)与[冻结参考包](./reference-r1-r2.zip)：75个原型、截图和决策文件；只适用于本轮
- [Electron证据归档](./electron-evidence-r1-r2.zip)：保留初审、整改与追加稳定/范围证据，不混成一批已批准基准

资产未升级为全产品视觉权威，未重写texa-ui-system。后续仅在实现与独立复审证实可复用后沉淀共享组件，并清理被替代的旧规则。

Git：所有本轮修改及证据登记留在当前Texa_MacOS工作区，未创建提交/PR；已有用户修改仍在。无需从其他工作区运行快照。
