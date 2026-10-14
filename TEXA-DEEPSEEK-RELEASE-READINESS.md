# Texa — DeepSeek Release Readiness

2026-10-13（Asia/Shanghai）。**最终判定：PASS（本轮冻结验收合同；Flash 仅可选）。** 三项 P0 修复与免费回归完成；用户随后明确“授权”，新 S1 在真实 Electron／教材检索／Provider／SQL／SSE 链路完整通过。本轮 DeepSeek 请求 **1**、Qwen **0**、重试 **0**。S5/S6采用历史真实响应与修复后生产链离线回放，不冒称新代码实时 Provider 验收。没有新 Benchmark、依赖安装、数据库迁移、默认模型切换、提交或合并 main。

状态定义：IMPLEMENTED＝代码已实现；FREE-VERIFIED＝离线／Mock／公开响应回放通过；LIVE-VERIFIED＝真实 Provider 实测；PENDING＝证据待补；BLOCKED＝明确条件未满足。历史真实协议证据与修复后回放分开记录。

## 1. 原始三个 P0 问题

| 问题 | 原有事实 | 本轮状态 |
|---|---|---|
| P0-A RequiredOutputs 误判 | S5 三工具成功、Oracle 残差 0；教学与精度描述被当字面对象 | IMPLEMENTED / FREE-VERIFIED；精度及工具绑定通过，语义完整性明确 unverified |
| P0-B 最终正文污染 | S6 原生 3 行／93 码点变成发布后 5 行／163 码点 | IMPLEMENTED / FREE-VERIFIED；SQL、SSE、Electron 回放均 3 行／93 码点 |
| P0-C 输出预算 | 4096 全部消耗于 Thinking，finish_reason=length，无公开正文 | 8192 映射 FREE-VERIFIED；新 S1 LIVE-VERIFIED，stop，4337输出，完整正文 |

读取了 `TEXA-DEEPSEEK-PRODUCTION-COMPATIBILITY.md`、PHASE0、两份 Astra ADR、FINAL-ACCEPTANCE、REQUEST-RECEIPTS、S1-UI-FIX、PRIVACY-AUDIT、PROTOCOL-AUDIT 与两组 S5 TOOL-RECORDS。历史 Phase2 Harness 工具合同错误没有被当作正式生产 Runtime 错误。权威历史证据位于 `docs/qa/evidence/deepseek-production/paid/`。

开始时 HEAD 为 `f91633673c40cf9c353e49804e2584b64f3131cc`，分支 `codex/cross-module-remediation`，已有 17 个 tracked 修改及大量未跟踪报告／适配器／实验／测试。实际工作区已包含公开阶段正文、计时、数学隔离、DeepSeek 私有协议与串行多工具、恢复栅栏、UI 教材切换竞态修复、8192 映射及 QA 凭证过滤。没有 reset、stash、覆盖这些工作或使用旧冻结 commit 代替当前代码。

## 2. 根因及实际代码定位

- `backend/services/answer_verification.py::derive_required_outputs` 是确定性生成器，**不是 LLM 生成合同**。原先按分隔符和“和／与”拆自然语言，`_anchors` 输出任意短语，`verify_answer(question_part)` 要求全部字面命中。
- `graph/generator.py::finalize_answer_verification`、`agent_runtime/multi_step.py` 与 `native_loop.py` 有三处核验说明追加。模型流式正文与最终 SQL／SSE replace 因而不同。
- `native_loop.py::wrap_model_call` 原硬编码 4096 已在此前修复；当前由 `DeepSeekChatOpenAI.native_output_token_limit=8192` 提供上限，Qwen／其他仍 4096。本轮核对真实 wire Mock，补充 request.model_settings 较小额度优先和数值计时元数据。
- 桌面检查还发现 Markdown soft newline 合并。`ChatMessage → MarkdownMessage → MarkdownRenderer` 现在只对指定行数／前缀合同使用 `white-space: pre-line`，普通回答保持现有渲染。

## 3. 具体修复内容

合同沿用现有 RequiredOutputs 字典、task verification 与 SQL schema，不引入验证模型或通用语义 Agent。

| 约束性质 | 当前处理及边界 |
|---|---|
| A 明确文本／结构 | 只有明确“必须包含／原样输出”的引号内容作 literal；明确行数、逐行前缀、码点上限、JSON、Markdown 表格、纯文本分别检查 |
| B 数学／格式 | 有效数字与舍入结果对比本题计算及独立核验收据；解析范围外保持 unverified；JSON 拒绝非 JSON 常量 |
| C 内容／教学覆盖 | 已知教材维度及短明确对象作 presence probe；真正缺失仍 failed，出现只算 coverage，语义完整性不宣布 verified；推导序列、闭式、原函数及积分常数另有结构门槛 |
| D 工具事实 | 请求运算、表达式、变量、上下限、成功独立核验及等价 candidate 绑定；其他题的成功收据不能借用 |
| E 无法确定性核验的语义 | 保留 semantic obligation，标 unverified，给出理由；不靠关键词刷成通过，未知 kind 同样不默认成功 |

旧 checkpoint 中任意中文自然语言 anchors 在读取时重新分类，不改写历史 task／checkpoint。验证结果保留检查 ID、理由，以及格式、候选数值、精度和工具证据方法；完整工具 provenance、原生 ID、operation_key 与参数仍在原 SQL 收据。证据来源合法性和相邻结论支持门槛继续保留。

## 4. RequiredOutputs 正负向验证

`tests/test_runtime_validation_remediation.py` 通过正式 Native HTTP wire Mock → LangChain → FixedRunner（实际数学工具）→ SQL → Chat SSE 回放已有真实公开响应。

- S5 三项工具重新实际执行成功；精度与工具验证状态 passed，无 RequiredOutputs failures。数值 `0.184320` 满足六位有效数字，独立定积分结果一致。
- **整段 S5 仍 unverified / task degraded**：分部积分、多项式除法教学完整性和各中间 LaTeX 等价关系没有被全量 Oracle 证明。这是准确披露边界，不是原来的 false failed，也不以已验证数值伪造整份答案 verified。
- 错数值、有效数字不足、明确推导缺失、仅数值却要求闭式／完整原函数：failed。
- 无实际核验／另一积分的收据：unverified，不能 verified。
- 既有错引用、无效 E-id、公式不等价、单位错误、编号／未编号真实内容缺失测试保留并通过。
- 原自然语言锚点的历史合同回放没有再误判 failed，且没有修改输入合同。

不能可靠识别的语义遗漏可能保留 unknown/unverified；本轮没有宣称发展目标中的逐项语义 coverage 已完整落地。

## 5. 最终正文与验证状态隔离结果

生产链：Model Content → 私有协议 Native Loop → 原有 LaTeX／引用规范化 → RequiredOutputs／Verification → `RuntimeStore.close` 的 answer＋verification → SQL task/outcome/outbox → SSE 最终 replace＋final task sidecar → ChatPage 生命周期 reducer → Electron。

三处核验说明追加全部移除。failed 仍 failed；unverified 仍 unverified；任务 degraded 仍由 SQL 权威决定。状态经 ExecutionEvent、LearningTask.verification 和现有 ExecutionTrace 展示。UI 文案改成“部分内容尚未验证，需要核对”，涵盖数学及语义未知。

S6 第二轮原始公开回答与最终 SQL answer 均 **3 行、93 Unicode 码点（不含换行）**，逐行前缀正确。SQL task artifact、run outcome、outbox body、SSE replace 一致；Electron 最终 DOM 的逻辑行数为 3。1280×820、1024×768、760×820 截图检查通过，无横向溢出。KaTeX 隐藏辅助阅读副本不计为额外正文行。

严格格式时，工具前公开阶段文字不会合并进最终格式正文；仍保留在原生公开 checkpoint，`interim_delivery` 仍 unverified。非严格回答保全既有“阶段推导／最终解答”交付结构；阶段文字不满足最后答案的 RequiredOutputs，也不因完成自动获得独立 verified。失败工具同样保持独立 unverified 元数据。

JSON、表格、纯文本、行数／前缀／码点限制的正负样本通过生产链验证；违规答案不会因为移除披露文案而变成通过。

## 6. DeepSeek 输出预算检查

**8192 配置有效：FREE-VERIFIED + LIVE-VERIFIED。8192 足以完成本次冻结 S1：LIVE-VERIFIED；统计稳定性仍未验证，本轮不扩大实验。**

- Adapter 的 8192 → Native Loop → DeepSeek `max_tokens`；Qwen 仍 `max_completion_tokens=4096`、原 enable_thinking 参数。constructor／request settings 中显式更小额度优先。
- 8192 是**单次 completion 的 Thinking＋公开输出共享上限**。reasoning 是 output 子集，不能再次相加。工具调用输出也是非推理输出，不能把它计作最终教学正文。
- 现有 SQL Runtime 的累计预算是模型调用次数（聊天合同 5 次）和工具次数，不是独立 token bucket。因而默认 Native 总输出上界 DeepSeek 为 5×8192、Qwen 为 5×4096；续答遵守剩余调用次数及每次上限，不误称每个 Run 共 8192，也不新增 Thinking 调度系统。
- 新付费 S1 gate 再收紧为 **整个 case 1 请求／8192 输出／40960 总预留 Token**；如果模型尝试续答，门禁在网络前拒绝，不增加预算。其他多轮回归仍按 SQL 累计次数守栅栏。
- `finish_reason=length` 拒绝最终提交；stop 但无公开正文现在也以 missing_final_answer 失败，不创建成功答案。流式收到的部分文字仅为未完成交付。
- Model ExecutionEvent 增加数值 output_token_limit、non_reasoning_output_tokens；非工具最终响应另记 final_content_tokens（completion−reasoning，可能含协议开销），finish_reason 只保存白名单枚举。没有持久化 Thinking 正文或密钥。

## 7. Qwen 回归结果

FREE-VERIFIED：默认 factory／显式 profile 优先级、缓存隔离、原生多工具 wire、4096、max_completion_tokens、enable_thinking、私有字段不注入、现有取消和恢复测试通过。共享后置验证现在也把无法证明的教学要求标为 unverified，不改变 Qwen 的工具权限、协议、默认模型或用户配置。

LIVE-VERIFIED（历史）：上一轮 Qwen 普通教学流式完成；这不是本轮付费验收，本轮 Qwen 请求为 0。

## 8. 免费测试结果

- 后端相关 9 文件：**161 passed**，Python `venv310` / 3.10.21。生产调用链回放、正负验证、私有 canary、原生调用、普通／教材入口、SSE、取消／恢复及预算均包含。日志：`docs/qa/evidence/deepseek-remediation/free-regression.log`。
- 前端 SSE／验证状态：**11 passed**；TypeScript -b、Vite build passed。现有大 chunk 与 Python 依赖弃用警告保留。
- macOS Electron 实机：S6 实际两轮与 S5 实际数学工具回放通过，`errors=[]`、`strict_dom_lines=3`。Provider HTTP 为 Mock，**不是新真实模型验收**。
- `git diff --check` passed。没有跑不相关的全项目矩阵，没有新增测试依赖。
- 保留失败 QA 尝试：初次隔离 18042 Origin 未加入白名单；soft newline 展示差异；KaTeX 辅助副本导致初次 DOM 计数脚本误判。均已定位并纠正，没有隐藏历史材料。初次沙箱端口／Electron 启动限制经批准的本机运行重试完成。

证据：`electron/results.json`、`ELECTRON-SQL-REPLAY.json`、三尺寸 S6 与 S5 截图、frontend-tests.log、frontend-build.log。

## 9. 真实模型验收结果及最小付费计划

本轮 LIVE-VERIFIED **1 新请求（S1）**。此前正式生产 S5 原生三工具及独立 Oracle、S6 正确原始三行输出是可靠的历史 LIVE 证据；本轮用它们证明修复后发布兼容性，标签为 FREE-VERIFIED replay，不把旧请求当新代码上线结果。

**已授权并完成：仅一次 S1。** 复用原冻结题面／Prompt／索引 c8b6947edb7858f2（schema6），不得注入替代 EvidencePack。由 Electron 发问、真实作用域检索、Provider、SQL、SSE 完整链验收。不重试，不加 S5/S6 请求，不重新 Benchmark。

价格于 2026-10-13 从两家官方页面重新核对：DeepSeek Flash 每百万 Token 峰时 cache miss $0.30、cache hit $0.006、output $1.20；非峰时减半。[DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/)。Qwen3.7 Plus 北京 ≤256K 档原价输入 ¥2／输出（含推理）¥8，当前页面限时八折 ¥1.6／¥6.4；本轮请求 0、费用 ¥0。[百炼官方价格](https://help.aliyun.com/zh/model-studio/model-pricing)。费用预留不用缓存／促销抵扣。

| 新验收上限 | 数值 |
|---|---:|
| DeepSeek 请求数／Qwen 请求数 | 1／0 |
| 每请求输入保守上限 | 32768 Token（UTF-8 字节＋2048 门禁） |
| Thinking＋正文总输出上限 | 8192 Token |
| 总 Token 预留上限 | 40960 |
| 按旧 S1 输入3018、满输出8192的峰价估算 | US$0.0107358 |
| 全输入／输出上限峰价 | US$0.0196608 |
| 含既有门禁10-token费用余量的预留 | US$0.0196728 |
| 硬预算 | **US$0.03／¥0** |

`PAID-S1-PLAN.json` + `.sha256` 是新的授权对象；旧授权已消耗其唯一 S1 请求，不能复用。`SOURCE-MANIFEST.json` 冻结当前有效代码，不只绑定 HEAD。新 launcher `scripts/qa-deepseek-remediation-paid.py` 要求 --authorized、匹配的新 APPROVAL 和源码 hash；APPROVAL.json 根据用户明确“授权”单独记录并绑定计划 hash，计划本身保持原冻结字节。共享 Budget 已免费验证更紧 plan caps 在网络前生效。

已记录 Reasoning Tokens、Final Content Tokens、Total Output Tokens、Finish Reason、First Meaningful Output、Total Run Time。首次有意义输出按 SSE 累积至少6字符并有句末标点／换行定义，不当作 DOM paint 时间。核查教材静态／准静态解释、时间常数、非矛盾关系、合适任务、合法支持引用和无编造截止频率。一次样本完成只证明该题能在8192内交付，不能证明统计稳定性。

### 已授权 S1 结果

| 指标 | 实测 |
|---|---:|
| Reasoning Tokens | 3849 |
| Final Content Tokens | 488（completion−reasoning，可能含协议开销） |
| Total Output Tokens | 4337（推理已经包含，不再相加） |
| Input／所有 Token | 3018／7355 |
| Finish Reason／wire上限 | stop／8192 |
| First Meaningful Output | 28.809秒，从SQL run创建起，SSE首个≥6字符且有标点／换行段落 |
| Provider首次公开字符 | 27.187秒，从Provider请求起 |
| Provider总时间／Runtime总时间 | 30.013秒／31.521秒 |
| 实际缓存命中输入 | 2816 Token |
| 非峰官方费率估算 | US$0.002640948（非账单），低于US$0.03硬预算 |

S1完整解释静态漏电、长时间常数与准静态范围、二者不矛盾，以及切削力测量任务；E1/E5/E6/E9真实、支持对应结论，没有编造截止频率。人工复核依据实际Native human prompt里的最终可见EvidencePack，见 `paid/S1-EVIDENCE-REVIEW.md`，没有额外评判模型。

原始模型公开正文与SQL run、task、outbox、最终SSE逐字一致；Electron公式／引用正常，独立显示“部分内容尚未验证，需要核对”。Runtime仍 **task=degraded / verification=unverified / failures=[]**，语义完整性边界如实保留，人工验收不升级SQL verified。SQL ExecutionEvent按原合同不持久化正文delta，逐字正文用SQL权威答案与捕获的SSE对照。正式请求后冻结源码hash再次全部一致。

证据目录 `docs/qa/evidence/deepseek-remediation/paid/`：APPROVAL、REQUEST-RECEIPTS、FINAL-ACCEPTANCE、FINAL-VISIBLE-EVIDENCE、S1-FINAL-ANSWER、VERIFICATION、Electron结果及截图。UI捕获器保留6个清理abort调用诊断，无pageerror/requestfailed，流和SQL均完成；不当作6次模型取消。付费QA进程与Electron已退出，没有后台重试。

## 10. QA 凭证风险检查

FREE-VERIFIED：付费 QA 保存器过滤 API_KEY／SECRET／TOKEN／PASSWORD／PRIVATE_KEY／AUTHORIZATION，仅写公开配置。新增回归走**真实 save_model_profile → save_profile → 实际 env writer**，profile、env、返回结果均不含继承或显式测试凭证；原 writer 回归仍保留。

当前 tracked＋nonignored untracked 文件、隔离 QA SQL／profile／env 和本轮材料，对两把真实凭证值作 RAM 内比较，无精确匹配，不输出值或密钥 hash。通用 key 模式两处命中均为已有合成 canary 测试／审计说明，已分类；Mock QA 的假密钥不当作真实泄漏。免费阶段扫描数值见 PRIVACY-AUDIT.json；授权后再次扫描3512个仓库文件及14个付费QA SQL／profile／env相关文件，真实凭证精确命中均为0，见 paid/PRIVACY-AUDIT.json。

**历史风险仍存在。** 上轮真实凭证曾写入临时 local.env；当前清理不能证明同步、版本控制历史、备份或系统快照中没有副本。建议轮换对应 DeepSeek／Qwen 密钥；不声称历史零泄漏或物理零化。用户原始凭证文件未修改。

## 11. Astra 是否参与及原因

本轮没有调用 Astra。问题可通过现有合同的局部分类、发布说明移除、数值元数据及严格换行修复解决；SQL schema、权威状态／持久化结构、工具协议与执行权限未改变，没有需要定点架构裁决的冲突。此前 Astra ADR 与二审条件继续保留。

## 12. 剩余发布 Blocker

本轮冻结验收范围内**没有尚未解决的P0或新增协议／安全／SQL-SSE一致性Blocker**。Flash由CONDITIONAL提升为 **PASS（可选模型准入）**，依据新S1 LIVE-VERIFIED、历史S5工具／Oracle与S6真实原文，以及修复后S5/S6生产链FREE-VERIFIED回放；用户允许可靠原始响应离线回放，因此不追加付费S5/S6。

持续保留的边界：教学语义／中间公式未被确定性全面证明时维持unverified；私有状态丢失拒绝续答；单个S1不能证明8192统计稳定性。上述不变成假verified或额外免费／付费Benchmark。历史凭证副本无法排除，应轮换对应密钥；当前扫描未见秘密不消除该历史风险。

**Qwen3.7 Plus继续默认，Flash仅进入可选范围。不自动切换已有profile、不合并main、不扩展路由架构。** 本次切换仅发生在隔离QA profile，用户生产配置未修改。
