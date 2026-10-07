# GPT-5.6 Sol：Texa Agent Runtime P0 实施交接

本文件是一份待执行任务说明。当前只完成架构审计和 RFC，没有实现 Runtime。主 RFC：`docs/agent-runtime-rfc.md`。

## 目标与边界

实现最小持久执行内核：canonical contracts、现有 ToolRegistry 的兼容扩展、SQLite AgentRun、现有 ExecutionEvent V1 的原子持久化集成。

P0 完成后可以在隔离数据库中用 service-level 测试执行零/一个只读工具，并恢复读取状态。生产聊天默认仍走旧链路；不接管 UI，不创建第二个 Agent 页面/API 回答入口，不调用真实模型。

这是架构和新数据库变更。开始前确认当前用户实施指令已明确授权 P0；仅有“阅读 RFC”不构成实施授权。不要沿用文档中的历史测试结果代替本轮测试。

## 先读这些代码

- `backend/tools/registry.py`、`learning_tools.py`、`services/tool_orchestration.py`。
- `backend/services/execution_events.py`、`learning_task.py`、`owned_stream.py`、`execution_effects.py`、`pending_actions.py`。
- `llm/types.py`、`registry.py`、`factory.py`。
- `utils/sqlite_migrations.py`、`sqlite_recovery.py`、`storage_manifest.py`。
- `tests/test_execution_events.py`、`test_execution_model.py`、`test_learning_task_state_machine.py`、`test_execution_outcomes.py`。
- `frontend/src/utils/chatActivities.ts` 与 `api/client.ts` 的 V1 validator；只读核对，本阶段不改 UI。

工作区已有用户未提交改动。先记录 git status；不清理、回滚或格式化无关文件。遵守 Python 3.10 / venv310；环境不具备时报告，不重装依赖或换解释器掩盖问题。

## 实施切片

### 1. 最小 contracts

建议放 `backend/services/agent_runtime/contracts.py`。定义 AgentRun、RunCommand、ToolCall、checkpoint/budget/error 的 typed contract，复用现有 ToolResult 的 data/evidence/verification/warnings 语义。

定义 ModelAdapter 的 Protocol 与 capability shape，但只使用 fake adapter/固定 driver。不要给现有 provider 凭空增加 tool_calling 支持，不实现 native API 调用。

固定模型动作只需 `finish` 和一个只读 `call` 的测试输入；多步骤 action union 可在 RFC 保留，P0 不编写通用循环、动态 planner 或 capability 扩张。

### 2. 扩展唯一 ToolRegistry

保留旧 ToolSpec/public_dict/call 调用兼容。新增 canonical 元数据映射：id、version、schema、permission、side_effect、source、timeout、provenance、idempotency。

只为 `get_recent_progress` 建一个严格 typed input/output wrapper；测试注入临时 LearningEventStore，不能访问真实 progress 数据。其余 legacy 简写 schema 工具不自动进入 Runtime allowlist。

该函数先限量取 learning events 再按日期过滤，返回计数不能被包装成全时间窗的完整统计。wrapper 要保留查询上限和“可能非全量”的说明；P0 不扩展成新的统计系统。

优先用现有 Pydantic 生成 schema 并验证，禁止写手工通用 JSON Schema 解释器。handler 调用前拒绝非法字段/类型、越界值、未注册工具、未 allowlist 工具与所有非 READ 权限；结果也验证。注册目录不承担授权和执行状态。

### 3. SQLite store

建议 `backend/services/agent_runtime/store.py`，路径通过构造参数显式注入；正常路径契约为 `PROGRESS_PATH/agent_runtime.db`，但 P0 不在生产 startup 自动打开。

只建四表：runtime_tasks、agent_runs、tool_calls、execution_events。runtime_tasks 使用 LearningTask 兼容 snapshot，只存新 Runtime task，不镜像旧 JSON。

必须具备：

- schema version 与显式迁移事务；支持更高版本时 fail closed。
- request_key 去重、task active run 唯一约束、revision CAS、owner_token fence。
- 工具冻结 args/hash、稳定 operation_key、result/receipt 字段。
- task/run/event 同事务 create 与 finish；checkpoint 与 tool result/event 同事务更新。
- 全量 milestone 保存及 after_seq 查询，不套用旧 40 项截断。
- read-only snapshot 接口；读取不执行工具或恢复副作用。

不改旧 SQLite 表、不导入 learning_tasks JSON、不双写状态、不删除 WAL/SHM。P0 无正式历史迁移命令。

### 4. Runner 与 V1 integration

建议 `runner.py` 与必要的 `events.py`，能少拆就少拆。只支持固定零/一工具 run：create → tool optional → finish；失败/暂停有可读快照。不要实现生产聊天编排。

用现有 ExecutionEventEmitter / validate_execution_event；语义名放 payload.lifecycle，顶层类型和枚举完全不变。P0 的事件身份仍要求真实传入非空 request/task/run/conversation/turn，测试用测试 ID。

事件持久回调在一个事务中更新对应状态/结果及事件；事务失败必须向上传播，不能继续派发或发布成功。无需新增事件总线。现有 `execution_sse_payload` 可用于测试验证 envelope。

ToolRunner 是调用 handler 的唯一新入口。P0 拒绝写操作，不实现 approvals。超时/取消不得让迟到结果更改已暂停 run；在途线程/任务数量必须有界，超时不代表物理调用已停止，不可无限生成 daemon thread。优先复用合适的现有 resource-limit 原语，避免引入新调度框架。

P0 暂停使用 running → interrupted 对应的 task 状态，关闭当前 run；恢复测试创建新 run，关联 resume_of_run_id。旧 run 不可继续写，累计预算继承。无需放宽现有 waiting_for_confirmation/cancelled transition。

启动恢复做成显式 service 方法，仅把未结束 run 标 interrupted/paused，保存恢复原因。测试调用它；生产 lifespan 集成留到 P2。不重跑模型或工具。

### 5. 验证与交付

必须新增的行为测试：

1. 零工具结束与一个真实只读 wrapper 结束，DB 重开仍可读取。
2. 相同 request_key 返回同一 run；不同 key 不重复 claim 同一 active task。
3. 创建/完成/tool-result 事务中注入失败，状态和 milestone 均不半提交，不发送成功。
4. pause/恢复后旧 owner、旧 run、迟到工具结果均不能更新新 run。
5. 进程式重开恢复将未完成 run 标 paused；不调用 handler/model。
6. schema 错误、未知工具、非 allowlist、LOCAL_WRITE/EXTERNAL_WRITE/DESTRUCTIVE 均在 handler 前拒绝。
7. timeout/异常不伪装成功；在途额度耗尽不创建额外无限 worker。
8. 同 operation_key 不同 args_hash 拒绝；READ 重试有界；跨 resume 不重置预算。
9. 完整 V1 milestone sequence 通过既有 validator；final 后无追加，SSE sidecar 无重复 lifecycle 字段。
10. seq/query 分页与 snapshot 一致，未截断持久历史。

先运行新增测试和相关既有 execution/tool/state 回归。按改动影响扩展到 chat parity/effects，不能删除旧断言以迁就新设计。不调用在线模型，不读写真实学习数据；新增 DB 的备份/manifest 生产接入验证留在 P2，不声称本轮已通过 Electron 实测。

交付内容：代码 diff、测试命令及实际结果、未验证限制、`patch_notes.md` 中新 schema 原因/影响/验证记录。无需提交或推送 Git，除非当前任务另有授权。

## 明确禁止扩大 P0

不实现 Hybrid Router，不训练模型，不接付费 API，不新增工具大合集，不修改 graph 检索/答案算法，不替换旧 task store，不实现 approval/Goal/Scheduler/Plugin/MCP，不更改页面设计，不把 `/api/agent/tools/call` 扩权成新工具执行入口。

遇到“必须迁移全部 JSON 才能继续”“必须改 V1 type 才能发事件”“必须同时改所有页面”等判断时，先检查是否越过本阶段边界。P0 可以独立通过 service 测试，不要求生产流量切换。

## 完成定义

一个小型 SQLite 执行内核可在离线隔离测试中证明状态、权限拒绝、事件和恢复一致性；旧生产链路保持兼容。把多步骤、审批和真实模型留给明确授权的 P2，而不是在 P0 中顺带实现。
