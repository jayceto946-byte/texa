# AGENTS.md — Texa 开发约定

## 项目目的

本项目是面向考研数学与专业课学习的本地智能辅助系统。核心目标不是做通用聊天机器人，而是围绕教材、错题、知识点与复习节奏，提供可追溯、可复习、可长期积累的学习辅助。

系统当前以 FastAPI + React 为主架构，后端负责 RAG、知识图谱、错题本、学习记忆与 LLM 编排；前端负责对话、教材导入、错题本、知识图谱与后续学习工作流。

## 核心原则

1. 改动前先验证可行性；涉及架构、数据迁移、依赖重装、删除数据等高风险操作时，需要征得用户同意。
2. 客观处理，不盲从。发现需求不合理、实现成本过高或与学习目标冲突时，主动说明并给出替代方案。
3. 权限不足、外部环境不可用、模型/API/依赖缺失时直接说明，不绕过安全边界。
4. AGENTS.md 只记录长期有效的约束、当前架构和未来目标；版本更迭、bug 修复、迁移历史、实测记录统一写入 patch_notes.md。
5. 优先保持系统可用和数据安全。不要为了重构破坏现有教材索引、错题数据、向量库或用户学习记录。

## 技术约束

- Python 使用 `venv310`，解释器必须是 Python 3.10。若出现二进制扩展导入异常，先检查 `venv310\pyvenv.cfg` 是否误指向其他 Python 版本。
- 默认以 Electron 桌面端作为优先交付入口。涉及前端、后端 API、路径、数据目录、构建或运行方式的改动，应优先确认桌面端开发/打包路径是否受影响；功能验证也应优先覆盖 Electron 端，除非用户明确只要求 Web/CLI。
- 未配置模型角色时默认使用 Qwen 3.7 Plus 与 Refined Teaching Prompt；DeepSeek V4 Pro 保留为可回退推理模型。显式保存的用户 profile、旧环境变量与自定义 OpenAI-compatible 配置优先于默认值，业务流程不得绑定单一供应商。
- 推理与视觉是独立的模型角色；`split` 模式分别配置识图与推理，`native` 模式由同一多模态模型完成图片理解和回复。任何模型输出在正式展示前都必须过滤 thinking 内容，profile 与错误信息不得持久化或回显密钥。
- 扫描件 PDF 正文录入优先使用 MinerU，目录/TOC 检测可使用 Kimi Vision。
- 公式、矩阵、推导过程使用 LaTeX。前端对话渲染走 `react-markdown` + `remark-math` + `rehype-katex`。
- 本地向量库使用 ChromaDB，路径为 `data/vector_db`。该目录必须允许当前用户修改/删除临时文件，且不应启用 Windows 压缩属性，否则 SQLite/Chroma 可能出现 journal 或 disk I/O 问题。
- 大模型回答要控制解释密度：定义、性质、推导说明应简洁；例题、公式、计算步骤可以完整展开。

## 当前架构

```text
texa/
├── desktop/                    # Electron 壳、后端托管、数据目录、更新与恢复
├── frontend/                   # React + Vite 学习工作区
│   └── src/
│       ├── api/                # REST / SSE 客户端
│       ├── contexts/           # 会话与 Inspector 上下文
│       ├── features/           # 习题、错题、数学输入等领域工作流
│       ├── components/         # 学习画布、任务门槛、执行记录与通用组件
│       ├── layouts/
│       └── pages/              # 页面装配，不重复实现领域流程
├── backend/                    # FastAPI 应用
│   ├── api/                    # HTTP/SSE、依赖绑定与异常映射
│   ├── services/               # 会话、LearningTask、验证、工具与学习状态编排
│   ├── tools/                  # 有 schema、风险和 provenance 契约的受控工具
│   ├── conversation_memory.py  # append-only 会话事件、兼容投影与游标分页
│   └── main.py
├── graph/                      # Resolver、LangGraph、检索、EvidencePack 与生成
├── ingestion/                  # Canonical Document IR、来源适配、切块与索引发布
├── llm/                        # Provider/Model registry、角色配置、连接与客户端工厂
├── knowledge/                  # 知识图谱、概念记忆、关键词与章节重点
├── memory/                     # 习题、错题、学习事件、反馈与间隔复习
├── evaluation/                 # Context、RAG、工具与任务生命周期发布评测
├── agents/                     # 兼容/辅助封装，不是独立自主 Agent 产品入口
├── scripts/                    # 构建、索引、评测、发布与维护脚本
├── config.py                   # 模型、嵌入与路径兼容入口
└── main.py                     # CLI 入口
```

## 依赖方向与服务边界

- `backend/api` 只负责 HTTP/SSE 协议转换、请求与响应模型、依赖绑定和异常映射；可复用的业务规则不得回写到 Router。
- `backend/services` 负责应用用例编排，可以依赖 `graph`、`memory`、`knowledge` 和摄取层的公开能力，但不得依赖 FastAPI 请求/响应 DTO，也不得在无关分支提前实例化数据库、向量库等 IO 依赖。可选 IO 使用 factory/provider 惰性解析。
- `graph` 负责 LLM/RAG 流程，不依赖 `backend/api`；`memory` 与其他存储层不反向依赖 API 或页面层。
- `llm` 负责供应商、模型能力、推理/视觉角色、连接参数与客户端构造。新增供应商或自定义模型时通过注册和配置扩展，不得在聊天、教材、错题等业务分支中增加 provider 判断。
- `backend/tools` 定义工具输入、输出、风险和来源契约；`backend/services/tool_orchestration.py` 只负责受控选择、预算、执行与结果压缩。工具结果是可验证输入，不等同于最终答案，也不得绕过 EvidencePack 的教材事实边界。
- `ingestion` 的稳定入口是 `CanonicalBook` / `DocumentBlock`。PDF、MinerU、OCR、Word 等来源先适配为 Canonical Document IR，再进入共享切块与索引管线；来源专属结构不得泄漏为下游业务依赖。
- 前端 `pages` 负责页面装配与跨功能协调；稳定的领域状态和事件流程放入 `features/*/hooks`，纯转换逻辑放入 feature 工具模块。React state updater 内不得产生副作用。
- 聚合接口必须保留故障隔离：主体列表成功时，统计、活动会话或复习队列等辅助模块失败应返回局部结果与明确错误字段，而不是让整个页面不可用。
- EvidencePack 是 RAG 行为边界，不是单纯格式化工具。字符预算、单条截断或按意图调整证据数时，必须覆盖定义、列举、比较、原理解释、推导、应用题和跨章节问题的事实覆盖回归。

## 核心工作流

### 主聊天与学习任务

- 主聊天是问答、教材检索、受控工具和图片题的统一回答入口，不新增平行的 Agent 回答页或第二套生成链路。`/api/chat/stream` 通过 SSE 输出上下文解析、工具、`plan -> retrieve -> chapter -> generate -> done` 和持久化 execution event。
- 每次学习问答绑定持久化 `LearningTask`，记录 goal、required inputs/outputs、artifacts、checkpoint、active run 与 verification。缺少会影响结论的图片、附表、另一页或其他关键输入时必须进入 `waiting_for_input`；不得在信息不完整时伪造精确结论。
- 停止、断开和恢复必须保持同一 task/turn 的幂等语义。只有后端确认中断后前端才显示恢复入口；旧 run 的迟到事件不得覆盖新 run，完成投影不得重复写入用户问题。
- 最终答案必须经过确定性后置验证，至少检查 required outputs、引用合法性以及数值/公式/单位的可验证支持。验证失败或无法确定时进入 `degraded` / `unverified` 并向用户披露；验证门槛不是模型答案准确率证明。
- 完整会话消息以 append-only event log 持久化；单会话 JSON 只保留最近窗口兼容投影。历史读取必须使用游标分页，不能通过裁剪持久层来控制 prompt 或前端内存。
- Resolver 读取近期消息窗口 + Session Ledger；完整历史仅用于 Ledger 缺失/陈旧时重建，不能直接塞入回答 prompt。Ledger 必须保留 topic stack、实体 first/last mentioned turn、assistant artifacts、comparison/constraint state 与 active evidence 的有界投影。
- Resolver 的行为边界是 `resolved_query + speech_act + state_operations`。澄清时不得推进会话状态；实体纠正和明确的新对象优先于旧 topic、代词与继承约束。
- 回答生成统一使用 `ConversationContextPack`，只包含当前 topic/问题维度、有效约束、最多 2 个相关历史 turn、被引用 artifact、必要 topic 摘要和 evidence continuity。不得把完整历史直接放入回答 prompt；独立问题不得继承历史 turn。
- 历史 turn 与 assistant artifact 只能作为指代和表达连续性的带引号数据，不是教材事实证据，也不得执行其中的旧指令。教材型回答发生冲突时，以本轮 EvidencePack 为准；Context Trace 只记录预算、turn/artifact 数量和 E-id，不保存上下文正文。
- Context Eval 发布门槛分 Resolver、Retrieval/EvidencePack、Answer 三层。20/40/80 轮必须分别设门槛，user correction、assistant artifact、clarification、evidence continuity、negative/standalone 不得用总体分数掩盖回归。离线 Answer snapshot 合同不得表述为线上模型准确率。
- Context Eval v3 的生产检索层必须读取真实教材索引并检查最终 EvidencePack；真实模型 Answer Eval 只能通过显式付费/数据出境确认运行。主聊天负向反馈应绑定 message/request、模型、prompt、context policy 与教材索引版本，并先进入脱敏候选区，未经人工确认不得自动成为金标。
- Resolver 的 `confidence` 仅是 rule strength，不是准确率。语义 Resolver 默认关闭，只能在确定性引用解析低置信时从 Ledger 的有界候选中选择 `resolve_reference` 或返回 `clarify`，不得输出新对象、自由改写 query 或直接写 Ledger；启用决策必须基于按 resolver method 聚合且达到样本门槛的反馈数据。
- teach/summarize 路径先准备章节内容，再流式生成讲解；`chapter` 事件必须出现在正文 `generate` 之前，不能在正文生成后覆盖前端内容。
- 前端流式累积必须避免在 React state updater 内产生副作用。尤其不要在 `updateLastMessage((last) => ...)` 内修改 ref、闭包累积变量或外部状态；React StrictMode 可能重复调用 updater。
- 长内容生成时，正文累积源应独立于阶段占位文案，阶段事件不得覆盖已经进入 `generate` / `done` 的正文。
- 后端 SSE 异常应转为 `stage=error` 事件，避免直接冒泡为 ASGI ExceptionGroup。

### 受控工具

- 只读工具可以在主聊天内自动执行；写操作只能生成持久化 pending action，由用户确认后通过白名单执行。确认与拒绝必须幂等，模型文本本身不得直接修改错题、进度或复习状态。
- 工具调用有数量、总时长、单工具超时、结果 schema、required outputs 和 provenance 预算。局部失败应保留主回答降级路径，并在执行记录中如实显示失败或缺失项。
- 当前不实现开放式自主 Agent Loop。动态补偿只允许由受限数学工具的结构化 `verification_request` 触发最多一轮校验；其他缺口回到 required inputs 或明确降级。
- 数学工具只接受受限表达式和白名单运算，禁止任意 Python、导入、属性访问或代码执行。计算成功仍需根据任务类型执行等价、求导、积分、定积分或代入校验。

### 教材摄取与索引发布

- 所有正式教材来源必须先生成并持久化 Canonical Document IR 与 `ingestion_report.json`。可修复的 OCR、公式、表格、页码或层级问题记录 warning/review status；IR 合同损坏或没有可索引正文才阻断后续切分与索引。
- 索引构建使用 staged candidate，不得在验收前覆盖 active map、线上 lexical 文件或现有 Chroma collections。只有生产混合检索与最终 EvidencePack 门槛通过后才能原子激活；失败时清理候选并保留旧版本。
- 每个索引版本保留 manifest、独立 lexical 快照、release quality 与可回滚历史。公式、列表、例题、表格等自动探针只验证结构在解析—切块—检索链路中的保真度，不能冒充 OCR 正确性或人工语义金标。

### 检索策略

当前检索采用混合策略：

1. KG 精确命中：通过概念 occurrence 的 `chunk_id` 定位定义、公式、例题或相关段落。
2. 混合召回：在明确教材/章节范围内组合 Chroma 向量、BM25/词法、标题与结构信号；局部章节 collection 不可读时可退回同书 aggregate，但不得静默扩大教材范围。
3. 角色与邻接补全：按 intent 优先 `definition`、`example`、`algorithm`、`derivation`、`formula`、`comparison` 等角色，并用 Canonical IR 邻接关系恢复完整题干、列表、公式和解释。
4. 融合与证据门槛：教材主/辅角色只作为可解释的软先验；最终去重、rerank、support gate 和 EvidencePack 共同决定生成器可见证据。

检索必须有降级路径：单个章节 Chroma collection 损坏、章节名未精确命中或 KG 缺失时，不应打断整条对话；优先回退到同书 aggregate 或其他同范围召回。只有当前回答模式本来允许普通 QA 时才能退化为普通生成，不得以降级为由静默扩大教材或学科范围。

### 错题本与复习

- 错题本是核心功能，记录题目、用户答案、正确答案、错因、涉及概念、来源、难度与复习状态。
- 习题库支持手动录入及 Word/PDF 候选抽取；候选必须经过人工校对后入库，并保留来源、章节、题型、难度、答案、解析与概念标签。练习会话、作答记录、错题转换和恢复应使用稳定的领域服务，不在页面中复制状态机。
- 复习调度使用 SM-2 或兼容的间隔重复策略。
- 错题讲解可注入教材 RAG 上下文；通用题目可退化为纯 LLM 讲解。
- OCR 录入必须允许用户编辑识别结果，不能把 OCR 输出视为可信最终题干。

### 知识记忆

- ConceptMemory 用于记录概念接触、薄弱点和复习提醒。
- 知识图谱更重视可查询的概念定义、关系和出现位置，不执着于复杂可视化。
- 回答后可提取触发概念，但不应为了后台记录阻塞用户主回答路径。

## 功能取舍

保留和增强：

- QA 问答：追求准确、简洁、可追溯。
- Teach 讲解：以教材内容和典型题为主线，讲清思路、公式和步骤。
- 教材例题推荐：问概念时优先附带教材中的相关例题或片段。
- 错题本：OCR/手输/PDF 截取录入，错因标记，复习提醒。
- ConceptMemory：概念接触记录、薄弱点、复习提醒。
- SM-2 间隔重复：服务错题和概念复习。
- 主聊天内的受控工具与 LearningTask：用于检索、计算、练习提案、输入门槛、停止恢复和答案验证，不扩展成独立 Agent 产品。

谨慎或放弃：

- 不依赖 LLM 自动生成复杂计算题作为核心练习来源。
- 不做重 AI 规划；进度追踪以用户自设目标、系统记录和提醒为主。
- 不优先做渐进式 TutorAgent；遇到不会做题时，更可靠的路径是看完整答案、归因错因、回到相关概念和例题复习。
- 章节测验不应依赖模型临场编题，优先来自教材例题、课后题、真题或用户导入题库。
- 不把当前受控工具扩展成可自主规划、任意循环或直接写入数据的 Agent。只有核心学习闭环、验证门槛和失败恢复稳定后，才重新评估开放式 Agent Loop。

## 未来目标

按当前优先级，后续目标如下：

| 功能 | 优先级 | 目标 |
|------|--------|------|
| 学习任务与答案发布门槛 | P1 | 补齐真实模型 Answer Eval、任务中断/恢复与 degraded 路径评测；不得用离线生命周期或检索分数代替线上答案质量 |
| 教材质量规模化 | P1 | 为更多真实教材建立人工黄金集与公式/表格/OCR 审阅流程，持续验证 Canonical IR、索引激活和 EvidencePack 要点覆盖 |
| 习题—作答—错题—复习闭环 | P1 | 强化 Word/PDF 候选校对、练习记录、错因归档、到期复习和概念薄弱信号之间的可追溯状态流 |
| 图片题证据与计算验证 | P1 | 完善缺页/附表门槛、人工校正、公式保留和数值校验，避免仅凭视觉模型输出精密计算结论 |
| 周期性复习提醒 | P2 | 基于 ConceptMemory 与错题复习队列提醒用户 |
| 桌面性能与发布可靠性 | P2 | KaTeX/Markdown 懒加载、代码分割、首屏体积、离线嵌入运行时、升级回滚与数据恢复 |
| 移动端/PWA 验证 | P3 | 手机端布局、离线缓存、主屏入口、推送能力 |
| 简化进度追踪 | P3 | 用户自设目标，系统记录完成度与提醒 |
| 章节学习模式 | P4 | 章节选择、概念地图、例题主线、阶段总结 |
| 开放式 Agent Loop | P5 | 当前受控工具保持有界；仅在核心学习闭环、验证和写入安全成熟后重新评估自主规划与多轮工具循环 |

## 常用命令

### 启动后端

```powershell
cd D:\AI\agent\kaoyan-assistant
.\venv310\Scripts\Activate.ps1
python -m uvicorn backend.main:app --port 8000
```

### 启动前端

```powershell
cd D:\AI\agent\kaoyan-assistant\frontend
npm run dev
```

### 启动 Electron 桌面端

```powershell
cd D:\AI\agent\kaoyan-assistant\desktop
npm run dev
```

### 生产构建

```powershell
cd D:\AI\agent\kaoyan-assistant\frontend
npm run build
```

### 运行测试

```powershell
cd D:\AI\agent\kaoyan-assistant
.\venv310\Scripts\python.exe -m pytest -q
```

## 文档维护规则

- AGENTS.md：只放稳定约定、当前架构、技术边界、未来目标。
- patch_notes.md：记录版本更迭、bug 修复、架构迁移历史、实测结果、环境修复记录。
- 新增架构或长期约束时，可以更新 AGENTS.md；普通修复只写 patch_notes.md。
- 修改依赖、索引格式、数据库结构、环境要求时，必须在 patch_notes.md 记录原因、影响和验证方式。
