# Texa Runtime Benchmark V0

版本：2026-10-06 / V0 author freeze。目标：评估本地 0.8B 模型在**现有可执行接口内**把中文请求变成 Runtime decision / 有限结构化解释的能力，不评价知识、计算、教材答案或最终回复质量。

依据为 Texa 当前工作树，而非仅 Git HEAD。HEAD 为 `d36767f32690506b3697340bb6eaa948395dbcf0`；仓库已有大量未提交改动。216 个相关源码、规范、测试文件的内容指纹见 [source-manifest](audit/source-manifest.json)，审计与冲突见 [Runtime audit](audit/Runtime-Audit.md)。未修改生产代码、现有数据集审批或用户学习数据。

**当前可交付的冻结版有 300 cases；其中 200 个是作者标注的语义接口任务，100 个是代码行为对照。语义 gold 已冻结字节，但尚无独立人工裁决，不能冒称仓库规范意义的 locked semantic test。** `human_adjudicated=false`、`semantic_test_locked=false` 是有意保留的真实性标识。也没有运行任何 0.8B 权重，不据此宣称模型已达标。

## A. Current Runtime Decision Surface

先区分真实接口，再确定测量范围。具体 input/output JSON Schema 见 [schemas](schemas/task-index.json)，机器可读 ontology 见 [decision-ontology](decision-ontology.json)。表中的“模型适合”是待验证的工程判断，不是已经测得的能力。

| 当前 decision | 输入 → 真实候选 / 输出 | invariant / fallback / critical failure | 0.8B 与确定性边界 |
|---|---|---|---|
| Policy V0 下一步选择 | `PolicyObservationV0` → 仅 `{action_id}`；候选 kind 只有 `generate_answer / call_tool / request_input` | 只能选本次冻结候选，不能改参数；stale 禁执行；invalid_format/unknown_action_id 最多一次规则 fallback。错误引用候选以外的写操作必须被拒绝 | 多候选适合试验；0 候选交 Runtime、1 候选直接选择，不能计模型智能 |
| 当前问题理解 | question、rule、有限 reference IDs → `action,intent,dimensions,entity_spans,reference_id` | 实体只能当前原文；指代只能已有 ID；锁定 intent 由规则覆盖；失败/超时保持规则轨道。错误对象会污染后续 topic/retrieval | 最适合小模型的受限语义任务；仅 gate 允许时有实际调用机会 |
| 旧 semantic resolver | question + 最多24个候选值 → 一个 `resolve_reference` 或 `clarify` | 不生成新对象；歧义不得假确定；默认关闭，只有 unresolved/低置信触发；失败保留既有澄清 | 可单测；不能把接口单测误报为当前主链覆盖率 |
| Goal 摘要 | 明确提交的 text → `title,objective,success_criteria[].description` | 不含 status、scope、criterion ID；Runtime 另补 ID；失败不上写。增加范围、删掉否定、伪造完成是语义破坏 | 可评估受限结构化变换；V0 用抽取 profile 避免 LLM judge |
| DecisionRouter route/capability | `DecisionContext` → `direct_answer / capability / clarify / unsupported` 与 capability | scope、缺输入、附件、显式 action 等先判；regex 或 optional calibrated semantic prototype；catalog 并不都能 resolve 到工具 | 当前确定性对照。不能新建一个模型 route 字段塞进 PolicyDecision |
| Canonical tool/native adapter | provider native tool call 或 finish + registry → 校验后的工具名/参数 | 只允许 registry 冻结 schema、scope、预算；副作用需确认和 receipt；不支持的 provider 不可假装 native 工具 | 现存模型面，但 V0 不测自由参数生成；只覆盖受限 read action ranking |
| 检索连续性提案 | use_textbook_context、scope、active evidence、same_topic、facet/support → `none / reuse / delta / full` | scope/corpus/topic 失效禁止沿用；reuse 后还要按 chunk hydration/fingerprint；hydrate 失败 full。旧回答不是证据 | 提案目前确定性；100 对照集里有30例。不得用30例状态分类宣称理解了用户是否要查书 |
| 会话上下文选择 | 当前 resolution trace + history → bounded ConversationContextPack/seed | 最多2轮生成原文；引用/纠正优先；新主题不机械保留旧轮；当前证据优先于历史；失败不授予历史证据身份 | 当前选择规则保持 deterministic；20例只测实际 seed，不发明 retain/drop action |
| Planner | 当前 query、scope、intent、章节候选 → intent/target_chapters/confidence/sub_tasks | 强规则锁定、fast path；章节范围受约束；当前 subtask action 未形成强闭集校验，不能当新 Runtime IR | 现存模型面，V0 不纳入核心分数；任务规划开放输出需另做接口收口 |
| Goal 生命周期 | 显式 service command + revision + Goal → 持久状态 | `draft/active/paused/completed/cancelled` 是状态；不是模型 action。activate 仅 draft/paused；pause 仅 active；measure 的 evidence 不能自行判完成，只有用户确认 | 必须 deterministic；10例为既定命令的后置状态对照，不测 NL→授权 |
| 学习状态桥接 | 明确学习 speech act + 已知书/章/已有 Goal → preview operations 或 clarify | `create_goal/start_learning/resume_learning/pause_learning/record_weakness` 是兼容层提案，歧义需澄清；不等同 GoalService 枚举 | 默认确定性；不把 preview 当提交，也不虚构 KEEP/SWITCH/COMPLETE |
| 错题/练习/复习/会话/笔记 | 有限工具提案、显式 UI/API 命令、receipt/事实 → 各领域状态 | pending action 需确认；错题掌握由用户/确定性证据；会话管理 CAS；笔记生成后显式保存 | 工具选择可研究；确认、幂等、掌握状态、保存、删除必须确定性；不测正文质量 |
| provider / execution / validation | registry/provider 能力、snapshot/revision、预算、tool receipt、verification → 接受/拒绝/终态/outcome | 一次执行权、未知写不重试、stale 不执行；completed/degraded 不等于用户目标完成或答案正确 | 全部保持 deterministic；10例故障注入仅检查校验/fallback |

### 当前 Policy 的真实窄口

候选由 `policy_projection.project_observation` 生成。V0 read 候选允许 builtin、非副作用/derived_cache 的 frozen refs。具体绑定包括 `get_recent_progress`（默认7天、12条）、`search_exercises`（query 限300字符、limit8）与有有效 frozen scope 的 `search_textbook`。模型不能自行改这些值。本版80条 Policy 语义 case 覆盖前两种与 `generate_answer` 的取舍/先后顺序；**没有声称覆盖教材工具所有路径**。

`request_input` 是真实 action，但 blocking gate 通常直接产生单候选；缺输入的 SQL 路径可能无候选。它不应被包装成“模型成功选择澄清”。现有 pre-SQL gate、0/1候选、scope、重复调用、预算的检验由现有 contract tests 辅助覆盖，本版不把这些白送题混入80条主分母。

80条全部使用真实 projection/harness 的多候选 Observation；fixture scope 为隔离的 `fixture/数学`，不会检索用户数据。候选存在不是执行授权：例如否定/引用触发规则候选时，semantic gold 仍可选 answer。`RulePolicyV0` 是对照预测，绝不是 semantic gold 的生成来源。

## B. Task 与 schemas

| task | 数量 | gold 与 scoring 单位 | 与实际执行的关系 |
|---|---:|---|---|
| policy_select | 80 | 单个本地 action_id exact match | 真实 admissible projection；read/answer；多意图只判**下一步** |
| goal_summary | 40 | GoalSummary + objective/criteria/constraint atoms | 现有输入输出接口，额外声明受限抽取评测 profile |
| question_understanding | 60 | 五字段结构化 match；维度顺序忽略 | 接口单测；其中41条通过当前调用 gate；两条存在上游规则意图冲突 |
| reference_resolve | 20 | 单操作/精确候选值 | 旧 adapter 单测；不声称20条会触发生产 gate |
| route_contract | 30 | mode/capability/rule_match/reason_codes exact | 规则兼容性诊断；坏 regex 行为不当语义正确 |
| retrieval_contract | 30 | retrieval_action exact | 给定状态下的 proposal；不是自然语言理解分 |
| context_contract | 20 | seed 选轮/topic/constraints + trace exact | off 模式现有行为对照；不是新 context IR |
| goal_lifecycle_control | 10 | accepted/status/revision/plan/criterion statuses | 已解码命令的服务后置条件；无真实用户写入 |
| decision_guard_control | 10 | validation code/attempts/执行 kind | 注入 invalid/duplicate/fenced/unknown/stale；测试保护而非语义 |

每条 curator record 含 ID、task、family/pair、split_group、question、实际 input、gold、basis、track、tags、metadata 与 input/gold/case hash。模型只能看到 `datasets/*.inputs.jsonl` 的 `id/task/input` 加固定 task prompt/schema，不得看到 metadata、basis、gold、作者 question caption 或规则预测。retrieval 的中文 question 是作者场景注释；模型输入就是实际状态，不偷渡它做语义题。

question-understanding 的合法 intents、dimensions 逐字取自 `graph/question_understanding.py`，见 `schemas/enums.json`。span 为 Python Unicode code point，非 UTF-16 code unit；左右闭开，2–80字符，排序不重叠，不能含标点/换行。候选 ID 只能在 unresolved/reference_fallback 时用。锁定 intent 在 Runtime 会覆盖模型输出，评分同时保留 wire exact 与 effective structured match，不奖励覆盖已有确定性权力。

本版 Goal transformation 的 profile 不改变生产 schema：把文本中的有效目标与限制抽成 objective 原文 atoms，以分号连接；criteria 为用户提出的产物/检查项；title 取核心目标短语。这样可逐字段验证，而不是拿一篇摘要作答案。**它不测任意同义改写质量**；未列入 frozen atoms 的自由改写会被标记 `unverified_new_atom_in_closed_profile`，不能把这个标记解释为“语言学上已证明 hallucination”。不让 scorer 通过 substring 吞掉否定：`别扩到导数` 与 `扩到导数` 不等价。

## C. Case 设计与覆盖边界

全部为人工构思方式生成的合成中文，由本任务作者编写，并非真实用户日志。包含口语、病句、打断、省略、指代、否定、引用、自我纠正、噪声、多意图排序、当前对象替换旧上下文、话题切换、工具不必要、歧义保持及协议攻击。

150组两例配对；143组 gold 有改变，7组是 invariant/规则缺陷见证，不假称全部是 action-changing minimal pairs。既包含小词变化的 contrast，也包含 state/protocol contrast；长句改写对不冒称严格 minimal edit。`pair_kind` 区分 language/state/protocol。当前 Topic 切换不等同持久 Goal SWITCH。

实例（全部完整输入和 gold 以 JSONL 为准）：

- “先查习题库，再看最近学习进度。” ↔ “先看最近学习进度，再查习题库。”：从两个真实工具候选中改变第一步。
- “不是让你讲学习方法，是让你查最近学习活动。” ↔ 相反纠正：read tool ↔ answer。
- “我说的那个是压阻效应，接着说它。” ↔ “我说的那个，接着说它。”：精确候选 ↔ clarify。
- Goal 原文“到周五前完成”换成另一明确时间限制：仅变更相应 objective atom，不补绝对日期。
- 相同 active evidence，`requires_new_facet=false→true`：reuse→delta；scope 改变应 full。
- 相同模型 JSON，observation 新鲜→过期：accept→stale，不执行也不规则重试。

V0 覆盖不足明确保留：没有真实教材索引/模型/GUI集成；只有短历史 seed；没有长达2k字符截断专项；缺完整 native write 参数生成、Planner子任务、所有 note/mistake API动作、实际 provider 超时与模型 latency；Policy textbook call 与多步全轨迹未进入80条主分母。这些放在扩展计划，不补造 gold。

## D. 冻结 gold 与评分

正常评分完全离线，无 LLM judge、无网络、无数据库。运行 `tools/score.py` 前验证 `FREEZE.json` 的内容 SHA-256 与每条 case hash；失败直接退出，不自动重建、重签或修 gold。SHA-256 证明包内一致性，不证明外部身份签名；可由保管人将 release digest 另存。

输入预测格式每行 `{"id":"TRB0-0001","raw_output":"{\"action_id\":\"a0\"}"}`。所有 raw output 都保留原文；不剥思考、Markdown、JSON前后说明。严格 JSON 解析拒绝重复key与非有限值；额外字段由 schema 拒绝。重复case ID、未知ID、错误split拒绝整次评分；缺预测计失败，分母不缩水。详见 [运行说明](README.md)。

分别报告：

1. **200条语义接口集**：task-wise exact/structured match、schema validity、executability、critical failure rate、两例同时正确。它含接口单测与非 gate 调用，不等价生产端到端准确率。两条上游 intent 冲突单列；自由 intent 子集另报。
2. **100条 deterministic control**：代码兼容率、保护机制失败；不得和模型主分数加权合成一个“300题准确率”。
3. **Goal fields**：objective 与 criteria atoms 的平均保留率作为受限 semantic fidelity / required field retention；constraints 单独 recall；unsupported atom 与 out-of-profile atom 分开；schema和可执行性；`compression_ratio=(title+objective+criteria文本字符数)/source字符数`。压缩不是越小越好，只有保真和约束保留合格时才解释。
4. **Fallback**：主决策错即错，fallback 成功不能改写 primary score。协议错误被 Runtime 拒绝通常 S2；stale 不执行才是正确。trace 中执行 succeeded/completed 不能代替语义 gold。

schema validity 是静态 JSON shape；executability 再加候选 membership、span/ref 条件。Goal 可执行只代表能进入 GoalSummary 接口，不代表授权创建/激活 Goal。control 的可执行指标仅表示预测 envelope 合法。

Goal atoms 可完整保留、仅顺序/标题周围空白变化时 structured match，S1；dimensions 仅顺序变化也是 S1。除此之外不做随意模糊匹配。runtime parser 容忍与 benchmark strict-wire 指标分开：Policy 原本严格；旧 semantic/understanding helper 会剥围栏/提取对象，V0 输出格式更严格，仅作为共同 wire profile，不能宣称生产会拒绝它本来接受的格式。

## E. Severity 与实际后果

| 级别 | 可检验定义 | 当前 Runtime 后果示例 |
|---|---|---|
| S0 correct | frozen exact 正确 | 正确本地 action_id、正确对象、正确状态对照 |
| S1 harmless deviation | schema/跨字段均合法，语义字段全保留，仅允许规范化差异 | dimensions顺序；Goal atom顺序或标题周围空白变化；不改变范围/状态 |
| S2 degraded behavior | 错误但守卫阻断，或无关键对象/状态破坏的多做/少做 | 无需查进度却选read；该查却answer；不必要clarify；非法JSON/未知action被拒；普通facet错；缺预测 |
| S3 semantic/state corruption | 合法形状仍选错对象/丢关键限制；或对照预测越过不可越过的状态边界 | clarify应保持却替用户指定候选；Goal删否定/时间限制、增加未证实目标；旧scope证据误判reuse；无授权把Goal判complete；过期判可执行 |

S3 的 control 结果是**离线预测的反事实破坏**，没有实际写入发生。被 schema 拒绝的额外 status 字段记录 attempted_authority_escalation，S2；不能声称已腐败数据库。关键 hallucination 指通过 schema 的错误对象/未支持原子/状态事实，记 critical failure。`goal_unverified_new_atom` 是受限 profile 的保守失败，不是开放语义 judge。

S3 不被其他高分抵消。V0 不预设“95% 就可接管”；这是诊断集。200条未独立审阅的数据和30条已向作者公开的 hidden split 不足以证明线上可靠。未来接管需按任务与调用gate另定风险阈值、报告分母/置信区间和延迟，不因参数量小或规则对照得分低直接上线。

## F. Split 与规模扩展

train150 / dev60 / test60 / hidden_test30；150个pair family，124个独立split group。先按共同措辞框架合并，再将规范化问题 SequenceMatcher ≥0.78 的跨family近似项做连通分组，最后整个group切分。10组工具顺序对子共用的框架整体放同split；同pair绝不拆散。检测得到0跨split exact/near duplicate及0pair违例；这是字符规则加作者分组检查，不是语义无泄漏的数学证明。

train可训练，dev只调prompt/阈值，test只一次最终评估；hidden_test 输入可另交执行方、gold仅保管方评分。**当前包是 curator 完整交付，作者和收件人可看到所有 gold，hidden 是角色分区而非已保密的盲测。** 不向模型目录复制 curator/、audit/、validation/。

扩到1k/10k时：先收集经授权去标识的真实请求/失败轨迹，按会话、源文档片段、生成模板、纠错frame、contrast family 建组；去重和拆分发生在任何训练前。每条必须绑定 contract/source digest、候选快照、gate、来源及人工review；新版本只追加新family，已发布test不回流train。实体替换/同模板同义改写不能跨split。按 task/语言机制/长度/历史深度/否定/歧义/工具成本分层采样；补足本版未覆盖分支后再扩大数量。

语义 gold 的 release gate：独立 reviewer 看输入、真实可执行候选与冻结依据，逐条 adjudicate，记录 reviewer/date/reason；不看教师模型答案投票替代裁决。冲突/歧义样本先隔离或定义冻结允许集合，不能打分后改 gold。本版为该流程准备了 [review queue](curator/review-queue.jsonl)，并非已经完成review。

## G. 应继续 deterministic 的决定

必须保留代码权威：action候选生成与参数绑定、scope/book/index identity、schema/enum/ref校验、stale/revision/owner检查、预算、0/1候选选择、工具副作用分级与确认、receipt/幂等/未知写恢复、Goal激活/暂停/完成、调度时间与闹钟触发、task终态、会话CAS/删除、错题掌握判定、source身份/引用映射/检索hydration、证据版本、上下文token预算与截断、RuntimeEvent合法性与decision/outcome关联。

小模型可以提出有限候选选择/解释；不得自证“这次成功”“用户目标已完成”“此证据足够正确”。V0 没有创建 `KEEP/UPDATE/SWITCH` Policy枚举、新的 ContextPack V1 或 Goal 状态机。

## H. 验证与交付状态

300条通过实际生成期的 production validators/隔离服务检查；发布包另做schema、hash、split及评分器mutation验证，结果见 `validation/release-checks.json`。现有仓库选定10个测试文件：249通过、20失败（旧 Policy Dataset source digest 过期），完整日志与环境见 `validation/repo-checks.*`。没有把旧失败修成绿色。RulePolicy 对80条作者semantic gold命中39，仅是当前规则的诊断结果，不是0.8B测量，也不是gold已获人工认可的证据。
