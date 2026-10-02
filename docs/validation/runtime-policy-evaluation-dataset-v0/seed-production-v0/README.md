# Seed V0 production workflow — Phase 0 初步校准

日期：2026-10-02。当前结论为 **SEED QUALITY HOLD / TRAINING PREP NO-GO**。这是初步代码/来源校准，不是完成人工裁决后的 seed release。

## 本轮产物

- [18 条 calibration queue](calibration/calibration-queue.jsonl)：逐条去向、逐候选建议及依据、初步责任角色、未分配的人工审核者、重投影差异。
- [校准摘要](calibration/calibration-summary.json)：8 single-correct、2 multiple-acceptable、2 candidate-generation-error、2 insufficient-information、1 invalid-sample、3 diagnostic-only。
- [16 个关联重投影版本](calibration/derived-samples.jsonl)：初始 gold 全部为 null，全部 pending；不增加独立 family 数。原 18 条与新版本共 34 samples / 15 families / 15 关联 groups，全部 development，locked=false。
- [全部冻结输入/投影](calibration/projections.json) 与 [可复用 recipes](calibration/calibration-recipes.jsonl)：明确 harness、constructed state、synthetic textbook scope。原始 JSONL 与旧 provisional adjudications 保留。
- [新版盲审包](blind-review-v1/blind-packets.jsonl)：完整逐候选 reason 占位、空白人工身份、无旧 gold/预测/split。`blind-review/` 为本轮较早的空白模板，已由 v1 补齐逐候选理由字段；两者均未填写人工审阅。
- [正式口径报告](report/report.json)：E=0，Rule N/A，Sol/Luna not_run，E2E not_evaluated。
- [默认关闭的 teacher batch](teachers-prepared-v1/batch-manifest.json)：0 scheduled，尚未独立审查候选的样本不发送；无实际模型配置、调用或凭证。`teachers-prepared/` 保留早期未运行的 adapter 摘要，实际准备须使用当前版本重新生成。

## 校准发现

11/18 原始 Observation 可由可见字段构造的 harness 假设精确重投影；这不是原生产轨迹的 provenance 证明。

| 原始版本 | 核查结果及关联版本处理 |
|---|---|
| `progress-done@v0` | `bounded_result_available` 只在没有其他摘要 flag 时生成，不能与 `coverage_incomplete` 共存。保留原样，重投影新版本。 |
| `resolved@v0` | resolved query 仅匹配进度，原习题候选来源无法直接复现。新版本使用实际 matcher 的候选集合。 |
| `pending@v0` / `insufficient@v0` | 请求缺少语义关键条件且当前 query 不匹配其工具；原 acceptable=null 保留，不虚构上下文或新任务版本。 |
| `input-gate@v0` | 真实 `input_gate_observation` 使用空 Registry/ToolContext；原 fixture 的教材/学科/answer_mode 不能证明真实门槛投影。新版本保留真实 pre-SQL 的空范围。 |
| `scope-defect@v0` | 新控制保留合法进度工具投影，然后显式注入 `other-book`。 |
| `missing-defect@v0` | 原“实时进度”请求不匹配当前 progress capability，不能据此证明漏候选。新控制明确改为“查询最近学习进度”，保存合法投影后 drop_tools；不是静默补来源。 |

其他语义建议仍待独立候选/参数相关性/人工审查；教材检索的 synthetic scope 不代替真实索引冻结。原分数 **Rule 4/6、forced 6/6** 保留在旧报告中，仅作为 provisional tooling baseline。

## 工作流实现

使用方法与输入格式见 [Seed V0 工作流](../../../policy-seed-v0-workflow.md)。新增 CLI 支持 calibrate、generate、blind-review、review-candidates、prepare-teachers、finalize、release、report。

生成器复用已 pin 的 matcher/resolver/projection/binder，使用 canonical schema snapshot 的无 IO Registry。教材门槛纯函数以固定 AST digest 隔离加载；冷启动不会导入模型/配置栈。默认不读真实用户任务或生产索引。

人工记录独立冻结 `sample_id + observation_hash + label_hash`、逐候选理由、候选有效性、盲态/轮次和实际 reviewer ID。正式确认要求两位真实人工盲审，分歧要求第三位人工；程序不能认证审核者身份。本轮没有填写或确认任何 human 记录。标签更新保留 Observation/source ref/main view，通过明确 base/final 绑定关联旧预测副本，不覆盖第一次 raw response。

Teacher batch 只提供默认关闭的准备入口和须单独授权的 one-shot transport API。本轮 fake 仅在测试中运行。真实 transport 必须禁用 SDK 重试、独立请求并执行 timeout。调用前校验输入/整个配置授权 hash，按调用数、预留输出 token 与 timeout 预算停止；保留原始 malformed/unknown/timeout/refusal/transport failure、完成/缺失清单及 incomplete。

Release 显式选择版本并重新核验来源、evidence、双审链、近重复和关联 split；selection 与 diagnostics 分轨，原 18 条及衍生 families 强制 development。没有正式人审数据，release 已在创建目录前被拒绝。没有进入 100-family 批量生产、训练准备或生产接入。

## 验证范围

- Python 3.10.21；新增 Seed 测试 45 项，原 Dataset/Runtime 及应用链路相关回归合计 **393 项通过**，详见 [regression-v1.log](regression-v1.log)。既有 Starlette/Swig deprecation warnings 保留。早期 392 项结果保留在 `regression.log`。
- 覆盖原始字节保留、16 个新版本、未定 null、source replay、schema binder 与真实 canonical model 一致、no retry、预算配对、fault 原投影、真实 gate 空范围、强制 development、盲审隔离/逐候选理由/双审/第三人、candidate-only review、release 和报告 round-trip。
- Teacher fake 验证共同输入字节一致、首次 malformed/unknown/timeout/refusal/transport failure、缺失 teacher 的固定分母、授权/配置/重试配置前置拒绝；验证 teacher-before-gold 后版本关联仍保留冻结 main view 和原始响应。
- 冷启动校准禁止网络/数据库/credential 读取，确认没有 `config` 或 `graph.generator` 导入。源 pins、原 fixtures 和旧 artifacts 摘要保持不变；见 [source-manifest.json](source-manifest.json)。
- Python compileall、新增文件空白检查及 `git diff --check` 通过。

本轮没有生产/桌面端改动，所以未启动 Electron；没有真实 teacher、真实用户数据、生产教材索引、正式人工双审、在线答案质量或实际 E2E 验收。当前 Phase 0 的正式完成条件仍未满足。
