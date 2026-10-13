# Texa — DeepSeek V4.1 Flash Production Compatibility

2026-10-13。当前判定：**CONDITIONAL — 仅允许受限测试或开发环境使用，不批准正式发布。** 用户明确授权冻结预算后，已通过正式 Chat API / macOS Electron 执行真实模型验收：DeepSeek 7 次、Qwen 1 次。原生多工具续答、取消栅栏和恢复拒绝通过；S1 输出截断、S5 验证误判、S6 最终格式失败阻止 PASS。S1 额度修正后的真实验收 **Pending**。用户 profile、默认 Qwen3.7 Plus、用户教材索引和学习数据库保持原样，没有合并 main。

## 1. 基线与原有生产缺口

分支 `codex/cross-module-remediation`，HEAD `f91633673c40cf9c353e49804e2584b64f3131cc`。旧实验使用该 commit 的冻结副本；当前工作区还包含未提交的公开阶段正文、计时、取消检查与隔离数学改进。保全原差异 `/private/tmp/texa-pre-deepseek-production.patch`，在其上局部修改，未 reset/stash 或覆盖实验资料。

Python 使用 venv310 / 3.10.21。已安装 langchain 1.3.2、langchain-openai 1.2.2、langchain-core 1.4.0、langgraph 1.2.2。未升级依赖或迁移 SQL schema。

ChatOpenAI 的字典/Delta 转换丢弃 reasoning_content，出站转换也不回传；其 max_tokens 自动转成 max_completion_tokens，与 DeepSeek 原生参数不同。正式 Loop 拒绝同消息多个调用；ToolNode 默认可并发。SQL 保存公开原生消息和工具收据，不能从公开 checkpoint 重建隐藏推理。恢复时读取当前 profile，原实现还未冻结协议身份。

两轮实验的 PrivateTranscript、多工具串行与真实收据仅证明隔离 Harness 的能力，未当作正式 Runtime 验收。详见 [Phase 0](docs/qa/evidence/deepseek-production/PHASE0-FINDINGS.md)。

## 2. Sol 最小方案与 Astra 审查

局部 DeepSeek ChatOpenAI 子类 + 一次 Run 私有 RAM 作用域，保留 LangChain 原生 AIMessage/ToolMessage；SQL 继续拥有执行、预算、收据和提交权。无新 Framework、Runtime 或协议数据库。

[Astra ADR](docs/qa/evidence/deepseek-production/ASTRA-ADR.md) 有条件认可方案，P0 要求私有状态关闭栅栏、协议身份冻结、全批校验、取消/预算停止排队项、参数映射和截断拒绝。已采纳这些必要要求。

原建议 graph 级 max_concurrency=1 实测造成 stream 等待任务占满唯一线程，连 1Model/0Tool 都停滞。Sol 提供最小复现及 Condition 顺序门候选，进行了必要的 Phase 4 二审。Astra 明确撤回全局单线程建议并认可局部门控，要求 checkpoint 后发布批次、唯一认领、执行期间释放锁、致命错误唤醒全部等待者。实现采用该结论。[二审记录](docs/qa/evidence/deepseek-production/ASTRA-ADR-ADDENDUM.md) 由 Sol 整理实际反馈；Astra 随后触及账户额度限制，未自行交付补充文档，不冒称完整二审报告。

## 3. 实际修改范围

| 文件 | 修改 |
|---|---|
| `llm/deepseek_chat.py` | 原生 Delta/非流式推理截获、私有作用域、DeepSeek 出站回传、max_tokens 映射、8192 原生输出上限（显式较小额度优先）、cache usage 标准化、固定错误脱敏 |
| `llm/factory.py` | 仅真实 DeepSeek provider 选专属子类；其他 provider 保持 ChatOpenAI |
| `llm/agent_adapter.py` | native Run 建立/释放作用域，生成不含凭证的协议身份 |
| `llm/registry.py` | 现有 deepseek-flash 标注 V4.1 Flash，Thinking enabled/high；Qwen 默认不变 |
| `native_loop.py` | 同 SQL 固定教材准备与收据复用；整批调用校验、局部顺序门/停止标记、私有轮次提交、恢复拒绝、截断拒绝和数值 usage |
| `store.py` | 现有 checkpoint 增加非私有身份字段；有界 turn 只读查询；明确失败文案；cached input 数值统计 |
| `chat_binding.py`、`backend/api/chat.py` | DeepSeek 普通/教材原生入口与固定证据准备；会话页面对尚未提交最终答案的 SQL 任务做只读投影，恢复暂停入口；游标仍引用权威会话消息，不写合成历史 |
| `frontend/src/pages/ChatPage.tsx` | 真实 Electron 暴露的教材切换竞态：忽略被更新请求取代的回调，比较最新范围，避免重复设置触发取消 |
| `tests/test_deepseek_paid_budget.py` | 请求前 Token/费用/次数/模型/端点及禁止重试门禁及 QA 凭证不落盘的 7 项免费测试 |
| `tests/test_deepseek_production.py` | 正式 HTTP 模拟响应 → LangChain → Native Loop → FixedRunner → SQL 的免费验证 |
| `tests/test_native_math_loop.py` | 原模拟模型支持多调用；恢复 fixture 补冻结身份，保留原收据/验证断言 |
| `scripts/qa-deepseek-production-*` | 隔离 Electron 实际交互，模型 HTTP 响应受控，真实 Runtime/SSE/配置与存储 |

DeepSeek 普通教学、教材问答和数学使用同一 Native Loop / SQL Runtime。入口读取 Adapter 暴露的原生协议需求，不在业务层判断 provider。普通教学候选工具为空；教材路径先由固定 `search_textbook` 经 FixedRunner 获取真实生产检索 EvidencePack，冻结范围、索引版本和 schema，然后使用共享 `prepare_answer_generation` 提示及后置验证。teach/summarize 复用纯 EvidencePack 章节准备接口，chapter SSE 先于正文，无额外模型请求。数学候选仍仅两个 READ 工具；教材数学可以先检索再使用这些工具。Qwen 仍走原入口，没有扩展写工具或非数学资产动作的权限。

这一步是 Sol 后续核对后完成的局部入口接线，范围为已有固定检索准备与现有 Native Loop，不将所有领域迁入 Native。Astra 的 Deferred 全领域迁移没有实施；无需新增 SQL schema、工具执行合同或新 Framework。非数学资产管理的旧 action 流程不在本轮扩展，仍有单调用限制。

## 4. Thinking 生命周期和隐私

原生入站在 LangChain callbacks 之前截获 reasoning_content；内容从不附到公开消息 metadata。共享 ContextVar 对象按已完成 AIMessage.id 保存，出站只为同 Run 的真实原生 assistant 注入原文，调用 ID 和消息顺序仍由 LangChain 保留。

每轮先 begin，再完整收集、成功后 commit。工具轮缺私有字段明确失败；合法空值与最终轮零新增推理可处理。单 Run 累计私有容量上限 1 MiB，超限失败而不截断续答。Run 结束、异常、取消、超时均 close/clear；已复制上下文的迟到线程无法重新填入。Python 逻辑释放不等于物理内存零化。

隐藏推理不进入 SQL、Checkpoint、UI、SSE、ContextPack、笔记、Commentary 或公开 callback。SDK 请求异常在模型错误 callback 前变成固定码；原生路径发现 OpenAI 请求体 debug 日志开启时拒绝运行。没有新增任何私有持久化、密钥摘要、协议数据库或加密方案。

ContextPack 当前以 System/Human 引用文本输入历史，未将旧公开回答伪造为缺推理的原生 assistant。当前支持的协议是单 completion 的 Chat Completions，Responses API 被明确拒绝。

## 5. 多工具和 Runtime 一致性

同消息最多 8 个调用，先检查所有 ID、重复、名字、READ 权限和冻结 schema/version，再发布批次。parallel_tool_calls=false 只是发送参数，不能授权执行。每项仍经 FixedRunner 的完整权限、schema、作用域与 SQL 预算检查。

工具按原生批次顺序执行。FixedRunner 完成、ToolMessage 写入 checkpoint 后才放行下一项；正常工具错误形成失败、计预算的收据，可继续模型解释。致命错误立即设置停止标记并唤醒排队者，SQL owner/status 栅栏仍生效。预算耗尽、取消或 checkpoint 失败后不补执行、不续答，不重置消费计数。

原生 ID、SQL operation_key、model_tool_call_id 与 ToolMessage 逐一对应。最终轮仍独立经过原验证门槛；保全工作区已有的阶段公开正文和 unverified 规则，没有将阶段文字当教材/计算证据。

## 6. Checkpoint、取消和恢复边界

SQL 保存公开正文、原生调用关系、预算、执行事件与收据。首次 checkpoint 冻结 provider/model 和去除 URL userinfo/query、仅含协议参数白名单的 wire digest；不保存原 URL/options/凭证。身份不一致为 native_model_changed。

- 新 Qwen checkpoint 可按原合同恢复，已完成工具通过 SQL 收据回填，不重放。
- DeepSeek 作用域退出后，含 assistant 的 checkpoint 无法续传必要私有状态：恢复在任何新模型/工具调用前进入 failed / provider_protocol_state_lost。用户明确重新发起问题，旧收据保留。
- 没有 assistant 协议消息时可继续原任务，仍守累计预算。
- 含 assistant 而没有身份的旧 checkpoint 无法证明原 provider，明确 native_protocol_identity_missing；这是已披露的旧数据恢复限制，不能默认为当前 Qwen。
- 进程重启通过原 SQL recovery fence 保留中断事实。免费子进程测试证明已成功收据 attempt_count 保持 1。

Electron 首次验收发现暂停任务刷新后只有用户问题、没有恢复入口。已补只读 SQL delivery 投影，既不创建最终答案消息，也不污染 Ledger/笔记来源；正式 outbox 消息出现后同 ID 投影消失。辅助投影失败不令整页失败。暂停入口、恢复失败详情和重新提问路径已在 macOS Electron 验证。

## 7. 免费验证与 Qwen 回归

最终相关后端回归 [free-regression-final.log](docs/qa/evidence/deepseek-production/free-regression-final.log)：**250 项通过**，包括 DeepSeek 专项 **38 项**、Qwen3.7 Plus 原生 wire、SQL/Runtime、SSE、预算、过滤和恢复。原 209 项记录保留，不把重叠结果相加。

覆盖普通教学/教材讲解同步与 SSE 入口、chapter 先于正文、准备失败零模型、检索后暂停恢复复用收据，以及无工具、单工具、同消息多工具、跨轮、拆片参数/推理、合法空最终推理、schema 失败、批后部未授权/缺 ID/重复 ID、预算停止排队项、取消、checkpoint 写入失败、迟到响应、私有清理、并行作用域隔离、子进程重启、模型身份变化、失败脱敏、缓存 usage、异步公开流、最终验证及只读投影隔离。

Qwen 默认、显式配置优先、缓存隔离和现有恢复回归通过。专项 wire 验证 Qwen 仍发送 max_completion_tokens/enable_thinking，不注入 DeepSeek reasoning_content；真实 Qwen 冒烟已执行，正常流式完成，公式依据不足保持 unverified，未伪造 verified。

前端 TypeScript/Vite 构建通过；SSE 状态 10 项通过；桌面壳 15 项通过。初次受沙箱 loopback 权限限制的一项桌面测试经允许本机端口后通过。现有构建大 chunk 警告保留。

环境曾因没有 npm 而使用备用 pnpm，触发自动安装检查，将现有包移到 .ignored；已中止并原位恢复全部包，清理本次 cache。没有下载/升级依赖或改变 package/lock 文件；之后直接运行现有 Node 工具验证。

失败分类保持具体来源，不归为笼统“模型不可靠”：

| 类别 | 实际判据 / 记录 |
|---|---|
| Provider 协议 | 缺 reasoning 字段、非法 Delta/choice、输出截断；固定 provider 错误码 |
| Runtime 状态 | 批次 ID/权限/schema、模型/工具预算、owner 栅栏、队列中止 |
| 工具执行 | 非法参数、handler/output schema/timeout 的失败收据，计入预算 |
| Checkpoint / 恢复 | 私有状态丢失、旧身份缺失、模型变更、写 checkpoint 失败；不重放 |
| UI / SSE | 实测刷新丢失暂停投影已修复；选择器/折叠详情的 QA 脚本失败另行保留 |
| 模型内容 | S1 4096 总输出全部消耗于 Thinking，无正文；S5 数学结论正确；S6 模型正文三行合规，Runtime 发布后五行失败。Mock 不当作模型质量证据 |

## 8. Electron / 真实 Provider 验收

[Electron 免费结果](docs/qa/evidence/deepseek-production/electron/results.json) errors=[]。实际 macOS Electron、正式 factory/Adapter/SQL/SSE，只有 Provider HTTP 响应为 Mock。通过模型方案选择 Flash、普通教学 1Model/0Tool、多工具最终输出、三个桌面尺寸、停止、刷新重开会话和明确恢复失败。教材入口有免费真实 FixedRunner + SQL + Mock 检索的回归；当时真实教材索引及教材 Electron 验收为 Pending，后续真实结果见下文。检查 SQL：恢复后 consumed_model_calls=2、consumed_calls=2；两条工具收据均 succeeded / attempt_count=1，没有重放。

免费交互中出现的测试选择器、折叠侧栏和失败详情未展开问题保留在 attempt1/2/3 记录；实际发现的刷新投影缺口已修复。截图见同目录。

用户后续以“授权”明确批准冻结清单与预算，授权及 SHA256 保存在 [APPROVAL.json](docs/qa/evidence/deepseek-production/paid/APPROVAL.json)。以下为真实验收，独立于上面的 Mock 结果。

隔离复制冻结 Canonical / 当前 active index c8b6947edb7858f2（schema 6）；源 manifest、三块冻结教材内容及真实本地检索预检通过。使用本地 ONNX embedding 和真实 dense/lexical 检索，没有直接注入预制 EvidencePack。从用户原有凭证文件加载真实密钥，隔离 profile 无密钥；QA .env 的临时副本发现与清理详见下文。HTTP 门禁在网络前限制唯一端点、指定 case/model、原始 UTF-8 字节 + 2048 的输入 Token 保守上界、输出 cap、次数与独立币种费用；SDK 重试为 0，未知 usage 保留完整预算，禁止该 case 再试。额外后台概念提取被门禁拒绝，没有额外外发请求。

实际调用均走 Electron → Chat API → Registry → Provider Adapter → Native Loop/现有 Qwen 路径 → FixedRunner（有工具时）→ SQL → SSE → Electron。付费服务已停止。证据汇总以 [FINAL-ACCEPTANCE.json](docs/qa/evidence/deepseek-production/paid/FINAL-ACCEPTANCE.json) 为权威，原始数值收据见 [REQUEST-RECEIPTS.json](docs/qa/evidence/deepseek-production/paid/REQUEST-RECEIPTS.json)。UI 脚本历史 status=completed 只表示交互结束，不表示验证通过；S1 首次脚本还存在等待竞态，其标记已由 SQL/Provider 记录纠正。

| 场景 | 请求 / 工具 | 首个可读正文片段 / Run 耗时 | 正式结果 |
|---|---|---|---|
| S1 教材概念 | 1 Model / 1 search_textbook | 无正文 / 28.917s | 真实检索成功；4096 输出全部为 Thinking，finish_reason=length；明确 provider_output_truncated，未发布虚假答案 |
| S5 积分 | 2 Model / 3 Tool | 13.350s / 15.619s | 同消息 3 个调用，积分、数值计算、定积分核验均 succeeded，attempt_count=1；原生 ID 严格匹配，续答回传私有字段。最终验收 failed，task degraded |
| S6 第1轮 | 1 Model / 0 Tool | 4.322s / 6.184s | 内容正确；公式无独立计算支持，unverified / degraded |
| S6 第2轮 | 1 Model / 0 Tool | 5.393s / 5.591s | 模型原正文 3行 / 93码点合规；发布附加提示后 5行 / 163码点，严格格式失败；RequiredOutputs failed / degraded |
| 取消 | 2 Model / 2 Tool | 续答停止，无完整最终正文 / 3.868s | 工具各执行一次；第二请求已 HTTP200 时用户停止，usage 未返回，保留完整费用额度。迟到事件未写入最终答案 |
| 刷新后恢复 | 新请求0 / 新工具0 | 14.52ms | provider_protocol_state_lost 明确终态，Electron 展示原因及重新提问入口，无重放 |
| Qwen 默认冒烟 | 1 Model / 0 Tool | 17.343s / 22.249s | 原路径公开流与完整答案正常；公式无独立依据保持 unverified |

时间按权威 Runtime 起点计算，首个可读片段定义为至少6字符且含句末标点/换行的累计公开正文，来自真实 SSE elapsed_ms；Provider 首个非空 Delta 和单请求耗时另保留在收据。未测 DOM 首次绘制延迟，不把一个汉字的首 Token 冒称完整有意义答案。S6 两轮 Run 累计 11.776s，case 含前端调度耗时另见原交互记录。

S5 独立数值核对 J=(2/3)ln2−5/18=0.1843203425955191，与真实积分及残差0的工具收据一致。验证器将“至少6位有效数字”“明确区分自己推导”“实际工具已验证的结论”等要求当作核心对象进行字面锚点检查，出现 false fail；未放宽门槛。S6 同类解析还将“空格”等格式描述当分项对象，追加失败提示破坏三行合同；属于 Runtime 验证/答案发布缺口，不能算模型格式失败。

SQL 原生消息与公开 SSE 均没有 reasoning_content 字段；UI 没有私有正文。真实隐藏文本从未采集，无法事后做隐藏原文等值泄露检查；免费 canary 测试提供精确非泄露断言，真实 usage 仅保存数字。

## 9. 预算结算、后续修正与剩余 Blocker

[冻结计划](docs/qa/evidence/deepseek-production/PAID-ACCEPTANCE-PLAN.json) 保持原文/原 SHA256，历史 status 仍为当时 Pending；授权和执行状态通过独立记录表示。预算最多 DeepSeek10 + Qwen1、总Token421888、$0.20 / ¥0.25、零自动重试，未超限。

实际 DeepSeek **7次**，6次取得完整 usage：输入11502（缓存4224）、输出含推理9427（其中推理7726）、总20929。一次取消请求 usage 未知，不计为0也不重复相加 reasoning 子集。Qwen **1次**：输入458、输出含推理1120（推理809）、总1578。已知总Token **22507**，未知请求上界保留 32768+4096。

按真实时段/缓存 usage 估算 DeepSeek 已知费用 **$0.006760572**，取消未知请求保留 **$0.0147576**；合计已知+未知保守上界 **$0.021518172**。Qwen估算 **¥0.009876**。这不是供应商账单；全部请求预留为 $0.1033032 / ¥0.131152，仍低于冻结上限。

最终隐私扫描发现既有 profile 保存器自动将继承的真实密钥写入隔离 QA 的 local.env；此前“仅 RAM”描述有误。密钥未出现在 profile、SQL 或付费材料，用户原始凭证文件未修改。已删除 QA .env 中的凭证项并设0600，再次扫描 QA SQL/profile/env 均无密钥；QA 保存器改为仅写非敏感配置，并以真实 env writer 的免费回归验证。清理为逻辑删除，不声称磁盘物理零化。审计前后结果保存在 [PRIVACY-AUDIT.json](docs/qa/evidence/deepseek-production/paid/PRIVACY-AUDIT.json)。费率来源为 [DeepSeek 官方 Pricing](https://api-docs.deepseek.com/quick_start/pricing/) 和授权前冻结核对的 Qwen清单费率，原始计价带保存在收据。

真实验收期间及之后的局部修正：

1. **教材范围竞态已修复。** 多次 S1 UI 中断均发生在工具/模型之前（付费0）；公开取消调用栈定位到过期 switchBook 回调重复设置教材。增加请求序号和最新范围比较，正常范围变化仍取消旧任务。修复后真实 S1 完整运行到 Provider 返回，TypeScript/Vite 构建通过。调用栈和修复身份保留在 paid/electron/S1-cancellation-callsite.json 和 S1-UI-FIX.json。
2. **DeepSeek 输出额度已修复，真实复验 Pending。** Native Loop 的硬编码4096覆盖了 S1 已授权8192设置，这是 Sol 审计遗漏。改为由 DeepSeek Adapter 提供8192总输出上限，Qwen/其他仍4096；Thinking 和正文共享额度。后续76项免费回归通过，明确断言 DeepSeek8192 / Qwen4096，并保留显式较小上限。S1授权仅1次已使用，不追加付费重试，不宣称8192已通过真实模型。初始、UI修复与最终源码身份分别保留，后改代码未冒充付费时已验证版本。

剩余发布 Blocker：

- **S1 修正后真实教材答案及引用验收 Pending。** 需要新的单次具体预算授权才能复验；原失败记录保留，不能以免费测试或第一次真实检索成功替代完整教学答案。
- **RequiredOutputs 内容/格式识别和最终提示发布边界未解决。** 推荐独立局部修复：显式格式合同与内容覆盖分开；使用可复现的数学/格式检查，验证状态通过既有 task/ExecutionTrace 公开，不改写受严格格式约束的答案正文。必须保留未知/失败披露，新增负向回归证明没有放宽验收。当前未擅自重构共享验证器来获取 PASS。
- DeepSeek 含助手历史的中断无法无损恢复、旧无身份 checkpoint 的恢复拒绝为已披露降级。无损恢复需要单独批准私有生命周期/持久化方案，不在本轮扩大范围。

因此最终 **CONDITIONAL**。原生协议和受控执行可供开发环境继续验证；S1 完整教材答案以及共享验证/严格格式发布合同通过前，不作为正式可选模型发布。Windows Electron未执行；本轮未重新排名或进行付费 Benchmark。
