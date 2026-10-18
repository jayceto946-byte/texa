# P1-B：上下文关联数学步骤校验

2026-10-18，有限代数实现与验收。确定性合同验收 PASS；真实模型及 Electron GUI 端到端验收 NOT VERIFIED，不宣称通用题干理解或全部数学推导可靠。

## Git 与 P0 基线

- 主仓库：`/Users/jichengqian/Documents/ChatGPT/texa`；主目录保持 `Texa_MacOS`。开始时已有大量习题候选与前端未提交改动，未 stash、reset、切换分支或提交这些内容。
- 本任务 Worktree：`/Users/jichengqian/Documents/ChatGPT/texa-p1-b-math`。
- 本任务 Branch：`feature/p1-math-verification`，按用户指定名称创建。
- 实际 Base SHA：`ac071baca0382bdfefece0c1a2b693105dced8a7`。它就是已提交在稳定分支的 P0：`fix(runtime): preserve math conditions and teaching delivery contracts`；不假设 master 包含 P0。
- P0 原报告：`docs/qa/P0-MATH-RUNTIME-REPAIR-2026-10-18.md`。报告记录 214 个不同回归、两道真实模型/Electron 样本及其保留限制；开始时又复跑四组核心回归，112 passed。
- 本实现直接继承 P0 的受限变量/假设解析、未约分 AST、隔离 worker、预算/取消、完整原生回执及最终答案保守门槛。未重复实施 P0，也未修改 symbolic_math v2 合同。
- 最终提交 SHA 见交付消息及本分支 `git log -1`，本报告保存在该独立提交内。没有 merge、push 或操作其他 Worktree。

## 实际代码审查结论

P0 已阻止无条件 `x/x=1` 及候选 `x=0` 被旧核验误接受；也区分 verified/failed/unverified，保留 scope/limitations。P1-B 没有重新修这些路径。剩余缺口是：旧 assumptions 来自工具调用方、候选代入不证明完整解集、原先没有可信原题到前序步骤的绑定，也没有表达单向蕴含的合同。

追踪了 math_tools/math_worker/registry、原生 native_loop、FixedRunner 的输入/输出校验、SQL 回执及恢复、tool_orchestration 的上下文压缩、answer_verification 的计算/答案绑定。新模式沿用同一工具与 Runtime，不新增编排器、工具名或模型评委。

## 输入与可信来源合同

扩展 `verify_math_result` 到 v3，新增 `kind="steps"`，其余 P0 kinds 保留。当前 v2 暂停 checkpoint 因既有版本/schema 栅栏而拒绝直接续用；历史记录不迁移、不改写。

模型输入 `context` 包含：

- `source_ref`：Runtime 根据持久化 `artifacts.request_question` 的完整 SHA-256 生成的 `request:<sha>`。模型不能提供原题正文或 authority 替代它。
- `steps`：1–4 个严格 schema 步骤，各有唯一 id、depends_on、before、after、relation，以及求解类的 candidates（最多 12 个）。
- `relation`：identity / implication / equation_equivalence / candidate_solution / solution_set。

有效数学上下文还包含由 host 单独注入 worker 的 `ToolContext.math_authority`：原始请求来源、一个实变量及其域、至多 8 个有来源的参数 predicates、至多 8 个条件和原始 expression/equation。它不出现在模型输入 schema，不能由额外参数、Resolver state、历史 assistant、模型自行声明“已验证”或跨调用的伪造 id 覆盖。

**来源支持有明确限制**：现有产品没有可复用的“用户确认数学条件”资产，本次不新增 UI/数据库。第一阶段只解释用户原始请求开头的 `<math-context>` 严格 JSON 块；尾部只允许空白或代码中列明的简单核验请求。任意自然语言条件、OCR、图片、引文、混合/冲突题干、缺少冻结原始请求或格式错误，都返回 unknown。不会把原题中的一个便利子串当可信条件，也不回退到可能已被改写的 task.goal。

可直接作为原始请求的例子（尾部“验算。”匹配既有数学路由，不修改工具裁剪）：

```text
<math-context>
{"variable":"x","domain":"real","parameters":{},"conditions":["x!=0"],"premise":{"left":"x/x"}}
</math-context>
验算。
```

条件语法仅支持该变量与有理常数的 `!=, >=, <=, >, <, =`；参数通过 P0 已有 real/positive/nonnegative/negative/nonpositive/nonzero/integer predicates 声明。实变量 integer 域求解仍 unknown。非零 predicate 沿用 P0 的实数且非零语义。相互冲突的变量条件 unknown，不用空条件域制造真命题。

原题条件属于上述唯一正式来源；更正后的原始请求具有不同 source_ref，旧 ref 不得复用。模型传入额外 assumptions 时，本模式返回 unknown，不能加强或覆盖用户来源。

## 步骤、域与证明范围

- 无依赖步骤的 before 必须与冻结原式语法一致；有依赖步骤只能引用本批次之前工具实际验证为 valid 的 identity / equation_equivalence 的 after，且 before 必须与其中一个 after 一致。所有依赖都必须有效；前向/缺失/失败/unknown 依赖均 unknown。单向蕴含和候选检查不升级为等价前提。当前不提供跨工具调用的已验证步骤引用。
- 使用 P0 `evaluate=False` 的 AST，在任何 simplify、cancel、subs、solveset 之前分别收集每个原始表达式的分母非零和平方根定义域，并在源条件域内比较。不能从约分后结果恢复域。
- 恒等检查要求两式在源条件下的域一致；以精确符号残差为零或完整零点集覆盖证明成立。精确采样点可用于给出反例；样本相等永远不能给出 valid。
- 方程等价使用保留域后的精确解集相等；单向蕴含只检查前式解集包含于后式，显式记录反向未检查。有限求解主要为一元有理/多项式（次数最多 4）及可确定解集的有限根式。
- 候选有效性只证明所列候选属于原方程解集，并记录完整性未检查；solution_set 才检查整个候选集和原方程解集相等，包括可证明无解的空集。
- 展开、因式分解、配方、约分、除法、平方/开方和根式化简使用上述合同，不用数学操作名称暗示证明成功。
- 参数可参与有确定条件的恒等式，如 `(x+a)^2` 展开、正参数根式和非零参数约分。无法排除参数为零的分母、含参数求解分支、参数不等式不使用 SymPy 的一般参数解冒充全部情况，保持 unknown。

## 输出与执行异常

数学输出为 `verdict=valid|invalid|unknown`；每步有 typed StepReceipt：实际 before/after/candidates、relation、depends_on、适用条件、checked、not_checked、counterexample 和 scope。全批次保留 source_ref/source_kind，scope 固定 `listed_steps_only_not_whole_answer`。

保留兼容字段 status=verified/failed/unverified 和 passed；**steps 的 ToolResult.success 表示执行完成，invalid/unknown 也可为 true**，execution_status=completed，passed 仅在所有列出步骤均 valid 时为 true。超时、取消、容量、非法输入、worker 异常为执行错误，没有数学 invalid 结论。

原生 ToolMessage 与 SQL 回执原样返回这些字段，源数据通过单独 host 参数传入子进程。math output schema v3 有强类型步骤回执。最终答案计算绑定显式排除 kind=steps；局部 valid 不自动满足 math_support，不证明建模、遗漏步骤或整题交付。

## 关键反例

| 场景 | 结果 |
|---|---|
| 实数域 x/x → 1，无非零条件 | invalid：定义域不同 |
| 同式，原题明确 x!=0 | valid |
| 0/x → 0，无非零条件 | invalid：原分母约束保留 |
| x²=1，只列候选 1 | candidate_solution valid；完整性明确未检查 |
| x²=1，声称完整解集 {1} | invalid，缺失 -1 |
| x²=1，完整解集 {-1,1} | valid |
| sqrt(x)=-1 → x=1，声称等价 | invalid，增根 |
| x=-1 → x²=1，只声称单向蕴含 | valid，反向未检查 |
| x²=x → x=1，两边除以可能为零的 x | invalid，丢失 0 分支；原题 x!=0 时 valid |
| sqrt(x²) → x，实数域 | invalid，有精确负数反例 |
| 同式，原题 nonnegative | valid；sqrt(x²)→abs(x) 在实数域 valid |
| (x+1)² 展开后再配方，同批依赖 | 两步 valid |
| 未验证、未来/伪造前序，或把 implication 当等价依赖 | unknown |
| 模型补充 x>0、Resolver 注入正数题干、原题版本不符 | unknown |
| 结构化正数条件与后续文字负数条件混合 | unknown |
| a/a，a 仅 real | unknown；可信 a nonzero 时 valid |
| a*x=0，a 仅 real，候选完整集 {0} | unknown，不漏掉 a=0 分支后误报成功 |
| 正确局部步骤后错误/未完成整题 | Runtime 仍不会因此升级 passed |

扩展参数测试曾捕获 `a/a` 的关键 false-valid：SymPy 对与 x 无关的参数表达式求零点时可能忽略 a=0。已在调用前阻断未证明的参数分母与求解分支；最终测试覆盖该失败。初次测试收集还暴露过导入位置错误，已修正，没有放宽数学断言。

## 验证与额外开销

最终回归：Python 3.10.21 / 原有 venv310；14 个文件 **257 passed**，其中新增 40 个数学合同/反例与 3 个原生 Loop 用例。P0 同范围 214 个用例一并复验。保留一个既有 Starlette/AnyIO 弃用警告。最终输出见 `evidence/p1-b-math-2026-10-18/regression.txt`。

新原生 Loop 用例使用真实 SQL Runtime、真实受限 SymPy 子进程和标准 AIMessage/ToolMessage，模型为确定性 ScriptedMathModel；覆盖 valid/invalid 回执完整性、原题优先级、Resolver 防伪和最终状态不升级。每个样本 2 次脚本模型步骤、1 次工具，无附加评委/生成链。

桌面：独立 Worktree `desktop/npm test`，**24 passed**。本次未更改 renderer、Electron API、路径、数据目录或构建启动方式。未安装依赖、未启动生产后端、未使用教材/学习数据库。现有 venv 仅作为解释器读取，所有实现与测试产物在指定独立 Worktree。

真实远程模型 Agent Loop、Electron GUI 点击/SSE 全链路、Windows/正式安装包：**NOT VERIFIED**。没有加载主桌面凭据、付费调用或将学习内容发送到远程服务；不把 P0 的真实模型样本当本功能的验收。无需为了本次确定性合同引入模型评委。

本地 3 次短测（含 spawn）：旧单个恒等核验中位 **321.23 ms**；一次四步批次 **332.62 ms**，均受原有 5 秒和进程/字节预算限制。样本少，不能推断一般延迟。输入 schema JSON 从重建 P0 的 1817 字符增加至 3295 字符；原生增加一个有界来源引用提示。这不是实际远程 token 计费测量。Runtime 不增加强制模型调用或工具调用，是否调用仍由模型决定，一次批次共用一个预算工具槽。数据见 `evidence/p1-b-math-2026-10-18/local-overhead.json`。

## 验收结论与保留范围

第一阶段有限、明确来源的确定性 P1-B 合同及反例验收 PASS；未发现最终版本的已知 false-valid 阻断项。该结论只适用于所列算法和测试。

尚不支持自动可信化任意自然语言/OCR/图片题干、通用多变量系统、参数方程分支完备性、复杂不等式/整数域、一般复数域、任意根式/超越方程、跨调用前序证明、几何建模、斯托克斯适用条件或自然语言证明；它们必须 unknown 或不在本合同范围内。暂未新增条件确认 UI/学习资产存储，因此不能把本实现称为普通聊天题干的全面上下文校验已上线。

整体真实 Agent 教学自主行为和 Electron 端到端仍 NOT VERIFIED；这部分不能宣布完整生产验收通过。提交供后续审查与集成，不自动合入 master 或 Texa_MacOS。
