# Checkpoint final acceptance — 2026-09-30

**CHECKPOINT NO-GO**。仅以当前 `Checkpoint Remediation Handoff` 为门槛；未引入原 audit 的 target architecture、M0–M3 或 Policy 数据完整性要求。

验收源码：`/Users/jichengqian/.codex/worktrees/ad0b/texa`，分支 `codex/checkpoint-remediation`，HEAD `d06403e` 加未提交整改。当前聊天 worktree HEAD 为旧版本 `898bec3`，因此在 `/private/tmp/texa-checkpoint-acceptance` 对 Sol 源码快照执行测试，而非测试当前聊天旧源码。未修改 Sol 的生产代码、正式数据或已有未提交工作。

唯一标准副本：[handoff.md](handoff.md)。独立校验整改 manifest 的 40 项 baseline/result 指纹一致，实际源码差异也为 40 项，无漏列差异，见 [scope-check.json](scope-check.json)。

## Remaining correctness issues

### C1 — P0-3 / F10：投影失败后的暂停重试仍会改变另一个 Goal

`LearningStateService.apply_operation` 仅以 LearningEvent 的 `source_id` 判断已应用。Goal A 的 pause 已提交、随后 `_project` 写事件失败时，该身份没有留下。随后启用同教材 Goal B，再以完全相同的 source_id 重试暂停，代码重新选择当前 active goal，实际将 B 也暂停。

- 定位：Sol `backend/services/learning_state.py:223,246–254`；`backend/services/goals/service.py:80–84`。
- 不是两个不同命令：新增测试明确重用 `same-preparation`。
- 正确行为断言：B 保持 active；实测 B 为 paused。
- [回归](test_acceptance_edges.py)：`test_pause_retry_after_projection_failure_does_not_pause_new_goal`。
- Acceptance **3 FAIL**。这是已列 preparation 幂等 failure mode 的未覆盖失败窗口。

## Regressions

### C2 — P0-2 / P1-5：已落盘 receipt 被执行合同检查阻断对账

审批写入已通过 `start_approved_tool` 准入后，交错更新 Goal objective 或确认 Goal 完成。领域写入正常提交，真实 `PendingActionStore.domain_receipt` 可读；旧 run 被 fence 后，SQL tool call 为 unknown。再次走现有 `resolve_runtime_action` 对账入口，却在 `confirm_approval → _validate_goal_run` 被旧摘要不符或 Goal 非 active 拒绝，因此无法记录已发生写入的成功结果。

- 定位：Sol `backend/services/agent_runtime/store.py:257–265,491`；`backend/services/agent_runtime/write_service.py:66–80`。
- 使用真实领域写入与 receipt，非仅 mock receipt；update、complete 两个参数均失败。
- 新增准入 guard 被同时用于既有 receipt 对账路径。这是整改引入的恢复行为回归；没有要求撤回副作用、继续旧合同或新建对账工作台。
- [回归](test_acceptance_edges.py)：`test_admitted_receipt_remains_reconcilable_after_goal_change[update/complete]`。
- Acceptance **2 / 6 FAIL**。

### C3 — P0-2 / P1-5：确认后、恢复前暂停留下假 unknown 和无操作待审批任务

`confirm_approval` 已提交 confirmed，但 `resume` 尚未开始时暂停 Goal。`_interrupt_runs` 只处理 pending approval 或 running run，遗漏 confirmed approval + paused run。结果 task 仍为 waiting_for_confirmation，call 仍 awaiting_approval，没有写入准入、没有 receipt，却被 `public_task` 的兜底分支显示为 unknown，并给出空 allowed_actions、resumable=false。UI 无确认、取消或继续入口，重新启用 Goal 后仍无法通过正常“开始执行”推进该任务。

- 定位：Sol `backend/services/goals/service.py:118–127`；`backend/services/agent_runtime/locator.py:31–45`。
- 原有 interleaving test 只断言暂停与写入次数，没有断言最终 task/approval 状态。新增断言揭示错误。
- [回归](test_acceptance_edges.py)：`test_pause_after_approval_before_resume_does_not_leave_fake_unknown`。
- 新 unknown 投影将可确定未执行的审批归为不确定写入，并移除了操作入口；Acceptance **2 / 6 FAIL**。

## Scope violations

**未发现。** 逐一对照 remediation-only patch：新增短准入锁、Goal 摘要、SQL 一致读、局部容量限制、投影身份检查均对应 handoff。未新增数据库迁移、第二份生命周期权威、通用 recovery/executor、训练基础设施或多层 fallback。未将此前错题/UI 未提交改动算作本轮整改。

Defensive debt **PASS**：DomainCapabilitySpec、BoundedFallback 与孤立 fallback helpers/注入分支实际删除；fake MCP/schedule harness 原文件内容移至 tests；Planner/Generator/Feedback 的 TypeError 二次调用删除；任意首章 fallback 删除；生产 run_offline 更名 run_bounded；无消费者 append_outcome 写入口删除且历史表保留。未用新的 capability/fallback abstraction 包装被删代码。Goal.plan、receipt、owner fence、outbox、EvidencePack、同范围检索降级与历史兼容保留。

## P0/P1 逐项结果

| Handoff 项 | 结果 | 本轮证据 |
|---|---|---|
| P0-1 数值验证 | PASS | 两个原反例均 unverified，现有 verifier 回归通过 |
| P0-2 生命周期准入 | FAIL | origin/旧合同 fence、标题/pause-reactivate、保存失败安全态通过；C2/C3 失败 |
| P0-3 preparation 幂等 | FAIL | 常规重复建 Goal/事件和 resume 跳过通过；C1 失败 |
| P1-1 部分初始化 | PASS | configure/link 故障重试、旧 revision 幂等查找、Thread.start 清理、缺 worker 禁自动重跑通过 |
| P1-2 Goal 投影隔离 | PASS | 原 A/B 事件反例消失；正式 GoalStore 覆盖及独立 scope 投影回归通过；C1 属命令重试错误而非 reducer 串写 |
| P1-3 SSE/UI 版本 | PASS | 原提交 race 不再出错；SQL 读版本交错、poll 版本检查/串行化、跨 Goal 响应守卫通过 |
| P1-4 outbox | PASS | 毒项失败仍 pending、attempts 增长、后续项不饥饿、稳定 message ID 重试通过 |
| P1-5 审批真实性 | FAIL | 通常 pending/expired/unknown/executed 通过；C2/C3 失败 |
| P1-6 最小输出/输入 | PASS | Goal required_outputs 非空；结构化 missing_inputs 明确 failed；保留人工完成与现有图片题门槛 |
| P1-7 诊断语义 | PASS | 原 retention 反例消失；工具错误不裁剪活跃 run；删除两处自动 user_outcome；shadow/已有版本透传通过 |
| P1-8 调度 | PASS | 103 项覆盖、坏 due/初始化异常隔离、blocked_reason 与 due 保留通过 |
| P1-9 超时/容量 | PASS | legacy/SQL READ 跨实例容量在底层实际结束前不释放；迟到 fence 与模型 TypeError 不重复调用通过 |

## Checkpoint acceptance criteria

| # | Criterion | 结果 | 原因 |
|---|---|---|---|
| 1 | 验证真实 | PASS | F01 原反例不再 verified |
| 2 | 生命周期封闭 | FAIL | C2/C3 的审批交错仍未闭合 |
| 3 | 幂等可证 | FAIL | C1 同一暂停请求重试改变 B |
| 4 | 投影一致 | PASS | Goal reducer 隔离、SQL final/snapshot 一致与 UI 版本保护；审批特殊状态问题列于 6 |
| 5 | 故障隔离与容量 | PASS | outbox、103 Goals、worker 存活和实际在途容量回归通过 |
| 6 | 持久结果与不确定写入 | FAIL | C2 有 receipt 无法对账；C3 未执行被误报 unknown |
| 7 | 诊断诚实 | PASS | best-effort 明示、retention/用户结果/shadow/版本语义通过 |
| 8 | 验证覆盖 | PASS | 本轮全量后端/前端/Electron 与独立故障验收已执行并记录；没有以旧测试替代 |
| 9 | 范围收口 | PASS | 40 项差异和指纹核对，无越界设计或用户数据修改 |

## 实际执行记录

- Python **3.10.21 / venv310**：全量 `python -m pytest -q` **950 passed**，[backend.log](backend.log)。首次未复制 dist 时 SPA fallback 失败，完成当前源码 build 后重新全量运行通过。
- 前端 Vitest：**26 files / 126 passed**，[frontend.log](frontend.log)；TypeScript + Vite build 和全量 ESLint 通过，[build.log](build.log)、[lint.log](lint.log)。保留既有 mixed import / chunk size 提示。
- Electron `node --test desktop/*.test.cjs`：**7 passed**，[electron.log](electron.log)。main/preload/runtime/appearance 四个入口 `node --check` 通过。首次回环 bind 被沙箱限制，经工具批准后重跑通过。
- 新增正确行为回归：[test_acceptance_edges.py](test_acceptance_edges.py)，**1 passed / 4 failed**，对应上述三类问题（C2 两个参数），[edges.log](edges.log)。未用 xfail 或改生产代码消除失败。
- 原 `repro.py` 原样执行在“旧 Goal 合同恢复被正确拒绝”处提前停止，[original-repro.log](original-repro.log)。随后用 [repro_after.py](repro_after.py) 保留原场景、接住现在预期的拒绝，并将 SSE 注入点移至当前 stream_snapshot；13 个范围内原缺陷均 `reproduced=false`，[repro-after.log](repro-after.log)。bridge 已改为纯解析，幂等的真实 apply 操作由现有整改测试及新增 C1 验证。原空合同直接调用和 best-effort flush 丢事件仍可观察；前者由生产 Goal derive_required_outputs 解决本次要求，后者明确不作为 checkpoint 阻塞项。
- 真实 Electron，源码 build、真实 API/SQL/JSON/receipt，假 adapter/generator，隔离 userData/data：点击审批、读持久结果、两 Goal 切换、运行中暂停；1024/1366/1720 宽度截图检查通过。[electron-ui.log](electron-ui.log)。expired/unknown 无确认入口；关闭 Electron 和独立测试后端、重开后同一 run 为 interrupted，显式继续可用，[electron-restart.log](electron-restart.log)、[restart screenshot](electron-restart.png)。首次 restart 脚本因测试使用错误 UI 文案而等待超时，修正定位器后通过，未改生产代码。
- 桌面验证使用临时后端生命周期 harness，复用真实 shutdown/recover_unfinished；没有声称完成生产安装包升级、Electron 托管后端全部路径或真实模型质量验收。没有调用付费模型、迁移正式库、重装依赖。测试进程已关闭。

重跑新增回归（将 PYTHONPATH 指向本轮 Sol 源码或其完整快照，而非当前聊天旧源码）：

```sh
ENV_PATH=/dev/null DATA_DIR=/private/tmp/texa-acceptance-edges \
PROGRESS_PATH=/private/tmp/texa-acceptance-edges/progress \
PYTHONPATH=/private/tmp/texa-checkpoint-acceptance \
/Users/jichengqian/Documents/ChatGPT/texa/venv310/bin/python -m pytest -q \
/Users/jichengqian/.codex/worktrees/7617/texa/docs/validation/checkpoint-final-2026-09-30/test_acceptance_edges.py
```

结论仅为 **CHECKPOINT NO-GO**，阻塞项为 C1/C2/C3，不附加 Policy 或新 Runtime 设计要求。
