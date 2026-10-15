# Texa — Model Latency Optimization / Phase 1

2026-10-13 · 主线 A · 只读审计、官方文档核查、免费请求构造实验。新增真实模型请求 **0**，费用 **¥0**。

**建议：暂时保留 Qwen3.7 Plus + Thinking；下一步先做 6 Run 的小实验，比较“减少重复推理的提示”和“Qwen3.8 Flash 的明确推理配置”。尚无可直接上线、已证明数学质量不退化的提速开关。不要继续优化毫秒级 Runtime，也不要把缩短最终答案或提前截断当成成功。**

## 1. 基线、范围与证据

- 共同基线：`codex/cross-module-remediation` 的本地最新已提交 HEAD **f91633673c40cf9c353e49804e2584b64f3131cc**。开始时该分支 ahead origin 6；没有 fetch、reset 或改写 Checkpoint。
- A 分支：`codex/agent-model-latency`；独立 worktree：`/Users/jichengqian/.codex/worktrees/agent-model-latency/texa`。创建后、报告提交前分支 HEAD 等于共同基线。交付提交 Hash 由 `git log -1 --format=%H` 查询，最终回执另给；不在提交内容中制造自指 Hash。
- 原工作区有 12 个已跟踪文件未提交修改及多项未跟踪实测资产，全部保留。A 未修改 Runtime、SSE、前端、模型工厂、凭据、默认模型或正式数据；未创建/修改 B 分支，未合并或 cherry-pick。B 是否采用同一基线由其独立回执核对。
- 实测来源：[性能报告](/Users/jichengqian/Documents/ChatGPT/texa/TEXA-AGENT-LOOP-PERFORMANCE-REPORT.md)（原工作区未跟踪）、`docs/qa/REAL-NATIVE-MATH-ACCEPTANCE-2026-10-13.md`、`docs/qa/evidence/agent-loop-performance/paired-2026-10-13/{manifest,provider-receipts,summary,independent-review}.json`。原工作区绝对路径为 `/Users/jichengqian/Documents/ChatGPT/texa`。这些历史结果并非本分支代码新跑的成绩。
- 可复现免费检查：[脚本](scripts/audit-model-latency-offline.py)、[结果及源 SHA-256](docs/qa/evidence/model-latency-phase1/offline-audit.json)。使用原工作区 `venv310/bin/python`，实测 Python **3.10.21**。脚本显式 `resolve_model_role(env={})`，不加载真实 profile/密钥，不发送 API 请求。

**身份限制：**历史性能实验使用原工作区未提交的 native loop、工具说明与计时改动；它们不在共同基线内。本报告同时审查已提交基线与这些只读证据，不把未提交代码移入 A。正式付费比较前必须先确定并冻结有效性能 Checkpoint；不能悄悄在旧基线执行、再和新代码历史成绩作因果比较。

## 2. 已知事实与未知部分

| 证据 | 对决策的含义 |
|---|---|
| 历史完成题模型 envelope 占 Run 99.3%–99.7%，单 Run 52–190 秒 | 模型相关等待是主要方向；envelope 包含供应商等待、传输、SDK 与回调，不等同全部隐藏推理 |
| 矩阵无工具请求 7551 输出、其中 6237 reasoning；请求 130.32 秒 | 无额外工具轮次仍可慢；应控制生成工作或换实际更快的服务 |
| 配对积分 A/B：31.91/32.22 秒；证明 A/B：17.07/17.01 秒且答案相同 | 4096 budget 没有已证提速收益；所有 B 回报请求 reasoning 都低于上限，包括被干扰 Stokes 的已完成第一请求 |
| 关闭 Thinking 的积分 C：26.86 秒、最终仅 1/5 完整度 | 少量节时伴随关键推导缺失，拒绝作为生产优化；阶段正文不能补最终答案 |
| 旧 Stokes：精确面积返回后再次 simplify 等价表达式，增加一轮约 22.94 秒 | 存在可避免的重复决策/计算，潜在收益是秒级；不是减少 SymPy 的毫秒 |
| 新 Stokes A：2 模型/1 工具、115.47 秒；D 无工具 95.91 秒 | 工具不保证更快；跨批旧/新差 74.76 秒不能全归提示，D 也缺额外半径验收项 |
| 新成功请求响应头约 1.78–3.69 秒；长空窗可达 55–74 秒 | 单纯换域名/网络不是目前有证据的主要收益；不能由响应头推出供应商生成速度 |

历史同题每条件只有一次，包含 APIConnectionError 和一次 harness startup recovery 干扰；失败不是更快，也不能推出 budget 不受支持。隐藏 reasoning 正文没有保留，因此只能直接证明重复工具操作；工具后是否在隐藏推理里重做整题只能由数量/耗时间接推断，不能声称已经看见。

另有历史 [Prompt 对照](docs/benchmarks/qwen37-prompt-presets-abg-20260825-final.md)：Legacy→Refined 的中位延迟 37.012→20.794 秒，reasoning 104659→51761；同时正文也缩短。它支持“流程化提示能影响生成工作量”的假设，不证明减少了思考而完全没减少答案，更不是当前 native 数学链的可重复收益。当前已经采用 refined v2，不重复旧迁移。

## 3. 当前真实调用与参数作用（A1）

调用链为角色配置 → `llm/factory.py` 的 ChatOpenAI → `llm/agent_adapter.py` → LangChain `create_agent`。模型自行决定调用数学工具；工具回执按原生 call ID 进入同一上下文；最终后置验证没有固定追加模型请求。

| 参数/结构 | 当前值或路径 | 真正作用及结论 |
|---|---|---|
| `enable_thinking` | registry 的 Qwen3.7 Plus `extra_body={enable_thinking:true}`；A/B/D 回执匹配 | 改变是否生成隐藏推理；关闭已出现最终缺项，不上线 |
| `thinking_budget` | 默认没有显式设置；实验 B=4096 | 推理长度上限，达到后转入回复；不是更快的 decoder，也不是自适应努力档位。低于自然推理长度才可能生效；不再重跑 4096 |
| `max_completion_tokens` | 历史付费 harness 强制 16384 | 包括推理与回复，不能调小制造提速；`length` 必须判失败 |
| Runtime `max_tokens=4096` | 基线和只读最新代码都有；免费 wire 构造实测变成 `max_completion_tokens=4096` | **运行额度与历史实验不同**。当前 LangChain 自动改名，不能把代码变量名解释为“只限制正文”。不是本阶段授权修改项 |
| streaming / usage | factory `streaming=True`；最新未提交 adapter 额外 `stream_usage=True`，基线没有显式开启 | 流式降低可读等待，不保证减少总推理或提高 token/s；usage 是计量，非提速 |
| Tool Calling | `parallel_tool_calls=False`，历史 paid payload `tool_choice=auto` | 非固定前置请求；合理工具续答有必要，重复等价运算可避免，不强制/禁用工具 |
| temperature | native 0.0、零自动重试 | 控制采样；不是推理预算或吞吐开关。重试关掉避免重复付费，不等于单次请求加速 |
| `reasoning_effort` | Qwen3.7 Plus 没有可核实支持档位 | 不能套用 Qwen3.8 或 DeepSeek 的 low；参数接受也不证明语义生效 |
| `preserve_thinking` | Qwen3.7 默认 false；checkpoint `_protocol` 去掉私有 metadata | 开启不会自动恢复被丢弃的 reasoning；需要完整传回且增加输入/隐私与恢复合同成本，本轮不做 |
| `tool_stream` | 未显式设置 | 影响复杂参数增量交付，不能消除推理，也不等于更早安全执行工具；排除为总耗时方案 |

上述 Qwen 参数与 Function Calling 限制以 [OpenAI-compatible API](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions/) 和 [深度思考用法](https://help.aliyun.com/zh/model-studio/deep-thinking) 为依据，核查日 2026-10-13。SDK 的 `extra_body` 会合并到 HTTP 请求顶层，不代表供应商需要名为 extra_body 的 JSON 字段。不要用 stop/thinking 标记强制终止隐藏推理。

**Prompt 实际结构：**`prepare_answer_generation` 按模式装配 system + human；human 包含问题、ContextPack、必要 EvidencePack/工具结果，而非完整历史。数学通用模式实际替换为 `GENERAL_TEACHING_PROMPT`，即使 preset=refined，也不使用教材版 Refined 正文。基线没有 `PUBLIC_DELIVERY_INSTRUCTION`；只读最新 native 代码在最前插入它，强调最终答案独立完整。后续工具原生消息追加到同一轮。

现有提示已要求必要公式/条件/步骤、按需举例、不套固定栏目。值得新增的约束应针对“同一计算的重复探索”，而不是删教学步骤、压 human 输入或再迁移 Minimal。

**端点：**真实成绩来自北京 `https://dashscope.aliyuncs.com/compatible-mode/v1`。官方 API 页建议业务空间专属北京域名；这只是服务建议，没有 Texa 同题速度证据。不同地区需要相应账户、模型可用性和价格/数据范围核查；暂不跨境、更换协议或付费购买专属吞吐。Qwen3.7 Plus 官方模型页只列百炼供应商，未找到可核验的其他供应商同一托管模型对照，不用同名开源 Qwen 代替它。

四类变化分别验收：①自然减少 reasoning：看 reasoning 用量及完整 rubric；②减少正文：单独记录公开输出，不能删必要解释；③budget/length 提前结束：视为质量风险，不视为自然少思考；④提高实际生成速度：看请求首 chunk 后至完成的有效输出速率与全任务耗时，不能用总 tokens/总墙钟称纯 decoder token/s。

## 4. 只保留两项高收益候选（A2）

| 方案 | 实现与作用环节 | 请求数 / 生产配置 | 数学风险、复杂度与预期收益 | 决策 |
|---|---|---|---|---|
| 保留 Thinking，促使简单任务收敛、复用精确工具结果 | 实验 system 添加下述短合同；不改 Runtime，不改工具权限。减少不必要的探索/重复计算/等价化简调用及后续长续答 | 不新增请求；有机会少一轮。模型参数不变；通过后才改共享教学/工具提示 | 可能过早信任无验证结果，或漏掉独立核验；须区分精确返回与 verified。低复杂度。历史有约 23 秒冗余轮次，收益未证、不是承诺；简单任务本已 17–20 秒，空间有限 | **优先实验**，不重复已有工具 description 修复 |
| 同供应商 Qwen3.8 Flash，思考模式 `reasoning_effort=medium` | 隔离 role/options，`preserve_thinking=false`；相同 prompt/tools/输出上限。比较整个“模型＋配置”而非只测 tokens/s | 无新增分类/路由模型；auto 轮数可能改变。实验不改生产，采纳需要显式切换模型/配置 | 新模型数学细节与工具 schema 未在 Texa 验收；medium 可能提前结束。低至中复杂度。官方定位响应快、成本低，存在秒级/几十秒级收益假设，无本地幅度保证 | **次优先实验**；未证明可靠前不迁移 |

实验提示原文（附加在当前有效通用 system，保留交付合同）：

> 对简单问题，选定满足条件的方法后完成必要推导与一次相关核验；不要额外展开等价解法。工具已成功返回的精确结果可用于对应计算，不再仅为换一种等价写法重复调用或重算。若条件、方向、定义域或结果有冲突，仍需检查；待验证不等于已验证。最终答案独立保留全部小问、关键步骤和必要教学解释。

这只是收敛策略，不要求展示内部思考。Stokes 的面积结果不能证明球面半径、方向和全部推导正确。

**排除：**4096 budget 重复试验、全局非思考、调小总输出/stop、短答替代完整教学、缓存少量输入、SQLite/回调优化、把 tools 全部移除、固定强制工具、增加分类模型。更低 budget（如 512/1024）虽可能真实缩短等待，却属于到限转回复，风险高于上述候选，本轮不纳入最小实验；不据此断言所有 budget 都无效。业务域名可作服务可靠性维护项，但现有响应头区间不足以支持优先把它作为主要延迟优化。

## 5. 替代模型与继续使用 Qwen 的判断（A3）

| 候选 | 可核实能力 / 速度与成本依据 | Texa 兼容性与限制 | 优先级 |
|---|---|---|---|
| **Qwen3.8 Flash / 百炼北京** | 官方列 Function Calling，兼容 Chat Completions；标准流式路径可用。官方定位响应快，价格输入 ¥0.8 / 输出 ¥2.7 每百万。支持 medium 推理档 | registry 已有；模型可见消息与 checkpoint 不回传私有推理，实验显式关闭 preserve_thinking。协议构造可接入，不等于已通过真实多轮/恢复验收 | 第一比较候选 |
| Qwen3.7 Flash / 百炼北京 | 同系列混合 Thinking、原生 Function Calling/流式；<=32K 输入 ¥0.2 / 输出 ¥0.8 每百万 | 同供应商迁移成本低；本轮查到的官方能力页没有足以证明 Texa 考研数学可靠性的独立结果，也没有同题延迟实测。不能只因名字 Flash 就判更快 | 备用，暂不付费比较 |
| **DeepSeek V4.1 Flash（`deepseek-flash`）/ 官方** | 官方发布报告数学 MathArena Apex 65.6，宣称新架构提高推理速度/吞吐，支持工具、流式和 low/high/max；属于厂家自报，仍需真实题 | 当前 LangChain wire 免费测试丢弃 AIMessage.additional_kwargs.reasoning_content；checkpoint 也剥离。官方工具思考续答要求完整回传，否则 400。**现状不是即插即用**，需 Phase 2 先决定私有字段的传输/恢复合同。本次价格页无法可靠读取，不预算、不调用 | 条件性研究候选，暂缓 |

价格与能力分别见 [Qwen3.8 Flash](https://help.aliyun.com/zh/model-studio/qwen3-8-flash)、[Qwen3.7 Flash](https://help.aliyun.com/zh/model-studio/qwen3-7-flash)；DeepSeek 的数学/速度依据见 [官方 2026-09-10 发布记录](https://api-docs.deepseek.com/updates/)，续答要求见 [官方 Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。不把 3.8-Flash-Next 开源架构或 Omni 的数学榜单冒充 `qwen3.8-flash` 商业端点结果。DeepSeek 旧 V4 Flash 名称已经路由到 V4.1，不把别名当独立候选。

**严格门槛判断：没有一个替代候选已证明同时满足“Texa 数学可靠＋现有链直接兼容＋实际更快”。**候选表是有依据的待验证名单，不是数学质量保证或生产排名。Qwen3.8 的官方响应速度定位仅使它值得一次小比较；数学结果、必要推导和工具协议必须先验收。DeepSeek V4 Pro 保持现有回退定位，不因模型规模或现有注册就列为更快方案。

因此继续使用 Qwen3.7 Plus 有价值：已观察到完整正确的综合题和低复杂度题，现有原生链确实运行；但它也有半径错误、工具失败和漏推导，不能认为质量已完美。若新提示没有明显收益、Flash 能在全部小问和工具核验通过下明显更快，应转入生产模型切换评估，而不是继续堆 Runtime 优化。

## 6. 最小真实实验与待授权预算（A4）

**本轮未运行以下付费实验。既有历史“执行”授权不继承。**

复用冻结积分题和 Stokes 全题/独立 oracle/rubric。积分验证简单任务/续答，Stokes 验证长推理、方向/区域与工具后重复计算。不重新采题、不实时检索、不送用户教材/历史。三个条件各两题，每条件一次，共 **6 Run**：

- A：Qwen3.7 Plus，Thinking 开启，当前有效 prompt，auto 工具。
- P：同 A，仅附加第 4 节收敛/精确结果复用提示。
- F：Qwen3.8 Flash，`reasoning_effort=medium`、`preserve_thinking=false`，使用 A prompt。不同时设置 thinking_budget，不为 3.8 照搬 enable_thinking 参数。

F 比较的是可用模型配置整体；不能将差异单独归因于模型架构、努力档位或吞吐。若 F 很快且完整，下一步才值得验证稳定性；不在这轮扩成多档 budget sweep。

**执行前的免费前提：**确认用户选定的性能 Checkpoint（含必要交付修复）及依赖 Hash；冻结题面、每条件 system/human hash、工具 schema、rubric、端点和角色 options。从原脚本复用发送前预算预留/回执逻辑，但另建 A 专用 harness，删除原有自动 prepare、16 Run/4096 条件和硬编码 ledger。原脚本未跟踪且硬编码模型/目录，不能直接改 --case 就声称隔离。对 F 免费构造两轮工具消息，确认无 reasoning 私有字段回传要求和序列化错误；真实支持仍由本批 Run 验证，不额外发 smoke 请求。

每题最多 **5 次模型请求 / 3 次工具**，总上限 **30 请求**（预计约 15，不保证），零自动重试、无失败补跑。每请求 `max_completion_tokens=16384`，供应商误差预留 10；每 Run 600 秒、单模型 180 秒。相同输出额度不代表必然不截断：任何 length/缺项仍失败。每请求完整 UTF-8 JSON 最多 20000 字节，总输入最多 240000 字节（A/P 160000，F 80000）。只用文本，发送前以完整消息＋schema＋工具结果字节数作为 token 保守上界，超过即不发送；含图像或 tokenizer/阶梯不符须重新预算。

| 预算 | A/P（最多 20 请求） | F（最多 10 请求） | 合计 |
|---|---:|---:|---:|
| 输入 token 保守上限 | 160000 | 80000 | 240000 |
| 输出 token 预留（含 thinking） | 327880 | 163940 | 491820 |
| 北京输入/输出每百万单价 | ¥2 / ¥8 | ¥0.8 / ¥2.7 | — |
| 忽略缓存优惠的最坏费用 | ¥2.943040 | ¥0.506638 | **¥3.449678** |

请求、token 总上限 **30 请求 / 731820 token**，费用硬上限 **¥4**。这是保守预留，不是实际账单承诺。按调用前官方当前价预检；任何模型、端点、价格、额度或数据范围变化停止并重新授权。没有 usage 的失败保留最坏费用，不能释放为免费。

隔离 `/private/tmp/texa-model-latency-A-<experiment-id>/{data,progress,logs,ledger}`，不启动其他服务读取这份活动 Runtime DB；这次使用现有后端 stream_run harness，无 HTTP server/端口。实验后若需要 Electron，只读回放已完成资产，禁止非 GET 和远程模型调用；不在活动实验过程中启动 recovery 服务。此轮对纯模型配置决策不需要再次改前端或重跑 UI 测试。

**唯一重要的判据：**最终答案逐项数学正确、所有必要推导/解释完整、原生工具及核验成功，没有 length、超时或不真实的核验来源声明；不以阶段正文补齐最终答案，不把 Runtime degraded 当 verified。独立人工审阅＋已有免费 SymPy oracle；不再发评审模型。

记录每请求发送/响应头/SDK 首 chunk/过滤后首公开/完成、finish_reason、输入/输出/reasoning；每 Run 总耗时、首最终正文、模型/工具轮数、有效与重复工具、rubric。首公开改善和总耗时改善分开。按题交错 A/P/F、F/A/P；不跨题相减，不用历史 A 当同条件对照。

决策阈值预先设定：综合题总耗时至少减少 **20% 且至少 10 秒**，简单题不明显退化（>10% 且 >2 秒算退化），且两题全部质量门槛通过，才进入 Phase 2 候选。P 如只减少正文长度但遗漏讲解直接拒绝。任何工具失败/关键质量退化停止该条件剩余 Run；不扩大样本“补救”。单次样本只决定是否继续验证，不能宣布稳定提速/正确率不退化，也不能据此直接改默认。若所有条件无明显收益，保持 Qwen；将下一次投入转向有协议基础的模型替换，而非继续微调这批参数。

## 7. Phase 2 改动、冲突与交付核对

本分支实际修改仅 **3 个新增文件**：本报告、免费审计脚本、审计 JSON。没有修改 patch_notes.md（未落地版本/配置/依赖变化，也避免和已有未提交记录冲突）。

免费验证：Python 3.10 下请求构造断言通过，证实总输出参数转换及 reasoning 字段丢失；历史 ledger **14 Run / 23 请求**及 B 返回 reasoning 均 <4096 的断言通过。依赖版本与源 Hash 在 JSON。文档/脚本 `git diff --check` 通过；没有运行生产模型、重装依赖、全量应用回归或新 Electron 验收，不把这些声称为已验证。

未来共享文件需求（都未实施）：

1. P 若通过：优先在 `graph/teaching_prompts.py` 的通用提示和教材提示加入有边界的结果复用策略，必要时 `backend/tools/math_tools.py` description；与 B 的 `PUBLIC_DELIVERY_INSTRUCTION` 修改需统一提示顺序，不叠加两套公开前言合同。
2. F 若通过：在 `llm/registry.py`、`llm/configuration.py`/profile 及现有工厂配置入口确定可回滚的选定配置；解决目前 Runtime 总输出 4096 与实验 16384 的身份差别。该问题可能涉及 `native_loop.py`，需共同协调，不能由 A 私改。
3. DeepSeek 如继续：`llm/factory.py`/adapter 的 reasoning wire 传输与 `native_loop.py` checkpoint/恢复涉及私有字段合同，成本和隐私须另行评审；与 B 的流式消费共享边界，不能临时持久化隐藏推理来绕过。

**最终建议：实验验证 P 和 F；现在不实施生产参数或模型迁移。放弃全局关 Thinking、重跑 4096 budget、缩短最终答案及毫秒级 Runtime 优化。**
