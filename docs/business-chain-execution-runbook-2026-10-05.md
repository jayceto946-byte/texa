# Texa 审计后分包执行手册

配套：[审计报告](business-chain-audit-2026-10-05.md)、[用例矩阵与完成标准](business-chain-validation-matrix-2026-10-05.md)。本轮仅审计；以下业务改动、真实模型及桌面验收尚未执行。工作包不要求清空数据、重装依赖、重新OCR或先迁移数据库。

## 0. 可立即重跑的审计证据

在仓库根目录，Python必须是venv310/3.10。下面脚本自行创建临时DATA_DIR等路径、跳过真实.env、禁止socket连接；不打开正式数据库、不加载真实向量库，不启用付费模型。日志含合成测试内容，仍需检查后再提交。脚本覆盖本目录同名审计结果，需保留旧结果时先复制到新的本地RUN目录。

```sh
venv310/bin/python docs/validation/business-chain-audit-2026-10-05/audit_probes.py
venv310/bin/python docs/validation/business-chain-audit-2026-10-05/isolated_checks.py core
venv310/bin/python docs/validation/business-chain-audit-2026-10-05/isolated_checks.py assets
venv310/bin/python docs/validation/business-chain-audit-2026-10-05/isolated_checks.py runtime
venv310/bin/python docs/validation/business-chain-audit-2026-10-05/isolated_checks.py policy
```

现状：core148、assets66、runtime78通过，policy128通过/20失败。probe退出0表示见证脚本执行完，不代表缺陷修好了。发布CI必须使用下面新增的**期望行为断言**，不能把probe的进程成功当门槛。

## W0 / 固定输入、运行身份与脱敏诊断（先决条件）

责任边界：`desktop/main.cjs`/`runtime.cjs`（运行身份）、`backend/rag_trace.py`/`runtime_events.py`（遥测）、`session_notes/generation.py`/`jobs.py`（生成诊断）、`backend/api/exercises.py`（异常映射）。

1. 保存工作树差异与各文件hash，不reset、不stash/清理用户改动；若需要隔离代码验证，复制当前工作树而非仅checkout HEAD。记录frontend/dist hash与后端运行代码，先不build覆盖正在使用的dist。确认没有活跃业务任务后再由用户安排正式应用重启，本轮不替用户中断。
2. 在 `/private/tmp/texa-business-<唯一ID>/` 建RUN并写所有权标记，DATA_DIR/PROGRESS_PATH/VECTOR_DB_PATH/BOOKS_PATH/CHAPTERS_PATH/IMAGES_PATH/MINERU_OUTPUT_PATH/ENV_PATH均指向RUN。正式数据副本通过现有一致备份/恢复能力创建；若用户未授权停止正式应用，只做支持的在线SQLite backup，不裸拷运行中的db+wal声称一致；需要跨库一致点则先停止或fence写入并批准窗口。故障只注入副本。
3. `I01–I03,V01`先检查健康端点/启动日志的instance_id、端口、isPackaged、appPath、Python3.10、前端资源、数据根及角色名；比对manifest、canonical hash、active map和lexical版本。禁止打印.env、凭据槽内容或完整profile。
4. 统一诊断元数据：case/request/task/turn/run/job/op关联、phase、reason枚举、错误字段路径、输入/输出长度、finish_reason、token usage、提示词/规则/模型版本、每阶段候选数量及最终要点缺口ID。Notes结构/JSON/来源/截断/网络/超时/收据失败分开；finish_reason不提供时记录unknown，不猜截断。
5. 删除**新诊断写入路径**对完整问题/异常正文的依赖：question用hash/长度，外部异常映射固定码。源正文继续在现有受控业务存储中，日志仅引用ID；不删除历史日志或资产。O01合成敏感标记必须零泄漏。

回归：core+runtime与O01；无数据库迁移，仅使用现有元数据字段或内存结构。若落地诊断确需新schema，先出迁移脚本、真实副本dry-run与整库回退方案，再审批；不可静默扩展本包。

## W1 / 确定性语义与范围（A01–A03）

文件：`backend/services/resolver_reference.py`、`session_context.py`、`graph/question_understanding.py`、`graph/planner.py`、`graph/retrieval_node.py`。API只传授权范围，不承担解析规则。

实施合同：在现有解析输出内增加/复用一份有界的实体区间、问题维度、编号/字面量角色投影；保留原question与resolved_query，检索query、支持度和required outputs消费同一已验证投影。理解接口保持off；shadow无行为变化，fallback不重写事实条件。简单确定性定义处理前置/后置/口语，不给每个故障另写独立黑名单。

明确范围来源：用户指定chapter/来源单元是硬约束，Planner只能选授权子集；未指定时才可在当前书允许列表中选择；非法JSON/类型/章名保留安全范围并降级。不得因主书优先级扩大用户所选参考书范围。

数字处理：只投影明确题首编号/来源标签，歧义不删；型号使用边界匹配；已知数值属于问题条件，检索的是方法/关系，不能逐chunk强制重复所有条件。最终求值校验仍严格保留这些参数。

最小新增断言（在现有文件扩展，名字是待新增测试，不宣称已存在）：

- `test_sensor_refusal_regressions.py`：3定义问法主题一致、口语变体、错误对象仍失败；PT100不匹配PT1000。
- `test_textbook_retrieval_policy.py`：限定第一章，替身Planner返回第二章/未知章/空/数组类型错误，最终范围不扩大；跨book/版本负向。
- `test_exercise_bank.py`或新的纯投影测试：题号16/17/100与无题号方法证据一致；16V/100Ω仍完整进入参数合同，编号和公式标签不混淆。

运行core、相关retrieval policy测试；R01–R04在L0通过后，使用B的真实混合检索跑L1，再授权L2。停止：负向边界回归、理解off产生调用、原题正文被改写。回滚只撤本包代码patch，保留用户原工作树和全部数据。

## W2 / 最终证据与答案发布（A04–A06，阻断最高）

文件：`graph/evidence_pack.py`、`generator.py`、`retrieval_node.py`、`backend/services/answer_verification.py`、`agent_runtime/multi_step.py`及主聊天任务状态映射。

实施合同：

1. Pack内部返回本轮E-id→chunk/version→**裁剪后正文**映射，与给模型的实际字符串同源；该映射只用于运行时校验，不随来源元数据写诊断。先选满足必需事实的最小完整单元，再按预算选择其他材料；不能把原始完整chunk尾部当作模型见过的证据。
2. 对最终Pack重新核对要点覆盖，状态从最终结果得出；数量/字符/章限导致事实丢失时保留明确缺口，不能沿用裁剪前supported。不能把书中本来存在但本轮未召回的事实算支持。
3. required outputs逐项表达问题交付，涵盖无编号多问、比较两对象、列举完整性、条件及跨章节支持；格式/词面锚只作线索，不能声明语义正确。
4. 引用逐出现位置核对当前E-id合法性、正文可用性及对应结论；没有正文不得跳过并通过。数字/公式/单位按可执行白名单校验并绑定最终结论；纯结构公式检查只命名结构通过，无法证明等价则数学状态unverified。
5. 已有math工具结果通过query/参数/operation与答案结论对齐后才能消费，失败/不同题收据不得放行。多项输出只完成一项则degraded，正向完整解答不因诚实降级而算验收通过。

最小新增断言：把probe中的生产Pack错误引用、尾部裁剪、U=I/R、未编号多问转换为预期失败/降级测试；另有正确欧姆定律、等价公式、正确参数计算正例，防“全部拒答”假修复。加入同一E-id两处冲突、一条支持句被裁剪、两书同名章节、多来源组合支持用例。

命令：core；`tests/test_textbook_retrieval_policy.py`、`test_citation_pipeline.py`、`test_answer_verification.py`、`test_agent_runtime_chat_binding.py`、`test_goal_execution.py`（均使用W0隔离环境）。L1覆盖七类及最终Pack，而不只top-k。停止：改阈值掩盖缺口、新增任意Python数学求值、日志出现正文、已支持问题全部拒答。回滚为代码包回退；不需要改正式索引。

## W3 / Notes生成合同与可恢复编辑（A08）

文件：`backend/services/session_notes/{generation,validation,jobs,service}.py`，`llm`角色工厂（仅已有能力），`frontend/src/features/notes/DraftWorkspace.tsx`及editor hook。

先生成一个服务端合同对象，同时用于提示词与校验说明：块类型/字段/长度、合法章节token、source/evidence token隶属和合法JSON-LaTeX样例；正常`\\frac`、矩阵`\\begin`要有最小示例。不要求模型提供未发送的chapter_ref_id，未关联可空。

保留finish_reason/usage/内容类型安全信封；只支持已声明文本内容块抽取、完整围栏去除等无语义转换。禁止补截断JSON、删除未知来源、自动再调模型修JSON。解码后公式控制字符/损坏转义给字段级错误；不要全局替换反斜杠误伤合法文本。结构化输出能力只有registry/transport声明且验证过才能使用，不在Notes业务中硬编码供应商。

保持candidate→completion CAS→publish顺序，保留全部cancel/restart测试；生成失败来源和手动编辑入口不丢；CAS冲突保留本地文字；保存不要求新增警告勾选、不把正式保存升级为数学已验证。

最小命令：core（包含session_notes）；新增N02完整错误表与N03控制字符负例，已有合法补充笔记仍可保存。L3在三个尺寸看失败/重试/手动/保存/重启，L2在小额授权阶段包含F01同源。F01再失败时依新分类定位，不默认加上下文/自动重试。回滚不删除Notes库/版本/冻结快照；schema改变需另批。

## W4 / 习题答案接服务与学习闭环（A07）

文件：`backend/api/exercises.py`只留DTO/Job调用/错误映射；新增或扩展`backend/services`应用服务，复用W1/W2输入、来源、Pack、生成与验证；`features/exercises/hooks/useExerciseAnswerJob.ts`消费真实状态；`exercise_practice.py`、`memory/exercise_bank.py`、`memory/mistake_lifecycle.py`保留现有事务语义。

先从题目source unit/index/version定位完整题干及附图表，再检索同范围方法；并不要求来源chunk自带答案。不满足关键输入时返回waiting，服务返回的草稿附verification、缺失输出和实际Pack来源ID；Job完成只代表草稿生成结束，不能展示“已核实标准答案”。保存仍需显式动作；用户手填不能自动算机器已核验。

并发创建Job在同一原子查重/创建边界中完成；明确重试尝试与重复提交。草稿恢复/切题处理绑定exercise/job，旧响应不得覆盖新题。先核对旧`/practice`是否仍被UI调用，再决定接现有幂等服务；不要只因有旧接口就宣称F04已发生重复。

命令：core、runtime；扩展X02缺表也“非空成功”负例、X03并发双请求、X04跨库部分失败重试、X05SM-2重复确认；L3完整做一题校对→生成→编辑保存→作答→错题→复习→重启。数学/事实验收独立于写入成功，F05需先查实际状态而不是自动抽KG。回滚应用代码，资产保留；必要迁移另批。

## W5 / 真书候选、Policy双轨审阅和恢复

### 教材候选

在C中从原始structured生成IR/report/probes，不在B原文件上补字段。复用`ingestion/document_workflows.py`、`document_publication.py`、`vector_store.py`现有发布能力；API/UI进入I04正常导入，可选概念关闭。无需重跑MinerU服务。

I06–I10验收：独立源清点→Canonical→chunk→生产混合检索→最终Pack；14例和首章6例、例1.3表与解、a/b成员、页码/heading身份逐项。比对本轮结构门槛、OCR审阅、事实gold，三者不互相冒充。

先在隔离根完成激活/回滚/故障恢复。正式切换前给用户具体候选版本/hash、旧版retained路径、质量差分、失败清理结果、回滚实测与预计中断窗口，再请求批准。未批准正式切换不妨碍继续全部副本工作；不能把副本成功标正式已生效。原页缺失的OCR判定仍待审。

### Policy基线和行为

保留原fixture六文件、原source-manifest和approved常量；当前policy检查失败应原样保留。对三处当前源码差异出审阅记录：off无hint、shadow不改变投影、fallback只补只读候选；对请求约束、候选集、绑定、预算、approval/unknown写结果分别比较。

最小行为集合：已有六fixture全量加每个理解模式下empty候选、非法entity span、quiz只读提案、显式写请求、scope变化、missing input、预算耗尽、重复确认。固定输入与registry，在当前函数上取Observation/decision/binding；与旧版在隔离代码副本的同输入结果比较。新候选仅作为新版本材料，旧金标不可就地修改。差异有合理理由也需人工签审；审核后新增有版本的manifest/labels/report，保留旧报告及哈希。

命令：assets、runtime、policy。要点是冻结门槛重新合规运行且行为验收通过，不能靠“20失败都是hash”免除发布门槛。发生迁移/正式激活/恢复覆盖均须按具体方案审批；不要求用户批准一般读操作与隔离回归。

## W6 / 真实模型与原生Electron验收

### 付费/发送范围授权包（本轮未授权，不运行）

拟发送：74个短问题中的当前问题、至多2相关历史turn/必要摘要、最终选中教材片段、经明确选择的图片；80轮会话每次仍只发送有界ContextPack；6份笔记冻结选区；3道人工校正题及必要图表；4个用户确认Goal的契约/受控工具结果。**不发送完整数据库、整本教材、profile、密钥或原始全会话历史。** 若某问题确需整页图片，单列该页与目的。

建议分两级，用户可调整，不默认为已授权：

- 烟测：从完整集合中固定12操作（D02两问法、分类/比较、错误前提、缺输入、计算、第16题、F01及其他笔记、恢复相关题），最多40次provider请求、费用上限人民币20元，零自动重试。失败立即按reason定位，不把12操作全量重跑当修复。
- 完整：74短问答+80连续轮+6笔记+3习题+4Goal，共167业务操作；烟测中重复样例不再新增分母。预算上界按每QA最多Planner+Answer、每Notes最多8+1、每Goal最多8加契约整理，最多420次provider请求，累计费用不超过人民币200元（包含烟测），零自动重试。实际触发额外角色/视觉/工具模型会消耗同一总上限；不允许后台KG或理解接口偷偷占额外预算。

这些金额是建议的硬上限，不是当前模型价格估算。执行前按用户选定供应商官方价格、冻结模型、输入/输出token上限算出最坏费用；超过金额上限先缩小批次或申请新预算，不靠实际usage事后发现超额。当前`get_llm`默认max_retries=2，真实验收必须通过角色工厂/transport显式置0且逐请求计数，不能仅靠文档声明“零重试”；配置好硬停止后才可开始。供应商未知计费、无法限制单次输出或无法监控请求时先blocked，不调用。真实发送/费用授权须由用户明确给出。

### 三个独立门槛

1. **离线L0/L1**：W1–W5完成，矩阵的范围/缺输入/写幂等负例全过，真书最终Pack要点人工签审；真实向量召回和纯词法结果分列。
2. **真实模型L2**：按矩阵冻结样例、每次首次输出不替换；人工逐项审阅事实、公式、单位、前提纠正及引用；原生模型错误/拒答单列，不以offline answer snapshot替代。Context Eval v3 CLI支持`--online --confirm-paid-model`，但旗标不等于人类授权；其默认dataset也不自动包含上述业务样例。
3. **Electron L3**：macOS dev及当前候选包分别执行J01–J04与三个尺寸。用实际文件选择、发送、停止、保存、复习、重启和来源点击；托管API成功不能代替GUI操作。Windows无主机明确not_run。发布必须针对实际验证包hash，不能沿用10月3日旧包通过记录。

前端或桌面代码有改动时，已有命令：

```sh
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix desktop test
npm --prefix desktop run check
```

build会更新dist，必须在当前验证代码副本执行或确认不会改变用户运行中的桌面资源。桌面测试回环端口若被sandbox拒绝，记环境阻塞；不要将其记业务失败或暗中关测试。实际dev启动使用 `KAOYAN_USER_DATA_DIR="$RUN/user-data" npm --prefix desktop run dev`，且先核对desktop/runtime的路径解析；启动日志必须证明后端在RUN。安装候选用同样独立userData启动，资源由实际包提供。禁止直接用正式root测试。

## 新故障处理、停止条件与回滚

发现失败后固定case/variant/版本，保留首次状态；依次比较Resolver、Planner范围、输入合同、召回、过滤、最终Pack、模型输出分类、验证、SSE、持久化，找最早偏离点。每次只对已证实偏离写最小修复：新增一个失败见证、一个正常对照、一个负向边界；复跑该包及共享服务所有调用方，再恢复纵向场景。不要用失败样本改金标、删分母或切通用模式。

立即停止相关运行：写到正式目录、预算/发送范围超限、敏感正文进入新日志、版本/索引错配、越书/越章、未知写仍继续、重复推进SM-2、资产丢失、旧run覆盖新run、错误公式/数值被标核验通过。保留副本/元数据，不继续污染后续样本；不因此自动中止无关的只读审计。

代码回滚只逆转本包patch，不使用`git reset --hard`/`git clean`；正式索引切换失败先fence写入，按已批准retained版本同时恢复map/lexical/IR/资产并跑I10。学习库恢复到新隔离根先过G05，之后才在获批窗口替换正式根。Schema变更时恢复整套一致备份，不让旧应用写新schema。所有删除限本次带所有权标记的临时目录，失败副本待诊断结束才清理。

最终发布单列：代码/包身份、数据/索引版本、L0/L1/L2/L3结果、四纵向场景的四维结论、人工签审、未验证平台/样例、故障与回滚证据。未完成项为not_run/blocked，不能从测试数量或历史G通过推成全链路通过。
