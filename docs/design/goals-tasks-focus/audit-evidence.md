# Goals / Tasks / Focus 审计证据

日期：2026-10-14（Asia/Shanghai）。不含生产数据库复制、模型调用或用户记录修改。

## 基线身份

| 位置 | 身份 | 用途 |
|---|---|---|
| `/Users/jichengqian/Documents/ChatGPT/texa` | master `f999e72`，审计开始时git status为空 | 本聊天文档交付目录、批准视觉基准、既有架构 |
| `/Users/jichengqian/.codex/worktrees/mobile-s3/texa` | feature/mobile-s3 `04e8d12ecb3d1b2ecc5dbabc5612f30ebb3f1088` | 实际番茄任务实现；git status仅列未跟踪desktop/node_modules与venv310 |
| 运行中的Electron窗口 | 标题Texa，页面`127.0.0.1:59999/goals` | 只读导航/AX与截图观察；没有启动或创建任务 |
| 后端监听进程 | PID11956，cwd为mobile-s3工作区（本轮观察时） | 连接实际窗口和源码的证据；PID不是长期身份 |

未额外校验运行dist每个bundle与commit的完整hash，因此运行界面与源码分别列证据，不能把进程cwd当作完整发布证明。CP0应核对前后端build身份。

## 视觉材料

已实际查看：

- [批准的学习画布](../../../artifacts/study-desk/learning-final-type.png)。
- [批准的教材列表](../../../artifacts/study-desk/textbooks-final-type.png)。
- [旧目标页截图](../../../artifacts/header-unification-2026-10-03/after/native-goals.png)，仅用于历史对照。
- 当前Electron目标页：通过CUA工具截图观察，画面2560×1640设备像素；CSS viewport未通过DOM单独核验，不能直接写成2560 CSS像素。截图保留于本聊天工具记录，本次未另存图片文件。

当前界面观察：左侧产品导航；第二栏一个“学习偏导数”目标；右侧“目标已启用 · 数学 · 不限教材”，完成条件3条；“番茄任务”下标题/分钟表单、从完成条件选择入口；再下方“本次任务·已停止”，提示旧任务无法按当前目标继续，随后“开始执行 / 暂停目标 / 定时执行 / 执行记录”。表单内已有文字未改动；未提交。

设计HTML为独立样稿。尝试本地HTTP预览遇到sandbox监听端口EPERM；随后内置浏览器拒绝file协议，未绕过浏览器访问限制。仅完成源结构/脚本语法检查，**未完成样稿渲染、点击行为、尺寸、可访问性或最终视觉签核**。不得拿它作为Electron实现截图。正式实施的渲染验收要求仍见报告CP2–CP5。

## 源码索引

下列 Focus 路径基于 mobile-s3工作区；master同名文件可能不存在。行号为本次审计版本。

| 证据 | 文件与定位 |
|---|---|
| Goal schema、版本上限 | `backend/services/goals/store.py:54`（mobile-s3允许≤2）；master同文件允许≤1 |
| 原Focus表、迁移备份 | `backend/services/goals/focus.py:19` 起；focus_tasks、focus_state、focus_receipts |
| time.time和duration截断 | 同文件`:64` `_elapsed` |
| 快照LIMIT100与派生expired | 同文件`:70` `_snapshot` |
| 幂等hash、CAS与命令事务 | 同文件`:89` `command` |
| 全库100项上限 | 同文件`:108` |
| start/switch与finish/complete | 同文件`:119` 起 |
| API操作白名单 | `backend/api/focus.py` `Command` |
| 全局Provider、performance.now投影 | `frontend/src/features/focus/FocusProvider.tsx:6` 起 |
| pending回执核对、sessionStorage | 同文件 `reconcile`；回执后不强制再GET最新快照 |
| 无task直接返回、选择即switch | `frontend/src/features/focus/FocusBar.tsx:3` 起 |
| 条件直接复制title、固定分钟输入 | `frontend/src/features/focus/FocusPanel.tsx:14` |
| 已有全局Provider挂载 | `frontend/src/Workspace.tsx:69` |
| 局部Chat FocusBar | `frontend/src/pages/ChatPage.tsx:952` |
| Goal页嵌入FocusPanel与AI控制 | `frontend/src/pages/GoalsPage.tsx:221` |
| Focus样式 | `frontend/src/layouts/MobileConvergence.css:45` 起 |
| 共享视觉角色 | `frontend/src/layouts/ApprovedWorkspace.css:1`；Goal规则`:374` 起；theme.ts |
| 路由驻留和壳层位置 | master `frontend/src/layouts/MainLayout.tsx:26`、`:234` 起 |
| BrowserWindow/最小尺寸 | `desktop/main.cjs:656` 起 |
| 关闭握手 | `desktop/window-close.cjs` 与 `desktop/preload.cjs:3` 起 |

Electron关于主进程suspend/resume事件的可行性依据是[官方powerMonitor文档](https://www.electronjs.org/docs/latest/api/power-monitor)。置顶窗口属于[BrowserWindow能力](https://www.electronjs.org/docs/latest/api/browser-window)，本报告将其列为后续选择，不代表现有项目已实现或已完成Electron37跨平台验证。

## 本轮测试

执行：

```sh
# cwd: /Users/jichengqian/.codex/worktrees/mobile-s3/texa
PYTHONDONTWRITEBYTECODE=1 /Users/jichengqian/Documents/ChatGPT/texa/venv310/bin/python \
  -m pytest tests/test_focus_tasks.py -q -p no:cacheprovider
```

解释器Python3.10.21，结果 **8 passed, 1 warning in 0.21s**；warning为Starlette使用的anyio BlockingPortal别名弃用。

覆盖已有迁移备份、暂停/重开Store/到期不完成Goal、回执重放与payload碰撞、两端同revision争用、切换保留elapsed、非法命令不提交、旧Goal恢复合同、HTTP校验。并未覆盖新设计的多session/正计时/休眠或全页面控制。

另以TemporaryDirectory与注入clock执行探针，结果在[audit-probes.json](audit-probes.json)：60秒上限任务20秒finish后start剩40秒；clock前进100秒再打开Store为expired；再start被拒绝；没有session或segment历史表。未访问生产DB。

## 未验证项

- 新设计未实现；未迁移正式数据。
- 没有在真实任务上做暂停/完成/切换试验，以免改用户学习记录。
- 当前实际Focus界面在其他页面的缺失基于源码引用检查；没有创建生产任务来逐页演示。
- 未进行Windows、手机、真实休眠、强杀或重启验收。
- 没有运行无关全库测试或真实模型评测。
