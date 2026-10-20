> **后续调整**：按用户要求将命令栏进一步左对齐，并与原生窗口区域分开。当前布局见 [笔记命令栏左对齐](notes-left-align-2026-10-19.md)；下文保留上一步修正记录。

# 笔记顶部布局与验收更正

2026-10-19。用户指出上轮截图中顶部标题、侧栏折叠、状态和操作分散错位。**撤回上轮对顶部视觉布局已经通过验收的判断。** 无遮挡和状态可见只能说明部分功能与几何条件成立，不能证明层级与分组合理。

本轮仅改 `NoteDetailPage.tsx`、`DraftWorkspace.tsx` 和 `notes.css`，继续使用 texa-ui-system。没有改业务、接口、依赖或其他页面的样式。

- 顶部恢复一条命令栏，标题与状态成组，操作在右侧；保留原生窗口安全区域。760px 实测从约 87.8px 高改为 56px，侧栏按钮与标题中心差从约 9.6px 缩至 0.5px；44px 操作区域、历史只读、归档和冲突状态均保留。
- 正文前两条独立折叠行合为“目录与笔记信息”一个次要入口；展开后左侧目录、右侧字段信息，保留原生 details 键盘操作和目录锚点，避免正文开头被分割成多层控件。
- 展开信息按字段排版，日期、版本不再挤在一条长句中折行。

| 对照 | 修改前 | 修改后 |
|---|---|---|
| 用户指出的历史页（760px） | [原图](../qa/notes-header-correction-2026-10-19/before/2026-10-19T11-41-15.416Z/760-history.png) | [修正](../qa/notes-header-correction-2026-10-19/after/2026-10-19T11-45-06.136Z/760-history.png) |
| 当前版本 | [原图](../qa/notes-header-correction-2026-10-19/before/2026-10-19T11-41-15.416Z/760-current.png) | [修正](../qa/notes-header-correction-2026-10-19/after/2026-10-19T11-45-06.136Z/760-current.png) |
| 编辑页 | [原图](../qa/notes-header-correction-2026-10-19/before/2026-10-19T11-41-15.416Z/760-draft.png) | [修正](../qa/notes-header-correction-2026-10-19/after/2026-10-19T11-45-06.136Z/760-draft.png) |
| 展开、冲突与宽窗 | — | [展开目录与信息](../qa/notes-header-correction-2026-10-19/after/2026-10-19T11-45-06.136Z/760-information-open.png)、[版本冲突](../qa/notes-header-correction-2026-10-19/after/2026-10-19T11-45-06.136Z/760-conflict.png)、[1280px](../qa/notes-header-correction-2026-10-19/after/2026-10-19T11-45-06.136Z/1280-history.png) |

实际 macOS Electron、同一长中文/多公式样本，在隔离临时库完成 760×820、1024×768、1280×820 截图复核，覆盖历史/当前/编辑、侧栏开合、目录键盘展开与定位、归档/恢复、版本冲突及 reduced motion；另检查学习页与笔记库。最终保留 20 张截图，无 renderer exception。[原始结果](../qa/notes-header-correction-2026-10-19/after/2026-10-19T11-45-06.136Z/results.json)。几何断言用于发现对齐错误，仍不代替对截图的分组与层级审阅；未验证 Windows、Safari、辅助技术全覆盖或真实用户效率。

本轮笔记前端 12 项测试、生产构建、改动 TSX 的定向 lint、diff 检查通过；既有 >500kB chunk 构建提示仍在。没有远端模型调用、正式数据写入或暂存提交。[本轮增量补丁（基于上轮结果）](../qa/notes-header-correction-2026-10-19/header-only.patch)。旧截图和原始结果保留；前一份修复记录已添加此更正入口。
