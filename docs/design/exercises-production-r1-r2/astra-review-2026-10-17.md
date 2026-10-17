# Astra 独立视觉复审：R1/R2 正式集成

2026-10-17 · Principal Product Designer · 初审：**CHANGES REQUIRED / DESIGN NOT APPROVED**

**最终状态：DESIGN APPROVED。** 初审与整改记录保留如下；批准范围及 E1 最终关闭依据见文末“最终独立复核”。

核心构图符合本轮 R1/R2 方向，可以继续局部整改，不需要第三套设计。以下阻断项关闭并由 Astra 直接复核更新后的 Electron 截图之前，工程测试通过不能改称 DESIGN APPROVED。

## 依据与范围

已阅读 AGENTS.md、[Texa UI 技能](../../../.agents/skills/texa-ui-system/SKILL.md)、其 learning-canvas/states 参考、[R1 设计评审](../exercises-visual-validation/design-review-2026-10-16.md)、[Sol 实施说明](../exercises-visual-validation/sol-handoff-2026-10-16.md)、[R2 增补](../exercises-visual-validation/reading-and-copy-r2-2026-10-16.md)及[生产交接](./visual-design-review-handoff.md)。本轮正式实施已获用户授权，旧文档中的待确认停止点不适用；R2 仅覆盖其明确替代的 R1 决策。

本次用 `view_image` 逐张直接检查下列真实 Electron PNG；没有以测试结果、源码或原型代替画面判断。证据目录：[final](../../../artifacts/design/exercises-production-r1-r2/final/)。环境是 macOS Electron 37.10.3、生产 React 构建、隔离固定 API 样例、mineral 主题、字体已就绪；HEAD 为 `1824fcc7d7f33c7a08faef9cd285d566f5b3ac79`，含未提交工作区改动。`final/results.json` 的 `errors` 为空；交接中的“重跑中”属于过期描述。数据/模型内容均为样例，不能推导真实模型、OCR、Windows 或完整打包发布结论。

直接检查路径清单（以下名称均相对 `artifacts/design/exercises-production-r1-r2/final/`）：

- `1280-` 和 `1024-` 两种前缀，各配以下 `.png`：`preparation`、`help`、`source-textbook`、`source-file`、`candidates`、`candidate-edit`、`source-compare`、`receipt`、`bank-reading`、`bank-generating`、`bank-ai`、`save-failed`、`saved`、`practice-reading`、`practice-ai`、`practice-return`、`mistake-reading`、`mistake-reference`、`mistake-ai-conflict`、`mistake-edit`、`matrix-reading`、`missing-answer`、`ai-failed`、`ai-disconnected`、`ai-recovered`、`analyzing`、`analyze-failed`、`zero-candidates`、`200-candidates`、`commit-unknown`、`image-question`、`empty`、`overview-error`。
- 1280 补充：`1280-manual-dialog.png`、`1280-chat-markdown.png`、`1280-chat-after-exercise.png`、`1280-note-reading.png`、`1280-mistake-archived.png`、`1280-review-four-results.png`、`1280-review-complete.png`。
- 760 补充：`760-preparation.png`、`760-bank-reading.png`、`760-bank-reference.png`。

直接打开比较的基准位于 `artifacts/design/exercises-validation/screenshots/`：`r2/1280-bank-ai.jpg`、`r2/1024-exercise-ai.jpg`、`r2/1280-bank-reading.jpg`、`r2/1280-practice.jpg`、`r2/1024-import.jpg`、`r2/1280-mistake-ai.jpg`、`r2/1024-review.jpg`、`1280-review.jpg`、`1024-file-ready.jpg`。原型与正式截图数据不一致，不声称严格同数据像素 A/B。

## 已成立的设计

准备页形成范围→题量→顺序→开始的清晰主轴，资源摘要处于次级；空库与读取失败有不同状态。教材/文件来源互斥，校对采用索引加单文档，原文宽窗对照、窄窗切换，没有永久第三列。长题、矩阵、200 候选的主体宽度和固定提交栏成立。

题库、练习、错题阅读保持同一阅读尺度和不同领域操作。1280 下实际工作区 1048px 采用约 40/60 分栏；1024 下 816px 使用单层页签。普通题库没有固定空底栏，练习自评与保存题库答案分开，错题重做仍保留四结果语义。760 题库阅读可用，未见整页横向溢出。现有图片读取的错题样例能在题目区域展示原图。

本轮不审改用户已有 AppRail、MainLayout 或共享 CSS，不把原型外壳与当前壳的差异当作本任务缺陷。

## 阻断与具体验收

P2 表示本轮必须修正的中等严重程度问题；不是数据破坏等级。E 项属于证据缺口，未确认前不能用猜测归因给实现。

| ID / 分类 | 严重程度 | 直接证据与发现 | 修正方向与验收 |
|---|---|---|---|
| I1 实现偏差：文件页首屏 | P2 / 阻断 | `1024-source-file.png` 的“分析文件”位于约 y740–768，贴底且下缘裁切；基础表单没有展开高级项仍需要滚动才能舒适操作。 | 恢复 R1 文件就绪/渐进展开关系：来源名、章节归高级项，已选文件改为紧凑行，局部收紧间距；保留直接可见 OCR 限制。双尺寸初始与文件已选态主操作完整可见，1024 下有明确底部余量，不缩小题干或改全局壳。 |
| I2 实现偏差：空答案状态矛盾 | P2 / 阻断 | 两尺寸 `missing-answer.png` 同时显示“已保存参考答案”与“暂无参考答案”。 | 仅实际有答案时显示已保存身份；空态用“暂无参考答案”，可继续提示 AI 草稿入口。双尺寸截图无相互矛盾状态。 |
| I3 实现偏差：零候选误报 | P2 / 阻断 | 两尺寸 `zero-candidates.png` 中没有候选，却显示“已抽取候选，请校对”。 | 基于候选实际数量显示“未找到候选题，请调整范围后重试。”，保留真实警告与可用原文。修正 fixture 的不实提示也不能替代前端正确的零结果身份。 |
| I4 实现偏差：未知回执操作顺序 | P2 / 阻断 | 两尺寸 `commit-unknown.png` 的唯一蓝色主操作为“准备练习”；“读取批次供核对”挤到下一行并紧贴上方按钮，未体现先核对的任务顺序。 | 主按钮改为“核对导入批次”，查看题库次级，准备练习移为文字次级或去掉。操作同组对齐且留 8–12px 间距，窄窗自然换行；不改 unknown 栅栏、不自动重发，不宣称核对能无身份自动确定成功。 |
| D1 设计缺陷：保存后阅读断裂 | P2 / 阻断，Astra 定方向 | 两尺寸 `saved.png` 在成功保存后清空解答正文，AI 栏回到“生成后可阅读…”的空态。用户刚保存的学习内容从当前阅读面消失。 | 成功回执后切至“参考答案”，立即展示刚保存的正式答案；这是首选局部实现。也可保持正文并显示已保存身份，但不能留空生成面。失败/未知必须保留草稿及所在区域。补双尺寸成功截图及失败不切区结果。 |
| E1 证据：选中状态与动画 | P2 / 证据阻断 | 两尺寸 `source-file.png` 文件表单上仍是教材页签蓝色；`mistake-ai-conflict.png` 中参考/AI 两个下划线同时出现。`1280-manual-dialog.png` 可透视背景文字，`1280-chat-after-exercise.png` 处于灰化帧。 | 先在真实渲染稳定后重截并断言当前状态，仅在稳定后仍错误时改本域实现。截图捕获可禁用有限动画，不能为截图改产品配色或共享动效。稳定截图只能有一个选中页签，弹窗/正文恢复正常最终透明度。 |
| E2 证据：练习长解答与降级 | P2 / 证据阻断 | `practice-ai.png` 两尺寸都是未生成空态，尚不能证明长草稿与练习自评底栏共存；题库 path-only 原图降级与展开题目管理尚未在本轮截图直接展示。 | 补双尺寸实际长草稿+自评底栏、末尾可达及窄区切换保留作答；补题目管理展开及 path-only 图片提示截图。不能用题库长解答代替练习组合状态。 |
| F1 功能冲突呈现 | P2 / 当前呈现阻断 | `mistake-ai-conflict.png` 的长技术警告与无可执行路径的禁用生成按钮占据正文上方，违背 R2 文案收敛。 | 按下节的有界降级实施，双尺寸重新检查；接受暂不接入 API，不接受把后端工程原因作为学习流程主体。 |

## 三个功能冲突的正式设计决定

**F1 错题 AI 直接写入：接受本轮不接入，修改降级呈现后不阻断。** `/mistakes/explain` 缺少 revision/CAS 与 operation_id/幂等协调，本轮不授权后端、数据库或 Runtime 迁移。保留“AI 讲解”页签作为可发现的状态入口；移除禁用的“生成讲解并保存”按钮。顶部直接用一句“AI 讲解暂不可用，已保存解析仍可阅读。”，下面紧接“已保存解析”和内容；没有解析时写“暂无已保存解析。”。不呈现接口、版本冲突、重复请求保护等术语，不伪造后台 job、草稿、恢复或成功写入。技术根因保留在交接文档。

**F2 题干不可编辑：接受“题目管理”替代本轮原型中的“编辑题目”，不阻断。** 现有 API 和旧详情都不支持题干写回；管理区保留真实状态/删除能力，短句为“当前题干只读，可编辑参考答案。”，答案编辑保留在答案区域。不增加不可兑现的题干编辑按钮，不用删除重建伪装编辑。这是限定本轮能力的设计例外，不代表题干编辑需求完成。

**F3 题库 path-only 原图：接受明确不可读例外，不阻断本轮视觉集成。** 在题目正文前直接显示“原图暂不可读取，请对照来源文件。”，保留实际来源可供识别；不得把本地路径直接拼成不鉴权读取，不伪造图片或来源。Markdown 已可读取图片、错题既有原图/附件能力继续保留。此例外不能被表述为题库 path-only 图片支持已完成；本轮 `image-question.png` 只证明错题既有图片路径的呈现。

以上三个决定均在既有授权范围内作局部呈现降级，不要求用户再次确认，不扩展后端范围。

## 非阻断优化

| ID | 观察 | 后续方向 |
|---|---|---|
| N1 示例摘要 | `preparation.png` 的题目示例把公式删除成“设函数 。……替换为 ，……结果为 。”，可扫读信息减弱。 | 用已有确定性摘要能力保留短公式，或用“公式”占位；不新增模型摘要，不修改题目原文。 |
| N2 草稿文案 | AI 草稿同时出现“答案草稿已生成，保存后才写入题库”与“未保存草稿·仅在当前页面内存中保留”。 | 可合并为紧邻保存的状态，并用用户语言表达离开/重启的实际风险；不删除必要未保存状态，也不暗示自动保存。 |
| N3 保存错误显著性 | `save-failed.png` 的“保存未确认”处在普通灰色说明层，虽在编辑器旁可见，但易略过。 | 可使用本域紧凑警示样式；保留“未确认”与“失败”的区别，不因视觉强化而自动重试。 |
| N4 模型未配置 | `ai-failed.png` 已显示未配置，但下一步仍为“生成解答”。 | 可在该确切状态提供去配置或明确重试前提的入口；不要从任意错误文本推断配置问题。 |

## 整改复核合同

Sol 可自主修复 I 项并执行 D1/F1 既定方向，无须阶段性请示。更新证据写入 `artifacts/design/exercises-production-r1-r2/review-fixes/`，保留 `final/` 作为初审证据。Astra 后续只需直接打开对应更新截图，核对 I1–I4、D1、E1–E2、F1 关闭情况及三个功能例外；无新证据说明的情况下不重新开启已通过核心构图。

更新包需保留真实 Electron/字体/视口/代码身份记录、针对性回归结果。共享 Markdown A→B→A 的 16px/30.4px 结果属于工程防回归证据；视觉批准仍须独立作出。未运行真实模型、真实 OCR、真实用户数据或 Windows，不因本轮截图合格扩大结论。

**初审状态：核心构图成立；存在阻断，尚未 DESIGN APPROVED。** R1/R2 及本文件仅作为本轮版本化设计决策，不成为全产品永久视觉权威，不修改 UI 技能。

## 整改复核（2026-10-17）

已直接打开 `artifacts/design/exercises-production-r1-r2/review-fixes/` 的 26 张对应 PNG：双尺寸 `source-file`、`file-ready`、`missing-answer`、`zero-candidates`、`commit-unknown`、`saved`、`save-failed`、`practice-ai`、`practice-ai-end`、`mistake-ai-conflict`、`bank-path-only-image`、`bank-management`，以及 `1280-manual-dialog.png`、`1280-chat-after-exercise.png`。已读取该目录 `results.json`：133 项检查、86 张截图、`errors=[]`，环境与初审相同。

I1–I4、D1、E2、F1 已关闭：文件初始/就绪主操作完整可见且有余量；空答案/零候选身份准确；未知回执以核对为主；成功保存转参考答案并保留正式正文，保存未确认仍保留编辑；长草稿末尾和重新生成在自评栏上方可达；三个功能冲突按既定短句及真实能力呈现。N3 保存错误显著性也已改善。

E1 的来源/解答页签与手动弹窗证据已关闭。聊天返回图仍灰化，左侧“练习”保持蓝色、“学习”为悬停态；仅禁用有限动画尚未证明该画面最终落稳。已要求只补一张路由与布局状态稳定的聊天返回截图，不要求改共享壳。此单项关闭前，最终批准继续待定。

## 最终独立复核（2026-10-17）

Astra 已重新阅读最新交接与本报告，并用 `view_image` 直接打开以下两张实际 Electron PNG，仅复核剩余 E1：

- [聊天返回稳定图](../../../artifacts/design/exercises-production-r1-r2/settled-regression/1280-chat-after-exercise.png)
- [聊天进入前对照图](../../../artifacts/design/exercises-production-r1-r2/settled-regression/1280-chat-markdown.png)

直接画面判断：返回后的“学习”导航明确选中，“练习”已恢复非选中状态；正文、公式、表格和输入区不再整体灰化，文字对比度及阅读层级恢复正常。前后截图的正文轴线、内容宽度、标题与正文的层级关系一致，公式清晰，输入区没有新增遮挡。两图处于不同正文滚动位置，因此此判断是阅读呈现及状态防回归检查，不是逐像素或同段落 A/B。无需修改共享壳、全局字体或动效。

**E1 正式关闭。** 加上已关闭的 I1–I4、D1、E2、F1，本轮没有剩余视觉设计阻断。这个决定来自 Astra 对实际图像的独立检查，不由 Sol 阅图、工程 PASS 或截图元信息替代。

**最终决定：DESIGN APPROVED — 限本轮 R1/R2 React/Electron 视觉集成及三个明确接受的功能例外。** 错题 AI 生成暂不接入、题库题干只读、题库 path-only 原图不可读取的能力边界继续有效；批准其真实降级呈现，不表示这三项功能已经实现。N 类未完成项仍为非阻断优化，不扩大本轮改动范围。

批准覆盖本报告及整改包所检查的 macOS Electron 37.10.3、隔离固定 API 样例、相关桌面尺寸与页面状态；不扩大为真实模型/OCR质量、用户生产数据、Windows、完整打包发布/升级恢复或真人可用性批准。R1/R2 仍是本轮版本化参考，不成为永久全产品视觉权威。本次最终复核只更新本文，未修改产品代码。
