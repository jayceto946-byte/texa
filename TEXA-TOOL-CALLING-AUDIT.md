# Texa Real Tool Calling：Phase 1 审计

日期：2026-10-12。范围：现状审计与无费用复现；未实施 Phase 2–5，未调用远程模型，未改模型配置、用户数据、依赖或 Gate。

## 结论与 Checkpoint

**CP1：审计完成。现有工具是真执行，现有 Runtime 能做有界多步执行，但主教学模型的原生数学工具闭环尚未接通。** 应修复现有连接与消息合同，复用 RuntimeStore、工具协议、ContextPack/EvidencePack、后置验证和 ExecutionEvent，无需另建 Agent 框架。

数学执行器名称为 `symbolic_math`，没有 `math_evaluate`。不能把改名或暴露 JSON schema 当成接通。

| 能力 | 审计结果 | 代码依据 |
|---|---|---|
| SymPy 真计算 | 已实现 calculate/simplify/differentiate/integrate/solve；integrate 支持定积分 | `backend/tools/math_tools.py:142` |
| 极限、假设与完整错误合同 | limit 未实现；符号使用默认 SymPy 假设；失败主要是 message，缺统一错误码 | 同文件 `:15`、`:142`、`:261` |
| 主聊天工具执行 | 已接通规则选择、真实执行、最多一轮固定验证补偿 | `backend/services/tool_orchestration.py:135`、`:281` 附近 |
| 主教学模型主动调用数学工具 | 未接通；生成器没有 bind_tools 或 tool_calls 循环 | `graph/generator.py:539`、`:552` |
| 原生工具调用适配器 | 已 bind_tools、解析规范化 tool_calls；调用 ID 与完整 AIMessage 被丢弃 | `llm/agent_adapter.py:32` |
| SQL Runtime 多步执行 | 已实现同 Run 多模型步骤、多工具步骤、预算与权限栅栏 | `backend/services/agent_runtime/multi_step.py:59`、`store.py:380` 附近 |
| 数学接入 SQL Runtime | 未接通：无 canonical schema、无 capability→工具映射、入口不准入 math.verify | `math_tools.py:261`、`decision/resolver.py:7`、`agent_runtime/chat_binding.py:112` |
| 工具结果返回模型 | 主聊天为提示文本；Runtime 也是数据文本，而非原生 ToolMessage | `tool_orchestration.py:248`、`store.py:480`、`agent_adapter.py:46` |
| 普通问答真实流式 | LangGraph messages 模式接收模型增量并输出 generate | `graph/main_graph.py:462` |
| Runtime 回答真实流式 | 未实现；invoke 结束、Run 关闭后合成一个完整 output_delta | `chat_binding.py:40`、`:253` |
| 流式 tool 参数聚合 | 无实现；原生 adapter 仅 invoke 后读取完整 calls | `agent_adapter.py:50` |
| 非流式 /ask 同 Runtime | 未实现；/ask 使用 LearningTaskStore + 规则工具 + run_graph | `backend/api/chat.py:1822` |
| 工具即答案 verified | 未自动等同；已有独立验证，但数学关联范围很窄 | `backend/services/answer_verification.py:198`、`:225` |

项目没有单独名为 ToolExecutor / AgentRuntime 的总入口类。等价职责分别在 Registry.call、execute_read_only_tools、FixedRunner、BoundedAgentRunner、RuntimeStore。审计按职责和实际调用链判断。

## 实际调用链

默认流式主聊天：

```text
/api/chat/stream → _chat_stream → _prepared_chat_stream
  → [未被可选 SQL Runtime 接管]
  → select_tool_calls：regex 预选
  → execute_read_only_tools → Registry.call → symbolic_math
  → verification_request → 固定 verify_math_result（最多一轮）
  → build_tool_context_pack（有界 JSON 文本）
  → run_graph_stream → generate_node
  → prepare_answer_generation（ContextPack + Final EvidencePack + 工具文本）
  → get_llm.invoke → LangGraph messages 增量 → generate SSE
  → finalize_generated_answer → Answer Verification → LearningTask 完成投影
```

这是规则执行与辅助生成，不是教学模型主动决定的工具循环。阶段进度事件不是模型 token。

可选 SQL Runtime 路径：

```text
try_chat_response（READ 开关 + capability + verified profile + candidate gates）
  → RuntimeStore.create/configure_chat
  → BoundedAgentRunner.run_bounded
  → start_model_step → NativeToolAdapter.next_action → bind_tools.invoke
  → FixedAction → FixedRunner.execute → RuntimeStore.finish_tool
  → checkpoint transcript → 下一次 next_action
  → finish → 另一次共享回答模型调用（无工具绑定）
  → prepare/finalize + verify → store.close → outbox
  → stream_run 合成完整答案 delta + final
```

`TEXA_AGENT_RUNTIME_READ` 默认 0；教材、写操作分别受独立开关控制。`TEXA_RUNTIME_POLICY_V0` 是规则 Policy 路径，不能用其成功证明模型驱动执行。

`NativeToolAdapter` 将 assistant_action 转成 assistant 字符串，其余 transcript（包括工具结果）转成 user 字符串；`FixedAction` 没有 provider tool_call_id。`finish_tool` 的摘要仅保存 tool_id/status/data 字符串，截断 3000 字符，未保留对应原生消息 ID。模型能读到结果文本，但协议关联、错误反馈和恢复后的原生上下文正确性不成立。主聊天的最终生成还会替换 adapter 的 finish 文本，增加一次模型调用。

## 免费复现与证据

新增 `tests/test_tool_calling_audit.py`，使用安装的真实 LangChain `BaseChatModel` / `AIMessage` / `ChatResult` 接口，控制响应，无网络访问。没有用 FakeAdapter 代替原生适配器。

复现序列：

```text
NativeToolAdapter + ControlledNativeModel #1
  → get_recent_progress(days=1, provider ID=native-1)
  → FixedRunner + 隔离 LearningEventStore 真执行
NativeToolAdapter + ControlledNativeModel #2
  → get_recent_progress(days=2, provider ID=native-2)
  → 同一 FixedRunner 真执行
NativeToolAdapter + ControlledNativeModel #3 → Final Answer
```

断言证据：同一 Run，consumed_model_calls=3，2 次工具均 succeeded；后两轮上下文包含 `range_days`；但没有原生 ToolMessage，没有携带 tool_calls 的历史 AIMessage，checkpoint 不含 native-1/native-2。这证明循环骨架能运行，也直接复现原生协议缺口。此探针为**缺口观察测试**，后续修复应改为正向消息合同验收；不是 Phase 5 通过证据。

其他新增探针证明：2^10 实际输出 1024；runtime_tool(symbolic_math) 抛出 no canonical runtime schema；math.verify 的候选集合为空；limit 返回 unsupported operation；“什么是导数？”无强制数学调用。

已有 `evaluation/tool_calling_eval.py` 的 40 案例 gate 测试通过，但它测的是规则路由与确定性计算验证，文件自身明确不评分 LLM 答案质量。不能当作真实 Tool Calling 或模型自主循环验收。

执行命令：

```sh
venv310/bin/python -m pytest -q tests/test_tool_calling_audit.py tests/test_tool_orchestration.py tests/test_agent_runtime_p2a.py tests/test_agent_runtime_chat_binding.py tests/test_tool_capability.py tests/test_answer_verification.py tests/test_chat_execution_parity.py tests/test_runtime_stream_cleanup_errors.py
```

结果：54 passed，6 条依赖弃用警告。覆盖规则数学真执行/禁止 Python 面、受控两工具三模型步骤、既有预算/模型超时、Runtime SSE 投影、验证与 /ask/stream 原有规则路径一致性。后者不代表原生 Runtime 路径一致。

补充执行 `tests/test_agent_runtime_p0.py tests/test_agent_runtime_textbook.py tests/test_evidence_pack.py tests/test_evidence_support_gate.py tests/test_execution_events.py tests/test_chat_stream_reliability.py`：114 passed，6 条依赖弃用警告。两批合计 168 passed；包括现有工具超时/迟到结果、权限、教材 Runtime 与消息增量合同测试，仍不代表未接入的数学原生链通过。

## 资源、失败与取消

- AST 白名单阻止属性访问、导入、任意函数和 comprehension；限制表达式 300 字符、AST 120 节点、数值大小及数值指数，但这些不足以约束 SymPy 求解复杂度。
- 现有两种工具执行入口均使用 daemon thread + queue deadline。超时仅停止等待，**不能杀死运算**；并发槽直到线程退出才释放。取消/断连与 run fence 防迟到写入，不等于停止计算。数学应使用可终止 worker、时间及输出预算，不能直接执行任意 Python。
- Registry.call 不验证公开 JSON 参数 schema；FixedRunner 验证 Pydantic canonical input/output。数学缺后者是接入前必须修复的连接点。
- 多步失败可进入下一轮，但 checkpoint 的工具摘要缺完整 success/message/error 语义，模型恢复依据不完整。
- `_serialized_result` 对列表尝试直接 float 转换，复数解可能失败；未求值 Integral 的 warning 用 `result is sp.Integral`，无法正确检测实例；非有限结果和解集完整性需要单独验收。
- 数学验证只验证给出的根代入成立，不证明解集完整或定义域有效；不能将该 receipt 上升为最终教学答案准确率。

## Gate、证据与验证边界

`graph/generator.py:148` 的 has_generation_support 已允许 sufficient 工具 pack 在教材证据不足时生成；`multi_step.py:156` 附近则要求教材型任务必须 has_textbook_evidence。两路径存在边界差异，不能简单移除教材 Gate 来接通数学。

工具结果目前没有教材 E-id，Final EvidencePack 来源来自教材 evidence_items，必须保持。`answer_verification.py:198` 只对 question 中出现的闭合 calculate 表达式、匹配 args 的 verifier、最终单个数值做绑定；不覆盖一般求导、解方程、积分和极限答案。Runtime `_generate_answer` 汇总工具时没有带上 args，进一步限制这条验证链。

若进入实施阶段，需先定点厘清：纯数学任务在教材工作区的可执行性如何与“按教材解释”所需证据分离；混合任务的事实缺口不能被计算成功掩盖。现有证据足以形成 Astra 定点审查题，但本轮未触发重大重构，也未创建或联络其他 chat。

## LangChain 可复用性评估

本地 Python 3.10.21；SymPy 1.14.0、LangChain 1.3.2、langchain-core 1.4.0、langchain-openai 1.2.2、LangGraph 1.2.2。无需为第一阶段新增依赖。

检查已安装源码 `langchain/agents/factory.py:create_agent` 与 `langgraph/prebuilt/tool_node.py:ToolNode`：现成 create_agent 已构建 model→tools→model/END 的条件循环，并提供 middleware、interrupt 与 streaming 能力。项目未使用这些 Agent API，目前只有自建 BoundedAgentRunner 和教学 LangGraph。

下一阶段优先做隔离技术验证：让 LangChain 承担消息与循环，工具 wrapper 仅委托现有 FixedRunner/RuntimeStore 执行；Runtime 保留唯一持久状态、身份、预算、取消、权限与发布权。LangChain checkpoint 不再建立第二套权威 task/run 状态。若 middleware/wrapper 无法满足现有 fencing，记录具体失败再决定局部适配，不直接重写整个 Runtime。此处是本地源码可行性评估，尚未验证 create_agent 与 SQL Runtime 集成。

## Streaming 与桌面展示

OpenAI-compatible factory 创建 streaming=True 的 ChatOpenAI；普通图通过 messages stream 推送增量。NativeToolAdapter 和 Runtime generate_answer 只调用 invoke，stream_run 仅实时输出执行事件，最终一次性输出回答。工具参数增量、同 Run 答案增量存储/转发仍需接入。

前端 `api/client.ts:297` 消费 /chat/stream；`components/chat/ExecutionTrace.tsx:80` 默认折叠详细过程，正文与过程组件分离。用户手动展开后完成并不会自动收起，与本次 Phase 5 要求存在差距；如需调整，应明确只影响工具 Run 的完成行为。细节包含工具信息，可保留诊断但不要放入普通状态文案。

Electron 的 `desktop/main.cjs` 托管同一 FastAPI 和 React 入口，源码未见独立工具引擎。第一阶段无运行/构建路径修改。本轮前端与 Electron仅源码核对，**未做视觉或真实 Electron 工具循环验收**。

## 后续最小修改面与验收顺序

1. 数学工具增加 canonical 输入输出、limit、变量假设、错误及可终止计算预算，复用 existing ToolSpec，不另建 registry。
2. 补 capability→math 候选及 chat ingress；概念题允许模型直接回答，不要求先算。Gate 的上述边界分歧在调整前提交定点审查。
3. 复用同 Runtime 身份，实现完整 AIMessage/tool_call_id/ToolMessage 上下文；错误结果也准确回传；受 LangChain 循环驱动，最终答案走现有 prepare/finalize，不再无故另调一次教学模型。
4. 同一执行服务同时供流式与 /ask 使用；模型增量、工具参数聚合、执行事件、取消、恢复和预算在同一 Run 下关联。
5. 免费强制验收两次真实 SymPy工具 + 三轮受控 LangChain模型；分别验证无工具、参数/非法表达式、异常、worker timeout/取消、预算耗尽、SSE顺序与错误不报成功；再做 Electron 验收。
6. 真实模型验收必须另行给出次数与成本上限并获得授权，当前零次付费调用。

## 本阶段交付限制

已完成 Phase 1 调用链审计、无费用缺口复现与 CP1；修改仅本文、审计探针、实现阶段报告和 patch_notes。Phase 2–5 的原生数学闭环、LangChain Agent 集成、流式参数聚合、/ask Runtime parity、强制数学端到端、Electron 与真实模型验收均未完成。不得把本审计的通过测试数表述为完整工具能力发布通过。
