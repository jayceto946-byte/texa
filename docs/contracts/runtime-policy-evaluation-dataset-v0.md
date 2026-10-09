# Runtime Policy Evaluation Dataset V0 Spec

**依据：已批准 Spec 的原始字段与语义，以下保留该契约；V0 离线实现细节见文末。**

评测单位是**一个冻结决策点的下一动作选择**，不是整段回答质量。可信样本必须能分别判断：Runtime 是否提供了正确候选、Policy 是否选对、执行后实际发生了什么。

## 1. Sample schema

建议使用版本化离线文件；不新增数据库。数据集 manifest 固定合同、标注规则、Runtime/Registry 版本和 split 清单。

| 字段 | 定义与存在理由 |
|---|---|
| `sample_id` | 不可变、唯一标识；修改 Observation 或 gold 时产生新样本版本 |
| `observation` | 完整 `PolicyObservationV0`；唯一的 Policy 输入 |
| `observation_hash` | canonical JSON 摘要，确保各比较对象看到完全相同的输入 |
| `source` | 来源类型、`source_family_id`、脱敏来源 ref、投影版本、决策位置；用于追踪、复现和防泄漏 |
| `scenario_tags` | 多标签类别，用于覆盖矩阵和分层报告 |
| `candidate_generation_valid` | `true / false / null`；分别表示已验证有效、确定错误、尚无法判断 |
| `candidate_generation_errors` | 候选错误代码及受影响 action ID；不能用 Policy 选择结果反推 |
| `ambiguity_status` | 见第 3 节；控制标注解释和指标纳入 |
| `acceptable_action_ids` | 所有可接受的已有候选 ID；可多选。`null` 表示未能定标，`[]` 表示已判断没有可接受候选 |
| `preferred_action_id` | 可选；必须属于 acceptable 集合，仅在有明确、可证明的优先理由时填写 |
| `action_judgments` | 对每个候选记录 `acceptable / unacceptable / undetermined` 及原因标签，支撑过早回答、过度调用等指标 |
| `input_requirement` | `required / not_required / undetermined`；表达语义上是否必须补输入，不直接复制 Runtime 判断 |
| `label_source` | 判定规则 ID、独立审核者、裁决方式及标注规则版本；允许多个来源 |
| `adjudication_reason` | 简短依据；说明 acceptable 集合及分歧如何处理 |
| `evidence_refs` | 可选；指向冻结、脱敏、可访问的审阅依据，用于核验候选生成和标签 |
| `hard_tags` | 可选；记录困难样本类型，不改变 gold 或评分权重 |

**存储约束：**

- `admissible_actions` 只存于 `observation`，不在顶层重复存储。
- 不复制 Runtime task/run、完整 tool result 或 EvidencePack。优先使用现有 ref 和有界摘要；ref 必须指向固定版本，不能只指向未来会变化的线上对象。
- 标注依据可以帮助审查候选生成，但**不能让选择 gold 依赖 teacher 看不到的关键事实**。Observation 不足以区分动作时，标记信息不足。
- execution outcome 不属于 gold。未来独立 evaluation result 通过 `sample_id + observation_hash` 关联原始 decision、validation、fallback 和已有 Outcome。
- split 在独立 manifest 中管理；不把 split 名称传给 Policy。

## 2. Gold-label policy

先验证候选生成，再判断下一动作是否符合任务语义、约束和当前信息。**admissible 表示 Runtime 允许执行，不表示该动作一定适合当前任务。**

### `generate_answer`

可接受条件：

- 当前可用信息足以给出符合任务要求的回答；或允许明确披露限制、不给出无依据结论的降级回答。
- 教材型回答已有同范围有效证据；不能以通用知识代替必要教材事实。
- 没有阻断结论的关键缺失输入。

属于过早回答：

- 用户要求查询当前记录，但尚未执行必要查询。
- 尚缺必要教材证据、图片附表或其他关键条件。
- 只有工具执行成功标记，摘要却不能支持当前结论。

归因必须分开：若 Runtime 违反硬证据门槛仍暴露回答候选，是候选生成错误；若回答在 Runtime 层面合法，但语义上应先查工具，是选择错误。

### `call_tool`

- **必要调用**：完成当前请求必须获取尚未掌握的事实，且该冻结工具及参数能取得相关事实。
- **合理但非必要**：当前已能回答，但调用可以解决具体不确定性、改善用户要求的覆盖，成本和约束允许；工具与回答可同时 acceptable。
- **unnecessary call**：不提供相关信息、重复已完成且未变化的查询、被关键词误导，或为无关范围取数。

工具名匹配不足以定标；必须核对冻结 args。参数错误属于 candidate-generation failure。

### `request_input`

必须请求：缺失信息会实质改变结论，且无法通过当前合法工具获得，也不能通过明确范围限制完成请求。

不应请求：信息已存在、合法工具可获取、只是非必要偏好，或系统正在等待审批。审批不是 missing input。

Runtime 漏掉真实阻断输入时，标记 `candidate_generation_error: missing_input_gate_error`，不得让 teacher 自造 `request_input`、参数或输入清单。

**V0 特有限制：**`request_input` 目前仅在 pre-SQL gate 作为单候选执行。SQL 路径缺输入走原失败路径，不能因没有该候选就认定违约；须结合 `source` 中的执行位置判断。

## 3. Ambiguity model

| 状态 | 含义 | 进入主选择 accuracy |
|---|---|---|
| `single_correct` | 恰有一个 acceptable 动作 | 仅有效多候选样本 |
| `multiple_acceptable` | 两个以上动作均合理 | 仅有效多候选样本 |
| `candidate_generation_error` | 缺候选、错误准入、绑定或 gate 错误 | 否 |
| `insufficient_information` | Observation 不足以确定 acceptable 集合 | 否 |
| `invalid_sample` | schema、来源、版本或标注记录损坏 | 否 |
| `runtime_only` | 合法零候选，应该走现有 Runtime 控制路径 | 否 |

多个 acceptable 动作**不必成本相同或执行轨迹相同**；只要求都符合当前任务。可存在偏好，但不得用 preferred 命中率替代 acceptable-action accuracy。

Teacher 分歧可能说明多解、信息不足，也可能只是某方错误。不能按多数票制造唯一答案。

单候选独立报告为 forced；唯一候选也可能暴露候选生成错误，不能自动判为 gold。

## 4. Error taxonomy 与归因

| 层次 | 错误代码示例 | 判断标准 |
|---|---|---|
| Candidate generation | `required_action_missing` | 必要动作未出现，且并非 V0 既有控制路径的合法边界 |
| Candidate generation | `forbidden_action_exposed` | 权限、范围、预算、重试或证据硬门槛禁止的动作被暴露 |
| Candidate generation | `invalid_bound_args` | 参数不合法，或绑定到错误对象、范围 |
| Candidate generation | `missing_input_gate_error` | 漏报阻断输入，或错误制造阻断门槛 |
| Selection | `wrong_acceptable_choice` | 有合理候选却选了 unacceptable 动作 |
| Selection | `premature_answer` | 应先补事实，却选择回答 |
| Selection | `unnecessary_tool_call` | 选择无必要信息收益的工具 |
| Selection | `missed_input_request` | 合法输入候选存在且必须选择，却选其他动作 |
| Decision validation | `invalid_format` / `unknown_action_id` | 原始输出不符合 Decision 合同 |
| Freshness validation | `stale_observation` / `precondition_changed` | 决策期间执行事实或环境变化 |

统计原则：

- 候选生成错误样本**整体排除 selection accuracy**，即使仍存在一个碰巧可选的好动作。
- malformed/unknown 是原 decision 的失败；在可评分样本中按未命中计，并单列原因。
- stale/precondition 使用成对冻结状态的合同探针验证，不计作模型语义选择错误。
- fallback 与 task success 永不覆盖原 decision failure。

## 5. Seed-set coverage matrix

不规定巨大样本数；先保证每类有可审阅的独立 source family，能区分关键反例。

| 场景 | 必须验证的区别 |
|---|---|
| Direct answer | 无需查工具；当前普通问答仅在离线 harness 验证，不暗示扩大生产接管 |
| Textbook retrieval required | 无教材证据时检索，有同范围证据时才允许回答 |
| Non-textbook tool required | 进度、习题查询必须读取实际记录 |
| Missing input | 真正缺失与不必要澄清；覆盖真实 pre-SQL forced gate |
| Multiple tool candidates | 多项任务的合理下一步，不把固定词法顺序直接当 gold |
| Tool vs answer | 必要查询、可选查询和无意义查询 |
| Tool already executed | 利用已有结果；成功、失败、unknown 均不得自动重试 |
| Zero-result retrieval | 空习题查询与教材证据不足的不同后续行为 |
| Tool failure | 可披露失败的回答与仍不可作答的任务 |
| `previous_result=succeeded` | 执行成功不等于覆盖充分 |
| `previous_result=failed` | 失败后的有限后续动作 |
| `previous_result=unknown` | 不把未知当成功，也不绕过重试限制 |
| Degraded allowed / forbidden | 可以说明限制，与不能编造精确结论的区别 |
| Multiple acceptable actions | 等价或均合理的执行顺序，不制造伪唯一 |
| Misleading lexical cues | 强关键词与实际意图相反 |
| Long request / rewritten query | 截断丢失关键条件、指代解析、显式纠正；信息不足时不得强行定标 |
| Goal context | 仅验证 Observation 中 goal/constraints 的影响，不接 Goal worker Policy |
| Candidate defect controls | 漏候选、错误参数、错误 gate；专门考察归因 |
| Decision/freshness controls | malformed、unknown、stale、precondition change、一次 fallback 的独立记账 |

人为篡改候选形成的样本必须标记为 **fault-injection control**，不得冒充生产可达决策点。

现有 11 个 baseline scenarios 可作为 seed 来源，但原固定 sequence 必须重新按上述规则审阅，不能直接转为唯一 gold。

## 6. Dataset splits

建议初始按 source family 约 **50% development/seed、25% validation、25% locked test**；覆盖和独立性优先于比例，小样本报告实际数量。

- 同一题及改写、同一教材实例、同一任务轨迹、相同模板衍生版本统一分组切分。
- Synthetic variants 继承 source family；反事实配对也留在同一 split。
- 真实用户样本纳入前先脱敏、授权审阅并去重；不能仅更换人名就视为新样本。
- 跨 split 检查规范化文本、近似模板、来源实例及轨迹关联。
- 已用于提示词或规则调整的样本只能留在 development。
- Validation 可用于方案比较；locked test 永不进入训练、teacher prompt tuning 或逐题调试。
- locked test 的题目级反馈应受限；发生泄漏的 family 从以后版本的 locked test 移出，不能继续声称独立。

## 7. Label sources and adjudication

来源表示**证据与责任链**，不表示自动可信等级：

- Deterministic contract rule：可判断 schema、唯一 ID、冻结参数、明确准入约束。
- RulePolicyV0：比较基线，只提供预测。
- Sol teacher、Luna teacher/reviewer：独立提供预测。
- Human adjudication：根据任务语义及证据确定最终 acceptable 集合。

处理规则：

| 情况 | 处理 |
|---|---|
| 确定性规则完整决定标签且输入已验证 | 可自动接受，并保存规则 ID、版本和依据 |
| Sol/Luna 一致 | 记录 agreement；仅有一致性不足以自动成为语义 gold |
| Sol/Luna 分歧 | 审查是否多解、缺信息或错误，不投票裁决 |
| Teacher 与 Rule 分歧 | 保留双方原始预测，由独立依据定标 |
| 多个动作合理 | 标注完整 acceptable 集合，preferred 可缺省 |
| 候选错误、信息不足、降级边界不清 | 人工审阅；无法裁决则退出主指标 |

**进入 locked test 的语义标签，若不能由已批准的确定性规则完整证明，必须人工裁决。** Teacher 比较本身始终只返回 `action_id`；标注说明由独立审阅流程记录。

## 8. Teacher comparison protocol

同一冻结输入分别提交给 RulePolicyV0、Sol、Luna：

1. 三者接收字节一致的 canonical Observation；候选顺序和 args 相同。
2. 不提供 gold、场景标签、hard tags、其他模型输出或隐藏审阅材料。
3. Teacher 仅返回 `{"action_id":"…"}`；使用同一严格 parser，不自动修复格式。
4. 固定并记录模型快照、提示词版本、解码配置；首次输出作为主结果，不挑选多次尝试中的最佳值。
5. 零候选、单候选不调用 teacher；分别报告 Runtime-only、forced。
6. 如测试 fallback，原始结果与 fallback 独立保存；fallback 后成功不算 teacher 原始命中。
7. 比较请求失败、超时、协议错误分别报告，不静默丢弃。

真实 teacher 调用属于未来单独授权的付费/数据出境步骤；本轮仅定义协议。

## 9. Hard / informative sample policy

建议 `hard_tags` 使用可组合标签：

- `rule_correct_teacher_wrong`
- `rule_wrong_teacher_correct`
- `sol_luna_disagreement`
- `multiple_near_equivalent`
- `lexical_counterexample`
- `previous_result_sensitive`
- `candidate_set_sensitive`
- `context_sensitive`

前两类只能在独立 gold 确立后赋值。配对样本通过 source family 和 pair ref 关联，必须由合法 Runtime 投影产生；故障注入另列。

Hard 标签仅帮助分析和审阅，不改变测试权重，也不在本轮设计 SFT 采样策略。

## 10. Locked evaluation quality gates

样本入锁前必须满足：

- Observation schema 及额外合同校验通过。
- action ID 唯一；冻结参数通过对应版本 canonical schema 和范围核验。
- candidate-generation validity 已判断，错误原因可追踪。
- acceptable 集合与 action judgments 一致；preferred 属于集合且有明确依据。
- ambiguity 状态明确；语义标签完成所需裁决。
- Observation 足以支持选择标签；无隐藏事实依赖。
- 来源、决策位置、投影版本和场景可追踪。
- refs 固定、可访问；不依赖临时线上状态。
- 无敏感信息、凭证或 split leakage。
- 标签、manifest、Observation hash 固定并版本化。

分两条锁定轨道：

- **Selection set**：候选生成有效、标签可判定；主指标再筛多候选。
- **Diagnostic controls**：候选生成错误、Runtime-only、freshness 和故障注入；缺陷必须已确认，不能混入 selection 分母。

损坏样本或未裁决样本不得进入锁定计分集合。

## 11. Metrics

设主选择集合 \(E\) 为：**候选生成有效、gold 已判定、候选数至少为 2** 的样本。

### Candidate-generation metrics

- Failure rate：确定候选生成错误数 / 已完成候选生成审查数。
- 按漏候选、错误准入、参数绑定、输入 gate 分项统计；允许一条样本多个原因。
- 单列未判定率、合法零候选数、forced 数。
- 自然来源与 fault-injection controls 分开报告；注入比例不能当生产错误率。

### Policy-selection metrics

| 指标 | 口径 |
|---|---|
| Exact acceptable-action accuracy | \(E\) 中原始 decision 严格合法且 action ID 属于 acceptable 集合的比例 |
| Single-correct accuracy | \(E\) 中 `single_correct` 子集命中率 |
| Preferred-action agreement | 仅有明确 preferred 的子集；不是 correctness |
| Invalid decision rate | 原始 malformed/unknown 输出比例；另列超时、调用失败 |
| Unnecessary tool-call rate | 选中 `unnecessary_tool_call` 的样本数 / \(|E|\)；另报占合法工具选择比例 |
| Premature-answer rate | 选中过早回答的样本数 / \(|E|\)；另报占合法回答选择比例 |
| Disagreement rate | 两方均返回合法 ID 时选择不同 ID 的比例，并报告共同有效样本数 |
| Harmful disagreement | 分歧中一方 acceptable、另一方 unacceptable；区别于双方均合理 |
| Rule vs teacher delta | 在完全相同的 \(E\) 上比较 acceptable accuracy 差值，附成对胜/负/平数量 |

Missing-input precision/recall 使用独立 `input_requirement` 标签：

- Precision：选择 request_input 且确实必须补输入 / 所有 request_input 选择。
- Recall：必须补输入且选择 request_input / 所有必须补输入样本。
- 候选生成错误不进入 Policy recall；漏识别 gate 在候选层统计。
- **当前 V0 request_input 为单候选 gate，因此真实多候选 teacher 的该指标通常为 N/A。** 另报 Runtime gate precision/recall 和 forced 正确性，不用人为制造多候选输入路径来填分数。

同时报告 ambiguity 分布、排除原因及各场景样本数。小样本不能只给百分比。

### End-to-end task metrics

仅对有独立任务验收标准且确实执行的轨迹统计：

- 任务验收通过率及可判定覆盖率。
- 工具执行成功率、答案验证状态分布。
- 原 decision rejected、fallback attempted/accepted/executed、最终任务成功分别计数。
- 同一轨迹按 task 计一次，不按多个 decision 重复计数。

`completed`、执行成功、用户反馈、Goal completion、独立任务验收不能互相替代。答案 stub 的结果只证明离线流程合同，不能表述为真实模型答案质量。

## 12. Explicitly deferred

本轮不做 ModelPolicy、Qwen 选型、SFT/LoRA、批量数据生成、reward model、preference optimization、active learning、online rollout、shadow deployment、用户反馈自动转 reward、RuntimeEvent 重建、新数据库或训练状态机。

## Implementation Handoff Outline

未来交给 Sol 的最小组件：

1. **Sample serializer**：冻结 Observation、canonical hash、source/ref 和版本信息。
2. **Sample validator**：合同、参数、标签一致性、可评分资格及 quality gates。
3. **Split assignment**：按 source family 分组、去重检查、锁定 manifest。
4. **Label/adjudication record**：保存独立预测、人工依据和最终 acceptable 集合。
5. **RulePolicy evaluator**：多候选执行；零/单候选独立记账。
6. **Teacher-evaluation adapter**：统一输入、严格 decision 输出、原始失败保留；经授权后运行。
7. **Report generator**：候选、选择、任务三层报告及覆盖/排除清单。

## V0 离线实现与本地使用

`evaluation/policy_dataset_v0` 使用普通 Python 与现有 Pydantic/Runtime models，无新依赖、数据库或生产接线。原 `evaluation/runtime_policy_v0.py` 继续作为独立 Runtime baseline harness。

输入文件：

- `samples.jsonl`：上文 16 个字段；严格拒绝顶层额外字段、重复 JSON key、非有限数、重复候选 ID、损坏 Observation/hash。可选 `evidence_refs`、`hard_tags` 默认空列表。`null` 与 `[]` 不互换。Observation/gold 变更须产生新 sample version；split manifest 的 fingerprint 防止旧 ID 静默变更。
- `manifest.json`：`texa.policy-dataset/v0`，固定 Policy、label policy、Runtime/Registry 版本及源代码 digest；保存本地冻结依据 digest、candidate review 与已批准 deterministic rule allowlist。文件 ref 不发起网络读取。
- `adjudications.jsonl`：`sample_id + observation_hash + label_hash` 绑定 `confirmed/pending`、独立来源和原因；预测文件不参与此记录或 gold 的构造。
- `evidence-files.json`：脱敏 ref 到数据集内部相对文件的映射；拒绝绝对路径/目录越界/越界 symlink。refs 包含固定来源、关联 family 依据和审阅材料。
- 独立 `split.json`：`family-split/v0`，seed、比例、family assignments、sample fingerprints、近似重复审阅结论、locked 状态。

嵌套格式由 `contracts.py` 明确定义：source 包含 type、family、ref、projection version、decision position、related refs、used_for_tuning；candidate errors 为 code + action_ids；action judgments 为 action_id + judgment + reason_tags；label sources 为 kind + ref + version + basis_refs。人工来源记录需来自实际人工审阅，不能由工具伪称。`fixture_review` 仅代表实现阶段独立按 Spec 编写的示例审阅，可用于草稿 baseline，不能通过 locked gate。`approved_rule` 必须在 manifest 的明确 allowlist 中，RulePolicy 和 teacher 不是裁决来源。

Quality 分机器合同、冻结依据、语义裁决三栏。canonical input schema（canonical-tools-v0.json 固定快照）、生产 V0 固定 binder、scope 与 registry metadata/hash 均独立核验；candidate flag 为 true 仍不足以通过。静态校验只能确认字段/引用/已给依据的一致性，不能自动证明审阅结论语义正确、生产可达性或 OCR/模型答案质量。冻结 evidence 必须实际可读取且 hash 相符。locked gate 还要求已批准规则或人工候选审阅与语义裁决；`insufficient_information`、损坏样本和未裁决记录均拒绝锁定。Selection 与已确认 Diagnostic controls 分轨，candidate errors 整条退出主分母。

`policy_input()` 是唯一 Policy 输入校验/序列化边界：从验证后的 sample **仅取 Observation**，或接收独立 `PolicyObservationV0`，重验证并建立深层副本。`serialize_policy_input()` 本身经此入口，不能绕过隔离；`invoke_policy()`、离线 `rule_policy_adapter()`、`call_teacher()`、默认 disabled adapter 和 evaluator 均复用同一个实现。未来 ModelPolicy 必须经此入口，当前不实现模型接线。

字段 ownership 来自既有 Dataset/manifest/prediction/transform 合同；这些字段不得进入 Observation 的开放数据对象。递归检查 constraints、missing inputs、工具输入和文本字段中的结构化数据，也识别完整、嵌入、fenced 及多层 JSON 字符串中的元数据对象/列表。局部候选 ID 必须恰为 `a0..a(n-1)`，不能把标签或其他 metadata 编入 ID。发现泄漏直接抛出 `policy_input_metadata` / `policy_input_action_id`，不静默清洗或重排损坏样本；evaluator 在 selector 调用之前记录 invalid_sample。

该边界不按自然语言关键词过滤：用户请求、普通 goal/约束说明中出现 gold、ambiguity、candidate_generation_errors 等词仍原样保留。合法 wire 模型的字段名及缺输入 status 等业务字段不是评测 metadata；只有结构化数据中的评测字段 ownership 会触发拒绝。不会把 envelope、标签、split、预测搬进任意 prompt/summary，也不会把审阅 ref 正文提交给 selector。保密审查不能完全依赖静态检测；真实用户样本仍需未来授权、脱敏和人工审阅，本阶段不导入。

### Manifest 版本/digest 的 fail-closed 门槛

`runtime_version`、`registry_version`、`label_policy_version`、`source_digests` 均必填，无 wildcard、unknown 或空值语义。前两者格式为 `sha256:` + 64 位小写 hex；label policy 仅接受已批准的 `evaluation-spec/v0`。所有 source/evidence digest 必须是 64 位小写 hex。

`validate_manifest()` 不只校验形状：Runtime/Registry 版本必须匹配当前已批准 V0 baseline；source map 必须覆盖固定的八个 Runtime/Registry 源文件及 canonical-tools-v0.json，且逐项匹配既有 `docs/validation/runtime-policy-evaluation-dataset-v0/source-manifest.json` 冻结记录与本地实际文件字节。只读取这些固定仓库路径，不读取 input manifest 自带的任意路径。Runtime 版本同时核对八个 source pins 的 canonical digest，Registry 版本同时核对现有 canonical schema/metadata 的 digest。修改 source、自行重算版本或修改 declared digest 不构成批准新版本；这需要以后单独审阅，当前不改生产 versioning。

错误码按条件明确区分：`manifest_<field>_missing/invalid`、`manifest_runtime_version_mismatch`、`manifest_registry_version_mismatch`、`manifest_source_digest_set_mismatch/zero/mismatch`、`source_content_digest_mismatch/unavailable`、`approved_source_digests_unavailable`、`registry_content_digest_mismatch/unavailable`。sample validator 重验证 raw manifest 与 model_copy/原位修改过的 manifest；任何错误均进入 frozen_errors，selection_eligible、diagnostic_eligible 和 candidate_reviewed 为 false。CLI 在任何输出创建或选择器调用之前拒绝损坏 manifest。独立 Observation-only schema 检查可以无 manifest 运行，但不会授予 selection eligibility。

排列是独立的 evaluation view，不是新的可执行 Observation 或正式 dataset sample：原样本字节保留，artifact identity 为 original sample + view + transformed hash。`hash-order/v0` 根据版本、seed、source ref 和候选 kind/args 排序，不读取标签/预测。main 与 position_and_id 重新分配 a0/a1；position_only 保留原 ID。少量 controls 使用固定一次循环移位，保存 original/transformed hash、顺序与原 ID→局部 ID 双射，映射 acceptable/preferred/judgments/candidate-error refs。报告通过反向映射比较动作身份；不把局部 ID 当语义，不新增 Runtime observation_id、run 或执行 authority。

Split 默认 50/25/25 的确定性 hash assignment，显式 related refs 合并 family，used_for_tuning 仅 development。可通过模块函数 overrides 调整小样本覆盖。旧 assignments/fingerprints保留；新增数据生成新的 unlocked manifest，旧 locked 文件不覆盖。Exact duplicate 忽略 action ID/顺序后跨 split 阻断，文本/模板相似度只产生待人工审阅项。显式 false-positive 理由才解除近似阻断；不会自动推断 family authority。锁定前必须检查全部样本质量和 leakage。

运行（输出目录必须尚不存在）：

```sh
venv310/bin/python -m evaluation.policy_dataset_v0 validate --output /tmp/texa-policy-validate-v0
venv310/bin/python -m evaluation.policy_dataset_v0 split --output /tmp/texa-policy-split-v0
venv310/bin/python -m evaluation.policy_dataset_v0 evaluate --output /tmp/texa-policy-eval-v0
venv310/bin/python -m evaluation.policy_dataset_v0 report --output /tmp/texa-policy-report-v0 \
  --control-family multi --control-family lexical --control-family optional
```

默认读取固定 `evaluation/fixtures/policy_dataset_v0`；`--dataset` 指定另一个离线目录。四个入口都严格校验并输出 round-trip samples、quality 和 split；evaluate 另写 predictions/transforms，report 再聚合报告。`--previous-split` 复用 assignments；`--seed` 固定切分与 hash-order 版本参数。所有写入限制在调用者指定的新输出目录，已有目录/文件拒绝覆盖，输入文件不修改。`--lock` 需真实完成锁定门槛，随包 fixtures 未完成该门槛，命令会拒绝且不创建输出目录。

Rule 多候选只接 Observation 副本；零候选只记录 Runtime route，单候选 forced；schema 损坏在读入时拒绝，可由 validator 单独诊断。原始 malformed、unknown、timeout、exception 分开保留；membership_only 不代表生产 stale/precondition 校验。Diagnostics 可运行观察规则行为，但不计选择分母。默认 teacher 是 disabled/not_run；接口不导入模型/provider、读取凭证或实现 transport。fake 仅在测试中定义，使用同样输入/strict parser，不修复、不 fallback。

报告按 data quality、candidate generation、selection、forced/Runtime-only、ordering、teacher、E2E 分开；百分比同时有 numerator/denominator，零分母 value=null、display=N/A。main 为唯一主分母，original/controls 不重复加权。报告显示原始/去排序线索的位置分布和 acceptable 状态变化，不宣称统计独立。teacher 缺失不计 accuracy/disagreement；缺 E2E 明确 not_evaluated。独立 ExecutionRecord 仅通过模块 API 接收已执行且有独立验收依据的任务；task 按 ref 去重，offline_stub 显式单列。原 rejected/fallback attempted/accepted/executed 与任务验收分开，不由 completed 或事件缺失推断。

固定 fixtures 为 18 个样本/15 个 family，含 2 个候选故障注入、2 个信息不足、2 个合法零候选；损坏 Observation 另存 `invalid-sample.json` 用于拒绝测试。未生成大规模数据，未导入用户记录，未接 teacher/ModelPolicy/训练。位置 controls 只应用三个指定 family。真实答案模型及 E2E 不可由这些示例评估。


## 2026-10-08 V0.1 源码基准切换

当前默认源码基准已在用户要求审阅后切换至 `runtime-source/v0.1`，审阅及版本身份见 [V0.1 报告](../validation/runtime-policy-evaluation-dataset-v0_1/README.md)。本文此前固定八项 pins/旧默认路径的描述保留为 V0 历史；当前以 `evaluation/policy_dataset_v0/baseline.py` 的十一项 Runtime 源码加 canonical-tools pins、V0.1 source-manifest 及 `evaluation/fixtures/policy_dataset_v0_1` 为准。

V0 JSON/action_id/label policy 格式未改变；输入 manifest 仍不能自行批准新源码，源码漂移仍拒绝。旧 gold/样本文件和 V0 pins/manifest 未覆盖，新版 source 审阅不提升 fixture 为人工 locked gold，也不启用付费或线上模型。
