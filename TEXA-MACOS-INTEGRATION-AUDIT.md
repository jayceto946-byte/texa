# Texa_MacOS 分支整合审计

2026-10-15。交付目录：`/Users/jichengqian/Documents/ChatGPT/texa`；集成分支：`Texa_MacOS`。

## 原因与范围

此前主目录停在 master，Anti-AI-Slop 修改尚未提交；启动脚本却编译另一个工作区的 Goals/Tasks/Focus 快照。两个版本分别包含不同成果，导致运行新功能时看不到审计修改。

审计覆盖 **8 个工作区、23 个本地及远端分支引用**。先保存所有工作区的 tracked diff、未跟踪源码/文档及 Git bundle，再整合。SSH fetch 失败后，同一仓库的 HTTPS fetch 成功；没有修改远端地址或重写原分支历史。分支清单见 [branch-coverage.json](docs/qa/branch-consolidation-2026-10-15/branch-coverage.json)，其中所有 `commits_not_integrated` 均为 0。

| 来源 | 审查及处理 |
| --- | --- |
| master / cross-module / checkpoint / Mobile S0–S2 / 旧重构分支 | 历史已互相包含；以 ancestry 核对纳入，保留主线 Runtime、DeepSeek、学习资产及恢复修复，未用旧分支文件覆盖新版 |
| 主目录未提交 Anti-AI-Slop | 保存为 45d4137 后整合；24 个实现文件中 21 个与审计结果完全一致，设置/目标/错题三处与新功能合并 |
| feature/mobile-s3 → codex/goals-tasks-focus | 纳入 f39a592 及其祖先的 7 个新提交：移动端适配、手机连接、目标/任务/专注及验证材料 |
| Goals/Tasks/Focus 工作区未提交调整 | 六个实现文件逐字纳入：顶部专注控制、Mini Panel、定位及回到最新按钮；保留历史记录 |
| codex/agent-early-output | 合入三个遗漏提交，仅保留显式运行的诊断脚本、离线测试及历史测量；未启用生产 hooks 或调用模型 |
| codex/agent-model-latency | 合入离线分析脚本及研究报告；没有按研究建议自动改变生产策略 |
| 7617 旧验收工作区 | 保留 43 个验收文件与历史结论；没有把旧验收快照作为当前生产实现 |
| 已取消的 Windows 打包准备补丁 | 未应用；属于未实施的打包工作，不是遗漏分支提交 |

原工作区及分支保留，未删除其文件或未提交修改。原始备份位于忽略目录 `artifacts/branch-consolidation-2026-10-15/`；交付前重新确认其他七个工作区的 diff 与备份一致。

## 冲突与整改

- 设置页：保留新增“手机连接”，同时保留偏好/模型/数据等分区的审计精简。五个主题只显示名称、色样和选择状态，删除颜色旁的小字，设备作用域提示保留。
- 目标页：保留任务、专注记录、AI 辅助及真实状态；完成条件仍为普通列表，不恢复表示虚假进度的空圆圈；保留“还未执行”的精简文案。
- 错题页：保留精简内容，并接入新 compact 范围控件。
- patch_notes：保留两条分支的历史，并补录旧验收记录，不用单边覆盖解决冲突。
- 渲染回归发现一处组合回归：菜单中的重复范围入口被移除，而旧移动端 CSS 仍隐藏顶部范围控件。恢复既有顶部控件在窄屏的可见性；未重新增加菜单入口。复测包含有内容的会话、专注中及空闲状态。
- 启动脚本直接编译当前主目录 `frontend/dist`，并运行主目录 `desktop`；不再复制或跳转到 `.codex/worktrees`。AGENTS.md 记录 macOS 统一集成入口。

## 验证

| 检查 | 最终结果 |
| --- | --- |
| Python 3.10 后端全部测试 | 1695 passed，6 条既有依赖告警 |
| 前端全部测试 | 219 passed / 49 files |
| 桌面 Node 测试 | 24 passed |
| TypeScript / ESLint / Vite | 通过；保留既有大 chunk 提示 |
| Electron + 浏览器路由/面板/状态/主题 | 214 项通过；无页面异常、未处理 fixture 接口、文档横向溢出 |
| 真实临时 Goal/Focus API + 浏览器 | 1280×820、1024×768、760×820、390×844 四组通过；开始→教材页暂停→有内容的学习页继续→结束，同一 session；任务仍为 pending；五主题无说明小字 |

实际查看原生设置、手机范围选择、桌面/手机页面联系表及多尺寸专注截图，确认布局和间距。代表截图与结果保存在 [整合证据](docs/qa/branch-consolidation-2026-10-15/)；原完整截图批次保留于 `artifacts/branch-consolidation-2026-10-15/visual-final`。

早期批次暴露旧面板脚本定位不再匹配移动端附件/历史入口、新增脚本在窄屏点击隐藏列表，以及一次从错误目录收集测试；均保留原日志，最终批次修正定位和运行目录后通过。移动端范围入口丢失是实际产品问题，已修复，不作为单纯脚本问题处理。

本轮使用临时数据和离线样例；没有新增依赖、付费模型调用或正式数据库迁移。用户数据库沿用此前已经批准并完成的 v3。未重新验收 Windows、手机实机软键盘、物理休眠、安装包或付费模型准确性。

## 日常启动

先正常退出旧 Texa，再执行：

```sh
cd /Users/jichengqian/Documents/ChatGPT/texa
bash scripts/start-latest-desktop-macos.sh
```

脚本使用当前检出，保留原用户数据和模型配置。原来的直接 Electron 命令也读取此主目录的构建；源码变化后应先重新编译。
