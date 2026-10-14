# Seed V0 离线生产与裁决工作流

本工具补充冻结的 [Policy V0](contracts/runtime-policy-v0.md) 与 [Dataset V0](contracts/runtime-policy-evaluation-dataset-v0.md)，不改变两份 contract。生产 Runtime、Electron 接线、数据库、原始 fixtures 和已保存 baseline 保持原样。

当前交付是 Phase 0 初步校准与后续工作流工具。没有真实人工裁决、正式锁定、付费 teacher 调用、训练或生产接入。人工审核完成前，结论为 **SEED QUALITY HOLD / TRAINING PREP NO-GO**；不能用原 provisional 4/6、forced 6/6 代替正式 baseline。

## 入口

使用 Python 3.10 的 `venv310/bin/python -m evaluation.policy_dataset_v0.seed`。Windows 对应 `venv310\Scripts\python.exe`。所有命令要求新的 `--output` 目录，拒绝覆盖。原四个 Dataset CLI 入口仍保留为 tooling baseline；正式 Seed 报告使用新 `seed report` 入口。

```sh
# 18 条原始 fixture 的审阅清单、16 个关联重投影版本、development split。
venv310/bin/python -m evaluation.policy_dataset_v0.seed calibrate --output /tmp/seed-calibration-001

# 根据明确的冻结任务生成 1–50 个 decision points；不是自动造 gold。
venv310/bin/python -m evaluation.policy_dataset_v0.seed generate \
  --recipes recipes.jsonl --output /tmp/seed-batch-001

# 分别交给两位真实人工审核者；空白模板不是已完成审阅。
venv310/bin/python -m evaluation.policy_dataset_v0.seed blind-review \
  --dataset /tmp/seed-batch-001 --output /tmp/seed-blind-001

# 导入候选审查，不授予语义 gold；版本和字段仍遵守 Dataset V0。
venv310/bin/python -m evaluation.policy_dataset_v0.seed review-candidates \
  --dataset /tmp/seed-batch-001 --reviews candidate-reviews.jsonl \
  --finalizations candidate-versions.json --output /tmp/seed-candidates-001

# 只准备共同输入，默认不启用模型；候选尚未独立审查的样本会跳过。
venv310/bin/python -m evaluation.policy_dataset_v0.seed prepare-teachers \
  --dataset /tmp/seed-candidates-001 --teacher-config teacher-config.json \
  --output /tmp/seed-teachers-prepared-001

# 两位人工先盲审全部候选；分歧需要第三位人工裁决者。
venv310/bin/python -m evaluation.policy_dataset_v0.seed finalize \
  --dataset /tmp/seed-candidates-001 --reviews human-reviews.jsonl \
  --finalizations final-versions.json --output /tmp/seed-adjudicated-001

# 显式选入已完成门槛的版本，其他原始/未定版本留在历史数据集中。
venv310/bin/python -m evaluation.policy_dataset_v0.seed release \
  --dataset /tmp/seed-adjudicated-001 --include independent-task@gold-v1 \
  --output /tmp/seed-release-001

venv310/bin/python -m evaluation.policy_dataset_v0.seed report \
  --dataset /tmp/seed-release-001 --output /tmp/seed-report-001
```

## 冻结输入与可达性

`recipes.jsonl` 的一行示例：

```json
{"sample_id":"task-A@v0","source_family_id":"task-A","source_ref":"synthetic/task-A@v0","related_refs":["template/task-A"],"request":"查询最近学习进度","resolved_query":"查询最近学习进度","book_name":"synthetic-book","subject":"数学","scenario_tags":["non_textbook_required","tool_vs_answer"]}
```

其他可选输入包括：`answer_mode`、`goal + goal_origin_ref`、`prior_calls`、工具/模型预算、`missing_inputs`、`position`、`used_for_tuning` 和 `fault`。`prior_calls` 只保存投影消费的有界结构事实：tool/status、计数、覆盖不足、证据不足与错误代码，不复制完整工具结果。相关任务、模板、教材实例和变体通过 `related_refs` 显式关联。同一 family 或关联组不跨 split。

当前生成器仅产生 `deterministic_fixture` 和 `fault_injection`。真实用户任务、生产教材索引和 `runtime_capture` 尚未导入；需要后续经授权的真实来源和审查依据。Recipe 中的调用状态是明确设计的 harness 前提，不证明一次真实调用发生过，也不认证完整工具结果符合实际输出 schema。

生成调用现有 `matched_tool_refs()` → resolver → `project_observation()`，复用 binder、预算、范围、不可重试和回答门槛。Registry 的模型适配器来自已批准 canonical schema snapshot，填充并检查原默认参数；工具 handler 禁止执行。没有手工传任意候选集合的入口。

教材样本使用显式 synthetic scope，没有 active index 版本核验，因此只证明 harness binder 行为。为避免导入 `graph.generator` 时加载 `.env` / 模型配置，教材分支执行固定源码中的投影函数，并仅把其 `has_textbook_evidence` 导入替换为该纯函数的固定源码。Runtime 文件摘要和纯函数 AST 摘要同时核验，任何变化 fail closed；没有重写 binder/gate 或改变生产代码。冷启动回归禁止数据库、网络、credential 读取，并检查未导入 `config` / `graph.generator`。

每个新样本初始 `acceptable_action_ids=null`，逐候选 `undetermined`，不生成 human/approved-rule 责任链。自然投影写 `natural-samples.jsonl`；`wrong_book` / `drop_tools` 控制写 `fault-controls.jsonl`，并保存原合法 Observation 与注入操作。Recipe 的关系/目标 refs 只记录 synthetic 设计关系，不是生产来源证明。

## 人工记录与版本

`blind-packets.jsonl` 包含 Observation、来源 ref、绑定 hash 和空白 `review_template`，不提供旧 gold、预测、scenario/hard tags 或 split。人必须阅读冻结 evidence，不得把模型输出填成 `reviewer_kind=human`。本地文件只能校验一致性，无法认证审核者本人或保证其实际保持盲态。

`candidate-versions.json`：

```json
[{"base_sample_id":"task-A@v0","new_sample_id":"task-A@candidate-v1","reviewer_id":"实际人工审核者ID"}]
```

`final-versions.json`：

```json
[{"base_sample_id":"task-A@candidate-v1","new_sample_id":"task-A@gold-v1","final":{}}]
```

`final` 必须填完整 `HumanReviewV0`，来自实际人工记录，绑定同一 `sample_id + observation_hash + label_hash`。候选有效性、ambiguity、完整 acceptable 集合、逐候选接受性/理由、输入需求、冻结 basis refs、耗时和盲审轮次均需填写。两位初审者结论不同，`final` 必须来自第三位人工的 `adjudication` 轮次；仍未定的样本不能确认。重复裁决使用 `round=repeat`，保留首次记录。

label-only 更新产生新 sample ID，但保持同一冻结来源 ref、Observation 和 main view；历史 sample、审阅材料与第一次预测不覆盖。后置报告通过明确 base/final 绑定重新关联预测副本，校验旧 label hash、候选排列、Observation hash 和 family split。第一次 raw response 与 log 保持原样。

所有进入 release 的样本重新验证 provenance、冻结 evidence、候选审查、正式裁决和 split leakage。Selection 与 diagnostics 分轨；信息不足、损坏和未裁决版本不能进入。18 个原 fixtures 及其关联 family 强制 development，不能通过换 ID 或编辑 assignment 成为独立 test。近重复待审项必须在冻结 split 中明确解决。尚无 approved deterministic semantic rule，本次自动锁定数量为零。

## Teacher transport 与运行

`prepare-teachers` 不读取凭证、不发送请求。Sol/Luna 是角色，配置必须提供实际 `model_id`，拒绝角色别名或 `latest`；同时记录 provider、可得的 snapshot、temperature/top-p、token limit、reasoning、seed、timeout、response format、SDK version 和 `max_retries=0`。两者使用相同冻结 prompt 与 canonical Observation 字节，不接收审阅材料或 gold。零候选和 forced 不调用。

真实运行采用 `teacher_batch.run_batch(plan, inputs, transports, authorization, output, run_id=...)`。需要单独授权的 `BatchAuthorizationV0`：authorization ref、输入范围 hash、完整 plan hash、付费与数据出境确认、最大调用数、总输出 token 预算与时长。CLI 不提供隐式真实 transport。调用者须提供经过检查的 `OneShotTransportV0`：禁用 SDK/HTTP 隐式重试、执行冻结 timeout、每次独立请求，不传入跨样本历史，返回 `TeacherResponseV0`。本轮只用 test-only fake 验证协议，没有真实供应商 transport 验收。

首个 raw response 立即落盘。malformed、unknown ID、timeout、refusal 和 transport failure 分开记账；refusal 复用 `selector_exception`，具体原因留在外部 log，不扩 Decision/Prediction 合同。无重试、格式修复或 fallback。每次调用前预留输出 token 和 timeout 预算；不足时保留 `incomplete`、停止位置和缺失清单。需要排障重跑时创建独立新 run。不可得的 immutable snapshot 会记录复现限制。

## 正式比较口径

`seed report` 使用正式裁决、可复现、候选有效且至少两项的唯一 main 集合 E。三种 selector 使用同一分母；启动后的失败或缺失计为未命中，incomplete 明确展示。Teacher 未启用时 N/A。forced、runtime-only、fault controls 与 original/order controls 不加到 teacher 主分母。

报告包括 samples/families/关联 groups、source/split/tag 分层、候选审查及错误率、多解、未解决根因、三方命中、共同合法输出上的分歧、harmful disagreement、成对胜负和过早回答/无益调用。重复裁决和双审一致性从 hash-bound 人工记录计算，不用可编辑摘要来通过训练准备门槛。置信区间重采样关联 group；E2E 无独立执行验收时保持 `not_evaluated`。

训练准备 GO 的保守工作目标另列于代码：正式 release、至少 60 个多候选点/40 families、≥90% 双审 acceptable 集合一致、至少 10 families 复审且变更≤5%、validation/test 各至少 10 个独立多候选组，以及至少一个 teacher 在两组上有正向 group-bootstrap 区间且未增加 premature answer。它们不是 contract 新约束，GO 也不授权训练。首批校准不满足这些条件。
