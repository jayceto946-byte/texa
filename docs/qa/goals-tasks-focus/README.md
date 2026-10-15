# Goals / Tasks / Focus 候选验收

2026-10-14 · 实施基线 `af861ba084d94e050f4cdff62bb01096f82a4a48`（mobile-s3 已有 Focus）。候选位于 `/Users/jichengqian/.codex/worktrees/goals-tasks-focus/texa`，未合并、未发布。原主检出目录及真实学习数据没有覆盖。

## 已交付

- 手动保存目标、编辑完成条件，任务队列与 AI 辅助分视图；行内新增、批量拆任务、排序、完成、撤销与软移除。
- 每个任务可有多个独立专注时段。倒计时到点仍记录实际投入；正计时、暂停、恢复、结束、历史及按日累计。
- MainLayout 单一控制器：各页面保持同一时段，窄窗用 sheet，空间不足时避让聊天输入区；下一项由用户开始。
- CAS、原 operation_id 回执、跨刷新 pending、迟到快照过滤；未知结果不提前显示完成。后台检查点、关闭暂停、电源事件及重启保守恢复。
- 显式 v1/v2→v3 迁移工具，包含 WAL 的 SQLite backup、旧 ID/Goal revision/links/累计保留和部署回滚说明。

## 验证结果

| 验证 | 结果 | 证据 |
|---|---|---|
| Python 3.10 受影响 Focus / Goal 测试 | 28 passed；同一源代码在管理工作区复验 28 passed | [backend-tests.log](backend-tests.log) |
| 前端受影响时间投影、位置、完成状态、Goal、笔记 autosave、API 测试 | 38 passed / 7 files | [frontend-tests.log](frontend-tests.log) |
| Electron 电源桥、关闭握手、已有远程连接合同 | 13 passed | [desktop-tests.log](desktop-tests.log) |
| TypeScript、修改区域 ESLint、Vite 生产构建 | 通过；现有 mathlive 大 chunk 提示保留 | [lint.log](lint.log)、[build.log](build.log) |
| 注入时钟 | 20秒+暂停300秒+10秒=30秒；25+18=43分；到点继续2分=27分；壁钟/重启未知尾段不补计 | [clock-examples.json](evidence/clock-examples.json)、领域测试 |
| 临时 v2/WAL 升级及备份还原 | integrity OK，旧表关键记录/ID、Goal revision/links 保留 | [migration-rehearsal.json](evidence/migration-rehearsal.json)、[迁移说明](migration.md) |
| macOS 当前 Electron + 临时真实 Focus/Goal API | 手动目标→4任务→排序→开始→完成→撤销→第二时段；关闭后 paused / shutdown；新目标保存后聚焦任务输入 | [原生操作记录](native-journeys.md)、[退出快照](evidence/after-native-close.json) |
| 正计时完成回执延迟 / 刷新 / 核对 | 等待期间显示“保存结果待核对”；原目标 3 个 session ID 保持不变，没有重复记录 | [前后核对](evidence/lost-reply-comparison.json)、[待核对截图](evidence/760-pending-final.jpg) |
| 五页面切换 | task/session ID 不变，前后都 running，历史数仍 5；后端估算 active_ms 202825→270039 | [之前](evidence/routes-before.json)、[之后](evidence/routes-after.json)、[截图板](review-board.html) |
| 1280 / 1024 / 760 原生窗口 | 目标页、托盘、窄窗 sheet 和输入区避让已抽查；不代表全状态视觉签核 | [截图板](review-board.html) |

共 79 项相关自动测试通过。未运行全库回归，未调用模型，未安装依赖。

## 验收边界

- Focus/Goal 使用临时真实 SQLite 及本次领域服务；AI Runtime 不启动，教材/复习/练习是只读样例，笔记为空库。截图证明布局与全局控制，不能替代各模块真实数据整链路。
- 相邻样例最初的复习会话 DTO 为数组，旧样例缺少字段，触发渲染错误；修正临时 fixture 后重测通过。未改 LearningPage 来掩盖样例问题。
- 真实 macOS 系统休眠 5 分钟、Windows、笔记脏草稿阻止关闭的实机组合、多端真实设备、Inspector / 长输入的全状态验收、AI 等待确认实机状态仍待验证。电源事件与保守尾段的自动测试不写成物理休眠结果。
- CP0 / CP1 有隔离证据；CP2 / CP3 已实施并有主要原生链路，仍有上面的整链路抽查项；CP4 部分原生验证；CP5 最终视觉签核未完成。没有把候选标为正式发布。
- 正式库迁移与部署另需批准，依据项目 AGENTS.md：“涉及架构、数据迁移、依赖重装、删除数据等高风险操作时，需要征得用户同意。” 当前完成的是隔离候选实现与临时迁移演练。

## 复现与交接

用项目 `venv310/bin/python` 运行 `tests/test_focus_tasks.py` 及受影响 Goal 测试。前端检查命令见日志与源码；必须先编译再启动同一构建，避免开发期间替换 dist 造成旧 renderer 读取不同 hash 的资源。

原生 fixture：先在临时 staging 根目录运行 `TEXA_VISUAL_PORT=18053 node scripts/visual-preview-server.mjs`，再以 `DATA_DIR=/private/tmp/texa-focus-qa-data venv310/bin/python -m uvicorn docs.qa.goals-tasks-focus.fixture_server:app --host 127.0.0.1 --port 18052 --no-access-log` 启动真实 Focus/Goal API。Electron wrapper 仅接受 `/private/tmp/texa-focus-qa*` userData；设置 `KAOYAN_SKIP_BACKEND=1`、`KAOYAN_BACKEND_URL=http://127.0.0.1:18052`、`KAOYAN_FRONTEND_DEV_URL=http://127.0.0.1:18052/goals` 后用已有 Electron 可执行文件运行 `electron-fixture.cjs`。邻页只读样例服务不可用于正式部署。

代码与证据文件哈希见 [同步清单](sync-manifest.json)。正式部署前按 [migration.md](migration.md) 核对真正的数据库路径、运行包与 schema；不要用 master 的旧读取器打开 v3 库。
