# Evaluation Dataset V0 — 2026-10-01 实现验证

本轮 verification 的两个 blocker 已修复，最新复跑 **348 passed** 与独立 **11/11**，指标不变；详见 [blocker-fixes/README.md](blocker-fixes/README.md)。下文 266 项及 baseline/ 保留为首次交付记录，未静默替换原冻结 artifact。

本轮仅新增离线模块、固定 fixtures、tests 与文档，更新 patch_notes。开始时已有 Runtime Policy V0 的未提交改动；本轮未编辑这些生产/desktop/frontend 文件，未改变排序、action space、Runtime ID/authority、开关、数据库或依赖。真实模型调用为 0；未访问/迁移真实用户数据库。

契约和使用说明：[Dataset V0 contract](../../contracts/runtime-policy-evaluation-dataset-v0.md)。本目录 `baseline/` 保存 original round-trip samples、quality、split、原始 predictions、可逆 transforms 和聚合 report。`runtime-baseline.json` 是独立复跑的原 Runtime harness 材料，未作为 Dataset gold 来源。

## 本轮实跑

- `venv310/bin/python`：Python 3.10.21。
- 新 Dataset deterministic tests **66 passed**。
- 新 tests 加原 Policy/Runtime/backend/checkpoint 组合回归 **266 passed**，其中既有相关回归 **200**；见 `regression.log`。保存日志只将工作区绝对路径替换为 `<workspace>`，不修改结果。
- 原 Runtime baseline harness **11/11** 场景通过，real_model_calls=0；见 `runtime-baseline.json` / `.log`。
- CLI validate/split/evaluate/report 各自两次临时输出逐字节一致，输入文件不变。默认入口冷进程带模型环境凭证，禁止 credential reads、网络和 sqlite3.connect，仍能完成报告；不导入 config、LLM 或 learning_tools。
- snapshot input/output schemas 与三个现有 canonical model 精确一致；沿用 Registry schema digest。
- `git diff --check` 通过。

组合回归命令：

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

仍有既有 Starlette/Swig deprecation warnings。Electron 的既有 7 项通过及隔离 smoke 属于上一阶段记录（`../runtime-policy-v0/README.md`）；**本轮未复跑 Electron**，生产和桌面文件未变。

## 固定 fixtures baseline

```sh
venv310/bin/python -m evaluation.policy_dataset_v0 report \
  --output docs/validation/runtime-policy-evaluation-dataset-v0/baseline \
  --control-family multi --control-family lexical --control-family optional
```

已保存的输出目录不可直接重复覆盖；重跑请换新临时目录。18 个固定样本，15 个 family；实际 sample split 为 development 5 / validation 7 / locked_test 6，**split manifest 未锁定**。全部都是实现阶段 fixtures，无真实用户样本；natural 栏表示非故障注入示例，不能解释为生产流量错误率。

| 层 | 本轮结果 |
|---|---|
| 候选审查，非注入 fixtures | 16 个有冻结依据的候选审阅，错误 0/16；语义仍有 2 条未裁决 |
| 候选故障注入 | 2/2 已确认缺陷：错误范围绑定、遗漏必要候选；退出选择分母 |
| 主 acceptable accuracy | 4/6，原顺序同为 4/6 |
| Single-correct | 2/4；多解样本 2 条不强制 preferred |
| 过度调用 / 过早回答 | 2/6 / 0/6 |
| 原始 invalid decision | 0/6；malformed、unknown、timeout、exception 由专门 tests 与 fake 覆盖 |
| Forced | 6/6，Policy 调用为 0 |
| 合法 Runtime-only | 2；全部零候选 route 共 3，另一条是故障注入，不能混同 |
| Runtime input gate | precision 1/1、recall 1/1；主 Policy missing-input precision/recall 均 N/A |
| 排列 controls | 3 个 family × 两类 controls；各自语义选择变化 0/3、acceptable 状态变化 0/3；不计入主分母 |
| Teacher | disabled/not_run，所有 accuracy/disagreement 为 N/A；fake 仅测试用途 |
| E2E | not_evaluated；stub 原拒绝/单次 fallback/独立任务验收关系只在 tests 中核验 |

原始顺序主样本的选择位置为 0→5、1→1；主 hash-order view 为 0→3、1→2、2→1。acceptable 位置分布同时保存在 report。排序键不读取 gold、预测或难度；有限 fixture 分布不能证明统计独立。Rule 的两个已知未命中是明确否定词法查询与 goal 限制，未为提高分数改写 Rule 偏好。

## 尚不可锁定或评测

- `pending@v0` 未裁决；`insufficient@v0` 的 Observation 不足，acceptable IDs 为 null。
- 其余 16 条有按 Spec 独立编写的 `fixture_review`，没有伪称实际人工裁决。全部需要实际人工或获批准且完整决定标签的 deterministic rule 才能进入 locked 集合；`--lock` 会拒绝。Diagnostic controls 也需要相应的独立候选审阅 authority。
- 当前 split 清单是固定 fixtures 的草稿分配，不宣称已有独立 locked-test 成绩。没有 teacher、真实答案质量或真实 E2E 分数。
- `invalid-sample.json` 是独立拒绝测试材料（损坏 Observation/重复 ID），不作为可序列化样本混入主 JSONL。
- Canonical schema 快照只覆盖生产 V0 的三个已有只读工具及固定 binder。新增/变化 schema 需另行版本化审阅，无法证明的范围/版本不通过 gate。静态 validator 不证明全部候选准入或语义正确性。

达到本阶段停止点：可以创建、校验、按 family 切分和离线评测可信样本，生成 Rule baseline 和显式限制报告；teacher 接口存在且默认禁用。未开始批量数据生产、真实 teacher、ModelPolicy、训练或线上 Policy 扩展。
