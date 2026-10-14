# Checkpoint remediation — 2026-09-30

本轮唯一范围依据：[implementation handoff](../../pre-policy-implementation-handoff-2026-09-30.md)。原 audit 的长期架构建议没有导入实现。

实现位置：`codex/checkpoint-remediation`，当前 worktree。起始 worktree 原为 `898bec3`，缺少交接文档中的 Runtime/Goal；因此切到审计源码基线 `d06403e`，将主目录已有未提交修改复制到隔离 worktree，再实施本轮补丁。主目录源码、用户配置和学习数据未改动。`remediation.patch` 只包含本轮相对复制基线的改动，避免混入此前错题/UI 工作。

| 范围 | 实现与验证 |
|---|---|
| P0-1 / F01 | 去除任意数学工具 passed / 共享数字的数值通过路径。没有结论绑定依据时保持 unverified，不生成通用 claim engine。两个 `2+2=999` 反例覆盖。 |
| P0-2 / F02 | 单进程短准入锁协调生命周期和 SQL 提交；checkpoint 保存 objective/scope/success_criteria 摘要。先 fence 后保存 Goal；完成也 fence。Chat 只恢复 user/ui_action origin。未带摘要的旧 Goal run 可停止但不能按旧合同恢复。标题/暂停再启用不使合同失效。 |
| P0-3 / F10 | Bridge 只解析提案；Chat 用 conversation/turn/operation 身份应用，复用 Goal/event ID 与已有 LearningEvent source 索引。source 身份与 Goal revision 在同一事务保存，投影失败/重启后仍绑定原 Goal；无状态变更的暂停/完成请求也有独立 revision 身份。resume 不重做 preparation。 |
| P1-1 / F04 | 已提交请求先查幂等身份，再检查新命令 revision。修补 configure/link；已 dispatch/已调用模型的任务失去 worker 时 interrupted，禁止自动重跑。线程启动失败清理注册。未 link 的 Goal task 也参与 fence。 |
| P1-2 / F05 | 生命周期事件按 goal_id 匹配；正式 GoalStore 状态覆盖学习投影。无归属历史事件不更改其他 Goal。 |
| P1-3 / F06,F13 | SQL snapshot、events、final output 使用一个读事务；公开执行记录也来自该 snapshot。UI 串行轮询；独立列表/运行请求计数；操作前后失效旧请求；检查 task revision/run_id，跨 Goal 的迟到操作响应不覆盖当前选择。 |
| P1-4 / F07 | outbox 逐项隔离，失败保留 pending，记录 ID、error code、attempts；按 attempts/updated_at 公平处理，稳定消息 ID 避免重复投影。 |
| P1-5 / F11 | pending/expired/unknown/executed 如实投影并提供 allowed_actions；expired 只能拒绝，unknown 不可普通确认/恢复。receipt 对账只记录已准入的事实，不重新准入/恢复；保留原 executed_run_id 和已关闭事件流。未准入审批被 Goal 停止撤销时 task 为 interrupted、call 为 denied、approval 为 rejected，可继续任务，旧审批不能执行。审批组件跟随新 snapshot。 |
| P1-6 / F08 | Goal 复用 derive_required_outputs 并持久化；已知结构化关键输入缺失时 failed，不发布假成功。完成仍由用户确认。SQL Goal 未增加后台补输入恢复工作流，UI 如实说明限制。 |
| P1-7 / F03,F09 | retention 按 session/turn/run（无 run 时 request）分组，以最后已知执行状态判断终止；工具错误和另一个 run 的 final 不裁剪活跃记录。删除两处自动 user_outcome。实际采用的 decision 非 shadow；透传已有工具版本/context_versions，resume 不补造当前历史版本。RuntimeEvent 明确 best-effort。 |
| P1-8 / F12 | 分页覆盖全部 Goal；坏 due、拒绝、初始化异常隔离；blocked_reason 保存在已有 next_action JSON，保留原 due，不假推进。worker 顶层隔离。 |
| P1-9 / F14 | 保存基线源码后复现首 100 条、坏 due 终止 tick 和超时线程无共享容量（见 baseline-faults.json）。legacy READ / SQL READ 分别有进程级容量，底层实际结束才释放；保留迟到 fence。 |
| Delete / simplify / F15 | 删除无消费者 DomainCapabilitySpec、BoundedFallback、Router fallback 注入分支和 append_outcome 写入口（历史表保留）；fake MCP/schedule harness 移至 tests；去除 Planner/Generator/Feedback 的 TypeError 二次调用，调整 test double；删除解析失败任意首章选择；run_offline 改为 run_bounded。Goal.plan、历史读取、receipt、EvidencePack 保留。 |

## 本轮验证

- Python **3.10.21**，使用主目录已有 **venv310** 解释器，工作目录为当前 worktree；`ENV_PATH=/dev/null`、`DATA_DIR=/private/tmp/...`。相关后端 **207 passed**，其中新增确定性故障回归 **36 passed**。覆盖 pause/update/complete、审批的三个交错边界、保存失败、未 link/旧合同、缺 worker、初始化重试、SSE 提交竞争、毒 outbox、调度容量、缺输入、幂等和诊断语义。
- 前端 **26 文件 / 126 passed**；TypeScript、Vite build、全前端 ESLint 通过。既有 Markdown 动态/静态导入与大 chunk 提示保留，不扩大本轮范围。
- Electron **4/4 runtime 单元测试**及三个入口语法检查通过。端口测试在沙箱内 EPERM，经批准仅允许临时回环绑定后通过。这是本轮实际结果，不引用历史审计的 7 项数字。
- 原生 Electron 使用当前打包前端、真实 Goal/Chat/action API、真实 SQL/JSON 存储及 domain receipt；模型为假 adapter/generator，数据和 userData 在 `/private/tmp/texa-desktop-checkpoint`。实际点击验证两个 Goal 切换、审批确认/持久结果、正在运行时暂停、expired 无确认入口、unknown 无再次执行入口、关闭/重开后“已停止 + 继续执行”，且 SQL consumed_model_calls 未自动增加。
- 原生检查发现首次列表加载被 poll 初始化失效的回归，已拆分列表计数并重建；重载后列表和审批状态正常。第一次重开时原生连接超时/旧 Electron 无窗口，结束本轮测试进程并重开后已核对持久状态。
- 桌面重启验证使用单独启动的临时后端与真实 shutdown/recovery 函数；**未宣称完成生产 Electron 后端托管、安装包升级或全部窗口宽度矩阵的验收**。真实模型/付费 Answer Eval、真实教材语义质量、长期调度未运行。未安装/重装依赖，未迁库或改索引；使用现有依赖副本和 bundled Node。

## 边界与收口

首次交付后独立复核给出 CHECKPOINT NO-GO：发现事件投影失败后的暂停重试、Goal 合同变化后的 receipt 对账、已确认未准入审批被暂停三类问题。以下是针对该结论的修复与实测，不将本轮实现自评替代独立 GO / NO-GO 复核。

## 独立复核后的修复

- **P0-3**：source 身份保存在已有 `goal_revisions.snapshot_json`，与 Goal 状态提交原子完成；后续 revision 不继承该身份。重试先找原 revision，只重放稳定事件 ID，避免解析到后来启用的 B。无新表、索引或迁库。
- **P0-2 / P1-5，receipt**：对账先匹配冻结提案、审批 args/scope、已准入 call 和真实 domain receipt；不经过当前 Goal 合同或工具版本准入，不恢复执行、不再次调用写工具、不改变执行归属。更新 call/result 与原 checkpoint，保留已关闭事件流和 final output；后续活跃 owner 不受影响。
- **P0-2 / P1-5，确认后暂停**：同一短准入锁内拒绝 `awaiting_approval` 且从未准入的 pending/confirmed 审批；任务进入 interrupted，审批投影 rejected。`waiting_for_confirmation -> interrupted` 是明确的合法停止转换。已准入的 running/unknown 写入仍不能拒绝，真实不确定结果保持 unknown。

验证全部在当前 worktree、Python **3.10.21**、临时数据目录进行：

- 独立复核原文件原样重跑：**5 passed**（修改前已复现 **4 failed / 1 passed**）。[重跑日志](acceptance-review-rerun.log)。本地保留测试与新增守卫：[test_checkpoint_acceptance_edges.py](../../../tests/test_checkpoint_acceptance_edges.py)，**13 passed**；新增 8 项覆盖暂停/完成的投影故障和重启、后续 revision、重复 receipt 对账、原 owner/关闭事件流、后续 owner、确认和 resume 两个未准入边界的继续入口。
- 全后端 **963 passed**，6 条既有依赖弃用 warning；[完整日志](backend-full-after-review.log)。前端 **26 文件 / 126 passed**，TypeScript、Vite build、ESLint 通过；Electron **7 passed**。沙箱的回环 bind EPERM 经批准重跑后通过。bundled Node 不提供 `npm`，使用现有 node_modules 的 CLI，无依赖安装。
- 此次没有重新进行原生 Electron 点击/重启验证；此前独立复核的真实 Electron 审批、暂停、重启和窗口检查结果属于修复前验证。此次交错边界使用确定性回归和真实临时 domain receipt，重启守卫重建存储服务，不宣称为新一轮 Electron 重启验收。

可重跑：

```sh
ENV_PATH=/dev/null DATA_DIR=/private/tmp/texa-checkpoint-recheck \
PROGRESS_PATH=/private/tmp/texa-checkpoint-recheck/progress PYTHONPATH="$PWD" \
/Users/jichengqian/Documents/ChatGPT/texa/venv310/bin/python -m pytest -q \
tests/test_checkpoint_acceptance_edges.py tests/test_checkpoint_remediation.py
```

`acceptance-fixes.patch` 是相对首次 40 项交付的追加补丁；`remediation.patch` 与 `change-manifest.json` 更新为完整整改差异，仍排除此前错题/UI 工作。RuntimeEvent 仍是可丢失的诊断投影；独立数据库、legacy 路径、Goal.plan 与 `finish.answer` debt 保留。没有新增训练事实层、数据库合并、通用恢复/执行框架或 fallback。真实模型、教材语义、生产打包全面验收不在本轮结果内；Policy 工作仍须另行定范围。
