# Texa 数学原生 Bounded Agent Loop 实现与验收

日期：2026-10-12。结论：**数学原生循环已接入主聊天，受控真实 LangChain 接口 + 真实 SymPy + 真实 Electron 开发壳验收通过；付费生产模型尚未授权测试。** 本报告不宣称全部发布门槛通过。

## Checkpoint 与修改范围

- CP1 `09d512c`：现状审计，见 [审计报告](TEXA-TOOL-CALLING-AUDIT.md)。
- CP2 `08cf3fc`：数学 canonical schema、limit、假设、精确值及隔离进程。
- CP3 `6c418db`：LangChain 原生循环、统一问答执行、SSE、纯数学边界、验证与恢复。
- CP4 `cd36765`：前端完成折叠、实际 Electron 证据、模型开始/完成身份配对及最终归档。
- CP5：2026-10-13 授权真实模型三题与无工具对照、截图与指标；有界推理等待、恢复预算冻结及取消回调修复，见[真实验收报告](docs/qa/REAL-NATIVE-MATH-ACCEPTANCE-2026-10-13.md)。

复用 ToolRegistry / ToolSpec、symbolic_math / verify_math_result、FixedRunner、RuntimeStore、LearningTask 投影、ContextPack、Final EvidencePack、prepare/finalize、Answer Verification 与 ExecutionEvent。没有新 Agent 产品页、第二套工具 registry、第二套持久 Run 状态、小模型依赖或通用插件平台。无数据库 schema 迁移、依赖安装、教材索引和用户数据修改。

主要实现：

| 模块 | 行为 |
|---|---|
| `backend/tools/math_tools.py`、`math_worker.py` | Pydantic 输入输出；calculate/simplify/solve/differentiate/integrate/limit；精确小数、复数候选、数字边界 0、显式变量假设；独立可终止进程 |
| `backend/services/agent_runtime/native_loop.py` | create_agent 驱动模型→工具→模型；middleware 只委托现有 Runtime；原生标准消息/调用 ID、结果、预算、最终发布 |
| `runner.py`、`store.py`、`multi_step.py` | canonical validation、isolated handler、Run fence、原生 checkpoint、SQL 工具回执恢复、模型步骤 ID 与瞬态 delta 序号 |
| `llm/agent_adapter.py` | 配置中的同一教学模型角色工厂；数学采用原生模型接口，不再调用另一个回答生成链 |
| `chat_binding.py`、`backend/api/chat.py` | 数学 capability 候选和准入；`/stream` 与 `/ask` 使用同一 `execute_run` |
| `math_support.py`、`graph/generator.py`、`answer_verification.py` | 冻结纯计算支持类型，教材边界保持；计算证据与教材证据独立；数学输出须绑定题目、操作、参数和 verifier |
| 前端 `ExecutionTrace` / `ChatMessage` | 真实“正在计算”状态；原生 Run 完成自动折叠，用户仍可重新查看；答案正文独立保留 |
| `desktop/backend_server.py` | freeze_support 在服务器与数据初始化前分流打包进程子任务 |

## 实际循环与状态权威

```text
主聊天 prepared turn
  → 数学能力候选 + 当前教学模型工厂
  → RuntimeStore 创建一个 task / run，冻结支持类型与预算
  → create_agent（无 checkpointer，无另一 Run 数据库）
      → model middleware：SQL start_model_step → 原生模型请求
      → 保存 AIMessage.content / tool_calls / opaque call ID
      → tool middleware：FixedRunner → canonical validation → 隔离 SymPy
      → SQL 工具状态/回执 → 对应 ID 的 ToolMessage
      → 模型决定继续工具或回答
  → finalize_generated_answer / Answer Verification → SQL close / outbox
```

LangChain 只持有单次调用的临时消息状态，SQL Runtime 是持久执行权威。模型可以直接回答，也可以多轮继续；没有固定执行“算一次再校验一次”的生产流水线。测试中的固定响应只用于可控验收。

数学候选只有两个受限工具。新 native dispatch **不接管教材搜索、其他 READ 或写操作**；这些路径保留原实现。数学调用默认 `TEXA_AGENT_RUNTIME_MATH=1`，可显式关闭。具备凭证的 OpenAI-compatible transport 可尝试原生调用；transport 支持不被当作该模型已经实测成功，原有能力验证回执仍保留。供应商不支持、输出非法或网络失败时如实终止，不切换其他模型冒称成功。

## Streaming 与身份

原生模型消息流由 LangChain 聚合分片工具参数；校验完整 AIMessage 后才执行工具。工具调用 ID 原样进入后续 ToolMessage；SQL call ID 与 model_call_id 同时保留在 checkpoint、操作键和事件中。每次模型 start/complete 使用同一 operation identity。

模型真正产生可展示文字时立即发送 output_delta。跨线程继承 contextvars，避免 invoke 在 deadline worker 中丢失 LangGraph streaming 回调。**ToolMessage 不转发为答案正文**；若模型先给出临时文字后选择工具，显式清除该轮文字。终态发送经过后置处理的完整 replace delta 与 final，正文与工具轨迹分别保留。

delta 为瞬态传输数据；序号在 SQL 预留，耐久执行里程碑和最终答案仍由现有 store 保存。`/ask` 消费同一循环直到结束，`/stream` 边运行边转发。没有借另一套非流式数学规则流程伪装 parity。

## 边界、失败与恢复

- 聊天数学 Run 默认最多 5 个模型步骤、3 个工具步骤；SQL 总限制仍是 8 / 6。请求不再额外调用回答模型。CP5 经真实复杂题超时证据，将新 native 数学 Run 的模型等待设为默认 180 秒、Run 600 秒，可配置且分别硬上限 300 / 600 秒，预算在 checkpoint 冻结。旧 checkpoint 与兼容路径保留旧值。每轮默认最多 4096 回答 token，展示文字总上限 64000 字符；授权 QA 使用额外的 16384 combined token 额度（含思考），没有静默替换生产角色配置。
- AST 白名单，不执行模型 Python。表达式 300 字符 / 120 AST 节点，参数与结果大小有界。SymPy spawn worker 使用 Unix CPU / 地址空间限制及跨平台 wall deadline；超时/取消 terminate、join，必要时 kill、join 后释放并发槽。
- 已验证超时/取消后无子进程残留。模型在下一真实 chunk 由 Run fence callback 中止迭代；等待网络首包时仍依赖 transport deadline，无法保证服务商立即终止远端计费。
- 参数不符合 canonical schema：生成预算内的 failed 工具回执，并以原生 ToolMessage 反馈模型；未知工具、并行调用、重复 ID、损坏参数协议、模型/工具预算耗尽等终止为 failed。
- 恢复先按原生 ID 查持久 SQL 工具回执，已有终态恢复真实结果；只有未完成调用才补 interruption 结果。包含修复后的 ID 去重，避免重复执行。迟到模型与工具结果不能覆盖新 Run。
- 失败重试可继续，但本轮曾出现工具失败时最终发布仍保守降级，不将失败隐藏为完全验证成功。

## Astra 定点审查与 Gate

审查确认不能把教材 Gate 替换成“有任意成功工具”。采用整条原问题和 resolved query 都匹配的 `explicit_math_only`，在 task / run 中冻结；保留教材、学科与 answer_mode 身份。

Astra 两轮定点审查提出的非数学工具泄漏、无工具数学错误完成及成功回执恢复问题已修复并加入回归。最后一次关闭确认因账户使用额度耗尽未完成，因此本报告不声明获得最终 Astra 签核。

独立、显式、完整运算可以在默认教材工作区不检索。要求教材定义、章节、页码、指定方法、混合解释、图片或缺失条件的请求仍走原证据/输入路径。显式 `requested_textbook_grounded` 仍保留教材要求；不借数学例外切换成通用模式。

纯数学交付项不要求教材 citation，evidence_support 为 not_applicable，数学结果不造 E-id。每个纯数学任务都有 math_support 检查；无工具、输入/变量/条件不匹配、错误最终数字、无匹配 verifier 时不能 completed。精确数字比对改用 Fraction，避免浮点舍入误判。

求导、积分、化简和极限的最终公式绑定仍较保守，未覆盖的表达方式会 unverified；解方程的代入验证不证明解集完整性或全部定义域。工具返回成功不是最终教学答案准确率证明，也不会自动让最终答案 verified。

## 强制验收与现场轨迹

受控 LangChain BaseChatModel、AIMessageChunk（分片 JSON 参数）经真实 create_agent、FixedRunner 与 SymPy：

```text
LLM #1 → symbolic_math(calculate, 2^10)
       → 精确结果 1024 → ToolMessage(calc-1)
LLM #2 → verify_math_result(equivalence, 2^10, 1024)
       → residual 0 → ToolMessage(verify-2)
LLM #3 → 结果是 1024。
```

同 Run 三轮模型、两次真实工具执行；下一轮上下文实际含前一轮 AIMessage、对应 ID 和 ToolMessage；最终正文没有 Runtime JSON。受控模型并非直接返回 FixedAction，更没有模拟工具执行器。

现场证据：[SQL 原生消息、执行事件与工具回执](docs/qa/evidence/native-tool-loop/runtime-traces.json)、[Electron SSE 与检查结果](docs/qa/evidence/native-tool-loop/electron/results.json)、[完成截图](docs/qa/evidence/native-tool-loop/electron/1280-final.png)。

真实 Electron 开发壳 8 项通过：preload、真实两工具三模型循环、完成折叠、1280/1024/760 无横向溢出、除零失败披露、积分停止确认、刷新后从历史打开权威答案。模型响应受控；FastAPI、SymPy、SQLite、SSE、React 与 Electron 都真实运行。修正过 QA 夹具错误读取历史问题的选择逻辑；没有通过改生产回答来迎合夹具。未进行 Windows、正式安装包或生产模型验证。

测试覆盖：常规/复数/精确小数/0 边界/limit/假设、非法表达式和参数、真实进程超时/取消回收、模型 timeout、重复 ID、模型及工具预算、无工具回答、无回执数学不得完成、原生恢复、SQL 成功提交间隙恢复、SSE 在 running 时到达、/ask-/stream 相同计数与无第二回答链。

测试记录分开陈述：

- 初次全量：**1526 passed / 48 failed**；失败全是旧 Policy 批准 manifest 的 `source_content_digest_mismatch`。
- 明确排除 `test_policy_baseline_v01.py`、`test_policy_dataset_v0.py`、`test_policy_seed_v0.py` 三个冻结身份文件：**1370 passed**；不称为全量通过。
- 后续最终数学/原生/SSE/验证/Runtime 相关回归：**111 passed**；模型身份配对后的针对性回归 **47 passed**。
- 归档前再次运行数学隔离、原生循环和答案验证：**47 passed**；`git diff --check` 通过。
- 前端 **202 passed**、类型检查 / build / lint 通过；桌面 **15 passed**。修正已有启动测试的陈旧 loading 文案断言，未修改启动生产行为。已有构建大 chunk 提示和依赖弃用警告保留。

## 遗留风险与后续授权

旧 Policy 基线批准 pins 没有更新，不能用它宣布当前代码通过旧发布评测，也不能据此断言那 48 项行为仍然正确。Astra 建议保留正确失效，后续需要独立重新审阅新源码身份，不修改历史金标刷绿。

仅数学 native 路径本轮交付；其他能力仍是旧兼容路径。最终数学验证覆盖保守、解集完整性未知、Windows 资源限制/正式冻结包、真实供应商原生参数流与取消均需进一步验收。

截至 CP4，远程付费调用 **0 次**。2026-10-13 用户授权并扩大为三道复杂题与一道无工具对照，取消先前建议的保守 token 额度。真实验收累计 11 次请求（含保留的超时）、58,222 tokens，估价 ¥0.367214，低于 ¥1 上限；完整结果、缺项、错误与截图见 CP5 报告。第二题完成真实三模型两工具循环，但教学答案仍有半径错误；第三题的工具前推导被 replace 清除、最终未重述，不能宣称教学完整性全部验收通过。后续不自动追加付费调用。
