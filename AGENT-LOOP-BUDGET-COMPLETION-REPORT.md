# Agent Loop Tool Budget & Completion

日期：2026-10-18（Asia/Shanghai）。结论：**CONDITIONAL PASS**。

最小工程修复及有界失败语义可交付审查；两个定向样本都从预算中断转为完整正文交付，但 task 均为 degraded / unverified。AB 出现一次不支持的元组调用。不能宣布整题 verified、稳定完成率提升或教学发布门槛通过。

## 1. Git、基线与隔离

- Worktree：`/Users/jichengqian/Documents/ChatGPT/texa-p1-agent-completion`
- Branch：`fix/p1-agent-loop-completion`
- 精确 Base SHA：`655aa481743b20e24eaab52f5f75d141b4db83dc`
- 实现、测试及验收证据 Commit：`35745375968f6acfd7d2740112fab23fea494478`
- 本报告和 patch_notes 为其后的独立文档提交；文档提交 SHA 以最终交付回执和 `git rev-parse HEAD` 为准。实现 SHA 不随文档提交变化。
- Base 来自干净的 `fix/p1-integration-reliability`，其最终提交为 `fix(p1): harden math metadata and budget failure delivery`。
- 已逐项执行 ancestry 检查：P1-A `c75695c77d7f6b2f6d7deb53f0ab6b360993212b`、P1-B `0c2f07389198c53e4879d305590b3a9be3611a3d`、P1-C `bfe4933ef8b24a49a347d88392062dd4d49b3ba8` 及集成 `9c1c013418f6a8e6d9a983b8490e6e1471592897` 全部为 Base 的祖先。
- 检查过原目录 status、branch -vv、worktree list、log。原 `Texa_MacOS` 工作区有既存未提交内容，未修改、清理、带入；未修改其他工作树。没有 merge、push、reset 或依赖重装。
- 指定分支与路径按用户要求创建。所有源码修改和测试从此 Worktree 运行；复用已有 Python 3.10.21 / venv310，只读引用现有依赖。测试/生成数据位于显式 `/private/tmp/texa-completion-*` 或 `/private/tmp/texa-agent-completion-20261018`。

## 2. 证据与核心纠正

阅读了 `P1-INTEGRATION-RELIABILITY-REPORT.md`、`docs/qa/p1-reliability/` 的温度 1 AB 前后原始 gzip、真实 sensor-B 原始结果、Provider usage、历史 sensor-B SQL checkpoint、现有验收脚本及真实执行代码。

完整逐调用审计见 [trace-audit.json](docs/qa/agent-loop-completion/trace-audit.json)。包含来源 hash、用户请求、候选工具、原生 call ID、原始参数、ToolResult、输入合法性、是否执行、信息收益、重复性、必要性、预算、模型使用方式和结束时机。未提交教材正文、历史学习记录、凭证或 reasoning_content。

**两个失败都不是“模型看到局部结果后继续决定调用”。** 它们的第一个模型响应就提出整个批次，随后 ToolNode 按原生顺序执行，达到预算后中止，没有第二次模型请求。即使请求设置 `parallel_tool_calls=false`，供应商仍可返回多 ToolCall；Runtime 不能把此设置当作单调用保证。

候选工具只有 `symbolic_math`、`verify_math_result`。`search_textbook` 是 Runtime 固定准备操作，不是模型提出的调用，却共享执行预算。计划的未执行项必须与成功执行区别。

## 3. AB：教材讲解与数学核验

原题：请先依据教材讲解闭区间最值的完整流程，再计算 f(x)=x³−3x 在 [−3,3] 的最值并核验关键数学结果。

### 3.1 最新基线 t1-after-AB

| 顺序 | 工具与参数要点 | 实际回执 | 有效性与预算 |
|---|---|---|---|
| 固定准备 | search_textbook，原题，同教材范围 | succeeded，已有流程/公式/例题证据 | F/A，必要，消耗 1 |
| 1 | verify derivative，original=x³−3x，candidate=3x²−3 | verified，残差 0；仅局部导数恒等式 | A，合法且有收益，消耗 1 |
| 2 | verify solutions，3x²−3=0，candidates=[−1,1] | verified，残差 [0,0]；只代入、不证明解集完整 | A，合法且有收益，消耗 1 |
| 3 | verify equivalence，(−3)³−3(−3)=−18 | verified，残差 0；仅输入等价关系 | A，合法且有收益，消耗 1 |
| 4 | verify equivalence，(−1)³−3(−1)=2 | 没有 SQL 回执/执行 | G，未消耗；不同点，不是重复 |
| 5 | verify equivalence，1³−3·1=−2 | 没有 SQL 回执/执行 | G，未消耗；不同点，不是重复 |
| 6 | verify equivalence，3³−3·3=18 | 没有 SQL 回执/执行 | G，未消耗；不同点，不是重复 |

六项数学参数均符合 Schema 和受限表达式；没有错误参数，没有重复计算或重复验证。不能把第 4–6 项算成执行失败或三次额外预算消耗。总预算 4=教材 1+数学 3，只有 1 次模型请求。模型没有机会读取这三条数学结果；Runtime 输出有限结果并正确保留 failed。

更早温度 1 的 t1-before-AB 批次也有 6 项，改用 symbolic_math 求导、解方程、逐点计算。实际执行前三项，最后三项未执行；结果仅 computed。旧空白交付与最新安全失败交付的差别已在 Base 修复，本轮不重做。

### 3.2 必要调用数与可以结束的时机

教材准备 1 次必要。求导、候选根核验及端点关系具有不同收益，不能精确缓存合并。若要求六项全部独立工具核验，需要 **6 次数学操作+1 次检索=7 次**；现有 solutions 已把两个候选根合在一次调用中。四个函数值分别属于不同的输入关系。

但原题要求“核验关键数学结果”，没有要求每个代入都独立认证。模型可核验关键关系后，用明确的因式分解和直接代入完成其余过程，并如实标注工具覆盖范围。不能据此认定“本题必须执行七个工具”。模型原先在首轮没有预算信息，选择了可选的逐点工具核验，超过可执行余额。

本可在第一轮选择不超过余额的关键核验，第二轮读取回执后直接教学。实际历史批次中，处理到预算边界时尚有待处理原生 calls；不能跳过合法 ToolMessage，假设模型已经同意结束。

## 4. 真实《传感器》B：灵敏度与表 1.1

任务：依据教材例 1.3、表 1.1 计算铂电阻温度计灵敏度，保留单位与线性条件；允许工具核对关键数值，区分计算/独立验证，不猜未读取的图。

真实来源：彭杰纲《传感器原理及应用》第 2 版，active index `c8b6947edb7858f2`，canonical hash `89dd1ed5d647ad563a49fe6c132ed7ebff8f34e6ff8c3b91d185c9625603dda3`（精确值以验收 JSON 为准）。锚点 chunk `b3696cd4e1f3706e7fd5`，第 1.3.1 节、PDF p.18。使用既有生产 BM25 + Canonical 展开 + EvidencePack + Runtime；未打开生产 Chroma 或学习 SQLite。文件前后 hash 一致。

| 顺序 | 工具与输入 | 实际回执 | 有效性与预算 |
|---|---|---|---|
| 固定准备 | search_textbook，灵敏度/表 1.1 原题 | succeeded，表格/公式/条件已进入证据 | F/A，消耗 1 |
| 1 | calculate，7/30 | computed；7/30≈0.2333333333 | 可用，但可直接对表格差商运算，消耗 1 |
| 2 | calculate，(314−307)/(230−200) | computed；同为 7/30 | 数值收益重复 C；输入绑定表格有意义，消耗 1 |
| 3 | verify equivalence，(321−314)/(260−230)=7/30 | verified，残差 0，scope=输入表达式 | A，另一区间局部检查，消耗 1 |
| 4 | verify equivalence，(328−321)/(290−260)=7/30 | 仅提出，未执行 | G；不同区间，非重复核验，消耗 0 |

三项已执行数学操作均合法成功；无错误参数。存在 **1 次可避免的数值重复计算**，不是完全相同输入。运行时不能把两个表达式直接视为同一 cache key。第 3、4 项是独立区间的关系，不可误标为 D 重复验证。

如果只需关键差商，1 次直接等价核验已能覆盖其所列输入关系；若还要工具给出十进制近似，可用 **2 次数学操作+1 次检索=3 次**。逐段工具核验并非此教学题的必需；线性建模、表格准确性与范围外外推不由局部等式回执认证。

旧模型没有读到执行结果后继续调用的证据；4 个数学 calls 同轮提出。故 E“已看结果仍继续”不成立，D 无重复验证，B 无参数错误；C 有一次数值重复，F 有一次固定准备，G 有一次未执行。

## 5. 当前预算机制：十项结论

1. **4 次是什么？** 历史与本轮定向 harness 的 RunCommand 设置 `budget_calls=4`；SQL task 的 `consumed_calls` 在 `request_tool` 原子预留时增加，不是成功次数，也不是模型轮数。生产 `chat_binding.py` 实际是 **3 次工具、5 次模型**；RunCommand 类默认 1，Store 接受的边界为工具≤6、模型≤8。不能把验收的 4 误称生产统一默认。
2. **教材检索？** 固定检索通过 FixedRunner，同一个 task 计数，通常占 1。复用既有 preparation 回执不再执行/计数；没有免费准备池。
3. **参数错误？** 原生路径为非法 Schema 参数保存 failed/input_schema 回执并消耗 1；受限语法错误也属于执行失败、消耗 1。超限前未取得预留的错误调用不计数。错误继续向模型可见。
4. **未执行？** 单纯计划不计数。正常预留后即计数，后续取消/超时不返还；不能把“实际 handler 成功次数”当 consumed_calls。
5. **计算/验证？** symbolic_math 与 verify_math_result 共享同一个预算，无独立加额。
6. **多个 calls？** 模型响应最多允许 8 个原生 calls；先检查身份、授权、版本，再按响应顺序串行预留/执行。达到余额后 abort 批次；剩余原生 IDs 得到未执行的 error ToolMessage，不产生 SQL 工具回执。不会为了压入余额而丢弃 calls。
7. **模型可见性？** Base 未提示剩余执行量，SQL 审计模型也看不到。现在每轮明确剩余/总量、固定准备数、错误也计数、同轮共享余额；实际 ToolMessages 继续给出输入、计算值、verification、scope、limitations。
8. **结束条件？** 原先有最终交付要求，没有预算感知；现在明确有足够信息即可完整回答，余额零停止新计算，必要缺口必须披露。模型仍自主选择工具或直接回答，Runtime 不建立强制教学阶段。
9. **结果复用？** Base 可以读上下文中的结果，但不同 native call ID 会再次执行；本轮增加同 run 的精确成功数学回执复用。没有额外模型请求。
10. **适配真实教学？** 统一 task 预算有成本/取消界限价值，但隐藏固定检索占用且无反馈，容易在首轮过度承诺。真实任务不能简单按“数学调用四次”规划。当前证据支持先改善表达与去重，不支持直接提高默认上限。

## 6. 实施范围与安全语义

仅修改两个生产文件：

- `native_loop.py`：每次现有模型请求的临时 delivery message 补预算信息；提示直接复用 ToolMessage、必要时可直接验证候选结果、一般解释可自行推理、齐备时完成回答。原教学 Prompt、工具选择协议、模型请求次数上限均不变。
- 同文件：对 **同一 executed_run_id、tool ID/version/schema_hash、完整校验后 args 完全相同** 的 computed 或 passed=True 数学回执复用；保留新原生 call ID 的独立 ToolMessage，指向原 `runtime_call_id`，增加 `runtime_reused=true`。不新增 SQL 执行回执/预算预留；审计在现有 native_messages 内。变量、assumptions、边界、来源、步骤、参数均参与比较；不进行符号等价归并。
- failed/unknown/unverified/invalid 不复用，错误仍完整反馈。每次复用前做合同/作用域验证，保持 active/cancel/deadline 栅栏；模型预算与 recursion_limit 保留，重复复用不能无限循环。不同 run 不缓存，PrivateProtocol 丢失的恢复仍拒绝。
- `math_tools.py`：仅增加两句工具说明，明确标量表达式不支持 tuple/list/vector 打包。没有更改 Schema、版本、数学 worker、验证算法、可信来源或通过标准。

未改变 P1-A 打包、检索、P1-C、数据库、默认预算、供应商配置、动态 mask/router、工具集合或 Agent 架构。现有预算失败的有限结果交付、failed task、失败 SSE、无成功 outbox 全部保留。

computed 不升级 verified。核验回执 valid/passed 仍只覆盖 scope。最终 answer verification 继续独立执行；本轮真实样本的局部通过没有升级成整题通过。

## 7. 前后对比与真实 DeepSeek 验收

专用 Profile `deepseek_v4.1_flash_test`，模型 API ID `deepseek-flash`（本地命名 DeepSeek V4.1 Flash）；temperature=1，thinking enabled，reasoning_effort=high，max_tokens=8192，单请求超时 180 秒，自动重试 0。未修改全局配置或凭证。供应商未返回可锁定的权重修订号。

恰好 **4 次真实 HTTP 请求**，每项最多 2 次，无额外失败发送/重试/模型评委。有限真实教材授权沿用用户本轮指示，仅发送相关检索片段；完整教材与生成正文仅留临时目录。公开证据在 [usage.json](docs/qa/agent-loop-completion/usage.json)、[AB](docs/qa/agent-loop-completion/completion-AB.json)、[sensor-B](docs/qa/agent-loop-completion/completion-sensor-B.json)。

| 场景 | 拟调用数学数 | 实际数学执行 | 固定检索 | 无效参数/语法 | 可避免重复 | 未执行计划 | 模型请求 | 最终 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Base 温度1 AB | 6 | 3 | 1 | 0 | 0 | 3 | 1 | failed，安全有限交付 |
| 本轮 AB | 3 | 3 | 1 | 1 | 0 | 0 | 2 | run completed，task degraded/unverified |
| Base 温度1 sensor-B | 4 | 3 | 1 | 0 | 1（数值） | 1 | 1 | failed，安全有限交付 |
| 本轮 sensor-B | 2 | 2 | 1 | 0 | 0 | 0 | 2 | run completed，task degraded/unverified |

**AB：** 首轮导数验证通过，候选根代入验证通过；第三项试图把四个函数值装入 tuple，Schema 可接受字符串，但 worker 返回 `unsupported expression syntax`，无有效核验。第二轮给出教材流程、连续性、驻点/不可导点/端点、四点值和最大18/最小−18，并明确逐点打包核验失败、其余步骤为直接推理，未声称整题工具通过。实际执行次数没有下降，独立通过的数学回执从3降为2，不能宣传数学覆盖率提高。

**sensor-B：** 仅 calculate(7/30)，再 verify equivalence(7/30,21/90)；后者仅输入等价性通过。第二轮交付灵敏度 0.233 Ω/°C、首末点差商、相邻增量、表中范围的线性条件和外推限制；明确计算不证明模型/表格，局部核验不涵盖整题。最终确定性门槛仍报告“没有可绑定本题结论的独立核验收据”及公式未验证，没有放宽。

两个真实样本均没有精确复用命中。减少 sensor-B 数值重复与首轮过额计划的收益来自预算提示后的行为观察，不能归因于缓存。缓存的 2→1 执行节省仅由确定性测试证明。

AB 暴露的 tuple 说明补充是在上述四次请求后完成；**最终这两句说明未做真实模型复测**。它们已有确定性拒绝/可见反馈回归，但不能宣称已稳定消除模型错误参数。

### 请求、Token 与延迟

| 场景 | 请求 | input / output / total tokens | cache_read input | 端到端秒 | 预算耗尽 |
|---|---:|---|---:|---:|---|
| Base t1-after-AB | 1 | 3570 / 858 / 4428 | 2304 | 6.37 | 是 |
| 本轮 AB | 2 | 9177 / 3511 / 12688 | 6528 | 20.563 | 否 |
| Base t1-sensor-B | 1 | 3738 / 1332 / 5070 | 2304 | 9.74 | 是 |
| 本轮 sensor-B | 2 | 8759 / 2108 / 10867 | 6912 | 17.653 | 否 |
| 本轮合计 | 4 | **17936 / 5619 / 23555** | **13440** | 38.216（两项之和） | 0/2 |

output 包含供应商报告的 reasoning tokens，未保存推理文本。首轮 input 相对历史同任务增加152 tokens（AB：3570→3722；sensor：3738→3890）；预算提示余额非零时262字符/700 UTF-8字节，动态提示不积累到持久会话。后补静态工具说明会再增加少量 input，未实测其 Provider token 数。

没有强制的额外模型请求、分类器或收尾模型。**与失败基线相比，实际费用和延迟仍增加了**：正常工具回执后的第二轮负责真正交付正文，旧样本在这一轮之前已失败。不能把“无隐式请求”说成“本轮实际 token/请求/延迟无增加”。简单直接回答确定性回归仍只有1次模型请求。

预算信息放在既有临时消息处，不增加工具 Schema 或持久历史长度；静态描述和动态剩余数可能影响提示缓存，不能承诺零缓存开销。实测 cache_read 如表，缓存命中率变化不构成优化因果证据。

## 8. 回归与未覆盖范围

- Python 3.10.21：最终 **252 passed，1 deselected**，66.70 秒。新增文件23项，通过真实数学 worker/SQL/native ToolMessage 路径；含两个原始失败批次精确离线回放。
- 单独保留的失败：`test_strict_final_does_not_merge_unverified_preamble`。Base SHA 及候选都因 computed 状态说明额外占行失败。用正常 pytest + 临时插件只在内存装入 Base native_loop 复现，数学进程正常；不是放宽/删除测试。整组门槛因此不是无条件全绿。
- 计数、非法参数、失败不复用、多 ToolCall顺序、余额零仍可直接回答、原始未执行项闭合、精确结果复用、不同变量/条件/边界/版本/source/run不复用、unknown不升级、重复复用受模型预算约束、已通过核验不丢失、普通问答单请求均覆盖。
- 现有回归继续覆盖取消、超时、数学进程回收、迟到输出、恢复栅栏、私有协议丢失拒绝、reasoning_content / ToolCall / ToolMessage后续请求连续性，数据库/SSE不得保存私有推理。
- SSE 终态与 SQL 一致、预算失败替换为有限正文后发 error、不发布成功、已有确定性回执保留均通过。前端 SSE/活动/API 展示 **31 passed**；Electron壳 **24 passed**。
- `git diff --check` 通过；检查过最终diff及提交证据的凭证/私有字段。复用依赖的前端链接已移除，缓存只写临时目录。
- 未运行全仓库、完整 Electron UI、真实付费取消/恢复、生产3次入口真实模型、视觉输入、完整Chroma混合检索。后补工具说明真实复测因四次请求上限未完成，不自动补跑。
- P1-A 长推导 provenance/打包问题沿用原报告 HOLD，不在本工作树修改。传感器 B 本轮必要表格/公式可见，未遇到该裁剪缺口。

详细范围、既有失败及初次测试配置纠正在 [validation.json](docs/qa/agent-loop-completion/validation.json)。

## 9. 是否应改默认上限

**本次不建议改变生产默认值，也没有将4改8（生产3同样未改）。** 没有证据证明这两个教学要求必须执行超过4个相互独立工具步骤；传感器本轮3个总操作已足够交付，AB的过额主要来自把每个简单代入都安排成工具检查。

如果未来明确要求六项逐一独立工具认证，AB需要7次总操作。当前 `solutions.candidates` 已批量核对两根；`kind=steps` 是最多4个、绑定可信原题条件的依赖代数步骤，原始AB/表格题没有合法 math-context，不能拿它当任意独立函数值批量口。tuple/list 不是现有合同。不能用这次失败去新建批量工具或放宽验证。

这类更严格任务应另立证据，评估显式的任务预算/已有批量合同是否适用；提高预算会增加最坏计算延迟、累计请求/输出量和取消等待窗口，并需重新验证恢复与成本边界。本轮保持原上限、单工具/模型/整run超时和取消合同，不提前实施建议。

## 10. A–H 最终答复

| 问题 | 结论 |
|---|---|
| A 为什么耗尽4次？ | 固定检索占1；首个模型响应一次提出6或4个数学calls，余额只有3，执行到第四个数学计划时拒绝。 |
| B 必要数量？ | 检索1次；传感器关键数值计算+核验2次即可交付。AB六项全部独立认证需6次数学，但原题未要求全部逐点工具认证，可关键核验+明确自推。不能把所有拟调用都称必须。 |
| C 重复/无效多少？ | Base AB无参数错误/精确重复，3项未执行；Base传感器有1次数值重复、1项未执行。本轮AB新增1次tuple语法错误；传感器0无效/重复。 |
| D 结果/预算不清导致继续？ | 预算不可见有直接代码证据；结果后继续无Trace证据，因为历史没有第二轮。修复后预算感知与调用收敛相关，但单样本不证明因果。 |
| E 最小改动有效？ | 工程 **CONDITIONAL PASS**：有界去重可确定性节省执行；两个真实样本避免超额中断并交付正文。总体完成率及稳定错误减少 **NOT VERIFIED**。 |
| F 需要改默认预算？ | 本轮没有证据支持；不修改。 |
| G 额外请求/Token？ | 无隐式模型请求；提示有input成本，实际两项各由1次失败请求变2次正常交付请求，成本/延迟明显增加，已计量。 |
| H 数学可靠性？ | 算法和通过标准不变，局部回执和最终门槛保持；真实task均unverified，未冒充成功。可靠性合同 **PASS**，完整验证教学发布 **HOLD**。 |

没有把安全失败交付、run completed 或非空正文等同于完整 verified 教学任务。剩余阻断是 AB 的不支持批量输入、最终证据/数学结论绑定、阶段文字导致的降级、生产入口/完整Electron覆盖及基线严格格式失败。
