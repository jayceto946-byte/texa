# Visual Design Review Handoff — R1/R2

2026-10-17 · Sol → Astra · **IMPLEMENTED / ENGINEERING VERIFIED / DESIGN APPROVED**

当前主目录 `Texa_MacOS`，HEAD `1824fcc7d7f33c7a08faef9cd285d566f5b3ac79`＋未提交工作区；没有借其他工作区快照运行。最终设计批准由Astra独立作出，限本轮R1/R2视觉集成及下述三个功能例外。

实施依据为 [R1评审](../exercises-visual-validation/design-review-2026-10-16.md)、[R1实施说明](../exercises-visual-validation/sol-handoff-2026-10-16.md)、[R2增补](../exercises-visual-validation/reading-and-copy-r2-2026-10-16.md)。用户的正式授权覆盖旧文档待确认停止点；R2明确修改优先，其余R1仍有效。

## 复审进度

[Astra独立复审报告](./astra-review-2026-10-17.md)保留初审及整改复核。Astra直接检查了初审真实Electron截图，分类为实现偏差、设计缺陷、功能冲突与非阻断优化；Sol按其决定修复并回归。

I1–I4、D1、E2、F1已由Astra关闭。额度恢复后，Astra直接打开最后两张稳定聊天图，确认学习导航正确选中、练习非选中，正文灰化消失，阅读轴线与层级保持，正式关闭E1。**Astra已给出 DESIGN APPROVED；本轮没有剩余视觉设计阻断。** 初审、整改及最终依据保留于独立复审报告。

## Astra已直接复核的最后证据

`artifacts/design/exercises-production-r1-r2/settled-regression/1280-chat-after-exercise.png`

这张图等待了实际“学习”导航is-active、可见聊天工作区、有限动画完成、双rAF和200ms稳定帧，并移开悬停鼠标；没有改共享壳/动画来迎合截图。该组`results.json`记录：route=`/`，activeNavigation=`[学习]`，panelOpacity=`1`，1280×820、fontReady=true；聊天正文A→B→A保持16px / 30.4px。请与同目录`1280-chat-markdown.png`直接比较。

## 各版真实截图

全部为macOS Electron37.10.3＋生产React构建＋隔离内存API样例，不是真实模型或用户生产数据：

| 组 | 用途 | 结论 |
|---|---|---|
| `artifacts/design/exercises-production-r1-r2/final/` | Astra初审76张图 | 保留初始问题，不当作最终批准基准 |
| `…/review-fixes/` | 双尺寸完整整改、长草稿/末端、管理与原图降级，86张 | 133项工程检查通过；Astra已关闭主要阻断 |
| `…/settled-regression/` | 最终聊天稳定图及跨页轻量重验，14张 | 19项检查通过；Astra已直接复核最后对照图并关闭E1 |
| `…/scope/` | 分析中跨页更改全局教材，候选/提交保持原范围 | 4项检查通过 |

重点整改图在`review-fixes/`：两尺寸`source-file`、`file-ready`、`missing-answer`、`zero-candidates`、`commit-unknown`、`saved`、`save-failed`、`practice-ai`、`practice-ai-end`、`mistake-ai-conflict`、`bank-path-only-image`、`bank-management`；手动弹窗`1280-manual-dialog.png`。

## 已由Astra决定的能力例外

1. `/mistakes/explain`直接写入但无CAS/幂等协调，本轮不接入；保留AI状态页签及已保存解析，移除禁用生成按钮，使用“AI讲解暂不可用，已保存解析仍可阅读”。没有解析时显示真实空态。未伪造job/草稿合同或写入成功。
2. 当前题库无题干更新端点；保留题目管理/状态/删除与参考答案编辑，明确“当前题干只读，可编辑参考答案”。不声称题干编辑已完成。
3. path-only原图无可用鉴权读取端点；正文前提示“原图暂不可读取，请对照来源文件”，保留真实来源，不把此降级算作图片支持。既有Markdown图片及错题原图/附件保留。

其它实现差异：原生壳与共享导航沿用现状，候选标题为确定性摘要，模型输出标题不强制包装。保存成功转到参考答案继续阅读，失败/未知保留草稿；普通题库无固定空底栏，三档习题自评与四档错题重做不混同。未改DB/后端解析/Provider/复习Runtime或UI技能。

## 工程验证与限制

前端222、桌面24、后端42项通过；本轮文件lint/TypeScript/Vite通过。Electron核心/异常/跨页验证与最后范围补测通过。完整说明、主要文件及未验证项见[交付报告](./delivery-report.md)。真实模型/OCR、Windows、生产数据、完整打包升级恢复及真人可用性未验。

## 资产及最终批准

[参考登记](./reference-register.json)、[冻结参考包](./reference-r1-r2.zip)、[证据登记](./evidence-register.json)保留版本/页面状态/关键决策/局限/实现差异和SHA256。R1/R2只是本轮实施参考，不能强迫其它页面复制构图，也没有升级成永久全产品视觉权威。

Astra已直接复核上述新稳定图、关闭E1并作出最终DESIGN APPROVED。批准覆盖复审所检查的macOS Electron、隔离固定API样例、相关桌面尺寸与页面状态，以及三个明确接受的能力例外；不扩大为真实模型/OCR质量、生产数据、Windows、完整打包发布/升级恢复或真人可用性批准。工程PASS或Sol阅图不替代设计批准。若要沉淀全局模式，应先证明跨页复用价值，再改共享组件/接口并清理旧规则，不追加无休止Markdown条款。
