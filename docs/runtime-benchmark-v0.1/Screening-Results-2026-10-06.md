# Runtime Benchmark V0.1 首次本地 Screening

2026-10-06。Harness 已实现；P0/P1/P2/P3 已完成并到此停止。复用本机 LM Studio snapshot，没有下载模型、安装依赖、调用外部模型或改动 Texa Runtime。

权威合并报告：[report.md](../validation/runtime-benchmark-v0.1/p3-semantic-all-verified/report.md)。明细：[diagnostics.json](../validation/runtime-benchmark-v0.1/p3-semantic-all-verified/diagnostics.json)、[failures.jsonl](../validation/runtime-benchmark-v0.1/p3-semantic-all-verified/failures.jsonl)。[使用说明](Harness-Usage.md)、[锁定配置](local-qwen35-8bit.config.json)。

## 实验资格

- 原冻结 V0 包：271 pinned 文件、300 input/gold 合同与 gold round-trip、10 scorer mutation；四个完整 split 和 all 的 frozen CLI/API 一致性通过。这是 self-test，不是模型准确率或独立 gold 裁决。
- 正式推理：primary 161 + secondary 39，共 200 唯一病例，每题一次 generation；100 controls 未参与模型 baseline。两轮均 complete，0 operational failure、0 missing，配置/实际模型/库版本相同。
- P1 和每轮 warmup 仅使用独立合成 Policy 输入，不计质量/稳态延迟。P1 输出合法但动作错误，原文保存；没有据此调正式 prompt。正式 prompt 为 frozen wire + task prompt + 完整 output schema + canonical input，模型文本不含 ID/gold/metadata。
- raw 先写盘，再调用未修改的 frozen scorer。恢复诊断独立，不清理首答、不修 schema；合并核验原 raw/token/time 记录与两个源 run 完全一致。
- 推理配置在正式失败分析前锁定；未看中途正式错例，不调整 prompt/预算，不重跑 primary。此次是未经 Texa 训练的 untouched author-frozen internal screening，不是 held-out 或盲测。现在 V0 failure 已曝光，后续调参必须新 run 并更新 exposure/tuned 标记。

## 结果

| 集合/任务 | S / N | strict / exact / recoverable | F | T | U |
|---|---:|---:|---:|---:|---:|
| primary Policy | 40/80 | 50.00% | 0 | 40 | 0 |
| primary Goal | 0/40 | 0% | 0 | 0 | 40 |
| primary Understanding | 0/41 | 0% | 0 | 0 | 41 |
| primary 总计 | 40/161 | 24.84% | 0 | 40 | 81 |
| secondary 总计 | 0/39 | 0% | 0 | 0 | 39 |
| semantic_all | 40/200 | 20.00% | 0 | 40 | 120 |

Primary task macro strict = 16.67%。官方 severity：S0=40，S2=160，S1/S3=0；critical=0。官方旧字段 `primary_semantic_without_upstream_conflicts.n=198` 保持原样，V0.1 主分组仍单列 161，不混用。

全集 12 条 invalid JSON、103 条 schema 不符合、5 条 schema 合法但 contract 拒绝；189 条 finish=stop，11 条 finish=length。Goal 样例出现照抄 output schema；Understanding 存在错误字段结构、无效 span 或截断；Reference 有 clarify 携带 value 等不符合 contract 的输出。保守 parser 没有可恢复成功的 format-only 样例；这些 schema/contract/truncation 失败属于 U，不是已证实语义错误。Policy 的 40 个合法但错误候选是 T。

critical=0 与大量输出被拒绝有关，不代表可以生产接管。Goal/Understanding 的 strict=0 也不能直接表述为模型语义能力为零。

## 模型与部署测量

复用 `~/.lmstudio/models/lmstudio-community/Qwen3.5-0.8B-MLX-8bit`。实际 config 为 qwen3_5 / Qwen3_5ForConditionalGeneration，text hidden_size=1024、layers=24、vocab=248320；8bit/group_size=64/affine，187 个加载模块的 bits/group size 验证通过。参数实际类型为 uint32 packed weights、bfloat16 和 float32；本地 snapshot 没有可验证 revision，记录为 null。MLX-LM 为文本加载，sanitizer 排除视觉权重。

评分使用 venv310 / Python 3.10.21；用户批准复用 LM Studio Python 3.11.9，仅推理运行在既有环境：MLX 0.32.0、MLX-LM 0.31.3、Transformers 5.14.1。沙箱外访问 Metal 后加载成功，未更换项目解释器。

设备记录：Mac17,5 / Apple A18 Pro / 8,589,934,592 bytes（8GiB）。greedy、seed=0、thinking=false、batch=1；128/384/384/256 task budgets。

- P2/P3 load：1.319s / 1.527s，含模型 materialization，不含下载。
- 成功请求 n=200，nearest-rank p50=0.972s、p95=7.871s；排除 warmup，包含模板/tokenization/prefill/生成/设备同步。
- generated_tokens_per_request_second=37.30；同一可靠 token/time 样本集合，含 EOS on stop，不是 decode-only throughput。
- P2/P3 peak process RSS：831,815,680 / 850,771,968 bytes；MLX allocator peak：1,160,565,198 / 1,163,384,782 bytes。各自含 load/warmup，分列且不可相加。

没有保证机器只运行该模型，`running_alone=false`；这些数字不是与 Electron、Chroma 和 embedding 共存的部署验收。

## 判断与停止边界

`insufficient_evidence`。Primary 中 81/161 属 U，主要测到输出合同遵循问题；Policy 合法输出的成功率仅 50%，同时已有明确决策错误。当前结果不支持“约 80% 的 prior 已成立”，也不足以判断修正输出习惯后的语义上限。首次低分是有效 baseline，已完整保留；不通过修改 prompt、增加预算或修复 JSON 后重算官方成绩。

数据仍是 author-frozen synthetic/closed-profile，human_adjudicated=false、semantic_test_locked=false，且 primary 教材工具与历史 reference 覆盖缺口仍在。若之后研究输出训练或 prompt 变体，V0 只能作为已曝光的开发/回归集，不能冒称新的 untouched 或 LoRA held-out 结果。本次不启动训练、不生成训练对、不接入生产。

验证：[31 项 harness tests](../validation/runtime-benchmark-v0.1/harness-tests.log)、[P0 sanity](../validation/runtime-benchmark-v0.1/p0-sanity.json)、[P1 原记录](../validation/runtime-benchmark-v0.1/p1-smoke/run.json)、[P2 原记录](../validation/runtime-benchmark-v0.1/p2-primary/run.json)、[P3 原记录](../validation/runtime-benchmark-v0.1/p3-secondary/run.json)。`p3-semantic-all` 是第一次离线合并产物；后续修正 replay 汇总请求计数后，在新目录 `p3-semantic-all-verified` 再离线验证，没有新增推理或覆盖首答。
