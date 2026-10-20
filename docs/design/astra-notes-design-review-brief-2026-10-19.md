# Astra Design Review Brief — 笔记编辑取证与试点收尾

日期：2026-10-19。**本轮没有修改产品代码或笔记设计。** 使用既有 texa-ui-system，审查对象是当前 `Texa_MacOS` 工作树（HEAD `1dc9adce`，包含其他已有未提交工作）；截图不是干净 HEAD 或发行包的快照。

## 1. 试点收尾结论

| 检查 | 结果与证据 |
|---|---|
| 三个产品文件的归属 | `ComposerOverflowMenu.tsx`、`ChatPage.tsx`、`index.css` 均与上轮 manifest 哈希一致，未混入额外修改。已保存仅含这三个文件的 [pilot-only.patch](../qa/ui-pilot-closeout-2026-10-19/pilot-only.patch)，reverse check 通过；未暂存或提交整个工作树。初始清单见 [scope-before.json](../qa/ui-pilot-closeout-2026-10-19/scope-before.json)，最终核对见 [scope-after.json](../qa/ui-pilot-closeout-2026-10-19/scope-after.json) |
| 已有证据 | 上轮测试、截图和研究记录保留原位；本轮新证据在独立目录。没有重新写入旧验收结果 |
| macOS 拼音 | CUA 原生按键驱动系统简体拼音：记录到 trusted `compositionstart` 和 `Enter/keyCode=229/isComposing=true`，Enter 确认没有发 SSE；空格确认候选得到“中文”，随后 Shift+Enter 换行。请求数 **0**。[摘要](../qa/ui-pilot-closeout-2026-10-19/native-summary.json)、[原始事件与截图](../qa/ui-pilot-closeout-2026-10-19/native/2026-10-19T07-35-58.687Z/results.json) |
| 真实模型 SSE | 当前配置 DeepSeek Flash，**1 次远端请求、1945 个 output_delta**；真实生产 Runtime/SSE/React 渲染，未替换 token 或节流播放。[摘要](../qa/ui-pilot-closeout-2026-10-19/real-sse-summary.json)、[请求回执](../qa/ui-pilot-closeout-2026-10-19/live-server-receipts.json) |
| 滚动 | 自动跟随时距底部 0.5px；手动上滚后约 2.1 秒内正文由 921 增至 1639 字符、内容高度增加 616px，scrollTop 保持 **22.5px**；点击返回最新后距底部 0.5px。[上滚阅读](../qa/ui-pilot-closeout-2026-10-19/live/2026-10-19T07-42-28.162Z/live-user-reading-up.png)、[继续生成时保持位置](../qa/ui-pilot-closeout-2026-10-19/live/2026-10-19T07-42-28.162Z/live-preserved-reading.png)、[返回最新](../qa/ui-pilot-closeout-2026-10-19/live/2026-10-19T07-42-28.162Z/live-return-latest.png) |

本轮未复现试点引入的回归，因此没有追加修复。真实模型只收到[自编提示及生产系统指令](../qa/ui-pilot-closeout-2026-10-19/real-sse-plan.json)，使用临时数据目录与临时 Electron userData，没有发送正式笔记、教材或历史会话。SSE 原始字节以 [gzip](../qa/ui-pilot-closeout-2026-10-19/live/2026-10-19T07-42-28.162Z/real-sse.txt.gz)无损保存；不把本次 UI 运行当作 Answer Eval 或准确率验收。

输入法边界：这是 CUA 驱动的系统拼音路径，不是物理键盘人工验收；日志中 compositionend 的 isTrusted 为 false，未将全部事件表述为 trusted。没有覆盖其他输入法、Windows 或 Safari。此次观察足以确认本路径的候选确认与换行没有误发，不能外推所有 IME。

## 2. 笔记样本与取证方式

使用[自编结构等价内容](../qa/ui-pilot-closeout-2026-10-19/note-content.json)：约 **1720 个汉字、16 块、4 个独立公式**，另含行内公式、矩阵、列表、表格、长标题与摘要。不是正式学习数据，也没有模型生成这份样本。通过生产 `SessionNoteService` / SQLite 校验并保存，再创建真实编辑草稿。

Electron 37 / macOS ARM64，当前 production frontend；覆盖 **1280×820、1024×768、760×820**。共采集 33 张笔记截图；[完整状态记录](../qa/ui-pilot-closeout-2026-10-19/notes/2026-10-19T07-39-34.130Z/results.json)与[同一草稿测量](../qa/ui-pilot-closeout-2026-10-19/notes-detail/2026-10-19T07-44-39.001Z/results.json)可回查。以下优先使用同一 draft、同一内容的对照，避免把生成草稿和正式编辑的标题差异混作视觉变化。

| 观察位置 | 编辑状态 | 阅读状态 / 对应证据 |
|---|---|---|
| 文档开头 | [同一草稿编辑](../qa/ui-pilot-closeout-2026-10-19/notes-detail/2026-10-19T07-44-39.001Z/same-draft-edit-top.png) | [同一草稿预览](../qa/ui-pilot-closeout-2026-10-19/notes-detail/2026-10-19T07-44-39.001Z/same-draft-preview-top.png) |
| 当前段落及相邻公式 | [第 4 块聚焦](../qa/ui-pilot-closeout-2026-10-19/notes-detail/2026-10-19T07-44-39.001Z/same-draft-edit-focused.png) | [同一段落阅读](../qa/ui-pilot-closeout-2026-10-19/notes-detail/2026-10-19T07-44-39.001Z/same-draft-preview-same-block.png) |
| 矩阵 | [公式编辑器聚焦](../qa/ui-pilot-closeout-2026-10-19/notes/2026-10-19T07-39-34.130Z/1280-edit-matrix-focus.png) | [矩阵阅读](../qa/ui-pilot-closeout-2026-10-19/notes/2026-10-19T07-39-34.130Z/1280-preview-matrix.png) |
| 窄窗 | [760px 编辑开头](../qa/ui-pilot-closeout-2026-10-19/notes/2026-10-19T07-39-34.130Z/760-edit-top.png) | [760px 阅读开头](../qa/ui-pilot-closeout-2026-10-19/notes/2026-10-19T07-39-34.130Z/760-preview-top.png) |

## 3. 已确认事实与判断边界

| 项目 | 已确认的实现 / 渲染事实 | 尚不能作为客观结论的部分 |
|---|---|---|
| 文章与表单 | 阅读正文为 **16px / 30.4px**，宽 740px；编辑文字为 **13px / 23.4px**，块内字段宽 706px。文字与公式在预览中连续，编辑中按独立字段呈现 | 哪一种密度更舒适、是否应改变编辑范式，需要 Astra 判断；没有用户完成时间或理解效率数据 |
| 重复层级 | 文档标题在上方 H1 和“标题”输入框中重复出现；每块均有“段落/公式·序号”工具条、字段标签、块外框及字段自身边框。单行章节标题也使用至少 85px 的 textarea | “层级过多”是设计判断。标签可能承担类型辨识和可访问性职责，不能仅凭重复就删除 |
| 当前与非当前块 | 16 块使用相同外框、背景与工具条规则，无 active block state/class。聚焦只改变输入控件边界；相邻块工具条仍为 visible、opacity 1。[悬停](../qa/ui-pilot-closeout-2026-10-19/notes/2026-10-19T07-39-34.130Z/1280-edit-toolbar-hover.png)不负责显示整组工具 | 是否降低非当前块权重、保留多少操作可发现性，属于后续设计取舍 |
| 长段落 | 示例第 4 块字段高 85px、clientHeight 83px、scrollHeight 154px；正文未完整显示，需要字段内滚动，外部页面也可滚动。截图中的截断是滚动视口，不是正文丢失 | 未证明嵌套滚动导致误操作；没有真实用户错误率证据 |
| 编辑/预览切换 | 同一草稿切换后焦点留在切换按钮，没有回到原输入或按块定位。一次稳定测量中编辑 scrollTop 829.5，预览也为 829.5，但该像素位置对应另一段内容；从手动定位的阅读块切回编辑后 scrollTop 为 0 | 当前实现没有跨模式内容锚点承诺；这是现有行为，不是本轮试点回归。是否要求内容位置连续，须作为后续交互合同决定 |
| 窄窗口 | 页面横向未溢出；当前工作树 760px 标题栏高 **119px**，1280px 为 **48px**，操作/返回/状态分布到多行。正式笔记版本文字在 ≤1024px 被 CSS 隐藏 | 未出现按钮裁切；不能将较高标题栏直接判为故障。是否接受其空间占用需 Astra 判断 |

## 4. 后续设计必须保留的交互合同

- **编辑和预览只是呈现切换。** `DraftWorkspace.tsx:15,87–105`：生成草稿默认预览，已有笔记的 edit draft 默认编辑；两者复用同一份 editor.content，切换不发布正式版本。
- **块工具常驻，普通 Tab 顺序。** `NoteBlocks.tsx:23–41`：上移、下移、删除是独立按钮；首/末移动有 disabled，只有一块时禁止删除，添加最多 300 块。公式用 MathLive，普通文字编辑 Markdown。当前没有块级键盘漫游或工具条显隐状态。
- **焦点落在具体控件。** `notes.css:25–30`：输入框自身 border 与额外 2px focus-visible outline 同时可见；MathLive 有自己的焦点样式。本轮未改变这些规则或削弱键盘可见性。
- **草稿自动保存与正式发布独立。** `autosave.ts:44–88`：800ms debounce、串行 CAS writer；自动保存期间仍可继续编辑，旧响应不覆盖新文字。实际观察了 [dirty](../qa/ui-pilot-closeout-2026-10-19/notes/2026-10-19T07-39-34.130Z/save-dirty.png)、[saving](../qa/ui-pilot-closeout-2026-10-19/notes/2026-10-19T07-39-34.130Z/save-pending.png)、[saved](../qa/ui-pilot-closeout-2026-10-19/notes/2026-10-19T07-39-34.130Z/save-saved.png)。为拍摄 saving，仅在浏览器侧延迟真实 PATCH 发出 1600ms，没有替换保存结果；不据此推断生产保存耗时。
- **正式保存是明确动作。** `DraftWorkspace.tsx:34–50` 先 flush 再以 revision/operation_id 提交。本次自动保存后正式版本仍为 1，点击保存后才变为 2。[正式版本 2](../qa/ui-pilot-closeout-2026-10-19/notes/2026-10-19T07-39-34.130Z/formal-saved-v2.png)；[历史版本 1](../qa/ui-pilot-closeout-2026-10-19/notes/2026-10-19T07-39-34.130Z/history-v1-readonly.png)只读，没有编辑按钮。
- **冲突与退出保护不能丢失。** 两个真实 edit draft 复现正式版本 CAS 冲突：发布被禁用，草稿仍 editable，提示可复制修改再编辑最新版本。[冲突截图](../qa/ui-pilot-closeout-2026-10-19/notes/2026-10-19T07-39-34.130Z/formal-version-conflict.png)。`useNoteEditor.ts` 的站内跳转/桌面退出须 flush，失败保留文字；本次没有重新验收整个退出恢复链。

源码入口：[DraftWorkspace](../../frontend/src/features/notes/DraftWorkspace.tsx)、[NoteBlocks](../../frontend/src/features/notes/NoteBlocks.tsx)、[notes.css](../../frontend/src/features/notes/notes.css)、[autosave](../../frontend/src/features/notes/autosave.ts)、[useNoteEditor](../../frontend/src/features/notes/hooks/useNoteEditor.ts)、[NoteDetailPage](../../frontend/src/pages/NoteDetailPage.tsx)。

## 5. 提交 Astra 判断的范围

1. 当前“整篇标题 + 字段标签 + 块类型工具条 + 两层边界”是否超过编辑辨识所需；若认为超出，哪些层级仍承担必要功能？
2. 是否需要区分正在编辑的块与其他块？现状是所有块操作常驻；本轮没有决定工具应何时隐藏。
3. 是否将跨模式内容位置连续性、窄窗标题栏占用列为下一阶段明确的交互/布局目标？两者均有截图和实现约束，不应伪装成本轮回归修复。

本 brief 没有提供重设计稿、替换编辑器、令牌迁移或新依赖建议。Astra 可基于证据决定维持现状、局部调整，或另行批准设计方向；未批准前不实施。

验证：新增笔记 Electron 检查 **10/10**、同草稿测量 **3/3**，原生输入事件检查与真实 SSE 检查完成；现有前端笔记测试 **8/8**、Python 3.10 笔记测试 **47/47**、TypeScript/Vite build 通过。测试有一条既有 Starlette deprecation warning；这些结果不代表发行包、跨平台或数学正确率验收。原有 235 项前端和 24 项桌面测试证据保持原样，没有把旧运行计入本轮新增数量。
