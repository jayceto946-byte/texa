# Texa 业务链路独立工程审计

日期：2026-10-05，Asia/Shanghai。范围：当前工作树，非仅 HEAD。结论：**当前不能放行“真实教材学习全闭环已验收”**。这不是所有功能不可用；已存在可靠的隔离存储、任务栅栏和候选发布设计，但证据覆盖、答案发布及生成错误诊断之间仍有断点。

执行入口：[验证矩阵](business-chain-validation-matrix-2026-10-05.md)、[分包执行手册](business-chain-execution-runbook-2026-10-05.md)。本轮只新增审计文档和隔离验证脚本，没有修业务源码、改金标、运行付费模型、重启桌面或修改正式资产。

## 1. 证据等级与本轮实际执行

- **当前复现**：使用 Python 3.10.21，在临时数据根运行生产函数；网络连接被禁止；输入为明确标记的合成样例。见 [audit_probes.py](validation/business-chain-audit-2026-10-05/audit_probes.py) 与 [audit-probes.json](validation/business-chain-audit-2026-10-05/audit-probes.json)。这些是缺陷见证，不是线上模型准确率评测。
- **当前磁盘核对**：桌面数据 manifest 仍为 index `c8b6947edb7858f2` / Canonical `89dd1ed5d647ad563a49fe6c132ed7ebff8f34e6ff8c3b91d185c9625603dda3`，1826 文本 chunks、2489 catalog 条目；例题门槛仍为 `not_applicable`、source_units=0。读取没有初始化 Chroma 或打开正式数据库。见 [inventory.json](validation/business-chain-audit-2026-10-05/inventory.json)。ready 字段是历史结果，不是本轮健康检查；未确认运行中进程正在使用此版本。
- **当前既有测试**：core 148 passed；assets 66 passed；runtime 78 passed；Policy Dataset 128 passed / 20 failed。分组不重复，共 420 passed / 20 failed；均为既有测试，不是新增业务通过数。[日志与入口](validation/business-chain-audit-2026-10-05/isolated_checks.py)。Policy 20 项失败与 source digest gate 阻断一致，不能当作 20 个已证实业务故障。
- **历史证据**：A/B/C、D/E/F/G 的真实语料与任务记录沿用已提供报告，明确标作历史；本轮未重新打开用户会话库、未重放真实模型响应。HEAD 为 `d36767f32690506b3697340bb6eaa948395dbcf0`，关键当前文件 hash 在 inventory 中，HEAD 不能代表工作树。
- **未验证**：真实 Planner 输出、完整混合向量检索、当前模型答案、原生 Electron 新一轮操作、安装包与 Windows。审查了桌面接线与恢复代码，不把源码阅读当作视觉验收。

优先级：P0 为资产破坏、越权执行或不可恢复的数据一致性事故；本轮没有新证实的 P0 事故。P1 为阻断学习或把不充分结论标为完成；P2 为诊断/发布治理缺口。P1 及未完成的强制发布门槛均阻塞相关发布声明。

## 2. 错误拒答：已确认与待定位项

### A01 / P1：同一问题在检索查询与支持度规则中有不同实体

位置：`graph/retrieval_node.py:131`、`:709`、`:1276`；`graph/planner.py:152`。定义检索 query 已识别“什么是 X”，support query 仍用原问句；`_extract_query_focus` 又独立猜主题，前置“什么是”进入实体。匹配到实体时也可能把“什么”留作焦点。

最小复现：运行 probe 的 `D02_focus`；“什么是电阻式传感器？”→主题“什么是电阻式传感器”，后置问句和“请解释…”→正确主题。历史生产词法对照已显示 0→9 条最终证据。影响不只 D02：句式、功能词、口语等价表达会改变 gate 输入；启用理解模型不能替代确定性修复。

遗漏原因：传感器回归测了“根据/关于”等前缀及分类，未把同一事实的前置/后置定义问法作为同组不变量；固定 intent/chapter 的词法对照也没有检查 Resolver→Planner→support 的字段一致性。

### A02 / P1：字面过滤把题号当参数，同时又把不同型号当作相同

位置：`graph/retrieval_node.py:1168`、`:1241`；`backend/api/exercises.py:632`。对所有拉丁串和两位整数逐片段做 substring 判断；这不是“精确型号”或“语义参数”校验。

当前复现：`16. 写出二阶测量系统的动态响应` 对方法片段为 false，去题号后 true；`型号PT100` 对 `型号PT1000` 为 true。前者造成误拒答，后者可放过错误型号。题中参数本来可能只在用户输入中，方法证据不必逐条重复参数，因此不能只删题号、继续要求每个方法 chunk 包含全部输入数值。

修复应区分题号/页码/公式标签、型号边界、已提供参数和待检索事实，并在任务/最终证据层组合支持；原始题干不变。遗漏原因：正向样例不含题首序号，负向样例不是相同型号前缀，且测试没有参数跨片段分布情形。

### A03 / P1：复杂 Planner 可以覆盖用户明确限定的章节

位置：`backend/api/chat.py:663`、`graph/planner.py:165`、`:265`、`graph/main_graph.py:503`。fast path 保留 state.target_chapters；LLM path 直接采用返回值，仅为空时 fallback，没有把用户授权范围与模型建议范围分开，也没有精确章节白名单校验。

当前复现：state 限定“第一章”，替身 Planner 返回已知“第二章”，plan_node 返回第二章。后续图合并该 update；检索只看到覆盖后的范围。已确认函数/接线缺陷，真实模型触发频率未知；不能声称历史 C04 就由此导致。

遗漏原因：此前检索对照固定正确章节、跳过 Planner；常见简单定义走 fast path。修复将用户/来源约束作为不可扩大的范围；模型只能在范围内选子集，无效返回保留安全范围并给诊断，不偷偷切章。

### C04 / 定位保留项：错误前提未获纠正，根因仍未知

历史反馈成立，但本轮材料没有足够的 case→request→最终证据→首答绑定，无法判定是 topic 误解析、Planner 漂移、反证未召回、gate 拒绝反证，还是模型拒答。**不得把 A01、A03 或“缺纠错提示词”直接认定为 C04 根因。**

执行矩阵 R08 用成对“正确事实问法 / 同对象错误前提 / 是否成立”重放；先检查反证能否进入最终 Pack，再看回答是否指出错误前提并给教材支持的纠正。查不到原 request 时只标历史个案无法精确重放，另建受控样例；不改写旧验收结果。

## 3. 缺证据、缺输入或公式错误仍可能假成功

### A04 / P1：支持度在裁剪前判定，最终模型可见证据失去必要事实

位置：`graph/retrieval_node.py:1199`，`graph/evidence_pack.py:129`、`:140`，`graph/generator.py:318`、`:434`。retrieval 先评估完整候选，Pack 再做章内数量、总字符和单条1800字符裁剪；生成路径没有按最终文本重新计算 required fact coverage。

当前复现：同一合成片段前部含对象、尾部含灵敏度定义；裁剪前 supported，最终 Pack 已没有“灵敏度”，状态仍沿用先前结果。现有检索探针有部分最终 Pack 检查，但不能覆盖任意问题的运行时裁剪损失。还需覆盖多书同名章节共享 chapter_counts、四条章内上限、跨页公式条件被剪掉等情况，后者本轮未另做业务实测。

修复在最终 Pack 上建立要点—证据映射；预算不足则明确 partial/missing，不靠盲目增大预算。保留裁剪后的可校验文本映射于本轮内存，不把正文写诊断日志。

### A05 / P1：生产形态的证据 ID 与正文没有接上引用支持验证

位置：`graph/evidence_pack.py:144`（items 为元数据、不含 text），`graph/generator.py:198`，`backend/services/answer_verification.py:87`、`:187`。原始 evidence_items 有 chunk_id/text 而无 E-id；sources 有 E-id 而无 text。`_source_texts` 无法 join 二者；`if source_id in source_texts` 使缺正文的有效 E-id 跳过相邻结论检查。

当前复现：用生产 build_evidence_pack→finalize_answer_verification，拿“压阻效应”的来源支持“霍尔效应由磁场引起”，得到 passed；手工 sources 加 text 后得到 failed。`tests/test_answer_verification.py:83` 正是后一种构造，解释了单测为什么通过而生产链路失效。影响主聊天及复用 generator 的 Runtime/Goal。修复以本轮 E-id 绑定**实际展示给模型的裁剪正文**；缺映射不得当已验证。

### A06 / P1：公式、分项和数值“验证”的强度与完成状态不匹配

位置：`backend/services/answer_verification.py:37`、`:173`、`:198`、`:217`；`graph/retrieval_node.py:1310`。一个已识别焦点会使函数提前返回，未识别的其他请求项被忽略；未编号多问通常只派生 answer/formula/citation。公式仅检查 LaTeX 存在及定界符；引用二字重叠/符号重叠不能证明等价。numeric 分支即使传了 tool_context_pack 也没有读取，精确数值始终 unverified，诚实但无法消费已有确定性核验结果。

当前复现：同时要求方程、灵敏度、固有频率、阻尼比、阶跃响应，只识别灵敏度；错误的 `$U=I/R$` 引用正确的 `$U=IR$`，仍 passed。该错误公式没有触发 numeric 条件，不能依靠数字分支补救。

要求：每个交付项分别有满足/缺失/不适用与依据；公式结构检查和数学等价/代入/单位检查分开。无法确定数学正确性时应 unverified，而不是把结构 passed 汇总成数学已验证。成功工具结果仍须绑定本题最终结论、参数和操作，不凭“工具成功”放行。

### A07 / P1：习题生成并未复用完整主聊天合同

位置：`backend/api/exercises.py:616–667`、`:677–703`、`:739`；`frontend/src/features/exercises/hooks/useExerciseAnswerJob.ts:61`。Router 内直接 retrieve→私有 prompt→get_llm.invoke→sanitize→非空成功，缺任务输入门槛、逐项 required outputs、引用后处理和后置验证；Job 把 success 映射成 completed。来源输出仅章/标题/页/角色，缺稳定 chunk/index 身份；evidence_count 取裁剪前条数，可能与最终 Pack 不同。

当前复现：合成题“根据附表计算输出电压”，没有附表，替身返回任意数值，接口 success=true，无 verification。该 witness 证明边界缺失，不代表真实模型一定如此回答。已有 job test 把 generate_exercise_answer 整体换成 success 替身，无法发现问题。

保存需要明确点击，当前没有自动写正式答案，这一安全边界应保留。将编排收进应用服务、接现有验证和输入合同即可，先不迁移库或创建第二套 Agent。另需修复异常 `str(exc)` 回显/写 Job（`:667`、`:702`）；通过合成含敏感标记的异常测试，不要使用真实密钥验证。并发创建 job 的查重与创建未在同一临界区，列为需故障注入确认的风险，不把它写成已发生重复付费事故。

### A08 / P1：Notes 同时缺可诊断结构错误与 LaTeX 转义完整性门槛

位置：`backend/services/session_notes/generation.py:13`、`:61–95`，`validation.py:68–89`，`jobs.py:45`；`frontend/src/features/notes/DraftWorkspace.tsx:77`。

历史 F01 三次 invalid_document、同一完整 turn 冻结来源均保留；具体返回已丢失，根因只能停在解析/结构合同阶段。当前模型调用丢弃 finish_reason/usage；多种 JSON/类型/长度错误折叠为一个代码。提示词未明确 JSON 中 LaTeX 双转义、字段长度等完整规则，不能保证输出符合校验器。

本轮新复现：正确 JSON `\\frac` 保留公式；JSON 中单反斜杠 `\frac` 被解析为 form-feed + `rac`，validate_document 仍接受；`\alpha` 则报 invalid_document。前者是**静默损坏**而非网络失败。不能通过宽松 JSON“修复”或删非法字段来放行；拒绝损坏的控制字符/公式，错误分类不保存模型原文；使用明确合法公式 JSON 样例及统一合同。

冻结来源读取在 `backend/conversation_memory.py:970` 的单 SQLite 快照；Notes candidate→complete CAS→publish 及 reconcile 不重跑付费调用（`jobs.py:39`、`:60`），本轮相关隔离测试通过。应保留这些设计，允许用户从同一来源重试、手动整理、编辑、显式保存；遵守当前 article-v4 允许适度补充的产品边界，不能恢复已废弃的逐句来源强制或警告勾选要求。

## 4. 资产版本、诊断及发布门槛

### A09 / P1：代码修好不等于正式教材与安装包已更新

当前磁盘 manifest 的例题类别仍为零探针放行；历史源端已清点14例、第一章6例。当前摄取代码新增只读学习单元、目录、图组与探针，不会反向更新旧 IR/索引报告。正式版本仍不能继承新候选结论。OCR 可疑块仅有历史信号，缺原页比对不能宣布 OCR 正确，也不能自动删源。

位置：`ingestion/acceptance_probes.py:229`，`ingestion/document_publication.py:21`，`desktop/main.cjs:849`、`desktop/package.json` extraResources。应绑定工作树 hash、frontend/dist、打包后端、运行端点、角色/提示词及 active index。当前安装包与运行进程身份未检查，Windows 未验证。候选的源端清点要有独立人工样本，不能解析器和 probe 共用同一漏识别规则后互相证明。

### A10 / P2，但发布阻塞：冻结 Policy 先验校验阻止行为评测

位置：`evaluation/policy_dataset_v0/validation.py:40–81`。实际差异是 policy/router 传递 question_understanding，projection 添加已接受理解提示；默认 off 的无提示路径可能等价，但不能仅凭阅读假定完全无行为差异。20 项测试在 source gate 提前退出，因而后面的 scope/schema 等断言没有执行到。

两条独立轨道：保留旧 fixture、金标和原 hash，冻结当前候选并审阅源码/注册表变化；同时为 off、shadow、fallback 跑当前行为不变量和旧/新 Observation→candidate→decision 差异。审阅批准后以新版本追加 manifest 和合法裁决记录，不能直接改 hash 让旧基线自称通过。候选行为通过不能替代基线批准，基线批准也不能证明业务行为正确。

### A11 / P2：诊断信息一处过少、一处可能过多

Notes 丢失结构字段路径，而 `backend/rag_trace.py:201` 会保存问题前1000字（短问题即完整正文），`:204` 保存异常文本前2000字；脱敏正则不等于无正文。习题原始异常也可进入持久 Job。按本次审计约束，新诊断只记录阶段、固定 reason、长度、路径、hash、版本及计数；正文保留于权限受控的原业务资产，审计记录只引用其身份。不要为诊断 F01 在日志中保存完整返回、对话或教材；旧日志的处理另行评估，不在本轮删除。

## 5. 已有可靠边界及未通过的范围

| 链路 | 当前代码/隔离证据 | 仍需业务验证 |
|---|---|---|
| 首次配置、Electron路径 | main 将独立 userData 的 DATA_DIR/ENV_PATH 传后端；历史开发版有启动证明 | 当前 dev/dist/安装包同一版本、角色凭证、离线嵌入与重启定位 |
| Canonical/候选发布 | staging、retained rollback、资产发布及相关66项测试通过 | 完整真书候选的新例题门槛、原页语义与跨进程硬终止 |
| Notes 来源/保存 | 权威事件库快照、CAS、candidate receipt、取消/重启/备份测试 | F01真实输出、公式渲染及同来源成功草稿→重启定位 |
| 作答→错题→复习 | PracticeAnswerService 幂等作答、稳定关联、失败局部返回；MistakeLifecycle测试 | F04重复/恢复余项；旧单题 /practice 无请求幂等键，需要核对是否仍有UI调用，不外推会话模式结论 |
| Goal/定时/审批 | goal origin独立，Runtime 6工具/8模型预算、scope check、写确认与unknown阻断；runtime78项通过 | 真实桌面确认、定时触发、关闭栅栏、与共享答案门槛A04–A06联验 |
| SSE/停止恢复 | 请求序号、生命周期合并、后端interrupt确认、run fence及相关测试 | E01–E04仍未原生验收；恢复流与切会话/双击/迟到事件联验 |
| F05概念/聚合 | 辅助故障隔离已有测试，KG可用性不应成为正文前置 | 原受阻原因未知，需区分未抽取/失败/失联/空数据 |
| G01–G04 | 保留历史通过，本輪有部分持久化合同复验 | 不扩大为所有故障/平台通过；修改后需副本备份恢复业务回归 |

## 6. 实施顺序与放行判断

按手册 W0→W1→W2→W3→W4→W5→W6 执行：先固定版本与无正文诊断，修确定性实体/数字/范围，补最终 Pack 与答案验证接线，处理 Notes 合同，再收口习题服务，最后真书候选/Policy审阅及真实模型/Electron闭环。

不能发布的声明包括：“模型准确率已验收”“F01已修复”“第16题完整可解”“E全通过”“例题索引已更新”“安装包与当前工作树相同”。修复前的通过日志仅代表其自身样本与层次；强制门槛未跑记 not_run，数据不足记 blocked，确实没有来源结构且有独立清点才记 not_applicable。

完成标准不是测试数量：一个真实学习场景走完导入→问答→追问/纠正→笔记明确保存→校对习题→作答→错题→复习→重启后来源定位；另过多书、缺输入及故障恢复场景。每条分别评价流程可达、事实覆盖、公式数值与引用支持、持久化一致性。任何关键项不通过都不能被总体分数抵消。
