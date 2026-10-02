# Runtime Policy V0 验证记录 — 2026-10-01

本次范围仅为 V0 合同与 deterministic baseline。未启用生产开关，未修改用户数据、依赖、数据库 schema、索引、审批/receipt/恢复所有权；真实模型调用为零。有限人工 fixture 的规则/任务成绩不代表线上模型准确率。

## 离线 baseline

运行：

```sh
venv310/bin/python -m evaluation.runtime_policy_v0 --output docs/validation/runtime-policy-v0/baseline.json
```

`baseline.json` 保存完整测试 observation、规范化 decision、原始 decision 输出、关联 trace、outcome、排除原因以及按维度分开的计数。共有 11 个场景：普通答案、进度、习题、多匹配工具、教材检索、空习题结果、失败工具、非法 decision/一次 fallback、空教材证据、输入门槛、stale/stop/resume。每个场景有明确的动作序列/任务状态验收标准；空教材证据的正确结果是原失败路径，不算答题成功。

| 维度 | 本轮结果 |
|---|---|
| Candidate generation | 21 个完整投影/21 个允许动作金标覆盖（含金标无动作），禁止动作泄漏 0；11 个参数绑定检查，错误 0 |
| Selection | 可接受动作在候选中的多候选样本 8/8；forced 12/12 单列；candidate-generation failure 0 |
| Decision validity | 原始格式拒绝 1；未知 ID 0（另有针对性测试）；stale/停止环境变化 1 独立列示，不算选择错误 |
| Fallback | 原始拒绝 1、实际 fallback 尝试 1、接受 1、执行成功 1；拒绝保留为独立 not_started outcome |
| Task execution | 11/11 达到 fixture 标准，包括 waiting、受控失败和恢复标准 |
| 调用开销 | 9 次 primary Policy 调用 + 1 次 fallback；10 次工具，9 次答案 stub；真实模型 0 |
| 规则耗时 | 见 JSON 的实际 rules source 耗时汇总，仅反映本机有限样本，不能作为性能基准 |

stale 原始候选因 fence 不写入旧 run，其完整轨迹不纳入选择分母；恢复后的完整轨迹正常统计。未知用户反馈/Goal 验收始终为 unknown，工具成功不等于结果覆盖完整，degraded 不等于验证通过。

## 回归

使用 `venv310/bin/python`，Python 3.10.21。指定的八组 regression 和受影响 Runtime、verification、任务、主聊天、Goal 与 checkpoint 测试合并运行通过。最终合并 **200 passed**（其中新增 Policy 文件 37 项，聊天 baseline 开/关额外 1 项）；既有 Starlette/Swig deprecation warnings 不影响通过。

```sh
venv310/bin/python -m pytest -q \
  tests/test_runtime_policy_v0.py tests/test_agent_decision_p1.py \
  tests/test_runtime_v0_contract.py tests/test_agent_runtime*.py \
  tests/test_checkpoint_remediation.py tests/test_checkpoint_acceptance_edges.py \
  tests/test_runtime_events.py tests/test_runtime_cleanup.py tests/test_answer_verification.py \
  tests/test_learning_task_state_machine.py tests/test_chat_execution_parity.py \
  tests/test_chat_stream_reliability.py tests/test_goal_execution.py
```

原聊天 SSE 用同一个测试参数化验证 baseline 开/关的发布、验证、outbox 与传输语义；关闭时沿原模型工具适配器，开启时不构造该适配器，模型预算只消耗答案 stub 的 1 次。

## Electron 后端启动与恢复

Electron 单元测试 7/7（初次回环端口测试被沙箱禁止，经自动审批后沙箱外重跑通过）。原生 smoke 脚本 `desktop_smoke.py` 使用临时 userData、空 `.env`、Python 3.10、明确的本地测试 token 和两个临时回环端口，启动真实 Electron development 入口及其 uvicorn 后端两次。没有使用正式学习记录或模型凭证。

`desktop-smoke.json`: 两次 health=ok、instance 匹配；SQL 未完成任务在首启恢复为 interrupted，原 API 返回 resumable=true；Policy checkpoint 保留，模型/工具消耗 0。第二次重开执行事件仍为 2，没有追加重复恢复事件。实际恢复后执行用上面的临时 Runtime/stub 测试验证；native smoke 没有触发真实答案生成。未进行生产打包/安装升级验证，也未重新审计 checkpoint。

## 停止范围

保留主聊天入口/范围与原开关。request_input 只接原 pre-SQL 澄清门槛；视觉、章节讲解、write/approval、Goal/schedule worker、插件/MCP，以及正式模型答案评测均未接入 Policy。本轮交付后停止，不接 ModelPolicy，不训练，不扩大数据集。
