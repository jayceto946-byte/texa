# Agent Runtime 实施状态

更新：2026-09-27。P0–P4 的内核、服务接入和最小目标 UI 已实现；默认生产接管保持关闭，发布验收仍有下列门槛。

| 阶段 | 已实现 | 发布前剩余 |
|---|---|---|
| P0 | SQL task/run/call/event authority、预算、幂等、owner fence、重启恢复 | 配合实际 profile 的线上验证 |
| P1 | 保守 capability Router/Resolver、语义 shadow、有限 fallback、脱敏 trace、人工 review/holdout CLI、真正绕开 plan/retrieve 的 direct 路径 | 真实 trace 人工标注、holdout 校准与接管决策；自动接管关闭 |
| P2 | 主聊天 SQL 分流、GET/interrupt/resume/actions、游标事件回放、共享生成/验证、限定教材搜索、审批、四种领域写工具收据、outbox/lifecycle、备份恢复 | 供应商/profile 原生 tool calling 实测与真实模型 Answer Eval；完整 Electron 端停止/断线/恢复 UI 验收 |
| P3 | 独立 Goal、revision、计划失效、手动测量、事件投影对账、legacy 写入 facade、多目标澄清、学习上下文目标入口、学习记录选择 | 历史 legacy 目标仍保留兼容事件视图，未全部迁入 Goal 列表；窄窗口完整视觉验收 |
| P4 | V2 origin + V1/V2 双读、fake trigger 去重、source 失效/版本/权限故障隔离、恢复契约 | 本地 Goal 定时队列已按用户新请求实现；插件装载和真实 MCP 连接仍未实现 |

## 启用策略

- `TEXA_AGENT_RUNTIME_READ=1` 才允许新任务进入 SQL runtime；写工具还需 `TEXA_AGENT_RUNTIME_WRITE=1`，教材 QA 还需 `TEXA_AGENT_RUNTIME_TEXTBOOK=1`。teach/summarize 使用既有 graph。
- `TEXA_AGENT_ROUTER_SHADOW`、`TEXA_AGENT_ROUTER_SEMANTIC_SHADOW`、`TEXA_AGENT_DIRECT_FAST_PATH` 默认关闭。
- 原生工具调用接受实际连接测试保存的 30 天能力记录（绑定模型、端点、options 与凭证摘要）；配置变化后失效。旧显式 `tool_calling_verified` + catalog 检查仍兼容。当前用户 Qwen profile 已完成实测；默认聊天接管开关仍关闭。
- 已归属 SQL 的任务发生异常不得转向旧任务存储。运行恢复只暂停/对账，不自动重放模型或未知写操作。
- Goal schema 1、runtime schema 3、routing trace schema 2、mistake book schema 2 已登记 storage manifest。升级在对应存储初始化时执行；本次未迁移用户实际数据库。

## 验证

- Python：80 项 runtime/router/goals/migration/learning-state/pending-action 测试通过，另 84 项 chat/generator/tools/LLM 配置回归通过。
- 前端：25 个文件、121 项测试通过；TypeScript、eslint 与 Vite 构建通过。构建仍提示已有 Markdown 动态导入及大 chunk。
- Electron runtime：4 项测试通过。备份恢复使用真实 backup/schedule_restore/apply_pending_restore 代码和临时数据，恢复后运行中任务只转 interrupted，不重放工具。
- 目标面板已检查包含已有会话、已有目标和学习记录的本地演示；Electron 与窄窗口验收单列，不能把浏览器演示视为全部桌面验收。
- 2026-09-27 用户授权后已完成真实小样本文本、工具、Goal Runtime 与公开图片测试；报告见 [真实验证](validation/agent-online-2026-09-27.md)。未用此结果声称总体线上准确率。

## 用户明确发起的目标与定时任务

- `/goals` 管理自然语言目标、显式后台运行和本地定时任务；主聊天可将草稿转为目标。模型整理不直接创建或执行目标，需用户确认。
- Goal run 复用共享 Runtime 与发布验证边界，最多 6 次工具/8 次模型步骤；遇到审批、缺输入、预算或故障保持可见状态。后台运行允许切换页面，用户确认完成 Goal，模型不自动声明目标已完成。
- 本地定时任务已获本次用户请求授权，实现单次/24 小时/7 天调度。关闭桌面不会在云端继续执行；下次启动处理到期任务，未知写操作继续等待人工对账。
- 首次启动需完成模型配置，教材可稍后添加；当前用户配置已完成真实链路测试，完整发布验收仍需上述门槛。
