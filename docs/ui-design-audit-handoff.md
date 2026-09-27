# Texa UI / Design System Handoff

日期：2026-09-24。来源：已完成的 UI 与 Design Skills 审计；本文不新增审计结论或设计方向。

## 1. Current state

- Texa 已有克制的中性表面、语义主题、开放式回答文档流和部分共享控件；主要差距是密度分配、视觉层级与跨页面控件一致性。
- 已实看 macOS Electron：学习空会话、复习、错题录入、练习、教材、服务器健康、模型配置。桌面包与本地构建主 CSS 哈希一致。
- 当前运行数据为空。长对话、密集列表、公式与引用状态的判断来自源码；小窗口、其他主题及 Windows 未完成本轮视觉实测，不得写成已通过。
- 仓库专用 UI skill 为 `.agents/skills/texa-ui-system/`：入口及 14 份参考文件共 721 行。核心实现为 `frontend/src/index.css`、`theme.ts`、`components/ui/`；历史实现约束集中于 `texaUiContract.test.ts`。
- 审计未修改代码、规则或文档。工作区已有其他改动；执行前确认归属，保留既有修改。

### 平台边界：执行时必须遵守

当前工作位于 macOS branch，但分支名称不决定 UI 修改范围。

| 标记 | 范围 |
|---|---|
| **SHARED** | Windows + macOS 共通：typography、spacing / density、layout、visual hierarchy、sidebar / header、button / input / tab、empty state、design tokens、shared components、management pages visual language |
| **MAC-ONLY** | macOS native traffic lights、依赖 macOS 的 titlebar / drag region、BrowserWindow 配置、原生窗口控件、OS-specific font fallback，以及确实依赖 macOS 能力的行为 |
| **WINDOWS-ONLY** | 对应的 Windows 原生窗口控件、titlebar / drag region、BrowserWindow 配置、OS-specific font fallback，以及确实依赖 Windows 能力的行为 |

**SHARED 修改不得放进 macOS-only CSS、darwin 条件分支，也不得复制独立 macOS UI。** 标题栏的原生控件避让属于平台适配；普通页面 header / sidebar 的排版、尺寸与视觉层级属于 SHARED。字体 fallback 可按平台区分，字号、字重、行高与角色仍属于 SHARED。

本 handoff 没有新增 WINDOWS-ONLY 功能要求；Windows 是所有 SHARED 修改的必验平台。

## 2. Confirmed problems

| 范围 | 已确认问题 | 设计理由 / 证据 |
|---|---|---|
| SHARED | 字体层级不统一 | 页面标题 20px、设置内部标题 24px、空会话标题 30px、导航标签 10px；500–600 使用同一 Medium 字体文件。见 `index.css` |
| SHARED | 密度与节奏不稳定 | 复习内容集中左上；练习少量控件撑起大横向区块；模型设置多层标题、间距、分隔线叠加。去卡片没有自动产生层级 |
| SHARED | 同类控件视觉语法分散 | 错题下划线 tabs、练习深色分段控件、教材浅色分段控件、设置侧边线选择态缺少一致的角色定义 |
| SHARED | 空态尺度与重心不统一 | 学习居中 `Ask Texa`、复习左上说明、教材列表提示、练习横条各自实现；空数据本身不是缺陷 |
| SHARED | 辅助文字过淡 | 默认 tertiary 色 `#858e88` 在三个常用背景上计算对比度约 2.91–3.28:1；这不是完整可访问性验收 |
| SHARED | 分组与对齐依赖局部补丁 | 页面 gutter、区块 padding、组件 padding 叠加；阅读正文 800px、外层与 Composer 920px，需要明确各轴线用途 |
| SHARED | 圆角、阴影和反馈缺少单一来源 | 实际存在 4/6/8/12px；教材菜单引用未定义 `--shadow-medium`；全局按钮 pressed 位移缩放；focus 有多种叠加方式 |
| SHARED | 阅读层级存在压平风险 | Markdown h1/h2 同为 18px，答案 strong 为 600；长内容效果尚待实测，不当作已确认阅读故障 |
| SHARED | 启动页与主应用视觉断层 | `desktop/loading.html` 独立使用蓝色、渐变、模糊与 16px 圆角；主应用为矿物绿和平面表面 |
| SHARED | 规则过密且与实现脱节 | 文档字体、圆角、settings 页面描述已过期；重复产品口号、形态禁令和任务模板增加负担 |
| SHARED | 测试锁实现而非结果 | `texaUiContract.test.ts` 锁定 `Ask Texa`、具体 class、Select 数量、禁止 `lazy(`；不能证明视觉一致性 |
| MAC-ONLY | 原生控件适配影响壳层比例 | macOS rail 为 84px，内部导航项仍 48px；原生控件避让与共享导航视觉需分别处理，不据此建立独立 macOS 设计系统 |

## 3. P0 / P1 / P2

| 优先级 | 范围 | 执行项 |
|---|---|---|
| P0 | SHARED | 已观察界面未确认阻碍阅读/操作的严重视觉问题；不得虚构 P0，也不得据此宣称所有状态通过 |
| P1 | SHARED | 统一 typography 角色、密度节奏、控件家族、sidebar/header 权重、空态尺度、必要辅助文字可读性、分组边界 |
| P1 | SHARED | 撤销过时禁令与实现锁定；精简 skill，明确 tokens / components 的权威来源 |
| P2 | SHARED | 校准内容轴线、圆角/阴影、hover/pressed/focus、长文层级，以及启动视觉一致性 |
| P2 | MAC-ONLY | 在原生 traffic lights、titlebar 和 drag region 范围内复核避让；普通壳层视觉仍走 SHARED |
| P2 | WINDOWS-ONLY | 若共享调整影响 Windows 原生窗口控件，仅在对应原生适配层修正；不建立 Windows 独立页面样式 |

## 4. Recommended changes

按以下顺序执行；保持现有内容、顺序、布局职责和业务行为。

1. **[SHARED] 精简约束。** 先清除过期禁令和固定实现的断言，保留用户可感知的行为保护；不要直接删除相关功能回归保障。
2. **[SHARED] 收敛 tokens。** 字体、字重、字号、行高、spacing、density、radius、elevation、motion 建立单一来源；合并 `theme.ts` 与 CSS 重复权威，补齐未定义 token。不要因旧规范而删除合理的 6px 或光学校正。
3. **[SHARED] 收敛高频组件。** 统一 Button / IconButton / Tabs / SegmentedControl / Field 的有限 variants 和状态。复用现有 Dialog、ScrollableSelect、Inspector；先纠正共享状态组件自身的嵌套边界问题，再扩大复用。
4. **[SHARED] 调整页面视觉。** 统一标题角色与操作尺度；收紧组内间距、明确组间距离；校准 sidebar/header 权重和页面轴线。阅读、列表、表单可以有不同密度，不能机械压缩全部内容。
5. **[SHARED] 统一空态和状态表达。** 保留场景位置差异，统一文字层级、图标、间距和最大宽度；必要信息不能靠过低对比隐藏。
6. **[SHARED] 校准精度。** 按控件角色统一 hover/selected/pressed/focus；验证长文标题、结论、推导、公式和引用的区分；启动阶段共享字体、色彩及状态语义。
7. **[MAC-ONLY] 保留原生适配边界。** 仅处理 traffic lights、titlebar/drag region、BrowserWindow/native controls 和系统字体 fallback；不将通用视觉修正藏进 macOS selector。
8. **[WINDOWS-ONLY] 保留原生适配边界。** 仅在需要时修正 Windows 对应原生能力；共享组件与页面不得分叉。

### 最小 Design Constitution [SHARED]

只保留六条稳定原则；不写具体页面模板或数字清单：

1. 学习内容优先：内容、来源与必要状态清楚，装饰不争夺注意力。
2. 层级来自关系：位置、对齐、间距、字重和必要边界共同表达主次。
3. 同类语义使用同类控件；差异服务于任务或平台。
4. 阅读舒适，操作紧凑；正文和工具区可采用不同密度。
5. 状态真实可辨认；不依赖颜色或 hover 单独传达。
6. 以实际渲染为准；复用代码系统，在相关状态和窗口尺寸下验证，允许规则基于证据演进。

目标结构 [SHARED]：**Core principles → Design tokens → Shared components → 按需读取的 Page-specific rules**。自然语言约束建议约 100–150 行，作为维护预算，不是硬性指标。

## 5. Design skills dispositions

以下处置全部为 **SHARED**；文件位于 `.agents/skills/texa-ui-system/`。

| 文件 | 结论 | 执行要求 |
|---|---|---|
| `SKILL.md` | SIMPLIFY | 保留简短执行入口；删除最高权威声明、重复原则及无条件“先改结构” |
| `references/00-product-model.md` | SIMPLIFY + MERGE | 保留对象语义、来源可信度；删除对象与外形永久绑定及重复矩阵 |
| `01-learning-flow.md` | MERGE | 路由/场景职责归入产品或页面说明；退出视觉任务默认阅读链 |
| `02-page-layout.md` | SIMPLIFY + MOVE TO CODE | 保留主区优先；尺寸、断点、区域行为交给 shell |
| `03-learning-canvas.md` | KEEP 核心 + SIMPLIFY | 保留阅读、公式、引用、内容连续性；删除问题背景/边界/消息形式的绝对禁令 |
| `04-components.md` | MOVE TO CODE | 控件契约归入组件 API、状态与测试 |
| `05-interaction.md` | MERGE + MOVE TO CODE | 一句键盘/焦点原则；具体行为交给组件 |
| `06-typography.md` | MOVE TO CODE | 数值、字体以 tokens 为准；仅保留阅读与界面文字的角色区别 |
| `07-color.md` | MOVE TO CODE + SIMPLIFY | registry 管理主题与色值；保留颜色表达语义 |
| `08-spacing.md` | MOVE TO CODE | 删除自然语言数字清单；以 spacing / density tokens 保证 |
| `09-surfaces.md` | MERGE + MOVE TO CODE | 保留分组原则；圆角/边框/阴影归组件 |
| `10-states.md` | KEEP 核心 + MOVE TO CODE | 保留真实状态、后果、恢复入口；具体表达和行为交给代码 |
| `11-review.md` | SIMPLIFY | 删除多数黑名单、卡片/字号计数、关键词扫描；检查可读性、层级、状态、一致性 |
| `12-task-patterns.md` | DELETE | 删除独立模板文件；必要步骤并入入口 |
| `13-reference-harnesses.md` | DELETE 出默认规则链 | 如需保留，归档为非规范性参考 |
| `agents/openai.yaml` | SIMPLIFY | 保留调用入口；删除“最高产品视觉约束” |
| `assets/README.md` | MERGE | 合并进真实品牌/字体资源说明 |

其他载体 [SHARED]：

- **KEEP** `AGENTS.md` 的桌面优先、数据安全、Markdown/KaTeX、流式状态等工程约束；不重复写进 skill。
- **KEEP + MERGE** `theme.ts` / `index.css` 的权威来源；**KEEP** 现有共享组件，承接规则。
- **SIMPLIFY** `texaUiContract.test.ts`：删除固定文案、class、控件数量、加载实现的锁定；改为必要的行为/视觉/性能目标验证。
- **KEEP** `theme.test.ts` 的完整性与主题应用检查；静态检查承接未定义 token、绕过共享 token 等确定性问题。
- **KEEP** `patch_notes.md` 和历史架构文档为历史资料，不作为现行视觉规范。
- **DELETE / 替换** `frontend/README.md` 的 Vite 模板正文，写实际设计系统入口。
- **KEEP** `site/assets/styles.css` 的宣传站独立范围，不并入应用视觉约束。

明确废弃 [SHARED]：无条件“结构优先”、固定字号数量、僵硬 4px 间距与 4/8/12 圆角限制、宽屏不得留空边、外形黑名单、否定视觉精度价值的例外规则、只有立即复用才允许 primitive、每次小改都全量检查所有功能。

## 6. Non-goals

- **[SHARED]** 不重设计页面；不改变信息架构、用户流程、内容顺序、业务逻辑、API、数据结构、持久化或教材索引。
- **[SHARED]** 不新增设计方向、主题、竞品模仿方案或一套更细的规则；不靠填满空白、减少卡片数量判定质量。
- **[SHARED]** 不删除有效的状态、来源、错误、修复入口、键盘支持和业务回归保护。
- **[SHARED]** 不为截图生成真实学习记录、不导入教材、不调用付费模型；需要内容样本时使用隔离的展示数据。
- **[MAC-ONLY / WINDOWS-ONLY]** 不复制平台专属页面、组件库或通用 typography/spacing/layout 样式；平台判断必须对应真实 OS 能力。

## 7. Acceptance criteria

- [ ] **[SHARED] 范围：** diff 不改变流程、路由职责、业务/API/数据契约；既有工作区改动未被覆盖。
- [ ] **[SHARED] 规则：** 每份旧文件有明确处置；重复内容已合并，过时数值和形态禁令不再是权威；默认阅读链只有短入口与核心原则。
- [ ] **[SHARED] 代码：** 关键视觉值有单一来源；无未定义 token；高频同类控件使用共享 variants，不再按页面复制相同样式。
- [ ] **[SHARED] 层级：** 页面/区块/控件/正文/辅助文字可区分；必要辅助信息可读；密度差异由内容用途解释。
- [ ] **[SHARED] 状态：** hover、selected、pressed、focus、disabled 可辨认；焦点不意外叠加；空态、错误和加载的尺度一致且不重复套框。
- [ ] **[SHARED] 阅读：** 使用代表性的长中文、公式、表格、引用和多级标题样本，检查层级、轴线与溢出；不把源码检查当作渲染验收。
- [ ] **[SHARED] 跨平台：** Windows 与 macOS Electron 均检查最小支持窗口、正常笔记本和宽窗口；至少覆盖五个主要页面、设置长表单、空态和代表性有数据状态。
- [ ] **[SHARED] 主题：** 受影响的现有主题均验证文字、边界、状态与选择态；不得仅默认主题通过。
- [ ] **[MAC-ONLY] 原生窗口：** traffic lights、标题栏避让、拖动区域正常；共享视觉没有混入 macOS-only CSS。
- [ ] **[WINDOWS-ONLY] 原生窗口：** 原生/自绘窗口控件、标题栏避让、拖动区域正常；无共享视觉分叉。
- [ ] **[SHARED] 验证与交付：** 执行与改动相关的 lint、类型/构建和必要测试；视觉验证单独记录。缺少平台环境时明确标为未验证，不宣称双平台通过；普通修复及验证结果写入 `patch_notes.md`。

执行完成报告必须区分：实际验证、源码确认、仍待验证；不得把原审计中的风险判断升级为已确认缺陷。
