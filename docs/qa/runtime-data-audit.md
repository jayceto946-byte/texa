# Runtime、会话与 Goal 数据审计

日期：2026-10-11。范围：`backend/api/chat.py`、`agent.py`、`goals.py`、`conversation_protocol.py`，LearningTask、OwnedStreamingResponse、ConversationManagement、Runtime/Goal 服务及会话权威存储；只读产品代码。已阅读根 AGENTS.md。未启动 Electron、未访问真实用户数据、未调用付费/远程模型，未迁移数据库或修改产品代码。已有脏文件未修改。

## 实际入口 → 服务 → 存储

| 入口 | 实际链路 | 权威存储和重要边界 |
| --- | --- | --- |
| `POST /api/chat/stream` | `_chat_stream` 先发 context progress → `prepare_owned_response(_prepared_chat_stream)` → `_prepare_chat_turn` → 规则 Resolver / Session Ledger / learning bridge → 原 graph stream 或满足开关与 capability 的 Runtime binding | 原链路 `LearningTaskStore(PROGRESS_PATH/learning_tasks/*.json)`；终态 event 与消息/effects 先提交 frozen outcome，再投影会话。Runtime 链路为 `PROGRESS_PATH/agent_runtime.db`。SSE由 OwnedStreamingResponse 拥有 producer 和关闭回调。 |
| Runtime chat 分支 | `try_chat_response` → DecisionRouter / 有界 candidates → RuntimeStore.create/configure_chat → `stream_run` 后台线程 → BoundedAgentRunner → 工具/答案发布验证 → RuntimeStore.close | SQLite 同事务保存 task/run、执行事件与 outbox；`RuntimeOutboxProjector` → append_message，固定 `msg_<task_id>`，失败留 outbox 供 retry。回答 delta 在 SSE 由终态生成，未作为永久 milestone 存储。 |
| `POST /api/chat/ask` | prepare → 同 graph/验证合同 → LearningTask outcome → 会话投影 | 为兼容非流式入口；未另建自主 Agent 产品。 |
| `/api/chat/tasks/{id}/interrupt`, `resume-stream`, `events` | locator 分辨 Runtime/legacy；Runtime owner/revision fence 或 legacy active_run_id fence；resume 保留 task/turn，事件 replay 校验 task/run 关联 | Runtime SQLite 与 legacy JSON 各自权威；不能用旧消息里的 LearningTask snapshot 执行状态变更。 |
| 会话读取及 `/conversations/{id}/management` | chat adapter → ConversationManagementService / load_message_page | `PROGRESS_PATH/conversations/_conversation_events.db` 的 append-only conversation_events 与 conversation_messages 投影；兼容 JSON 最多近期40条，Resolver近期48条，数据库仍保留完整历史。管理 metadata/幂等 receipts 独立表，不增加消息事件。 |
| 会话 archive/trash/cancel | ConversationManagementService → shared GOAL_CONTROL_LOCK → 扫描 legacy task authority / 只读 Runtime SQL → CAS与幂等 receipt | 未完成/unknown write阻止 archive/trash；回收站阻止新 user message / 新 task；明确取消保留部分内容。管理操作不级联删除其他资产。 |
| Session Ledger / ContextPack | `_resolve_request_question` → get_or_rebuild_session_ledger → build_resolution_trace → bounded conversation context seed | 同会话 SQLite 的 conversation_ledgers；仅过期时从权威消息重建，当前实现重建最多5000条。生成 ContextPack 最多2个相关原文 turn，独立问题不继承历史。 |
| `/api/agent/tools/call`, deprecated `/read-only` | 工具 registry → ToolOrchestration；兼容 read-only入口可选有界合成 | 不是主聊天替代入口；只读工具可自动运行，写提案交 pending action。此次仅静态检查该兼容入口，未执行其模型合成。 |
| `/api/agent/actions/{id}/confirm|reject` | PendingActionStore → locator 判断 Runtime → RuntimeWriteService/resolve_runtime_action 或 legacy confirmation → 学习任务投影 | frozen approval、args hash、revision与领域receipt限制重试；unknown write没有receipt不能自动重试。 |
| `/api/goals`、commands、run、schedule | GoalService → GoalStore；显式 run → execution.start_goal → prepare registry/adapter → 同 Runtime → Goal worker；schedule → 本地 GoalScheduleWorker.tick | `PROGRESS_PATH/goals.db` 保存 goals/revisions/run_links。Runtime trigger_kind/id为goal或schedule，独立运行conversation_id/turn_id为空。pause/关键变更共享锁并 fence run；重启不自动重新模型执行。 |
| 后端启动恢复 | RuntimeRecoveryWorker.recover → recover_unfinished；周期 project_outcomes | 仅关闭未完成 run并重放outbox；执行中的写操作标记unknown，读操作failed，不重跑模型或工具。 |

## 执行证据

解释器：`venv310/bin/python`，实测 Python 3.10.21；pyvenv.cfg 与3.10运行时一致。全部测试进程指定 `DATA_DIR=/private/tmp/texa-runtime-audit-data` 与 `PROGRESS_PATH=/private/tmp/texa-runtime-audit-data/progress`，pytest fixture 使用独立 tmp_path；模型/检索相关测试使用 fake adapter、fake graph或 monkeypatch。没有使用生产 `data/`。

| 检查 | 结果 | 证据 / 覆盖 |
| --- | --- | --- |
| 正常：task状态、公用capability、Goal revision/测量 | PASS（已执行） | `test_learning_task_state_machine.py`, `test_agent_goals_p3.py`, `test_agent_goals_api.py`；测量有refs仍是unverified，不自动宣称掌握。 |
| 正常：Runtime tool→发布→SSE→SQL/outbox→消息；Goal后台运行 | PASS（已执行） | `test_agent_runtime_chat_binding.py`, `test_agent_runtime_p0.py`, `test_goal_execution.py`；fake模型下真实服务/SQLite及TestClient。 |
| 边界：同request重试、并发claim、旧owner、预算、未知schema、task/run replay关联 | PASS（已执行） | `test_agent_runtime_p0.py`, `test_learning_task_state_machine.py`, `test_agent_runtime_chat_binding.py`。 |
| 边界：完整历史/游标、legacy导入一次、并发append、40/48窗口、80轮Ledger；独立问题与2-turn上限 | PASS（已执行） | `test_conversation_event_store.py`, `test_conversation_memory_concurrency.py`, `test_conversation_context_pack.py`。 |
| 边界：管理CAS/receipt、分页scope、busy/unknown write、trash准入、恢复 | PASS（已执行） | `test_conversation_management.py`。 |
| 失败：投影/JSON写失败、domain receipt后Runtime提交失败、数据库事务回滚、工具超时/迟到、启动恢复不执行 | PASS（已执行） | `test_conversation_event_store.py`, `test_agent_runtime_p2_recovery.py`, `test_agent_runtime_p0.py`。 |
| 失败：SSE单个终态与task匹配、已确认中断防迟到、索引变更拒绝旧resume、pending action门槛 | PASS（已执行） | `test_chat_stream_reliability.py`, `test_agent_runtime_p4_contract.py`。 |
| 原graph同步/stream语义一致、章节/证据生成前准备 | PASS（已执行） | `test_chat_execution_parity.py`及stream reliability；不表示真实模型答案准确率。 |
| 失败：关闭回调异常仍释放producer | FAIL（已复现） | R1，`evidence/runtime-owned-close-repro.log`。 |
| 失败：异常消息凭证过滤 | FAIL（已复现） | R2，`evidence/runtime-error-redaction-repro.log`；仅使用人工合成canary。 |
| Electron实际断网/退出/升级恢复，真实provider行为，生产SQLite/真实教材与真实图片输入 | 未执行 | 本子审计禁止真实数据/付费调用；不能据fake测试宣称通过。 |

两批现有测试：78 passed + 41 passed = **119 passed**。日志分别为 `evidence/runtime-data-pytest.log` 和 `evidence/runtime-stream-pytest.log`。警告为Starlette/AnyIO及SWIG deprecation；未出现测试失败。

重跑第一批：

```sh
DATA_DIR=/private/tmp/texa-runtime-audit-data PROGRESS_PATH=/private/tmp/texa-runtime-audit-data/progress venv310/bin/python -m pytest -q tests/test_learning_task_state_machine.py tests/test_conversation_event_store.py tests/test_conversation_memory_concurrency.py tests/test_conversation_management.py tests/test_conversation_context_pack.py tests/test_agent_runtime_p0.py tests/test_agent_runtime_p2_recovery.py tests/test_agent_runtime_chat_binding.py tests/test_agent_goals_p3.py tests/test_agent_goals_api.py --basetemp=/private/tmp/texa-runtime-audit-pytest
```

第二批同样隔离环境，执行 `tests/test_chat_stream_reliability.py tests/test_chat_execution_parity.py tests/test_goal_execution.py tests/test_agent_runtime_p4_contract.py`，basetemp为 `/private/tmp/texa-runtime-stream-pytest`。

## 发现

### R1 — P2：关闭栅栏写入异常会永久跳过producer释放

证据：`backend/services/owned_stream.py:33–47`，aclose先置closed=True，再执行on_close；on_close位于producer close的try外。注入OSError后，首次aclose抛错、producer.close调用次数为0；第二次aclose直接返回，调用次数仍为0。正常重复关闭则只调用close一次。复现脚本与日志位于 `evidence/runtime-owned-close-repro.py` / `.log`。

触发：disconnect/response结束时，`close_task_run` 的LearningTask读取/原子写入失败，或Runtime `pause` 的SQLite读取/写入失败。`_chat_stream`最终也await prepared.aclose（chat.py:1692–1694）。影响：producer的finally不会由该owner执行，provider iterator/resource清理失去保证；可能伴随response尾部异常。没有证明真实provider泄漏或恢复中的数据损坏，故不扩大结论。

根因：把“已开始清理”当作“清理完成”，而且fence与producer释放没有finally关系。**高置信最小修复候选**：让producer close在on_close失败时仍由finally执行；保留原栅栏错误并规定两种清理同时失败时的异常优先级；增加callback抛OSError和正常幂等close的回归。不应吞掉fence失败并宣称中断已确认。

### R2 — P1：stream异常直接回显未脱敏文本

证据：`backend/api/chat.py:1685`把任意preflight异常的str(exc)作为ExecutionEvent.summary；离线patch `_prepared_chat_stream`抛带合成 `api_key=sk-SYNTHETIC-AUDIT-CANARY-NOT-A-REAL-KEY` 的RuntimeError，消费 `_chat_stream` body_iterator后canary原样出现在SSE。`execution_events.py`仅限长，没有凭证过滤。日志为 `evidence/runtime-error-redaction-repro.log`。

静态扩展：generation失败也把str(exc)存入checkpoint detail并回显（chat.py:1598–1608）。此次已执行证明的是preflight SSE回显；未执行真实provider泄密或generation持久化canary，不把二者算作已实测。并非所有provider错误一定含密钥，但该异常边界允许它通过，违反AGENTS.md“错误信息不得持久化或回显密钥”。

根因：把内部异常字符串直接当用户错误文案；限长不等于脱敏。建议对外使用稳定错误码/友好文案，checkpoint也使用安全摘要；内部日志同样考虑脱敏。验证用人工合成canary覆盖preflight、generation和持久化，禁止读取真实密钥。

## 结论与限制

状态/并发/投影等现有合同在119个隔离测试中通过，但错误文本与异常清理各有一个实际复现缺口。优先处理R2的信息边界；R1是独立、范围小、可回归的修复候选。此次没有修改实现或patch_notes，没有把静态检查、fake模型测试、Web TestClient当成Electron/真实模型验收。

## 后续授权修复（FIXED，2026-10-11）

上述内容记录**修复前**只读审计与故障复现。随后主审计授权仅修改 `backend/services/owned_stream.py`、`backend/api/chat.py` 和新增聚焦回归测试；未修改依赖、数据库结构、AGENTS或patch_notes，既有用户脏文件仍未触碰。

| ID | 状态 | 实际修复 | 执行验证 |
| --- | --- | --- | --- |
| R1 | FIXED | on_close执行置于try，producer close置于finally；callback异常仍向上传播；producer同时失败时原fence异常为主异常、producer异常为cause；正常幂等关闭维持一次调用。 | 新增6组sync/async producer + callback OSError / producer无错、ValueError、OSError；另验fence成功时producer异常不被掩盖。全部PASS。 |
| R2 | FIXED（本次发现边界） | 复用`backend.rag_trace._redact_diagnostic`，chat-local `_safe_chat_error`在限长前脱敏；preflight保留安全summary并新增payload error_code/error_type；generation SSE与LearningTask checkpoint均用脱敏文本；流式generation日志保留类型和安全消息、不回显原异常traceback；兼容`/ask`generation checkpoint同步修复。 | canary preflight SSE；流式及`/ask`异常持久化；流式caplog无canary。全部PASS。 |

共享helper选择证据：先检查utils/backend/llm，现有候选包括API system的`_redact_public_value`、Notes的`safe_text/sanitize_metadata`以及RAG的`_redact_diagnostic`。RAG helper已有凭证、token、secret、password、邮箱及本机路径规则，且适用于诊断而非笔记领域；本次复用它，不跨API依赖system、不把Notes存储引入聊天。

新增测试文件：`tests/test_runtime_stream_cleanup_errors.py`，10例。修复后执行新增测试及stream reliability、chat parity、Goal execution、Runtime P4和Runtime chat binding，**55 passed, 6 warnings, 2.48s**；日志为 `evidence/runtime-fixed-pytest.log`。隔离环境目录为 `/private/tmp/texa-runtime-fix-data` 与 `/private/tmp/texa-runtime-fix-pytest`。此前119个通过结果不重复累计为独立新增测试数。

```sh
DATA_DIR=/private/tmp/texa-runtime-fix-data PROGRESS_PATH=/private/tmp/texa-runtime-fix-data/progress venv310/bin/python -m pytest -q tests/test_runtime_stream_cleanup_errors.py tests/test_chat_stream_reliability.py tests/test_chat_execution_parity.py tests/test_goal_execution.py tests/test_agent_runtime_p4_contract.py tests/test_agent_runtime_chat_binding.py --basetemp=/private/tmp/texa-runtime-fix-pytest
```

保留修复前故障脚本/log作为证据；其“缺陷仍存在”assertion在修复后应失败，不作为当前验收命令。新聚焦测试才是修复验收入口。R2不承诺识别任意无标签未知密钥格式；真实provider/Electron仍未验收，其他模块的错误边界不在该修复范围。
