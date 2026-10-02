# Dataset V0 Tooling Verification — 两项 blocker 修复

日期：2026-10-01。仅修离线 manifest/version/digest 校验和 Policy 输入隔离；生产 Runtime、desktop wiring、数据库 schema 与固定数据集未修改。原冻结 source pins / baseline artifacts 保留，本目录保存修复后的验证材料。

## 修复结果

1. `validate_manifest()` 将三种 version、固定 source map、approved source pins、实际文件 SHA256、Runtime/Registry canonical digest 联合核验。缺失、空值、bogus、格式错误、全零、digest mismatch、批准依据/源文件不可用均 fail closed。raw dict 和绕过构造检查的 mutated model 都重验证；sample 的 frozen_errors 给出明确错误码，三个 eligibility/review 标志不授予。CLI 在创建输出目录前拒绝损坏 manifest。无 wildcard / unknown，未建立新 provenance 系统或改变生产 versioning。
2. `policy_input()` 是唯一实现的输入边界；direct serializer、invoke_policy、离线 Rule adapter、teacher invocation、disabled adapter 与 evaluator 均复用。只取独立 Observation，做深层副本、字段 ownership 校验和结构化 JSON 递归检查，不把 sample 元数据拼入输入。nested gold、ambiguity/candidate errors、action judgments、action references、object/list/字符串/fenced/多层 JSON 注入均拒绝；非法候选 ID 在 permutation 前拒绝。正常 prose 中的 gold/ambiguity 等词原样保留。未引入真实 teacher 或模型 transport。

## 本轮实跑

- `venv310/bin/python`，Python 3.10.21。
- Dataset tests **148 passed** = 原 66 + 新负向/正常文本回归 82。
- 原 266 tests + 新 82 合并 **348 passed**，仅既有 Starlette/Swig deprecation warnings；见 regression.log。
- 原 Runtime baseline harness 独立 **11/11 passed**，real_model_calls=0；见 runtime-baseline.json。
- 主 Dataset baseline 多候选 **4/6**、forced **6/6**。`policy_selection`、`forced_runtime_only`、`ordering_controls` 三份对象与首次保存报告精确相等；两个排列 controls 各 0/3 语义/acceptable 状态变化，独立于主分母。
- 默认 teacher disabled/not_run，E2E not_evaluated；真实模型调用 0。冷启动凭证读取/数据库/网络禁止测试继续通过。
- git diff --check 及新增文件空白检查通过。固定 fixtures 和生产源文件 digest 与原记录一致。
- Electron 未复跑：本轮未改生产/桌面文件，既有 7 项不作为新测试声明。

复跑命令与首次记录相同，tests 文件包含新增项：

```sh
venv310/bin/python -m pytest -q \
  tests/test_policy_dataset_v0.py tests/test_runtime_policy_v0.py \
  tests/test_agent_decision_p1.py tests/test_runtime_v0_contract.py \
  tests/test_agent_runtime*.py tests/test_checkpoint_remediation.py \
  tests/test_checkpoint_acceptance_edges.py tests/test_runtime_events.py \
  tests/test_runtime_cleanup.py tests/test_answer_verification.py \
  tests/test_learning_task_state_machine.py tests/test_chat_execution_parity.py \
  tests/test_chat_stream_reliability.py tests/test_goal_execution.py
```

本目录 baseline/ 存新 CLI report、quality、split、原始 predictions 与 transforms；输出目录不可静默覆盖，重跑用新目录。source-manifest.json 记录本轮源码/固定输入摘要；上一层 source-manifest.json 仍是原批准 source pins 的验证依据，不由调用者提供。

原有人工锁定限制不变：2 条语义未定，16 条 fixture_review 不能冒充人工 locked gold。此次不增加数据、不接 teacher/ModelPolicy/训练，完成两项 blocker 后停止。
