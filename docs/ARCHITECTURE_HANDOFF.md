# Texa Architecture Handoff

> 本文档基于当前仓库只读静态分析生成，供后续 Codex / 工程 agent 继续处理时快速对齐现状。
> 生成阶段未修改任何源码文件；本文档为唯一新增交付物。
> 验证状态：本轮未运行 pytest / compileall / 启动验证；文中“已完成”表示代码层面已完成对应修改，后续仍需按第 6 节执行验证。

---

## 1. 当前系统状态

### 1.1 主要架构

| 层 | 实际位置 | 说明 |
|---|---|---|
| Electron frontend | `desktop/main.cjs`、`desktop/preload.cjs`、`desktop/backend_server.py` | 桌面壳：启动本地 FastAPI，加载 React 构建产物，管理本地 token 与用户数据目录 |
| React/Vite frontend | `frontend/src`，入口 `frontend/src/main.tsx`、路由 `App.tsx` | 学习对话、教材、习题、错题、学习情况、设置等页面 |
| FastAPI backend | `backend/main.py`，路由在 `backend/api/*` | 12+ 组 API；开发/生产均以 `backend.main:app` 为唯一后端入口 |
| Graph/LangGraph orchestration | `graph/`，核心 `graph/main_graph.py` | 当前存在两条执行路径：编译图 `run_graph()` 与手动流式 `run_graph_stream()` |
| RAG pipeline | `ingestion/`、`graph/retrieval_node.py`、`graph/evidence_pack.py` | PDF/MinerU/OCR 摄取 → 切分 → 词法索引 + Chroma 向量索引 → KG/向量/BM25 混合检索 → evidence pack → 生成 |
| Conversation/context system | `backend/conversation_memory.py`、`backend/services/session_context.py`、`backend/services/session_ledger.py`、`backend/services/evidence_continuity.py`、`graph/conversation_context.py` | SQLite 事件表 + JSON 投影 + session ledger 派生缓存；追问解析、学习 speech act、evidence 连续性统一在此 |
| Evidence/citation system | `graph/evidence_pack.py`、`utils/citation_protocol.py`、`frontend/src/utils/citations.ts` | 证据块 `[E1]...`，模型输出 `[[cite:E1]]`，后端清洗后前端渲染引用 |
| AgentState 管理 | `graph/state.py`、`graph/main_graph.py: build_initial_state()` | `TypedDict` 定义；仅 `messages` 使用 `operator.add` reducer，其余字段默认 LangGraph `LastValue` channel |

### 1.2 当前主链路

```
用户请求
  → frontend/src/api/client.ts（chatStream / chatAsk）
  → POST /api/chat/stream 或 /api/chat/ask
  → backend/api/chat.py
      1) resolve_conversation_id_for_scope + load_history
      2) _resolve_request_question（session ledger + resolver + learning bridge）
      3) build_evidence_continuity_context + _conversation_context_seed
      4) decide_answer_scope（backend/services/textbook_scope.py）
  → graph execution
      流式：run_graph_stream() 手动执行 plan → retrieve → [chapter] → generate → feedback
      非流式：run_graph() 编译图执行相同节点序列
  → retrieval
      graph/retrieval_node.py：KG precise + dense vector + lexical BM25 + neighbor，
      _merge_and_rerank 融合排序，evidence_support gate
  → generation
      graph/generator.py：prompt 组装、stream/非流式生成、LaTeX/引用清洗
  → persistence
      backend/conversation_memory.py：append_message（SQLite + JSON 投影）
      backend/services/session_ledger.py：record_assistant_in_ledger
      backend/rag_trace.py：save_trace
  → SSE 阶段事件 / JSON response 返回前端
```

---

## 2. 已完成修改

### 2.1 evidence_sources 修复

- **原问题**：非流式 `/api/chat/ask` 返回的 `sources` 恒为空。
- **根因**：
  - `graph/generator.py` 中 `_build_generate_prompt()` 会把 `evidence_pack["items"]` 写入 `state["evidence_sources"]`；
  - 但 `generate_node()` 的返回字典未携带 `evidence_sources`；
  - LangGraph 编译图只传播节点返回值，节点内原地写入不能保证进入最终 state；
  - 因此 `run_graph()` 结果缺少 `evidence_sources`，`backend/api/chat.py` 的 `/ask` 只能拿到空列表。
- **修改位置**：
  - `graph/generator.py`：`generate_node()` 的 `subject_mismatch`、无证据、正常生成三个返回分支均返回 `"evidence_sources": state.get("evidence_sources") or []`。
  - `graph/chapter_subgraph.py`：`chapter_subgraph_run()` 无内容返回与正常返回均返回 `evidence_sources`（teach/summarize 非流式路径依赖此节点传播）。
  - `graph/main_graph.py`：`build_initial_state()` 初始化 `"evidence_sources": []`。
- **当前行为**：
  - 流式与非流式路径都返回 `evidence_sources`；
  - 数据结构保持不变，仍是 `evidence_pack["items"]` 的 list，元素包含 `id/chunk_id/book_name/chapter/section_title/section_path/label/chars` 等字段；
  - 未修改 evidence pipeline 与 retrieval 逻辑。

### 2.2 AgentState schema 收敛

- **新增字段**：
  - `_local_intent: str`
  - `_local_intent_hint: str`
  - `_local_intent_locked: bool`
  - `evidence_sources: list[dict]`
  - `evidence_gate_applied: bool`
  - `active_evidence_invalidation_reason: str`
- **初始化方式**（`graph/main_graph.py: build_initial_state()`）：
  - `_local_intent` 默认 `"qa"`，`_local_intent_hint` 默认 `"无"`，`_local_intent_locked` 默认 `False`，与原先 `plan_node()` 使用 `state.get(..., 默认值)` 的语义一致；
  - `evidence_sources` 默认 `[]`；
  - `evidence_gate_applied` 默认 `False`；
  - `active_evidence_invalidation_reason` 从 continuity context 透传，默认 `""`。
- **为什么保持 LastValue channel**：
  - 只有 `messages` 是 `Annotated[list[dict], operator.add]`；
  - 其余字段均未使用 `Annotated`，LangGraph 默认使用 `LastValue`；
  - 新增字段由单一节点或初始化逻辑写入，不需要 reducer 聚合，保持 LastValue 即可。

### 2.3 Legacy UI 清理

- deprecated Gradio Web 入口已删除；`ui/` 只保留 legacy developer CLI。
- `requirements*.txt` 不包含 Gradio 依赖。
- **main.py web 入口**：
  - `main.py` 现在支持 `cli` 与 `web` 两种 mode；
  - `python main.py web --host 127.0.0.1 --port N` 会执行 `uvicorn.run("backend.main:app", ...)`；
  - `cli` mode 仍保留为 legacy developer CLI。
- **launch/install 脚本变化**：
  - `launch.ps1`：依赖检查从 `gradio/langchain/sentence_transformers/chromadb` 改为 `fastapi/uvicorn/langchain/chromadb`；进程清理匹配 `uvicorn` / `backend.main`；启动命令改为 `python main.py web --host 127.0.0.1 --port $Port`。
  - `install.ps1`：生成的 `启动Web.bat` 改为 `python "...\main.py" web --host 127.0.0.1 --port 8000`；使用说明改为 FastAPI 后端。

---

## 3. 当前确认稳定部分

以下模块当前被视为主链路稳定区，**不要轻易修改**：

| 模块 | 原因 |
|---|---|
| `graph/retrieval_node.py` | 混合检索、融合排序、evidence support gate 已形成闭环，且包含降级逻辑；修改容易影响引用质量 |
| `graph/evidence_pack.py` | evidence 数据结构是前后端 + 引用的契约；结构变化会同时影响生成、citation、持久化与 UI |
| `backend/services/evidence_continuity.py` + `graph/retrieval_policy.py` | evidence reuse/delta/full 策略依赖 topic、scope、corpus_version 的精确判断，逻辑链长 |
| `backend/services/session_context.py` + `backend/services/session_ledger.py` | 追问解析与 ledger 重建逻辑复杂；当前可用，不宜小范围随意改动 |
| `desktop/backend_server.py` + `desktop/main.cjs` | Electron 后端启动与恢复链路已验证；不应与开发入口 `main.py web` 混改 |
| `frontend/src/api/client.ts` + `frontend/src/utils/citations.ts` | SSE 事件结构、sources 结构与引用解析是前后端契约；变更必须前后端同步 |
| `ingestion/index_pipeline.py` | 版本化、staging、原子切换的索引构建流程已稳定；重建风险高 |
| `backend/conversation_memory.py` 的 SQLite schema | 历史会话已落库；schema 变更需要迁移，不应顺手改动 |

---

## 4. 未完成问题（重点）

### P1: Quiz Agent / Learning Loop

**当前状态**：
- `graph/intent_classifier.py` 已支持 `quiz` 意图（关键词：出题/测验/练习等）。
- 但 `graph/main_graph.py` 只把 `teach/summarize` 路由到 chapter subgraph，`quiz` 直接进入 generate。
- `graph/generator.py: _format_quiz_appendix()` 依赖 `state["quiz_questions"]`，但没有任何节点填充它。
- `graph/chapter_subgraph.py: _generate_quiz()` 已存在，但 `prepare_chapter_subgraph()` 未真正启动后台出题任务（executor/futures 恒为空）。
- `agents/quiz_agent.py` 也有出题实现，但与主 graph 未连接。

**未来目标**：

```
question generation
  → answer evaluation
  → mastery update
  → review scheduling
```

这意味着下一阶段不只是“让 quiz 出题”，还要把练习结果写入 `memory/exercise_bank.py` / `memory/spaced_repetition.py` / `memory/learning_events.py`，形成学习闭环。

---

### P2: Stream / Non-stream pipeline 统一

**当前存在**：
- `graph/main_graph.py` 中 `run_graph()` 走 LangGraph 编译图。
- `run_graph_stream()` 手动按顺序调用 `plan_node → retrieve_node → prepare_chapter_subgraph → generate → feedback thread`。

**风险**：
- 节点序列、条件路由、state 合并规则在两处重复实现，未来新增节点或修改路由时可能只改一处，导致两条路径行为漂移。

**建议后续考虑**：
- 抽象共享 execution layer（节点序列 + 路由 + state 更新规则单一定义），流式与非流式只保留渲染差异。
- 不要立即迁移 LangGraph streaming；先用共享编排层降低漂移风险。

---

### P3: Context / State 管理

**包括**：
- `AgentState` 字段已经较完整，但仍在增长；未来应避免把纯 UI 字段继续堆入同一状态对象。
- context resolver（`backend/services/session_context.py`）与 conversation continuity 逻辑复杂，但当前可用。
- 会话存储存在 SQLite 事件表 + JSON 投影 + session ledger 三层，derived cache 重建逻辑依赖 `last_message_id` 比对；短期不重构，但新功能要避免引入第四套会话状态。
- `active_evidence_invalidation_reason` 已能透传入 state，但要注意其与 `same_topic` 的兜底关系，不要单独依赖该字段做路由判断。

**说明**：当前可用，长期需要治理；治理应在功能迭代之外单独立项。

---

### P4: Retrieval 优化

**包括**：
- `graph/retrieval_node.py` 中 `_search_chapter_with_role()` / `_search_all_with_role()` 名为 role-aware，但实际未使用 `priority_roles` 参数，role 只在融合排序阶段生效。当前不影响功能，但命名与实现不一致。
- `backend/rag_trace.py` 只保存 chunk_id/chapter/section_title/source/score，丢失 `fusion_sources/relevance_score/textbook_role_multiplier/query_coverage` 等排序依据，线上排序问题难以复现。
- `section_path` 在检索项中可能是 JSON 字符串或 list，最终由 `graph/evidence_pack.py` 的 `_section_path()` 兼容解析；建议未来在入站边界统一为 list。

**说明**：属于优化项，不影响当前功能；不要作为下一阶段首要任务。

---

## 5. 明确禁止下一阶段直接做的事情

**不要**：
- 全面重构 graph；
- 迁移 LangGraph streaming；
- 大规模拆分文件（即使 `backend/api/chat.py`、`graph/retrieval_node.py` 等较长）；
- 重写 RAG pipeline；
- 改变 evidence 数据结构；
- 修改 `backend/conversation_memory.py` 的 SQLite schema；
- 改动前端 SSE 事件字段或 sources 结构而不做前后端联调；
- 删除 legacy surface 后再顺手重构周边模块。

**原因**：
当前系统需要稳定迭代，而不是重新设计。上一阶段已经出现“同一能力多处实现、启动入口不统一”等问题，但修复应当按阶段小步进行，避免在验证不足时引入新风险。

---

## 6. 建议下一阶段开发顺序

### Phase 1：验证当前修复

- 运行 `python -m compileall graph backend ui main.py`；
- 运行 `python -m pytest -q`；
- 启动 `backend.main:app`，确认 `/health` 正常；
- 调用 `/api/chat/ask` 确认 `sources` 返回非空（需已导入教材并建立索引）；
- 启动 Electron，确认桌面后端与窗口正常；
- 验证 `python main.py web` 启动 `backend.main:app`。

### Phase 2：设计并实现 Quiz Agent

- 先梳理 `quiz` 意图在 stream / non-stream 两条路径中的统一接入点；
- 实现 question generation → answer evaluation → mastery update → review scheduling 的最小闭环；
- 复用 `graph/chapter_subgraph._generate_quiz()` 或 `agents/quiz_agent.py` 中的可用逻辑，收敛为单一实现；
- 不要同时改 retrieval / evidence 结构。

### Phase 3：统一 graph execution

- 抽取共享节点序列与路由规则，让 `run_graph()` 与 `run_graph_stream()` 复用同一编排定义；
- 保持 SSE 事件格式与前端契约不变；
- 暂不强制使用 LangGraph streaming API，先消除重复编排。

### Phase 4：架构清理

- 删除或正式归档 `agents/` 中的死代码；
- 处理 `backend/api/chat.py`、`graph/retrieval_node.py` 等长文件拆分；
- 统一 `launch.ps1` / `install.ps1` / Vite 代理的默认端口；
- 清理仓库根目录中的运行时数据、备份与发布产物。

---

## 7. 给后续 Agent 的工作原则

- **优先理解现有数据流**：动手前先沿第 1 节主链路走一遍，确认真实调用链。
- **修改前定位真实调用链**：不要只根据文件名或模块名推断；先找到 API → graph → persistence 的实际 import 与返回路径。
- **小步修改**：每次只处理一个行为变化，避免把“修 bug”和“顺手优化”混在一个变更里。
- **保留行为兼容**：前端 SSE 事件、sources/evidence 结构、会话持久化格式是外部契约；变更必须保持兼容或明确迁移。
- **不因代码规模进行无意义重构**：长文件、旧代码不是必须立即清理的理由；优先处理会导致行为错误或漂移的问题。
- **验证优先**：完成任一阶段后，至少运行 compileall、pytest，并做一次流式 + 非流式的手动对比验证。
