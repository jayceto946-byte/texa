# Minimal Harness Implementation Plan V0.1

2026-10-06。设计交付，未实现 inference Harness、未下载/加载 Qwen。替代 [Sol Plan V0](/Users/jichengqian/Documents/Codex/2026-10-06/1-users-jichengqian-documents-codex-2026-2/outputs/Sol-Runtime-Benchmark-Harness-Implementation-Plan-V0.md) 的实施阶段、基础设施与性能要求；测量政策以 [Spec V0.1](Runtime-Benchmark-Spec-V0.1.md) 为准。

目标：在 MacBook Neo 8GB 上，以 Qwen3.5-0.8B 8bit 首答筛选是否值得专项训练。只做小型本地顺序实验，不修改 Texa Runtime、不执行工具、不测试最终回答。

## 1. 保留的核心链路

```text
Benchmark cases → PromptBuilder → ModelAdapter → 原始 raw 落盘
                                                  ↓
                                             Frozen Scorer
                                                  ↓
                               独立 recoverability / diagnostics
                                                  ↓
                                       Report + Failure Corpus
```

建议仅有 `prompting.py`、`adapter.py`（Protocol 与 MLX 实现）、`runner.py`、`scoring.py`（冻结 scorer 薄封装）、`diagnostics.py`、`reporting.py`、一个 CLI 和少量测试。run/config 用普通 JSON，records 用 JSONL；不建 artifact schema 平台、服务或数据库。评分路径不 import MLX。

保留最小 `ModelAdapter.load(config) / generate(messages, generation_config) / close()`。输出为 `raw_output, status, finish_reason, generated_tokens, request_ms`，以及可靠时的 memory；不含 gold。MLX 模板、tokenizer、模型加载与库差异封装在 adapter，后续换 4bit/BF16 不改 runner/scorer。当前不实现 LoRA adapter、merge 或其他后端，只用 FakeAdapter 验证解耦。

PromptBuilder 仅接收 `id/task/input`，ID 只关联结果；模型文本为原冻结 wire prompt + task prompt + output schema，加 canonical JSON input。不传 gold、作者 caption、basis、metadata、规则预测、split 或 tier。保留这种数据边界即可，不强制独立进程、权限隔离或输入包安全系统。

## 2. 首答与最小可追踪性

每个预定 case 恰好一次 generation，无 retry、fallback、补答、repair prompt、grammar-constrained 抬分或跨题 KV 复用。原始模型 continuation（含 thinking/fence/prose）先保存，official scorer 始终读取它。模板本身插入的 prefix 与 continuation 分开记录；不可用 thinking filter 清理首答。

每次 run 保存：

| 产物 | 最小内容 |
|---|---|
| `run.json` | run_id、时间、status、purpose、benchmark/freeze/scorer版本、scope manifest版本、预定 case IDs/顺序、模型ID与本地路径、revision（可得时）、真实量化配置、weight dtype、prompt版本、generation有效配置、库版本、设备/内存、load_ms、run peak memory、untouched/tuned标记 |
| `requests.jsonl` | case_id、实际 messages、实际 rendered prompt、模板设置；可保存 token IDs，但不要求所有 tokenizer 文件 hash |
| `outputs.jsonl` | case_id、未经清理的 raw_output、status/error、finish_reason、token数、request_ms；不可用计数附 null+reason |
| `predictions.jsonl` | 冻结 scorer 的 `{id,raw_output}` 投影；无返回不伪造文本，按 missing 评分 |
| `official-report.json` | 原 scorer 输出，原样保留；注明所选 scope 与 N |
| `diagnostics.json` | parser版本、恢复子串/范围/转换日志、诊断结果、primary/secondary/task/split汇总、性能 |
| `failures.jsonl` | input、gold、raw、official结果/severity、恢复状态与字段差异、错误分类、task/tier/split/family/pair/group、run/case引用 |
| `report.md` | 从以上结果生成的阅读报告 |

单一 `run.json` 足够，不必拆一串互相引用的 provenance manifests。已存在的 benchmark FREEZE/hash 校验继续使用；不做模型每 shard SHA256、tokenizer全文件hash、dirty patch溯源、签名或环境取证体系。记录真实量化配置（bits/group size/method 可得则记），不能仅凭目录名写 8bit。仅为实验追踪，不承诺密码学可复现。

模型身份/8bit/MLX 支持须在 P1 读取实际 config 并加载核实。依赖先检查本地版本与对应 API；本计划不虚构权重 repo、revision 或可加载结论，不安装/重装环境。Texa 侧 sanity/scoring 使用 venv310/Python 3.10；若真实 MLX 依赖不兼容，报告并另行确认独立实验环境，不能改坏项目解释器。

建议起点：greedy、temperature=0、batch=1、一次固定 seed（支持则设置，不支持则如实记录）、policy 128 / goal 384 / understanding 384 / legacy reference 256 max_new_tokens。其他采样参数记录有效值或 inactive；thinking 设置支持情况明确。不做 per-case RNG 派生。必须在看 baseline failure 前锁定 prompt、预算与配置；P1 不用正式 case 调优。

每次新推理用新目录，已有目录拒绝覆盖。逐条写出并 flush 即可；发生 OOM、崩溃或不可恢复异常保存已有结果并终止，标 incomplete。剩余 case 保留在 N 中计 missing，不静默跳过。不实现 crash tail recovery、自动 resume 或 interrupted-run 状态机；损坏 JSONL 明确报错，不悄悄截尾。重跑属于新 run，不能 best-of 拼接。如果错误可安全返回 raw，仍保留 frozen 判定，operational failure 单列，不另编 official severity。

## 3. 评分与诊断的最小实现

加载原 `tools/score.py`，校验原 FREEZE；读取原 curator 行，但仅 scorer/报告函数消费。预先按 `case-scope-manifest.json` 选出 rows，调用冻结 `score(selected_rows, predictions)` API，不复制/修改评分逻辑。API 本身未做完整 ID 校验，wrapper 必须拒绝重复、未知或不属于预定集合的预测；缺预测仍留分母。

原 CLI 只按 split 过滤且会包含 control，不能给它只传 semantic 首答后把缺的 control 当模型失败。对完整 split，wrapper 与 CLI 结果做一次一致性检查；对 primary/secondary，按未修改的 `score` API 生成有 scope/N 的报告。P3 合并的是预定同配置 P2+P3 首答记录，而不是重新生成 primary。

Diagnostics 实现 Spec 的保守唯一 payload 提取、S/F/T/U 分桶。恢复结果可在独立内存对象中送同一 scorer，输出名称明确为 diagnostic；不覆盖 predictions 或 official-report。recoverability 不需 native Runtime parser、LLM judge、schema 自动修复或语义近似匹配。

必要测试仅覆盖真实测量风险：

- 原包 sanity / gold round-trip / 原 scorer mutation，结果标 self-test。
- 正确 JSON、围栏+说明正确 JSON、完整 think 后正确 JSON：official 不变，后两者仅 diagnostic 可恢复。
- 两个 JSON（一对一错）、嵌套对象、数组包对象、重复 key、NaN、未闭合 think/JSON、额外字段、单引号：不得挑正确子串或修复抬分。
- 唯一合法但错误 action → T；Goal 等义但 out-of-profile → U；缺输出/截断 → U。S/F/T/U 分母相加为 N。
- 161/39/100 分类、全部 split 分母、缺输出、重复/未知 ID，严禁 control 混入 semantic。
- 相同 raw 的两种 FakeAdapter 元数据给相同 strict/recoverability；离线 replay 不推理、不改性能数据。
- 基本计时/token与百分位公式、warmup排除；raw 在打分前保存且与 adapter 返回一致。

Macro F1、context turn-set F1、混淆矩阵及 control 特有报告移至 optional；P2 只需 per-task accuracy、primary task macro、format/schema失败、官方 S0–S3/critical、T/U 和 failure corpus。

## 4. 性能只测部署判断需要的项目

- `model_load_ms`：开始加载到模型可推理，含必要 materialization，不含下载。
- `request_ms`：从模板/tokenization 到生成返回且设备实际完成；不含打分/落盘。MLX 异步边界按锁定版本可靠 API 核实。
- p50/p95：成功请求的 request_ms，nearest-rank，索引 ceil(p*n)，带 n；失败耗时和数量另列。n<20 标尾延迟样本不足。
- `generated_tokens_per_request_second = sum(generated_tokens)/sum(request_ms/1000)`，同一有效样本集合，含 prefill，不冒称 decode-only 吞吐；token 来自实际生成流/tokenizer，计数是否含 EOS 明确。
- peak process RSS / MLX allocator memory：API可靠时分别记 bytes、测量API、run scope与是否含load；不可相加。无法可靠采集时 null+reason，不阻塞质量 baseline。

一次独立合成 warmup，排除质量/steady latency，另记首次请求耗时；单个进程整体 peak 无法分离 warmup 时说明。TTFT、decode-only throughput、allocator详细核算、冷缓存实验为 optional，不是 P0/P1 blocker。报告本地设备实测身份、8GB、是否单独运行；该离线实验不等于与 Electron/Chroma/embedding 同时运行的内存验收。没有实测不能宣称现实部署已可行，也不新增桌面整合工作。

## 5. P0–P3，停止条件

| 阶段 | 实施 | 验收与停止边界 |
|---|---|---|
| P0 Benchmark sanity | 冻结包、schema、scorer、gold结构一致性；scope分类；可选独立非candidate gold交叉核验 | 无模型；不要求人工裁决。本次已有 sanity 与 scope 记录，独立语义 review 未做；复用记录并检查版本，勿反复造基础设施 |
| P1 Minimal inference chain | PromptBuilder + MLX adapter；核实 Qwen3.5-0.8B 8bit；单独合成 Policy smoke case；raw → frozen strict score | 一次 generation；真实身份/量化/有效配置/原文可查。smoke 使用同schema、独立题，不计 baseline、不根据正式case调prompt。加载不可行则报告阻碍，不换模型冒名 |
| P2 Semantic baseline | 配置锁定后顺序运行 primary 161 | strict、recoverable、per-task、format/schema、severity、T/U、latency/memory、failure corpus；无缺失才称完整。到此只读分析，不按失败调参后继续冒称 untouched |
| P3 Foundation screening | 同配置只运行 secondary 39，合并 P2 原首答 | semantic_all 200、四split、primary/secondary、taxonomy与训练价值结论；不运行100 control，不重新生成primary。**到这里停止** |

若 P2 工程失败或改配置，保存 incomplete 与 exposure 状态；新 run 必须明确是否已经看过 failure，不能用“还没做 LoRA”替代 untouched 条件。P0/P1 无模型成绩；P2/P3 首次完整质量差也是有效结果，不以达 80% 或 95% 作为交付门槛。

最小 CLI 只需要 `sanity / run / replay`，以下仅为待实现示意，不是现有命令：

```text
texa-bench sanity --benchmark <V0目录> --scope <V0.1清单>
texa-bench run --scope primary_semantic --config <固定8bit配置> --out <P2目录>
texa-bench run --scope secondary_semantic --config <同一配置> --out <P3目录>
texa-bench replay --runs <P2目录> <P3目录> --scope semantic_all --out <报告目录>
```

replay 检查两个 run 的病例不重叠、配置/模型/prompt/benchmark相同且集合恰为200；不发模型请求。可加 split 过滤只用于报告，不另建 prepare/infer/score 隔离协议。

## 6. 最终报告与 failure corpus

报告顺序：实验资格与缺口 → primary三task（count/N、strict/exact/recoverable/F/T/U）→ primary micro和task macro → secondary → semantic_all与split → 官方severity/critical及格式/限制丢失/错误对象等taxonomy → load/p50/p95/tok/s/peak与缺测原因 → 训练价值判断和限制。

保留官方 S1 与 S2/S3 区别；S1 可成功，不能都叫失败。format-only 即使诊断语义正确，官方格式失败仍留在 failures。每条 failure 同时保留原始 expected/raw、官方 reason/severity 与 diagnostic reason；不得把 U 自动标成 true semantic failure 或把 closed-profile 不识别称为已证实幻觉。

Corpus 只供本次分析，不导出训练对、不自动生成 hard cases、不启动训练。若未来使用其中任何 split 调优，明确 V0 已暴露；另备新的 V1/V1.1 held-out，不用 failure 的近似改写冒充独立评测。人工 review workflow 不再是 V0 screening 前提。

明确不实施：LoRA/SFT、production/shadow接入、dashboard、公共平台、控制套件扩展、分布式执行、模型hash基础设施、socket隔离、专用权限进程、安全字节码措施、复杂resume/crash修复、全套atomic/signing、dirty patch链、逐case RNG、环境取证。保留只读冻结校验、raw、strict评分、错误分析和基本身份配置记录已经足以回答当前问题。
