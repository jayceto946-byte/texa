# Agent Runtime v0 冻结契约

发布标签：`agent-runtime-v0`。机器基线：[agent-runtime-v0.json](agent-runtime-v0.json)，回归入口：`tests/test_runtime_v0_contract.py`。本基线冻结当前实现，不引入第二套 AgentRun/ToolCall 类型；它们分别由 SQL 表及 RuntimeStore snapshot 表达。

## 数据与接口边界

| 契约 | 当前权威与约束 |
|---|---|
| AgentRun | `agent_runs`，SQLite schema 3。task/run/request/root/resume 身份稳定；request_key 唯一；owner token + revision fence 所有活跃写入；累计工具/模型预算归属 task，不随恢复重置。snapshot 附加解析后的 checkpoint/output。owner_token 与内部 JSON 列属于服务内部接口，不作为前端公开契约。 |
| ToolCall | `tool_calls`；`(task_id, operation_key)` 唯一；冻结工具 id/version/schema_hash、参数与参数摘要、permission。requested/executed run 分开记录；未知写操作仅能对账，不能重放。snapshot 附加 args/result。 |
| ToolResult | success、data、message、pending_action、evidence、verification、warnings。data 必须经所选工具输出 schema 校验；成功不是最终答案正确性的证明。pending_action 仅是提案，不能冒充已执行的写入。 |
| ExecutionEvent | `texa.execution/v1` 保持兼容；v2 增加稳定 origin。每个 run 的 seq 单调递增，事件身份不可跨 run 混用；完整身份、类型与状态集合见 JSON 基线。仅公开阶段摘要，不包含隐藏推理。output_delta 不持久化；state_transition/tool_result/final/error 是持久里程碑。 |
| ToolRegistry | canonical runtime metadata 包含 id/version、输入输出 schema、schema_hash、permission、side_effect、source、timeout_ms、provenance、idempotency。缺少 canonical schema 的旧工具不能直接进入 Runtime；候选引用冻结 id/version/schema_hash，执行前重新验证。 |

只读执行、审批、暂停、恢复、未知写入对账、outbox 都服从同一 SQL authority。已经归属 Runtime 的任务不能因为异常转写 legacy JSON。主聊天、显式 Goal、local schedule 共用此契约；Goal/schedule 不伪造会话或 turn。

## 变更规则

修改字段、枚举、事件身份、schema hash 算法、幂等语义或持久状态转换，应增加新版本契约、兼容策略及迁移测试。不得只更新基线 JSON 来消除回归失败。新增工具需显式版本与 canonical schema，已有工具 schema 变化需更新 version；发布前同时检查冻结候选失效行为。

SQLite 迁移由版本门槛执行，重复打开不是重复 ALTER。v1/v2 → v3、重复打开与数据保留通过临时数据库测试；比实现更新的数据库拒绝打开。未对用户实际数据库进行发布迁移演练。

## 实际验证范围

- 全量 Python 回归、前端 tests/typecheck/lint/build、Electron runtime 单元测试；具体本次统计见 patch_notes。
- 真实 Qwen 请求：文本、合法原生工具调用、目标 JSON 整理、1 次工具/3 次模型的 Goal Runtime、公开教材图视觉 IR、图片推理解题与缺附表 blocking input。
- 临时数据覆盖审批/领域收据/备份恢复与 fence；这些不代表真实用户领域写入已验收。

尚未验证：生产教材索引与真实教材黄金集、20/40/80 轮人工评分 Answer Eval、真实定时到期执行、原生 Electron 停止/断线/恢复完整交互，以及真实 MCP/插件装载。默认生产聊天 Runtime/Router 接管关闭。`agent-runtime-v0` 是已验证内核与小样本链路基线，不能解释为全部 P0–P4 发布验收完成。
