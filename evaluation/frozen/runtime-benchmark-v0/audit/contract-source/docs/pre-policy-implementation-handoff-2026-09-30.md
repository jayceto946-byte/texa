# Scope

Texa — Checkpoint Remediation Plan / Implementation Handoff，2026-09-30。

本文件固化已确定的整改计划，不增加 findings，不启动代码实现。后续实现目标：**修真实 failure mode，删除无价值复杂度，把当前 Texa 收尾为成熟、稳定、低歧义的 checkpoint，然后停止架构扩张。** 当前版本不必成为完整 Policy-ready architecture。

执行顺序：P0 correctness → P1 consistency / stability → 已确认无价值的 defensive debt → acceptance。每项修改必须对应下文的具体 failure mode 或确认无消费者的代码；不得以“未来训练可能需要”为理由增加当前 Runtime。

四类定义：

- **CHECKPOINT BUG**：当前 correctness、consistency、race、idempotency 问题，按本文件最小范围修复。
- **DEFENSIVE DEBT**：重复 fallback、catch-all、测试兼容胶水、无消费者抽象；优先删除或局部简化。
- **POLICY PREREQUISITE**：真正开始 Policy 设计或采集时再处理；当前只保留现有接口边界与 TODO。
- **FUTURE ARCHITECTURE**：长期迁移或框架统一；全部 defer，不属于 checkpoint remediation。

同一 finding 可包含多类子问题；只实施明确映射到 P0/P1 或 Delete / simplify 的部分。

| Finding | 新分类与当前范围 | Deferred / DO NOT |
|---|---|---|
| F01 | CHECKPOINT BUG → P0-1：删除与最终结论无绑定的 numeric passed | POLICY PREREQUISITE：claim / reward 标签；不建通用结论验证器 |
| F02 | CHECKPOINT BUG → P0-2：跨 origin resume、旧 Goal 合同恢复、完成后仍运行、生命周期竞争 | FUTURE ARCHITECTURE：Goal/Runtime DB 统一、单一控制事务库；不迁库 |
| F03 | CHECKPOINT BUG → P1-7：错误 retention、重复/虚假 user_outcome、诊断承诺失真 | POLICY PREREQUISITE：无损采集与完整因果链；FUTURE ARCHITECTURE：事件系统重建；不再整体列为 P0 |
| F04 | CHECKPOINT BUG → P1-1：部分初始化失败后重试提前返回，缺 link/worker | FUTURE ARCHITECTURE：durable dispatch queue、通用恢复协议；不把可重试初始化扩大为自动重跑 |
| F05 | CHECKPOINT BUG → P1-2：A 的事件改变 B；正式 Goal 生命周期由 GoalStore 拥有 | 不重写全部 LearningState，不迁移历史 |
| F06 | CHECKPOINT BUG → P1-3：SSE event/outcome 读取版本一致 | 不新增事件总线 |
| F07 | CHECKPOINT BUG → P1-4：outbox 逐项失败隔离、公平处理 | FUTURE ARCHITECTURE：通用 recovery；不建重试平台 |
| F08 | CHECKPOINT BUG → P1-6：复用 verifier，保存最小输出合同；已知缺输入不能伪装成功 | POLICY PREREQUISITE：机器可评成功标准；后台补输入恢复工作流后置，不在本次实现 |
| F09 | CHECKPOINT BUG → P1-7：shadow 标签真实、透传已有版本；DEFENSIVE DEBT：无消费者分支 | POLICY PREREQUISITE：完整 decision→outcome join、provenance 与版本冻结；不要求完整训练闭环 |
| F10 | CHECKPOINT BUG → P0-3：请求重试不重复建 Goal/事件，resume 不重复 preparation 副作用 | FUTURE ARCHITECTURE：统一 Command Service；不建操作日志框架 |
| F11 | CHECKPOINT BUG → P1-5：pending/expired/unknown/executed 投影与动作真实 | FUTURE ARCHITECTURE：SQL/JSON approval 合并；不迁审批存储 |
| F12 | CHECKPOINT BUG → P1-8：首 100 条遗漏、坏记录杀死 worker、静默 blocked | 完整调度历史/平台后置，不建 trigger 状态机 |
| F13 | CHECKPOINT BUG → P1-3：旧 poll 响应覆盖新状态 | 不建全局前端状态层 |
| F14 | DEFENSIVE DEBT：重复 timeout/catch-all；已复现的线程无界/错误冒充成功属于 CHECKPOINT BUG → P1-9 | FUTURE ARCHITECTURE：统一 executor/recovery；不顺势统一框架 |
| F15 | DEFENSIVE DEBT → Delete / simplify：无消费者抽象、测试胶水、fake harness、误导命名 | 不用新的 abstraction 替换被删除的 abstraction |

# Authority / precedence

**本 handoff 是本次 checkpoint 后续实现的唯一 authority。只读本文件即可确定实现范围、优先级、禁止事项与验收条件。** 它是计划，不是完成声明，也不自动授权本文列为 deferred 的工作。

- 原始 [Pre-Policy Architecture Audit](pre-policy-architecture-audit-2026-09-30.md) 保持不变，继续作为 F01–F15 findings、代码定位与 reproduction evidence 的历史审计报告；[复现材料](validation/pre-policy-2026-09-30/README.md) 仍然有效。
- 原报告的 **M0–M3、target architecture 和 NO-GO 条件不再作为实现范围或 checkpoint 验收门槛，全部由本 handoff 替代**。引用原报告仅用于定位和证据，不得把其中长期建议重新带入实现。
- **若 audit 与 handoff 在“整改范围、优先级、是否需要架构迁移”上冲突，以 handoff 为准。** 其他历史 runtime / architecture handoff 也不能向本 checkpoint 导入额外任务。
- 保留已证明有价值的 owner fence、receipt、outbox、EvidencePack，以及必要的权限、schema、版本与输入输出检查。删除依据是消费者和 failure mode，不是开发者或模型归属。
- **DO NOT**：Goal/Runtime database unification；JSON→SQL Runtime 全量迁移；RuntimeEvent V1 training/event-sourcing 化；新增多层 fallback、recovery abstraction 或 speculative infrastructure。

# P0

## P0-1 — 数值验证假通过（F01）

- **Failure**：无关工具的成功标记或任意共享数字使错误结论通过，例如 `2+2=999` 仅因输入中有 `2` 被视为 verified。
- **Change**：在现有 verifier 中删除这两类宽松通过分支；没有与最终结论实际绑定的核验依据时返回 `unverified`，保留答案及现有降级披露。
- **Do not**：不建通用 claim engine、数学证明器、LLM judge 或 reward/label 系统。

## P0-2 — Goal 生命周期与运行准入（F02）

- **Failure**：暂停 Goal 可从 Chat 绕道恢复；关键目标已变更却继续旧任务；完成后仍有 active run；审批、恢复和更新竞争导致旧 run 继续获得写入许可。
- **Change**：限制 Chat resume 的 origin；在现有 checkpoint 保存执行相关 Goal 内容摘要；start/resume/approval 检查当前 Goal 状态及摘要。暂停、关键更新、完成复用现有 owner fence。
  - 在现有单后端进程内，用短临界区协调 Goal start/resume/pause/关键 update/complete 与写入准入；不把模型/工具调用放入长锁。
  - 先 fence，再确认 Goal 更新成功。Goal 保存失败时允许留下“Goal 仍 active、run 已 interrupted”的安全状态并明确报错，不伪称跨库原子成功。
  - 摘要仅覆盖 `objective/scope/success_criteria`；标题、调度或 pause/reactivate 本身不使未变的执行合同失效。
  - 已准入、在途的领域写入可完成，由 receipt 对账；pause 不撤销已发生写入，也不允许新写入绕过准入。
  - 保留启动时将未完成运行转为 interrupted 的行为，不自动续跑。
- **Do not**：不合并数据库，不建单一控制事务库、统一 Command Service、新授权框架或多进程/分布式一致性方案；不承诺撤回已发生的副作用。

## P0-3 — Preparation 副作用幂等（F10）

- **Failure**：相同请求重试重复创建 Goal/事件；恢复 task 时重复应用最初的 state operations。
- **Change**：在现有 Chat 流程局部分离解析与一次性应用；以稳定 turn/request + operation 身份复用已有 Goal/event ID；重试及 resume 跳过已应用操作。
- **Do not**：不建 command bus、通用 operation journal 或新编排层；不重写整个 Resolver/Memory。

# P1

## P1-1 — 部分初始化可重试（F04）

- **Failure**：configure 已提交、link 失败后，重试提前返回，留下没有 worker 的 running task；线程启动失败留下假 worker 注册。
- **Change**：移除错误 early return，补齐缺失 configure/link；只对尚未执行过的初始化安全启动一次。`Thread.start` 失败清理注册并终止或中断。先查幂等请求，再判断是否为 revision 过期的新命令。
- **Do not**：已调用模型或工具的任务不能因内存中没有 worker 就自动重跑，必须 interrupted 后显式 resume；不建 durable dispatch queue 或后台修复扫描器。

## P1-2 — Goal 投影隔离（F05）

- **Failure**：Goal A 的生命周期事件被 reducer 应用到 Goal B，投影与正式状态漂移。
- **Change**：按 `goal_id` 匹配事件；正式 Goal 生命周期以 GoalStore 为权威。无归属 legacy event 不得修改其他 Goal。
- **Do not**：不迁移历史事件，不全面重写 LearningState/Memory，不增加第二份生命周期权威。

## P1-3 — SSE 与 UI 版本一致（F06/F13）

- **Failure**：final 已提交，但 SSE 使用不匹配的旧 snapshot 报错；重叠 poll 的旧响应覆盖用户刚完成的操作或新 run。
- **Change**：从一致的 SQL snapshot 读取状态和结果，final 只取匹配的已提交 run；UI 串行 poll，手动操作完成后使之前请求失效，并检查 revision/run_id。
- **Do not**：不建 sync service、事件总线或全局状态框架；UI 不成为第二份执行权威。

## P1-4 — Outbox 失败隔离（F07）

- **Failure**：一条投影失败阻断其他会话；毒记录一直占据首批，使后续记录饥饿。
- **Change**：逐项隔离异常，复用已有 attempts；公平处理后续条目。失败项保留 pending，记录 outbox ID 与错误；继续使用稳定 message/event ID 防止重复投影。
- **Do not**：不丢弃失败项或标记假成功；不新建 retry framework、dead-letter 平台或通用 recovery 协议。

## P1-5 — 审批状态与动作真实（F11）

- **Failure**：unknown/expired 被投影成 pending，UI/API 给出不安全或无效的再次确认入口。
- **Change**：如实投影 pending/expired/unknown/executed，只暴露当前允许动作；复用现有 receipt reconciliation。无 receipt 的不确定写入保持 unknown、不可普通重放；expired 不可确认。
- **Do not**：不合并 SQL/JSON 审批数据库，不新增 reconciliation 工作台，不把未知写入当普通失败重试。

## P1-6 — 最小输出合同与缺输入披露（F08）

- **Failure**：Goal 没有冻结最小 required outputs；已知关键输入缺失仍被当作成功。
- **Change**：Goal start 复用现有 `derive_required_outputs` 并持久化，交给现有 verifier；Goal 完成仍由用户确认。已知缺少必需输入时明确 failed/degraded，不伪造成功或精确结论。
- **Do not**：不建通用 Goal contract language，不自动机器评判全部 success criteria，不实现完整后台补输入/恢复工作流。保留现有图片题 `waiting_for_input`；明确当前 SQL Goal 的能力限制，不宣称其支持尚未实现的恢复。

## P1-7 — 诊断数据语义真实（F03/F09）

- **Failure**：retention 分组/终止判断错误而裁剪活跃记录；adapter final 与 legacy done 自动发出虚假或重复 user_outcome；实际采用的 decision 被标为 shadow；版本被遗漏或用当前配置冒充历史。
- **Change**：修正 retention 分组及 terminal 判断；删除两处自动 user_outcome emission；shadow 按实际是否采用决策标记；透传本轮已有 context/version 元数据，不补造历史值。RuntimeEvent 明确维持 best-effort 诊断定位。
- **Do not**：不建 durable audit outbox、DecisionRecord、完整训练因果链、全量 provenance 冻结或 RuntimeEvent 重建；不把 flush/drain 当持久性保证，不宣称完整 replay，也不把 best-effort 本身作为 checkpoint 阻塞项。

## P1-8 — 调度覆盖与 worker 存活（F12）

- **Failure**：只扫描首 100 个 Goal 导致到期任务遗漏；坏记录/初始化异常杀死 worker；拒绝运行只静默跳过。
- **Change**：在现有 GoalStore 用 due 查询或分页覆盖到期项；单项异常隔离，顶层 worker 保持存活并报告错误；明确 blocked reason，不把被阻塞触发当成功推进 due。
- **Do not**：不建新 scheduler、完整 trigger 状态机或全量调度历史平台。

## P1-9 — 已证实的超时容量与错误处理（F14）

- **Failure**：超时仅结束等待，底层调用仍在运行；反复调用导致线程无界，或 catch-all 把真实失败当成功。
- **Change**：先用确定性/故障注入复现具体路径；在现有入口设置进程级容量约束，只在底层调用实际结束后释放。容量不足明确失败，保留迟到结果 fence；对已复现的错误冒充成功分支局部修正。
- **Do not**：不把超时视为物理调用已停止，不建统一 executor/recovery，不增加补偿调用或 fallback 链，不为统一错误类型重写所有路径。

F12/F13/F14 中原本只有静态证据的子项，实施时先补确定性或故障复现，再限定补丁范围；不得从静态风险扩展为全面框架治理。已有历史测试结果只作基线，不代表整改已通过。

# Delete / simplify

下面是既定删除/简化清单。实施前只做必要的消费者确认；无生产消费者时直接删除，有真实消费者时仅局部简化，不机械删除安全边界。

| 对象 | 删除/简化及解决的具体问题 | DO NOT |
|---|---|---|
| `DomainCapabilitySpec` | 无生产消费者则删除，消除没有执行作用的契约歧义 | 不新增替代 capability abstraction |
| `BoundedFallback` 及孤立 helpers | 无生产实例则删除，移除不存在的恢复能力表象 | 不实现它、不另建 fallback manager |
| fake MCP / schedule harness | 移到 tests，去除测试设施与生产服务的混杂 | 不扩展成插件或调度平台 |
| `TypeError → 再调用一次` 的 test-double 兼容 | 删除重试胶水，让 test double 遵守真实接口，避免模型/领域调用重复发生 | 不以另一种 broad catch 重建兼容重试 |
| Planner 解析失败后的 `chapters[:1]` | 删除任意首章 fallback，避免无依据选章 | 不静默扩大教材范围；保留有真实价值的同范围召回降级 |
| 已有真实前置检查后的重复分支、空 wrapper、F09 无消费者分支 | 局部删除，减少重复决策和维护歧义 | 不删除权限、输入输出、版本、时间边界检查；不全仓机械合并 catch |
| `run_offline` 的误导命名 | 对实际生产使用的内部名称做窄范围纠正 | 不改变执行协议，不顺带统一 legacy/SQL runtime |

保留顶层 worker 的异常隔离、receipt、owner fence、outbox、EvidencePack、同范围检索 fallback、已保存用户 profile/旧环境变量以及历史读取兼容。不得为整理 schema 删除持久化/公开的 `Goal.plan` 或历史字段。

`finish.answer` 被丢弃后重新生成属于非阻塞 debt：当前只记录，不重写 native tool 协议，不纳入 checkpoint 必修条件。DO NOT：把本节当成无边界“清理所有 legacy”的授权。

# Deferred

## Policy prerequisite

当前只保留既有 Router 输入/输出、Tool schema/result/provenance 边界与 TODO；以下工作等 Policy 真正开始设计或采集时处理。

| 后置内容 | DO NOT（当前） |
|---|---|
| 完整 observation→decision→execution→outcome training join | 不建 DecisionRecord/训练事实层 |
| admissible actions、policy version、排序/排除原因 | 不增设 policy 决策框架或候选动作基础设施 |
| 无损事件、跨重启 parent、训练 retention | 不新增采集 outbox 或把 RuntimeEvent V1 升级成完整事件系统 |
| profile/model/prompt/verifier 全版本冻结 | 不补造历史版本，不为潜在训练复制当前所有配置 |
| episode checker/export、labels/reward/holdout | 不建训练导出、标注或评估平台 |
| 机器可评的 Goal success criteria、通用 claim verifier | 不取代本次最小 required outputs 与现有 verifier |
| 语义 Router 校准与 Policy 接管 | 不扩大当前 Runtime 决策能力 |
| 后台 Goal 补输入与恢复工作流 | 不冒称已有能力，不改造现有图片题输入门槛 |

## Future architecture

| 后置内容 | DO NOT（当前） |
|---|---|
| Goal/Runtime DB unification、单一控制事务库 | 不迁库，不用统一事务作为 P0-2 前提 |
| 全量 JSON→SQL Runtime、关闭 legacy 主写路径 | 不大迁移，不以入口数量本身判断 checkpoint 不合格 |
| RuntimeEvent 全面重建 / event sourcing | 不重建完整事件/回放系统 |
| 统一 Command Service、executor、general recovery | 不新增通用框架，不把局部 correctness fix 演变成内核建设 |
| SQL/JSON approval 合并 | 不迁审批数据，不扩展本次 reconciliation 范围 |
| 通用 RuntimeKernel、durable dispatch、完整调度平台 | 不增加 speculative infrastructure 或后台修复机制 |

独立数据库和现有多条 runtime 路径可以保留；前提是具体 task 的 writer/owner 清晰，不能从其他入口绕过状态限制，projection 不成为执行权威。以上 deferred 内容不是隐藏验收门槛。

# Acceptance criteria

以下是整改后的验收要求，不是当前已通过声明：

1. **验证真实**：F01 数值反例返回 unverified，不再仅凭无关工具成功或共享数字发布 verified；不要求建立通用数学正确性证明。
2. **生命周期封闭**：pause/update/complete/approve/resume 的确定性交错测试通过，过期合同/旧 run 被 fence，跨 origin 不能绕过状态；不要求跨库事务或分布式一致性。
3. **幂等可证**：重试创建、部分初始化失败、审批与 resume 不重复领域写入或执行；已执行任务不会因 worker 丢失自动重跑；不要求通用 command journal。
4. **投影一致**：Goal 事件互不串写；SSE final 与 snapshot race 可复现并消除；旧 poll 响应被忽略；不增加第二份权威状态。
5. **故障隔离与容量**：毒 outbox 不阻断其他项，超过 100 个 Goal 仍覆盖到期任务，坏调度记录不杀死 worker，在途线程受实际完成约束；不要求新恢复/调度平台。
6. **持久结果与不确定写入**：已提交 final 可读；unknown 保持真实，可用 receipt 对账，不可重放写入不能走普通 retry；不声称暂停能撤回已发生写入。
7. **诊断诚实**：RuntimeEvent 的 best-effort 限制明确，不错误裁剪已知活跃 run，不自动伪造 user_outcome，shadow/已有版本透传真实；不要求 lossless capture 或完整 replay。
8. **验证覆盖**：运行相关后端回归（Python 3.10 / venv310）、前端检查与 build；优先覆盖 Electron 的停止/重启、审批、投影失败、多 Goal 场景。记录实际执行与环境限制，不能用旧审计测试冒充本轮验证；不新增训练评测项目作为本 checkpoint 门槛。
9. **范围收口**：每个 diff 对应本 handoff 的 failure mode 或确认无消费者代码；无 DB 统一、新框架、多层 fallback 或训练基础设施。保护已有用户数据、配置和无关未提交改动；不得顺带完成 Deferred。

**冻结结论：已列明的真实 bug 修复且以上 criteria 满足后，checkpoint 为 GO。** Best-effort RuntimeEvent、独立数据库和保留 legacy 路径本身不阻塞该 GO。此 GO 只表示适合作为 Runtime Policy 开始前的稳定基线，不表示现有日志已是可信训练数据集或完整 Policy-ready architecture。验收后停止架构扩张，后续 Policy 工作单独定范围。
