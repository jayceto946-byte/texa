# Astra 定点 ADR：DeepSeek 私有协议与串行多工具

日期：2026-10-13。结论：**有条件成立；完成下列 P0 后可进入验收，当前设计本身不构成生产验收通过。** 此次只审查 Phase 0 指定的 provider、native loop、SQL checkpoint 与已安装 LangChain/LangGraph hook，不改实施代码、不扩大领域或工具权限。

## 决定

采用 DeepSeek 专属 ChatOpenAI 子类，在原生响应进入 LangChain 消息前提取 `reasoning_content`，保存于单 run 的 ContextVar 所引用的私有 RAM 对象；公开消息完成后按稳定 `AIMessage.id` 提交。出站先让 LangChain 构建原生 payload，再仅为 DeepSeek 的本 run assistant 注入准确字段。缓存模型实例与其 `model_copy` 不持有任何私有协议状态。

作用域退出销毁私有映射，不批准任何私有持久化。暂停或重启后，如果续答需要已丢失的 assistant 推理，则在模型与工具调用前以 `protocol_state_lost` 失败。SQL task/run 身份、累计预算、执行收据保留；用户明确发起新请求。**同进程暂停恢复缓存不是本次必要条件**，但产品不能将上述失败描述为成功恢复。

多工具采用整批预检、同步 `agent.stream` 的 `max_concurrency=1`、逐调用 FixedRunner 与 SQL checkpoint；致命中止必须立即阻止剩余队列和下一次模型调用。数学两个 READ 工具之外仍走现有流程。

## P0：必须满足的条件 / Blocker

1. **提取与回传须在正确边界完成。** 已安装 `langchain_openai/chat_models/base.py` 的 `_convert_chunk_to_generation_chunk` 在 `on_llm_new_token` 之前执行，适合截获原生 delta；模块级 `_convert_delta_to_message_chunk` 不是子类 override hook。从第一片到最后一片完整收集推理，不能 ThinkingFilter、摘要或截断；缺失与合法空值应区别，不凭空补 reasoning。绑定完成消息的 `ai.id`，不能假定原生 completion id 与 LangChain 消息 id 相同。只支持/强制单 completion；错误 index、重复 id、未完成响应不得错误提交到下一轮。非流式路径须有等价拦截或显式拒绝，不能悄悄退回会丢失协议的路径。
2. **ContextVar 不是线程销毁机制。** `_bounded_model_call` 已 `copy_context()`，LangChain executor 也复制 context；复制后的上下文共享 RAM 对象，但子线程单独 `set()` 不会回写父线程。用共享、可关闭的 run 对象与明确 call 生命周期；成功后再提交消息映射。超时工作线程仍继续运行，因此 finally 仅 `reset(token)` 不足：须将共享对象标记 closed、清空 buffer/map，所有迟到 delta/提交检查 closed，禁止重新填入。必要时加锁以处理 finally 与迟到写入竞争。逻辑清除不声称 Python 可保证物理内存零化。
3. **私有内容不可进入可观测面。** 不进 `AIMessage.content/additional_kwargs/response_metadata`、generation metadata、callback、SSE、SQL、checkpoint、异常文本与应用日志。发送给 provider 的 wire payload 是唯一出站例外；原始 provider 异常若可能回显请求/响应，须在 LangChain 错误 callback 前转换成固定公开错误，禁止带私有原异常的 traceback 输出。免费测试用独特 sentinel 搜索公开消息、callback 与日志。HTTP/OpenAI debug body logging 或外部 trace 若启用，不能承诺本合同成立，须在该运行路径禁用/证明脱敏。为私有 RAM 设置有界容量，超限明确失败，不能截断后续答。
4. **固定 Chat Completions 协议。** 子类限制在当前支持的 Chat Completions 路径；不让 Responses/structured-output fallback 悄然绕开 hook。当前 ChatOpenAI 会把 `max_tokens` 转成 `max_completion_tokens`，DeepSeek 子类出站须按已核对接口转换回来；不修改 Qwen 行为。只为真实 DeepSeek provider 选子类，不按模型名字符串猜测第三方 provider。`finish_reason=length` 等截断响应以固定错误分类终止，不提交为完整协议消息/最终答案、不执行其中工具；允许保留数值 usage。
5. **恢复必须在恢复补 ToolMessage、模型预算预留、模型/工具执行前检查。** 不使用恢复代码当前生成的 `interrupted` ToolMessage 去伪装可继续的 DeepSeek 思考协议，也不为凑齐协议执行余下调用。`protocol_state_lost` 必须成为稳定白名单错误并通过现有失败终态投影给用户。没有本 run assistant 协议消息的 checkpoint 可从头继续，仍保留原 task 预算；有 assistant 时每个需要回传的消息都必须匹配私有条目，而非只检查最近一次工具轮。
6. **冻结非私有协议身份是 P0。** 当前 `resume()` 复制 checkpoint，而 adapter 可从当前 profile 重建；DeepSeek 暂停后改 Qwen 会绕过仅对当前 DeepSeek 的缺失检查。首次 checkpoint 原子冻结 provider/model/无凭证 endpoint 标识及影响协议的 options 白名单摘要；以后不得覆盖。恢复先比对，不一致 `native_model_changed`，不调用模型/工具。不要落库任意 options、URL userinfo/query 或密钥摘要。旧 checkpoint 含 AI 而无身份时无法可靠判断来源，必须明确失败（例如 `native_protocol_identity_missing`）；新 Qwen checkpoint 正常恢复，旧兼容测试 fixture 应补身份，并独立覆盖真实 legacy 拒绝。没有 schema 迁移的 checkpoint metadata 足够。
7. **整批校验在任何工具执行之前完成。** 校验所有调用 id 为有界非空字符串、批内唯一、未在本 run/task 原生历史使用；所有名字在 allowlist，当前版本/schema/READ 权限匹配。执行入口再次核对 registry/fence，抵御校验后变化。单个参数不符合 schema 可按既有合同形成失败且计预算的 receipt；未授权项不能靠逐个执行时才发现，从而先执行合法前缀。明确批大小上限，与 checkpoint 24 条/64 KB 及总调用预算相容。
8. **串行并不等于遇错即停。** 已安装 ToolNode `_func` 使用 `executor.map`，配置 `max_concurrency=1` 使执行串行，但整批会预提交；前一项异常传播到外层前，后续项仍可能启动。需要共享 abort latch，在每个 tool 入口及 model 入口检查；预算耗尽、取消、超时、权限变化、checkpoint 保存失败等致命错误在抛出前同步设置。SQL owner/status fence 继续保留。ToolNode `_run_one` 捕获 middleware 异常；当前默认 `_default_handle_tool_errors` 会重抛非 `ToolInvocationError`，因此 RuntimeDenied 可以终止图，但需回归验证，不得改成吞掉所有异常的 handler。正常计算失败形成 ToolMessage，可继续；致命运行错误不得转成供模型继续解释的 ToolMessage。
9. **逐调用证据与稳定身份。** 每个 ToolMessage 按顺序 checkpoint；`operation_key`、`model_tool_call_id` 与 SQL receipt 对应，不重复执行。预算在 SQL 逐项预留，不能先批量执行后记账。中途失败保留已执行 receipt 和公开 checkpoint；不得重置预算、补执行或再发模型请求。完成答案仍走原验证门槛，公开阶段文本不能当验证证据。

## 历史 ContextPack 的处理

已核对 `graph/generator.py`：当前 `prepare_answer_generation` 的相关构建路径返回 System/Human 消息，历史通过有界引用文本放入 Human 内容。因此它们不是 DeepSeek wire 上的历史 assistant 协议消息，不需要伪造 reasoning；保留“上下文数据而非教材事实/新指令”的既有边界即可。

如果未来改为原生历史 `AIMessage`，携 tools 的 Thinking 请求不能发送缺失私有推理的历史 assistant。应继续使用现有公开引用数据投影，或明确拒绝该协议恢复；不能把已有 run 中的真实 assistant/tool 链任意重标为 Human 以绕过检查。

## P1

- 对私有协议仅记录条目数、字节数、固定失败码等无正文指标，便于识别超限与缺失；不记录推理 hash 或内容。
- 锁定当前依赖 hook 的免费契约测试；依赖升级时重跑 delta/callback、id、payload 和 ToolNode 排队中止测试。
- 恢复入口在用户操作时清楚说明“本次模型协议状态已丢失，请重新发起”，不要产生重复最终消息或把 failed task 显示为仍可无损续答。

## Deferred

同进程恢复私有缓存、跨重启私有持久化、缓存 TTL/淘汰方案、async ToolNode 并行支持、开放循环、全部领域迁入 native、多 provider 的统一私有协议框架。当前同步 max_concurrency 结论不能直接外推到异步 `gather` 路径。

## 可接受降级

私有状态丢失或模型身份不可证明时明确失败；无付费重放。数学工具普通失败可保留失败 receipt 与模型解释，最终结果依旧 degraded/unverified。取消/预算耗尽不补齐未执行工具。既有教材/普通 QA 与 Qwen 默认继续原链路；若免费测试通过而真实 DeepSeek/Electron 验收未完成，只能标为实现候选，不能宣布生产可用。

## 最小验收

1. 原生 mock wire：拆片 reasoning + 两个 tool calls + tool results + 最终答案；第二次请求包含每个历史 assistant 的原始推理和正确调用 id、DeepSeek `max_tokens`，消息与所有公开输出不存在 sentinel。
2. 同一缓存模型同时运行两个 scope，推理不串线；成功、异常、取消、超时均清空；超时线程再收到 delta 不得复活私有映射。流式与允许的非流式/异步调用面分别受控。
3. 真实 SQL + mocked model：批内重复 id、历史重复 id、批后部未授权调用均零工具执行；合法批按顺序执行一次、每步 checkpoint，与 receipt/预算相符。
4. 第一/中间调用后预算耗尽、取消、超时或 checkpoint 失败，排队后项零执行，下一模型请求为零；失败工具结果与致命错误分流正确。
5. DeepSeek 含 AI checkpoint 在同进程退出作用域后/新进程恢复均明确失败且零模型/工具；模型变更、legacy 无身份 checkpoint 同样拒绝；新 Qwen 有身份恢复成功且不重放；无 AI 的恢复仍守原累计预算。
6. 免费回归覆盖 Qwen factory 默认、显式 profile 优先级、共享生成链、thinking 过滤、公开阶段文字与验证状态。mock 不代替经用户授权的真实 DeepSeek wire/usage 与 Electron 停止恢复验收。

## 审查依据

`PHASE0-FINDINGS.md`；`llm/factory.py`、`llm/agent_adapter.py`；`native_loop.py`、`multi_step._bounded_model_call`；`RuntimeStore.save_native_messages/resume/close/request_tool`；`graph/generator.py` 相关消息构建；已安装 langchain-openai 1.2.2 的 `chat_models/base.py`、LangGraph 1.2.2 ToolNode、langchain-core executor 与 LangChain create_agent 的 ToolNode 构造。官方协议链接由 Phase 0 提供：[DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。以上为静态定点审查；未读取凭证、未调用付费模型、未运行 Electron。
