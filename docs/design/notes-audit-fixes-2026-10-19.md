> **顶部视觉验收更正（2026-10-19）**：用户指出标题、侧栏按钮和操作分组存在明显问题。撤回本文对顶部视觉布局已通过验收的判断；下文截图与测试作为历史记录保留。最新修正见 [顶部布局与验收更正](notes-header-correction-2026-10-19.md)。

# 笔记审计修复与验收

2026-10-19 · `Texa_MacOS` · 依据 [Astra 审计](notes-design-audit-2026-10-19.md)，按删除恢复 → 窄窗正文/状态 → 按块位置连续性 → 编辑层级顺序实施。继续使用 texa-ui-system；没有引入依赖、并行设计系统、后端生产改动或数据迁移。

## 已完成的修复

| 顺序 | 修改及实测结果 | 实现 |
|---|---|---|
| 1 | 真实复现误删并自动保存后无恢复入口；新增本次编辑内的连续删除撤销。恢复正文、稳定 ID、来源引用、分组及位置；自动保存仍走同一 CAS writer。删除后焦点移至撤销，恢复后回到块。 | `autosave.ts`、`DraftWorkspace.tsx` |
| 2 | 三档尺寸的普通段落和列表均为 16px/30.4px；760px 原为 13px/21.06px。行内公式实测由 15.73px 恢复为 19.36px。历史只读、归档、当前版本文本保持可见。 | `notes.css` |
| 3 | 按已有 block_id 加块内相对位置恢复可见内容，等待 Markdown/MathLive 完成布局；鼠标、键盘切换均保持同一块可见。切换按钮保留焦点，不强制抢进正文，也不保证恢复编辑选区。 | `hooks/useDraftPosition.ts` |
| 4 | 文档标题仅保留一个可编辑呈现；块标签保留 accessible name；非当前块以分隔线组织，当前块有独立背景/边界，字段保留单一焦点轮廓。工具常驻并可由 Tab 到达，没有 hover 才可用的操作。标题字段 40px，样本标题块整体 96px（原审计约 209px）。长段落按内容增高，极长文本限制在 min(60vh,520px)。760px 标题栏约 87.8px（旧 brief 为 119px），保留状态及 44px 操作区域。 | `NoteBlocks.tsx`、`NoteTextarea.tsx`、`notes.css` |

移除了 `MobileConvergence.css` 中与笔记标题栏冲突的旧布局，把笔记布局集中到 `notes.css`；没有改变其他页面的规则或原生窗口安全区域。样本正文第 4 块在 1280px 为 clientHeight=scrollHeight=288px，760px 为 318px，已无原先的 83px/154px 内部滚动；极长文本实测控件 492px，内容 3327px，仍可内部滚动。

**恢复边界：** 撤销栈只在当前编辑器生命周期内有效，刷新、离开后重新打开或重新载入服务端草稿不保留；不是草稿历史版本系统。恢复提交保留来源引用，但服务端按既有验证规则将重新加入的块归为用户新增，核实状态仍由服务端决定，并不恢复或授予数学 verified。新增后端用例使用非空冻结来源引用，确认恢复不丢失引用。块数达到既有 300 上限时，保留撤销项，待腾出位置后才能恢复。

## 前后截图

同一份自编长中文样本，16 块、4 个独立公式；实际 macOS ARM64 Electron 37、生产构建、真实 SessionNoteService/SQLite，所有写入仅发生在 `/private/tmp` 的隔离库。

| 场景 | 修改前 | 修改后 |
|---|---|---|
| 编辑开头 | [1280px](../qa/notes-audit-fixes-2026-10-19/before/2026-10-19T11-07-37.668Z/1280-edit-top.png) | [1280px](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/1280-edit-top.png)、[760px](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/760-edit-top.png) |
| 窄窗阅读 | [760px](../qa/notes-audit-fixes-2026-10-19/before/2026-10-19T11-07-37.668Z/760-reading.png) | [760px](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/760-reading.png) |
| 历史只读状态 | [760px](../qa/notes-audit-fixes-2026-10-19/before/2026-10-19T11-07-37.668Z/760-history.png) | [760px](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/760-history.png) |
| 删除与恢复 | [自动保存后删除](../qa/notes-audit-fixes-2026-10-19/before/2026-10-19T11-07-37.668Z/deleted-after-autosave.png) | [撤销入口](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/deleted-after-autosave.png)、[恢复原块](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/undo-restored.png) |
| 同块校对 | [上阶段位置证据](../qa/ui-pilot-closeout-2026-10-19/notes-detail/2026-10-19T07-44-39.001Z/results.json) | [阅读同块](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/760-preview-same-block.png)、[回到公式编辑](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/760-equation-after-toggle.png) |

其他已检查截图：[聚焦正文](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/1280-edit-focused.png)、[键盘工具焦点](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/keyboard-tool-focus.png)、[MathLive 键盘编辑](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/formula-keyboard-edit.png)、[对应公式预览](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/formula-keyboard-preview.png)、[冲突](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/760-version-conflict.png)、[归档](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/760-archived.png)、[关闭失败保留编辑](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/native-close-flush-error.png)、[reduced motion](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/reduced-motion-history.png)。公式测试的 +1 仅用于输入持久化验证，不是数学正确性示例。

## 验证结果与界限

- 最终笔记 Electron 运行：37 张截图、101 个具名断言通过，无 renderer exception。[原始结果](../qa/notes-audit-fixes-2026-10-19/after/2026-10-19T11-24-31.735Z/results.json)。断言包含逐张截图标题栏几何检查，不应解读成 101 种独立编辑工作流。
- 实际覆盖：新内容→删除→自动保存完成→切换预览→撤销；段落/公式跨模式同块连续性；MathLive 真正键盘输入后等待 PATCH 回执；Tab/Shift+Tab 工具顺序；正文/列表/公式有效样式；1280×820、1024×768、760×820 下历史/归档状态、无横向文档溢出、标题栏无重叠。
- 保存合同：自动保存不发布正式版本；显式保存前 flush 最新输入；正式版本冲突不覆盖现有版本且保留草稿；阻断 PATCH 的网络故障保留文字并可重试；返回路由 flush 失败留在编辑器；真实 Electron 关闭 handshake 失败后窗口仍在、文字保留、字段重新可编辑。
- 相邻页面：学习问答和笔记库在 1280/760px 的 4 张截图及 10 个断言通过，没有发送模型请求。[结果](../qa/notes-audit-fixes-2026-10-19/adjacent/2026-10-19T11-25-37.110Z/results.json)、[学习页](../qa/notes-audit-fixes-2026-10-19/adjacent/2026-10-19T11-25-37.110Z/760-learning.png)、[笔记库](../qa/notes-audit-fixes-2026-10-19/adjacent/2026-10-19T11-25-37.110Z/760-notes-list.png)。
- 前端全量 51 文件 / 239 测试、笔记后端 48 测试、桌面 24 测试通过；TypeScript/Vite 构建、改动 TS/TSX 的定向 ESLint、`git diff --check` 通过。[前端](../qa/notes-audit-fixes-2026-10-19/frontend-tests.log)、[后端](../qa/notes-audit-fixes-2026-10-19/backend-tests.log)、[桌面](../qa/notes-audit-fixes-2026-10-19/desktop-tests.log)、[构建](../qa/notes-audit-fixes-2026-10-19/build.log)、[lint](../qa/notes-audit-fixes-2026-10-19/lint.log)。既有 MathLive chunk >500kB 与 Starlette deprecation 警告仍在，不把它们算作失败或宣称已消除。
- 没有重新做真实 macOS 中文输入法人工验收、完整辅助技术验收、Windows/Safari 或真实用户效率评估；本轮未改输入事件处理，也未调用远端模型。不能把像素位置相同、编译通过或本次断言数量替代完整体验验收。

## 后续沿用的检查方式

长文编辑改动继续沿用同稿、同内容、三档尺寸的对照。涉及删除时检查草稿自动保存后的撤销；涉及阅读样式时测实际段落/列表/公式，不能只看根节点或无溢出；涉及响应式标题栏时同时检查历史、归档及冲突状态；涉及跨模式布局时按块核对可见内容、键盘路径及焦点。工具的操作能力和可发现性是合同，常驻外观及具体层级仍可审查。

原 brief、Astra 审计和旧证据保留为历史记录；本记录限定并补充原 brief 的字号测量、测试范围与构建警告。可独立审查的 [7 个产品文件补丁](../qa/notes-audit-fixes-2026-10-19/notes-only.patch)、[文件清单](../qa/notes-audit-fixes-2026-10-19/implementation-manifest.json)不包含其他未提交工作；未暂存或提交。
