# Texa 桌面 UI 重构：第一阶段实施与验收

后续状态：用户已批准持久会话管理，并要求移除笔记来源/核实提示；后续结果见 [实施补充](desktop-ui-refactor-followup-2026-10-03.md)。下文保留第一阶段当时的实施与验收记录。

日期：2026-10-03。状态：Astra 方案与无需迁移的第一阶段已实施；持久会话管理待批准。本记录与原审查文档分开，原审查的“只读”状态描述不代表此次实施没有代码改动。

## 交接与责任

- 原审查：[用户五图与额外十五项问题](desktop-ui-audit-astra-handoff-2026-10-03.md)。审查依据包括实际 macOS Electron 页、截图和源码，分别标明证据类型。
- 宏观方案：[Astra 重构计划](desktop-ui-refactor-astra-plan-2026-10-03.md)。由用户指定的 GPT-6 Astra 制定，明确阅读画布、管理工作区、入口和 S0–S6 阶段。
- GPT-6.1 Sol 完成主要第一阶段代码及离线 fixture，之后遇到账户额度限制，未交付自己的最终验收报告。主代理接续代码审查、修复下述验收问题、执行检查并编写本报告。因此不能把全部验收及接续修改归为 Sol 亲自完成。
- 保留工作区此前及并行任务的修改；未提交 Git、重装依赖、改写用户运行的 frontend/dist、启动真实模型、发布正式笔记、运行 Goal 或删除学习数据。

## 实施结果

| 用户反馈 | 第一阶段结果 | 具体位置与边界 |
|---|---|---|
| 整理侧重太多、首屏杂乱 | 默认“按实际内容”，设置和来源详情折叠；先呈现会话、整理范围、必要警告、生成动作 | NotePreflight 使用共享 Dialog；保留完整轮次、fingerprint 和操作幂等；没有上线小模型自动选侧重 |
| 生成/草稿页面像普通网页，字号与头部不统一 | 接共享 48px 页头、19px 页名；长标题在 24px 文档标题位置，正文 16px、740px 阅读宽 | notes.css、DraftWorkspace、NoteDetailPage、NotesPage；后台任务按真实状态提供返回/停止/重试/手动整理 |
| 会话两处整理入口、常驻错题动作 | 历史行三点菜单；当前行可见时隐藏顶部同义入口，侧栏不可见或当前行未列出时保留当前会话菜单；整页一个预检 controller | MainLayout、NoteCommandContext、Sidebar、ChatPage。置顶/归档/删除没有做成假按钮，见后续提案 |
| 已录入问题仍显示“记录为错题” | 问题动作进入三点菜单，批量查询持久状态；区分未保存、未录入、草稿、已正式记录和读取失败 | useChatMistakeSources、ChatMessage、MistakeChatSourceService；已有草稿继续整理，已记录直接查看；并发录入复用同一草稿 |
| 笔记逐句来源、待核实行割裂文章 | 删除正文下逐块 metadata footer；来源与编辑/核实状态放段落侧边，点击进入 inspector；未核实标记与保存确认保留 | NoteBlocks、NoteSourceInspector。来源快照、历史版本、warning hash、revision CAS 不变；并未证明真实模型的文章组织质量 |
| 全选把应用壳一起选中 | 导航、头部、按钮、菜单、控件标签不可选；正文、公式、输入和编辑区仍可选 | ApprovedWorkspace.css。没有全局拦截 Ctrl/Cmd+A；原生 macOS Electron 和浏览器分别验证 |

其他页面沿同一方案调整：笔记库保留搜索、标签视图，筛选渐进展开；Goal 把当前状态、动作与结果放在说明前，说明/完成条件折叠；复习洞察折叠、未完成复习使用现有存储提供只读继续入口；空题库先导入/手动录入，题数和排序待有题目再显示；错题页去掉重复标题与补录按钮。历史缓存失败有明确提示与重试，不把错误伪装成空记录。

## 复核时发现并修正的边界

1. 首次 fixture 的 index.css 导入顺序与 main.tsx 不同，使拖拽区域 flex 撑大页头。修正 fixture 顺序以匹配生产，并让笔记页头显式固定 flex basis，避免导入次序改变时长高。复查为 48px。不能把 fixture 早期高度当作所有生产页的实测。
2. 空题库仍有第二组“暂无可练习习题/导入题目”，移除重复区；只保留一个准备题库入口。
3. 手动录入 Dialog 的关闭 callback 每次输入都会变，触发共享焦点 effect。稳定 callback 后连续键入保留 textarea 焦点；未提交练习。
4. 切换来源时先清除旧 inspector 数据/错误，避免加载新段落时展示旧来源。
5. 懒加载渲染器期间曾短暂显示原始 Markdown/LaTeX。共享 fallback 改为加载状态，正式内容仍由原 Markdown/KaTeX renderer 渲染，没有新生成链。
6. 取消生成要检查返回 success，失败不当作后端确认；failed/cancelled/queued 不沿用旧的“正在生成”进度文案。第一次未勾选警告保存时明确引导核对，不错误声称草稿已变化。
7. Windows 控件模拟发现共享 padding 覆盖原生窗口按钮避让，保存动作与窗口按钮可能重叠。统一页头保留 window-controls-inset；复查同时测视口溢出和控件区域交叠。此为浏览器平台样式模拟，不是原生 Windows 实测。
8. load_turn_messages 是上下文用有界函数，最多四轮，默认两轮。错题身份查询不能把这个结果当作整页完整状态。服务显式分四轮读取所有请求的 turn，再复用真实持久 user message ID。新增真实临时 SQLite 七轮回归，避免连续提问后部分问题永久处于 pending。

## 数据与 API 边界

- 新增 /mistakes/chat-sources/query 与 /capture，复用现有 MistakeLifecycleStore 和表；没有新增表、迁移或回填旧记录。Router 负责协议，身份与复用由应用 service / storage 实现。
- 稳定来源以存储 scope、conversation_id、持久 user message_id 标识；新问题未持久化时不能用前端临时 turnId 冒充 message ID。每个请求有上限，前端以 400 条分批；未读到持久问题保留 pending。
- 兼容旧 source_ref，查询扫描完整既有来源命名空间，不限最近 100 个草稿；优先正式记录，再复用既有草稿。BEGIN IMMEDIATE 保证并发捕获只创建一个草稿。已有重复数据不删除。
- 已录入的归档错题仍为 recorded；不同教材存储不混合。草稿正式收录仍走原人工核对、candidate、operation receipt 流程，不能以生成草稿算已正式录入。
- 未完成复习查询复用现有复习表，仅返回未完成且学科匹配的记录；结束复习后不再提供继续入口。
- 聊天执行记录的正文与回执改造是工作区并行任务，见其独立报告；本轮的测试总数包含当前合并工作区，不能都称为本轮新增测试。

## 实际验证

### 自动检查

- Python 3.10.21 / venv310：`test_mistake_chat_sources.py`、`test_session_notes.py`、`test_mistake_lifecycle.py`、`test_mistakes_api.py`、`test_mistake_image_lifecycle.py` 合并 **80 passed**。覆盖冻结来源、版本/CAS、确认 hash、并发复用、旧来源全量查询、跨 scope、真实 turn 身份、未完成复习及结束排除。
- 前端：**30 files / 137 tests passed**；TypeScript、变更文件 ESLint、Vite 生产构建和 git diff --check 通过。构建输出仅在 /private/tmp，用户运行的 dist 保留。
- 保留既有 Starlette/Swig deprecation 与 Markdown mixed import / 大 chunk 构建警告。未增加依赖。

### 原生 macOS Electron

使用仓库已有 Electron 包的临时副本，独立 bundle identifier、临时 userData、1280×820 窗口，加载内存 API fixture；目的仅为 UI 和选择验证，不接真实后端。

实际点击验证草稿阅读、公式/表格、来源 inspector、未确认警告的保存门槛、笔记/草稿列表导航。Cmd+A 后正文出现选择高亮，左导航、页头和按钮保持不选中。控件仍可使用。没有正式保存 API 提交。

截图：

- [原生草稿阅读](../artifacts/desktop-ui-audit-2026-10-03/refactor-native-draft-1280.png)
- [原生 Cmd+A](../artifacts/desktop-ui-audit-2026-10-03/refactor-native-cmd-a.png)

临时副本的标题栏可能包含 macOS 系统共享指示，不属于 Texa 产品控件。

### 浏览器隔离 fixture

- 1280×820、1024×768、760×820：草稿、生成、笔记库、Goal、复习、练习、错题七页；分别渲染 macOS 和 Windows chrome 标记，42 个 DOM 尺寸场景，无视口横向溢出，页头48px，Windows 页面命令不与原生控件模拟区域交叠。记录见 [尺寸矩阵](../artifacts/desktop-ui-audit-2026-10-03/refactor-layout-matrix.json)。矩阵是布局检查，不代表每页所有业务状态都做过端到端验证。
- 实际截图/交互检查：长中文、公式、矩阵、表格、待核实段落、来源打不开仍可读、集合空状态、历史失败缓存、错题未录入/已录入/失败、预检折叠设置、单一 dialog、Escape 回焦、错误菜单跳过禁用项、手动录入连续键入、输入全选。
- 生成状态检查 running、queued、cancelling、cancelled、failed、interrupted；末次复核确认失败/已取消不会继续显示旧的生成进度，重试与手动整理入口保留。没有触发模型重试或付费生成。
- [预检截图](../artifacts/desktop-ui-audit-2026-10-03/refactor-preflight-1280.png)、[生成页](../artifacts/desktop-ui-audit-2026-10-03/refactor-generation-1280.png)、[窄窗草稿](../artifacts/desktop-ui-audit-2026-10-03/refactor-draft-760.png)、[Windows 模拟窄窗](../artifacts/desktop-ui-audit-2026-10-03/refactor-windows-layout-760.png)。

### 仍未验收

原生 Windows、安装包/升级、真实付费模型的文章质量、真实长会话新侧重选择、各种真实用户数据的所有混合状态和窄窗原生 Electron。不能用 fixture 或离线测试声称这些通过。现有用户实例未更新其 dist，所以当前打开的旧界面不作为改动已部署的证据。

## 可重复预览

`frontend/ui-refactor-preview.html` 和 `src/ui-refactor-preview.tsx` 只用于开发验收，未加入 Vite 默认生产入口。先运行现有 Vite 开发服务，然后打开：

```text
/ui-refactor-preview.html?scene=draft
/ui-refactor-preview.html?scene=chat&mistake=recorded
/ui-refactor-preview.html?scene=chat&error
/ui-refactor-preview.html?scene=generation&status=interrupted
```

scene 可用 detail/draft/generation/chat/notes/goals/review/exercises/mistakes；empty 模拟空笔记库，platform=darwin/win32 仅模拟 chrome。API 拦截全部在内存，不连接真实学习存储，不代表真实模型结果。

## 待批准的下一阶段

[会话管理具体提案](conversation-management-approval-proposal-2026-10-03.md)：新增独立元数据与回执、CAS/幂等、稳定分页、置顶、归档/恢复、回收站/恢复，以及真实运行任务门槛和备份回退。没有永久删除或自动清理。该阶段需要存储/API 扩展，按 AGENTS.md 先批准后实施。小模型自动侧重和 Goal 持续对话依旧为未来方向。
