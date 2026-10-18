# Texa Agent Runtime P0 数学可靠性修复

2026-10-18。范围：现有数学解析、条件合同、原生工具回执和交付要求保留。不新增工具、模型审查、路由器、Agent 阶段、依赖或数据库迁移。

结论：建议合入本次有限修复。解析根因与 Runtime 信息保留已修复并有回归；不能据此宣布任意教学推导或语义完整性已可靠保证。真实复验统计题恢复了最终 CDF 推导，但仍未显式列全 CDF 区间外分支。

## 1. 审查与复现

起点为 `Texa_MacOS` / `c0673fc75d938bce25304a08aac8c70a70c11f18`。开始时已有习题候选、侧栏/布局等改动和 `patch_notes.md` 的其他任务记录；本修复的八个代码/测试文件原先均干净。没有 reset、stash、覆盖或提交其他任务代码。

已逐段追踪：

- `chat_binding.py` 的候选选择、数学开关和原题/required outputs 冻结；`llm/agent_adapter.py`、`deepseek_chat.py` 的实际 Provider 与私有协议边界。
- `native_loop.py` 的 create_agent、中间件、SQL FixedRunner、标准 AIMessage/ToolMessage、恢复和最终生成；`runner.py`、`store.py` 的权限、版本/schema、预算与完整回执。
- `math_tools.py` / `math_worker.py` 的 Pydantic、受限 AST、符号假设、运算、校验、spawn 和输出预算。
- `tool_orchestration.py` 的兼容工具链与上下文压缩；`graph/generator.py`、`teaching_prompts.py`、`answer_verification.py` 的消息装配、教学约束和最终 Gate。
- `REAL-NATIVE-MATH-ACCEPTANCE-2026-10-13.md`、原 questions/runtime-traces、近期提交及数学/原生/恢复/答案验证测试。

没有仅凭旧报告重复修复：后续提交 `33d6db0` 已保留阶段文字、要求最终独立重述、在核验时隔离 interim，并覆盖 SSE final replacement。本次保留并复验这些逻辑。现有 Refined Teaching Prompt 已要求必要条件/步骤，没有发现与完整解答相冲突的强制简答规则。

| 问题 | 实际根因与修复前行为 | 修复后行为 |
|---|---|---|
| theta / lambda | schema、AST、worker 各硬编码八个变量；lambda 还是 Python 关键字 | 三处统一为受限标识符合同；lambda 仅转为数学 Name，不能成为可执行 lambda |
| 统计积分 | 原失败输入是 `integrate(n*x^n/theta^n, x, 0, theta)`；即使修复 theta，旧 closed-bound 检查仍拒绝上限 | 允许与积分变量无关的实数参数限；显式条件传递；不能确定条件/收敛性时保留限制 |
| 定义域丢失 | 已复现 `x/x=1` 无条件通过，候选 `x=0` 也通过；解析时约分抹掉除零限制 | 核验使用未约分 AST；非零条件不明和未定义残差不通过 |
| 缺条件与错误混同 | `sqrt(x^2)=x` 无条件未通过，但被统一标为 failed | 区分 verified / failed / unverified；nonnegative 条件可验证，未知不冒充反例或证明 |
| 结果边界 | 原生 SQL → ToolMessage 已完整；结构化最终上下文却会在 3500 字后被 summary 替换；worker 会覆盖未通过核验的 data | 原生回传保持原状；数学结构化回执完整保留；未通过的残差、条件和 scope 不丢失 |
| 交付要求 | 已有原题/required outputs，但生成使用 resolved query；缺少每轮与原始 request_question 的明确提醒 | 每个原生模型步骤携带精确原题和短交付约束；不累计到历史，不新增模型调用 |

## 2. 修改文件与关键合同

生产代码仅四个文件：

- `backend/tools/math_tools.py`：最多 32 字符的 ASCII 数学标识符、16 个表达式符号/假设，支持 Greek 别名和编号参数；函数仍为显式白名单，常量/函数不能当变量，拒绝属性、下标、lambda、推导式等代码结构。保留 300 字符/120 AST 节点、数值和幂预算。SymPy 自身的 `Abs` 拼写可安全往返。使用 tokenize 保留数字精度与隐式乘法，不拆坏 `mass2` 等标识符。
- 同文件：共享显式假设校验；支持实数、正/负、非正/非负、整数、nonzero 等 SymPy predicates。**nonzero 在 SymPy 中意味着实数且非零**，不是一般复数非零条件。省略假设仍为一般复数，不擅自补正性。非积分操作传积分限、非极限操作传 point 直接拒绝，防止求解区间被静默忽略。
- 同文件：以现有 SymPy 化简、谓词、continuous_domain 进行有限条件检查；保留原始分母/函数/幂结构。参数积分、奇点/端点条件、未求值表达式和条件分支不能凭零残差获得 verified。候选解检查自身假设与代入定义域；空集不当作无解证明。
- `backend/tools/math_worker.py`：复用统一 schema，不再复制变量表；保留失败/不确定核验 data。原进程数、CPU/内存、5 秒、输入/输出字节预算及取消回收均保留。
- `backend/services/agent_runtime/native_loop.py`：逐轮提醒精确原题、教学交付和工具 scope；提醒不进入持久消息历史。工具版本升至 v2，旧 checkpoint 在调用模型前 fail closed；不静默沿用旧条件核验结果。
- `backend/services/tool_orchestration.py`：数学机器可读输出不受展示 summary 替换；兼容路径的 prompt text 仍保持既有 9000 字预算。**不把这个投影当作完整原生 ToolMessage**。

测试扩展放在既有 `test_math_isolation.py`、`test_native_math_loop.py`、`test_tool_orchestration.py`、`test_answer_verification.py`，没有新 Benchmark。核验结果含 assumptions / scope / limitations；verified 只覆盖输入运算，不覆盖建模、题外条件、整套自然语言推导。没有增加 mandatory verify 调用、重解模型或答案模板。

## 3. 验证结果

| 验证项 | 结果 | 依据/限制 |
|---|---|---|
| 相关后端回归 | PASS | Python 3.10.21 / venv310，13 个既有测试文件 213 passed；随后新增旧合同阻断并复验整个 native 文件 33 passed（32 项与前一批重复，总计 214 个不同用例） |
| 原数学能力 | PASS | 数值精度、科学计数法、化简、求导、积分、极限、复数解、自动核验兼容路径及离线既有门槛 |
| 命名与安全 | PASS | theta/lambda/alpha/beta、Greek、编号参数、假设往返；非法属性/函数/代码、未授权工具等拒绝 |
| 条件与传播 | PASS | sqrt、约分除零、对数、变量假设、候选解/空集、奇点积分、参数限；data/verification 原样传回模型，旧版本无模型调用即拒绝 |
| Runtime/协议 | PASS | SQL 身份/预算、标准调用 ID、恢复、实际停止迭代、阶段文字、SSE replacement、DeepSeek 原生协议与错误边界 |
| Electron 合同 | PASS | `npm test` 24 passed；初次 sandbox 端口 EPERM 后在允许 loopback 的环境重跑通过 |
| Git diff | PASS | 已检查本次文件 diff 与空白；无依赖、DB、索引或全局配置改动 |
| Windows / 正式安装包 | NOT VERIFIED | 本次未进行打包或实机验收 |
| 整题语义完整性/全部中间步骤 | NOT VERIFIED | 有限 Runtime 检查不能提供这种保证，不新增启发式“已证明”标记 |

后端命令：

```sh
venv310/bin/python -m pytest -q tests/test_math_isolation.py tests/test_native_math_loop.py tests/test_tool_orchestration.py tests/test_answer_verification.py tests/test_agent_runtime_chat_binding.py tests/test_agent_runtime_p0.py tests/test_agent_runtime_p2a.py tests/test_agent_runtime_p2c_receipts.py tests/test_agent_runtime_p2_recovery.py tests/test_runtime_events.py tests/test_runtime_validation_remediation.py tests/test_minimal_teaching_prompt.py tests/test_deepseek_production.py
venv310/bin/python -m pytest -q tests/test_native_math_loop.py
```

一次新增 stale-contract 测试初稿忘传已有 runner 所要求的 answer_generator，测试夹具抛 ValueError；补齐该参数后 33 项通过。未放松业务断言。既有 Starlette/AnyIO 弃用警告保留。没有重跑含冻结源码身份 pins 的全量发布评测，也没有改 pins。

## 4. 两道真实模型/Electron 复验

使用桌面当前配置 **DeepSeek Flash**，未改 model、API key 或 profile。项目进程默认 Qwen 没凭证，但 Electron 实际 userData 中已有 DeepSeek 配置；只读加载到隔离进程内存，学习数据与空 ENV_PATH 位于 `/private/tmp/texa-p0-math-20261018`。沿用 Provider factory、主聊天 API、原生 Runtime、SQL、真实 SymPy、SSE 与现有 Electron 验收脚本，复用已构建 renderer；不重编译其他任务的 UI 改动。

最大 2 题 / 8 远程调用 / 每调用至多 8192 输出 token，无重试，未强制 tool_choice、替换模型输出或增加审查模型；实际 **3 次远程调用、3 次工具、19,520 tokens（输入 9,180 / 输出 10,340，含 reasoning）**。未采用旧 Qwen 价格估算当前账单。QA 窗口和后端均已退出。

| 原题 | 实测行为 | 评审结论 |
|---|---|---|
| 空间曲线积分 | 34.407 秒；1 模型 / 0 工具；球面配方右端为 1，方向/旋度/投影与积分值 `4*sqrt(5)*pi/25` 正确 | 本次样本正确；模型自主不调用工具，不能据此证明工具一致性改善；Runtime 仍 unverified/degraded |
| 次序统计量/无偏/MSE | 21.670 秒；2 模型 / 3 工具；带 theta>0、n>0 的一、二阶矩积分与 MSE 化简成功，全部实际回执逐字段一致回传 | 最终正文包含 CDF 概率推导、两个矩及两问；针对“推导只在 interim”的缺陷改善可观察；但 CDF 在区间外的 0、1 分支未显式列出，完整性仍 PARTIAL，Runtime 仍 unverified/degraded |

这不是同模型前后配对实验：旧报告用 Qwen，本次用当前配置 DeepSeek；不能把单次模型表现差异归因为修复或推断一般准确率。统计题没有调用 verify_math_result，三次 symbolic_math 成功不等于整题通过核验。

[真实用量回执](evidence/p0-math-runtime-2026-10-18/provider-receipts.json)、[SQL/原生消息/最终答案](evidence/p0-math-runtime-2026-10-18/runtime-traces.json)、[逐字段回传核对](evidence/p0-math-runtime-2026-10-18/receipt-integrity.json)、[独立工程评审](evidence/p0-math-runtime-2026-10-18/independent-review.json)、[Electron 完整采集（无损 gzip）](evidence/p0-math-runtime-2026-10-18/electron-results.json.gz)。

截图：[曲线积分完成](evidence/p0-math-runtime-2026-10-18/q2-stokes-complete.png)、[统计题完成](evidence/p0-math-runtime-2026-10-18/q3-estimation-complete.png)。统计题浏览器 SSE 记录为 0，是复用夹具在关闭窗口前异步 response.text 未完成的采集缺口；不伪补浏览器轨迹、不付费重试。SQL 事件、最终 DOM、原生三回执和 Provider 用量均有记录；该题浏览器逐事件传输单独记 NOT VERIFIED。

最后的旧合同启动拒绝与“nonzero 意味实数”schema 文案在真实运行后补充；由本地回归验证，未为这两个不影响该次有效输入路径的改动追加付费复验。

## 5. 保留边界与 P1

- 不是一般定义域求解器或证明系统。任意参数不等式、多个假设合取、复数非零域、任意方程区间、完整解集与参数/广义积分收敛证明超出本修复；未知宁可保持 unverified。
- derivative / antiderivative 的 scope 是局部表达式恒等检查，不证明全域可导、边界性质或积分收敛。纯数值结果不能验证未输入的球面半径推导；已加“正确积分回执不能认证错误半径文字”的负向回归。
- 原题逐轮保留能防 Runtime 丢失明确要求，不能强制 LLM 满足任意教学要求。CDF 尾部分支遗漏与通用语义 coverage 属于需要单独样本/人工复核的 P1，不为宣布 P0 全过而增加不可靠启发式检查。
- 复杂 required-output 语义判定、跨步骤教学正确性、更丰富条件表达及人工黄金集交给 P1；未开展用户禁止的工具路由/动态 mask、新数学工具、矩阵/统计工具、检索或数据库重构。

## 6. 合入与 Diff

建议将有限修复独立 checkpoint 留在 `Texa_MacOS`，按正常审查进入交付；不表示 P1 或全量数学可靠性已签收，不自动合并 master。

代码/测试 diff：8 文件，438 行新增 / 81 行删除（另有“nonzero”说明文字调整不改变行数）；另含本报告、真实验收证据和本次 patch_notes 条目。`patch_notes.md` 采用独立 index patch，只提交本条记录，其余候选/侧栏记录与相关代码继续留在工作区。历史学习数据、教材索引和旧报告不改写。
