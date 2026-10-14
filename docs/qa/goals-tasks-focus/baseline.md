# CP0 / 基线与实施身份

日期：2026-10-14，Asia/Shanghai。

| 对象 | 实际身份 | 处理 |
|---|---|---|
| 原聊天目录 | `/Users/jichengqian/Documents/ChatGPT/texa`，master `f999e7282b59780f295eb7b5b54fa76913f9eb66` | 开始时 `patch_notes.md` 已修改，设计提案及 `docs/design/` 未跟踪；保留 |
| 原有 Focus | `/Users/jichengqian/.codex/worktrees/mobile-s3/texa`，feature/mobile-s3 `af861ba084d94e050f4cdff62bb01096f82a4a48` | 文档中的 `04e8d12` 后又有桌面导航/手机连接修复；不整分支覆盖，不在该目录编辑 |
| 管理工作区 | `/Users/jichengqian/.codex/worktrees/goals-tasks-focus/texa`，基于 `af861ba` | 本次候选源代码与证据；未合并、未发布 |
| 临时构建目录 | `/private/tmp/texa-goals-focus-stage`，同一 baseline 的 archive 加本次修改 | 沙箱不允许直接编辑管理工作区，因此先在允许写入的临时目录完成编辑和验证，再只同步本次文件 |
| Electron 验收 | Electron 37 / Chromium 138，实际 `desktop/main.cjs` + `preload.cjs`，临时 userData | `127.0.0.1:18052`；临时 SQLite，Focus/Goal 是真实领域服务，邻页为只读样例，无模型调用 |

原 mobile-s3 的 `tests/test_focus_tasks.py` 8 passed（venv310 Python 3.10.21）。主 master 的 GoalStore 只读到 schema1，mobile-s3 读到2；本候选读到3。不得让旧包读 v3 库。

原文档所述 `59999` 运行实例本轮未重新确认，不能把历史 PID/cwd 当作现在的包身份。一次通过名称查看 Texa 的调用误启动了 `release/mac-arm64/Texa.app` 旧包；已退出，未在其界面提交操作。后续任务/计时修改只发生在明确的临时 fixture。

在正式部署前，仍须核对实际要升级的数据库路径和运行包身份，停掉所有旧后端。已有 v1/v2 库的构造器默认拒绝 Focus 升级；生产数据没有复制、迁移或覆盖。
