# Texa — Early Meaningful Output / Phase 1（主线 B）

日期：2026-10-13。决策：**B，轻量 Prompt 引导有可测试空间，但没有稳定提前输出的证据。暂不工程化 Commentary。**

回答核心问题：不增加模型请求，现有公开 content 流已经能够展示题目专属行动说明；但**不能据此保证在长时间 Thinking 期间、更不能保证在 Thinking 之前出现**。Stokes 的真实行动计划仍等了 56.15 秒。SSE 适配无法使尚未生成的公开信息提前到达。若一次有限 Prompt 对照仍无实质改善，应转为 C，停止这条开发，保留现有零额外请求 Progress。

本阶段远程模型请求 **0**，新增模型费用 **¥0**；未读取凭据，未启动 Runtime、数据库或 Provider 实验，未修改生产代码、配置、持久化合同或前端。以下实验是待授权计划，不是已获授权的任务。

## 1. 基线、证据身份与边界

- 共同基线：`codex/cross-module-remediation` 的 `f91633673c40cf9c353e49804e2584b64f3131cc`，创建时为最新本地 Commit；没有 fetch 或改变远程引用。
- B 分支：`codex/agent-early-output`；独立 Worktree：`/Users/jichengqian/.codex/worktrees/agent-early-output/texa`。研究开始时 B HEAD 同上述基线。报告和证据作为一个独立交付 Commit；最终 Hash 用本分支 `git log -1 --format=%H` 查验，避免把提交自身 Hash 写入其内容。
- 主工作区当时存在 native_loop/store/math_tools/adapter/前端等未提交修复及未跟踪性能证据；全部保留。没有复制、cherry-pick 或依赖主线 A 的未完成代码。未操作 A 分支。
- 基线有原生流、工具、最终验证、取消/恢复与折叠。主工作区补充版本才有 `PUBLIC_DELIVERY_INSTRUCTION`、保留阶段正文、性能字段及四种紧凑状态。**后者不能当成 B 基线已提交实现。**

读取 [真实数学验收](docs/qa/REAL-NATIVE-MATH-ACCEPTANCE-2026-10-13.md)；主工作区的 `TEXA-AGENT-LOOP-PERFORMANCE-REPORT.md` 和 `docs/qa/evidence/agent-loop-performance/paired-2026-10-13/*` 作为已完成历史验收的只读补充证据，未将其未提交生产修改作为 B 的执行依赖。随报告交付 [独立摘录与源文件 SHA-256](docs/qa/evidence/early-output-phase1/audit.json)，保存必要数字和已公开前言，不包含私有推理、凭据或完整提示。此摘录在 B 分支内自包含；原补充证据若未合并，不应假装上述路径在 B Worktree 中存在。

## 2. Qwen3.7 Plus 当前公开输出能力（B1）

2026-10-13 查阅官方页面：[模型能力和北京定价](https://help.aliyun.com/zh/model-studio/qwen3-7-plus)、[Chat 参数和流式响应合同](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions/)、[深度思考说明](https://help.aliyun.com/zh/model-studio/deep-thinking)、[Function Calling](https://help.aliyun.com/zh/model-studio/qwen-function-calling)。结论只适用于当前百炼 OpenAI-compatible Chat 路径，不从其他模型或 API 推导 Qwen 通道。

| 信息类别 | 权威来源 / 现有表示 | 公开展示边界 |
|---|---|---|
| 私有 Thinking / Reasoning | Provider `reasoning_content`，或需过滤的 think 标签 | 不展示、不改写为进度、不持久化正文；usage 数量不是思路 |
| 公开 Commentary | 普通 assistant `content` 中的一句行动说明 | 属于公开文字；目前没有专用原生 Commentary 字段 |
| 工具调用请求 | `tool_calls` 的原生 ID、名称、参数 | 结构化请求，尚未执行；参数增量不是完整、可信工具结果 |
| 工具执行结果 | Runtime 回执、匹配 ID 的 ToolMessage | 仅报告实际执行与验证状态；成功不代表整题正确 |
| 公开教学解答 | 过滤后的 assistant content 增量 | 可含工具前推导，仍可能有错误或被后续更正 |
| 最终权威答案 | 最后一条无工具 AIMessage，经 Runtime 后置验证与终态提交 | `stop` 不等于 verified；degraded/unverified 必须如实保留 |

官方合同支持 `stream`、`delta.content`、`delta.reasoning_content`、`delta.tool_calls`；`finish_reason` 说明停止、工具交接或截断，**不是** Commentary/教学/最终答案语义阶段。Qwen3.7 Plus 支持 Function Calling、Thinking 开关及 thinking_budget；后者是长度限制。官方说明思考模式先推理再回复，没有“先公开一句计划，然后继续私有思考”的时序保证。[Chat 合同](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions/)、[深度思考](https://help.aliyun.com/zh/model-studio/deep-thinking)。

同一 assistant 消息可以有 content 和 tool_calls；真实完成样本中 **8 条工具决策消息有 6 条非空公开前言**。计入后来被 harness 干扰中断的 Stokes B 时是 9/7，不能混成完成样本成功率。这里只证明同消息共存及本批流式展示，不能证明每个 chunk 都混排、出现顺序固定或有稳定公开阶段协议。

因此 Provider 能力表为：公开内容流式传递 **是**；同消息文字与调用共存 **实测是**；原生专用 Commentary **所查合同未提供**；明确教学/Commentary阶段 **未提供**；长推理前简短计划 **无合同保证、现有证据未证明**。不建议切换 API、添加标记协议或把 Responses 的结构套入当前路径。

## 3. 首次有效文字为什么迟迟不出现

旧验收模型 envelope 占总时间 99.3%–99.7%，但包含供应商响应、网络、SDK 和应用处理，不能全部叫隐藏思考。旧日志缺首原始 chunk/响应头，无法精确拆出排队与推理。

独立核对补充实验的原生消息和事件：

| 已有真实样本 | 首公开内容（消费者）s | 首最终消息内容 s | Run 总时间 s | 模型/工具 |
|---|---:|---:|---:|---:|
| 积分 A，默认 Thinking+auto | 8.625 | 24.771 | 31.913 | 3/2 |
| Stokes A，默认 Thinking+auto | 56.145 | 102.060 | 115.475 | 2/1 |
| 证明 A，默认 Thinking+auto | 8.933 | 8.933 | 17.065 | 1/0 |
| 积分 C，关闭 Thinking | 3.038 | 25.808 | 26.860 | 3/2，1工具失败 |

Stokes A 第一条 AIMessage 的公开前言是：

> 我将使用斯托克斯公式计算此曲线积分。先计算旋度，再确定曲面和投影区域。

它只有 35 个字符，却直到服务端 `output_delta.elapsed_ms=56144.49` 才出现；同 seq 的消费者收到时间为 `56145.07ms`。这些是各自计时原点的观测值，差值不能直接宣称纯网络延迟；但没有支持“SSE 缓冲几十秒”的证据。补充报告记录 Stokes A 共 5524 reasoning tokens，未记录推理正文，不能把数量映射成正在解决哪个步骤。

主要限制：Thinking 请求通常先完成本轮内部推理再生成 content；工具可引发下一轮模型，再等一段时间。提示要求的短句也可能排在长思考之后。工具前长推导还会增加可见内容长度和后续上下文。基线在发现 tool_calls 后 `on_output("", True)` 清空早期内容，是另一个真实交付问题；补充工作区已修复并验收，B 不重做，不用该修复宣称首公开时间变早。

表中“首公开”是非空增量；它不自动等于读者理解所需的完整句子。Stokes 前言本身确有题目专属意义，但旧指标未量出其完整句子抵达时间。首最终是事后识别的最终消息首字符，仍不是完成验证/发布；权威答案发布应另量到终态。积分 C 最终仅给结果、推导留在阶段文本，最终完整性 1/5，因此不能把 3 秒首公开当作可上线改善。

## 4. Runtime → SSE → ExecutionTrace 能力评估（B3）

代码链：`native_loop.py create_agent(...).stream(messages, updates)` → ThinkingFilter 过滤普通 content → runner.on_output → `chat_binding.py` 分段入队/排序 → `execution_sse_payload` 校验 → `useChat` / `mergeExecutionLifecycle` → ChatMessage / ExecutionTrace。公开正文不等 model.completed 才展示；ToolMessage 不当正文转发。

| 能力 | 基线 / 补充实现与验收 | 本阶段结论 |
|---|---|---|
| 第一条真实反馈 | context/run.created/model.started，已有 SSE；服务端早事件不等于 UI paint | 已具备，不能计为 Meaningful Output |
| 模型阶段切换 | 基线 model.started/completed；补充版标题分分析、计算、继续解答、生成 | 已有真实事件；不是私有思考子阶段 |
| 工具开始/结束 | requested/started/completed/failed 与真实回执 | 已具备，不能提前声称成功 |
| 公开正文流式展示 | 实际 LangChain 消息增量经 content 过滤和 output_delta 展示 | 已具备；基线工具交接清空缺口已由补充修复解决 |
| 等待计时 | ExecutionTrace 使用实际 elapsed 加本地墙钟刷新 | 已具备，不轮播推理阶段、不推断完成百分比 |
| 完成折叠 | native_loop artifact 控制 collapseOnComplete，可重新展开 | 已实现，macOS Electron 补充验收通过 |
| 停止/恢复/错误 | owner/run/request/seq 栅栏、停止确认、checkpoint及回执恢复、错误终态 | 后端回归和 Electron 停止/reload有证据；真实付费 Provider 断线恢复专项未覆盖 |

补充 `electron/results.json` 记录四状态、流式正文、工具失败、长空窗/计时、停止、reload，无 errors；模型有人工等待，只能证明 UI/合同。补充只读真实答案回放也不等于在线付费 SSE/paint 验收。B 本阶段只读核对代码与证据，没有新开 Electron 验收，不声称 Windows 包或所有公式布局已验证。

缺口不是新的消息系统，而是**模型尚未产生可公开的题目专属下一步**。真实工具 ID/结果可以让用户了解已做什么，无法填补第一个模型请求的长空窗。公开 content 没有 phase 标签，途中不能确定某句话最终是否属于最后消息；仍由现有最终发布合同决定权威，不引入新 parser 或状态机。

## 5. 零额外请求方案与风险（B2）

唯一建议测试的策略：在原有教学/交付 System Prompt 上加入一个可选、简短的公开行动说明要求，继续用普通 content 流。例题专属计划是公开输出创作，不能取材于 reasoning_content，不要求每轮输出，更不能生成占位话。

候选指令（不是生产修改）：

> 如果本轮需要调用工具，并且能够明确说明接下来的实际操作，可在同一条公开回复中先用一句简短中文说明本题的下一步，再发起原生工具调用；不要为了说明而新增模型轮次、虚构已完成的工作或输出隐藏思考。工具结果返回后，仅在结果支持时说明已完成的计算。最终答案仍须独立覆盖所有小问和必要推导；简单问题可直接回答。

它只能影响模型在公开回复阶段的组织，不能靠措辞重排 Provider 的私有推理/公开输出边界。现有补充 `PUBLIC_DELIVERY_INSTRUCTION` 已要求工具前可用公开正文简述实际操作，Stokes 正是在此条件下等了 56 秒；新策略与它很接近，预期收益低且不确定，不应把已有提示重新包装为创新。

同一工具结果已经真实返回后，沿用工具完成事件展示准确摘要仍是零请求，但这是 Runtime 结果反馈，不是主模型提前生成 Commentary。已有详情应继续利用，不用固定轮播、伪进度、额外动效或强制“准备完成”遮盖等待。

潜在影响需实测：新增输入/输出 tokens；公开前言与历史重复增加后续输入；模型可能延长推理以规划前言；原生调用可能省略、延后或因“先说话”而单独结束本轮，导致额外请求；短句可能预判方法、夸大核验，或者挤占最终推导。没有证据可承诺延迟不增、Tool Calling 不退化、额外 tokens 可忽略。关闭 Thinking/限预算属于 A 的配置优化，不在 B 同时实验，积分 C 的质量退化不能绕过。

## 6. 最小实验计划及待授权预算（B4）

只比较**一个候选策略**与现有公开交付提示基准，不设计第二套协议。方案 P0：保留现有 PUBLIC_DELIVERY_INSTRUCTION；P1：仅追加上一节候选指令。这样能检验短句要求是否有增量收益，而不是把“无前言提示”当稻草对照。两组同一冻结模型/端点/工具 schema/教学 Prompt/ContextPack/EvidencePack/required outputs；不读取 A 临时参数。共同基线缺少的补充提示只作为两组相同的隔离实验输入，生产文件保持不动；实验执行前冻结完整代码和 payload hash。

题目：冻结积分 A、Stokes A 的原题及交付要求，另加证明 A 作为无工具负向对照。不重组为更简单题，不给 oracle。每题每组最多 2 次，最多 **12 Run / 36 Provider 请求**（每 Run最多3模型/2工具），交错 P0/P1；第一遍共6 Run即做停止判断。无自动重试、不追加失败重跑；一次无工具证明应保持1模型/0工具。使用独立目录/SQL/日志且只有一个隔离 Runtime，不复用其他 QA 服务，避免历史 startup recovery 干扰。

固定 Qwen3.7 Plus 北京、Thinking开启、auto调用、temperature=0、parallel_tool_calls=false；保留完整答案额度 `max_completion_tokens=16384`、模型180秒/Run600秒。仅隔离实例的预算，不调整全局 Provider 或生产限制。

测量标准：

- **TTFMO**：从提交/Run开始分别记录，人工标注“第一句可理解、真实且题目专属”的公开句子抵达时间；第一字符、空白、模板状态均不算。另量工具后第一句，明确它不能解决首轮等待。
- **TTFFA**：事后根据最终无工具 AIMessage 标注其首公开字符；另记确定性验证后终态发布时间。若无完整最终答案，记失败/null，不以阶段文本补齐。
- **Total Run Time**：同一 clock 的起止；Provider发送、响应头、首SDK chunk、过滤后首content、SSE receive可额外分段，paint若未量就unknown。
- 请求数与每请求usage（input/output/reasoning）和累计费用；P1对同题P0的差值才是额外tokens。前言文字tokens可单列，但不能代替全部成本增量；缺usage保守预留。
- 原生Tool Calling合法性、ID/ToolMessage配对、工具失败与多余调用；最终小问、条件、方向、公式和推导完整性独立审阅；数学正确、来源准确、Runtime verified分开。

预注册推进条件（探索性筛选，不是统计显著性）：首遍两个工具题的完整有效句均比各自P0早至少5秒且至少20%，没有单独前言轮次、额外模型请求、工具合法性或最终完整性退化，才做第二遍；所有结果保留。最终至少3/4工具题配对达到该门槛，总耗时不比同题P0增加超过10%，累计tokens不增超过10%，证明对照不增加调用，才讨论小范围Phase2。任何关键数学/来源错误、私有推理泄露、最终缺项或增加请求即停止P1；首遍无实质提前就转C，不调参扩样追逐好结果。小样本只筛方向，不能证明普遍可靠性。

预算提交如下，**需要用户另行明确授权后才执行**：当前官方北京输入≤256k价格为输入¥2/输出¥8每百万tokens，不计缓存优惠。[官方价格](https://help.aliyun.com/zh/model-studio/qwen3-7-plus)。累计输入按实际请求UTF-8字节保守预留，上限300,000（含tools/完整上下文）；单请求字节上限25,000，防止进入更高价格阶梯；此字节上界方法也须预检适用于实际payload/tokenizer，否则停止重预算。输出预留36×(16,384+10)=590,184 tokens；总上限890,184 tokens，最坏估算 **¥5.321472，硬费用上限¥6**。发送前检查累计请求、字节、预留费；缺usage保留整次预留，不按免费释放。预期消费不是授权上限。端点/价格/模型身份变化先重预算；不继承历史实验授权。

B不请求现在执行：收益预期有限，先由用户综合A/B决定是否值得花这一次预算。

## 7. 技术决策与 Phase 2 冲突

**最终选 B；复杂 Commentary 工程暂缓。** A不成立：当前传输已经会显示合法content，没有证据表明“小范围SSE适配”能使Qwen在长思考之前公开计划。尚不直接宣称模型绝对不可能，因此允许一次轻量Prompt对照；但若用户要求“稳定在长推理期间持续提供题目专属文字”，目前证据不能满足，应按C停止开发，不通过新增复杂度掩盖限制。

Phase2只有实验达标后再协调：`native_loop.py` 的公开交付指令是可能的唯一产品修改点；与A模型调用设置/计时改动同文件冲突。`llm/agent_adapter.py`、模型工厂/registry仅用于只读确认冻结配置，B无已证明的修改需求。`chat_binding.py`、`execution_events.py`、`useChat.ts`、`chatActivities.ts`、ExecutionTrace均无新增Commentary字段/parser/状态机需求。先核对并统一落地已有阶段保留修复，不做第二套。最终答案发布与验证合同不改。

## 8. 交付与验证记录

实际新增：`EARLY-OUTPUT-PHASE1.md`、`docs/qa/evidence/early-output-phase1/audit.json`；没有修改共享核心文件、patch_notes或AGENTS（本次仅研究资产）。

免费验证：Python **3.10.21 / venv310** 只读解析原生消息与事件，独立计数完成Run工具决策 **8/6**，含中断样本 **9/7**；重建4样本首非空公开服务端/消费者时间，与既有summary一致；生成SHA-256来源身份。报告交付做JSON解析、数字一致性、Markdown相对链接和`git diff --check`。没有跑生产测试或新Electron验收，文档研究没有代码行为变化；先前93/1379测试结论属于历史验收，不记成本阶段测试成绩。

本分支独立提交，不自动合并Main/A/B、不cherry-pick、不清理原工作区或Checkpoint。交付Commit身份以Git记录及最终回复为准。
