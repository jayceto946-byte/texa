# Current Runtime Audit / Benchmark V0

审计对象是2026-10-06的实际 Texa dirty worktree。此文区分接口冲突、已知限制、未来设计与历史记录；没有借评测任务修改生产实现。相对链接指向本交付冻结的源码；[symbol-index](symbol-index.json)提供函数起止行，[source-manifest](source-manifest.json)提供内容指纹。快照目录中保留了审计相关代码/规范/测试，**文件被纳入hash清单不等于所有旁支都得到同等深度验证**。

## 1. 主链与状态权威

```text
用户/UI → scope + SessionContext/ledger resolution → (可选 question-understanding)
        → DecisionRouter / canonical capability resolver
        → legacy graph 或符合门控的 bounded runtime

legacy graph: direct → generate
              grounded → plan → retrieve → generate 或 chapter agent → feedback

bounded runtime: task/run snapshot → frozen Observation → Policy action_id
                 → freshness/schema/candidate guard → bounded tool/shared generator
                 → validation + fact Outcome → ExecutionEvent/outbox
                 → RuntimeEvent metadata projection（best effort）

Goal: explicit summarize → GoalSummary → explicit create/activate/execute
      GoalService + revision/contract fence 为状态权威
```

`TEXA_AGENT_RUNTIME_READ`、`TEXA_RUNTIME_POLICY_V0`、textbook/write gates 与 provider native support 共同决定实际接线。不能看到工具在 registry 就假设每句 chat 都经过该工具或小模型。实际入口见 [chat_binding.try_chat_response](contract-source/backend/services/agent_runtime/chat_binding.py:111)。general直接问答、vision、teach/summarize章节路径、缺canonical mapping等都有自己的分支。

模型返回 finish 后仍由共享 generator 生成正文；不是把 finish 的自由文本原封不动当最终结果。task 状态由执行及 verification 决定；task completed/degraded、execution succeeded、Policy选择正确、Goal达成是四件事。

## 2. RuntimeEvent / decision / outcome

- [RuntimeEvent V1 spec](contract-source/docs/runtime-event-v1.md) 与 [writer](contract-source/backend/services/runtime_events.py)在隐私和持久性边界上相符：文本仅hash+长度、payload白名单、source refs，不保存prompt/完整回答/用户工具结果。queue4096、batch128、retry3，满队列/失败允许丢事件；10万条按已完成turn轮转。不能从这条日志反推训练gold。
- [ExecutionEvent](contract-source/backend/services/execution_events.py)是UI传输/里程碑协议；progress/output_delta不全部持久化。run/task/owner限制、seq与final/error闭合属于执行确定性。
- [PolicyAttempt / select_decision](contract-source/backend/services/decision/policy.py:54)有observation_id、decision_ref、fallback_of、validation。`decision_ref=digest(observation_id,slot)`；primary和fallback分开。stale在写旧run trace之前拒绝，不能制造“失败一次再fallback成功”记录。
- [PolicyOutcomeV0](contract-source/backend/services/decision/policy_contracts.py)只记录validation/execution/result refs/continuation/task status等事实；默认user_feedback/goal_completion为unknown，没有decision_correct。Policy日志的linkage不能等同RuntimeEvent已完整保存相同字段。
- `RuntimeEvent.replay`重建的是有限metadata，可能缺父事件、截断窗口；绝非可直接还原Observation和semantic label的数据集。

## 3. Goal与学习生命周期

[GoalSummary](contract-source/backend/services/goals/execution.py:28)三个字段；criteria只description，service补ID。summary最多6条；[GoalStore](contract-source/backend/services/goals/store.py)领域存储最多12条且可无criteria。两者有不同用途，不应统一成一个“全Runtime Goal schema”。

[GoalService](contract-source/backend/services/goals/service.py:30)的实际操作是create/update/activate/pause/measure等。状态draft/active/paused/completed/cancelled是存储枚举；没有model output的CREATE/KEEP/UPDATE/PAUSE/COMPLETE/SWITCH六分类接口。`activate`只允许draft/paused，`pause`只active。title-only更新与objective/scope/criteria等关键更新后果不同：后者重置progress/plan/next action并fence已有run。`measure`把证据标为evidence_present_unverified；`user_confirms_completion=true`才标completed。即使本轮任务运行完毕，也不自动达到长期目标。

[Goal execution](contract-source/backend/services/goals/execution.py)启动前检查native工具能力；paused需先激活；有6tool/8model预算、稳定request key、Goal contract hash、owner fence。schedule只支持一次或24/168小时，运行依赖本地worker；不是云端永不休眠调度能力。

[learning_state_bridge](contract-source/backend/services/learning_state_bridge.py)从speech act产生preview与clarify；原有LearningGoal/Session兼容层与GoalService应分层看待。0个/多个可恢复目标或不确定book/chapter需澄清。不能将preview操作名挪为Policy合法action，不能从“继续那个”自动认定用户授权某个持久目标。

## 4. Context、理解与教材检索

[session_context](contract-source/backend/services/session_context.py)、resolver helpers与[session_ledger](contract-source/backend/services/session_ledger.py)是bounded投影链：当前明确实体/纠正/引用/artifact/ordinal/plural/意图片段等按实现优先级处理，clarify不推进state。ledger是SQLite权威、revision/CAS更新；完整历史只用于受限重建，不是每轮无限prompt。

[question-understanding adapter](contract-source/backend/services/question_understanding.py)默认off，支持shadow/fallback；低置信、未解指代、局部冲突才尝试，强规则已解对象/纠正不会每轮调用。输入question≤2000，prompt≤6500，refs≤12，6秒/无重试/384 token，不用最终答案模型fallback。输出验证器只有五字段；spans必须原文、ref必须候选。它能给检索维度/对象提示，不能改scope或授权写。保留原始rule trace以区分上游故障。

[旧semantic resolver](contract-source/backend/services/semantic_resolver.py)是另一个兼容入口：候选**值**，不是理解接口的reference ID；仅resolve_reference/clarify、最多24候选，默认off。它验证候选membership，不验证“第九个”等表达是否真的能由候选确定；模型解释正确与validator接受不能混淆。

[ConversationContextPack](contract-source/graph/conversation_context.py:81)生成侧最多2轮：显式引用优先，再按correction/return/continue/followup选最新；独立新问题可不带历史。user600/assistant1400，默认总2800、配置范围800–5000；artifact≤2、constraints≤12，可附有限topic摘要。当前EvidencePack引用优先，历史文本被标记引用数据，不授予事实来源地位。预算/引用映射不适合交给小模型猜。

[continuity builder](contract-source/backend/services/evidence_continuity.py)只从最近assistant收集source≤12；有scope/corpus/topic失效检查。但是缺版本值在当前实现被宽容对待；同intent会判requires_new_facet=false。这是当前保守/启发式实现的真实行为，不用未来设计替代。

[retrieval policy](contract-source/graph/retrieval_policy.py:20)只决定none/reuse/delta/full。scope变化或实质invalidations→full；有active IDs、same_topic、supported/partial时reuse或delta；其余full。scope比较只在双方非空时认定变化。`sufficient`不是这里的` supported`枚举，不应跨领域混用。

[retrieval_node](contract-source/graph/retrieval_node.py:336)的reuse还要按chunk回读正文及fingerprint，失败降full。提案不等于最终结果。真实检索另有hybrid/vector/BM25/KG、章节与书范围、邻接/层级/枚举策略、role软prior、support gate。当前支持判断仍可能将候选过滤至supported/partial；未来H1取消错误语义硬阻断的设计不能被写进本版gold。

[EvidencePack](contract-source/graph/evidence_pack.py)固定容量与条目截断，生成可见E-ID/text与verification items现在对齐；book+index+chapter身份隔离是本次工作树已有修复。答案核验并不是一般数学真理证明；引文/数值receipt等均是有限契约，本benchmark不测它的数学能力。

## 5. Tools、学习资产与执行保护

[DecisionRouter](contract-source/backend/services/decision/router.py)支持10个catalog capability；[resolver](contract-source/backend/services/decision/resolver.py)只有其中部分能落到canonical tools。`textbook.read`、`mistake.search_related`、`review.manage`、`math.verify`不能仅凭catalog名称认定已进入Policy V0。legacy registry 的math/verify工具与schema另属旧编排链；同名search_textbook的参数schema也不同。

[tool orchestration](contract-source/backend/services/tool_orchestration.py)是既有有限规则编排，不是任意agent。选择工具/聚合结果、状态包skip retrieval与pending write有独立边界。native adapter只允许verified能力、冻结refs和native工具调用；开放自由工具文本不能靠模型“说调用了”视为执行。

[pending_actions](contract-source/backend/services/pending_actions.py)允许add_mistake、mark_concept_reviewed、create_practice_session、record_practice_result、update_mistake。stable action_id防重、显式confirm/reject、写前查domain receipt，确认失败持久failed；已写成功不能reject成没发生。练习结果还要补投影到LearningEvent。

[mistake_lifecycle](contract-source/backend/services/mistake_lifecycle.py)基于持久redo事实：用户确认/确定性判定、无提示、题目revision一致、跨间隔且到期的独立正确证据等，才可能mastered；另有manual mastery。模型一句“我看你会了”没有该权限。

[conversation_management](contract-source/backend/services/conversation_management.py:174)只接受pin/unpin/archive/restore/trash；expected_revision + operation receipt，busy task阻止archive/trash。不是聊天中出现“删除”就能执行。

[session_notes](contract-source/backend/services/session_notes/generation.py)是article-v5生成与校验/显式保存链；允许有限教材补充，不是所有笔记都严格只抽历史原文。该正文质量不进入Benchmark。学习资产ID、选择范围、source引用、保存/确认仍由代码决定。

[agent runtime store](contract-source/backend/services/agent_runtime/store.py)与runner/lifecycle/write_service收口task/run、唯一运行权、revision/owner/Goal合同、budget、approval、receipt、outbox。写unknown只能对账，不能盲重放；关闭/重启标interrupted而非从头执行；verification不足会degraded。LearningTask与SQL runtime的状态快照转换不应强拼成一个模型可控制的超级状态机。

## 6. Spec / code mismatch 与限制登记

| ID / 类型 | 文档或直觉可能引出的结论 | 当前真实执行语义与证据 | Benchmark处理 |
|---|---|---|---|
| M01 冻结依据失效 | 旧policy dataset manifest仍能验证当前代码 | 20条现有tests报`source_content_digest_mismatch`；见repo-checks.log，当前question-understanding相关链已变化 | 保留旧文件；新包独立source pin，不代签旧approval |
| M02 未来设计非实现 | 2026-10-05设计/10-06handoff中的ContextPackV1、FinalEvidencePackV1、共享PolicyLM任务联合已可调用 | 文档自己声明分H0–H7后续实施；当前PolicyDecision仅action_id | 只列future-excluded，不创造这些schema的300条gold |
| M03 历史审计过期 | 旧business-chain audit A01–A08仍全数未修 | repair文档与当前source已有身份隔离、final pack核验对齐、history边界等修复；A09/A10仍单独待处理 | 不复述旧问题为当前事实；保留版本区别 |
| M04 taxonomy错层 | capability catalog=可用Policy工具，legacy tool schema=canonical schema | resolver缺4个映射；native/legacy参数不同 | task间不混枚举；Policy只真实projection |
| M05 parser边界差异 | 所有model JSON都如Policy严格拒绝围栏/额外数据 | Policy拒duplicate/prose/fences；semantic helper提取大括号并json.loads，额外keys可能忽略 | strict-wire评测profile单列，不冒充所有生产parser行为 |
| M06 意图规则与中文冲突 | 强intent lock一定正确 | TRB0-0145/0169 authored intent与rule锁定不同；validator强制rule intent | 兼容gold保留、显式标冲突；不算自由语义理解成功 |
| M07 regex不理解否定/顺序 | 关键词出现就应该查工具 | RulePolicy对80个作者语义样本39命中；否定/引用常选tool，排序未遵循自然语言 | semantic gold独立于rule；对照差异不是模型质量结果 |
| M08 状态层差异 | PolicyOutcome task_status与LearningTask状态完全一致 | Outcome还允许pending；各执行层resume/paused映射不等同单一转换表 | 控制任务按实际service/validator；不合并enum |
| M09 Goal接口不同层 | GoalSummary与GoalStore约束必须相同 | summary1..6 criteria/title+objective必填；store≤12且可空；状态不在summary | 不改生产，按各自contract分任务 |
| M10 evidence namespace /启发式 | sufficient等价supported；同intent一定无新facet；缺版本一定拒绝 | continuity分支只认supported/partial；同intent短路；缺版本宽容 | 状态对照冻结此行为，明确不当作语义真理/安全证明 |
| M11 scope设计与现状 | 用户明确要查教材就一定进入教材路径；H1方案已取消错误hard gate | 无选书可退general；auto词法/anchor可能subject_mismatch；support gate仍存在 | 不擅改scope gold；记录候选/信息可达性限制 |
| M12 telemetry不等于gold | RuntimeEvent完整串出正确decision→用户Goal成功 | metadata best effort不含完整payload，Outcome事实没有correctness，Goal unknown默认 | 不从成功事件自动标注、不把trace当semantic judge |
| M13 暴露信息截断 | 模型可用完整原始用户文本推断隐藏约束 | Observation request/resolved≤2000，exercise query≤300；模型看不到截断后文 | 不用hidden原文定标；长截断专项留扩展 |
| M14 model输入不足vs判错 | 看接口存在就能把任意歧义丢给模型 | gate强规则先走；reference validator只保证membership | case标interface-only/gate；不能用runtime接受率替代语义正确率 |

其中M04/M08/M09是层间契约差异，未断言为生产bug；M02是明确的未来设计；M06/M07/M10是当前语义限制；M01是可复现的冻结规范失配。生产Policy V0 spec与核心three-action/fallback契约本次未发现需要改写的冲突。

## 7. 测试证据与未测范围

本任务使用Python3.10.21、临时DATA/PROGRESS/BOOKS/VECTOR等路径、socket.connect禁止网络，`PYTHONDONTWRITEBYTECODE=1`，pytest关闭cache。10文件269测试，249通过20失败；包括Policy、understanding、context pack、Goal、LearningTask、错题、write/recovery与旧dataset。结果不意味着未选中的全仓测试全部通过，也不覆盖真实provider/本地模型/教材索引/桌面UI。

生成300条时调用真实projection、RulePolicy对照、understanding/semantic validators、DecisionRouter、retrieval proposal、context seed、临时GoalService、select_decision注入；并非仅按文档想象gold。模型语义部分仍需独立裁决。源码完整性检查见source-integrity-check.json；不把生成的300/300 gold round-trip冒充模型得分。
