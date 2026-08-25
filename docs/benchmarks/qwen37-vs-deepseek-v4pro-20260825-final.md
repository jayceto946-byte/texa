# Qwen 3.7 Plus vs DeepSeek V4 Pro 受控对照实验

日期：2026-08-25  
状态：`COMPLETE_WITH_LIMITATIONS`

## 1. 结论先行

本次结果支持把 **Qwen 3.7 Plus 作为 Texa 默认 learning-agent reasoning model 试运行**，DeepSeek V4 Pro 保留为回退和短答案对照模型；但这不等于把 Qwen 原生视觉直接提升为精密教材题的可信默认路径。

在没有 Qwen 专属 prompt engineering、两边使用相同消息、`temperature=0.1`、请求 `max_tokens=4096` 的条件下：

- 普通教材 RAG 必需事实点召回：Qwen `96.3%`，DeepSeek `92.6%`（各 9 个可自动评分回答）。两边均未生成不存在的 E-id。
- 75 条文本回答中，Qwen `0` 次空答、`0` 次 length finish；DeepSeek `3` 次空答、`5` 次 length finish。三次空答都发生在长会话第 10 轮，4096 个输出 token 全是 reasoning。
- 12 轮学习 session 中实际进入模型的 9 轮 × 3 次：Qwen 总延迟中位数 `22.372s`，DeepSeek `42.290s`；Qwen 的长会话稳定性明显更好。
- 全部文本样本中位总延迟几乎相同：Qwen `19.339s`，DeepSeek `19.508s`；TTFT 也几乎相同（`0.909s` vs `0.904s`）。
- Qwen 回答更长：正文字符中位数 `440` vs `277`。工具结果续答中这个差距更明显，且 Qwen 更常出现泛化鼓励语，解释密度偏高。
- 结构化输出经 Texa 当前“提取首尾花括号”解析均为 `12/12`；若严格把整个响应直接交给 `json.loads`，DeepSeek `12/12`，Qwen `11/12`，后者有一次包了 Markdown JSON fence。
- Qwen 原生视觉 3 次均完成，但数值题 3 次都将正确的约 `492.4–492.5℃` 算为约 `490℃`。Kimi K2.5→DeepSeek 链路 3 次均成功提取 VisualProblemIR，但 DeepSeek 在相同 4096 上限下 3 次都只输出 reasoning、正文为空。

所以，Qwen 的优势是 **文本 RAG 与长会话的可交付性**，不是已经证明了更高的精密视觉推理正确率。若必须只选一个默认 reasoning model，本次证据倾向 Qwen；若按场景分配，应让精密图表/分度表题继续经过可验证的检索或计算链路，不能把任一视觉方案的自由生成结果直接视为可靠答案。

任务清单中一处写了“V4 Flash”，本实验按任务主体比较的是 **DeepSeek V4 Pro**，没有把 Flash 历史数据混入结果。

## 2. 当前 Teaching Prompt 架构审查

主链为：`backend/api/chat.py` → `graph/main_graph.py` → `graph/planner.py` → 检索/章节子图 → `graph/generator.py`。

| 场景 | Prompt / 行为来源 | 最终实际行为 |
|---|---|---|
| 普通教材问答、概念、公式、计算、推导、应用、比较 | `graph/generator.py` 的 `GENERATE_PROMPT` 与 intent-specific `output_instruction` | 同一大模板叠加 intent 规则、EvidencePack、ConversationContextPack、工具结果与学习历史 |
| Teach / summarize | `graph/chapter_subgraph.py` 的 `TEACH_PROMPT`，随后进入 generator | 章节子图先生成教学内容，generator 再整合，存在教学规则重复 |
| Quiz | planner 识别 `quiz`；generator 可注入 `quiz_questions` | 主路径没有稳定的独立 quiz schema 生成器；自由文本 quiz 不能冒充结构化能力 |
| Follow-up / conversation resolution | `backend/services/session_context.py`、`resolver_reference.py` 等 | 默认先由确定性 Resolver 形成 `resolved_query`；语义 Resolver 默认关闭 |
| Evidence insufficient | Evidence gate 与 `graph/generator.py::grounded_failure_message` | 不足证据通常在生成模型前拒答 |
| Tool calling | `backend/services/tool_orchestration.py` 与工具 registry | 当前是确定性选取/执行工具，模型只负责读取冻结结果后续答，不是原生 function-calling 对决 |
| Structured intent / retrieval plan | `graph/planner.py::INTENT_PROMPT` | 独立 routing JSON prompt；为保持控制变量，没有随 Teaching Prompt 改写 |
| Vision 分离模式 | `backend/services/multimodal_bridge.py` | Kimi 生成 VisualProblemIR，再交 reasoning model |
| Vision 集成模式 | provider registry + 同一模型调用 | Qwen 原生读取图片并回答；设置页只需一个模型选项 |

### Legacy Prompt 复杂点

Legacy generator 同时规定证据边界、工具边界、穷举、引用格式、粗体、拒答、直观例子、以题讲知识点、关系题固定结构、例题自检、LaTeX 与 intent-specific 输出方式。主要问题是：

1. 多个编号重复为 `0.`，优先级不清晰。
2. “不得用模型记忆补缺”与“没有完整例题时允许构造补充例题”存在张力。
3. comparison 被固定为流程，容易把模型能力测试变成遵循模板测试。
4. Teach 子图和 generator 重复规定定义、类比、题目主线、公式与格式，增加 token 并可能二次改写。
5. subject/global prompt 又重复 LaTeX、教学结构和工具约束，维护时容易漂移。

引用协议、证据边界和工具结果真实性仍是产品合同，不能从正式路径直接删除；但不应全部成为本次无专项调优实验的系统指令。

## 3. Minimal Teaching Prompt 接入与回滚

实验系统消息严格使用指定中文版，定义在 `graph/teaching_prompts.py`：

> 你是 Texa，一个以教材为主要依据的学习助手。  
> 你的目标是帮助学习者理解概念、原理、关系、推导和应用，而不只是给出最终答案。  
> 优先依据当前提供的教材内容和检索证据回答；如果证据不足，应明确说明，不要虚构教材依据。  
> 保持与当前学习主题和前文的连续性。需要检索、计算或读取学习上下文时，可以调用相应工具。

默认仍为 legacy。仅在 `TEXA_TEACHING_PROMPT_MODE=minimal` 时，generator 与 Teach 子图切换到实验分支。Minimal 分支保留相同 EvidencePack、ConversationContextPack、工具结果和学习历史；只额外保留架构必需的 `[[cite:E…]]` 引用协议，没有加入 Qwen 专属规则、CoT、复杂教学步骤或新 routing prompt。

Legacy 代码没有删除；完整 UTF-8 源码快照位于 `benchmark_results/prompt_backups/teaching_prompt_legacy_20260825.json`。取消环境变量即可回切。

## 4. Benchmark case 与方法

夹具由真实生产检索、Resolver、EvidencePack、工具输出和 Context Eval 数据冻结得到，共 31 个 case：A=4、B=5、C=2、D=3、E=4、F=1、G=12。文本侧有 25 个 case 进入模型，两模型各重复 3 次，共 `150` 条有效文本结果；F 视觉两条路径各 3 次。C 的 2 个 case 与 G 的 3 个不足证据 turn 由生产 gate 直接处理。

固定项：

- 相同 system/user messages，逐 case 保存 SHA-256；
- 相同检索 chunks、EvidencePack、Context Pack、conversation history；
- 相同工具定义与冻结工具结果；
- 相同 `temperature=0.1`，均请求 `max_tokens=4096`；
- thinking 均开启；DeepSeek 使用当前正式 `reasoning_effort=high`；
- 每个关键 case 3 次；原始响应、reasoning/token 统计、TTFT、总延迟、finish reason、成本估算与视觉阶段 trace 均落盘。

需注意：Qwen provider 在原生视觉回答中返回了每次约 9.8k–11.1k output tokens，实际没有按请求的 4096 截断；DeepSeek 严格在约 4096 截断。实验保持了请求参数相同，但 provider 的有效限额语义并不相同，这本身属于需要纳入选型的模型特异性行为。

## 5. 分项结果

### A. 普通教材 RAG

| 指标 | DeepSeek V4 Pro | Qwen 3.7 Plus |
|---|---:|---:|
| 样本 | 12 | 12 |
| 必需事实点平均召回 | 92.6% | 96.3% |
| 至少一个合法引用 | 12/12 | 12/12 |
| 虚构 E-id | 0 | 0 |
| 中位总延迟 | 17.844s | 19.678s |
| 中位正文字符 | 314 | 485 |

Qwen 在电容动态特性 case 三次均覆盖完整事实点；DeepSeek 有两次漏点。Qwen 在压电静态 case 有一次漏点，另外两次完整。两者都能正确依赖教材证据解决问题；Qwen 略完整但更长。

### B. Conversation Resolver

上游 5 个困难追问的生产 `resolved_query` 均随夹具保存。生成结果没有出现切换到完全无关主题的案例。自动字符串评分给出 DeepSeek `94.4%`、Qwen `77.8%`，但这个差值不能直接当语义准确率：Qwen 在“电感式传感器适合高频动态测量吗”三次都明确回答“不适合、响应频率低、不宜用于高频动态测量”，评分器却因期望词是“不宜于”而将其中一次判为 0、两次判为 0.5。人工复核后这三次均语义正确。

引用协议方面，Qwen 为 `15/15`；DeepSeek 为 `14/15`。失败原文使用了 `[cite:E1]` / `[cite:E2]`，缺少双层方括号，因此不是可解析引用，但并未编造来源编号。

### C. Evidence Insufficiency

两条故意不足的教材问题均被生产 Evidence gate 在模型前拦截，输出：

> 当前导入教材中未检索到足够的直接证据，因此不使用模型自身知识补齐答案。

结果是 gate `2/2` 正确、无虚构引用，但 **不能据此声称任一模型自身更克制**。这是 Texa 系统能力，不是模型胜负；第一轮没有为了 benchmark 绕过正式证据门槛。

### D. Tool Calling

当前 Texa 工具路由是确定性的：积分 case 正确选择 `symbolic_math` + `verify_math_result`，学习进度选择 `get_recent_progress`，普通定义题保持零调用；参数与结果均正确，没有重复调用。两模型在冻结工具结果注入后都 `3/3` 算对积分，并在三次学习进度摘要中保留了 `44` 个事件与 `9` 次 QA 的关键数字。

| 指标 | DeepSeek | Qwen |
|---|---:|---:|
| 中位总延迟 | 14.222s | 24.689s |
| 中位正文字符 | 476 | 852 |
| 总 output tokens | 6,999 | 11,916 |

Qwen 在这里明显更慢、更长；其额外教学展开没有提高计算正确率。这是最清楚的“回答密度”退化场景。

### E. Structured Output

两模型的 intent、字段、字段类型与必需键均为 `12/12` 正确，没有虚构字段。Texa 当前宽容解析（提取首个 `{` 到最后一个 `}`）两边均 `12/12`；严格 whole-response JSON 为 DeepSeek `12/12`、Qwen `11/12`，Qwen 有一次把合法 JSON 包进了 Markdown JSON fence。Qwen 更快且 reasoning tokens 更少，但严格协议稳定性略逊一例。

### F. Vision + Textbook

测试图为现有 E 型热电偶教材题，四个关键答案为：A′/B′ 是补偿导线；冷端补偿在显示仪表内部；a/b 短路显示 35.0℃；普通导线替代时应查 E 型分度表并得到约 492.4–492.5℃。

| 指标 | Qwen 原生视觉 | Kimi K2.5 VisualProblemIR → DeepSeek |
|---|---:|---:|
| 完整响应 | 3/3 | 0/3 |
| 关键点平均召回 | 66.7% | 0%（正文为空） |
| 中位总延迟 | 181.294s | 113.055s |
| 中位可见 TTFT | 1.532s | 31.976s（含 Kimi 非流式前置） |
| 三次成本估算 | ¥0.259234 | Kimi ¥0.092610 + DeepSeek $0.013400 |

Qwen 三次都识别出补偿导线和 35℃，大体理解图文关系，但三次都以不可靠的温差线性近似或错误分度值推得约 490℃，而不是 492.4–492.5℃。它还一边声明图片未含分度表，一边调用未经证据提供的“标准分度值”，属于精密教材题中不可接受的外部知识补齐。

Kimi 三次都成功生成结构化 VisualProblemIR，完整提取题干、`t₁=35℃`、`t₂=25℃`、连线和“需查附录分度表”的不确定性。失败发生在后续 DeepSeek：三次各消耗 4095–4096 output tokens，全部是 reasoning，`finish_reason=length`，最终正文为空。因此本轮只能确认 Kimi 识图结构化可用，不能确认组合链的最终答案能力。为保持变量单一，没有临时提高 DeepSeek 上限或降低 reasoning effort。

### G. 12 轮真实学习 Session

Context Pack 始终有界，序列化大小约 357–432 字符，未随轮次单调膨胀。12 轮中 9 轮进入模型，3 轮因证据不足由 gate 处理。

| 指标（27 次模型回答） | DeepSeek | Qwen |
|---|---:|---:|
| 中位总延迟 | 42.290s | 22.372s |
| 中位 TTFT | 0.938s | 0.889s |
| input / output tokens | 30,501 / 60,611 | 29,640 / 39,833 |
| reasoning tokens | 55,629 | 32,689 |
| 空答 | 3 | 0 |
| length finish | 5 | 0 |
| 成本估算 | $0.054735 | ¥0.377944 |

这里的主要连续性失败来自模型之前的 Resolver，而非某个生成模型：

- 第 6 轮“第一个方法怎么算”被解析成“随机误差方法怎么算”；
- 第 7 轮“它有什么适用条件”被解析成“随机误差有什么适用条件”；
- 第 8 轮“第三个方法呢”退化成“对应方法呢”；
- 第 10 轮把当前问题与旧比较约束拼成“在给出一组测量值……对应方法和第三个方法有什么区别”。

两个模型都被错误 Context Packet 带偏。Qwen 在第 8/10 轮至少明确指出指代不清并分支回答；DeepSeek 第 10 轮三次都在 thinking 中耗尽上限而没有正文。结论是：Qwen 更能在坏 packet 下交付一个可见回答，但它不能替代 Resolver 修复，也会在分支解释中扩大 topic drift。

## 6. Token、延迟与成本

### 全部 75 条文本结果/模型

| 指标 | DeepSeek V4 Pro | Qwen 3.7 Plus |
|---|---:|---:|
| input tokens | 127,173 | 129,138 |
| cached input tokens | 119,808 | 36,992 |
| output tokens | 110,508 | 88,555 |
| reasoning tokens | 97,708 | 68,862 |
| total tokens | 237,681 | 217,693 |
| 中位总延迟 | 19.508s | 19.339s |
| 中位 TTFT | 0.904s | 0.909s |
| 中位正文字符 | 277 | 440 |
| 有效样本估算成本 | $0.099780 | ¥0.907529 |

成本按 2026-08-25 provider usage 字段和官方公开单价估算，保留原计费币种，不用临时汇率制造伪精度。DeepSeek 参考其官方 pricing；Qwen 使用北京 endpoint 的 ≤256K 档；Kimi 使用 K2.5 公开价格。账单仍以 provider 为准。

有效结果成本不等于本次操作的全部账单：首轮 checkpoint 曾被 Windows 文件占用中断，后续一次错误续跑重做了少量样本，DeepSeek 又有 24 次余额不足请求及 preflight。append-only 日志不能完整还原所有早期已计费请求，因此不伪造“实际总成本”；应以供应商账单核对。最终报告中的 150 条文本与 6 条视觉结果均可追溯且无重复计分。

## 7. 失败原文与原因

### DeepSeek 长会话空答

第 10 轮三次均为：

```text
finish_reason: length
output_tokens: 4095 / 4096 / 4095
reasoning_tokens: 4095 / 4096 / 4095
answer: ""
```

原因：高 reasoning effort 在复杂、被污染的 context 中耗尽统一输出预算，未留出最终答案。这是当前正式配置下的可交付性问题。

### DeepSeek 引用格式

```text
……不宜于高频动态测量[cite:E1]……不宜用于快速测量[cite:E2]。
```

事实正确，但没有遵守 `[[cite:E1]]` 协议，前端无法按正式引用解析。

### Qwen 严格 JSON

一次 intent-quiz 响应使用 Markdown `json` fence 包裹。内容 schema 正确，宽容解析可用，但 whole-response JSON 不合规。

### Qwen 原生视觉数值错误

三次最终均约为：

```text
E(tx,0) = E(500,0) - E(35,0) + E(25,0)
tx ≈ 490.0–490.1℃
```

关系式方向可以验证，但把热电势差近似成温度差，或使用了错误的 E 型分度表数值；正确反查约为 492.4–492.5℃。这是稳定复现的模型特异性错误，不是 OCR 漏读。

### 两模型的共同 topic drift

第 8/10 轮收到的 `resolved_query` 已错误。模型回答围绕“对应方法”“第三种方法”分支扩展，语义漂移源头是上游 Resolver；Qwen 更愿意显式澄清，DeepSeek 更容易长时间 thinking，但两者都未恢复正确的“贝塞尔法/极差法”主线。

## 8. 模型特异性行为

- **Qwen**：教材事实覆盖略高；长会话 reasoning 更少、完成率更高；正文更长；严格 JSON 偶尔加 fence；provider 对视觉请求没有执行同样的 4096 有效截断；原生视觉会在缺少分度表时用自身知识补数，并稳定得到错误数值。
- **DeepSeek**：短 RAG/工具回答更凝练，输入缓存命中显著更高；复杂长上下文和视觉 IR 在 high reasoning + 4096 限额下容易把预算全部耗在 thinking；一次引用格式不合规。
- **共同点**：简单教材证据、工具结果和结构化 intent 都能稳定处理；都无法靠生成模型自动修复错误 Resolver packet。

## 9. 最终建议

1. **默认 reasoning：Qwen 3.7 Plus。** 本次最重要的生产指标不是微小平均分差，而是 Qwen 在 75 条文本中无空答、长会话快约 47%、教材 RAG 略好，同时没有专项 prompt 调优。
2. **DeepSeek V4 Pro 保留为回退/短回答档。** 它在工具续答更凝练、缓存利用更好；但在修复 thinking 预算饥饿前，不宜作为长 session 或视觉二阶段的唯一默认模型。
3. **视觉不要因“一个模型选项”而降低证据标准。** Qwen 可作为便捷集成视觉入口，但涉及公式、表格、分度表与精密数值时，必须取得表格证据并用 calculator/确定性查表校验。Kimi→DeepSeek 当前配置为 `UNUSABLE_AT_4096_HIGH_REASONING`，不能因旧的高预算历史成功结果而宣称本轮通过。
4. **先修 Resolver，再扩大模型测试。** 第 6/7/8/10 轮的错误解析比两个模型之间的普通回答差异更影响学习连续性。修复后应复用同一冻结 harness 再跑 session 子集，不改 Teaching Prompt。
5. **上线方式：小流量默认切换，而非删除旧方案。** 保留 `TEXA_TEACHING_PROMPT_MODE` 回滚、DeepSeek profile 与原始 benchmark artifacts；观察真实负反馈、空答率、正文长度和成本后再扩大。

回答核心问题：**是的，在本次真实 Texa 文本 workload 和相同 Minimal Teaching Prompt 下，Qwen 3.7 Plus 比当前 DeepSeek V4 Pro high-reasoning 配置更适合作为 learning-agent reasoning 默认模型；但它没有证明自己是更可靠的精密 vision model。**

## 10. 可复现产物

- 原始结果：`benchmark_results/qwen37_vs_deepseek_v4pro_20260825.json`
- append-only 调用日志：`benchmark_results/qwen37_vs_deepseek_v4pro_20260825.json.results.jsonl`
- 固定夹具：`benchmark_results/qwen37_vs_deepseek_v4pro_fixture_20260825.json`
- 聚合指标：`benchmark_results/qwen37_vs_deepseek_v4pro_analysis_20260825.json`
- Legacy Prompt 备份：`benchmark_results/prompt_backups/teaching_prompt_legacy_20260825.json`
- 运行脚本：`scripts/benchmark_qwen37_vs_deepseek_v4pro.py`
- 分析脚本：`scripts/analyze_qwen37_vs_deepseek_v4pro.py`

官方价格参考：[DeepSeek API Pricing](https://api-docs.deepseek.com/quick_start/pricing)、[Qwen 3.7 Plus 模型说明](https://help.aliyun.com/zh/model-studio/qwen3-7-plus)、[阿里云百炼模型价格](https://help.aliyun.com/zh/model-studio/model-pricing)、[Kimi 开放平台](https://platform.kimi.com/)。
