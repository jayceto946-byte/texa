# Runtime Policy V0

实现范围是确定性的候选选择基线。Policy 不生成候选、参数、答案、审批或权限，也没有 ModelPolicy、学习/训练、额外执行框架或独立状态存储。

## 合同

Python 合同在 `backend/services/decision/policy_contracts.py`；对应结构 schema 见 `runtime-policy-v0.json`。Python validator 还检查 JSON schema 无法单独表达的动作/参数一致性、上一结果的 tool_id 条件、候选 ID 唯一性、goal 不重复 request，以及 rejected outcome 不得执行。

- `PolicyObservationV0`: request 为有界文本；context 包含 resolved_query、可选 goal、当前 constraints；previous_result 是确定性的 action_kind/tool_id/status/summary；missing_inputs 和 admissible_actions 是有界列表。
- `PolicyActionV0`: `{id, kind, args}`。generate_answer/request_input 的 args 必须为 `{}`；call_tool 的 args 是 `{tool_id, input}`。input 由 Runtime 用 Registry 的原 canonical schema 验证并填充默认值。
- `PolicyDecisionV0`: 唯一输出为 `{"action_id":"a0"}`。禁止重复键、额外正文、代码围栏、类型转换和额外字段。
- `PolicyOutcomeV0`: decision_ref、validation、execution、result_refs、continuation、真实 task_status、user_feedback、goal_completion。无反馈/验收事实时最后两项为 unknown；没有 decision_correct。
- 内部 `PolicyObservationEnvelope`: observation_id、policy_contract_version=`texa.runtime-policy/v0`、payload。Policy 只接收 payload 副本。

## 投影和选择

Router 与 Policy 共用 `matching_capabilities` 的确定性匹配/优先级；投影遍历所有匹配能力并经现有 resolver 映射，绝不把 Router 单个胜出工具当作完整候选集。参数绑定仅支持 get_recent_progress、search_exercises、search_textbook 的 canonical 调用；不混入旧工具 schema 的 limit 参数。进度查询保留原默认 7 天/12 条，不猜测新的日期、过滤条件或章节参数。

候选准入检查 READ、builtin、只读副作用、schema/version、当前范围、工具预算、可绑定参数，以及同 task 的所有旧调用；成功、失败、unknown 或请求中的旧工具都不会自动重试。教材回答候选必须先有同一冻结范围的有效 EvidencePack。教材工具的 scope/index 检查由 Registry 的 `runtime_scope_check` 复用原检查，工具输入/输出 schema 与 schema hash 不变。

内部绑定与 envelope 以独立 canonical JSON 字符串冻结。每次 Policy 调用解出新对象；修改嵌套 input、constraints 或候选列表不会改变执行参数。相同 task/run、revision、执行位置、payload 和冻结绑定产生相同 observation_id；ID 只关联，执行仍依赖 owner、active run、revision、预算和实际范围复核。

0 个候选由 Runtime 返回现有输入/证据/生成失败控制路径，不调用 Policy；1 个候选 forced 选择且 Policy 调用数为零；多个候选进入 RulePolicy。规则按原 Router 优先级选择仍存在的匹配工具，随后进入原答案链；不创建动作或补参数。

## 执行与 trace

主/回退 decision_ref 从 observation_id 和 primary/fallback 固定槽位派生。strict parse 或未知 ID 最多触发一次规则 fallback；stale 环境、停止、owner/revision 改变不触发旧 run fallback，也不绕过 fence 写入旧任务。实际工具 operation key 由 Runtime 根据内部 decision_ref 生成，不用 Policy 局部 action ID，也不占用模型 step 计数。

SQL 路径复用既有 state_transition/final/error 的有限 payload：policy_decision 记录关联、source、fallback_of、validation 与耗时；policy_outcome 记录上述合同事实。拒绝与其 not_started outcome 在同一现有事件事务保存；答案 outcome 与原验证/发布 close 在同一事务保存。工具结果关联原 tool_call ID。原拒绝不会被 fallback 或最终 task completion 覆盖；fallback_used 只在离线完整捕获中根据实际 fallback_of 派生，不能根据 source=rules 推断。

`generate_answer` 进入从原 driver 提取的同一个 `_generate_answer`，继续使用原生成、thinking 过滤、验证和发布。规则不调用 start_model_step；只有实际答案生成占用原预算。执行准入在原 request_tool/start_model_step 事务内复核 revision；原 owner/Goal fence、审批、receipt、commit 与 recovery 所有权不变。

`request_input` 仅在 SQL 接管前现有澄清 checkpoint 启用：关联已有 request/task 和明确 gate 位置，forced 选择后保存有限 policy_gate 元数据及 waiting outcome。没有创建 SQL run；approval 不映射为输入；SQL 已持有且缺输入的任务仍走原失败处理。

## 接入范围

默认关闭：`TEXA_RUNTIME_POLICY_V0=0`（未设置同义）。现有 `TEXA_AGENT_RUNTIME_READ`/`TEXA_AGENT_RUNTIME_TEXTBOOK` 与主聊天接管条件仍有效。启用基线后，只读进度/习题/教材路径采用规则；不构造模型工具适配器。运行方式存于原 checkpoint，在停止/重开/恢复时保持。

普通问答在临时 Runtime harness 中验证 generate_answer 合同；主聊天原有不接管普通问答的入口条件保留。视觉、teach/summarize、write/approval、Goal/schedule 驱动、插件/MCP、存储迁移均保留原路径。答案模型入口仍存在于原生产链，本阶段验证只注入 stub，未调用真实模型，也未开启生产接线。

完整测试 Observation/原始 Decision 输出/Outcome 只进入有限离线 artifact。RuntimeEvent 仍是 best-effort 内容受限诊断，不增加字段/事件类型、不写正文或参数，不可用其缺记录推断没有 fallback，也不承诺可由它完整重放；生产关联不完整的诊断不进入本离线统计。
