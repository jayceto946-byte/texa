# Phase 0 — 2026-10-13

基线：`codex/cross-module-remediation` / `f91633673c40cf9c353e49804e2584b64f3131cc`，以当前未提交工作区为准。原差异保全于 `/private/tmp/texa-pre-deepseek-production.patch`；不 reset、stash、合并 main 或改实验冻结件。Python 3.10.21；langchain 1.3.2、langchain-openai 1.2.2、core 1.4.0、langgraph 1.2.2。旧实验 archive 不是当前完整代码。没有读取凭证或启动付费请求。

## 已有能力

- factory/registry/configuration 统一模型入口；Qwen3.7 Plus 默认不变。
- Chat binding → BoundedAgentRunner → NativeToolAdapter → create_agent → middleware → FixedRunner → SQL Runtime → SSE；数学原生 loop 已存在，普通教学/教材回答走共享生成链，不需要另建 Runtime。
- SQL task 累计模型/工具预算、owner/revision 栅栏、operation_key、ExecutionEvent、暂停/恢复、outbox 最终投影。原生公开 assistant/tool 消息及调用 ID 在 checkpoint 中保留。
- READ allowlist、schema/version、作用域、隔离数学超时/取消、确定性最终验证、ThinkingFilter；现工作区新增公开阶段正文保留和计时必须保全。

## 缺口与实际差异

1. ChatOpenAI 的 `_convert_delta_to_message_chunk` 与 `_convert_dict_to_message` 不提取 reasoning_content；`_convert_message_to_dict` 也不回传。需同时覆盖入站及出站，单在 loop 读取 AIMessage 无效。
2. Harness 的 PrivateTranscript 完整保留私有推理，仅 RAM；正式 `_protocol` 正确排除私有 metadata，因此 SQL 无法原样恢复 DeepSeek Thinking 工具续答。
3. Middleware `len(ai.tool_calls)>1` 拒绝多调用。LangGraph ToolNode 默认 executor.map 可并发；仅移除此判断会让 SQL pending pointer、latest_messages 和执行顺序竞争。必须显式 max_concurrency=1，并验证全批 ID/权限，在任何执行前拒绝非法批。
4. FixedRunner 可逐调用保留收据与预算；执行失败可合法 ToolMessage 续答。预算中途耗尽必须停止模型续答，保留已执行收据，不能重放。
5. Registry 已有 deepseek-flash，但标签/Thinking 默认未明确；官方当前 alias 是 deepseek-flash，旧 deepseek-v4-flash 是兼容 alias。不得发明 deepseek-v4.1-flash API ID。
6. 原生 loop 限数学两个 READ 工具；教材/普通教学有现成 shared generation，READ 其他工具使用既有 bounded flow。此次不扩大写工具权限、不把所有领域迁入 native loop。

## 最小方案与文件

- 新增 `llm/deepseek_chat.py`：ChatOpenAI 局部子类，解析原生 delta，使用 Run 作用域 ContextVar 私有内存，把完成消息 id 映射到推理。不放进 AIMessage additional_kwargs、callback、SSE、日志或普通存储。出站仍由 LangChain 构造原生消息，只增加 DeepSeek 字段。
- `llm/factory.py` 仅 DeepSeek provider 选择子类；`llm/agent_adapter.py` 为一次原生 run 建立/释放私有作用域，cached client 不存协议状态。
- `native_loop.py` 在模型调用边界开启/提交私有轮次；全批 ID 校验；max_concurrency=1 串行 FixedRunner。SQL checkpoint 无隐藏推理，DeepSeek 私有状态缺失时在任何模型/工具调用前终止为明确 protocol_state_lost，提示重新发起。不伪造 reasoning，不自动重放，不重置预算。
- `registry.py` 明确 Flash label/Thinking high，保持 Qwen 和已保存 profile 优先级。免费回归新增 provider wire、真实 SQL/mocked model loop、恢复/取消/Qwen；无需 ChatPage 重设计或依赖变更。

## 核心风险 / Astra 裁决

A. 上述外置 RAM 作用域是否满足 provider boundary？如何避免 LangChain callbacks/线程/cached copy 泄露？
B. 当前作用域退出即释放，暂停后含 assistant 协议消息的恢复明确失败并要求重新发起是否可接受？是否需同进程续答缓存（建议 Deferred）？无私有持久化批准，不扩大 SQL。
C. 全批校验 + LangGraph max_concurrency=1 + 既有 SQL逐调用预算/收据是否充分？中途取消、预算不足保留终态、阻断下一模型调用；不为了补齐消息执行剩余调用。

官方协议已核对：https://api-docs.deepseek.com/guides/thinking_mode/ 。携带 tools 时所有历史 assistant 推理均需完整回传（即使该轮无工具），最终轮可无新增推理；历史公开上下文中无私有状态的 assistant 不得伪装为可续答协议消息。

正式验收、真实费用/usage 和 Electron 生产调用仍 Pending；Mock 不代替这些证据。
