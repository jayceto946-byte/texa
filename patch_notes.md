# 2026-08-10 - venv310 环境重建与依赖锁定修复

## 原因

- venv310 长期混装 PaddleOCR / Marker / Surya / MinerU 等可选 OCR 运行库，未纳入锁定文件，`pip check` 报告 protobuf、numpy、pillow、openai 等版本冲突，环境不可复现。
- 核实生产 OCR 路径：错题图片 OCR 走 Kimi Vision（`backend/api/mistakes.py`），教材解析走外部 MinerU（`ingestion/mineru_client.py`，纯 httpx API）；`ingestion/ocr.py` 的 PaddleOCR/PPStructure 只被遗留 CLI（`ui/cli.py`）与独立 agent（`agents/coordinator.py`）引用，生产路径不依赖本地 OCR 运行库。

## 动作

- 旧环境改名保留：`venv310` → `venv310-mixed-backup`（6.1G，未删除），包清单备份至 `logs/venv310_pip_freeze_backup.txt`（305 项，被 gitignore 忽略）。
- 用 Python 3.10.11 全新创建 `venv310`，按 `requirements-dev.txt` 精确安装（torch 2.11.0+cpu、openai 2.46.0、chromadb 1.5.9 等），体积约 848M。
- 修复锁定文件：`requirements-release.txt` 中 `openai==1.109.1` 与 `langchain-openai==1.2.2`（要求 `openai>=2.26,<3`）冲突，说明该锁定集此前从未从零安装验证；改为 `openai==2.46.0`（与已验证通过全量测试的本地环境版本一致）。

## 影响

- 主 venv310 回归纯净锁定集，`pip check` 通过、可复现；Electron/CI 的 fresh-env 安装现在可解析成功。
- `ingestion/ocr.py` 缺 PaddleOCR 时按原有 try/except 降级返回“[PaddleOCR 不可用]”提示，不阻塞导入；CLI / `agents/coordinator.py` 的本地 OCR 功能不可用（生产路径不受影响）。
- 未修改数据库、向量索引、教材、错题或学习记录。

## 验证

- `pip check`：No broken requirements found。
- 后端全量 pytest：403 passed（88.8s），仅既有 Starlette/httpx2 弃用警告。
- uvicorn 启动冒烟：`/api/system/health` 200、`/api/system/version` 200，embedding 本地快照加载，2.3s。
- git：`requirements-release.txt` 的 openai pin 修复与本次环境重建记录已随独立 commit 提交；旧环境 `venv310-mixed-backup` 已于确认后删除，磁盘释放约 6G。

# 2026-08-09 - Read-only Agent 超时与可观测性修复

- Read-only Agent 新增 50 秒总预算、8 秒单工具预算和 35 秒模型总结预算；Agent 专用 LLM 请求禁用自动重试，并以相同的请求超时约束底层客户端。超时工具只标记为局部不可用，模型总结超时则保留已读取证据并返回明确提示，不再无限占用前端请求。
- 每个工具输出新增执行状态、耗时和超时预算；响应新增总耗时、逐工具 trace 与模型总结 trace。后端只记录 conversation id、工具名、成功数、总结状态和总耗时，不记录问题或证据正文；前端 Agent 卡片显示总耗时、逐工具耗时和总结超时/失败标记。
- 前端 Agent 请求上限调整为 55 秒，普通回答降级设置 60 秒上限；发生 Agent 网络/协议失败时，阶段文案明确切换为“正在降级到普通回答”，不再保留误导性的工具读取状态。普通非流式回答也获得 130 秒有界超时。
- “我今天复习什么”等复习任务精简为 `build_review_plan` 与 `get_weak_concepts`，不再重复调用到期错题、错题统计，也不再附加无关的教材与概念搜索。加入错题提案不会再因包含“错题”而同时触发复习计划。
- 未修改数据库、向量索引、教材、错题或学习记录格式。验证：后端全量 390 passed；前端 Vitest 15 files / 70 tests passed；ESLint、TypeScript、Vite production build 与 `git diff --check` 通过。构建仅保留既有 MathLive 大 chunk 提示。

# 2026-08-09 - 主聊天接入 Read-only Agent

- 主聊天发送链路新增保守的学习任务路由：明确的复习计划、学习进度、组题练习和教材例题查找进入 Read-only Agent；概念解释、讲题、证明推导、普通追问和依赖历史对象的“把这道题加入错题本”继续走既有 SSE/RAG，避免误路由和错误写入提案。
- Agent 请求复用 ChatContext 的全局 loading/abort 生命周期，支持停止；请求失败或没有选择到工具时自动降级到 `/api/chat/ask` 普通回答。Agent 成功回答通过 `/api/chat/log` 写入 append-only 会话历史，保存完成后才重新开放下一轮输入，避免紧邻追问读不到刚完成的 Agent turn。
- `runReadOnlyAgent` 接入 AbortSignal；通用 fetch timeout 现在会合并外部取消与内部超时，避免传入 signal 后丢失超时保护。
- Agent 卡片补齐教材例题、薄弱概念、习题筛选、最近进度和练习提案标签；展示成功工具、局部失败数量和待确认操作，并明确标记提案“尚未执行”，不提供虚假的确认按钮。
- 新增确定性前端路由回归，覆盖 5 类正例、6 类普通 RAG 负例、无教材 scope 和四类阶段文案。验证：前端 15 files / 69 tests passed，ESLint、TypeScript 与 Vite production build 通过；后端 Agent 工具专项 9 passed，`git diff --check` 通过。构建仍只有既有 mathlive 大 chunk 提示。

# 2026-08-09 - 首批学习 Agent 工具补全

- 补齐并注册首批工具中的四个缺口：`find_textbook_examples`、`get_weak_concepts`、`search_exercises` 与 `get_recent_progress`。连同既有的教材/概念搜索、到期错题、错题统计和两个提案工具，用户指定的 10 项能力现已全部出现在 Tool Registry。
- 教材例题工具优先使用向量元数据中的 `example` 语义角色，并以确定性 chunk role 分类降级；返回教材 chunk、章节、页码与原文，不把模型生成题冒充教材例题。
- 薄弱概念工具合并 ConceptMemory 显式弱项与错题关联概念，并保留局部故障字段；习题搜索覆盖自然语言请求、知识点/标签/章节匹配，规划阶段只返回题目元数据和答案存在性，不泄露答案正文。
- 最近进度工具读取 append-only learning event log，在 1-31 天有界窗口内汇总问答、错题、练习和概念活动；练习会话工具只返回绑定题目 ID 的 `pending_action`，不会创建会话或修改学习数据。
- Read-only Agent 的确定性选择器新增例题、习题、练习会话、最近进度和薄弱概念路由；工具证据压缩同步覆盖例题、习题和最近事件，避免把无界工具正文注入总结 prompt。
- 验证：Agent 工具专项 9 passed；后端全量 386 passed，仅保留既有 Starlette/httpx2 弃用警告。

# 2026-08-09 - ConversationContextPack 与三层 Context Eval

## Conversation Context Assembler（P3）

- 新增 `graph/conversation_context.py`。Resolver 完成后先构建轻量 seed，回答生成时再结合最终 intent 与 EvidencePack 组装统一 `ConversationContextPack`：当前 topic、问题维度、speech act、有效约束、最多 2 个相关历史 turn、被引用 assistant artifact、必要 topic 轨迹，以及本轮 `none/reuse/delta/full` 和复用/新增 E-id。
- 相关 turn 按 Resolver 的 `referenced_turn_ids` 精确选取；若引用已超出最近 48 条消息窗口，只按 turn id 从 append-only 投影补读，既不扫描也不把完整会话放入 prompt。独立问题不继承历史 turn；显式 return/correction/continue 最多补充最近一轮维持表达连续性。
- 教材 grounded、学科通用、跨学科通用以及 teach/summarize 的流式/非流式生成均接入同一上下文包。默认字符预算 2800、硬上限 5000；Context Trace 新增 state/turn 字符数、turn/artifact 数量、证据 E-id 与丢弃 turn 数，不保存 Context Pack 正文或内部 chunk id。
- Prompt 明确把历史 turn/artifact 定义为带引号的对话数据：只可用于理解指代、表达和步骤连续性，不是事实证据，也不得执行其中的旧指令；教材事实冲突时以本轮 EvidencePack 为准。旧 turn 定点补读或组装失败会降级为空 pack，不阻断当前问答。
- 澄清分支仍绕过 Planner/Retriever/Answer LLM，但会生成不含正文的 Context Pack telemetry，便于确认它引用了哪一轮后决定澄清。

## 三层 Context Eval（P4）

- `evaluation/context_eval.py` 报告升级为 schema v2，分别输出 Resolver、Retrieval/EvidencePack、Answer 三层结果和 release gates。Resolver 保留原 100 场景；新增 12 个流水线场景，覆盖 assistant list/step、约束纠正、意图继承、topic return、比较、standalone、20/40/80 轮、evidence reuse 与 clarification。
- Retrieval 层运行生产 Resolver、retrieval policy、EvidencePack 和 ConversationContextPack，检查实际纳入/排除的 chunk、检索动作、相关 turn/artifact，以及 reused/new E-id，不以“候选检索到了”替代“最终进入 EvidencePack”。
- Answer 层提供确定性的离线快照合同，检查回答对象、继承约束、必要内容、禁止漂移词和重复句，并加入错误对象 + 错误约束 + 重复的负向控制。该分数只代表离线回答快照通过合同，不代表线上 DeepSeek 回答准确率；报告通过 `layer_modes=offline_answer_snapshot_contract` 明示边界，后续可把真实采集回答送入同一评分器。
- 发布门槛：三层总体均至少 80%，Retrieval/Answer 至少各 10 例；user correction、assistant artifact、clarification、evidence reuse/delta、negative 与 standalone 必须 100%；20/40/80 轮分别至少 80%，任何单独长会话门槛失败都会阻止 strict 通过。
- 为支持“再简要解释一下”类 Answer 连续性，Resolver 新增 `deterministic_rephrase`，显式恢复 topic 与上轮 intent 并输出 `keep_previous_intent`；同时修正长会话引用 turn 优先级，避免“概念1”被“概念19”的字符串包含关系误绑。

## 验证

- Context Eval strict：Resolver 100/100、Retrieval/EvidencePack 12/12、离线 Answer snapshot contract 12/12；全部总体、专项和 20/40/80 独立 release gates 通过。
- P3/P4 专项回归：66 passed（仅 1 条既存 Starlette/httpx2 弃用警告）。
- 后端全量：380 passed（同一条既存弃用警告）。Electron 共用前端：ESLint 通过、56 tests passed、TypeScript 与 Vite production build 通过；构建仅保留既有的 mathlive 大 chunk 提示。

# 2026-08-09 - Append-only 会话历史、Session Ledger 与 Resolver v2

## 会话历史与分页

- 会话消息改为 SQLite append-only event log：`conversations/_conversation_events.db` 保存不可变事件，`conversation_messages` 作为可分页读取的当前投影。原有单会话 JSON 保留为最近 40 条消息的轻量兼容投影，不再承担完整历史存储；列表中的 `message_count` 来自完整投影。
- 旧 JSON 会话在首次读取/追加时惰性导入一次，迁移使用 `conversation_imports` 防重复。迁移不会修改教材索引、ChromaDB、错题或学习记录；若旧 JSON 在本次升级前已经裁掉了更早消息，那部分历史没有数据来源，无法事后恢复。
- 会话详情和独立消息接口支持 `limit/before_seq` 游标分页。前端首次只加载最近 40 条，顶部可继续加载更早消息并保持滚动位置，不再把完整会话一次送入 React state。
- 更新概念标签、证据支持状态、会话重分类和 turn 拆分时，同时更新消息投影并追加对应事件；重分类/拆分会使派生 Ledger 失效并在下次请求重建，原始事件不删除。

## Session Ledger

- 新增 `backend/services/session_ledger.py`，为每个会话保存有界的结构化状态：topic stack、最近 100 个实体及 first/last mentioned turn、entity groups、assistant artifacts、constraints、comparison frame、intent 和 active evidence。
- Resolver 请求只读取最近 48 条消息与 Ledger；Ledger 缺失或落后于最新消息时，才从完整事件投影重建。完整历史用于重建状态，不直接塞入 Planner/Answer prompt。
- Ledger 使用原子 JSON 写入和按会话分片的重入锁，避免同一会话并发读改写造成文件损坏或静默丢更新。80 轮专项回归确认：近期窗口已经不含第一轮时，“回到第一个”仍能解析到首轮实体。

## Resolver v2

- Resolver trace 在 `resolved_query` 之外正式输出 `speech_act` 与 `state_operations`。当前稳定操作包括 `set_topic`、`return_to_topic`、`select_artifact`、`replace_constraint`、`correct_entity`、`keep_previous_intent`、`add_constraint` 和 `clarify`。
- 已覆盖条件替换、实体纠正并继承上轮意图、显式返回旧话题、长序数引用、多实体/assistant artifact 引用和独立问题防错误继承。澄清请求不再推进 `state_after`，避免无法解析的指代污染当前主题。
- Context Trace v2 对 `speech_act/state_operations` 做有界持久化；Context Eval 同时校验这两个字段，不再只检查字符串改写是否碰巧正确。

## 验证

- Context Eval strict：100/100；resolution、follow-up、references、clarification、speech act、state operations、state、retrieval action/query、scope change 和 standalone preservation 均为 100%。其中包含真实展开的 20/40/80 轮场景。
- 后端全量：371 passed（仅 1 条既存 Starlette/httpx2 弃用警告）。前端：ESLint 通过、56 tests passed、TypeScript 与 Vite production build 通过。
- 新增专项测试覆盖 261 条消息的完整读取与两页无重叠分页、旧 JSON 单次导入、append-only event 数量、80 轮 Ledger 回指、Resolver v2 条件替换和澄清状态不变。

# 2026-08-09 - Assistant Artifact Index、主动澄清与 Evidence Continuity

## Assistant Artifact Index

- 新增有界、确定性的 assistant 输出索引。Resolver 会从最近回答中提取可被后续指向的列表项、步骤、例题/反例、公式、Markdown 标题、表格数据行、结论和命名方法；普通正文不进入索引，单条回答最多保留 32 个 artifact，会话状态最多保留 48 个。
- 支持“第一个/第二道题/第二步/第一部分/第二行/前者/后者/这个式子/这个结论/它的条件”等引用，并在 Context Trace 中记录 `deterministic_assistant_artifact`、引用对象和 assistant turn id。
- Artifact Index 从现有会话正文即时重建，不新增数据库、不改历史会话格式，也不把整段 assistant 回答写入 RAG Trace。

## 主动澄清

- Resolver 对缺少候选集合的序数、前者/后者及无锚点代词返回 `resolution_action=clarify`，保留用户原问题并生成简短澄清请求；不再把低置信度猜测送入教材检索。
- SSE 与 `/api/chat/ask` 均有独立 clarification 路径：保存 user/assistant 消息，但完全绕过 Planner、Retriever 和回答 LLM；Context Trace 记录 `retrieval_action=none` 与 `clarification_no_generation`。

## Evidence Continuity

- 会话从上一条 assistant 消息读取 sources 与最终 `evidence_support_status` 快照，结合 topic、intent、教材/学科 scope 和是否请求新维度，选择 `none/reuse/delta/full`。
- `reuse` 通过 chunk id 从本地教材词法索引恢复原始证据正文并跳过向量库/KG 初始化；无法恢复正文时如实降级为 `full`。`delta` 保留已恢复的旧证据，并运行检索补充新维度，最终分别记录真正进入 EvidencePack 的 reused/new/dropped ids。
- 只允许紧邻的上一条 assistant 回答提供 active evidence；中间出现无来源回答、topic 改变、教材/学科切换或旧证据不可恢复时，不复活更早的 stale evidence。上一轮 support 为 `partial` 时，即使同一维度也强制走 `delta`。
- 会话 JSON 新增可选的 `evidence_support_status` 消息字段，旧会话无需迁移；教材索引、ChromaDB、错题和学习记录均未修改。

## 评测与验证

- 100 场景 Context Eval 从初始 41/100 提升到 64/100：assistant artifact 16/16、clarification 3/3、evidence reuse 2/2、evidence delta 2/2、retrieval policy 10/10；core 7/7 与 negative 9/9 保持不变。剩余 36 个失败主要属于长程早期实体、用户纠正、条件替换和更复杂意图链。
- 新增生产路径测试覆盖 artifact 解析、澄清绕过 Graph、SSE/非流式协议、reuse 不初始化向量检索、delta 合并旧/新证据、partial support 强制补检和 support 快照持久化。
- 针对性回归 58 passed；后端全量 366 passed，仅有既存 Starlette/httpx2 弃用警告；`git diff --check` 通过。

# 2026-08-09 - Context Trace v2 与多轮 Context Eval 基线

## Context Trace v2

- 会话 Resolver 在保持原改写结果不变的前提下，新增有界的解析观测：`raw_query / resolved_query`、规则来源、规则强度、引用实体与 turn、以及 `state_before / state_after`。规则强度明确标记为 `rule_strength`，不冒充统计校准后的概率。
- Chat 的 SSE 与非流式路径统一写入 Context Trace；检索侧记录 `none/reuse/delta/full` 动作、实际 retrieval query、复用/新增/丢弃的 chunk id、支持状态与降级错误。该初始基线尚未实现 evidence reuse，因此当时教材问答如实记录 `full` 和空的 reused 集合。
- Generation 记录最终组装上下文的字符预算，包括实际 prompt、query、教材证据、学习历史、教学内容、scaffold、EvidencePack 候选/纳入/丢弃数量和 Planner prompt 字符数。Trace 只存大小与标识，不保存 prompt 正文、回答或 thinking。
- RAG trace SQLite schema 升级到 v2，新增非空 `context_json`（默认 `{}`）。迁移使用现有 `PRAGMA user_version` runner，旧记录原样保留并回读为空 context；写入改为显式列名，避免后续加列破坏历史兼容。

## Educational Conversation Eval

- `evaluation/context_eval.py` 与 JSONL 黄金集扩展为 100 个多轮场景：指代 16、序数 14、比较 12、assistant artifact 16、用户纠正 4、scope 8、retrieval policy 10；另外分别包含 4 个 20/40/80 轮场景。测试对各类最小覆盖数量设有 release guard，避免后续删用例虚增分数。
- 长会话使用受限的 `history_spec=topic_sequence` 确定性展开为真实 user/assistant turns，报告保存展开后的 `history_turn_count`；不是把一个摘要假装成长会话。教材/学科切换会校验 scope change；检索场景校验 action 与实际 retrieval query。
- 新增显式 `graph/retrieval_policy.py` 边界并接入生产 Retriever。初始策略严格等价于旧行为：禁用教材时 `none`，启用教材时 `full`；active-evidence 输入先用于定义后续 `reuse/delta` 黄金目标。
- 报告提供 resolution/follow-up/reference/state/clarification/retrieval-action/retrieval-query/scope accuracy、standalone preservation、按 tag 分组和逐例失败详情；默认生成报告但不因已知缺口退出失败，`--strict` 可用于未来 CI release gate。
- 100 场景扩展基线为 41/100（41%）：core 7/7、negative 9/9、no-retrieval 3/3；20/40/80 轮均为 2/4。assistant artifact 0/16、clarification 0/3、evidence reuse 0/2、evidence delta 0/2；这些均是未实现能力的真实红灯，不是本轮回归。retrieval action 为 77.8%，retrieval query 与 scope-change checks 均为 100%。

## 影响与验证

- 针对性回归：49 passed，覆盖 v1 -> v2 SQLite 迁移、trace 裁剪、SSE 主链路、状态前后快照、上下文预算、长会话展开、coverage guard、clarification 红灯和 retrieval policy 红灯。
- 后端全量：356 passed；仅有既存 Starlette/httpx2 弃用警告。`git diff --check` 通过。
- 未改变 Planner、Retriever、EvidencePack 排序或回答策略；未修改会话文件、教材索引、向量库、错题和学习记录。现有 RAG trace 数据不删除。

# 2026-08-09 - Citation 协议收口与来源层级整理

- 畸形引用根因：模型偶发输出全角/半角混用的 `［[cite:E7]］`；原前端只识别标准 ASCII `[[cite:E7]]`，因此协议文本会直接显示。会话抽查中对应 E1/E6/E7 的结构化来源均存在，问题不是多轮 metadata 丢失。
- 新回答修复：生成收口阶段统一规范标准、全角混合和折叠 citation token，并按本轮 EvidencePack 的 E-id 白名单删除越界引用；规范化统计随 RAG trace timings 保存。持久化内容与最终 UI 内容使用同一份清洗结果。
- 历史兼容：前端解析器兼容已经保存的全角/半角混合 token，旧会话无需迁移即可恢复为上标引用。
- 编号乱序根因：正文编号按首次引用顺序派生，但来源列表此前仍按 EvidencePack 检索顺序渲染，形成 `1、2、5、3、6、4`。现改为先按正文编号排序，再展示。
- 来源整理：将检索中已有的 `section_path`、`chunk_index` 和推断的 `heading_level` 贯通到 EvidencePack/UI；来源按“教材 → 章 → 现有标题路径”分组，同一位置的多个证据段合并显示，未被正文引用的检索材料默认二次折叠。章名与节名相同时去重，避免 `第六章 / 第六章`。
- 边界：本轮不重建教材索引，不补造索引中缺失的中间标题，不修改向量库、教材数据、数据库结构或依赖。现有 metadata 只有“章 → 三级标题”时，UI 会忠实展示该路径，不会假定其所属二级标题。

## 验证

- 后端针对性测试：21 passed；后端全量：343 passed（仅既有 Starlette/httpx 弃用 warning）。
- 前端 citation 工具：16 passed；前端全量：54 passed；ESLint 与生产构建通过。
- 新增覆盖：全角/半角混合 token、折叠 token、越界 E-id 删除、正文顺序排序、同位置合并、章名去重、现有 section_path 贯通。

# 2026-08-08 - Session 上下文追问 + ConceptMemory + Citation + 对话 UI 专项修复

## 一、Session 内上下文追问（P0）

- 现状确认：此前只有 `backend/conversation_memory.py::rewrite_followup` 的词法拼接（把上一条用户消息拼进 query），没有真正的 Conversation Resolver；graph 从未收到 history，概念抽取/retrieval/answer LLM 都只看改写后的单条 query。
- 三个 Context 测试失败原因（均已实测复现）：
  - Test1 Q3「那前者通常用在哪些传感器里？」：“前者”不在旧 follow-up 标记里 -> 原样进检索 -> KG 只命中「传感器」-> 答错对象。
  - Test2 Q2「条件呢？」：非 follow-up 标记 -> 原样进检索 -> 无法检索到支撑证据。
  - Test3 Q2「再解释一下霍尔效应。」：「再解释」被识别为 follow-up -> 拼接成「解释压阻效应。；再解释一下霍尔效应。」-> retrieval gate 因 focus 词覆盖失败判 `insufficient` -> 拒答。实测 standalone「再解释一下霍尔效应」单独检索完全正常（`supported, matched=[霍尔效应]`），拒答纯粹是错误拼接造成。
- 修复（`backend/conversation_memory.py::rewrite_followup` 重写为规则式 Resolver，毫秒级、无 LLM）：
  1. 自足检测：query 含显式概念时绝不拼接历史（修复 Test3 拒答根因）；
  2. 「前者/后者」：取最近用户消息的比较对（含对侧指代解析）解析（Test1）；
  3. 纯省略追问（条件呢/定义呢/性质呢...）：锚点概念 + 问题模板（Test2）；
  4. 指代词（它/这个/...）：替换为当前显式概念或历史锚点；话题切换引导词（回到刚才的）剥离（Topic Switch Test）；
  5. 解析失败且有指代信号才回退旧拼接。
- 附带修复 `graph/retrieval_node.py`：`_SUPPORT_FILLER_PHRASES` 增加应用场景功能词（通常/用在/用于/应用于/哪些...），避免「通常用在哪些」被当成无法覆盖的 focus 词导致误拒答；缺点/特点/性质 等真实 focus 校验不变。

## 二、ConceptMemory 延迟（P1）

- 确认：`link_concepts_for_response`（UI 概念标签）同步运行在 answer 关键路径（done 事件之前）；确定性部分（词典/别名/KG 扫描）实测 1-3ms，唯一慢点是 `_targeted_repair` 的 LLM 逐项验证（仅当 query 含非 KG 并列概念时触发，约数秒）。`ConceptMemory` 持久化（`_record_concept_memory`）本就在后台线程。真实 trace 显示用户观察到的 5-10s 停顿主要是 plan LLM（非 fast-path 查询），概念链路本身不是主因。
- 修复（`graph/feedback_node.py`）：`link_concepts_for_response` 走 `allow_llm_repair=False` 快速路径（无 LLM），UI 概念标签不再被 LLM 阻塞；完整（含 LLM repair）解析由后台 `_record_concept_memory` 执行，能力保留。增加 fast/full pipeline 耗时日志。

## 三、Container 概念过度抽取（P1）

- 根因：KG 概念无 type 字段；「传感器」「线性代数」等 container 作为 KG 概念被 `query_dictionary` 命中，`coverage_gate` 判 `auto_missing` 后被 `_targeted_repair` 无条件补回（confidence=1.0），成为 core concept。
- 修复：`_targeted_repair` 对与当前 book/subject/chapter container 同名的 `auto_missing` 候选默认不补回（`_container_names_for_state`，book 名去 长书/短书/教材 等后缀）；「什么是传感器？」这类显式询问仍由 kg_matched 路径保留。

## 四、Citation 泄漏（P1）

- 根因：`frontend/src/utils/citations.ts::parseCitations` 正则只匹配 `[[cite:E1]]`；模型连续引用输出的折叠形式 `[[cite:E1][cite:E5]]` 不匹配，原样泄漏进正文。实测单引用/相邻/空格间隔正常，仅折叠形式泄漏。
- 修复：正则升级为 `[[cite:E<id>](?:[cite:E<id>])*]`，单/多/连续/折叠引用统一替换为上标；非法 id 仍剔除。live streaming 与 history 共用同一 parser，两端同步生效。

## 五、概念历史持久化（P2）

- 根因：`append_message` 只持久化 content/sources，`linked_concepts` 只存在于前端内存 state；历史会话重载时概念消失。
- 修复：`append_message` 新增 `linked_concepts` 参数；流式回答在 done 阶段用 `update_message_linked_concepts` 把概念快照补写回原消息（不新增消息、不重新抽取）；`/ask` 路径直接随消息持久化。

## 六、输入框双重蓝线（P2）

- 根因（Electron 实测）：`.chat-question-box` 有 `focus-within:border-accent` 蓝边（预期焦点指示），同时全局 `textarea:focus-visible { outline: 2px solid ...accent }` 因特异性 (0,1,1) 高于 textarea 的 `outline-none` (0,1,0) 而生效，形成内外两层蓝框（“双重输入框”）。box-shadow 已被 `focus:shadow-none` 抑制，非本因。
- 修复：`index.css` 增加 `.chat-question-box textarea:focus-visible { outline: none }`，仅取消内层冗余 outline，外层 focus 指示保留。

## 验证

- 新增回归测试：`tests/test_conversation_followup.py`（Context A/B/C + Topic Switch + 负例）、`tests/test_evidence_support_gate.py`（TestA gate + focus 校验保持）、`tests/test_query_concepts.py`（container 过滤 2 例）、`tests/test_citation_pipeline.py`（概念持久化 2 例）、`frontend/src/utils/citations.test.ts`（折叠引用 3 例）。
- 后端全量 301 passed；前端 vitest 49 passed；`tsc -b` 与 `vite build` 通过。
- 端到端：三个 Context 测试 + Topic Switch 经 resolver -> retrieval gate 均 `supported/partial`，不再拒答。
- 未改动依赖、索引格式、数据库结构、环境要求。

# 2026-08-07 - 关键概念抽取：Query-first 候选 + Coverage Gate + Targeted repair

- 问题：教材激活时最终概念集几乎完全由 KG 驱动（`ConceptLinker` 只返回能精确/别名命中 KG 的概念），且 LLM fallback 仅在 `not book_name and not concepts` 时运行。用户并列列出多个独立概念时，只要其中任何一个不是 KG 中的独立概念（如 "横向效应" 不在 KG、"压电效应" 只有 横向/纵向/正/逆压电效应 子类型而无裸形式），就会漏失。实测 "总结一下横向效应、压阻效应、压电效应的定义和区别" 最终只有 `压阻效应`。
- 实现（新增 `knowledge/query_concepts.py`，只读、无副作用）：
  1. `extract_query_candidates`：确定性并列结构切分（、，,/ 和 与 以及 及 或）+ KG 字典/别名扫描，正常情况不调用 LLM；词典精确命中视为已确认。任务词（定义/区别/特点/优点/缺点/应用 等）与通用噪声在切分时过滤。
  2. 子串包含去重："随机误差、系统误差和粗大误差" 中 "误差" 从未独立出现，不再把 "误差/绝对误差(别名 误差)" 当独立候选；"什么是误差和随机误差的区别" 中 "误差" 有独立出现，保留。精确 canonical 命中优先于别名碰撞。
  3. `coverage_gate`：按 concept_id / 归一化名称比较 query 显式候选与 final concepts；绝不使用 embedding/fuzzy 相似度（压阻效应 vs 压电效应 不会被误合并）。返回 auto_missing（字典确认缺失）与 validate_missing（启发式缺失）。
  4. Targeted repair：字典确认缺失直接补回（不调 LLM）；启发式缺失做一次受限逐项验证（constrained classification，非重新自由生成），仅本地 KG 激活时执行。
- 接入 `graph/feedback_node.py`：`_resolve_final_concepts` 统一 query-first -> 现有 KG linking -> merge -> coverage -> repair；`link_concepts_for_response`（UI）与 `_record_concept_memory`（学习记忆）共用同一结果；后台记忆线程复用 `state["linked_concepts"]` 避免重复 LLM 调用。非教材上下文（学科路由）保持原行为。
- `knowledge/concept_memory.py`：`_CONCEPT_EXTRACT_PROMPT` 改为穷尽式识别语义（不按重要性排序、并列项逐项独立判断、任务词不作概念、上限 8->12）。
- 新增回归测试 `tests/test_query_concepts.py`（覆盖任务 CASE 1-12）。
- 未改动依赖、索引格式、数据库结构、环境要求；未改动检索/证据/Citation/前端。

### Validation

- 真实 pipeline（传感器长书 + DeepSeek repair）："总结一下横向效应、压阻效应、压电效应的定义和区别" 最终概念集 = `[压阻效应(question_mention), 横向效应(query_repair), 压电效应(query_repair)]`，无 "定义/区别"。
- normal case（热敏电阻/正态分布/金属应变片/随机误差等）0 次额外 LLM 调用；repair case 每轮 +1 次受限验证调用，后台记忆不重复调用。
- 精度："随机误差、系统误差和粗大误差？" 精确得到 3 个概念，不再带出 误差/绝对误差；"热敏电阻的定义、特点、优点、缺点和应用" 仅得 热敏电阻。
- 全量测试 284 passed（含 22 个新测试）。
- 残余 best-effort：generic QA（无教材）仍走既有 LLM `extract_concepts`（prompt 已改穷尽式）；"绝对误差" 别名碰撞在既有 linker weak-intent boost 下仍可能进入（KG 数据问题，非本次引入）；"金属应变片" 依赖 KG 中 电阻应变片 的 应变片 别名。

# 2026-08-07 - Desktop dev 模式恢复「接管已有后端」工作流

- 修复：dev（非打包）下 `npm run dev` 现在先探测 `BACKEND_URL/health`，若端口上已有健康后端（如手动启动的 uvicorn）则直接接管、跳过 spawn，不再因端口被手动后端占用而报 `后端进程退出：code=1, signal=null`。
- 根因：8-03 提交 `55fcaf45` 引入的 instance_id 身份握手 + 「自拉后端退出即判失败」逻辑，破坏了「手动起后端 + npm run dev」这一既有工作流——此前自拉失败会被容忍并静默连上手动后端。
- 实现（仅 `desktop/main.cjs`）：`startBackend` 改为 async，dev 路径 spawn 前调用 `probeExistingBackend()` 探测，命中则记录 `dev: adopting existing backend ...` 并返回；`waitForBackend` 的 fail-fast 与 identity 校验改为仅对 `app.isPackaged` 生效；dev 下自拉后端退出时保留 fallback 窗口，确无可用后端才以记录的退出原因判失败；退出处理器按打包/开发模式分流。
- 打包版行为保持不变：仍严格校验 instance_id，自拉后端退出即失败。
- 未改动任何数据、索引、数据库结构或依赖。

### Validation

- dev + 手动后端在 8000：日志出现 `dev: adopting existing backend at http://127.0.0.1:8000 (spawn skipped).`，无 10048、无 code=1，Electron 正常打开并接入手动后端；`node --check` 语法通过。
- dev + 无后端（测试端口 8011）：自拉后端成功（`Uvicorn running on http://127.0.0.1:8011`），前端加载与 API 调用全部 200，无回归。
- 打包版路径未做运行时验证（需完整打包构建），代码与改动前一致。

# 2026-08-04 - Electron textbook retrieval smoke acceptance

- Ran the packaged Electron UI against the local FastAPI backend with the `专业课 / 传感器` textbook scope selected.
- Verified one normal sensor question through the complete UI path, then submitted four consecutive textbook-external questions covering a future market size, a general market-size claim, a sales forecast, and an unrelated Mars-agriculture scenario.
- Closed and cleanly relaunched Electron, restored the sensor scope, and verified a second normal textbook question to confirm that the rebuilt index remained usable across a desktop restart.
- This was a read-only acceptance run: no textbook index, vector collection, mistake record, exercise record, or learning history was modified.

### Validation

- Normal grounded answers: 2/2 completed with correct textbook content and visible chapter/section citations. The post-restart thermistor query returned 10 evidence items and completed in 7.52 seconds.
- Textbook-external refusal: 4/4 correctly refused to fill unsupported facts from model knowledge. All six RAG traces finished with status `done`, empty error fields, and no surfaced HNSW failure.
- Retrieval stage latency across the six requests was 0.77-1.29 seconds. The first normal answer took 36.17 seconds backend total, dominated by 28.38 seconds to generation TTFT; this fails a strict no-obvious-wait latency expectation even though retrieval correctness and stability passed.
- System health after the run was `healthy`; vector-store health reported 49 active chapter indexes and RAG trace storage was healthy.
- Observed UX follow-up: scoped refusal messages still render a textbook source/tag derived from topic-overlap evidence, which can misleadingly imply that the refused fact itself has a citation.

# 2026-08-03 - Sensor index repair and bounded dense fallback

- Created and verified a complete pre-change backup including derived vector data: `learning_data_20260803_233450_pre_sensor_index_rebuild.zip`, SHA-256 `69BA32AF4C652C334F5A46B867631AC046CD9CBA106457A67AF8FFCFE691E665`.
- Rebuilt `传感器短书` through the versioned schema-4 pipeline from 562 preserved OCR chunks. Exact chapter-heading boundaries mapped all chunks to 13 chapters with zero unmatched rows; the activated index now has 13 chapter collections plus one validated whole-book aggregate, version `e883c88af247f5fe`.
- Extended the supported reindex script to hydrate empty chapter shells from exact, monotonic section headings. Missing or out-of-order headings still fail closed instead of guessing.
- Aggregate query failures are now logged and quarantined for the process. Dense fallback receives a BM25 chapter shortlist capped at 12; an unavailable aggregate without a shortlist cannot fan out across more than 12 chapter collections.
- Did not rebuild `传感器长书`: after bounded BM25 preselection it searches only 3-5 chapters in the measured workload, so another index mutation had limited incremental value.

### Validation

- Active short-book mapping: 13 chapter collections + 1 aggregate, 14/14 present, schema 4, 562 lexical/vector chunks, no source fallback.
- Ten repeated short-book aggregate searches: median 23 ms, p95 150 ms, maximum/first query 554 ms; no HNSW errors.
- Real 13-case textbook evaluation: Top-10 complete recall 100%, factual point recall 100%, unanswerable refusal 4/4; total run about 22 seconds versus about 69 seconds before repair.
- Full backend suite: 259 passed with one existing Starlette/httpx2 warning.
# 2026-08-03 - Textbook evidence sufficiency gate and factual-list recall

- Added a query-level evidence sufficiency gate that separates the requested fact from the general topic. Topic-only BM25/vector hits no longer authorize a textbook-grounded answer for unsupported market-size, sales-forecast, or unrelated scenario questions.
- Propagated explicit `supported`, `partial`, `insufficient`, `unavailable`, and `not_applicable` evidence states into generation. Insufficient evidence now produces a scoped refusal; partial evidence must disclose its limitation.
- Kept full section titles in literal and evaluation matching, and retained the complete lexical chunk when dense and BM25 hits share a chunk ID.
- Added an explicit selected-book marker independent of core/reference role. For factual enumeration questions only, selected-book BM25 order is preserved so list members split across consecutive sections survive Top-10 fusion; other intents retain hybrid reranking.
- Expanded the retrieval evaluation set with three topic-overlap but unanswerable questions. No textbook index, vector collection, mistake record, exercise record, or learning history was modified.

### Validation

- Real 13-case textbook evaluation at Top-10: complete recall 100%, factual point recall 100%, and unanswerable refusal 4/4 (100%).
- Full backend suite: 254 passed with one existing Starlette/httpx2 warning.
- Observed but did not modify two independent index/performance issues: one corrupted Chroma HNSW segment is skipped through the existing degradation path, and a 479-chapter dense scan took about 40 seconds.
# 2026-08-03 - Desktop startup identity and SPA route reliability

- Added a constrained React SPA fallback for client-side routes while preserving real 404 responses for unknown API and missing asset paths. Refreshing `/settings`, `/books`, and other application routes now reloads the React entry point.
- Added a per-launch desktop/backend instance ID handshake. A normal Electron launch no longer accepts an unrelated process that merely responds on the configured port; `KAOYAN_SKIP_BACKEND=1` remains the explicit opt-in path for an existing backend.
- Made `parse_method=auto` fall back to local PDF text extraction when neither MinerU API nor CLI is configured, while explicit `mineru` and legacy `require_mineru=True` behavior remain strict.
- Replaced double-escaped updater status strings with actual Chinese messages.
- No textbook index, vector collection, mistake record, exercise record, or learning history was migrated.

### Validation

- Focused SPA, health identity, MinerU routing, and system-health regressions: 12 passed.
- Full backend suite: 247 passed with one existing Starlette/httpx2 warning.
- Frontend Vitest: 38 passed; ESLint and TypeScript/Vite production build passed.
- Electron main-process syntax check and `git diff --check` passed.
# 2026-08-03 - Explicit textbook parsing modes

- Replaced the ambiguous high-quality-recognition checkbox with explicit MinerU parsing and local text extraction choices. Explanations are available from adjacent help buttons instead of permanent secondary copy.
- Added a validated parse_method import field. Selecting local now always bypasses configured MinerU services and uses the PDF text layer; selecting mineru requires the configured API or CLI.
- Kept legacy require_mineru callers compatible when parse_method is absent. External parsed ZIP import remains a separate source option.
- Clarified that local extraction does not perform OCR and is unsuitable for image-only scanned textbooks.

### Validation

- MinerU/local routing regression: 6 passed.
- Frontend TypeScript and Vite production build passed.
- Full backend suite: 243 passed with one existing Starlette/httpx2 warning.

# 2026-08-03 - Versioned textbook indexing and asynchronous concept extraction

- Added one supported schema-4 indexing pipeline for normal imports and manual rebuilds. It builds versioned chapter and whole-book Chroma collections off to the side, validates exact counts plus a real dense query, stages the lexical corpus, validates a real BM25 query, and only then switches the active collection map and lexical file. Failed builds keep the previous active assets.
- Index health now distinguishes `vector_ready`, `lexical_ready`, `source_fallback_active`, `status`, and `index_version`. Legacy direct Chroma-writing maintenance entry points are disabled; `scripts/reindex_book.py` is the supported rebuild command.
- Created and verified a complete pre-change backup including Chroma, progress, books, imports, uploads, and MinerU output: `learning_data_20260803_125018_pre_stable_index_pipeline_error_.zip`, SHA-256 `190910097881834e55b505cd30d95d1988be6e043a6918d949f4a18049f88a79`.
- Rebuilt `error theory and data processing` from its 511 preserved OCR chunks while retaining chunk IDs. The activated index has 7 chapter collections, one whole-book collection, 511 persisted lexical rows, schema 4, version `b0a00943f1bc0436`, and no source-file fallback.
- Textbook import now offers an explicit, default-off option to send selected excerpts to the configured external LLM for concept-index extraction. The searchable textbook finishes first; concept extraction runs as a separate durable job and cannot turn a successful import into a failure.
- Renamed the learning-page action from the misleading knowledge-relation wording to `extract textbook concept index`. Candidate checkpoints are content-fingerprint aware, and a completed graph is activated from a dedicated directory only after extraction finishes.

### Validation

- Real hybrid retrieval for the rounding question returned `status=ok` and included the exact `digital rounding rules` section with all three rules.
- Full backend suite: 242 passed with one existing Starlette/httpx2 warning.
- Frontend TypeScript and Vite production build passed.

# 2026-08-03 - Read-only retrieval fallback for imported source chunks

- When a persisted lexical index is absent, textbook retrieval now reads existing `*_middle_chunks.json` import artifacts as a cached, read-only BM25 source.
- Persisted lexical indexes remain preferred. The fallback does not create or modify Chroma collections, lexical index files, textbook data, or learning records.
- This restores direct evidence retrieval for the imported error-theory textbook, whose source chunks exist but whose Chroma and persisted lexical indexes are absent.

### Validation

- Fallback regression passed; real error-theory retrieval included the rounding section and all three rules in the generation prompt; full backend suite passed 240 tests with one existing Starlette/httpx2 warning.

# 2026-08-02 - Thread-safe vector-store startup

- Serialized the process-wide `ChapterVectorStore` singleton initialization so startup warmup and an early retrieval request cannot create competing Chroma `PersistentClient` instances for the same path.
- Vector-store reset now uses the same lifecycle lock. Constructor failures leave the singleton empty so a later request can retry normally.
- No vector collection, mapping, textbook index, or user learning data was changed.

### Validation

- Concurrency regression passed; a real 8-thread probe produced one initialized instance; full backend suite passed 238 tests with one existing Starlette/httpx2 warning.

# 2026-08-01 - Subject routing and conversation scope isolation

- Lexical subject routing now compares the current subject's textbooks too; another subject must clearly outperform the current one before a transfer is suggested.
- Each conversation ID is bound to one exact subject and textbook scope. Scope changes create a new ID in the frontend, with a matching backend safeguard.
- Legacy mixed-scope conversations expose only messages from their current scope. Move-turn and reclassify-conversation workflows remain supported.

### Validation

- Real-index routing checks passed for three error-theory questions; backend 236 passed; frontend lint and TypeScript/Vite production build passed.

# 2026-07-23 - 教材、学习汇总与页面初始化性能优化

- 教材 PDF 列表、metadata、章节 JSON 和索引健康状态增加线程安全文件快照缓存；文件签名变化自动刷新，章节或 metadata 写入后主动失效。
- KG 学习汇总增加 5 秒依赖感知缓存；概念记忆、错题 SQLite/WAL 或学习事件 SQLite/WAL 变化会立即重算，失败响应不缓存，概念复习成功后主动清空。
- 新增习题与错题 overview 聚合接口并保留全部旧接口；习题页初始化从列表、统计、活动会话 3 个请求降为 1 个，错题页从列表、待复习 2 个请求降为 1 个，错题统计请求改为并行。

### Validation

- 教材缓存微基准：约 2000 条章节 JSON 连续读取 100 次，从约 270 ms 降至约 41 ms，当前环境约 6.6 倍。
- 缓存、KG 与聚合端点定向回归：18 passed；聚合流程扩展回归：14 passed。
- 后端全量回归：187 passed。
- 前端 ESLint、Vitest 14 项、TypeScript 与 Vite 生产构建通过。
# 2026-07-23 - 保守解耦第二批

- 将习题练习会话的创建、读取、作答、暂停、恢复、放弃和幂等错题转换编排迁入 `ExercisePracticeService`；SQLite 原子状态转换继续由现有 `ExerciseBank` 负责。
- 将教材 OCR 章节形态识别、目录解析、标题降级和前端章节格式化迁入无 I/O 的 `backend/services/book_chapters.py`。
- 原 API 路由、响应字段和兼容函数名保持不变；教材导入提交、失败回滚、向量索引与当前教材状态没有迁移。

### Validation

- 练习会话定向回归：14 passed。
- 教材章节与导入相关定向回归：22 passed。
- 后端全量回归：177 passed。
# 2026-07-23 - 保守解耦第一批

- 将知识图谱学习汇总中的日期计算、错题摘要和概念复习优先级迁入无 I/O 的 `backend/services/kg_learning_summary.py`；API 保留原函数签名和错题库读取职责。
- 将错题图片上传、暂存、优化、提交和清理迁入 `MistakeImageStore`；API 保留同名兼容包装，OCR 路由和图片事务语义不变。
- 将错题图片裁剪/锐化工具及习题、错题无状态展示组件迁入 `frontend/src/features`；页面请求、状态和交互流程不变。
- 教材导入和习题练习状态机暂未迁移，避免在第一批同时触碰高风险写入链路。

### Validation

- KG 定向回归：10 passed。
- 错题图片与 API 定向回归：20 passed。
- 后端全量回归：174 passed。
- 前端 ESLint、Vitest 14 项、TypeScript 与 Vite 生产构建通过。
# 2026-07-23 - P0/P1 稳定性与安全修复

- 修复流式 `<think>` / `</think>` 标签跨 chunk 时推理内容泄漏；未闭合推理块与不完整标签片段会安全丢弃。
- 收紧本地 API Origin 校验，不再信任请求可控的 `Host`；错题图片识别/解答补充 24 MiB 请求上限，移动采集令牌也不能绕过上传限制。
- MinerU 配置改为调用时读取，API、CLI 与显式本地降级路由均可达；移除从未被代码支持的 `OCR_API_URL` 部署项并纠正文档。
- 教材 PDF 先写入暂存区，解析成功后才进入资料库；导入失败或取消时清理新建 PDF、章节、MinerU、词法与向量产物，同名教材使用唯一存储名。
- 后台任务完成与取消改为 SQLite 条件更新，消除“取消请求覆盖已完成任务”及“取消后仍提交完成”的竞态。
- 错题 OCR 图片先进入待提交区，保存错题后才转为永久文件；识别、解答、数据库保存失败及删除错题时清理对应图片，过期待提交文件自动回收。

### Validation

- P0/P1 定向回归：45 passed。
- 后端全量回归：171 passed。
- 前端 ESLint、Vitest 11 项、TypeScript 与 Vite 生产构建通过。
- Electron 主进程/预加载脚本语法检查、Python AST 检查、Docker Compose YAML 解析和 `git diff --check` 通过。
# 2026-07-21 - 教材抽题页码映射修复

- 修复习题工作区使用 PDF 物理页码，而现有 MinerU/OCR/source package chunk 使用教材印刷页码时，已有 chunk 被误判为空并触发 Kimi Vision OCR 的问题。
- 抽题时读取 PDF page labels：显式选页先映射到印刷页检索现有 chunk；仅按章节抽取时则把印刷页反向映射到 PDF 物理页，供 PDF 文本层和 OCR 降级使用。
- 未手动填写章节时，根据映射后的印刷页范围自动推断唯一章节，并将章节字段传递到候选题和习题库记录。
- 页码范围跨越多个章节或无法匹配目录时，停止生成可导入候选并提示缩小范围或手动填写章节，避免无章节题目进入题库。
- 不修改教材索引、OCR 产物、向量库或学习记录。

### Validation

- 真实教材验证：不填写章节时，传感器短书 PDF 第 52 页映射为印刷第 42 页，自动归入“第二章 电阻式传感器”，命中 1 个 source package 习题 chunk，未调用 OCR。
- 教材抽题与入库定向回归：14 passed。

# 2026-07-18 - AutoDL MinerU 教材解析全流程说明

- 将 `docs/mineru_deploy.md` 重写为 AutoDL 全流程教程，覆盖租卡与镜像选择、独立环境安装、上传、5 页试跑、整本解析、产物打包下载、桌面端导入、关机计费、SSH 隧道直连和故障排查。
- 明确 `GPU Host` 是远端 GPU 实例的泛称；默认推荐输出包流程，直连则使用本地 SSH 隧道端点 `http://127.0.0.1:9001`，避免暴露无认证 API。
- 同步修正首次运行向导、系统设置和 `.env.example` 中含糊的 `gpu-host` 示例。
- 指令依据 MinerU 3.x 与 AutoDL 当前官方文档核对；未租用真实付费实例执行 MinerU。
# 2026-07-18 无教材通用问答学习记录修复

- 无教材科目的通用问答统一写入 `default` 学习空间；学习情况页不再强制要求选择教材，并可按科目查看概念、活动与复习队列。
- 学习情况页新增“最近问答题干”，通用问答即使没有形成严格概念，也会保留完整问题并参与每日问答统计。
- 通用问答在回答完成后的后台反馈阶段启用概念抽取降级；仅保留置信度不低于 0.85、且概念名或有效别名直接出现在问题中的严格概念，其余仅存为候选，不影响复习统计。
- 有教材问答仍优先使用本地知识图谱关联，不新增 LLM 调用；知识关联增强仍只对真实教材开放。

### Validation

- 后端定向回归：7 passed（反馈节点与学习记忆 API）。
- 前端 TypeScript 与 Vite 生产构建：通过。
# 2026-07-18 Electron sidebar and window-control fixes

- Standardized expanded and collapsed sidebar navigation icons at 18px, including the sidebar toggle icons.
- Kept desktop sidebar states mounted and added a restrained width/cross-fade transition, with a `prefers-reduced-motion` fallback.
- Restored reliable frameless-window control hit testing by giving the title-bar overlay its real 52px height and explicitly keeping the control capsule and buttons out of Electron drag regions.
# 2026-07-18 Learning-summary concept criteria and review feedback

- Unified strict concept/exposure criteria at confidence >= 0.85 plus a direct concept or meaningful alias mention; explicit mistake links remain eligible. Strict concepts count unique names, while high-confidence exposures count events.
- Stopped treating ordinary definition/formula/property requests as automatic weakness. Weak concepts now come from mistakes, explicit learner difficulty, review quality 0-2, or manual marking. Legacy QA-only false positives are ignored in statistics and queues.
- Added an in-progress state and durable success feedback for concept review. Concepts reviewed today are removed from both concept-review queues to prevent repeated no-op clicks.
- Added criterion help text to the three concept metric cards.
## 2026-07-16 - 扫描教材按页抽题与桌面标题栏避让

- 修复扫描教材已选择 PDF 页码、但既有 OCR 切分缺少页码元数据时无法抽题的问题：现有 source package、MinerU、外部 OCR 和 PDF 文本层均未命中后，对明确选择的最多 8 页执行 Kimi Vision 按页 OCR，并复用页面缓存。
- Kimi 按需阅读统一使用 `KIMI_VISION_MODEL` 与 `MOONSHOT_API_BASE`，避免把正文 LLM 模型名错误发送到 Moonshot Vision 接口。
- 习题工作区顶部增加 Electron 窗口控件安全区，右上角刷新按钮不再被最大化/关闭状态栏遮挡。
- 不修改教材索引、向量库、外部 OCR 切分或学习记录。

### Validation

- 教材抽题定向回归：6 passed。
- 后端完整回归：119 passed，1 条第三方 TestClient 弃用警告。
- 前端 ESLint：通过。
- 前端 TypeScript 与 Vite 生产构建：通过。

## 2026-07-15 - 存储版本治理与稳定教材身份 P0-P1

### P0：版本、备份与原子写入

- 新增 `data/storage_manifest.json`，统一记录业务组件版本，并明确区分不可重建数据、昂贵派生产物和可重建检索索引。
- 学习进度、测验历史、聊天历史和间隔复习卡片改用临时文件 + `fsync` + 原子替换；保持旧 JSON 数组/对象形状，现有直接读取路径无需迁移。
- 备份格式升级到 v2，加入数据 schema、组件版本和数据分类；恢复端可在内存中将 v1 manifest 迁移到 v2，旧备份继续可用。
- 默认备份新增存储组件清单；Chroma 仍是可选的可重建派生索引，未迁入 SQLite。
- 错题库、习题库、学习事件、后台任务和 RAG trace SQLite 文件接入统一迁移执行器，并写入 `PRAGMA user_version = 1`；遇到比程序更新的数据库版本会拒绝静默打开。

### P1：稳定教材身份与生命周期

- 新增版本化 `book_registry.json`，教材使用 UUID `book_id` 作为稳定身份，物理 `storage_name` 与可修改 `display_name` 分离。
- 启动时为现有教材补齐 `book_id` 和元数据；不移动 PDF、进度目录、SQLite 文件或 Chroma collection。损坏的 metadata 会跳过并报告，不会被静默覆盖。
- 教材列表、当前教材、切换和更新响应返回 `book_id`；相关接口兼容旧存储名与新 ID。
- 资料库支持逻辑重命名、归档列表和恢复。逻辑重命名只更新展示名称，物理存储名保持不变。
- 新错题和习题自动写入对应 `book_id`，旧 JSON blob 记录缺少该字段时继续按默认值读取。
- 彻底删除增加影响预览、精确 `book_id` 二次确认和删除前完整安全备份；归档仍不删除任何文件、索引或学习记录。

### Compatibility and validation

- 未执行现有教材文件搬迁、Chroma 重建或真实数据删除。
- v1 备份、无 `book_id` 的教材元数据、旧错题/习题记录及旧学习 JSON 均保留兼容路径。
- 后端最终全量回归：117 passed，1 条第三方 TestClient 弃用警告。
- 前端 ESLint 通过；Vitest 3 个测试文件共 9 项通过；TypeScript 与 Vite 生产构建通过。
- `git diff --check` 通过。
## 2026-07-13 - v1.0.0 教材范围与桌面端体验修复

- 将问答范围从“物理教材文件”提升为逻辑教材范围。具有相同资料组，或同一科目下的主要教材与辅助教材，在对话界面合并为一个范围；当前传感器短书与长书统一显示为“传感器”。
- 保留检索层的主辅优先级：短书继续作为主要来源，长书作为辅助来源参与补充，不删除、不迁移任何教材索引。
- 设置页将“检索角色”改为更易理解的“教材用途”，使用“主要教材 / 辅助教材 / 独立使用”，并直接说明辅助教材补充的资料组及其在问答中的行为。
- 有教材时不再提供通用 QA 入口。首次进入会优先选择当前学科下的逻辑教材范围；只有尚未导入任何教材时才保留通用 QA。
- 合并范围兼容既有历史会话：短书和长书下保存的旧传感器对话会一起显示，加载后归一为传感器学科范围。
- 桌面模式下，新建会话和加载历史会话不再自动折叠侧边栏；紧凑布局仍保持抽屉式自动关闭行为。
- 教材范围菜单改为基于视口定位的浮层，自动选择向上或向下展开，并限制在窗口边界内，修复非全屏时左侧菜单被裁切的问题。
- 收紧“考研助手”和“学习对话”的标题字号，提高学科范围字号，使标题、导航和选择器层级更均衡。
- Electron 顶部标题区域支持标准双击最大化或还原；右上角按钮行为保持不变。

### Compatibility

- 无数据迁移，无索引重建，不修改已有教材、错题、向量库或学习记录。
- 旧会话中保存的传感器短书或长书名称继续有效。
- 显式资料组优先于科目分组；没有有效主要教材的辅助教材组不会被错误隐藏。

### Validation

- Frontend production build passed: `tsc -b && vite build`.
- Frontend lint passed: `eslint .`.
- Frontend unit tests passed: 9 tests across 3 files, including logical textbook-scope grouping and invalid-group fallback.
- Local UI regression passed at 1280x720 and 900x650: sensor scope appeared once, the menu stayed inside the viewport, old short/long-book conversations remained visible, and the desktop sidebar stayed expanded after new/load conversation actions.
- Settings UI regression confirmed the primary/auxiliary labels and the explicit “辅助传感器” guidance.

## 2026-07-13 - Generalize textbook indexing, retrieval groups, and KG enhancement

- Removed inferred prerequisite/extension KG paths from answer generation and concept linking. Runtime KG retrieval now uses evidence occurrences and verbatim formulas only; unverified directional relations remain disabled.
- Added a canonical textbook chunk model that preserves page index, bounding box, formula text, semantic role, section hierarchy, source Markdown, and neighboring chunk IDs through MinerU import.
- Added a schema-3 versioned whole-book Chroma collection. Rebuilds create the new aggregate before switching the collection map, while existing per-chapter collections and lexical indexes remain available for degradation fallback.
- Added opt-in KG enhancement for any imported textbook as a durable background job. The UI estimates the selected excerpt volume and requires explicit confirmation before sending excerpts to the configured external LLM. Extracted names, definitions, aliases, and formulas are checked against source text; no directional relations are generated.
- Replaced sensor-specific retrieval routing with metadata-driven `standalone`, `core`, and `reference` roles. Core/reference books can share an explicit resource group or, when no group is set, the same subject; priorities are configurable without changing code.
- Persisted import source paths so downstream exercise extraction and PDF lookup can use metadata for user-imported books before legacy packaged-data fallbacks.
- Index acceptance remains an internal system check (non-empty/healthy vector and lexical indexes plus rebuild consistency); users are not asked to know or enter chapter or chunk counts.

### Compatibility and migration

- Existing textbook indexes are not deleted or mutated automatically. The schema-3 aggregate is created on the next explicit import/reindex.
- Existing books default to `standalone`, so retrieval behavior does not broaden until a user assigns `core`/`reference` roles.
- Existing packaged sensor/error-theory source aliases remain read-only fallbacks for old data; new imports use recorded metadata paths.

### Validation

- Python compile check passed for all changed backend, ingestion, retrieval, KG, utility, and test modules.
- Frontend TypeScript and Vite production build passed.
- New textbook-generalization regression suite passed with a clean exit: 5 passed.
- Full backend suite completed all assertions: 92 passed, 1 dependency warning in 25.75s. The command wrapper timed out during process cleanup after pytest printed its completed report.
- FastAPI route smoke check confirmed the KG enhancement, estimate, and generic job-status routes are mounted.
- `git diff --check` passed.

## 2026-07-12 - Textbook exercise extraction page scoping

- The PDF picker now navigates the embedded preview to the entered page and the selection action sets both range endpoints to that page, preventing a stale end page from expanding a single-page request into a large range.
- Explicit page-scoped extraction now rejects chunks with unknown page metadata instead of treating them as matches for every page.
- Page resolution now supports zero-based page_idx values, page/page_number/pdf_page/page_no fields, source_markdown filenames, and page references.
- Source-package fallback warnings now report the selected range and retain that same range for fallback extraction.

### Validation

- Full backend test suite: 85 passed, 1 dependency deprecation warning.
- Frontend npm production build: passed.

## 2026-07-12 - Runtime shutdown and non-blocking startup

- Background textbook prereading now clears its running flag and persists a terminal completed/stopped/failed status even when reader initialization or progress persistence fails.
- FastAPI startup now exposes /health immediately and performs embedding/vector-store warmup in a daemon thread. The health payload includes a separate warmup state, and embedding initialization is protected against duplicate concurrent loads.
- Chat SSE explicitly closes the underlying graph generator when the client disconnects, allowing generator cleanup to run promptly.
- Electron shutdown now waits for backend cleanup. On Windows it uses taskkill /T /F for the backend PID so Python/PyInstaller and descendant processes are removed before the desktop app exits; updater installation follows the same cleanup path.

### Validation

- .\\venv310\\Scripts\\python.exe -B -m pytest -q -p no:cacheprovider: 83 passed, 1 dependency deprecation warning.
- node --check desktop/main.cjs and git diff --check: passed.

## 2026-07-12 - Harden PDF preview, durable answer generation, and OCR highlight lookup

- Served textbook PDFs with an explicit inline content disposition and reduced the exercise PDF modal to a compact desktop-friendly size.
- Hid the unfinished agentic review-plan actions and reserved title-bar space for Electron window controls.
- Reworked the exercise workspace into a full-width question followed by editable user-answer and standard-answer areas.
- Moved standard-answer generation to persistent background jobs. The frontend resumes queued/running jobs after navigation and only saves the generated draft after user review.
- Fixed chapter and subsection highlight source discovery to prefer the populated external OCR output and infer chapter boundaries for legacy chunks without page metadata.

### Validation

- Confirmed the packaged sensor PDF exists and is returned as application/pdf with an inline filename header; Chromium rendered it in the page-select modal.
- Confirmed the real short-book OCR source returns 32 chunks for chapter 1 and 18 chunks for its first subsection.
- Added regression coverage for durable answer jobs and page-less external OCR chunks; the full backend suite passed with 81 tests and the frontend production build passed.

---
## 2026-07-12 - Merge sensor course scope, restore TOC, and ground exercise answers

- Unified the normal frontend scope selector into one 专业课/传感器 entry displayed as “传感器（短书重点 + 长书补充）”; the highlight repository intentionally keeps the two physical books separate.
- Canonicalized sensor retrieval to use 传感器短书 as the primary KG/vector/BM25 source and 传感器长书 as the lower-priority reference source, including legacy long-book selections.
- Kept the existing core/reference reranking bias so short-book evidence wins when both books cover the same concept, while long-book chunks can fill missing details.
- Restored data/progress/传感器短书/_chapters.json from Chapter.md: 13 chapters and 65 subsections. The former 479-item OCR-heading file is preserved as _chapters.bak_before_chapter_md_restore_20260712.json.
- Changed chapter persistence to collapse external OCR heading/chunk records into a real TOC before saving, preventing future reimports from exposing hundreds of chunks as chapters.
- Tightened chapter-highlight generation to evidence-only OCR summarization: no model-memory completion, self-authored questions, external analogies, or internal chunk identifiers. Bumped the prompt version so old artifacts are marked stale.
- Replaced the inline exercise PDF iframe with a large modal viewer that opens on textbook selection or page entry, supports direct page navigation, and can copy the selected page into the extraction range.
- Added exercise answer draft APIs and UI: retrieve with the same hybrid textbook strategy as QA, enforce the evidence gate, generate an editable answer draft, and save only after user review.

### Validation

- Python AST validation passed for all changed backend/retrieval/highlight modules; the full backend suite passed: 79 tests, 1 deprecation warning.
- Frontend TypeScript and Vite production build passed; this is the static frontend served by the Electron backend.
- The actual highlight service returned 13 chapters / 65 subsections, including “第二节 等效电路与测量电路” at p107.
- A read-only “霍尔效应是什么” probe returned 6 grounded evidence items; short-book evidence occupied the top two ranks. Runtime role fallback now labels legacy long-book lexical rows as reference without requiring an index rebuild.

---
## 2026-07-12 - Restore chat concept feedback after external OCR index rebuild

- Backed up the three imported textbooks' existing learning metadata under `data/backups/kg_learning/20260711-235745` before generating knowledge graphs.
- Added `scripts/build_external_ocr_knowledge_graph.py` to assemble runtime knowledge graphs from the existing reviewed OCR concept candidates and long-book concept links without repeating LLM extraction.
- Generated local runtime graphs for 传感器短书 (282 concepts), 传感器长书 (86 linked concepts), and 误差理论与数据处理 (184 concepts) under each book's `hybrid_auto_external` directory.
- Updated `KnowledgeGraph` discovery to load `hybrid_auto_external` graphs and updated the three-book OCR index rebuild script to regenerate matching graphs after vector indexing.
- Mirrored runtime graphs into each book's progress seed and desktop/sample_data_three_books, so packaged Electron installs can load the same graphs from user data without relying on the repository-level MinerU directory.
- Changed strict chat exposure acceptance from confidence 1.0 to 0.85 while retaining the direct question mention requirement and generic-alias exclusion. Uncertain or indirect matches remain candidates.
- Preserved stable concept IDs using canonical-name hashes so repeated rebuilds do not break existing ConceptMemory links.

### Validation

- Runtime graph loading passed for all three books; concept counts were 282 / 86 / 184.
- Concept-link quality probes found 压阻效应, 传感器, 系统误差, and 随机误差 from representative questions.
- End-to-end learning write probe for “什么是压阻效应” linked the canonical concept at confidence 0.88 and increased the formal exposure count from 0 to 1.
- Targeted feedback and system-health tests passed: 5 passed, 1 warning.

---
## 2026-07-10 - CPU-only desktop installer with three-book sample data

- Audited the desktop release changes after the previous CUDA DLL packaging failure.
- Confirmed the release dependency set pins torch 2.11.0+cpu and the GitHub desktop workflow installs requirements-release.txt.
- Found two remaining verification gaps: torch.cuda.is_available() can be false for a CUDA build without a working driver, and the old post-build check allowed a complete CUDA DLL set to pass.
- Hardened scripts/build-desktop-backend.ps1 to require an explicit +cpu torch version, require torch.version.cuda to be null, validate required sample data, and fail on any CUDA binary or PE import.
- Added scripts/verify_cpu_only_build.py, which parses Windows PE import tables without third-party dependencies and checks every packaged EXE/DLL, including shm.dll.
- Bundled desktop/sample_data_three_books as the seed dataset: 6435 files / 689.6 MiB, including the PDFs, OCR imports, progress/KG data, CPU embedding model, and clean Chroma index for 传感器短书、传感器长书、误差理论与数据处理. 优化设计 remains excluded.
- Rebuilt the PyInstaller backend and generated release/kaoyan-assistant-desktop-setup-0.1.0.exe.

### Validation

- Build environment: torch 2.11.0+cpu, torch.version.cuda=null, torch.cuda.is_available()=False.
- Fresh backend build passed the PE verification: 67 EXE/DLL files inspected, zero CUDA/NVIDIA binary names, and zero CUDA import references.
- Packaged shm.dll imports torch_cpu.dll and c10.dll; it does not reference torch_cuda.dll.
- Packaged seed contains 6435 files. All three PDF hashes match the source seed, and vector_db/chroma.sqlite3 also matches.
- Installer size: 564147970 bytes (538.0 MiB).
- Installer SHA-256: 57BFE1C17C539968BB24A5701B2F2AF9E258EE8D71032D5BD6338024C9ABE9E7.
- Frontend production build, PyInstaller backend build, and electron-builder NSIS build passed.
- A packaged-process /health smoke launch was attempted but blocked by the Codex execution-approval quota; this was not counted as passed.

---
## 2026-07-10 - High-priority reliability and local data safety fixes

- Moved streaming feedback persistence off the user-visible completion path. Streaming and non-streaming answers now survive learning-memory write failures; the SSE done event is no longer replaced by an error.
- Split local KG concept linking from background learning records and removed the automatic post-answer LLM concept-extraction fallback, preventing a hidden second LLM call before completion.
- Replaced automatic deletion of non-empty SQLite WAL/SHM/journal files with conservative recovery that removes only zero-byte artifacts and preserves files that may contain recoverable transactions.
- Added a URL scheme allowlist and a restrictive Content Security Policy to generated chapter-highlight HTML; executable, data, file, and protocol-relative links are no longer rendered as anchors.
- Lifted active chat cancellation into ChatContext, added AbortSignal support for non-streaming chat, and guarded stream callbacks by request generation so new/loaded conversations cannot be overwritten by stale events.
- Added striped per-conversation locks around JSON read-modify-write persistence to prevent concurrent message loss.
- Added regression coverage for stream completion, no automatic feedback LLM call, concurrent conversation writes, conservative SQLite recovery, and chapter-highlight HTML safety.

### Validation

- Full backend test suite passed: 71 passed, 3 warnings.
- Targeted high-priority regression suite passed: 12 passed, 3 warnings.
- Frontend tests passed: 2 test files, 7 tests.
- Frontend production build passed.
- Frontend lint completed with no errors and the existing HighlightRepositoryDialog.tsx hooks dependency warning.

---
## 2026-07-03 - RAG retrieval hardening and Chroma recovery

- Preserved final prompt chunk metadata in retrieval state via `retrieval_debug_items`, including rank, chapter, chunk id, source, role, section title, page index, direct-hit flag, TOC-like flag, and preview text.
- Changed the RAG evaluator to score the final prompt chunks instead of an intermediate KG-only order, and added `bootstrap` support for expanding KG-derived golden sets.
- Improved KG concept ranking so exact short concept names win over longer partial matches, while TOC/directory chunks are filtered or downranked before prompt assembly.
- Added section title and page index metadata to newly built vector chunks.
- Added `scripts/rebuild_vector_store_from_mineru.py` to safely rebuild Chroma from MinerU middle chunks with timestamped backups.
- Rebuilt the optimization-design vector store from MinerU output. Previous vector DBs were kept at `data/vector_db.backup-20260703-221607` and `data/vector_db.backup-20260703-222412`.
- Kept third-layer generated-answer evaluation opt-in; the external API retry was not used because it would send local textbook context outside the machine without explicit authorization.

### Validation

- `./venv310/Scripts/python.exe -B -m pytest tests/test_rag_retrieval_eval.py tests/test_rag_degradation.py tests/test_chat_stream_reliability.py -q` passed: `8 passed, 3 warnings`.
- `./venv310/Scripts/python.exe -B scripts/evaluate_rag.py run --golden data/eval/rag_golden_optimization_40.jsonl --output data/eval/rag_eval_report_40_top_level.json` completed outside the Windows sandbox so Chroma/SQLite journal writes could run normally.
- `./venv310/Scripts/python.exe -B scripts/evaluate_rag_ir_measures.py --report data/eval/rag_eval_report_40_top_level.json --output data/eval/rag_eval_ir_measures_report.json` passed using the external `ir_measures` library.
- Final 40-sample report: retrieval status `ok=40`, Hit@1 `0.775`, Hit@3 `0.975`, Hit@5 `1.0`, MRR `0.8729166667`, expected chapter hit rate `1.0`.
- External `ir_measures` cross-check matched the retrieval metrics and added ranking quality scores: `R@1=0.775`, `R@3=0.975`, `R@5=1.0`, `R@10=1.0`, `RR@10=0.8729166667`, `nDCG@3=0.8946394630`, `nDCG@5=0.9054063770`, `nDCG@10=0.9054063770`.
- Non-escalated SQLite probes still fail in the restricted Windows sandbox with `disk I/O error`; escalated local probes and the rebuilt Chroma evaluation succeed, indicating the observed failure is sandbox/journal related rather than a remaining retrieval-node crash.

---

## 2026-07-03 - Local RAG evaluation harness

- Added `scripts/evaluate_rag.py` for three-layer RAG checks: deterministic retrieval metrics, context relevance proxies, and optional generated-answer quality proxies.
- Added a starter JSONL golden set at `data/eval/rag_golden_optimization.jsonl` for the current optimization-design textbook index.
- Kept external evaluator libraries out of runtime dependencies; generated-answer checks are opt-in with `--with-generation` so retrieval experiments can run without API/network access.

### Validation

- `./venv310/Scripts/python.exe -B scripts/evaluate_rag.py --help` passed.
- `./venv310/Scripts/python.exe -B scripts/evaluate_rag.py run --limit 6 --output data/eval/rag_eval_report.json` completed; vector retrieval degraded because Chroma returned SQLite `disk I/O error`.
- `./venv310/Scripts/python.exe -B scripts/evaluate_rag.py run --limit 1 --with-generation --output data/eval/rag_eval_report_generation_sample.json` was attempted without escalation and recorded `Connection error`; escalated external API retry was rejected because it would send local textbook context to an external LLM.

---

# 2026-07-03

- Refined the Electron-only startup and window chrome polish: `desktop/loading.html` now uses the current black/white/blue Apple-inspired visual language with a frosted-glass panel, subtle entrance motion, reduced-motion fallback, and readable Chinese startup/error copy.
- Changed the Electron title controls from a full-width top strip into a floating glass control capsule with a narrow invisible drag strip, so the desktop app no longer looks like a browser page wrapped by a separate title bar.
- Kept the glass/motion treatment scoped to Electron startup/chrome as a low-risk trial before applying similar transitions to broader web/Electron modal surfaces.
- Added frontend typography tokens and mapped the Electron desktop chat shell, sidebar, home cards, toolbar, and composer to a smaller unified type scale.

### Validation

- `./venv310/Scripts/python.exe -B scripts/check_encoding.py --json encoding_audit_report.json --fail-on-issues` passed: `invalid_utf8=0`, `bom_files=0`, `suspicious_files=0`.
- `npm.cmd run build` passed.
- `npm.cmd run lint` completed with no errors and the existing `HighlightRepositoryDialog.tsx` React hooks dependency warning.

---
# Patch Notes - Kaoyan Assistant

This file records version changes, bug fixes, migration notes, validation results, and environment repair records.

Note: Earlier historical entries contained mojibake from an encoding mismatch. Those damaged details were compressed on 2026-07-03 instead of being guessed back into Chinese text. For long-term constraints and architecture, use `AGENTS.md`.

---

## 2026-07-03 - Stage closeout cleanup

- Cleaned `patch_notes.md` so the file is UTF-8 readable and no longer carries historical mojibake blocks.
- Kept this file focused on durable release notes and validation results; unstable or damaged historical prose was replaced with this explicit note.

### Validation

- `./venv310/Scripts/python.exe -m pytest -q` passed: `59 passed, 3 warnings`.
- `./venv310/Scripts/python.exe -B scripts/check_encoding.py --json encoding_audit_report.json --fail-on-issues` passed: `invalid_utf8=0`, `bom_files=0`, `suspicious_files=0`.
- `npm.cmd run lint` completed with no errors and one existing React hooks dependency warning in `HighlightRepositoryDialog.tsx`.
- `npm.cmd test` passed outside the Windows sandbox after the sandboxed run hit `spawn EPERM`: `2 passed`, `7 passed`.
- `npm.cmd run build` passed.

---

## 2026-07-03 - Controlled Learning Tool Registry

- Added `backend/tools/` with a controlled tool registry for textbook search, concept search/linking, due mistakes, mistake stats, review-plan building, and confirmation-only write proposals.
- Added `/api/agent/tools`, `/api/agent/tools/call`, and `/api/agent/read-only` as the first read-only agent orchestration surface.
- Mounted the new agent router in `backend/main.py`.
- Added frontend API client helpers and TypeScript response types for listing tools, calling a tool, and running the read-only agent.

### Validation

- `python -m pytest tests/test_agent_tools.py -q` passed in the original feature run.
- Importing `backend.main.app` confirmed `/api/agent/read-only` was registered.

---

## 2026-07-03 - Read-only agent frontend entry points

- Connected the controlled read-only agent to chat quick workflows for today's review plan and recent weak-point/mistake analysis.
- Added `AgentResultCard` to show synthesized answers, collapsed tool evidence, and confirmation-only pending actions.
- Added an AI review-plan action to the Learning page header.

### Validation

- `npm.cmd run build` passed in the original feature run.
- `python -B -m pytest tests/test_agent_tools.py -q` passed in the original feature run.

---

## 2026-07-03 - Project encoding audit

- Added `scripts/check_encoding.py` to scan project text files for UTF-8 decode failures, BOMs, replacement characters, long question-mark runs, and common Chinese mojibake fragments.
- Removed UTF-8 BOM noise from source and documentation files.
- Fixed mojibake in `memory/exercise_importer.py` prompt text, `knowledge/concept_memory.py` docstrings, and affected tests.
- Recorded that `patch_notes.md` was the only remaining suspicious file before this cleanup.

### Validation

- `python -B scripts/check_encoding.py --json encoding_audit_report.json` previously reported `invalid_utf8=0`, `bom_files=0`, and `suspicious_files=1` for `patch_notes.md`.
- The closeout run should regenerate this report after the cleanup.

---

## 2026-07-03 - Chapter highlight repository task state and compact layout

- Fixed chapter-highlight repository progress so background-generation state only appears for the matching selected book, chapter, section, and job target.
- Bound highlight jobs to a concrete generation scope and surfaced completion prompts that jump to the generated highlight result.
- Moved the highlight repository dialog to a portal attached to `document.body`, improving compact-window and Electron layout behavior.
- Lowered the Electron desktop minimum window size to `720x560` to support compact layout verification.

### Validation

- `npm.cmd run build` passed in the original feature run.
- Full-chapter highlight generation remained serial by section; this is still the primary latency point.

---

## 2026-07-03 - Mistake image crop interaction

- Reworked mistake-image capture cropping from numeric sliders into a draggable selection rectangle on the image.
- Added drag-to-move, eight edge/corner resize handles, and drag-to-create region selection.
- Preserved brightness, contrast, sharpening, and black-white scan tuning controls.

### Validation

- `npm.cmd run build` passed in the original feature run.

---

## 2026-07-03 - Chapter highlight background task behavior

- Fixed chat quick actions so background chapter-highlight generation no longer blocks unrelated chat workflows.
- Added duplicate-scope reuse and serial execution for chapter-highlight background jobs.
- Reduced extra LLM repair calls by preferring local LaTeX cleanup and validation before one optional formula repair pass.
- Reviewed other long-task paths: textbook import and external OCR import already run as background jobs; mistake OCR/solve, reports, and random practice remain local synchronous actions.

### Validation

- `npm.cmd run build` passed in the original feature run.
- Import checks for `ChapterHighlightService` and `HighlightJobStore` passed in the original feature run.

---

## 2026-07-02 - Study cockpit, book management, and highlight background tasks

- Added a richer chat home panel with current subject/textbook context, due-mistake review, weak-concept review, random exercise, highlight, report, and quick mistake capture actions.
- Added settings-center textbook management so imported books can have their subject corrected and can be set as the current chat book without renaming paths or touching indexes.
- Added `PATCH /api/books/{book_name}` for safe textbook metadata updates.
- Added chapter-highlight deletion for generated artifacts.
- Adjusted exercise Word/PDF import copy to clarify that low-confidence repair uses the text LLM backend by default.

### Validation

- `./venv310/Scripts/python.exe -m pytest -q` passed in the original feature run: `56 passed, 3 warnings`.
- `npm.cmd run build` passed.
- `npm.cmd run lint` passed.
- `npm.cmd test` passed after rerunning outside the Windows sandbox EPERM.

---

## 2026-07-02 - Chapter highlight split and frontend lazy rendering

- Split `knowledge/chapter_highlights.py` into focused modules for source assembly, LLM generation, LaTeX validation/repair, artifact writing, shared types/constants, and background job management.
- Preserved public imports for `ChapterHighlightService`, `ChapterHighlightError`, `PROMPT_VERSION`, and `HighlightJobStore`.
- Lazy-loaded rich Markdown/KaTeX rendering through `MarkdownRenderer.tsx`.
- Added `useVisibleList()` and applied client-side pagination to long exercise and mistake lists.
- Extracted settings health polling into `useSystemHealth()`.

### Validation

- `./venv310/Scripts/python.exe -B -m pytest tests/test_generator.py tests/test_job_manager_and_roles.py -q` passed in the original feature run: `15 passed`.
- `./venv310/Scripts/python.exe -B -m pytest -q` passed in the original feature run: `56 passed, 3 warnings`.
- `npm.cmd run build` passed.
- `npm.cmd run lint -- --no-cache` passed.

---

## 2026-07-02 - Retrieval isolation and main workflow hardening

- Scoped new Chroma collections by `book_name + chapter_title`, with legacy chapter-only collections still readable as fallback.
- Rebuilt target scoped collections before writing new documents to prevent duplicates and stale chunks.
- Passed active `book_name` into planner, retrieval, chapter teaching, and mistake explanation RAG calls.
- Added safe vector-store adapters so Chroma failures degrade instead of breaking user-facing flows.
- Fixed chat quick mistake capture book loading, textbook import polling cleanup, external OCR output copy, and chat stop behavior.
- Lazy-loaded frontend route bundles.

### Validation

- `./venv310/Scripts/python.exe -m pytest tests/test_job_manager_and_roles.py tests/test_external_mineru_output_import.py tests/test_rag_degradation.py tests/test_chat_stream_reliability.py -q` passed in the original feature run: `13 passed, 3 warnings`.
- `./venv310/Scripts/python.exe -m pytest -q` passed in the original feature run: `56 passed, 3 warnings`.
- `npm.cmd run build` passed.
- `npm.cmd run lint -- --no-cache` passed.

---

## 2026-07-01 - External OCR output import path

- Added `import_textbook_from_mineru_output()` for workflows where MinerU runs on another machine and the desktop app only builds local chapters and Chroma indexes.
- Added `POST /api/books/import-mineru-output` for safe zip uploads with path traversal checks.
- Changed book listing/switching so externally imported books can appear and be selected without a local source PDF.
- Exposed `MINERU_API_URL` as the recommended external-service path and kept local MinerU CLI as advanced configuration.

### Validation

- `./venv310/Scripts/python.exe -m pytest tests/test_external_mineru_output_import.py -q` passed in the original feature run: `2 passed`.
- `./venv310/Scripts/python.exe -m pytest -q` passed in the original feature run: `55 passed, 3 warnings`.
- `npm.cmd run build` passed.
- `npm.cmd run lint -- --no-cache` passed.

---

## 2026-07-01 - Exercise import LLM repair and release lock

- Changed `memory/exercise_importer.py` to produce scored candidate splits before labeling.
- Added optional low-confidence LLM repair for uncertain exercise-import blocks while keeping the rule pipeline as the default.
- Added `split_confidence`, `split_reasons`, `refined_by_llm`, and `summary.llm_refined` to exercise analysis responses.
- Added `requirements-release.txt` as a release-only pinned backend/build dependency set.
- Updated the desktop backend build script to exclude legacy agents, OCR runtimes, and extra data-science/dev packages.

### Validation

- `./venv310/Scripts/python.exe -m pytest tests/test_exercise_importer.py tests/test_exercise_file_importer.py -q` passed in the original feature run: `5 passed, 3 warnings`.
- `./venv310/Scripts/python.exe -m pytest -q` passed in the original feature run: `53 passed, 3 warnings`.
- `npm.cmd run build` passed.
- `npm.cmd run lint -- --no-cache` passed.

---

## 2026-07-01 - Learning event log and packaging trim

- Added `memory/learning_events.py`, a SQLite append-only timeline for chat QA, concept exposure/candidates, mistakes, and exercise actions.
- Added `book_name`, `subject`, and `conversation_id` plumbing to concept exposure and chat graph state.
- Changed mistake and exercise APIs to write best-effort learning events for add/review/explain/practice/import/transfer actions.
- Trimmed the desktop PyInstaller build by excluding retired UI/dev packages.

### Validation

- Backend tests and frontend build passed in the original feature run.

---

## 2026-06-23 to 2026-06-30 - Historical compressed notes

The detailed historical notes for this period were damaged by mojibake before this cleanup. The reliable high-level record is:

- Added and iterated the exercise bank, including manual entry, Word/PDF import, rule-based candidate splitting, batch add, status updates, and mistake/exercise transfer flows.
- Added mistake image OCR/solve workflows, Kimi Vision OCR configuration, image preprocessing, and SM-2 review improvements.
- Hardened streaming chat, including SSE stage ordering, frontend accumulation safety under React StrictMode, long-answer rendering fallback, LaTeX sanitization, and ASGI error conversion.
- Improved retrieval with KG exact hits, vector fallback, role-aware retrieval, example completeness handling, and Chroma degradation.
- Added desktop packaging, first-run resource guidance, local asset status/download APIs, sample-data preparation, and data-safety tooling.
- Added chapter highlight generation, HTML artifacts, highlight reading page, chapter/section navigation, image support, LaTeX validation, and job-backed generation.
- Added project-level `AGENTS.md` conventions and moved durable architecture guidance out of patch notes.

### Validation

- Multiple historical runs of backend pytest and frontend production builds passed during those changes.
- Exact old command outputs are not reconstructed here because the source entries were encoding-damaged.

## 2026-07-04 OCR 教材向量索引导入

- 新增 `scripts/import_ocr_chunks.py`，用于将租卡 OCR 产物 `data/imports/kaoyan_ocr_20260704/deliverables/*_chunks.jsonl` 导入 Chroma。
- 已导入三本教材：`传感器短书` 562 chunks、`传感器长书` 943 chunks、`误差理论与数据处理` 511 chunks。
- `传感器短书` 与 `误差理论与数据处理` 标记为 `core`，`传感器长书` 标记为 `reference`，metadata 保留 `subject`、`book_role`、`rag_priority`、`review_status`、`source_markdown`。
- 因 `D:\AI\agent\kaoyan-assistant` 所在目录的 Windows 压缩/SQLite I/O 问题，Chroma 最终写入 `C:\tmp\chroma_smoke_test`，并在 `.env` 中设置 `VECTOR_DB_PATH=C:\tmp\chroma_smoke_test`。
- 验证：`get_vector_store()` 可加载 1589 个 collection；检索 `霍尔效应是什么` 能命中 `传感器短书` 中的定义 chunk。

## 2026-07-04 OCR 检索聚合索引优化

- 为三本 OCR 教材新增按书聚合 Chroma collection：`传感器短书`、`传感器长书`、`误差理论与数据处理` 各 1 个 aggregate collection，同时保留原有章节级 collection 供精确章节检索使用。
- `ChapterVectorStore.search_all()` 优先使用 book aggregate collection；无聚合索引时回退到旧的逐章节扫描。
- 启动预加载从全部章节 collection 改为只预加载 aggregate collection，避免 1500+ collection 冷启动开销。
- 最终 rerank 透传并使用 `book_role` / `rag_priority` metadata，使 `core` 教材优先于 `reference` 补充材料。
- 验证：`霍尔效应是什么` 在 `传感器短书` 内检索从约 40s 降至约 0.6s；跨书检索 `不确定度怎么合成` 扫描 3 个 aggregate collection，约 1.1s 返回 `误差理论与数据处理` 相关章节。


## 2026-07-04 OCR 教材 LLM 概念抽取与长书挂接

- 新增 scripts/extract_kg_candidates.py，支持对 OCR chunk 增量调用 DeepSeek V4 Pro 抽取 KG 候选，并过滤 thinking 内容，只落结构化 JSONL。
- 已对 传感器短书 与 误差理论与数据处理 的高价值语义块（definition/formula/theorem/derivation/example/exercise）完成主干概念抽取。
- 已按 传感器短书 高置信概念，将 传感器长书 高价值语义块挂接为 same_concept、expansion、proof、condition、edge_case、example_more、background 等关系。
- 产物位于 data/imports/kaoyan_ocr_20260704/deliverables/：kg_candidates_sensor_core.jsonl、kg_candidates_error_theory.jsonl、concept_links_sensor.jsonl、kg_review_queue.jsonl。
- 验证：传感器短书 165 chunk rows / 292 concepts；误差理论与数据处理 181 chunk rows / 228 concepts；传感器长书 364 links、32 no-match rows；低置信 review queue 49 rows。
## 2026-07-04 教材内习题抽取导入

- 新增教材抽题入口：`/api/exercises/textbook-analyze`，从已导入教材中按章节或页码范围提取候选题，并复用现有规则切题、低置信 LLM 修复和人工确认导入流程。
- 新增 `memory/textbook_exercise_importer.py`，抽取顺序为 chapter highlight `source_package.json`、MinerU `*_middle_chunks.json`、PDF 文本层；不修改现有教材索引、Chroma 向量库或题库结构。
- 前端习题库新增“从当前教材抽题”面板，支持章节/页码范围、习题页优先/章节例题/整页文本三种模式，候选题继续由用户勾选确认后入库。
- 验证：`python -m pytest tests/test_textbook_exercise_importer.py tests/test_exercise_importer.py -q` 通过；`npm run build` 通过；本地“优化设计”教材 page 50 可从 source_package 抽出候选题。

补充验证：已按 Electron 桌面端路径执行构建。`scripts/build-desktop-backend.ps1` 生成 `build/backend/backend_server/backend_server.exe`；`desktop/npm run dist` 生成 `release/win-unpacked` 与 `release/kaoyan-assistant-desktop-setup-0.1.0.exe`，内置 `frontend/dist` 时间戳已更新。

## 2026-07-04 教材问答概念与 OCR 抽题修复

- 修复流式问答 `done` 事件在 `feedback_node` 后台执行前就返回的问题，现在会把本轮 `linked_concepts` 同步写回 SSE state，避免非《优化设计》教材问答阶段前端拿不到概念链接。
- 教材抽题新增外部 OCR JSONL 读取路径，支持 `data/imports/.../*_chunks.jsonl` 产物；未找到 MinerU `middle_chunks` 时不再直接退化为“未提取到可切分文本”。
- Books API 对 `external_ocr_jsonl` 导入产生的“chunk 标题目录”做运行时目录折叠，从内嵌目录文本解析真实章节/小节，不改写现有 `_chapters.json` 数据文件。
- 前端习题库的教材抽题面板新增源 PDF/origin.pdf 预览入口，用户可先查看教材页，再输入起止页执行抽题。`r`n- 源 PDF 查找新增 `D:\OCR_NEEDED` 别名：`传感器短书 -> CGQ_1.pdf`、`传感器长书 -> CGQ_2.pdf`、`误差理论与数据处理 -> WC.pdf`，不复制原件。

### Validation

- `python -B -c "compile(...)"` 解析检查通过：`graph/main_graph.py`、`memory/textbook_exercise_importer.py`、`backend/api/books.py`。
- OCR 教材目录加载已折叠：`传感器短书` 13 章、`传感器长书` 12 章、`误差理论与数据处理` 7 章；外部 OCR 抽题路径返回 `external-ocr-jsonl` 文本。
- `npm.cmd run build` 通过。

## 2026-07-05 三本教材目录与桌面安装包打包

- 将 `Chapter.md` 中 Kimi 识别的目录写入三本教材：`传感器短书` 13 章、`传感器长书` 12 章、`误差理论与数据处理` 7 章；覆盖前保留 `_chapters.bak_chapter_md_*` 备份。
- 将 `D:\OCR_NEEDED\CGQ_1.pdf`、`CGQ_2.pdf`、`WC.pdf` 复制为 `data/books/传感器短书.pdf`、`传感器长书.pdf`、`误差理论与数据处理.pdf`，供桌面端 PDF 预览和 seed 数据使用。
- 新增错题/习题详情页删除入口，复用已有后端 DELETE API；删除后同步刷新列表、复习队列和统计状态。
- 构建了仅包含三本新教材的干净 Chroma 向量库与 `desktop/sample_data_three_books` seed 数据，不包含 `优化设计`。
- `scripts/build-desktop-backend.ps1` 增加 `-SampleDataDir` 参数，允许桌面后端构建显式指定 seed 数据目录。
- PyInstaller 输出中移除了本应用 CPU embedding 不需要的 CUDA/cuDNN DLL，使 NSIS 安装包避开 2GB mmap 限制；最终生成 `release/kaoyan-assistant-desktop-setup-0.1.0.exe`。

验证：

- `npm run build`：通过。
- `python -B` 编译检查 `backend/api/books.py`、`memory/textbook_exercise_importer.py`、`graph/main_graph.py`、`ingestion/pdf_parser.py`：通过。
- `scripts/build-desktop-backend.ps1 -SkipSampleDataPrepare -SampleDataDir desktop\sample_data_three_books`：通过。
- `npm run dist`：通过，生成 NSIS 安装包。
- release 内置 `sample_data` 抽查：6435 个文件，含三本 PDF，不含 `优化设计` 路径。
## 2026-07-11 教材 RAG 准确率 P0-P3 改造

### 原因与数据修复

- 定位“电容式传感器是否适合动态测量”只回答“质量轻”的根因：运行环境曾指向 `C:\tmp\chroma_smoke_test`，正式 `data/vector_db` 中没有《传感器长书》索引，模型实际依赖自身知识作答。
- 将运行时 `VECTOR_DB_PATH` 恢复为项目约定的 `./data/vector_db`；旧烟雾测试库保留，不执行删除。
- 为《传感器长书》在正式库中重建 12 个章节 collection、1359 个结构化 chunk；Dense 与 BM25 索引数量一致，健康检查通过。
- 本地 `torchvision` 与 `torch` 二进制不匹配会阻断 `sentence-transformers`。文本 Embedding 加载阶段现会隔离不需要的可选 `torchvision` 探测，不卸载或重装依赖。

### P0：索引完整性与安全降级

- 本地 PDF 导入现在也会构建教材索引，不再只解析章节而返回 `indexed_chunks=0`。
- 新增每本教材的 `collection_count`、`chunk_count`、`lexical_chunk_count`、`healthy` 健康统计，并在 Books API 列表中返回。
- 新增 `POST /api/books/{book_name}/reindex`，只重建派生检索资产，保留 PDF、OCR 原文、错题和学习记录。
- 教材存在但索引为空时返回 `book_index_empty`；教材模式无直接证据时强制拒答，不再静默使用模型参数知识补齐。

### P1：背诵准确模式与混合检索

- 新增 `factual_recall` 意图，用于原因、特点、优缺点、条件和并列要点等专业课背诵问题。
- 新增持久化本地 BM25 索引，采用 Dense Top 20 + BM25 Top 20 + RRF 融合；取消“第一个 role 有结果就停止”的硬过滤，role 改为软加权。
- 原 `_merge_and_rerank()` 的固定优先级排序改为问题相关的融合评分，保留 Dense/BM25/KG 来源、覆盖率和最终分数调试信息。
- 新增可选本地 Cross-Encoder 接口；设置 `RERANKER_MODEL_PATH` 后启用，未配置时使用确定性融合精排。
- 生成提示要求每个事实结论由选定教材证据支持；列表题必须穷尽证据中的并列项并附章节、小节、页码和 chunk_id。教材生成温度降为 0.1。
- 对年份、公式编号、英文缩写和数字参数增加精确字面证据约束，避免只有主题相似的段落冒充直接证据。

### P2：结构化切块与上下文补全

- 默认切块由 2000/100 字符调整为 700/80 字符，并优先按 Markdown 标题和自然段边界切分。
- chunk 新增 `section_path`、`parent_id`、`prev_chunk_id`、`next_chunk_id`、`parent_content` 和仅供检索使用的教材/章节前缀。
- Chroma 同时保存带上下文的 `retrieval_text` 与不带前缀的 `raw_content`；生成阶段使用原始教材正文。
- BM25 命中后支持相邻块扩展；公式、例题和列表可沿文档顺序补足上下文。

### P3：评测与回归

- 新增 `evaluation/rag_eval.py`，支持离线计算 Recall@K、MRR、要点完整率以及不可回答题拒答结果。
- 新增 `evaluation/datasets/textbook_recall.jsonl` 首批专业课背诵评测集，以及事实意图、RRF、切块关系、要点完整率和空索引拒答测试。
- 关键回归“电容式传感器是否适合动态测量”在正式库中排名 Top 1，Dense 与 BM25 双命中，同一证据完整包含“静电引力很小、质量很轻、介质损耗小”。
- 当前 10 题离线基线：Recall@10 为 80%，要点召回率为 83.3%；剩余薄弱项主要是完整特点块的标题排序和跨连续小节的列表聚合，作为后续调参基线保留。

### Validation

- `.\venv310\Scripts\python.exe -B -m pytest -q`：77 passed，3 warnings。
- `frontend/npm.cmd run build`：通过，Vite production build 成功。
- 正式《传感器长书》索引健康统计：12 collections / 1359 vector chunks / 1359 lexical chunks。
- 关键案例 Top 1 chunk：`3e87d09788d31566`，章节“第4章 力敏传感器”，融合来源 `dense + bm25`。

## 2026-07-11 传感器问答检索与展示修复

- 从保留的 OCR chunks 重建传感器短书索引：479 个章节 collection、562 个 chunk，并补建 562 条 BM25 索引；未改动长书索引、OCR 源和学习记录。
- 传感器问答改为分层联邦检索：短书为 core 主证据，长书作为 reference 补证；两库保持独立以保留来源追踪。
- 生成提示与前端双重隐藏内部 chunk ID；Markdown 不再保留源文本缩进空白，并折叠过量空行。
- 追问改写不再把所有短问题一律视为追问，只对显式指代词启用上下文；历史输入会清除内部索引号。
- 重建脚本复用项目文本嵌入加载器，规避不兼容 torchvision，并支持 KAOYAN_IMPORT_BOOKS 选择性重建。

验证：Python 语法检查通过；frontend npm run build 通过；短书 Chroma 与 BM25 计数见上。


## 2026-07-11 - P0/P1 evaluation, latency trace, and runtime convergence

- Extended the gold-set evaluator with expected chunk recall/MRR, forbidden-chunk detection, expected-page hits, and per-query retrieval latency.
- Added bounded SQLite RAG traces (last 500 requests) with request ID, fast-path flag, TTFT, total time, stage timings, and evidence metadata; answer text and model thinking are not stored.
- Added `GET /api/system/rag-traces`, trace database health, and LLM runtime-configuration health.
- Added request IDs and elapsed milliseconds to chat SSE events and replaced backend startup/chat `print` diagnostics with structured logging.
- Retired the obsolete Gradio web entry and removed Gradio from the development dependency list. Electron + React + FastAPI remains the supported product path; the root CLI is explicitly legacy.

### Validation

- `python -B -m pytest -q`: 79 passed, 1 dependency deprecation warning.
- `frontend/npm.cmd run build`: passed (TypeScript and Vite production build).
- `git diff --check`: passed.


## 2026-07-12 - 资料库目录统一（方案 B）

- 设置中心合并“教材管理”和“学科管理”为单一“资料库”入口，采用左侧学科/科目树与右侧教材内容区。
- 教材归属不再提供自由文本编辑入口；教材只能在已有目录间移动，未分类教材集中展示。
- 非空学科或科目禁止重命名和删除；后端保存目录前再次校验现有教材归属，避免产生孤儿分类。
- 本次仅更新学科目录与教材 subject 元数据的管理方式，不移动或改名 PDF，不修改章节数据，不删除或重建 Chroma 索引，不迁移学习记录。
- 验证：前端生产构建通过；前端 7 项测试通过；后端 87 项测试通过；当前教材归属只读检查结果为 `used_assignments=['专业课']`、`orphaned=[]`。

- 后续交互修正：每本教材增加“归属到”分组下拉框，可直接选择如“专业课 / 传感器”的二级科目；原有间接移动区已移除。


## 2026-07-12 - 章节重点查看、公式与断网续生成修复

- 桌面端打开重点改为在现有 React 路由内跳转，避免相对地址被 FastAPI 当作服务端路由并返回 404。
- 清理未解析的图片/公式索引，并移除会导致 KaTeX multiple tag 报错的公式编号、标签和引用命令。
- 生成任务按小节保存 generation_checkpoint.json；重新启动同一范围时复用已完成小节，成功后删除断点。前端轮询使用退避重连，连续失败后停止空转并恢复可重试状态。
- 提示词减少非必要逐行推导，增加背诵要点、教材证据支持的直观类比及章内对比联动，同时禁止无依据扩展和自拟题。
- 独立 highlight.html 定位为本机产物；应用内重点页使用打包的 KaTeX，本机离线可显示，直接发送 HTML 不作为可移植分享格式。

### Validation

- 重点相关后端测试：18 passed。
- 前端 TypeScript 与 Vite 生产构建通过。

- 桌面 release 数据支持在 sample_data/mineru_output 中携带 OCR 产物；首次启动时会复制到用户 mineru_output 目录，GitHub sample_data 仍可只保留单本演示教材。

## 2026-07-13 - 产品化 P0：1.0.0 发布、数据恢复与访问边界

### 发布治理

- 新增根 `VERSION`，统一前端、Electron、FastAPI 和设置页版本为 `1.0.0`。
- 新增版本设置/一致性检查脚本；桌面发布 tag 必须与 `VERSION` 一致。
- 新增 CI，发布前强制执行后端测试、前端测试、lint 和生产构建。
- Electron 发布工作流接入可选 Windows 代码签名 secrets；证书本身仍需由发布者提供。

### 数据安全

- 设置中心新增“备份恢复”：默认备份教材、章节、图片、错题、习题和学习记录，可选包含 Chroma 与 MinerU 派生数据。
- SQLite 使用在线 backup API 生成一致性副本；压缩包包含版本化 manifest、SHA-256 和展开安全限制，不包含 `.env` 或 API Key。
- 恢复前自动创建当前状态安全备份；恢复登记后在下次启动、向量库预热前执行目录替换，失败时自动回滚。
- Electron 新增安全重启 IPC，使桌面端可以完成“选择备份 → 安全快照 → 重启恢复”闭环。

### 安全边界

- Docker 默认端口映射收紧为 `127.0.0.1:8000`。
- 非本机 API 访问默认拒绝；配置 `KAOYAN_API_TOKEN` 后使用 `X-Kaoyan-Token` 认证，前端支持通过 URL fragment 一次性写入本地令牌。
- Electron 启用 renderer sandbox，并拦截窗口内外部导航，HTTP(S) 外链交给系统浏览器。

### Validation

- P0 定向测试：9 passed。
- 后端完整测试：99 passed，1 条第三方 TestClient 弃用警告。
- 前端测试：7 passed；ESLint：0 warning / 0 error。
- 前端 TypeScript 与 Vite 生产构建：通过。
- `scripts/check_version_consistency.py`：通过，版本与 lockfiles 均为 `1.0.0`；Electron Node 语法检查通过。


## 2026-07-14 - 习题导入校对工作台与连续练习会话 P0

### 导入校对与数据安全

- 习题候选新增切题边界、选项完整性、题干长度、知识点缺失和题库重复检测；重复检测一次构建题干指纹映射，避免按候选题重复扫描题库。
- 习题页保留完整导入原文作为对照，候选题支持异常/重复筛选、题干/答案/解析/题型/难度/标签/来源/章节编辑、选中合并和按空行拆分。
- 批量导入改为单个 SQLite 事务，记录 `exercise_import_batches` 批次；默认跳过题库已有题和同批重复题，导入完成后可按批次回滚。
- Word/PDF 文件导入支持可选的独立答案文件；仅按明确题号确定性配对，未匹配候选会标记异常，不使用 LLM 猜测答案。
- 新表为兼容性增量创建，不改写现有 `exercises`、错题、教材、Chroma 或学习记录。

### 连续练习会话

- 新增持久化 `exercise_practice_sessions`：固定题目队列、筛选条件、随机种子、当前进度、逐题答案、自评结果、错题关联和完成摘要。
- 习题页支持设置题数、优先复习/随机顺序、自动下一题、暂停、恢复、结束和重启后继续未完成会话。
- “做错”会在记录本题练习结果的同时转入错题本；暂停状态禁止提交，服务端校验提交题目必须与当前会话进度一致。
- 随机模式只打乱按“需复习 → 练习中 → 新题 → 已掌握”选出的优先题池，不会把已掌握题随机混入有限题量。

### Validation

- 后端完整测试：105 passed，1 条第三方 TestClient 弃用警告。
- 前端 Vitest：9 passed。
- ESLint：通过，0 error。
- 前端 TypeScript 与 Vite 生产构建：通过。
- `git diff --check`：通过。

## 2026-07-15 - Electron 学习工作台视觉收敛

### 交互与视觉层级

- 移除全局主按钮胶囊化规则，统一桌面端按钮、导航、输入框和容器圆角，主色只用于当前状态与关键操作。
- 对话首页改为“优先复习 + 其他入口”的任务列表，去除问候语、装饰性 AI 图标和重复推荐卡；空白对话不再重复显示底部快捷工具栏。
- 习题页拆分为“练习 / 题库 / 导入”三个工作区，避免练习、检索、文件导入和候选校对同时堆在同一屏；导入空状态补充确定性流程说明。
- 教材导入页缩短上传区，补充导入目标说明，并将 MinerU 选项改写为面向结果的“扫描件必须完成高质量解析”。
- 学习情况、错题本补充页面说明；知识增强改为“完善知识关联”；错题空状态增加明确的录入入口，并强调 OCR 后人工校对。

### Validation

- 前端 TypeScript 与 Vite 生产构建：通过。
- Electron 开发模式实机检查：对话、学习情况、错题本、习题练习、题库、习题导入、教材导入和设置窗口均可打开；分段切换、导航和空状态无明显溢出。
## 2026-07-15 - 录入流程、教材导入与设置页结构化

### 工作流重构

- 错题录入拆分为“添加题目、校对内容、归因保存”三个阶段；图片 OCR 与看图讲解均先进入可编辑校对步骤，手动录入不再依赖图片或自动讲解。
- 归档步骤始终允许补充来源、学科、章节、标签、难度与错因；保存成功、识别失败和处理中状态使用统一反馈样式。
- 教材导入改为“PDF 教材”和“MinerU 输出包”二选一，避免两套参数与操作同时堆叠；PDF 参数顺序与后端请求保持不变。
- 设置从全局浮层迁移到 `/settings` 独立页面，并加入主导航；服务器健康、版本更新、备份恢复、资料库和模型配置功能保持不变。

### 状态系统

- 新增 `AsyncState` 组件族，统一页面加载骨架、空状态、错误/成功提示和带进度后台任务。
- 教材导入、学习情况、错题录入和设置页已接入统一状态组件。
- 系统健康组件由重复卡片改为可扫描列表，并补全“检索记录”“模型连接”等中文标签及运行状态文案。

### Validation

- 前端 Vitest：9 passed。
- ESLint：通过。
- TypeScript 与 Vite 生产构建：通过。
- `git diff --check`：通过。
- Electron 实机检查：错题添加与手动校对、PDF/MinerU 方式切换、独立设置页及健康状态加载正常。

## 2026-07-15 - 学习情况页去卡片化与页面标题收敛

### 视觉层级

- 学习情况页将四张指标卡合并为单一统计带，只用网格分隔线区分指标，不再为每个数字单独添加圆角容器。
- 待复习错题、今日概念复习和待复习概念合并为连续折叠分组；概念、错题与空状态改用行级留白和稀疏分隔线，移除卡片套卡片结构。
- 高频概念、错题薄弱点和最近每日活动合并为同一分析区；活动详情、教材线索和错题预览使用轻背景层级，不再重复叠加边框与圆角。
- 后台任务状态由双层面板改为单层状态区，保留错误、进度和无障碍语义。

### 页面标题

- 移除学习对话、学习情况、错题本、习题工作区、教材导入和设置标题下方的泛化说明句。
- 顶部页面标题统一为 19px/600 字重；正文中的操作说明、错误信息和真实来源元数据不受影响。

### Validation

- 前端 TypeScript 与 Vite 生产构建：通过。
- ESLint：通过，0 error。
- 前端 Vitest：9 passed。
- 定向 `git diff --check`：通过；相关页面未新增 em dash 字符。
- Electron 窗口视觉检查授权超时，未取得实机截图；应用内浏览器访问本地地址被客户端安全策略阻止，未绕过限制。

## 2026-07-16 - 一级页面标题栏位置统一

### 界面一致性

- 新增共享的 app-page-header 与 app-page-title 规则，统一一级页面标题栏为 64px 最小高度、20px 水平内边距、19px/600 标题和垂直居中。
- 学习对话、学习情况、错题本、习题工作区、教材导入和设置全部迁移到共享规则；移除教材导入与设置标题的居中内容容器。
- Electron 无边框窗口统一为所有一级标题栏预留右上角窗口控件安全区，并保持标题栏内按钮可交互；紧凑布局继续使用相同的 20px 水平基线。

### Validation

- ESLint：通过。
- 前端 Vitest：3 files / 9 tests passed。
- TypeScript 与 Vite 生产构建：通过。
- 应用内浏览器 1280px 桌面视口实测：六个标题栏均为 64px 高，标题左偏移 20px、顶部偏移 19.6px、文字高度 24px。


## 2026-07-18 - 备份恢复安全与练习会话原子性修复

### 备份与恢复

- SQLite 备份仅接受 `sqlite3.backup()` 生成且 `PRAGMA quick_check` 通过的快照；数据库锁定或备份失败时不再退化为缺少 WAL 的主文件拷贝。
- 恢复前始终创建包含向量库和 MinerU 产物的完整安全备份；目标备份未包含的派生数据在恢复时会被失效，避免旧学习数据与新索引混用。
- 待恢复压缩包缺失、pending JSON 异常或安装失败时，记录失败与回滚结果并消费 pending 请求，不再阻塞每次后端启动。
- 恢复后若向量索引已失效，设置页会明确提示重新索引教材。

### 练习会话

- 习题练习记录与会话进度改为同一 SQLite `BEGIN IMMEDIATE` 事务，任一写入失败时整体回滚。
- 重复提交已作答题目时直接返回持久化结果，不再重复增加练习次数。
- 练习会话转入错题本使用稳定错题 ID 和幂等写入；跨数据库写入中断后可安全重试，不会生成重复错题。

### Validation

- 后端完整测试：126 passed，1 条第三方 TestClient 弃用警告。
- 新增回归覆盖 SQLite 备份失败、缺失恢复包、派生索引失效、练习事务回滚和重试幂等。
- ESLint 通过；TypeScript 与 Vite 生产构建通过。

## 2026-07-18 - Learning-state concurrency, local API boundary, and upload limits

### Learning-state consistency

- Added path-scoped re-entrant locks shared by all ConceptMemory, StudyMemory, and SpacedRepetition instances.
- Every read/modify/write operation reloads the latest JSON snapshot while holding the shared lock, preventing background feedback and concurrent API requests from overwriting each other.
- Kept the existing JSON storage format; no user-data migration is required.
- Added multi-instance concurrency regression tests for concept exposures, chat history, and SM-2 cards.

### Local API boundary

- Electron now creates a random 256-bit API token for each launch, requires it in the backend, and bootstraps it into the renderer through a URL fragment that the frontend immediately removes.
- Valid tokens are accepted before the loopback development fallback; packaged desktop requests therefore remain authenticated.
- Development mode rejects unsafe local API requests carrying an untrusted Origin, while trusted Vite origins and non-browser CLI clients remain supported.
- Upload endpoints reject oversized multipart requests from Content-Length before Starlette parses or spools the body.

### Upload and archive limits

- PDF, DOCX, and external MinerU ZIP uploads now use bounded streaming copies, exclusive destination creation, partial-file cleanup, and a minimum free-disk reserve.
- ZIP and DOCX inspection now limits file count, per-member size, total expanded bytes, and compression ratio, and rejects encrypted members, symbolic links, and unsafe paths.
- Failed external-output extraction removes its job-specific partial directory.
- Default limits are configurable through KAOYAN_MAX_* and KAOYAN_MIN_FREE_DISK_BYTES environment variables.

### Validation

- Backend: 137 passed; one existing Starlette TestClient deprecation warning.
- Frontend: 3 files / 9 tests passed; ESLint passed; TypeScript and Vite production build passed.
- Electron main-process syntax and changed Python source syntax passed.
- git diff --check passed (line-ending warnings only).
## 2026-07-18 - 开源发布材料与桌面入口实测

### 项目审计与展示材料

- 基于实际目录、入口、API、持久化和调用链新增 PROJECT_AUDIT.md，并重写根 README。
- 新增 docs/images 下六张 1440 × 900 实机截图，覆盖工作台、资料库、教材问答会话、习题、错题和学习情况。
- 新增无构建工具的 site/ 静态项目页，包含响应式布局、系统明暗模式、真实截图、功能边界与 Roadmap。
- 新增 scripts/seed_docs_demo.py，用稳定 ID 向显式隔离目录写入非个人展示数据，并拒绝正式 data/ 与 desktop/sample_data。

### Electron

- 修复 desktop/main.cjs 中 desktopAppUrl 被错误定义在 loadAppUrl 内部的问题。
- 修复前 Electron 窗口停留在未进入应用的状态；移动为模块级函数后，dev:existing 已进入真实 React 应用并显示首次使用引导。

### Validation

- Python 3.10.11；后端完整测试 137 passed，1 条既有弃用警告。
- 前端 Vitest 3 files / 9 passed；ESLint 和 TypeScript/Vite 生产构建通过。
- FastAPI 隔离实例 health 返回 200；Electron dev:existing 实机进入应用。
- 浏览器自动化在 1440 × 900 和 390 × 844 下通过；主要页面与静态宣传页无控制台错误。
- README 六张图片、site 本地资源和页内锚点均存在；六张 PNG 均为 1440 × 900。
- demo seed 直接运行、幂等运行和受保护路径拒绝均通过。
- 未调用真实付费 LLM、OCR、MinerU，没有构建 Docker、PyInstaller 或 NSIS 产物。
## 2026-07-18 - 静态宣传页截图与配色调整

### 展示体验

- 将截图从 Hero 和功能文本卡中移除，统一放入独立截图资源区。
- 六张缩略图使用固定 16:10 容器，点击后通过原生 dialog 按原始比例展开。
- 功能区保留三个文本入口，可直接打开对应截图；灯箱支持关闭按钮、Escape、点击背景关闭和焦点恢复。
- 页面配色从绿色倾向调整为冷白、灰蓝和单一钴蓝强调色；暗色模式改为中性石墨与海军蓝，不再使用深绿色 token。

### Validation

- 桌面 1440 × 900 与移动 390 × 844 均无横向溢出。
- 6 个截图卡、9 个预览入口和 6 个唯一截图资源均通过检查。
- 所有截图容器比例均为 1.6，灯箱图片成功加载为 1440 × 900。
- 移动导航、灯箱打开/关闭、焦点恢复和控制台检查通过。
- site 本地资源无缺失，JavaScript 语法通过，页面可见文案不含 em dash。
## 2026-07-18 - GitHub Pages 发布

### Deployment

- 新增 `.github/workflows/pages.yml`，从 `site/` 打包并部署静态项目页。
- 仓库 Pages 发布源已切换为 GitHub Actions，并启用默认域名 HTTPS。
- Pages 工作流使用 `actions/checkout@v6`、`actions/configure-pages@v6`、`actions/upload-pages-artifact@v4` 与 `actions/deploy-pages@v4`。
- 公开地址为 `https://jayceto946-byte.github.io/kaoyan-assistant/`。

### Validation

- GitHub Actions `Deploy Project Site` 第二次运行成功，耗时 17 秒。
- 公开页面标题、样式表、6 张截图与 9 个预览入口加载正常。
- 1440 × 900 截图灯箱在公开站点实测可打开，浏览器控制台无错误。

## 2026-07-18 - 隐藏教材默认范围修复

### Fix

- 教材隐藏后若仍是当前对话范围，前端在教材列表刷新完成后会清除该失效选择。
- 切换学科时会同时清除已隐藏或已移除的教材，不再保留陈旧的教材名称。
- 学科没有匹配教材时保持通用问答，不再回退到全局第一本教材。

### Validation

- `npm.cmd test -- textbookScopes.test.ts`：4 项测试全部通过，覆盖父/子科目匹配和无关科目不得回退。
- `npm.cmd run build`：TypeScript 检查与 Vite 生产构建通过。

## 2026-07-18 - Electron 原生窗口控制与折叠侧栏对齐

### Fix

- 放弃容易被拖拽命中区吞掉点击事件的 React 自绘窗口按钮，改用 Electron `titleBarStyle: hidden` 与 Windows/Linux 原生 `titleBarOverlay`。
- 保留页面标题区域的 drag/no-drag 划分，并为原生窗口按钮预留安全间距。
- 折叠侧栏 rail 补充全高约束，避免折叠后导航内容按自身高度向顶部收缩。
- 左右桌面标题栏统一为不可收缩的 64px 高度，避免窗口变矮时左侧品牌栏被 flex 压缩而导致分隔线错位。

### Validation

- `desktop/main.cjs` 与 `desktop/preload.cjs` Node 语法检查通过。
- 前端 TypeScript 与生产构建通过。

## 2026-07-24 - 解耦分支复审修复

### Fix

- `BookReadCache` 在缓存存取边界使用防御性复制，避免调用方修改 JSON 或索引统计后污染后续请求；小型元数据文件增加内容指纹，可靠识别 Windows 同尺寸快速覆盖，同时避免大型章节文件每次重读全文。
- KG 复习计划增加概念名稳定排序兜底，并兼容有/无时区时间相减。
- KG 错题关联改为一次构建“显式概念 -> 错题摘要”和“规范化题干 -> 错题 ID”索引，不再用短概念或问题子串扫描全文，减少误命中和重复遍历。
- 删除 books API 中无语义的一行转发函数，移除未使用的参数和导入，直接调用章节纯函数。
- 错题图片服务改为模块级单实例，路由直接调用其生命周期方法，不再逐次重建相同服务或保留私有转发层。
- 图片大小错误信息从 `max_image_bytes` 动态生成；Pillow 缺失或图片无法解码时记录降级原因，其他优化异常记录堆栈并向上抛出。
- `/mistakes/recognize-image` 的失败文案改为 OCR 识别失败，不再误报为讲解失败。

### Validation

- `python -m pytest -q tests/test_book_read_cache.py tests/test_kg_learning_summary_service.py tests/test_mistake_image_lifecycle.py`：16 passed。
- 覆盖缓存结果隔离、同尺寸覆盖、KG 稳定排序、时区兼容、短概念误匹配、题干子串误匹配、图片路径约束、失败清理、动态大小提示和意外优化异常向上抛出。
- 完整后端测试：199 passed，1 条既有 Starlette/httpx2 弃用警告。

## 2026-07-24 - 解耦复审第二批边界整理

### Backend

- `ExercisePracticeService` 移除 `Any`、请求 DTO、响应字典和序列化回调，改为明确的 `ExerciseBank`、`MistakeBook`、`ExerciseRecord`、`PracticeSession` 类型。
- 新增 `PracticeAnswerResult`，由应用服务表达作答、稳定错题 ID 和可重试的错题写入失败；FastAPI Router 独立负责 Pydantic 序列化、成功/失败响应和用户文案。
- 作答已经持久化但错题写入失败时，仍记录一次正常练习事件；重试继续复用稳定错题 ID，不重复作答。

### Frontend

- 新增 `useExerciseAnswerJob`，集中管理标准答案任务恢复、轮询、失败终止、草稿编辑和保存。
- 新增 `useExerciseImportCandidates`，集中管理候选题筛选、选择、编辑、合并、拆分和摘要统计；所有跨状态更新均位于事件处理流程，不在 React state updater 中产生副作用。
- `ExercisesPage` 从 909 行降至 820 行，删除重复工作流实现，没有继续抽取纯样式叶子组件。

### Validation

- 后端练习与 overview 针对性测试：12 passed；完整后端测试：199 passed，1 条既有 Starlette/httpx2 弃用警告。

## 2026-07-24 - 解耦复审第三批工作流拆分

### Review corrections

- 复审发现原 `ExercisePracticeService` 仍包含四个只转发到 `ExerciseBank` 的方法；移除这些方法并收窄为只承载幂等作答、错题写入和学习事件协调的 `PracticeAnswerService`，会话查询与状态切换由 Router 直接调用题库。
- 候选题 hook 不再向页面暴露原始 `setCandidates` / `setSelectedIds`，改为替换候选、移除已选、全选和清空选择等语义操作。
- 候选题合并、拆分、筛选和摘要提取为纯操作并增加测试；合并现在真正校验所选题目相邻，避免界面提示与行为不一致。
- 答案任务创建未返回任务 ID、轮询返回失败或缺少任务数据时会结束 busy 状态并给出明确提示，不再无限等待。

### Workflow split

- 新增 `usePracticeSession`，集中连续练习启动、暂停、恢复、作答、转入错题本、当前题选择和本地状态同步；`ExercisesPage` 进一步降至约 716 行。
- 新增 `useMistakeReview`，集中到期复习展开状态、评分提交、记录同步以及到期列表和统计刷新。
- 保留 `_bank()` / `_mb()` 配置入口：它们统一绑定教材范围和 `PROGRESS_PATH`，不是纯改名转发。
- 暂不把截图裁剪强行抽成综合 hook；该流程仍与 DOM ref、Canvas 和裁剪弹窗紧密耦合，待先拆出稳定的图片处理状态模型后再迁移。

### Validation

- 前端 ESLint 通过。
- 前端 Vitest：5 个测试文件、18 项测试通过。
- 前端 TypeScript 检查与 Vite 生产构建通过。
- 后端练习与 overview 针对性测试：12 passed。
- 完整后端测试：199 passed，1 条既有 Starlette/httpx2 弃用警告。

## 2026-07-24 - RAG EvidencePack 与问答时序优化

### RAG generation

- 将生成阶段重复注入的 `chapter_contents`、`evidence_items` 和 `concept_results` 收敛为单一 `EvidencePack`；按 `chunk_id` 与规范化正文去重，并使用 9000 字符总预算和 1800 字符单段上限。
- `EvidencePack` 保持为显式接收 `evidence_items`、`chapter_contents`、`intent` 的纯函数，不直接依赖完整 GraphState、环境变量、索引或存储，避免破坏现有检索与解耦边界。
- 证据数量限制按意图区分：普通定义保持同章最多 2 段；公式/性质最多 3 段；推导、应用、教学等最多 4 段；事实背诵允许保留检索层同章最多 6 段，避免漏掉并列要点。旧索引缺少 `evidence_items` 时仍从 `chapter_contents` 降级。
- 检索调试项和最终证据继续分离；仅补齐 `book_name`、语义角色和命中来源等既有元数据。引用标签优先使用真实教材名，未知页码不再显示 `p.?`，未改动检索排序、证据门禁、向量库或知识图谱格式。

### Runtime

- 复用相同不可变配置下的 LangChain/OpenAI/Ollama 客户端，保留 DeepSeek V4 Pro、thinking 与温度配置，不引入 Planner 模型降级。
- 修正 SSE 阶段计时归属，分别记录 context、plan、retrieve、chapter、generate TTFT、generate total 和 total；仅增加事件观测字段，不改变事件顺序和正文累积协议。

### Benchmark

- 固定问题“什么是电容式传感器”和同一检索结果的隔离生成测试中，Prompt 从 6782 字符降至 4419 字符（-34.8%）；3 次中位 TTFT 从 23220.97 ms 降至 10169.70 ms（-56.2%），生成总时长从 27500.96 ms 降至 14664.82 ms（-46.7%）。
- 完整链路前后各仅 1 次，改动后总时长高 11.2%；该结果包含 Planner 和外部模型波动，样本不足，不能宣称完整链路稳定提速。前后答案及原始计时保存在 `benchmark_results/`。

### Validation

- EvidencePack、生成、通用教材资源组、检索降级与 SSE 定向回归：29 passed。
- 完整后端测试：201 passed，1 条既有 Starlette/httpx2 弃用警告。
- 前端 TypeScript 与 Vite 生产构建通过；Electron `main.cjs`、`preload.cjs` Node 语法检查通过。
- `git diff --check` 通过。`compileall` 因现有 `__pycache__` 目录权限无法写入而未作为验证依据；完整 pytest 已成功导入并执行相关 Python 模块。

## 2026-07-24 - 解耦分支功能契约修复

### Compatibility and fault isolation

- KG 概念复习优先使用 `linked_concepts` 与标签精确关联；某概念没有显式命中时，再从旧错题的题干、OCR 与解析文本做兼容包含匹配。单字符概念不进入全文兜底，最近题目关联还要求最短四字符且长度比例不低于 0.75，避免短片段误命中。
- `PracticeAnswerService` 改为接收 `MistakeBook` provider；仅在 `add_to_mistake=True` 且尚无稳定错题 ID 时初始化错题库，普通作答不再受错题数据库权限或损坏影响。
- 习题与错题 overview 保留主体列表，将统计、活动会话和到期复习队列作为隔离的可选部分；辅助模块失败时返回局部数据及 `errors` 字段。

### RAG quality contract

- EvidencePack 继续保留 9000 字符总预算与单条 1800 字符上限，同时为定义、列举、比较、普通原理问答、推导、应用题和跨章节问题设置显式的每章证据覆盖基线。
- 新增确定性多题型回归测试；它验证证据覆盖边界，不调用付费 LLM，也不把单次模型延迟当作答案质量结论。

### Validation

- 针对性后端测试：41 passed，覆盖五类 KG 关联来源、短概念防误匹配、惰性错题依赖、overview 局部失败和 EvidencePack 多题型矩阵。
- 完整后端测试：218 passed；仅有 1 条既有 Starlette/httpx2 弃用警告。
- 前端 Vitest：5 files / 18 tests passed；ESLint、TypeScript 与 Vite 生产构建通过。
- Electron `main.cjs`、`preload.cjs` Node 语法检查通过；版本一致性检查通过。
- 当前 CI 已配置 `pull_request` 触发；合并前仍需让当前真实 HEAD 通过远端完整 CI。未调用真实付费 LLM、OCR 或 MinerU。

## 2026-07-24 - 本地 API 卡片请求 Origin 分类修复

### Fix

- 本地 API 安全边界不再只按 HTTP 方法判断写操作；`/exercises/list`、`/exercises/overview`、`/mistakes/list`、`/mistakes/overview` 虽使用 POST 传递筛选条件，但按只读请求处理。
- “按薄弱点抽题”和“随机抽一道题”不再因只读 `/exercises/list` 被误报 `UNTRUSTED_ORIGIN`；习题库 overview、错题列表和错题 overview 同步恢复。
- 将后端自身提供的本地 UI Origin `http://localhost:8000` 与 `http://127.0.0.1:8000` 加入明确白名单。Electron 仍优先使用每次启动生成的 API token。
- 真正写入或产生外部成本的卡片操作仍受保护，包括错题速录保存、练习提交、复习评分、教材重点生成、设置修改和数据恢复；未知 Web Origin 不能借只读豁免调用这些接口。

### Card audit

- 到期错题复习、概念复习是前端本地卡片；学习日报/周报和教材重点读取使用 GET，不受此次误分类影响。
- 教材重点生成、错题图片识别与保存、题目作答等写入型操作统一通过带桌面 token 的 API client；本地 8000 UI 可正常使用，其他来源仍需显式配置可信 Origin 或有效 token。

### Validation

- 安全边界定向测试：12 passed；覆盖未知 Origin 只读 POST 放行、真实写请求继续拒绝、尾斜杠归一化、本地 5173/3000/8000 Origin 和桌面 token。
- 相关 API 定向测试：28 passed。
- 完整后端测试：220 passed；仅有 1 条既有 Starlette/httpx2 弃用警告。
- 前端 Vitest：5 files / 18 tests passed；ESLint、TypeScript 与 Vite 生产构建通过。
- Electron `main.cjs`、`preload.cjs` Node 语法检查通过；`git diff --check` 通过。
## 2026-07-24 - 章节重点任务终态与卡片停止状态修复

### Fix

- 章节重点生成失败或取消时，同时把 SQLite 后台任务和对应 `metadata.json` 写入 `failed` / `cancelled` 终态；即使元数据写入本身失败，任务表也会结束，不再永久保留 `running`。
- 章节重点列表会按同范围最新任务修复后端重启造成的陈旧 `running` 元数据；只修复已有的临时状态，不复活用户已删除的重点记录，也不覆盖较新的成功产物。
- 前端轮询收到 `completed`、`failed`、`cancelled` 或 `interrupted` 后统一清理活动任务并刷新章节状态；启动缺少任务 ID、连续网络失败也会解除本地“生成中”。
- 章节重点卡片新增“终止生成”，复用持久化任务取消接口；任务完成改用原子完成操作，取消与完成并发时由取消状态优先。

### Adjacent card audit

- 教材导入卡片现在把 `cancelled`、`interrupted` 作为终态，停止轮询、解除按钮禁用并显示错误态。
- 学习页知识关联卡片在 `cancelling` 时保持禁用并显示终止中；`cancelled`、`interrupted` 不再继续显示加载态。
- 习题标准答案任务原有轮询已完整处理 `failed`、`cancelled`、`interrupted`，无需修改。

### Validation

- 章节重点任务定向回归：10 passed，覆盖失败元数据落盘、重启中断修复、工作线程失败和取消前置检查。
- 完整后端测试：223 passed；仅有 1 条既有 Starlette/httpx2 弃用警告。
- 前端 Vitest：5 files / 18 tests passed；ESLint、TypeScript 与 Vite 生产构建通过。
- `git diff --check` 通过。

## 2026-07-27 - 问答数学符号辅助输入第一版

### Frontend

- 问答输入区新增数学符号面板，按常用、微积分、线性代数和希腊字母分组提供 48 个 LaTeX 符号与公式模板；复用现有 Markdown + KaTeX 消息格式，不修改后端请求协议、数据库或模型调用链。
- 模板按当前光标位置插入；选中文字后可直接套用分数、根式、函数、向量等结构，插入完成后恢复输入焦点并选中下一处待填写内容。
- 面板支持当前输入预览、点击外部关闭和 Escape 关闭；2×2、3×3 矩阵使用独占行块级定界符。紧凑布局下对面板内部按钮做局部尺寸隔离，并验证 390px 移动视口无横向溢出。

### Validation

- 前端 Vitest：7 files / 25 tests passed，覆盖光标插入、选区套用、占位定位、矩阵块定界符和模板标记清理。
- 前端 ESLint 通过；TypeScript 检查与 Vite 生产构建通过。
- 本地实际界面验证通过：桌面 1280×720 下分数插入、KaTeX 预览和矩阵渲染正常；390×844 紧凑布局下面板边界、分类标签和模板点击区域正常。
- 未新增第三方依赖，未调用真实 LLM、OCR 或教材索引。

## 2026-07-27 - 问答可视化公式编辑与矩阵输入

### Frontend

- 将第一版的“把 LaTeX 源码直接插入 textarea”调整为“自然语言输入 + 可视化公式卡片”。公式在 MathLive 编辑器中按排版结果填写，保存后以 KaTeX 卡片展示，可再次编辑或删除；发送时再统一组合为 Markdown + LaTeX，后端接口和 LLM 输入约定保持不变。
- 48 个原有模板不再暴露占位源码，点击后进入带灰色占位框的公式编辑器；占位未填写时禁止保存，并可选择行内公式或独立公式。
- 新增矩阵构造器：支持 1–5 行、1–5 列，方括号、圆括号、行列式和无括号四种外框；逐格输入并实时预览，所有格子填写后生成标准矩阵 LaTeX。
- 移除已被替代的旧版原始 LaTeX 弹层与输入预览组件，保留模板数据和纯转换测试。

### Dependency and performance

- 新增 `mathlive@0.110.0`，仅用于前端可视化公式编辑；MathLive 使用动态导入，并在 Vite 中拆分为独立 `vendor-mathlive` 资源，避免混入通用 vendor 首屏包。
- 不修改数据库、后端 API、RAG、错题或教材索引格式；本次依赖变化只影响前端安装与构建产物。

### Validation

- 前端 Vitest：10 files / 33 tests passed，新增覆盖文字与公式组合、模板占位转换、矩阵缩放、矩阵序列化和空格校验。
- 前端 ESLint 通过；TypeScript 检查与 Vite 生产构建通过。
- 本地实际界面验证通过：桌面端完成分数可视化编辑、2×2 矩阵逐格填写、实时预览、公式卡片添加及二次编辑；390×844 紧凑布局下模板面板可用且无页面级横向溢出。
- 未调用真实 LLM、OCR 或教材索引。

## 2026-07-27 - 公式快捷键与输入法页面位移修复

### Frontend

- 可视化公式编辑器下方新增单行快捷键，包含平方、立方、0–9、x/y/z、加减等号与圆括号；快捷键保持公式框当前选择，不会因为按钮获得焦点而丢失输入位置。
- 模板载入后显式定位到第一个公式占位框，快捷键通过 MathLive 的键盘输入命令填写，避免第一次点击数字时覆盖整条公式。
- 禁用 MathLive 在输入、组合输入和光标变更时对宿主节点执行 `scrollIntoView()`；程序化聚焦使用 `preventScroll`，并在焦点事件后恢复页面滚动位置。
- Electron 桌面布局改用稳定的 `100vh` 工作区高度，不再随输入法造成的动态可视视口变化压缩主页面；紧凑移动布局仍保留动态视口适配。

### Validation

- 前端 Vitest：11 files / 35 tests passed，新增快捷键唯一性以及平方、立方命令测试。
- 前端 ESLint 通过；TypeScript 检查与 Vite 生产构建通过。
- 本地界面实测：极限模板载入后，数字快捷键只填写当前占位框且保留 `lim` 结构；变量后添加平方正常；连续聚焦和快捷输入前后 `scrollY=0`、应用顶边为 0、应用高度与视口高度均保持 720px。

## 2026-07-27 - 问答框公式附件

### Frontend

- 可视化编辑完成后的操作统一为“插入问答框”，插入成功即关闭公式面板；公式在问答框内部以“公式 1”“公式 2”等编号附件显示，并保留预览、编辑和删除操作。
- 自然语言与公式附件共用一个输入容器，避免用户直接修改 LaTeX 源码；发送时按照界面编号组合为 Markdown + LaTeX，LLM 仍收到完整、结构化的数学表达式。
- 本版未引入富文本 `contenteditable` 或拖拽排序，避免扩大输入法、光标定位和无障碍交互的风险；多公式按插入顺序稳定编号。

### Validation

- 前端 Vitest：11 files / 35 tests passed；ESLint 与 Vite 生产构建通过。
- 本地界面实测：连续插入无穷符号和希腊字母后，问答框内正确显示“公式 1”“公式 2”，面板自动关闭，编辑、删除与发送入口可用。

## 2026-07-28 - Conservative subject-routing correction for chat

### Backend

- Chat requests and persisted messages now share a stable `turn_id`; persisted messages also receive a stable message `id`. Existing conversation files remain readable without migration.
- Added a conservative subject router that combines the configured subject catalog, explicit subject/course terms, textbook metadata and local BM25 evidence. A suggestion is emitted only when its score and lead over the runner-up pass feedback-adjusted thresholds.
- Subject-routing failures are isolated from the main answer path. A failed classifier or local index read does not turn a successful answer into an SSE error.
- Added conversation scope APIs for relabeling a whole conversation and for moving one identified turn into a new conversation. Both preserve message bodies and record scope history; mistake records, learning events and RAG traces are intentionally not rewritten.
- Accepted and dismissed suggestions are counted per source/target route. Repeated acceptance can slightly lower the threshold, while repeated dismissal raises it.

### Frontend

- Assistant answers can show an actionable subject suggestion card with confidence and evidence.
- The card supports moving only the current turn, relabeling the whole conversation, or dismissing the suggestion. Moving one turn opens the newly created conversation under the corrected subject/book scope.
- Conversation history restores stable message and turn identifiers, and chat rendering uses stable keys when available.

### Validation

- Targeted backend regression: 9 tests passed, covering routing, current-scope suppression, feedback persistence, concurrent conversation writes, whole-conversation relabeling, turn splitting, and SSE persistence failure isolation.
- Full backend regression: 228 tests passed with one existing Starlette/httpx2 deprecation warning.
- Frontend validation passed: 11 Vitest files / 35 tests, ESLint, TypeScript, and the Vite production build.
- No database schema, textbook index format, mistake record, learning-event record, or RAG-trace migration was introduced.

## 2026-07-28 - Stable formula references in the chat composer

### Frontend

- Replaced the clipped textarea focus shadow beneath formula attachments with the existing outer composer focus border, and added a quiet `surface-subtle` background to separate the formula layer from the question text.
- Formula labels are now actionable: clicking `公式1`, `公式2`, and so on inserts that exact compact reference at the current question cursor or replaces the current selection.
- Formula reference numbers remain stable after deletion, so removing `公式1` does not silently rename an existing `公式2`. Newly attached formulas continue from the highest remaining reference number.
- Outgoing questions include an explicit reference registry mapping each compact label to its LaTeX expression, making phrases such as “比较公式1和公式2” deterministic for the answer generator.
- No backend API, database, textbook index, mistake record, learning event, or RAG trace was changed.

### Validation

- Frontend Vitest: 12 files / 38 tests passed, including cursor insertion, selection replacement, stable numbering after deletion, formula-only questions, and explicit reference serialization.
- Frontend ESLint, TypeScript checks, and the Vite production build passed.
- The existing MathLive chunk-size warning remains unchanged and does not block the build.

## 2026-07-29 - Cross-subject routing preflight correction

### Backend

- Fixed subject ranking so a parent subject and its matching child route reinforce the same classification instead of incorrectly competing for the minimum lead. The reported sensor-to-English-writing question now resolves to the English/Writing scope with a high-confidence suggestion.
- Subject routing now runs before the graph. When a confident cross-subject suggestion exists, the turn uses ordinary QA generation and does not retrieve from the currently selected, known-wrong textbook.
- Streaming and non-streaming chat reuse the same preflight suggestion, while the actionable suggestion card remains attached to the completed answer.
- The initial routing fix did not mutate Chroma. A follow-up integrity audit identified the reported `Nothing found on disk` entries as empty read-created collections rather than missing files from populated textbook indexes.

### Validation

- Added regression coverage for parent/child route scoring and for suppressing wrong-textbook retrieval when a cross-subject suggestion is active.
- Targeted routing and stream reliability tests: 11 passed.
- Full backend regression: 230 tests passed with one existing Starlette/httpx2 deprecation warning.

## 2026-07-29 - Chroma phantom-collection repair

### Cause and repair

- `get_chapter_store()` had used LangChain Chroma get-or-create semantics on the read path since commit `ebf058e1` (2026-05-31). Commit `21ea40b9` (2026-07-03) added the current book-scoped `bk...` names but did not delete existing index files. Querying planner-generated subsection names triggered the latent bug on 2026-07-29.
- The SQLite catalog contained eight unmapped collections with `count=0`; their HNSW directories never existed. All 507 mapped vector segments had matching directories, so no populated textbook index was corrupt.
- Created a byte-for-byte full backup at `data/vector_db.backup-20260729-empty-collections` before repair, then deleted only the eight verified empty collections. PDFs, OCR/MinerU chunks, lexical indexes, mistakes, and learning records were untouched.
- The read path now checks `get_collection()` before constructing the LangChain wrapper, preventing unknown chapter lookups from creating empty collections.

### Validation

- Chroma now reports 507 collections and zero registered vector segments with missing directories; unknown subsection queries keep the collection count unchanged at 507.
- Sensor long-book index: 12 collections / 1359 vector chunks / 1359 lexical chunks; sensor short-book index: 479 collections / 562 vector chunks / 562 lexical chunks.
- Real chapter retrieval returned results, and whole-book retrieval ranked Chapter 4 (force sensors) and Chapter 11 (signal processing) for the dynamic capacitive-sensor query.
- Added a regression test proving a missing chapter read cannot construct a Chroma collection. Full backend regression: 231 tests passed with one existing Starlette/httpx2 deprecation warning.

## 2026-07-30 - Electron startup recovery and titlebar feedback

### Desktop and frontend

- Replaced the non-customizable Windows Window Controls Overlay with isolated custom controls in both the React application and startup page. The BrowserWindow now uses `frame: false`; each interactive button owns an explicit `no-drag` hit region and standard click semantics, while window dragging remains on the non-overlapping left brand header. Minimize and maximize animate a full-button background and glyph geometry on hover, provide a compressed active state, preserve keyboard focus, and honor `prefers-reduced-motion`; close keeps its red danger state.
- Restored the main page header as an Electron drag region, including native double-click maximize and restore behavior. Interactive controls inside the header remain explicit `no-drag` regions.
- Kept the page-header drag region outside the 138px window-control hit area so it cannot suppress button hover/click feedback. The control backing now spans the full 64px header height and draws the same bottom border and translucent surface while the three animated buttons remain 42px high.
- Electron now waits for backend health even when a frontend development URL is configured, preventing the React application from opening against a backend that is still starting.
- Added a startup retry IPC flow and a visible “重新连接” action on the failure screen. If the backend process has exited, retry starts it again before waiting for health.
- Added a per-launch cache key when loading the application so a restarted desktop client cannot reuse stale titlebar/overlay assets from the previous renderer session.
- Removed the explanatory caption below “选择导入方式” and both option subtitles below “导入 PDF 教材” and “导入 MinerU 输出包”. Promoted the section heading to 18px semibold and the two option labels to 16px medium.
- No backend API, database, vector index, textbook data, mistake record, or learning record format changed.

### Validation

- Frontend ESLint passed; TypeScript and Vite production build passed.
- Frontend Vitest: 12 files / 38 tests passed. The first sandboxed run was blocked by Windows `spawn EPERM`; the approved unsandboxed rerun passed.
- Electron main/preload syntax checks and `git diff --check` passed.
- Windows Electron production-build validation at 125% display scaling confirmed visible full-button hover feedback for both minimize and maximize. A real maximize click changed the test window from 981×820 to 2048×1232 and synchronized the restore glyph. The 教材导入 page renders without the section caption or either option subtitle, and an isolated missing-backend simulation shows “重新连接”, Web fallback, and backend-log actions.
- Fresh Electron development-window validation confirmed that double-clicking the central page header changes the window from 1280×820 to 2048×1232 and a second double-click restores it to 1280×820. Visual inspection confirmed one continuous bottom border across the brand header, page header, and right-side window-control area.
- Follow-up Electron validation reproduced the overlapping drag-region regression, then confirmed the full-button hover background was visible again after separating the page-header and control hit areas; central-header double-click maximize remained functional.

## 2026-07-30 - Scoped font trial

### Frontend and packaging

- Added a self-hosted Latin Regular subset of JetBrains Mono and placed it before the existing Windows monospaced fallbacks for code, identifiers, and other explicitly monospaced content.
- Added the Unicode-split LXGW WenKai Screen webfont for learning suggestions and Markdown quotations only. Its stylesheet is injected only when a report or quotation surface mounts; navigation, controls, tables, metrics, normal answers, and the application shell continue to use the existing Windows system font stack.
- Added bundled-font provenance and license texts under `THIRD_PARTY_NOTICES/fonts`; the desktop backend build now carries that notice directory into the packaged application.
- No backend API, database, vector index, textbook data, mistake record, or learning record format changed.

### Validation

- Frontend ESLint passed; Vitest passed 12 files / 38 tests; TypeScript and the Vite production build passed.
- Chromium production-asset checks confirmed both `LXGW WenKai Screen` and `JetBrains Mono` load successfully, and a visual specimen confirmed distinct glyph rendering without changing the surrounding system-font UI.
- The production entry does not preload the LXGW stylesheet. The report surface injects the hashed `result-*.css` asset on mount.
- JetBrains Mono adds two Latin font assets totaling 47.5 KiB. LXGW WenKai Screen adds 241 Unicode-split WOFF2 assets totaling 12.53 MiB to the offline package, while runtime font downloads remain limited by `unicode-range`.
## 2026-07-30 - Practice workspace visual restructuring

### Frontend

- Rebuilt the practice workspace as one focused exercise surface instead of stacked full-width cards. Session controls, question context, answer entry, solution review, and mastery rating now form a clear top-to-bottom workflow with a bounded desktop reading width.
- Removed the chat-bubble treatment from exercise questions and explanations by adding a reusable document rendering variant to `ChatMessage`; normal conversation rendering remains unchanged.
- Kept answers and explanations collapsed by default. The expanded state uses a balanced two-column layout on desktop and falls back to one column on narrower viewports.
- No practice handlers, backend APIs, database schemas, exercise records, or review scheduling rules changed.

### Validation

- Frontend ESLint passed.
- Frontend Vitest passed 12 files / 38 tests.
- TypeScript and the Vite production build passed.
- Electron visual validation at 1280 x 820 confirmed both collapsed and expanded states fit without horizontal overflow and keep the primary practice actions visible.

## 2026-08-01 - Sensor chapter index rebuild and Chroma preflight repair

### Cause and data repair

- The planner benchmark repeatedly reported `Error creating hnsw segment reader: Nothing found on disk` for valid sensor chapters. A direct full-store audit could query all 507 collections, but the real chat order (`get_book_index_stats()` followed by chapter retrieval) reproduced the failure reliably.
- Created a complete recoverable backup at `data/vector_db.backup-20260801-230303-chapter-repair` before mutation.
- Rebuilt the sensor short book from its independent lexical source (479 chapters / 562 chunks) and the sensor long book (12 chapters / 1359 chunks).
- Replaced the legacy ASCII-parentheses full-text collection with the canonical chapter title. The old collection was removed only after all 59 `chunk_id` values and document texts matched the replacement exactly.
- The underlying failure was not missing persisted HNSW files after rebuild: calling `count()` across hundreds of chapter collections during the chat preflight invalidated subsequent Chroma HNSW readers. Book health now uses collection mappings plus the independent lexical chunk count instead of opening every HNSW segment.
- `ChapterVectorStore` now owns one persistent Chroma client and passes it to all LangChain Chroma wrappers, avoiding competing client lifecycles for the same persistent path.

### Validation

- Full vector audit: 507/507 collections completed a real embedding-vector query; zero mapped collections were missing, zero collections were unmapped, and no files under `data/vector_db` had the NTFS compressed attribute.
- The exact production order of book-health preflight followed by retrieval now returns the requested `第二节 等效电路与测量电路` chapter without an HNSW error.
- The full sensor teach retrieval includes both `第二节 等效电路与测量电路` and `第六章 压电式传感器` in the retrieved chapter set.
- Added client-lifecycle and safe-health-check regression coverage. Full backend suite: 233 tests passed with one existing Starlette/httpx2 deprecation warning.
- Machine-readable reports: `data/eval/vector_collection_health_20260801.json` and `data/eval/chapter_index_repair_final_20260801.json`.

## 2026-08-02 - Task-first frontend hierarchy cleanup

### Frontend

- Reworked the chat empty state into one focused starting surface: one due-review recommendation, four flat study intents, and a tertiary mistake-capture entry replace the previous dashboard-like card collection.
- Separated exercise configuration, continuous-session, single-question, submitted-solution, and mastery-rating states. The exercise question is hidden until practice starts, mastery controls appear only after solution review, and direct practice from the exercise bank remains an explicit single-question flow.
- Simplified the mistake-entry wizard so crop, recognition, and clearing controls appear only when relevant; reduced the upload surface and removed implementation-oriented OCR microcopy.
- Split textbook import into source selection and file/settings steps, moved MinerU quality controls under advanced options, and made missing prerequisites explicit next to the disabled primary action.
- Reordered the learning overview to show today's conclusion first, then recommended actions, then supporting analysis; recent questions and secondary review concepts are collapsed by default.
- Reduced settings width and navigation weight, replaced oversized exercise metric cards with a compact summary row, and removed explanatory or internal-status copy that did not help the next user decision.
- No backend API, database schema, vector index, textbook data, mistake record, or review-scheduling format changed.

### Validation

- Frontend ESLint passed.
- Frontend Vitest passed 12 files / 38 tests.
- TypeScript and the Vite production build passed; the existing MathLive chunk-size warning remains unchanged.
- In-app desktop-browser visual checks at 1280 x 720 covered chat, exercises, textbook import, mistake entry, and settings. The learning page layout was type/build verified because its local summary API remained unavailable during visual QA.
## 2026-08-03 - Lightweight interaction motion system

### Frontend

- Added a keyed route-stage entrance for page navigation, using a 200 ms opacity and 6 px vertical transform without retaining the previous route.
- Added shared entrance treatments for modal backdrops, normal and large dialogs, the compact sidebar drawer, popovers, and completion notices. Large surfaces avoid scale transforms; all motion uses only opacity and transform.
- Added a 90 ms tactile active state to shared primary/secondary buttons, sidebar navigation, sidebar controls, and scope-selector options.
- Motion runs only when `prefers-reduced-motion: no-preference`; no animation library, timer, scroll listener, or persistent `will-change` layer was added.
- No backend API, database schema, vector index, textbook data, mistake record, or learning record format changed.

### Validation and performance

- Frontend ESLint passed; Vitest passed 12 files / 38 tests; TypeScript and the Vite production build passed. The existing MathLive chunk-size warning remains unchanged.
- Compared with the preceding production build, entry CSS increased from 68.52 kB / 12.99 kB gzip to 70.57 kB / 13.36 kB gzip (+2.05 kB / +0.37 kB gzip). Entry JavaScript increased from 42.79 kB / 13.35 kB gzip to 43.01 kB / 13.41 kB gzip (+0.22 kB / +0.06 kB gzip).
- Fresh Electron validation at 1280 x 820 covered the first-run large dialog, 12 consecutive route changes across all six primary pages, and opening/closing the scope-selector popover.
- In an 18-second interaction sample, the four new Electron processes averaged 58.2% of one CPU core, versus 33.3% during an equal recovery-idle sample. The process group returned to the lower idle level after interaction rather than remaining elevated. The 250 ms sampling peak was 267.8% of one core during page loading/capture.
- Working set rose from 571.9 MB to a 614.0 MB peak while all lazy routes were visited, then stabilized around 586.0 MB; private memory stabilized around 285.6 MB. The retained increase is consistent with first-load route modules and page data, and no repeated growth was observed after interaction stopped.
- Runtime CPU figures include Windows Graphics Capture used by the UI validation tool, so they are suitable for relative interaction-versus-idle comparison, not as an end-user absolute idle benchmark.

## 2026-08-09 - Session Context and Planner routing专项优化

### Planner 与教材范围路由

- 为 Planner 增加内部可观测 telemetry：提示词构建、API 请求起止、首 token、响应解析、章节 fallback 与总耗时，以及 token usage、reasoning token、finish reason、retry count、模型名和 request id。Fast-path 与 General QA bypass 使用相同的有界 trace 结构，不记录提示词或回答正文。
- 在 Session Resolver 后加入保守的 deterministic 教材范围 gate。显式教材请求和已解析追问保留教材检索；明确学科错配、健康词法索引中缺失的特征英文词或定义锚点可退出当前教材模式；其余模糊问题继续继承已选教材。
- 扩展短且结构明确的 deterministic fast-path，覆盖简单比较、计算方法和简短“解释 X”；多约束比较、推导、证明和详细解释仍进入 Planner。
- 删除 fast-path 在正式 retrieve 前的向量章节预探测。章节定位由唯一的 retrieve 流程负责，避免同一问题做两次完整向量检索。

### Session Context

- 将追问解析迁移到 `backend/services/session_context.py`，以可重放的 `topic / entities / frame / constraints / intent / last_resolved_query` 状态替代旧的历史短语拼接。
- 支持稳定实体顺序下的“第一个”、比较 frame 的“前者/后者”、后续条件增量，以及“性质 → 怎么算 → 举例”等连续意图继承。派生状态不写入会话文件，旧会话无需迁移，也不会把一次误解析永久固化。
- 前端 retrieve 阶段根据 `use_textbook_context` 区分“检索教材上下文”和普通“准备回答”，避免 General QA 显示误导性的教材检索提示。
- 未修改数据库、会话文件、向量索引、教材数据、错题记录或学习记录格式。

### Validation

- 后端全量 pytest 通过：319 tests passed；仅有既存 Starlette/httpx2 弃用警告。
- 前端 ESLint、TypeScript 与 Vite 生产构建通过；Vitest 13 files / 49 tests passed。沙箱内首次 Vitest 因 Windows `spawn EPERM` 失败，获批的沙箱外重跑通过。
- `git diff --check` 通过；Python `compileall` 因现有 `__pycache__` 目录写权限不足未作为验证依据，相关模块已由全量 pytest 导入覆盖。

## 2026-08-09 - 学科专属 General QA 与 ConceptMemory 路由

### 回答范围

- 将回答范围显式拆分为 `textbook_grounded`、`subject_general`、`global_general` 和运行时的 `subject_mismatch`，保留 `use_textbook_context` 作为是否执行教材检索的内部细节，不再用它同时表达知识边界。
- 自动模式优先使用当前教材；问题明显属于当前学科但教材没有对应内容时转为学科通用回答；明显跨出当前学科时停止生成并提示范围不匹配。用户可从该提示直接发起一次显式的跨学科通用回答，避免系统暗中扩大边界。
- 范围判断会检查当前学科下全部健康教材的词法概念锚点，避免仅因当前选中的短教材未收录某个学科内概念就误判为跨学科。显式跨学科模式始终拥有最高优先级。
- 对话界面显示“教材依据 / 学科通用 / 跨学科通用 / 范围待确认”来源标记；范围不匹配消息提供“跨学科通用回答”按钮，并保留原问题用于重新提交。

### ConceptMemory

- 教材回答继续按教材 KG 与检索概念归属；学科通用回答使用当前学科归属；跨学科通用回答进入通用归属，不再错误复用当前教材的知识图谱。
- 通用回答在严格的本地概念链接后，异步复用结构化 LLM 概念提取作为 fallback；提取提示词带回答范围和学科约束，既支持无教材概念，也保留显式提及、证据支持和去泛化门槛。
- `subject_mismatch` 不生成答案，也不写入 ConceptMemory。学习事件新增回答模式与范围原因，来源细分为教材、学科通用和跨学科通用。
- 未迁移或重建 ConceptMemory、教材索引、向量库、错题及复习数据。会话消息仅新增可选的回答模式与范围原因字段，旧会话保持兼容。

### Validation

- 后端全量 pytest 通过：329 tests passed；仅有既存 Starlette/httpx2 弃用警告。
- 前端 ESLint、TypeScript 与 Vite 生产构建通过；Vitest 通过：13 files / 49 tests passed。沙箱内首次启动仍受 Windows `spawn EPERM` 限制，获批的沙箱外重跑通过。构建仅保留既有的 MathLive 大 chunk 提示。
- `git diff --check` 通过；真实路由检查确认传感器教材中的“QKV”进入 `subject_mismatch`，“压阻效应”保持 `textbook_grounded`，显式跨学科请求进入 `global_general`。

## 2026-08-09 - 复合问答与指代追问修复

### 根因与路由

- “压阻式传感器怎么算”此前被归入宽泛的 `application`，其检索角色优先例题和实例，导致回答列举压阻式加速度、压力传感器而没有给出计算链路。新增独立的 `calculation` 意图，公式、算法和推导证据优先，并要求生成器先说明计算对象是否唯一，再给公式、变量、适用条件和计算顺序。
- 显式“比较 / 推导 / 计算”任务现在可锁定本地确定性意图；Planner 仍负责复杂问题的章节定位，但不能因“并说明”等次要词把多维比较改判成事实背诵。
- 计算检索使用同一次向量与词法调用中的意图化查询，不增加第二轮向量预检或新的 LLM 调用，保留本轮优化后的生成速度收益。

### Session Context 与证据支持

- 比较 frame 支持“比较 A 和 B。”以及三项以上的“比较 A、B 和 C，并分别说明……”结构，并补全中文并列结构中省略的共享后缀，例如将“压阻式和压电式传感器”解析为两个完整实体。
- “前者 / 后者”从 comparison frame 按稳定顺序解析；“那后者呢”这类省略追问会继承上一问的谓词，而不是把原始指代词交给向量检索。由此避免误命中“静态磁头 / 动态磁头”。
- 复合问题的 Evidence Support Gate 改为逐个事实维度检查。灵敏度、频响、静态测量能力、误差来源、基本公式和近似条件不再被拼成一个不可能逐字命中的长短语；多个证据块可以共同覆盖各维度。
- 真实教材证据仍不足时不会自动混入模型知识。拒答文案给出缩小问题或改用学科通用回答的引导，前端同时提供显式“改用学科通用回答”按钮；拒答本身不写入 ConceptMemory。
- 会话消息仅新增可选的建议回答模式字段；未迁移数据库、向量库、教材索引、ConceptMemory、错题或复习数据。

### Validation

- 用传感器短书真实索引重放：复杂推导题与三类传感器多维比较均由 `insufficient` 转为 `supported`；计算题进入 `calculation`；“前者”解析为压阻式传感器，“那后者呢”解析为同一谓词下的压电式传感器。
- 后端全量 pytest 通过：340 tests passed；仅有既存 Starlette/httpx2 弃用警告。
- 前端 ESLint、TypeScript、Vite 生产构建通过；Vitest 13 files / 49 tests passed。构建仅保留既有的 MathLive 大 chunk 提示。

## 2026-08-09 - 发布闸门与关键正确性收口

### 数据安全与桌面生命周期

- 将备份恢复正式定义为非破坏性的“合并恢复”：备份内的核心根目录会被替换，备份中未包含的其他核心数据会保留；恢复结果记录 `restore_mode` 与 `preserved_unlisted`，API 和设置页使用一致文案。派生向量库与 MinerU 产物仍按原策略失效，以避免旧索引和恢复数据不匹配。
- 打包后端改为显式 `uvicorn.Server`，提供受本地 API token 保护的优雅停机端点。Electron 退出时先请求取消 durable jobs、等待 Uvicorn 排空请求并退出，8 秒超时后才回退到强制终止；后端 lifespan 退出阶段释放向量库缓存引用。
- 首次引导升级隐私确认版本，明确 LLM 会接收问题、必要会话上下文和选中教材证据，Kimi OCR 会接收所选图片；“稍后再看”不再永久跳过提示。产品页同步删除“完全不上传云端、不依赖网络”的错误承诺。

### 发布合规

- 新增 `scripts/check_release_content.py`。正式包若包含样例教材、派生索引、图片或模型，必须逐文件声明来源、许可证、可再分发状态和 SHA-256；未声明、许可缺失或哈希不一致即阻止构建。样例 PDF 默认不再自动复制，历史错误的默认数据路径已修正。
- Windows release workflow 现在要求仓库存在 `LICENSE`、要求签名证书和密码，并在发布产物生成后验证安装器与主程序 Authenticode 签名。
- 当前本地 `desktop/sample_data` 仍包含未登记授权的《优化设计》PDF及派生文件，因此内容闸门按设计失败；未删除这些本地文件，也未伪造授权。补齐内容清单或从发布输入中移除后方可正式构建。

### RAG、会话与导入正确性

- teach/summarize 的同步与流式路径统一使用 Retrieval 产出的 EvidencePack；证据支持为 `insufficient/unavailable` 时直接走教材拒答，不再通过章节二次检索绕过门禁。教学提示词使用 E-id 引用协议，流式最终正文也执行 citation 清洗。
- SQLite 事件库成为会话权威存储，最近窗口 JSON 明确降级为可重建的兼容投影；JSON 写入失败不再让已提交消息或 split 操作向调用方误报失败。
- 同一 `conversation_id + turn_id + role` 重试改为幂等；断开的 SSE 会持久化 `partial` assistant 消息，重试完成后原位升级为 `complete`，避免重复 turn 和刷新后完全丢失已生成正文。
- KG 加载边界兼容当前 `content` 与旧 `text` chunk schema；`/books/import-local` 成功后将 PDF 从 staging 提升至正式教材目录，失败时执行索引、metadata、上传文件与正式 PDF 的补偿清理。
- 周报兼容错题复习和习题练习当前写入的 `date` 字段，修复本周复习数与练习数长期为零或偏低的问题。

### Validation

- 新增备份合并语义、会话幂等、partial completion、JSON 故障注入、split 投影故障、EvidencePack 拒答、KG schema、本地教材归档补偿、周报日期、内容授权闸门和优雅停机回归测试。
- 后端全量 pytest：403 passed；仅保留既有 Starlette/httpx2 弃用警告。
- 前端 Vitest：15 files / 70 tests passed；ESLint、TypeScript 与 Vite production build 通过。构建仍保留既有 MathLive 801.47 kB 大 chunk 提示。
- `node --check desktop/main.cjs` 与变更 Python 文件 AST 解析通过；`git diff --check` 无空白错误。

## 2026-08-09 - 桌面运行链路可靠性收口

### 动态端口、单实例与故障恢复

- Electron 在未显式设置 `KAOYAN_BACKEND_URL` / `KAOYAN_BACKEND_PORT` 时，启动和恢复阶段会按当前绑定范围分配可用端口；实际 API base 随一次性桌面启动参数传给前端，远程采集地址、优雅停机、健康检查和导航白名单统一使用当前端口。显式端口/URL以及 `KAOYAN_SKIP_BACKEND=1` 仍保留原有开发覆盖语义。
- 主进程取得单实例锁；重复启动只恢复、显示并聚焦已有窗口，不再并行拉起第二套后端和数据目录访问者。
- 被主进程托管的后端意外退出后最多自动恢复 3 次，使用有界指数退避并在成功后刷新到新的动态端口。前端增加“启动中 / 恢复中 / 失败”状态条，恢复耗尽后提供手动重试和打开后端日志；切换局域网采集导致的计划内重启也会刷新 API base。
- 新增可独立运行的桌面 runtime helper 与 Node 单测；CI 新增 desktop job，使用 `npm ci` 后执行 helper 测试及 Electron 脚本语法检查，打包文件显式包含 runtime helper。

### 鉴权资源与依赖锁定

- 教材 PDF、章节重点静态 HTML及其本地图片不再以裸 `/api` URL 交给 `iframe`、`img` 或新窗口。前端先通过带 `X-Kaoyan-Token` 的请求取得内容，再使用有生命周期清理的 blob URL；静态 HTML 内的本地 API 图片同样会先鉴权并改写，外部 URL 被拒绝进入本地鉴权请求，避免 token 泄漏。
- PDF 页码 fragment 只在 blob URL 上拼接一次，修复原先重复 `#page` 导致的错误预览地址。应用内重点入口改为 SPA 内导航，避免 Electron 把相对入口当成外部浏览器链接。
- `requirements.txt` 改为兼容入口，统一转到复用精确发布依赖的 `requirements-dev.txt`；pytest 固定到 `9.0.3`。新增依赖锁检查脚本，CI 与桌面发布均执行 exact-pin 检查和 fresh-env `pip check`；前端/桌面继续由 lockfile + `npm ci` 约束。PaddleOCR、Marker、MinerU 等冲突较多的可选栈明确保持在主锁之外。

### Validation

- 后端全量 pytest：403 passed；仅保留既有 Starlette/httpx2 弃用警告。
- Desktop Node tests：2 passed；`main.cjs`、`preload.cjs`、`runtime.cjs` 语法检查通过。
- Frontend Vitest：15 files / 70 tests passed；ESLint、TypeScript 与 Vite production build 通过。构建仅保留既有 MathLive 801.47 kB 大 chunk 提示。
- Python dependency exact-pin 检查通过；`git diff --check` 通过。
- 当前既有 `venv310` 仍混装了未纳入主锁的 PaddleOCR、Marker、Surya 等可选栈，`pip check` 会报告其 Pillow、protobuf、PyYAML、numpy、openai、websockets 与 fsspec 冲突。按数据/环境安全约束，本次未擅自重装或清理该环境；fresh CI/发布环境会执行并要求 `pip check` 通过。
