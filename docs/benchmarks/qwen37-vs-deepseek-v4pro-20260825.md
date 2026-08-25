# Qwen 3.7 Plus vs DeepSeek V4 Pro 受控对照实验

> 本文件是在线运行前的审查快照。完整在线结果与最终建议见 `qwen37-vs-deepseek-v4pro-20260825-final.md`。

日期：2026-08-25  
状态：`BLOCKED_QWEN_CREDENTIAL`（离线审查、Minimal Prompt、固定夹具已完成；尚未产生在线模型胜负结论）

## 1. 结论先行

当前不能诚实回答“Qwen 3.7 Plus 是否更适合作为 Texa 默认 reasoning model”：运行环境已配置 DeepSeek V4 Pro 与 Kimi K2.5，但未配置 Qwen/DashScope 凭据。为避免只消耗 DeepSeek 配额并得到不可比较的单边数据，本轮没有调用任何付费模型，新增实验成本为 0。

在取得 Qwen 凭据前，不建议改变默认模型。现阶段唯一可辩护的临时结论是：保持 DeepSeek V4 Pro 默认，并把 Qwen 3.7 Plus 的默认/分档决策标为待实验，而不是把缺失数据解释为模型失败。

用户结果清单第 5 项写了“V4 Flash”，但本实验按任务主体统一使用 **DeepSeek V4 Pro**；Flash 的旧结果只可作为历史背景，不混入本次评分。

## 2. 当前 Teaching Prompt 架构审查

主链为：`backend/api/chat.py` → `graph/main_graph.py` → `graph/planner.py` → 检索/章节子图 → `graph/generator.py`。

| 场景 | Prompt / 行为来源 | 最终行为 |
|---|---|---|
| 普通教材问答、概念、公式、计算、推导、应用、比较 | `graph/generator.py` 的 `GENERATE_PROMPT`、intent-specific `output_instruction` | 同一大模板叠加不同 intent 规则、EvidencePack、ConversationContextPack、工具结果和学习历史 |
| Teach / summarize | `graph/chapter_subgraph.py` 的 `TEACH_PROMPT`，随后进入 generator | 先生成章节教学内容，再由 generator 二次整合，教学规则有重复 |
| Quiz | planner 识别 `quiz`；generator 可附加 `quiz_questions` | 主路径目前没有稳定的独立 quiz schema 生成器；不能把自由文本 quiz 当作结构化能力 |
| Follow-up / conversation resolution | `backend/services/session_context.py` 等确定性 Resolver；可选 `semantic_resolver.py` | 默认语义 Resolver 关闭，指代解析大部分在模型调用前完成 |
| Evidence insufficient | retrieval/evidence gate 与 `graph/generator.py::grounded_failure_message` | 多数不足证据案例在调用生成模型前确定性拒答 |
| Tool calling | `backend/services/tool_orchestration.py` 与 registry | 当前是确定性选择/执行工具，不是两个模型原生 function calling 竞赛 |
| Structured intent / retrieval plan | `graph/planner.py::INTENT_PROMPT` | 独立结构化 routing prompt；为控制变量，本轮不随 Teaching Prompt 改写 |
| Vision | `backend/services/multimodal_bridge.py` | 分离模式是 Kimi 视觉解析后交给 reasoning model；集成模式由单一原生视觉模型处理 |

### 复杂与冲突点

Legacy generator 同时规定教材证据边界、工具结果边界、穷举、引用格式、粗体、拒答、直观例子、以题讲知识点、关系题固定结构、例题自检、LaTeX 和 intent-specific 输出方式。主要问题是：

1. 多个编号为 `0.` 的规则和 intent 规则重复，优先级不清晰。
2. “不得用模型记忆补缺”与“证据没有完整例题时允许构造补充例题”存在张力。
3. comparison 被规定为固定教学流程，容易把模型能力测试变成遵循流程测试。
4. Teach 子图与 generator 重复规定定义、类比、题目主线、公式和格式，增加 token 并可能二次改写。
5. subject/global prompt 又重复 LaTeX、教学结构和工具约束，维护时容易漂移。

这些规则并非都错误；引用协议、证据边界、工具结果真实性属于产品合同，不能简单删除。但它们不适合全部作为本次“无专项调优”的模型对照条件。

## 3. Minimal Teaching Prompt 接入

实验系统消息严格使用任务指定的中文文本，定义于 `graph/teaching_prompts.py`。默认仍为 legacy；仅当环境变量 `TEXA_TEACHING_PROMPT_MODE=minimal` 时，generator 与 Teach 子图切到 Minimal Prompt。

Minimal 模式保留相同用户问题、ConversationContextPack、EvidencePack、工具结果和学习历史。Human message 只额外保留一个架构必需的引用协议：引用必须使用真实 `[[cite:E…]]`，不得编造编号。未增加 Qwen 专属规则、CoT、教学步骤或新的 routing prompt。

Legacy 分支没有删除，完整源码快照保存在 `benchmark_results/prompt_backups/teaching_prompt_legacy_20260825.json`，可通过取消环境变量立即回切。

## 4. Benchmark 设计与固定条件

离线夹具来自真实生产检索、Resolver、EvidencePack、工具执行结果与现有 Context Eval 数据。共 31 个 case：A=4、B=5、C=2、D=3、E=4、F=1、G=12；其中 25 个需要模型调用，其余是确定性拒答或 unsupported 记录。

固定条件：temperature `0.1`、最大输出 `4096`、每个关键 case 重复 `3` 次；每个 case 的消息体保存 SHA-256，两模型必须收到完全相同的 system/user messages。检索和工具只运行一次，其结果冻结后复用，避免并发索引波动污染模型比较。

评分不只给总分：

- A：必需事实点、引用合法性、虚构引用、是否解决问题。
- B：Resolver 的 resolved query/引用实体单独记为系统指标；模型只评回答是否沿用正确主题、有无漂移。
- C：区分“上游 gate 正确拒答”和“模型面对部分证据是否克制”。
- D：确定性工具选择、参数、重复调用属于系统指标；模型比较工具结果注入后的解释与警告保真。
- E：JSON parse、schema、字段/类型、虚构字段。
- F：使用现有教材热电偶截图；Qwen 原生视觉与 Kimi K2.5 视觉解析 + DeepSeek V4 Pro 推理分别保存阶段耗时、tokens 和结果。
- G：12 轮同章 session，保存每轮 resolved query、EvidencePack、Context Pack、输入/输出 tokens、延迟和成本。

脚本默认仅 dry-run；在线必须显式传入 `--online --confirm-paid-model`，并且两边凭据齐全，否则拒绝运行。

## 5. 当前分项结果

| 分组 | 已完成 | 模型对照结果 |
|---|---|---|
| A 普通教材 RAG | 4 个真实检索夹具和预期事实点 | 未运行，Qwen 凭据缺失 |
| B Conversation Resolver | 5 个困难追问，含“前者”“条件呢”“怎么算”等 | 上游确定性 trace 已保存；模型生成未运行 |
| C Evidence Insufficiency | 2 个不足证据案例 | 生产 gate 均可在模型前拒答；这不是模型优劣证据 |
| D Tool Calling | calculator / learning state / no-tool 固定结果 | 工具路由是确定性系统层；模型续答未运行 |
| E Structured Output | 4 个 planner JSON case | 未运行 |
| F Vision + Textbook | 已确认真实教材截图和现有路径 | 未运行；不会为 benchmark 临时重构视觉架构 |
| G 12 轮 Session | 12 轮固定会话，9 轮进入模型、3 轮因证据不足拒答 | 未运行 |

因此目前没有 Qwen vs V4 Pro 的有效成功率、失败原文、token、latency 或 cost 数字，也没有足够证据判断模型特异性行为。任何数值填充都会是伪造。

## 6. 成本口径

实际在线结果将优先采用 API usage 字段计费；若 provider 不返回可计费明细，再按官方单价估算并明确标注。DeepSeek V4 Pro 与 Qwen 3.7 Plus 的输入缓存口径不同，不能只拿总 token 乘一个统一价格。视觉组合还要拆分 Kimi 视觉阶段和 DeepSeek 推理阶段，避免掩盖双调用成本。

本轮实际 API 调用数为 0，实际新增成本为 0；TTFT、总延迟和线上 token 均为 `N/A`。

## 7. 运行前缺口与最终决策门槛

缺口只有 Qwen 凭据。应在 Texa 模型设置中配置 Qwen，或在进程环境中配置 `LLM_CREDENTIAL_QWEN_API_KEY` / `DASHSCOPE_API_KEY`；不要把密钥写入 profile、报告、夹具或聊天消息。

凭据就绪后执行：

```powershell
$env:TEXA_TEACHING_PROMPT_MODE = "minimal"
.\venv310\Scripts\python.exe -B scripts\benchmark_qwen37_vs_deepseek_v4pro.py --online --confirm-paid-model
```

默认模型变更必须同时满足：真实教材事实/引用不退化，Resolver 后续回答不漂移，不足证据不伪装教材来源，结构化输出稳定，12 轮 session 的 token/延迟/成本可接受。若 Qwen 只在原生视觉占优而文本 RAG/长会话没有优势，更合理的结论是分场景模型，而不是全局替换。
