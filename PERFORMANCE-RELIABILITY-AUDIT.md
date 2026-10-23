# Texa 全栈性能与可靠性审计

日期：2026-10-23（Asia/Shanghai）。审计起点：`Texa_MacOS`，HEAD `140255ad180b8076c830e5600ca4297942eee105`，另有 12 个既有修改文件。审计对象是当时的**实际工作树**，不能把 HEAD 单独当作全部运行代码。未提交、合并、推送或发布。

## 结论与计数

| 优先级 | 发现 | 本轮修复 | 未解决 |
|---|---:|---:|---:|
| P0 | 0 | 0 | 0 |
| P1 | 3 | 3 | 0 |
| P2 | 9 | 5 | 4 |
| P3 | 2 | 0 | 2 |
| 合计 | 14 | 8 | 6 |

已修复：会话分页串线、工具失败布尔值被误认为满足、SSE 阻塞事件循环、两类学习资产库连接释放、词法检索重复计算、过时的原生工具协议测试、macOS Embedding 基准 RSS 单位错误，以及发布前端资源隔离（AUD-09 后续修复）。没有发现已证实的 P0；这不等同于证明不存在安全漏洞或数据损坏路径。

**当前不满足“全部发布验证通过”条件。**AUD-09 后续工作树补跑为2166 passed / 3 failed；另将暂存源码导出，31项定点后端、249项前端、lint/build及真实Electron12项通过（见后续提交验证与QA记录）。本轮审计自身最后一次全量为2139 passed / 4 failed：3个持续失败的冻结Policy合同测试（AUD-07），另1个来自既有搁置功能的取消测试，仅最后一轮失败，根因未判定且不在本轮修复范围。本轮没有发现未修复的已复现 P1，但不能据此签发生产发布许可：真实模型答案、正式教材人工覆盖、Windows/安装包升级、真实手机网络和长时间运行仍未重验。AUD-07 及本机批量 Embedding 吞吐未达现有门槛（AUD-14）是明确的验证门槛阻断，不能把它表述为已证实的线上崩溃。

## 范围、方法与基线

阅读项目与前端 README、AGENTS、统一 development handoff、Semantic Runtime/Evidence/Context 设计、Runtime 状态说明、移动 Remote 文档、pytest/npm/Vite 配置，并沿当前实现检查以下边界。历史设计和历史测试报告仅作为导航，不继承其“通过”结论；Runtime 旧状态文档中的默认关闭描述也不能代替当前原生数学/回答分流代码。

| 范围 | 当前实现与本轮核查 | 验证边界 |
|---|---|---|
| Electron / React | `desktop/main.cjs`、runtime/preload、React Context、`MainLayout` 保活路由、ChatPage/useChat、Markdown/MathLive 懒加载、教材读取缓存 | Electron 53 项测试；真实 macOS Electron 生产 renderer + 内存 HTTP 夹具；未运行打包端 |
| HTTP / Remote | `backend/main.py` 生命周期、同步 API 线程池入口、SSE、security、static_assets、remote_reads；同一后端经 Tailscale Serve、认证与配对供手机访问 | 本地安全/网络/压缩/恢复测试；没有真实 tailnet、蜂窝、手机锁屏验收 |
| 学习数据 | conversation append-only SQLite + 游标投影；独立 Notes/Goal/Focus/错题/习题存储；CAS、幂等和恢复 | 全量离线测试、真实临时 SQLite、事务提交/回滚/关闭故障见证；未访问正式学习数据 |
| 检索与摄取 | Canonical IR → 分块 → staged candidate → production retrieval/EvidencePack 门槛 → 激活；Chroma + lexical + KG + 邻接；ONNX singleton 与独立 ingestion session | 现有 IR/发布/向量范围/故障回退测试；合成 lexical 配对；本地 ONNX 与隔离 Chroma 基线；无正式索引重建 |
| Runtime / 模型 | 主聊天路由到既有 graph 或有限 SQL/native runtime；tool schema、owner/run fence、budget、验证、outbox、Goal 调度；ContextPack 与 EvidencePack 分离 | 离线模型替身、生产工具/SQL/协议回归、真实锁竞争；没有付费模型请求 |
| 日志 / 评测 | execution events、runtime_events、rag_trace、前端 performanceMetrics、Server-Timing、既有 embedding 与 Electron QA 脚本 | 复用机制；未引入监控服务。报告只含合成文本及运行统计 |

三个只读子代理曾按前端、存储、Runtime 分工，因额度限制提前终止；仅采纳主代理随后独立核实的发现，不把未完成分工作为已覆盖的证据。

基线：前端 **251 passed**；Electron 沙箱首次为端口监听 EPERM，允许临时回环监听后 **53 passed**；Python 3.10 **2131 passed / 4 failed**。优化后首轮全量 **2138 passed / 3 failed**；新增RSS回归后最终 **2139 passed / 4 failed**（含上述范围外搁置测试观察，详情见性能对照）；前端仍 **251 passed**，lint/build 通过。完整命令、样本与限制见 [性能对照](PERFORMANCE-BEFORE-AFTER.md)，修复与回滚见 [实施报告](OPTIMIZATION-IMPLEMENTATION-REPORT.md)。

证据分类：**R**＝本轮隔离条件下复现；**E**＝代码/产物支持，但未复现实际用户故障；**S**＝静态推测。优先级与证据等级分开，测试通过也不证明任意数学答案正确。

## 问题清单

| ID | 优先级 / 证据 | 问题 | 状态 |
|---|---|---|---|
| AUD-01 | P1 / R | 迟到历史分页污染或切回旧会话 | 已修复 |
| AUD-02 | P1 / R | 失败布尔后置条件被计为满足 | 已修复 |
| AUD-03 | P1 / R | SSE 同步锁/SQLite 阻塞 ASGI 事件循环 | 已修复 |
| AUD-04 | P2 / R | 错题和习题事务退出不确定性关闭连接 | 已修复 |
| AUD-05 | P2 / R | lexical 对相同标题重复计算查询特征 | 已修复 |
| AUD-06 | P2 / R | 原生协议测试把正确收据复用判为失败 | 已修复 |
| AUD-07 | P2 / R | 冻结 Policy 工具 schema 与生产不一致 | 保留失败，需版本化评审 |
| AUD-08 | P2 / E | 其他 SQLite 模块仍依赖 GC 关闭连接 | 待逐模块收口 |
| AUD-09 | P2 / R | 持续构建目录混入旧哈希资源，打包直接收录 | 已隔离发布构建；完整安装升级未验收 |
| AUD-10 | P2 / E | 笔记生成仅按 job 去重，缺全局并发准入 | 待调度方案 |
| AUD-11 | P3 / S | 流式消息使共享 Context 消费者重新渲染 | 待 profiler，不重构 |
| AUD-12 | P3 / E | 兼容工具软超时不终止底层线程 | 有容量界限，保留限制 |
| AUD-13 | P2 / R | Embedding 基准在 macOS 将 RSS 放大 1024 倍 | 已修复 |
| AUD-14 | P2 / R | 本机批量 Embedding 未达现有吞吐门槛 | 待受控调优 |

下述位置均为审计后工作树行号；修复前机制以见证日志及固定基线为准。

### AUD-01 — 历史分页跨会话竞态

- 位置：`frontend/src/pages/ChatPage.tsx:201`、`:1022`；`frontend/src/contexts/ChatContext.tsx:80`、`:154`、`:169`。
- 机制/触发：A 发出 earlier/later 请求，切到 B 后 A 才返回。原 earlier 直接向当前全局消息 prepend；原 later 用捕获的 A 消息调用 `loadConversation`，还会取消当前活动流。
- 证据：R，真实 Electron 夹具在 before 中分别记录 `contaminated=true`；later 还记录 `switchedBack=true`。见 `electron-before/results.json`。没有发现该路径本身直接改写持久化消息，不能宣称数据库已损坏。
- 用户影响：看错上下文，误回旧会话；可能中断用户当前问答。
- 修复：Context 提供同步捕获的会话读取版本；完整替换（含同 ID 重读）失效旧版本。分页检查身份并取消旧请求，后续页按当前消息去重合并，不重载整个会话；cursor 绑定会话 ID。
- 收益/不确定性：两种竞态均消除；不宣称会话切换更快。
- 风险：低至中，主要是同 ID 重读、分页去重和 loading 清理。
- 回归：相同延迟夹具前后对照；正常双向分页、重复消息、同会话重新定位均覆盖；三档窗口保持公式和布局。after 共 12 项通过。

### AUD-02 — False 被误算为有效 RequiredOutput

- 位置：`backend/services/tool_orchestration.py:47`、`:257`、`:343`。
- 机制/触发：`False not in (None, '', [], {})` 为真。计算成功后验证失败时，`verified_math` 仍进入 satisfied 列表，整个 pack 可能 `sufficient=True`。
- 证据：R，`witnesses-before.log` 的 stub registry 经真实编排器返回错误 `sufficient=True`；默认 `success=False` 也误算满足。数学数值 0 必须仍合法。
- 用户影响：工具完整性汇总不可信，可能给生成器错误的就绪信号。最终 `answer_verification` 另有绑定检查；**未证明最终错误答案因此被标 verified**。
- 修复：bool 明确按真假处理，其余值继续原空值语义；不改变工具次数、prompt、schema 或验证能力。
- 收益/不确定性：确定性合同修正，无速度或线上准确率收益声明。
- 风险：低；避免用通用 truthiness 错杀 0。
- 回归：失败验证/默认失败输出/数值 0，既有数学编排及答案验证；before 失败、after 通过。

### AUD-03 — SSE 竞争锁阻塞整个事件循环

- 位置：`backend/services/agent_runtime/chat_binding.py:346`、`:357`、`:367`；`backend/services/agent_runtime/store.py:126`、`:371`。
- 机制/触发：同步 producer 在 `stream_lock` 内预留 SQL seq；SQL writer 等待时锁仍被持有。原异步 events 直接 acquire 同一线程锁并同步读 SQLite，因此阻塞该 ASGI loop 的其他任务。SQLite busy timeout 可达 15 秒，但本轮没有实测 15 秒卡顿。
- 证据：R，真实临时 SQLite writer 持锁 300ms，生产 SSE + 替身执行器，5ms 心跳最大间隔 before 380.33ms、after 17.00ms。非真实模型端到端压测。
- 用户影响：竞争时其他设备请求、流式读取或取消确认可能延迟。
- 修复：用已有 AnyIO 有界线程池执行原来的原子 snapshot + queue drain；保留锁、cursor、排序、budget 和 owner fence。
- 收益/不确定性：实测事件循环响应改善；数据库竞争本身没有消失，线程池饱和仍可能排队。
- 风险：中，流顺序与关闭路径敏感；未改 Agent 决策、数据库结构或公共协议。
- 回归：线程身份断言、两段输出无丢失/乱序、现有停止恢复/断流/清理测试；流相关集合 93 passed。

### AUD-04 — 两类资产库连接依赖 GC

- 位置：`memory/mistake_book.py:144`；`memory/exercise_bank.py:121`。
- 机制/触发：`sqlite3.Connection.__exit__` 仅提交/回滚，原 `_connect` 返回连接，`with` 退出不关闭。频繁列表/作答、GC 延迟或外部持有引用时连接可持续占资源。
- 证据：R，退出后仍可执行 SQL；保留引用并关闭 GC 的 100 次事务，before 100 连接可用，after 0。此试验证明生命周期问题，**不证明正常 CPython 中无限泄漏或已经耗尽 FD**。
- 用户影响：不确定性释放、潜在文件句柄/WAL资源压力。
- 修复：两 store 的连接上下文在 `with conn` 提交/回滚后 `finally close`，初始化 pragma 异常也走 close。
- 收益/不确定性：资源确定释放；每次事务额外开关/WAL清理开销在本机约 0.2–0.3ms，非性能提速。
- 风险：低至中，已检查这两个私有连接入口的调用均使用上下文；不对其他 raw connection 工厂作全库替换。
- 回归：成功提交、异常回滚、重开读取、错题生命周期、习题、SQLite故障恢复；不更改表、索引或学习记录。

### AUD-05 — 同一检索重复计算标题与查询特征

- 位置：`ingestion/lexical_index.py:212`、`:238`、`:255`。
- 机制/触发：同一节的多个 chunk 重复执行 query/title tokenization、标题质量与 IDF，列举数量 query normalization 也原先逐 chunk 重算。
- 证据：R，600/3000 个合成片段、84 个重复标题、固定查询；9 轮交替执行旧/新算法，最终受控样本中位耗时下降 15.7%–26.3%。8 查询 × 2 范围 × 2 大小，共 32 个完整返回对象逐项相等。
- 用户影响：同范围 lexical CPU 开销降低；网络/模型占主导时整体改善可能很小。
- 修复：仅在本次 search 内复用标题特征，将查询计数特征移出循环；排序、得分公式、候选、章节过滤和元数据均保持。
- 收益/不确定性：上述微基准收益已测；真实教材、top-k事实覆盖与端到端收益未测。文档 tokenization 仍随正文总量线性，不宣称解决所有大书开销。
- 风险：低，缓存不跨请求，不增加失效/索引发布合同。
- 回归：固定 Git 基线精确比较 + 既有 lexical/表格/列表/范围/检索门槛测试；没有缩短证据、调小 k 或减少教学信息。

### AUD-06 — 原生工具协议测试忽略收据复用

- 位置：`tests/test_tool_calling_audit.py:29`、`:51`；生产依据 `backend/services/agent_runtime/native_loop.py:448`。
- 机制/触发：替身两次返回同一数学表达式，测试却期待两条物理工具执行。现有 Runtime 会复用同 run、相同绑定参数的成功收据。
- 证据：R，基线实际只有一条成功执行，仍消耗三次模型步骤；原断言失败。
- 用户影响：错误测试阻挡回归评估；不是用户功能故障，也不是本轮新增的工具去重收益。
- 修复：参数化“重复表达式”和“不同表达式”；分别要求 1/2 条实际执行，并检查两次 provider call ID 的 ToolMessage 配对、复用标记及不同计算的 27 结果。
- 收益/不确定性：测试与当前合同一致，同时增强协议覆盖；无生产速度收益。
- 风险：低，不改生产去重或预算，也不删除断言。
- 回归：native/protocol 42 passed，全量该失败消失。

### AUD-07 — 冻结 Policy 与当前教材工具 schema 漂移

- 位置：`backend/services/agent_runtime/textbook_tool.py:21`；`tests/test_policy_dataset_v0.py:546`、`tests/test_policy_seed_v0.py:470`、`tests/test_runtime_policy_v0.py:256`。
- 机制/触发：当前 `TextbookSearchInput` 增加 `continuation`，冻结 snapshot 仍只有 query/chapter，导致 schema/model_dump 和绑定误差门槛不一致。
- 证据：R，前后全量均有这 3 项失败；baseline 的 binding_errors 为 2。与本轮 lexical/SSE/连接修复无关。
- 用户影响：不能再用旧冻结评测证明当前 Runtime 合同通过；未证明生产教材查询失败。
- 方案：保留旧冻结版本；单独审阅 continuation 的范围/版本/预算合同，新增版本化 manifest、明确兼容适配及新评测基线，再决定是否启用 Policy。
- 收益/不确定性：恢复评测可信度，不承诺模型准确率。
- 风险：高于普通测试修正，涉及冻结合同和验收权威；本轮没有篡改 hash、金标或跳过测试。
- 回归：上述 3 项、新旧合同分离、越范围/旧索引/伪造 continuation 负例、原冻结可重现性。

### AUD-08 — 其他存储仍存在相同连接生命周期模式

- 位置：`backend/conversation_memory.py:71`、`backend/job_manager.py:349`、`memory/learning_events.py:52`、`backend/rag_trace.py:44`、`backend/services/answer_feedback.py:25`。
- 机制/触发：raw connection 工厂与 `with connection` 仍并存，依赖 GC；有些消费者（如 `backend/services/conversation_management.py:110`）需要 raw connection 并自行关闭，不能直接统一改为 generator contextmanager。
- 证据：E，直接代码/调用链支持；本轮只对 AUD-04 的两个库做资源数量对照，没有测这里的长期 FD/RSS 趋势。
- 用户影响：可能延迟释放会话、Job、trace 等资源；无已复现用户崩溃。
- 方案：逐模块区分 raw connection 所有权与事务上下文，先补关闭/回滚/错误路径测试；对调用点使用 closing 或提供明确 managed 入口，避免改全局 sqlite factory。
- 收益/不确定性：预计更确定的资源释放；延迟和 WAL checkpoint 成本需分别测量。
- 风险：中，会话管理有外部事务边界，本轮不做未经验证的全库 API 改造。
- 回归：append-only历史、并发追加、游标、Notes冻结来源、回收站栅栏、Job取消及强制异常路径。

### AUD-09 — 旧前端资源进入发布构建目录（后续已修复）

- 位置：`scripts/build-desktop-backend-macos.sh`、`scripts/build-desktop-backend.ps1`；`frontend/vite.config.ts` 保持原策略。
- 机制/触发：普通 Vite 构建通过 `emptyOutDir:false` 为已打开的手机页面保留旧 hash；原桌面打包复制整个累积的 `frontend/dist`。
- 原审计证据：本地 dist 112,717,031 bytes / 3,921 文件，独立干净输出约 42.84 MB / 395 文件；当时仅静态确认打包路径。
- 修复：macOS 每次用 `mktemp`、Windows 用 GUID 创建独立 staging，显式传给 Vite 的 `--outDir --emptyOutDir`，只将此目录映射到包内原有 `frontend/dist`。成功或正常失败均清理自身 staging，不清空服务目录、不修改运行时读取路径。
- 回归证据：实际 macOS 发布脚本在替身构建工具下连续两版仅收录当版资源，含空格路径、前端失败、后端失败及其他构建目录保护。旧 hash 经生产静态资源中间件仍返回 200。另以真实 Vite 连续两版及最小真实 PyInstaller 冻结程序验证，每版 395 文件 / 42,845,254 bytes，包内文件和 SHA-256 全部等于 staging，冻结探针启动通过；服务目录全量哈希不变。
- 收益/边界：已验证发布资源输入不受服务目录历史影响；不是完整后端或安装包体积对照。Windows 无本机 PowerShell，脚本已审阅但未执行；完整安装、升级、回滚及真实手机旧页面仍需平台验收。
- 证据与复现说明：`docs/qa/aud-09-release-2026-10-23/README.md`；回滚只需恢复两平台构建脚本，不涉及数据迁移。

### AUD-10 — 笔记生成缺全局并发准入

- 位置：`backend/services/session_notes/jobs.py:9`、`:21`、`:68`。
- 机制/触发：`_WORKERS` 去重同 job，不限制不同 draft/job 数量；每个新 job 启动 daemon thread，多设备并行触发可能叠加模型连接、CPU和内存。
- 证据：E，代码确认线程创建及单 job 去重；未制造真实付费请求，也未证明常见单用户操作已出现瓶颈。
- 用户影响：负载大时前台响应/模型费用竞争；理论上 Thread.start 失败还需要清理准入状态。
- 方案：先测峰值活跃 job，复用 Job queued/claim 设计有限准入和取消；给排队、重启、失败释放定义语义，不临时加入静默丢任务策略。
- 收益/不确定性：限制资源峰值，可能增加排队延迟；收益需多任务试验。
- 风险：中，涉及后台调度行为，不在本轮直接改变。
- 回归：多设备重复/独立提交、排队取消、启动线程失败、重启不重付费、候选发布 hash/CAS。

### AUD-11 — Context 流式更新可能扩大渲染范围

- 位置：`frontend/src/contexts/ChatContext.tsx:203`、`:232`；`frontend/src/pages/ChatPage.tsx:1014`；`frontend/src/hooks/useChat.ts:125`。
- 机制/触发：messages 与 scope/actions 同一 Context value，流式更新可能通知多个消费者；长会话对全部 messages 做 map。
- 证据：S，仅静态推测。已有 Markdown memo/lazy、历史40条分页及页面保活，不能据此说每个 token 都重新解析所有公式；本轮未采集 React commit profiler。
- 用户影响：长列表/快速 delta 下可能卡顿，未证实。
- 方案：先针对长公式、数百条已加载历史采集 render/commit 与 main-thread 时间，再决定批处理、Context拆分或窗口化。
- 收益/不确定性：未知；虚拟列表会影响阅读锚点、选区和来源定位。
- 风险：中至高，当前低收益证据不足，不重构。
- 回归：流式逐字/终止、历史锚点、复制、KaTeX、恢复及三档窗口。

### AUD-12 — 兼容工具软超时后后台工作可继续

- 位置：`backend/services/tool_orchestration.py:203`、`:206`、`:211`。
- 机制/触发：`queue.get(timeout)` 限制调用者等待时间，不能终止 Python daemon thread 中正在运行的 handler。
- 证据：E，代码明确；已存在 `_TOOL_SLOTS` 容量控制，运行完才释放，并非无限创建线程。受限数学另有进程隔离，不能混为一谈。
- 用户影响：慢 IO 可在主回答降级后继续占一个 slot；不是已证实的无限 Agent loop。
- 方案：仅在发现慢 handler 时传递 cooperative cancellation/客户端 deadline；对不支持取消的外部工作保留耗尽与降级回执，不泛化改为开放并行工具执行。
- 收益/不确定性：尾部资源占用可能下降；常规低延迟工具可能无收益。
- 风险：中，不能通过关闭失败检查、强杀共用线程或重复重试获得表面加速。
- 回归：超时后 slot 释放、耗尽拒绝、一次补偿预算、取消后的写操作不可执行。

### AUD-13 — macOS 内存基准单位错误

- 位置：`evaluation/embedding_backend/phase1_worker.py:90`；调用者 `scripts/benchmark_phase3_embedding.py:38`。
- 机制/触发：非 Windows 一律把 `ru_maxrss` 乘 1024；Darwin 原始值已经是 bytes，因此报告出现数十万 MiB。POSIX 该指标还是进程生命周期峰值，不能当作每次调用的独立增量。
- 证据：R，真实 ONNX 基线 ingestion 报 960544 MiB；按同一原始样本纠正为 938.03125 MiB。原始 JSON 保留不覆盖；`embedding-rss-correction.json` 明确标为单位换算而非重新推理。
- 用户影响：误判内存需求、把不存在的超大内存峰值作为优化依据；不影响模型结果。
- 修复：Darwin multiplier=1，Linux multiplier=1024；Windows 分支不变，代码注明 lifetime peak。
- 收益/不确定性：恢复测量可信度，无生产内存减少。POSIX `max_native_threads` 目前仅统计 Python 线程，本报告不把它作为 ONNX 原生线程证据。
- 风险：低，仅评测辅助函数。
- 回归：两平台单位合同测试通过，修正后当前独立进程约 27.67 MiB；没有把这次轻量导入与完整 ONNX 进程比较。

### AUD-14 — 本机摄取 Embedding 吞吐低于已有门槛

- 位置：`scripts/benchmark_phase3_embedding.py:90`；生产配置记录于 `embedding-baseline.json:4`。
- 机制/触发：本机 6 核/8 GiB、ONNX FP32、batch16、摄取 intra-op3、inter-op1；冻结500文本预热后5轮，单批中位49.45秒，10.11条/秒。
- 证据：R，现有脚本 exit1，`ingestion_gte_20_texts_per_second=false`；其余4项门槛通过。未测该机器的当前 Torch，历史10.59仅用于已有脚本门槛，不能当作同环境 before。
- 用户影响：大教材建立向量的吞吐可能受限；本轮未完整解析真实大教材，不能把总导入时间全归因于 embedding。
- 方案：独立受控试验 batch与线程组合，记录长度分布、RSS和并发查询 p95，并运行 embedding parity/检索质量门槛后再决定配置。不能直接减少精度、截断正文或降低门槛。
- 收益/不确定性：未知；更多线程/更大batch可能挤占交互与内存，不能承诺翻倍。
- 风险：中，改变全局runtime配置影响所有检索/摄取；本轮仅保留基线与方案。
- 回归：同冻结500文本至少5轮、交互20轮、并发20轮；真实教材样本和向量parity；检查安装包运行身份。当前是基准门槛失败，未复现前台崩溃，归P2。

## 已有有效设计与暂不值得做的重构

- 不新增开放 Agent loop 或并行任意工具。当前原生 batch 顺序与 fatal-error latch 保证预算、可追溯回执及后续调用抑制；未证明串行是主要瓶颈。
- 保留 ContextPack 有界历史、EvidencePack 最终可见事实、数学独立验证、缺输入/降级状态。此次没有以 token、tool 数或字符裁剪换取性能。
- 保留 staged candidate、原子发布与回滚，不重建正式 Chroma collections。局部 Chroma失败/同书fallback/范围负例已有回归。
- 保留 ONNX singleton、惰性 ingestion provider、教材列表共用读缓存、Markdown/MathLive 按需加载。大 chunk 警告不等于首屏必然加载全部 MathLive。
- 不统一所有 SQLite 表、不迁移独立 Notes/Goal/错题资产，不删除兼容路径，不单凭文件大小拆分 Runtime，不用代码行数衡量优化。
- 不删除历史前端 hash 资源以“修复包体”；不关闭校验、日志或失败恢复；不改模型供应商、profile、默认开关或正式数据。

## 未覆盖与发布建议

本轮安全用例包括路径/解压限额、认证与跨站写边界、HTML与thinking过滤、工具白名单、未知写入/幂等/恢复；全量离线测试通过相关用例，不是专项渗透测试。没有读取、打印或发送正式密钥、教材和学习记录。

真实模型生成质量/Token费用、完整真实教材混合检索事实覆盖、大教材 OCR/MinerU服务、持续数小时多任务负载、真实手机网络、Windows与安装包更新恢复均保持未测。先处理 AUD-07 的版本化合同审阅及 AUD-14 的吞吐门槛，再按已有发布矩阵完成这些适用门槛；不要把本次修复和离线通过率作为完整发布认证。

## 收尾期间的其他工作树改动

收尾时检测到另一组图片识别恢复/错题API修改：`backend/api/mistakes.py`、`backend/services/multimodal_bridge.py`、`tests/test_mistakes_api.py`、新`tests/test_visual_recognition_recovery.py`及独立patch_notes条目。它们不属于本轮7项修复，已原样保留；没有把其他任务成果计入本次性能收益。为避免用旧结果代表新树，另跑当前工作树完整测试，记录在`docs/qa/performance-reliability-2026-10-23/backend-current-tree.log`，运行前后源码哈希核对记录在同目录。原审计各轮日志和样本不覆盖。

此次当前工作树补跑为 **2163 passed / 3 failed，91.80秒**，仍为同3项Policy合同失败；此前那项搁置取消测试此次通过，保留其失败观察且不认定根因。运行前后源码哈希一致（`test-source-stability.json`）；新增用例属于另一任务，不能计入本轮修复数量。其他任务的暂存操作亦不属于本轮；本任务没有暂存、提交或推送。

## AUD-09 后续提交验证

用户授权将 AUD-09 与原七项审计修复一起提交到 `Texa_MacOS`。图片识别恢复已在 `e870e3b` 独立提交，本次提交继承该记录。其余搁置功能差异继续留在工作区；提交只选择经审阅的无关 hunk。新增构建证据见 `docs/qa/aud-09-release-2026-10-23/`。历史审计数据不改写为本次安装包验收结果。
