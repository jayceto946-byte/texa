# 页头统一与 Electron 视觉验收 — 2026-10-03

按用户最新要求，以学习页的 48px 高度统一桌面页头，并将共享标题字号从 19px 降至 16px（缩小 3px）。页头采用 1px 下边框、600 字重和 1.3 行高；学习页与管理页共用默认 32px 横向内距，窄窗口沿用 20px 内距及原生窗口控件避让。文章标题、公式与正文保留阅读层级。设置弹窗的页头也采用 48px / 16px。

实现集中于 `frontend/src/layouts/ApprovedWorkspace.css` 与 `StudyDesk.css`。补齐学习周报、章节重点、错题详情/诊断/录入、复习开始/进行、笔记加载/失败/已发布/已放弃状态的标题与固定页头。教材导入页此前由整个页面滚动，导致页头随内容移动、滚动条压缩其宽度；现改为仅内容滚动，并把返回按钮放在标题右侧。

## 实际视觉验收

重新启动仓库 Electron 桌面入口，加载更新后的生产构建，在 macOS 原生 1280×820 窗口逐页点击学习、目标与任务、复习、笔记、错题、练习、教材，另检查教材导入、现有笔记草稿和设置弹窗。查看全幅截图与页头对照图，标题位置、高度、边框及控件垂直对齐一致。教材导入页向下滚动后页头仍固定。

真实笔记草稿只读打开，没有编辑、生成或保存；未启动 Goal、导入教材或修改学习资产。Electron 保持开启，并停留在现有草稿，便于查看新页头。

原生截图位于 `artifacts/header-unification-2026-10-03/after/native-*.png`：

- [原生页头对照](../artifacts/header-unification-2026-10-03/after/native-headers-contact-sheet.png)
- [真实笔记草稿全幅](../artifacts/header-unification-2026-10-03/after/native-draft.png)
- [导入页滚动后](../artifacts/header-unification-2026-10-03/after/native-import-scrolled.png)
- [设置弹窗](../artifacts/header-unification-2026-10-03/after/native-settings.png)

## 隔离页面与尺寸验收

开发预览使用真实页面组件和内存 API 样例，覆盖 19 个页面/状态：学习、目标、复习概览、笔记列表、错题列表、练习、教材、导入、周报、章节重点、笔记草稿、正式笔记、笔记生成、错题详情、诊断、录入起始、录入草稿、复习起始、复习进行。

19 场景 × 1280×820 / 1024×768 / 760×820 × macOS / Windows 平台标记，共 114 项。最终变更后另复查 19 项默认宽度场景、6 项笔记加载/错误/终态、3 项设置尺寸，合计记录 142 项。所有记录均为页头 48px、标题 16px、下边框 1px，没有页面横向溢出或页头控件越界。Windows 平台标记下控件没有进入原生窗口按钮区域。

逐页查看 19 场景截图对照，并检查窄窗口样例。Windows 结果来自浏览器平台标记模拟，未进行原生 Windows 或安装包验收；三个尺寸的完整矩阵来自隔离浏览器，原生 Mac 窗口验收为 1280×820。

- [逐页截图对照](../artifacts/header-unification-2026-10-03/after/all-headers-contact-sheet.png)
- [计算样式与溢出记录](../artifacts/header-unification-2026-10-03/header-metrics.json)

## 工程验证与交付

- 前端 31 个测试文件 / 140 项通过。
- TypeScript、变更 TSX 文件 ESLint、Vite 生产构建、`git diff --check` 通过。
- 构建仍有既有 Markdown 混合导入及 MathLive 大分块提示。
- 已更新 `frontend/dist`，当前入口为 `index-BGo0DTDt.js`；保留旧 hash 资源。旧构建备份在 `/private/tmp/texa-frontend-dist-before-header-20261003`。
- 无新增依赖、数据库/索引迁移或付费模型调用。本次未调整笔记生成 prompt；此前自然文章 v4 提示保持生效。

本轮只对页头相关布局作修改；工作区原有其他未提交改动保留。
