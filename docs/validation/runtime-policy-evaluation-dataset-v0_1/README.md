# Runtime 源码基准 V0.1 — 2026-10-08 审阅与切换

**审阅结论：通过，作为当前默认源码基准。K02 已关闭。** 用户明确要求“审阅新版基准，以新版为主”；本次完成源码/合同审阅、版本化冻结和回归，没有覆盖 V0 的 pins、manifest、gold 或首次失败记录。本审阅由 Codex 完成，不冒充独立人工 gold 裁决。

## 审阅范围与结论

| 变化 | 审阅结果与限制 |
|---|---|
| `DecisionContext.question_understanding` | 可选字段，默认空 dict；无提示调用保持兼容。未改变 READ 默认权限和已有输入/会话门槛。 |
| `matching_capabilities(..., understanding=...)` | 仅消费版本合法、accepted、continue 的白名单意图/维度；可增加 `exercise.inspect`，不由模型自由提供工具名或写权限。明确 UI 动作仍由原入口处理，错题、练习写规则和学习进度规则保留优先级；有效习题提示可以排在教材/数学查询前，此优先级变化是新版明确行为。 |
| `project_observation()` | constraints 只投影 version/accepted/action/intent/dimensions，不携带实体原文、额外模型字段或凭证；冻结 payload/bindings 的身份、预算、范围及不可重试检查继续有效。 |
| `RulePolicyV0()` | 使用同一提示排列 Runtime 已准入的候选；不会创建新候选或执行权限，request_input 仍优先。 |
| 工具绑定/执行 | 原 Registry canonical metadata、只读检查、作用域绑定、缺输入、inactive run、工具预算、重复调用门槛不变。无工具调用或真实模型付费由本次审阅触发。 |

复跑旧版与当前源码的 27 个初始投影比较：18 个 off/shadow 的 payload、bindings 相同；9 个接受提示的 fallback payload 发生预期变化。控制集包含非法/未接受提示不改候选、输入缺口、inactive run、预算耗尽与失败工具不重试，以及额外实体/敏感标记不进入投影。此范围不证明 LLM 理解准确率、最终答案正确率或完整学习业务签收。

## 新版身份与默认入口

- 源码基准：`runtime-source/v0.1`。
- Runtime digest：`sha256:d6b75d38d73aa04d157bde32b7a7602e20073c35c8438fb90c1d3d984b8d834a`。
- Registry digest 维持原版本：`sha256:468a8259856e03d4f63f8e478eebf058467dd05395fae044de2d20aa95ec7013`。
- 默认数据目录：`evaluation/fixtures/policy_dataset_v0_1`。
- 默认基准定义：`evaluation/policy_dataset_v0/baseline.py`；固定读取本目录 `source-manifest.json`，调用者 manifest 不能选择审批文件。
- 原八个 Runtime/Registry pins 增至十一项，新增 `decision/contracts.py`、`decision/resolver.py`、`graph/question_understanding.py`；另核对 canonical-tools-v0.json。修改任何一项仍拒绝，重算输入 manifest 的 digest 不构成批准。
- JSON dataset、PolicyObservation、action_id 选择协议及 label policy 仍采用 V0 格式，故 Python 模块名和样本 ID 的 `v0` 后缀继续保留；V0.1 是经过审阅的源码基准版本，不是全库数据迁移。

CLI report/validate/split/evaluate、seed calibrate/generate 及 seed projection 的默认基准全部切到 V0.1。显式输入旧 V0 manifest 在当前代码下会因 Runtime 版本不符而拒绝，避免把旧记录当成本轮源码评测。问题理解模型默认 off 不变；更换评测基准不等于批准生产启用语义模型。

```sh
venv310/bin/python -m evaluation.policy_dataset_v0 report --output /path/to/new/report
venv310/bin/python -m evaluation.policy_dataset_v0.seed calibrate --output /path/to/new/calibration
```

## 保留旧样本与历史身份

新目录仅更新 manifest 的 runtime_version/source_digests；`samples.jsonl`、`adjudications.jsonl`、`evidence-files.json`、`invalid-sample.json`、`review-basis.md` 与旧目录逐字节相同。它们没有新版理解提示，协议与无提示规则保持兼容，原标签可继续作为实现回归 fixtures。原样本来源/校准限制仍适用，未据此宣称它们是真实 Runtime 轨迹或新增金标。

`baseline-transition.json` 记录旧 manifest/pins 与复用文件 hash；`source/` 冻结新版源文件，`previous-v0-source/` 留存校验过旧 pins 的源码及旧评测入口。原 V0 数据、文档与 `evaluation/frozen/runtime-benchmark-v0` 均未改写；不重新签发其 300-case benchmark gold。

源码基准通过没有提升 provisional fixtures 为 human-reviewed locked gold；默认报告 `locked=false`。真实生产数据/teacher/锁定集仍需各自原有门槛。

## 实测

| 检查 | 结果 |
|---|---|
| Policy dataset/seed/runtime 与问题理解相关回归 | 271 passed，4.27s |
| 新版源码 pins、旧版保留、提示/Runtime fence 控制 | 15 passed |
| Python 3.10.21 隔离离线全量 | **1470 passed，0 failed**，6 个既有 deprecation warnings，14.41s |
| 默认 CLI report，不指定 dataset | 18 samples，locked=false，real_model_calls=0 |
| 旧/新投影比较 | 27 cases，off/shadow 相同；9 个 fallback payload 变化 |

日志在 `validation/`，CLI 实际输出在 `validation/default-report/`。source/hash 损坏、缺批准文件、冷启动不得读凭证/连数据库/联网、首失败保留与锁定 gate 等原回归没有放松。

本次只关闭 K02。教材原页/人工、多书/Windows、L2/L3、升级恢复及完整学习纵向链仍待验收，**整体发布仍为 NO-GO**。之前生成的桌面候选不因本次评测通过自动变成正式发布版本。
