# Texa Agent Loop Performance Report

2026-10-13 · 免费审计、局部优化、Electron 验收及用户授权的配对实验。真实实验已结束：**14 Run / 23 请求**，回报 57,747 Token，含缺失 usage 预留的保守费用 **¥0.830728**。

## 1. Latency Breakdown

复用 `docs/qa/REAL-NATIVE-MATH-ACCEPTANCE-2026-10-13.md`、Provider usage、SQL milestone 与 Electron SSE 记录。`AGENT-LOOP-PROGRESS-ANALYSIS-2026-10-13.md` 在当前 workspace（含忽略文件）及 Documents/ChatGPT 搜索中未找到，未假装读取它。逐 Run 时间线见 [historical-timelines.json](docs/qa/evidence/agent-loop-performance/historical-timelines.json)，由 [profile-native-loop.py](scripts/profile-native-loop.py) 免费重建。

| 已完成真实题目 | 总耗时 s | 模型区间 s | 工具执行 s | 其余应用区间 s | 首公开内容 s | 最长事件空窗 s | 模型/工具 |
|---|---:|---:|---:|---:|---:|---:|---|
| 最值 | 109.569 | 108.835 | 0.304 | 0.430 | 81.521 | 45.703 | 2/1 |
| Stokes | 190.236 | 189.447 | 0.715 | 0.075 | 174.245 | 93.039 | 3/2 |
| 次序统计量 | 52.486 | 52.143 | 0.295 | 0.048 | 21.767 | 21.751 | 2/1（失败） |
| 无工具矩阵递推 | 130.776 | 130.367 | 0 | 0.409 | 108.492 | 108.100 | 1/0 |

- 模型区间占 99.3%–99.7%，是 `model.started→model.completed`，**包括供应商排队/生成、网络、SDK、流式回调和部分应用处理**，不等于隐藏推理耗时。工具区间是 `tool.started→tool.completed/failed`，包括隔离进程启动、计算及校验，不能只算 SymPy 内核。
- 其余应用区间是差额，包含上下文、消息 checkpoint、工具结果回传、最终验证及终态持久化，旧记录不足以进一步精确拆分。终态之后的 outbox 会话投影不包含在 Run 耗时内。
- 首公开内容包括工具前公开推导；不等于最终正文 TTFT。统计题 21.767 秒的早期正文仍需与最终权威答案区分。
- 事件空窗按服务端 `elapsed_ms` 计算，包含真实 milestone 与非空公开增量；不是浏览器 receive/paint 间隔。首次 SQL 进度在 0.27–1.46 ms（run.created）；首次真实模型工作在约 16–30 ms。API 的 context event 使用另一个时间原点，未混为 Run TTFT。
- Electron 提交至完成墙钟分别为 110.511 / 190.705 / 52.576 / 131.561 秒。差值包括提交、UI、网络、调度等，不能全部声称是 SSE 传输时间。
- 120 秒失败的无工具试验保留于 JSON，未计入完成表。未收到 model.completed 时，模型区间按终态截尾并标记 `model_envelope_censored=true`；迟到 Provider 回执约 128.422 秒，超出 Run 终态，不能记成应用耗时或成功完成。

### 每次成功请求的 Provider 用量与墙钟

| Run / 请求 | 请求到回执 s | 输入 | 输出（含推理） | 推理 |
|---|---:|---:|---:|---:|
| 最值 #1 | 45.659 | 1518 | 2530 | 2348 |
| 最值 #2 | 63.115 | 1839 | 3595 | 1940 |
| Stokes #1 | 57.460 | 1495 | 3267 | 3162 |
| Stokes #2 | 22.917 | 1802 | 1239 | 1188 |
| Stokes #3 | 109.004 | 2087 | 6283 | 5337 |
| 统计 #1 | 26.519 | 1547 | 1326 | 1039 |
| 统计 #2 | 25.584 | 1870 | 1405 | 737 |
| 矩阵 #1 | 130.320 | 628 | 7551 | 6237 |

开始、结束绝对时间及各次请求对应的 SSE 首公开时间保留于时间线 JSON。旧证据没有首原始 Chunk、DNS/TLS/响应头/浏览器绘制时间，字段保持 unknown/null，**不能事后重建网络与供应商内部等待的独立占比**。

### 新 Run 轻量计时

沿用同一 SQL ExecutionEvent，无数据库迁移、独立监控服务或状态机：

- `model.completed.payload.performance`：handler 总耗时、首 LangChain Chunk、首经过 ThinkingFilter 的公开 content、native checkpoint 耗时，以及 Provider 返回的 input/output/total/reasoning token 数。
- `runtime.profile.payload.performance`：初始上下文构建、初始 checkpoint、工具结果回传、最终验证与答案组织耗时（不包含最终 close 事务）。独立 `tool.started/completed/failed` 保留原执行耗时。
- Native adapter 请求同一流的 usage 末块（`stream_usage=True`），不增加模型请求；供应商不给 usage 时字段缺失，不能算 0。
- 所有新增持久化字段采用数字白名单；不记录 reasoning_content、提示正文、密钥或供应商错误正文。性能记录不出现在正常进度/步骤列表。
- 首 Chunk 是 SDK 观测时间，首公开字段是在 callback 的过滤结果时间；UI 实际显示仍由现有 output_delta/SSE 驱动，两者不可混称。超时/取消没有完整回执时，完整分段和 usage 仍可能缺失。
- API 前置 Retrieval/Gate 继续复用现有 context/retrieval/evidence event；本轮真实样本都是非教材数学模式，因此不能给出真实教材检索耗时结论。

## 2. Redundant Work Audit

| 检查项 | 发现与处理 |
|---|---|
| 重复生成/固定补偿 | Native loop 直接发布最后 AIMessage，确定性后置验证不发模型请求；未发现固定第二条生成链。`prepare_answer_generation` 仅首次构建或恢复无 checkpoint 时运行。保留同一原生 message/tool-call ID 上下文。 |
| 重复计算 | Stokes #1 calculate 已得到 `4*sqrt(5)*pi/25`、LaTeX 与近似值；#2 simplify 同一等价值无新增数学事实。#2 请求 3041 tokens，其中 1188 推理，随后工具约 0.331 s；下一轮再次带上这组消息增加输入。 |
| 工具返回不足 | 工具原本已经给简化 exact/LaTeX/numeric，却未在 description 中明确。现在说明已简化，返回 raw 运算形式；计算/化简路径删去序列化阶段的第二次 `sp.simplify`。 |
| 符号不受支持 | 统计题 theta 白名单失败。现在 schema 对外 description 明示允许符号和函数，要求明确参数映射；未扩大解析语言、权限或资源上限。能否减少真实模型失败仍需配对测试。 |
| 每 Chunk 应用处理 | 原 callback 与 stream consumer 都读取完整 snapshot（消息、历史事件、工具回执等）。现在每次检查读取 status/owner 两字段，仍逐 Chunk fence，不缓存取消状态，不减少检查频率。需要完整 snapshot 的工具边界仍读取完整数据。 |
| 普通问答 | Native 无工具答案直接结束，离线回归证明 1 模型/0 工具/0 额外生成。普通非工具路由保持现有直接回答，不引入意图模型。非数学兼容 next_action 路径仍可能另用 answer_generator；本轮未将它扩大重构。 |

**没有在 Runtime 中禁止重复工具，没有强制 tool_choice，没有降低模型/工具数量预算。** 指导模型复用已有精确结果，同时允许合理的新计算、校验和多轮调用。新 Stokes A 样本为 2 请求/1 工具，未重复化简面积；历史为 3/2。由于未运行同条件旧代码对照，这只是观察，不能把差额全部归因于此次修改。

## 3. Optimization Results

[local-overhead.json](docs/qa/evidence/agent-loop-performance/local-overhead.json) 为同机同条件、7 组重复的真实本地函数/SQLite 微基准；没有模拟响应参与速度结论。数学内核每组 20 次，SQLite 每组 100 次。序列化旧行为保留二次 simplify，对照使用同一个受限表达式。

| 局部操作 | 修改前中位 ms | 修改后中位 ms | 说明 |
|---|---:|---:|---|
| 栅栏读（同一 SQL task，约 32KB 公开 checkpoint） | 0.423 | 0.325 | 减少约 0.098 ms/检查；仍建连接并读取权威状态 |
| Stokes calculate 内核与序列化 | 2.490 | 1.406 | 减少约 1.085 ms/调用；不含隔离进程和工具校验 |

这两项是确定的局部工作减少，**不代表真实端到端等待减少 23%/44%**。主要等待仍在模型区间；新增同题配置比较见第 7 节，但没有旧代码同条件端到端配对。去掉 Stokes #2 的候选等待约 22.94 秒是历史冗余区间，不能直接从 190.236 秒相减当作优化后成绩：后续推理/回答可能改变。

安全与正确性：精确形式不变，Stokes 结果独立验证通过；既有 parser 白名单、AST/长度限制、进程隔离、5 秒工具预算和验证不放宽。未声称新提示可以保持真实教学正确率；原验收工具题完整正确仍只有 1/3，曲面半径表述错误和最终 CDF 推导缺项不能被性能指标掩盖。

## 4. Progress UX

复用 ExecutionTrace、ChatActivity reducer 和现有 SSE；新增模型请求 **0**，Timer 只刷新实际已等待时长。

| 真实触发 | 紧凑状态 |
|---|---|
| 首次 model.started | 正在分析题目 |
| symbolic_math / verify_math_result tool.started | 正在计算 |
| 工具完成或失败后下一次 model.started | 正在继续解答 |
| 非空公开 output_delta | 正在生成回答 |

只读教材工具保留其原标签，不将检索伪称计算；恢复的新 Run 依旧由 reducer 检查 request/task/run/seq 栅栏。标题采用 180ms 渐显，并尊重 reduced-motion。没有事件时状态不轮播，已输出正文不因阶段切换被抹掉。完成自动折叠，可重新展开查看真实步骤；失败、停止和 degraded 保持原标签与恢复能力。

真实 macOS Electron 开发壳验收、隔离 FastAPI/SQL/SymPy/SSE，**模型受控且加入 1.2/15 秒人工等待，只用于 UX 与事件合同，不能用于真实性能/正确率结论**。截图和 [results.json](docs/qa/evidence/agent-loop-performance/electron/results.json)：

- [分析](docs/qa/evidence/agent-loop-performance/electron/analysis.png)、[计算](docs/qa/evidence/agent-loop-performance/electron/calculation.png)、[继续解答](docs/qa/evidence/agent-loop-performance/electron/continuation.png)、[即时公开正文](docs/qa/evidence/agent-loop-performance/electron/public-stream.png)。
- [长等待](docs/qa/evidence/agent-loop-performance/electron/long-wait.png)：无事件时仍为实际分析状态，显示 6 秒墙钟，未虚构细分进度。
- [工具失败](docs/qa/evidence/agent-loop-performance/electron/failure.png)、[停止](docs/qa/evidence/agent-loop-performance/electron/cancelled.png)。停止后 reload 正常；完整 resume 幂等由后端回归覆盖，未宣称付费供应商断线恢复已经验收。
- 完成与布局：[1280×820](docs/qa/evidence/agent-loop-performance/electron/1280-final.png)、[1024×768](docs/qa/evidence/agent-loop-performance/electron/1024-final.png)、[760×820](docs/qa/evidence/agent-loop-performance/electron/760-final.png)，无页面横向溢出；完成折叠与按需展开均通过。未覆盖 Windows 安装包或所有复杂长矩阵。

中间内容：保留本轮开始前已有的 PUBLIC_DELIVERY_INSTRUCTION 与阶段推导修复。进度状态不写入答案；工具前公开内容不 replace 清空；最终仅最后 AIMessage 先独立验证，阶段内容不补齐 required outputs、不当教材证据。持久化答案把它保留在“阶段推导（未独立核验）”，与“最终解答”分开；最终权威答案仍必须独立完整。不为性能放松保守 unverified 标记。

## 5. Commentary Feasibility 与推理实验

官方 [OpenAI-compatible 参数文档](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions/)确认 Qwen3.7 支持 `extra_body.enable_thinking` 和 `extra_body.thinking_budget`；后者仅限制思考部分。Qwen3.8 的 reasoning_effort 档位不能假定适用于 Qwen3.7 Plus。生产 registry 目前 `enable_thinking=true`，本轮未修改默认。`max_completion_tokens` 包含思考和回答；不缩短它来伪造提速。`preserve_thinking` 默认关闭，开启会增加历史推理输入和费用，本轮不启用。

当前原生协议容许同一 AIMessage 有公开 content + tool_calls，现有统计题真实记录证明工具前公开推导**可以发生**。这不是专用 Commentary channel，也没有稳定“先简短行动说明，再工具”的保证。现有 stream 可以零额外请求展示合法 content；提示语可能增加输出、改变工具选择或拖慢解答，授权实验中 8 条成功工具决策消息有 6 条同时包含公开前言，证明可行性；并不保证简短、稳定或早于长时间推理。暂不增加 Provider 私有解析协议、强制前言或复杂 Commentary 工程。

### 已授权并执行的实验预案（实际结果见第 7 节）

固定 4 题、每题 4 条件，共 **16 Run**，每条件 1 次，不自动重试，不追加失败重跑；顺序交错。如此小样本只能发现风险，不能证明普遍正确率不退化。

1. 概念：解释可导与连续关系，给出反例，并说明反例为何不可导。
2. 常规计算：计算定积分 `∫_0^1 x^2 e^x dx`，完整分部积分推导和核验。
3. 综合：复用已冻结 `extended-deadline/questions.json` 的 Stokes 全题，单独检查球面半径、投影区域、方向和最终值。
4. 证明：用中值定理证明 `x>0` 时 `ln(1+x)<x`，说明适用条件和严格性。

四条件 A 当前默认思考+auto 工具；B 思考+thinking_budget=4096+auto；C enable_thinking=false+auto；D 默认思考+彻底移除 tools/tool_choice。同题使用同一个冻结的教材摘录/Final EvidencePack、ContextPack 与 required outputs；每题四条件逐字一致，不实时检索改变上下文。无可用合法教材摘录时明确标记无教材上下文、四条件一致，不伪装真实 RAG 测试。A 的工具前公开内容同步观察 Commentary，无第五条额外请求。

模型 Qwen3.7 Plus、北京端点、temperature=0、同一教学 prompt；统一 `max_completion_tokens=16384`，不改输出额度来制造对照。A/B/C 每 Run 最多 5 请求/3 工具，D 最多 1 请求/0 工具；**最多 64 请求**，预计 24–40（只是规划估计，实际受 auto 决定）。模型等待统一 180 秒，Run 600 秒。

预算预案：累计输入保守上限 400,000 UTF-8 请求字节（以字节为 input-token 上界，发送前含 tools/全部上下文），输出每请求 16,384+10，最多 1,049,216 token；全部 token 保守上限 1,449,216。按 [Qwen3.7 Plus 北京价格](https://help.aliyun.com/zh/model-studio/qwen3-7-plus)输入 2/输出 8 元每百万 token、忽略缓存，最坏估算 **¥9.194，费用硬上限 ¥10**。发送前预留最坏费用，缺 usage 不算免费；价格/端点/tokenizer/阶梯不匹配就停止预检并重新预算。授权仅用于上述 16 Run 和上限，不继承之前真实验收的调用授权。

输出：逐请求起止/首 Chunk/首公开/usage，逐工具有效性，Run 首正文/总耗时/最长空窗/调用数；离线 SymPy oracle 和独立 rubric 区分完整答案与关键推导。finish_reason=length、超时、输出缺项都记失败/截断，不能记提速。首轮出现关键质量退化时保留证据并停止相应配置，不自动扩大样本或改生产默认。不同题之间不作因果速度对比。

## 6. Remaining Risks 与 Checkpoints

- 已定位主要等待区间；无法从旧日志区分 Provider 排队、内部推理和网络，新增 SDK 计时也不提供供应商内部真值。隔离 Electron harness 已记录 fetch 响应头和逐次读取时刻/字节量（results.json browser_delivery）；未接入生产绘制或网络细分探针，不能把读取间隔等同纯网络时间。
- 授权配置配对已完成，低预算没有稳定收益，非思考最终交付失败已停止；**仍无旧代码与新代码同条件的真实速度/正确率对照**，不宣称普遍提速或质量不退化。
- description 略增输入 Token，raw 结果略增工具 payload；若不能减少重复请求，可能没有净收益，需配对实验决定是否保留提示增量。
- 工具参数仍仅允许原符号集，复杂数学的定义域、推导及 required-output 字面检查遗留缺陷保持可见；没有借本轮重构 Gate 或 Runtime。
- 新计时增加每成功 Run 一条已存在 schema 的性能 milestone；取消后不补写迟到结果，不修改 checkpoint 身份/恢复/预算合同。未测所有供应商 stream_usage 兼容性。
- 当前分支 `codex/cross-module-remediation`；不合并 main，不覆盖其他分支。开始时已有 native_loop.py / test_native_math_loop.py / patch_notes.md 未提交改动，已保留。

免费验证：后端数学/native/SSE/停止恢复/最终验证/直接路由/SQL 权威合同回归；模型角色与工厂回归；前端全部 203 tests、ESLint、TypeScript 与生产 build；真实 Electron 事件交互。后端合同 101 passed，模型配置/工厂 27 passed，桌面 runtime/main 5 passed。没有执行旧冻结 Policy 源码身份的全量发布门槛，不把离线受控模型当真实模型质量验证。

### 三个问题的当前答案

① 默认 auto 的概念/证明均 1 请求/0 工具；积分 3 请求/2 工具，Stokes 2/1。相同题目的无工具条件各为 1 请求，分别多 2/1 次续答。工具调用后的续答有必要；旧 Stokes 重复化简同一精确结果的一轮是明确冗余候选（3041 Token、约 22.94 秒），新样本没有重复它。没有固定额外决策模型。

② 已证明局部 SQLite 与数学序列化减少工作，但尚不能证明净端到端提速。积分 A 比 D 快约 3.75 秒，Stokes A 比 D 慢约 19.57 秒；单次同题配置样本不能推广。B 预算未实际约束已回报的推理，C 最终缺项，因此保持生产默认，不以不完整答案换速度。

③ 可以：真实事件驱动单行状态、真实等待时长、公开正文立即展示、完成折叠均通过 Electron 验收，新增进度模型请求为零。长时间无事件时保留真实状态和计时；无法保证模型不断输出新的具体行动说明。

## 7. Authorized Paired Experiment Results

### 实验身份、范围与成本

用户在预算预案后以“执行”授权。固定 4 题 × 4 条件，实际 14 个 Run、23 次远程请求，未自动重试或补样。A 默认思考+auto；B 思考预算 4096+auto；C 非思考+auto；D 默认思考且移除工具。温度 0，输出上限 16384，各题条件交错；同题初始 prompt hash 完全相同。D 按预案移除 tools 及工具控制参数，工具配置本身是处理变量。

冻结的是无教材、无历史的相同问题和上下文，不涉及用户教材出境。调用真实 `chat_binding.stream_run → LangChain → Qwen3.7 Plus → SymPy → SSE`，没有覆盖完整 HTTP Chat API、实时 Retrieval/Gate 或浏览器在线付费流。表中时间从 stream_run 消费开始计算，不称为浏览器 paint。初始生成上下文在冻结准备时构建，不在计时区间内；新 profile 的 0.03ms 是恢复冻结 native_messages，不能代表完整上下文构建。

证据：[冻结题目/配置](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/manifest.json)、[逐请求回执与预留](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/provider-receipts.json)、[完整汇总](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/summary.json)、[独立审阅](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/independent-review.json)、[SymPy oracle](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/oracles.json)、[代码身份](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/code-identities.json)。每个 case.json 保留逐事件、接收时间、公开文本、原生工具协议与请求计时，隐藏推理只保留数量。

实际回报输入 33,222 / 输出 24,525（包含推理 17,231），共 57,747 Token。按北京公开输入 2/输出 8 元每百万 Token、不计缓存优惠，回报费用估算 ¥0.262644；4 次缺 usage 请求仍预留 ¥0.568084，总保守 ¥0.830728。发送请求共 140,233 UTF-8 字节，均在已授权 64 请求、1,449,216 Token、¥10 硬上限内。费用是回执估算，不是账单结算。没有 finish_reason=length，没有降低输出上限。

### 同题配置结果

首公开包含阶段前言；首最终只统计已确认的最终 AIMessage。最终正确性单独审阅，不用阶段文本补分。下表只列有完整最终答案的 10 个 Run。

| 题目/条件 | 首公开 s | 首最终 s | 总耗时 s | 模型/工具（失败） | 输入/输出 Token | 推理 Token | 最终审阅 |
|---|---:|---:|---:|---|---|---:|---|
| 概念 A | 8.64 | 8.64 | 20.40 | 1/0 | 1622/988 | 291 | 4/4 正确 |
| 积分 A | 8.62 | 24.77 | 31.91 | 3/2 | 5784/1450 | 846 | 5/5 数学正确；工具核验来源表述有误 |
| 积分 B | 5.79 | 25.34 | 32.22 | 4/3（1） | 8228/1301 | 595 | 5/5；失败参数后自主恢复 |
| 积分 C | 3.04 | 25.81 | 26.86 | 3/2（1） | 7006/989 | 0 | 1/5；最终缺推导，不合格 |
| 积分 D | 25.48 | 25.48 | 35.66 | 1/0 | 593/1964 | 1363 | 5/5 正确 |
| Stokes A | 56.15 | 102.06 | 115.47 | 2/1 | 3741/6447 | 5524 | 6/6 正确 |
| Stokes D | 74.29 | 74.29 | 95.91 | 1/0 | 673/5489 | 4219 | 5/6；题面交付完整，额外半径探针未展示 |
| 证明 A | 8.93 | 8.93 | 17.07 | 1/0 | 1634/864 | 395 | 4/4 正确 |
| 证明 B | 9.02 | 9.02 | 17.01 | 1/0 | 1634/864 | 395 | 4/4，与 A 正文逐字相同 |
| 证明 D | 19.70 | 19.70 | 28.05 | 1/0 | 602/1525 | 1026 | 4/4；“中点”应写“中值点” |

概念 B/C/D 分别 30.82/5.32/30.98 秒 APIConnectionError，没有响应头、usage 或答案，保留为失败，不算速度改善或参数不支持。Stokes B 在 95.47 秒被验收进程干扰中断，无完整最终答案：我在其运行时启动了共用隔离 QA 数据库的只读展示后端，startup recovery fence 了活动 Run。这是实验操作错误，不归因于低预算；按不重试预案不补跑，排除配对速度/质量比较，第一请求的已返回 usage 计费，第二请求保守预留。详见 [harness-interruption.json](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/harness-interruption.json)。展示服务随后停止，剩余证明实验在无展示服务干扰下完成。

C 积分只有阶段正文包含推导，最终独立答案仅 e−2，立即停止 C 的 Stokes/证明两个条件，见 [stopped-arms.json](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/stopped-arms.json)。保留中间内容并不修复最终完整性。默认 A 积分声称工具已验证原函数求导，但工具回执只包含 pending verification_request 与后续定积分校验，不能把该声明当成真实核验。数学正确与来源准确性分别记录。全部完成 Run 仍为 Runtime degraded，不把离线人工数学正确等同于生产 verified 或发布通过。

### 耗时与参数判断

完成样本中模型 envelope：积分 A/B/C/D 为 30.955/30.925/25.915/35.367 秒，工具为 0.619/0.931/0.602/0 秒；Stokes A/D 为 114.764/95.570 秒，工具 0.384/0 秒。每个完成 Run 其余差额约 0.28–0.37 秒，最终验证约 1.85–5.23ms、工具回传约 1.31–4ms。新 HTTPX hooks 保留发送、响应头、SDK 首 Chunk、过滤后首公开及 usage 结束时刻；成功响应头等待约 1.78–3.69 秒，混合传输和供应商响应前处理，不能称为纯网络。最长接收空窗逐 Run 见 summary.json，例如 Stokes A 55.88 秒、D 74.06 秒；它与首最终时间不同。

B 成功请求接受 thinking_budget，C 成功请求回报 reasoning=0，实测支持这两种配置；但 B 所有回报推理均低于 4096，上限没有约束成功请求，不能推断“减少思考预算已经提速”。证明 A/B 完全相同，耗时仅差 0.059 秒；积分 B 比 A 多一轮失败恢复且略慢。保持默认思考。

默认 auto 概念与证明直接结束，未增加工具决策请求。积分 A 比无工具 D 多 2 次模型、4677 Token，却此次快 3.75 秒；Stokes A 多 1 次模型、4026 Token（65.3%），慢 19.57 秒（20.4%），提供被积函数因式检查。工具可以提供验证收益，但并非必然提速，不强制或禁止自主调用。旧 Stokes 190.236 秒/3模型/2工具/16173 Token 与新 A 115.475 秒/2模型/1工具/10188 Token 的差异是跨批观察：prompt、工具说明、阶段保留及生成过程均可能影响，不宣布节约 74.76 秒或证明此次提示造成改善。

同请求公开 content+tool_calls 出现在 6/8 条成功工具决策消息中，未增加专用 Commentary 请求。Stokes 前言仍要等 56.15 秒，前言也可能包含长推导；暂缓复杂协议与强制行动说明。真实事件进度是当前有证据支持的反馈方案。

### 真实答案 Electron 只读回放

实验全部结束后，实际 macOS Electron 打开隔离持久化答案，拦截所有非 GET API，未再次调用模型。通过会话侧栏加载 Integral A/C、Stokes A，确认阶段与最终标题区分、公式渲染和过程默认折叠；[回放结果](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/electron-restored/results.json)。首次回放只设置当前会话 ID 未加载正文，已修正为真实侧栏点击并重新验收。这是持久化展示验收，不冒充付费在线 SSE/paint 测量。

- [积分 A](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/electron-restored/integral-A.png)、[积分 C 阶段](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/electron-restored/integral-C.png)、[积分 C 最终](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/electron-restored/integral-C-final.png)、[Stokes A](docs/qa/evidence/agent-loop-performance/paired-2026-10-13/electron-restored/stokes-A.png)。

样本每题每配置仅一次，含网络缺失、一次 harness 干扰与质量停止，不能给出统计正确率、稳定速度提升或一般教学质量不退化结论。已验证局部优化与零额外请求反馈；保留生产默认、自主性、预算和验证门槛，未扩大为 Runtime 重构。
