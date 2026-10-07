# Runtime Benchmark Spec V0.1

2026-10-06。状态：scope reduction + measurement correction；本次交付规范与计划，不运行 Qwen，不实现或接入生产 Harness。

唯一决策问题：**未经 Texa 专项训练的 Qwen3.5-0.8B，是否已有值得继续 LoRA/SFT 的 Runtime semantic prior？** 约 80% 且错误集中在可训练边界，可以成为继续训练的依据；不预设 95% 门槛，也不把任何分数当生产接管许可。

## 1. 继承关系与事实依据

本文件取代 V0 的评价目的、主次分组、split 使用和人工审核要求；其余真实 input/output contract、冻结 gold、strict scorer 与 severity 继续沿用。V0.1 是**测量政策版本**，底层数据仍是 Runtime Benchmark V0，没有把改过的数据冒称原冻结包。

- [原 Runtime Benchmark Spec V0](/Users/jichengqian/Documents/Codex/2026-10-06/texa-runtime-benchmark-v0-0-8b/outputs/runtime-benchmark-v0/Runtime-Benchmark-Spec-V0.md)
- [原冻结 scorer](/Users/jichengqian/Documents/Codex/2026-10-06/texa-runtime-benchmark-v0-0-8b/outputs/runtime-benchmark-v0/tools/score.py)，版本 `runtime-benchmark-v0/1`。
- FREEZE.json SHA256：`30a2730fa3def4c6d2b05de21b5733b78cd90ebab53a1ebd0ecf70d10342f7b4`。
- [逐 case 分类清单](case-scope-manifest.json)、[本次来源与 gate 核验](scope-audit.json)、[冻结包 sanity 检查](frozen-sanity.json)。分类清单位于原包之外，不改变 case/gold/hash/split。

仍遵循 `Actual Runtime code/schema → model-responsible semantic surface → benchmark`。不创造 KEEP/SWITCH/COMPLETE，不评知识问答、最终答案、长程 Planner 或确定性状态机智能。候选生成、权限、参数绑定、确认、提交、预算、恢复及 verified 均由 Runtime 负责。

本次核验原 FREEZE 的 271 个文件、300 条 input/gold schema 与 gold round-trip，重跑原有 10 项 scorer mutation 检查；216 个冻结来源文件与工作树内容一致（本次文档修改前快照）。重新运行当前规则得到的 60 条 understanding 请求和 gate 与冻结 metadata 一致。**这些是结构/代码一致性验证，不是独立语义 gold 审核，也不是模型成绩。**

## 2. Primary / secondary / control

| task / 子集 | Primary | Secondary | Control | 依据与意义 |
|---|---:|---:|---:|---|
| policy_select | 80 | 0 | 0 | 真实多候选 PolicyObservation → `{action_id}`；下一步选择 |
| goal_summary | 40 | 0 | 0 | GoalSummary 真实接口，闭集抽取 profile；整理目标与限制 |
| question_understanding，gate eligible | 41 | 0 | 0 | 五字段语义解释；本子集 intent 均未锁定 |
| question_understanding，gate 不调用 | 0 | 19 | 0 | 接口诊断；其中 2 条上游 locked intent 冲突 |
| reference_resolve | 0 | 20 | 0 | 旧 adapter 单测，没有完整 gate 调用依据 |
| route_contract | 0 | 0 | 30 | 代码路由兼容性 |
| retrieval_contract | 0 | 0 | 30 | 已解码状态的 retrieval proposal |
| context_contract | 0 | 0 | 20 | 确定性上下文 seed |
| goal_lifecycle_control | 0 | 0 | 10 | 已授权命令的后置状态 |
| decision_guard_control | 0 | 0 | 10 | 校验/fallback 保护行为 |
| 总数 | **161** | **39** | **100** | 200 semantic = 161 + 39 |

Primary 的 gate eligible 指给定输入满足代码调用条件，并不意味着当前 off 配置会调用模型、主聊天已交由 PolicyLM 或已获生产启用批准。Policy 多候选是已有可替换 selector 接口；Goal 仍只整理，不能创建/激活/完成目标。单候选和零候选不计语义能力。

19 条 non-gated understanding：TRB0-0123、0124、0132、0145、0146、0151、0152、0158、0168、0169、0170、0171、0172、0173、0174、0177、0178、0179、0180（均带 TRB0 前缀）。其中 0145、0169 是 locked intent 冲突，单列 reason，不能算小模型语义短板。旧 resolver 为 TRB0-0181–0200。

V0 scorer 原字段 `primary_semantic_without_upstream_conflicts` 实际仍混合旧 resolver 和 non-gated 接口，全集分母为 198，**不能作为 V0.1 primary**。保持原 report 原样，将逐条 frozen results 按分类清单聚合为单独 `screening.primary_semantic`，分母 161。不得改名覆盖原字段。

## 3. 真实覆盖与缺口

| Texa 场景 | 真实 contract / 来源 | 现有覆盖 | V0.1 判断 |
|---|---|---|---|
| 下一步动作、否定、引用、自纠正、先后顺序 | `decision/policy_projection.py::project_observation`；`policy.py::select_decision` | Policy 80，多候选；gold 为 answer 30、progress 25、exercise 25 | primary；只测下一步，不测完整轨迹 |
| direct answer | 同上，真实 `generate_answer` | 30 个正向 gold，以及工具正例的反向候选 | primary；主要为“不需要工具”，不测答案内容或所有直接问答类型 |
| 教材检索 | 同上已有 scoped `search_textbook` 绑定；`agent_runtime/textbook_tool.py` | 80 条 Policy 中没有该候选；retrieval_contract 30 只测布尔状态 | **已有接口但数据缺口**。未来在同一 action_id contract 补候选选择；本版不拿 control 顶替语义检索分 |
| 工具语义选择 | Policy read 候选；`tool_orchestration.py` / canonical registry | 只有 progress、exercise 与 answer；无 native 参数生成 | 部分 primary；其他工具/参数能力未测，不新增工具 IR |
| exercise / mistake | `search_exercises`、理解维度 exercises；领域写服务与确认 | 查询习题有覆盖；Goal 中提错题只是文本整理 | 不能声称覆盖错题写入路由、作答归因或复习选择；未形成适用小模型的选择 contract 时只登记缺口 |
| 当前问题的 intent/entity/dimension | `question_understanding.py::build_request/should_attempt`；`graph/question_understanding.py::validate_interpretation` | primary 41；同一句实体、意图和维度 | primary；非当前 gate 的 19 条 secondary |
| previous-context/reference | 上述五字段允许 bounded `reference_id` / clarify；`semantic_resolver.py` 旧接口 | primary 41 全是 continue、当前原文 span、空 reference_id；旧 resolver 20 在 secondary | **已有 bounded 接口但没有 primary 历史指代/歧义选择样本**。不能用旧 resolver 成绩弥补；深历史/artifact 消歧也未测 |
| Goal extraction/transformation | `goals/execution.py::GoalSummary/summarize_goal` | 40，目标/否定/范围/时间/产物抽取 | primary；closed extractive profile，不测任意等义摘要、生命周期授权 |
| evidence coverage / context selection / Planner | 当前源码及设计中的未来 PolicyLM 面 | 现有 control 或开放输出，不是统一已冻结小模型闭集 | 不创造新 IR；本版不测，未来先确认 contract 再补数据 |

上述源码均相对于 `backend/services/`，明确标出的 graph 文件除外；权威快照可在原包 `audit/contract-source/` 查阅。V0.1 不新增 case、不补造 gold。现有接口缺题与接口尚未收口分开记录，不把整体分数外推到这些缺口。

## 4. Official strict 与 semantic_recoverability

### 4.1 Official 永远使用首答原文

原 raw output → frozen `score(rows, predictions)`。非 JSON、围栏、think/prose、前后说明、重复 key、NaN/Infinity、schema violation、非法候选均按冻结规则失败。不重试、不 fallback、不改 gold、不用候选模型或 LLM judge 评分。

主表中的 `official_strict_accuracy` = frozen `structured_match` 成功数 / 预定分母 N；同时报告 `official_exact_accuracy`。strict 指严格 wire/contract，structured 仍保留原允许的 dimension 顺序和 Goal atom 顺序等 S1 差异，不擅自改成字节相等。原 `official-report.json` 原样保存。

### 4.2 独立诊断 parser：semantic-recoverability/v0.1

该 parser 仅处理已经保存的同一 raw，绝不再次生成。输入为 raw（不含 gold）；输出 `status, extracted_text, source_range, transform_log`。规则在首次 baseline 前固定：

1. 先严格解析整个 raw；若合法 JSON，保留整体。schema 错误也不进入“找内层正确对象”流程。
2. 整体不是 JSON 时，仅允许识别、排除完整成对的 `<think>...</think>` 区段；未闭合/嵌套不明时记 unresolved。不得把 think 内的备选答案拿来打分。
3. 在剩余文本中用识别字符串/转义的括号扫描查找完整最外层 JSON object/array，不能用简单首尾大括号截取。允许外部 prose 和 Markdown fence；不递归搜嵌套对象。不把 JSON 字符串内部的对象当候选。
4. 必须只有一个完整最外层候选，且外部没有损坏/未闭合的 JSON 容器；多个候选一律 `ambiguous_multiple_payloads`，不按先后、schema 或 gold 选正确的那个。数组仍按数组送 validator，不摘出其中对象。
5. 对唯一候选复用 frozen `json_strict`，仍拒重复 key、非有限值。不修单引号、逗号、截断，不改键名/类型、增删字段、猜 action/span/ref、补 Goal atoms。额外字段仍失败。
6. 对恢复出的完整原文 JSON 子串调用同一 frozen scorer/validator；沿用同一 structured match。记录在 diagnostics，绝不写回 predictions 或替换 official severity。

这是保守的 recoverability 下界，不是开放语义判官。schema 违规但似乎选对 action，可保存字段观察用于 failure analysis，不能以删字段方式获得 recoverable success。

### 4.3 指标与错误归因

每个预先确定的集合、task、split 都显示 count/N 与 rate：

- S：official structured match 成功。
- F：official 失败，但上述唯一恢复 payload 通过 frozen structured match；format-only failure。
- T：存在通过完整 contract 的唯一 payload，structured match 错误且可由闭集判定为决策/字段语义错误；true semantic failure。可同时带 format_error 标签。
- U：其余失败，如无输出、截断、多个 JSON、schema/membership/span 错误、无法恢复，或 Goal profile 无法确认同义改写；语义未判定。

`official_strict_accuracy=S/N`；`recoverable_semantic_accuracy=(S+F)/N`；`format_only_failure_rate=F/N`；`true_semantic_failure_rate=T/N`；另强制报告 `unresolved_failure_rate=U/N`。四类 S/F/T/U 互斥完备；**1−recoverable 不等于 true semantic failure**。T 可除以可判定数作为辅助条件率，但不得替换以 N 为分母的主率。

Goal 闭集 profile 对同义改写不充分：`goal_unverified_new_atom_in_closed_profile` 进入 U 的 `profile_limited`；`goal_constraint_loss` 若同时出现 out-of-profile atoms，也保守列 U，不能声称已证明遗漏。完全在已知 atoms 中漏掉目标/约束/产物时可记 T。这些诊断不降低 frozen S3/critical 记录。输出中的明确错误、格式和 operational 状态可有多个标签。

示意而非实测：strict 78%、recoverable 90% 表示至少 12 个百分点是可恢复格式损失；strict 78%、recoverable 79% 仍需看 T 与 U，不能直接宣称理解能力只有 79%。

## 5. Foundation screening policy / split

| 原 split | Primary | Secondary | semantic 合计 | Control（不纳入） |
|---|---:|---:|---:|---:|
| train | 77 | 21 | 98 | 52 |
| dev | 32 | 8 | 40 | 20 |
| test | 36 | 6 | 42 | 18 |
| hidden_test | 16 | 4 | 20 | 10 |
| all | 161 | 39 | 200 | 100 |

首次未经 Texa 专项训练、也未根据这些 failure 调 prompt/config 的 baseline，可报告 `semantic_all`（200 条）总体诊断；必须同时显示 primary 161、secondary 39、全部 split 与每 task 的分数。不合入 control，不称 held-out、盲测或 unbiased final evaluation。hidden_test 是原 provenance 标签，完整交付方已可见，不建立保密基础设施。

P1 使用独立合成 smoke；P2 先固定配置运行 primary，P3 同配置只补 secondary，与 P2 原始首答合并，200 条各生成一次。P2 后不能按失败改 prompt 再把 P3 拼成 untouched run。若改过模板、预算、参数或模型，则新 run 明确 `tuned_on_v0=true`，保留第一次结果，不沿用 untouched 标签。所有 split 保留 family/pair/group 来源；分类把 pair 拆至不同 tier 时，仅完整 pair 计算 both-correct，并报告完整 pair 数。

后续 4bit/8bit/BF16 使用同一病例、分类版本、prompt、scorer、recoverability、case 顺序与 generation 配置横比；量化/实现导致必需模板差异要注明可比性限制。greedy/固定 seed 不保证跨后端逐 bit 一致。开始利用 V0 failure 调 prompt 或 LoRA 后，V0 只能作开发/回归集，LoRA 效果需另建未参与调优、family/group 隔离的 V1/V1.1 held-out；不在本轮实施训练。

判断是否值得训练以 primary 为主，配合三类 task 的 macro 平均、每 family 的错例与 S3，不让 80 条 Policy 掩盖理解或 Goal 短板；secondary 仅解释接口能力，control 不投票。约 80% 是探索性参考：格式差距大可优先训练输出纪律；有效 JSON 下的否定/顺序/对象/限制错误是语义训练候选；U 很高先修测量/输出预算并承认新 run 已非 untouched。覆盖缺口和合成模板相似性使总体分数无法代表“掌握大部分真实 Texa 场景”。

报告给出 `promising_for_task_specific_training / insufficient_evidence / weak_on_measured_boundaries` 及具体证据；不自动启动 LoRA、不授予上线许可。当前尚无 Qwen 实测，结论是未测。

## 6. Gold 资格与本轮边界

不要求人工逐条 adjudication，始终保留 `human_adjudicated=false`、`semantic_test_locked=false`。可用独立非 candidate 模型基于真实 source contract 交叉检查 author gold，Qwen 不参与构造或评分。检查者须看输入/候选/源码，记录语义依据；多数票和 gold round-trip 都不证明语义正确。

本次独立模型 gold review **未执行**；sanity 通过可先开展明确标为 author-frozen 的 internal screening，不冒称独立裁决完成。若后续交叉检查产生分歧，先隔离 case，保留原 official 全分母分数和隔离清单，再单列 reviewed subset；要改 gold/允许答案集须发布新数据版本并重新 freeze，不能在看到 candidate failure 后热修原分数。无需建立人工 review UI 或平台。

本轮只交付规范、最小计划、分类与 sanity 记录。Harness 后续到 P3 report + failure corpus 即停止；不做 LoRA、shadow、production integration、dashboard、公开 Benchmark 或 control-suite 扩张。Electron 与生产业务代码/数据路径不受本次文档修订影响，未进行桌面或模型性能验收。
