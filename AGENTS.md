# AGENTS.md — 考研智能辅助系统开发约定

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
- 主要 LLM 使用 DeepSeek V4 Pro 思考模式，正式展示给用户前必须过滤 thinking 内容。
- 扫描件 PDF 正文录入优先使用 MinerU，目录/TOC 检测可使用 Kimi Vision。
- 公式、矩阵、推导过程使用 LaTeX。前端对话渲染走 `react-markdown` + `remark-math` + `rehype-katex`。
- 本地向量库使用 ChromaDB，路径为 `data/vector_db`。该目录必须允许当前用户修改/删除临时文件，且不应启用 Windows 压缩属性，否则 SQLite/Chroma 可能出现 journal 或 disk I/O 问题。
- 大模型回答要控制解释密度：定义、性质、推导说明应简洁；例题、公式、计算步骤可以完整展开。

## 当前架构

```text
kaoyan-assistant/
├── main.py                     # CLI 入口
├── config.py                   # LLM、嵌入模型、路径配置
├── agents/                     # Agent 封装，与 UI 解耦
├── graph/                      # LangGraph 主流程与节点
│   ├── main_graph.py           # 主图、run_graph_stream()
│   ├── planner.py              # 意图规划与章节定位
│   ├── retrieval_node.py       # 混合检索
│   ├── chapter_subgraph.py     # 章节讲解路径
│   ├── generator.py            # 回答生成
│   ├── evidence_pack.py        # 有预算、按意图裁剪的统一证据包
│   └── feedback_node.py        # 反馈闭环
├── ingestion/                  # 教材摄取、解析、向量索引
│   ├── pdf_parser.py
│   ├── kimi_reader.py
│   ├── background_reader.py
│   ├── chapter_splitter.py
│   ├── vector_store.py
│   └── ocr.py
├── knowledge/                  # 知识层
│   ├── knowledge_graph.py
│   ├── concept_memory.py
│   ├── keyword_index.py
│   └── kg_visualizer.py
├── memory/                     # 学习记录、错题、间隔重复
│   ├── study_memory.py
│   ├── spaced_repetition.py
│   ├── mistake_book.py
│   └── feedback.py
├── backend/                    # FastAPI 后端
│   ├── main.py
│   ├── schemas.py
│   ├── services/               # 应用用例编排、缓存与跨存储协调
│   │   ├── exercise_practice.py
│   │   ├── kg_learning_summary.py
│   │   └── mistake_images.py
│   └── api/                    # 协议转换、依赖绑定与异常映射
│       ├── chat.py             # SSE / 非流式对话
│       ├── exercises.py        # 习题库与练习会话
│       ├── mistakes.py         # 错题本 CRUD 与讲题
│       ├── books.py            # 教材管理
│       └── kg.py               # 知识图谱 API
├── frontend/                   # React + Vite 前端
│   └── src/
│       ├── contexts/ChatContext.tsx
│       ├── api/client.ts
│       ├── hooks/useChat.ts
│       ├── features/           # 习题、错题等领域工作流与局部组件
│       ├── components/
│       ├── layouts/
│       └── pages/              # 页面装配，不重复实现领域工作流
└── ui/                         # CLI 保留；Gradio web 已废弃
```

## 依赖方向与服务边界

- `backend/api` 只负责 HTTP/SSE 协议转换、请求与响应模型、依赖绑定和异常映射；可复用的业务规则不得回写到 Router。
- `backend/services` 负责应用用例编排，可以依赖 `graph`、`memory`、`knowledge` 和摄取层的公开能力，但不得依赖 FastAPI 请求/响应 DTO，也不得在无关分支提前实例化数据库、向量库等 IO 依赖。可选 IO 使用 factory/provider 惰性解析。
- `graph` 负责 LLM/RAG 流程，不依赖 `backend/api`；`memory` 与其他存储层不反向依赖 API 或页面层。
- 前端 `pages` 负责页面装配与跨功能协调；稳定的领域状态和事件流程放入 `features/*/hooks`，纯转换逻辑放入 feature 工具模块。React state updater 内不得产生副作用。
- 聚合接口必须保留故障隔离：主体列表成功时，统计、活动会话或复习队列等辅助模块失败应返回局部结果与明确错误字段，而不是让整个页面不可用。
- EvidencePack 是 RAG 行为边界，不是单纯格式化工具。字符预算、单条截断或按意图调整证据数时，必须覆盖定义、列举、比较、原理解释、推导、应用题和跨章节问题的事实覆盖回归。

## 核心工作流

### 对话与讲解

- `/api/chat/stream` 使用 SSE 输出阶段事件：`plan -> retrieve -> chapter -> generate -> done`。
- teach/summarize 路径先准备章节内容，再流式生成讲解；`chapter` 事件必须出现在正文 `generate` 之前，不能在正文生成后覆盖前端内容。
- 前端流式累积必须避免在 React state updater 内产生副作用。尤其不要在 `updateLastMessage((last) => ...)` 内修改 ref、闭包累积变量或外部状态；React StrictMode 可能重复调用 updater。
- 长内容生成时，正文累积源应独立于阶段占位文案，阶段事件不得覆盖已经进入 `generate` / `done` 的正文。
- 后端 SSE 异常应转为 `stage=error` 事件，避免直接冒泡为 ASGI ExceptionGroup。

### 检索策略

当前检索采用混合策略：

1. KG 精确命中：通过概念 occurrence 的 `chunk_id` 定位定义、公式、例题或相关段落。
2. 向量补充：使用 ChromaDB 在目标章节或全库检索相关 chunk。
3. 语义角色过滤：按 intent 优先检索 `definition`、`example`、`algorithm`、`derivation` 等 role。
4. 去重重排：精确命中优先，向量结果补充；例题场景需要尽量带回完整题干、步骤和相邻 chunk。

检索必须有降级路径：单个 Chroma collection 损坏、章节名未精确命中或 KG 缺失时，不应打断整条对话，应回退到更宽的向量检索或普通 QA 生成。

### 错题本与复习

- 错题本是核心功能，记录题目、用户答案、正确答案、错因、涉及概念、来源、难度与复习状态。
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

谨慎或放弃：

- 不依赖 LLM 自动生成复杂计算题作为核心练习来源。
- 不做重 AI 规划；进度追踪以用户自设目标、系统记录和提醒为主。
- 不优先做渐进式 TutorAgent；遇到不会做题时，更可靠的路径是看完整答案、归因错因、回到相关概念和例题复习。
- 章节测验不应依赖模型临场编题，优先来自教材例题、课后题、真题或用户导入题库。

## 未来目标

按当前优先级，后续目标如下：

| 功能 | 优先级 | 目标 |
|------|--------|------|
| 习题库建设 | P1 | 支持 Word/PDF/真题解析，题目结构化、知识点标注、来源追踪 |
| 图片上传与 OCR | P1 | 错题录入支持图片上传、OCR、人工校正、公式保留 |
| 错题复习工作流 | P1 | 到期复习、薄弱点统计、按概念/错因/来源筛选 |
| 周期性复习提醒 | P2 | 基于 ConceptMemory 与错题复习队列提醒用户 |
| 前端性能优化 | P2 | KaTeX/Markdown 懒加载、代码分割、首屏体积下降 |
| 移动端/PWA 验证 | P3 | 手机端布局、离线缓存、主屏入口、推送能力 |
| 简化进度追踪 | P3 | 用户自设目标，系统记录完成度与提醒 |
| 章节学习模式 | P4 | 章节选择、概念地图、例题主线、阶段总结 |
| Tool Calling / Agent Loop | P5 | 仅在核心学习闭环稳定后再引入 |

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