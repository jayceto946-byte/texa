# 审计验证记录

报告：`../../pre-policy-architecture-audit-2026-09-30.md`。

所有后端回归均使用项目 `venv310`（Python 3.10.21），设置 `ENV_PATH=/dev/null`、`DATA_DIR=/tmp/texa-prepolicy-audit/data`、`PROGRESS_PATH=/tmp/texa-prepolicy-audit/data/progress`。未运行付费模型或访问真实学习数据。复现脚本自行建立新的临时目录。

## 结果

| 检查 | 结果 | 记录 |
|---|---|---|
| Runtime/Decision/Goal/事件/审批/验证/provenance 核心回归 | 176 passed | backend-core.log |
| Chat 恢复、会话并发、Memory、迁移、RAG 降级、资源/关闭边界 | 114 passed | backend-boundaries.log |
| 前端 Vitest | 26 文件 / 124 passed | frontend.log |
| Electron appearance/runtime 单元测试 | 7 passed | 本次工具执行记录；首次沙箱内端口 bind EPERM，批准后重跑成功 |
| 定向故障复现 | 15/15 reproduced=true | repro-results.json |
| 源文件 SHA-256 | 447 文件 | source-manifest.json |

`reproduced=true` 的含义是当前缺陷/合同缺口仍能复现；不能当作修复测试通过。`repro.py` 最后的断言仅确保报告证据与该版本一致；未来修复后应把相关案例改写为断言正确行为的回归测试。

## 可重复命令

在项目根目录：

```sh
venv310/bin/python docs/validation/pre-policy-2026-09-30/repro.py
```

核心测试选择：

```text
tests/test_agent_runtime*.py
tests/test_agent_decision_p1.py
tests/test_agent_direct_path.py
tests/test_agent_goals*.py
tests/test_goal_execution.py
tests/test_runtime_events.py
tests/test_runtime_v0_contract.py
tests/test_execution*.py
tests/test_learning_task_state_machine.py
tests/test_pending_actions.py
tests/test_provenance_contract.py
tests/test_chat_execution_parity.py
tests/test_answer_verification.py
```

边界测试选择：

```text
tests/test_chat_stream_reliability.py
tests/test_crosslayer_recovery.py
tests/test_context_safety_failures.py
tests/test_conversation_event_store.py
tests/test_conversation_memory_concurrency.py
tests/test_learning_state_v1.py
tests/test_learning_state_concurrency.py
tests/test_sqlite_migrations.py
tests/test_rag_degradation.py
tests/test_evidence_support_gate.py
tests/test_resource_limits.py
tests/test_graceful_shutdown.py
```

前端使用已有 node_modules 中的 Vitest，桌面端使用 `node --test desktop/*.test.cjs`。当前 shell 无 npm，使用 Codex 已提供的 Node 可执行文件；没有安装运行时或依赖。此次只有审计文档和验证材料变化，未额外执行 lint/build 或视觉验收。

源指纹用于识别工作区版本，不表示 447 个文件全部逐行审阅，也不包含用户数据、凭证或向量库。报告中的代码位置与当前工作区匹配；后续修改后需重新核对。
