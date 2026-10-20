# Claude UI 源码研究与 Texa 小范围验证

2026-10-19。结论：**输入工具的状态与菜单键盘行为有可复现的改善；没有证据支持全局改版。** 本文研究、映射与截图均对应当前 `Texa_MacOS` 工作树（起始 HEAD `1dc9adce`，含已有未提交改动）。

## 1. 研究证据的边界

- 参考仓库在 Texa 之外：`/private/tmp/texa-open-claude-ui-study`，detached HEAD 固定为 [`4045ce76afdcb7dccef1b7e6417b04c4c6046e9c`](https://github.com/Caho1/open-claude-ui/tree/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c)，提交时间 2026-10-19 14:43:54 +08:00。没有安装、导入其组件库，没有复制其 Agent 指令或品牌资产。
- 阅读了 AGENTS.md、v1 手册的令牌/控件/会话/动效/桌面键盘章节及 v2 版本边界、密度对照；交叉检查 `code-examples`、`cds-theme.css`、`ClaudeMotionPresets.ts` 和仓库内 HTML Storybook。
- [线上预览](https://claude-storybook.bystanderss.chatgpt.site/)在独立 Chrome 临时环境只读查看；[原图](../qa/ui-source-study-2026-10-19/reference/storybook.png)、[焦点](../qa/ui-source-study-2026-10-19/reference/storybook-focus.png)、[分段选择](../qa/ui-source-study-2026-10-19/reference/storybook-segmented-selected.png)、[活跃折叠区](../qa/ui-source-study-2026-10-19/reference/storybook-thinking-active.png)、[弹簧演示](../qa/ui-source-study-2026-10-19/reference/storybook-springs-triggered.png)。实际切换了分段项、思考完成/运行状态并触发弹簧演示；没有向外部页面输入或提交学习内容。线上部署没有可核验的 commit 身份，不能视为固定源码版本的运行验收。
- 以下“实现”仅表示公开仓库确实写了什么；“作者解释”来自逆向手册；“判断”是对 Texa 的设计推论。没有拿到可独立复核的 Claude 官方原始包和运行跟踪，不能背书“100% Fidelity”“全部生产验证”等宣传。

### 已发现的证据冲突

| 位置 | 实际差异 | 对研究的影响 |
|---|---|---|
| AGENTS.md 动效表 vs `ClaudeMotionPresets.ts:61–99` | 文档 SNAPPY 为 600/30/0.6，代码为 320/28/1；代码 GENTLE 为 380/18/1，注释称约 19.4% 超调 | 不能按名字或表格直接采用；参数、运动距离、载体都要实测。HEAVY 的实际阻尼比约 3.65，也不同于 Agent 表的 1.826 |
| v2 密度手册 vs `ChatComposer.tsx:99`、线上预览 | 手册为 12/14px；组件和预览仍为 20px | 是不同版本/示例，不能拼成一套统一规范；Texa 无需更换现有 5px 外框 |
| `ConfirmationDialog.tsx:58–99` | 注释称 focus trap；实现只有 Escape、overlay click 和 dialog role，未见 Tab trap/焦点恢复 | 不迁入；Texa 现有 `components/ui/Dialog.tsx` 已有这些能力 |
| 仓库 HTML Storybook `:1781–1792` vs `ChatComposer.tsx:77–87` | HTML 的 Enter handler 无 IME 守卫；React 组件有 | 演示看起来正常并不代表边界行为可靠；保留 Texa 原有 `isComposing/keyCode 229` |
| 线上 Composer 的 Add content | 点击后仅观察到按钮状态变化，没有展开仓库示例中的附件菜单 | 截图只能证明按钮反馈，不能证明完整附件工作流；线上与仓库 HTML 也不是同一个演示实现 |

## 2. 能复用的具体机制

下面源码链接均锁定上述提交；用途解释是本次判断，作者动机另行标明。

| 机制与源码 | 解决的问题、布局与独立状态 | Texa 可复用经验与限制 |
|---|---|---|
| [Composer](https://github.com/Caho1/open-claude-ui/blob/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c/code-examples/ChatComposer.tsx#L98-L156)：附件、文本域、工具栏三层 | 文本增长不挤走发送操作；`field-sizing: content` 加 min/max height，把短问句与长问题放在同一容器。空白禁用、输入焦点、附件移除、弹出菜单各有状态 | Texa 已有同样的三层结构和 JS 限高，没必要换成原生 field-sizing 或抽一个新 Composer。数学公式和图片区域是 Texa 必须保留的额外层 |
| [CdsButton](https://github.com/Caho1/open-claude-ui/blob/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c/code-examples/CdsButton.tsx#L28-L138)：size × variant × loading，paint 层与内容分开 | 固定几何避免 hover 边框/加载图标引起跳动；次操作低对比、主动作实底，独立处理 disabled/focus/pressed/loading | 采用“状态不改变控件占位”和“嵌套工具少一层边框”。Texa 当前不需要 paint DOM 或新的 Button 抽象；“所有嵌套控件不得有边框”过于绝对，输入框、危险操作仍可能需要边界 |
| [theme CSS](https://github.com/Caho1/open-claude-ui/blob/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c/code-examples/cds-theme.css#L85-L127)、`:205–213,249–257,360–362` | 表面、边界和浮层阴影分角色；CJK 回退与等宽数字处理混合语言和动态计数；DPR hairline 改变光学重量 | 用 Texa 的 `workspace-canvas/tray/separator`，不搬灰阶和字号。计时器已 tabular-nums。发丝边在中文小字、低对比屏幕上未必更清晰；不能因为作者称 OLED 改善就当成测量结论 |
| [MessageBubbles](https://github.com/Caho1/open-claude-ui/blob/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c/code-examples/ChatMessageBubbles.tsx#L77)、v1 手册 §3.1 | 用户问题与助手正文不同结构，长提问可折叠；正文、卡片和代码块分别控制缩进，避免层层 padding 缩窄阅读列 | Texa 学习问题是文档标题、回答是连续阅读画布，本已适合教材推导；不换成 Claude 聊天气泡。正文/公式/来源维持同轴，内部面板只在承担局部任务时出现 |
| [Roving focus](https://github.com/Caho1/open-claude-ui/blob/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c/code-examples/useClaudeRovingFocus.ts#L21-L85)、[SegmentedControl](https://github.com/Caho1/open-claude-ui/blob/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c/code-examples/SegmentedControl.tsx#L40) | 漫游用一个 Tab 入口，方向键/Home/End 在组内移动，Tab 退出；分段滑块把“当前项”作为独立视觉层 | Texa `SelectionControls` 已支持选择与方向键；Composer 菜单却缺失，适合小改补齐。参考 hook 不处理禁用项，SegmentedControl 也没接入它，不能宣称整库已完成键盘支持。Texa 菜单独立过滤禁用项 |
| [ContainerResponsiveBar](https://github.com/Caho1/open-claude-ui/blob/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c/code-examples/ContainerResponsiveBar.tsx#L13) | 依据容器宽度缩短信息、保留图标和主操作；`min-w-0 + truncate + shrink-0` 避免长模型名挤掉动作 | 有 Inspector 时页面总宽不等于内容宽。Texa `QuestionReadingLayout` 已用 ResizeObserver 按容器切换双栏/单栏；优先复用，不能搬 576/480/384/320 的断点或随意隐藏必要教材条件 |
| [scroll pinning](https://github.com/Caho1/open-claude-ui/blob/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c/code-examples/useClaudeScrollPinning.ts#L14-L65) | 用户滚轮/触摸后释放跟随，150ms cooldown 阻止流式 token 抢回滚动；距离底部与返回最新入口分开 | Texa `useReadingScroll` 已区分跟随、历史锚点和历史补页；应对真实 SSE 检查滚轮竞态，再决定是否补冷却。不能直接换 hook，否则会丢历史定位语义；本轮未改、未把等待中的 SSE 当成完整 token 流验收 |
| [Motion presets](https://github.com/Caho1/open-claude-ui/blob/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c/code-examples/ClaudeMotionPresets.ts#L25-L111)、[ThinkingAccordion](https://github.com/Caho1/open-claude-ui/blob/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c/code-examples/ThinkingAccordion.tsx#L46) | 用二阶阻尼区分按压、卡片展开、面板吸附；活跃状态与用户折叠偏好分开。作者称其模拟真实物理 | 可学“状态与转场分离”，不能据此加弹簧库。Texa 已有 90/170/200ms 与 reduced-motion；本试点无需新动效。不引入模糊逐字显现或思考正文，公式需即时可读，thinking 仍必须过滤 |
| [AttachmentCard](https://github.com/Caho1/open-claude-ui/blob/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c/code-examples/AttachmentCard.tsx#L20)、[MCP card](https://github.com/Caho1/open-claude-ui/blob/4045ce76afdcb7dccef1b7e6417b04c4c6046e9c/code-examples/McpToolDecisionCard.tsx#L54) | 附件把类型、名称、上传状态、移除分开；工具卡把待审批、运行、成功/失败与输入详情分开 | 可复用信息顺序和显式状态。MCP 示例是客户端 setTimeout 模拟成功，“始终允许”和本地状态机不适合 Texa；必须保留后端 pending action/回执权威，工具成功不能暗示答案已验证 |

## 3. 对 Texa 当前实现的映射

现有权威：`.agents/skills/texa-ui-system` 与批准截图；`ApprovedWorkspace.css` 负责共享角色，`StudyDesk.css` 保留原学习/教材实现，`theme.ts` 保留主题身份。当前共享规格是正文 16px/1.9、阅读宽 740px、接口 13px、辅助 12px、元数据 11px、桌面控件 28px、发送 30px；部分控件仍被 `index.css`、页面规则叠加，检查必须读取 computed style，不能只看第一处声明。

| 流程 / 当前源码 | 当前事实或问题 | 值得采用 / 适配方式 | 不采用或待验证；组件/依赖判断 |
|---|---|---|---|
| 学习问答：`pages/ChatPage.tsx`、`chat/ComposerOverflowMenu.tsx`、`features/chat/useReadingScroll.ts` | 阅读轴线、输入限高、IME 守卫已有；菜单焦点和首尾导航缺失，禁用工具仍有 hover 边框 | **本轮采用**：补菜单完整键盘行为，低层工具只用填充反馈，禁用项不高亮 | 不换气泡、布局、品牌、字体；流式滚动竞态留真实 delta 测试。现有组件小改足够 |
| 题目导入：`features/exercises/components/CandidateReviewWorkspace.tsx` | 已有来源—校对—入库阶段，原文对照与候选阅读；内容 warning、属性与版本确认同时出现 | **值得采用**：沿用题干优先、动作稳定、细节局部展开；按“当前需处理项”组织真实信号 | 不能照搬普通附件即上传成功；缺图、来源和人工校对是业务条件。较长中文 warning 的密度需专项截图；不加通用 Stepper 或上传库 |
| 练习准备：`pages/ExercisesPage.tsx:573–612` | 已有范围、题量、顺序与一个开始动作；`SelectionControls` 已支持方向键 | **保留**现有分段器与准备流程，统一已选/焦点/禁用视觉，不追加说明卡 | 不引入 Claude 分段滑块；均分指示器对中文长标签未必合适。本轮不改已有待审查的练习页面 |
| 笔记编辑：`features/notes/DraftWorkspace.tsx`、`NoteBlocks.tsx` | 草稿保存与正式保存分开；编辑块有边框、字段、工具条，文章阅读更连贯 | **待验证**：降低非当前编辑块的工具权重，保持阅读预览和编辑位置连续 | 不能为“像聊天”取消明确保存或版本冲突恢复。大篇幅编辑构图需 Astra；无须引入富文本编辑器 |
| 错题：`pages/MistakesPage.tsx`、`features/reading/QuestionReadingLayout.tsx` | `nextAction` 已区分待处理/到期/掌握依据，详情共用题目阅读布局 | **值得保留/推广**：内容、下一动作、辅助元数据各有层级；继续用现有分栏与单栏切换 | 不把全部状态压成彩色圆点，不把“工具完成”映射为“已掌握”；不需新卡片系统。本轮只读检查 |
| 工具调用：`chat/ExecutionTrace.tsx`、`LearningTaskActions.tsx`、`LearningTaskGate.tsx` | 有后端执行状态、局部详情、审批与缺输入；过程/正文有明确边界 | **可采用**：明确“做了什么/结果是什么/下一步”，保留可展开入参和来源；已有结构足够 | 不迁 MCP 本地模拟状态、不加“始终允许”、不显示 thinking；等待/失败/降级不能都渲染为成功。真实审批流程需独立验收 |
| 跨页专注：`features/focus/FocusController.tsx`、`focus.css` | 已是一个全局控制器，跟随当前页 header；等宽数字、面板避开 composer、150ms reduced-motion 条件转场已有 | **保留**单实例、稳定数字宽度和焦点恢复；优先核对各页可用区域 | 不复制悬浮计时器到每页，不靠新全局动效解决位置。本轮未跑真实计时状态切换，不重复造 Focus 组件 |

没有一项映射要求新增依赖。公开参考更有价值的是“按职责拆状态和布局”，不是组件越多越好。

## 4. 试点实施与截图

产品代码只改三个文件：`ComposerOverflowMenu.tsx`、`index.css` 中 composer 的既有规则，以及 `ChatPage.tsx` 的错误提示 class。没有更改接口、领域状态、问答生成、数据契约、字体、设计令牌或 Electron 宿主。

- 菜单打开聚焦首项；ArrowUp 打开聚焦末项；↑/↓ 循环、Home/End 到首尾；跳过 disabled/aria-disabled；Escape 回触发器，Tab/Shift+Tab 离开并关闭，点外部关闭；补 `aria-controls` 与正确菜单名称。
- 工具 hover/focus 用同一低对比填充，去掉嵌套工具的多余边框；焦点轮廓仍保留。disabled 工具减弱显示，不触发 hover 高亮；发送按钮只在 enabled 时响应 hover。
- 截图复查后修正图片错误提示贴边的问题：增加与文本域一致的 12px 横向留白与 8px 顶部间距，并使用既有 `danger-text` 角色；不增加新警告框。
- 不追加解释文案或动效，不为统一样式抽象新组件。共享 OverflowMenu 已有近似键盘合同但定位/Portal 不同且正在被其他改动使用，本轮不迁移它；后续出现第三份相同实现再考虑提取 headless 键盘工具。

| 对照 | 修改前 | 修改后 | 可观察差异 |
|---|---|---|---|
| 键盘展开 | [原图](../qa/ui-source-study-2026-10-19/before/menu-keyboard.png) | [原图](../qa/ui-source-study-2026-10-19/after/menu-keyboard.png) | 原来焦点留在触发器；现在首个命令有填充与清晰轮廓，接着可用方向键选择 |
| 生成期间工具 hover | [原图](../qa/ui-source-study-2026-10-19/before/composer-loading.png) | [原图](../qa/ui-source-study-2026-10-19/after/composer-loading.png) | 原来禁用图片按钮仍像可点击按钮；现在弱化、无 hover 边框，停止仍是实色动作 |
| 正常学习画布 | [原图](../qa/ui-source-study-2026-10-19/before/learning-normal.png) | [原图](../qa/ui-source-study-2026-10-19/after/learning-normal.png) | 保留原来的文字层级、阅读列和输入栏几何；不是全页视觉重设计 |
| 输入错误 / 长输入 | 修改前也采集同名截图 | [错误](../qa/ui-source-study-2026-10-19/after/composer-error.png)、[长输入](../qa/ui-source-study-2026-10-19/after/composer-multiline.png) | 原有提示与可滚动限高保留 |
| 窄窗口 / 主题 / 减少动效 | 基线有空态及教材截图 | [760px 菜单](../qa/ui-source-study-2026-10-19/after/760-menu.png)、[石墨](../qa/ui-source-study-2026-10-19/after/menu-graphite.png)、[reduced motion](../qa/ui-source-study-2026-10-19/after/menu-reduced-motion.png) | 检查真实可用宽度；没有为展示动效新增动画 |

## 5. 验证与局限

可重跑脚本：`scripts/qa-ui-source-study.mjs before|after|reference`。使用已有 bundled Playwright，未修改项目依赖；正常前端 production build，真实 Electron 37、macOS ARM64、临时 userData、本机 fixture API。没有接触正式教材、会话库、模型凭证或付费服务。

- 前端现有 **51 文件 / 235 测试通过**；lint、TypeScript/Vite build 通过；桌面现有 **24/24 测试通过**。桌面初跑的端口测试曾被沙箱禁止 loopback bind，在允许本机监听的环境复跑通过。构建仍有既有 mathlive 大 chunk 提示；不把本次试点扩成性能重构。日志见 [验证目录](../qa/ui-source-study-2026-10-19/)。
- 基线 17 项检查中有 3 项菜单行为 FAIL；修改后 **24/24**（包含同项）通过。完整结果及额外键盘/状态检查见 [before/results.json](../qa/ui-source-study-2026-10-19/before/results.json)、[after/results.json](../qa/ui-source-study-2026-10-19/after/results.json)。
- 检查正常、hover、focus、空白 disabled、等待 SSE、停止、错误文件、长中文、Shift+Enter、合成中 Enter 和 compositionend 后 keyCode 229、三个窗口宽度、石墨主题、reduced-motion；中文守卫用 DOM 合成事件回归，未改提交逻辑。
- 1280×820 / 1024×768 / 760×820 下重新渲染学习与教材；修改后窄窗口学习使用真实已填充样例会话。修改前窄窗口学习为本次空态，因此不能宣称该尺寸内容截图逐像素等价。已目视检查正文、菜单焦点、工具 disabled、错误与窄窗，未发现裁切或相邻教材构图变化。
- [原生输入探针](../qa/ui-source-study-2026-10-19/native-input.json)使用 CUA 在隔离 Electron 粘贴中文并换行，发送请求数为 0；尝试输入法切换未产生 composition 事件，**真实 OS 拼音候选确认仍未验证**，不能用粘贴中文冒充。Windows、Safari、发行包和真实模型 token 流未验收。
- 外部学习问题输入曾被自动审批拒绝，理由是没有向该网站传输具体内容的授权；未执行该输入，改为只读外部观察与本地输入测试。

## 6. 持续使用与 Astra 决策

本次经验只补充现有 `texa-ui-system` 的状态/画布/复查文档，不建 CDS token 别名层。每次 UI 修改按“使用实例 → 状态矩阵 → computed style → 相邻消费者 → 实际截图”检查。

需要 Astra 决策、尚未实施的两项：

1. **笔记编辑由块表单走向更连续的文章编辑**。事实：`NoteBlocks.tsx` 每块有工具条和字段标签，`DraftWorkspace` 已有文章预览及保存状态。应先准备同一长中文/多公式笔记的编辑与阅读两张当前截图，比较当前块工具显隐两案；本次没有这些新截图，不足以批准方向变更。
2. **输入栏密度是否进一步收敛**。本次 [正常画布](../qa/ui-source-study-2026-10-19/after/learning-normal.png)和 [760px 菜单](../qa/ui-source-study-2026-10-19/after/760-menu.png)提供依据；事实是桌面工具 28px、发送 30px，窄窗保留更大目标区。当前没有裁切证据，不建议借参考项目把圆角、字号或全部工具替换成图标。

可确认的提升是：一个原先有三项失败的实际菜单流程变得键盘可操作，工具反馈与其他页面的交互语言更一致；其余页面只有映射和候选，不宣称整体审美或学习效率已被证明提升。
