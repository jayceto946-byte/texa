# Gemma3-1B-IT-8bit-Screening

2026-10-06（Asia/Shanghai）。本轮是已曝光、author-frozen 内部 foundation 横向筛选；不是 held-out 准确率或生产验收。没有训练、LoRA、prompt 调参或修改 Runtime。

## 模型身份与执行合同

- exact repo：`mlx-community/gemma-3-1b-it-8bit`，revision `7b963136f21d05ca8b367c93a9c47a7944ad281a`。来源转换声明：`google/gemma-3-1b-it`（IT，非 Base）。[仓库](https://huggingface.co/mlx-community/gemma-3-1b-it-8bit)。
- 单一权重缓存：`/Users/jichengqian/.cache/huggingface/hub/models--mlx-community--gemma-3-1b-it-8bit/snapshots/7b963136f21d05ca8b367c93a9c47a7944ad281a`。snapshot 链接到 HF blobs；未另存 LM Studio 或项目权重副本。API gated=false，现有 credential=false，下载成功，没有绕过权限。
- architecture `['Gemma3ForCausalLM']`，model_type `gemma3_text`；hidden_size 1152 / layers 26 / vocab 262144。名义 1B；按 tensor 形状重建唯一参数 999,885,952。转换导出同时保存相同 embedding/lm_head，物理 tensor 参数 1,301,875,840；三个对应 weight/scales/biases 的 SHA256 均相同，详见 model-audit.json。未改权重或去重加载。
- quantization `{'group_size': 64, 'bits': 8}`；实际加载 184 个量化模块，全部 bits=8/group_size=64。weight dtypes `['mlx.core.float16', 'mlx.core.uint32']`；磁盘 tensor dtypes `{'F16': 525, 'U32': 184}`。
- 库：`{'mlx': '0.32.0', 'mlx-lm': '0.31.3', 'transformers': '5.14.1'}`。评分使用 venv310 / Python 3.10.21；推理复用既有 LM Studio Python 3.11.9，不安装依赖。
- 原生 tokenizer/chat template 完整保存于 permutation/run.json，SHA256 `7de1c58e208eda46e9c7f86397df37ec49883aeece39fb961e0a6b24088dd3c4`；system 内容由原生模板并入首个 user turn，messages 文本逐项保持旧 screening 内容。thinking=false = not_applicable。
- 原转换仓库未提供 generation_config，MLX 只识别 `<eos>`，未识别 IT 原生 `<end_of_turn>`。发现后停止原无效尝试，raw 全保留在相邻 gemma3-1b-it-8bit-20261006 目录；其结果不作为有效模型评分。仅在 adapter/tokenizer 层注册停止符，未截取或修复 raw。[Gemma 3 技术报告](https://storage.googleapis.com/deepmind-media/gemma/Gemma3Report.pdf)说明 IT 使用 end_of_turn 结束生成。有效 run EOS IDs `[1,106]`。
- greedy / temperature=0 / batch=1 / seed=0，无 retry、self-correction、best-of 或 constrained decoding。Policy=128、Goal=384、Understanding=384、Reference=256 tokens，与基线一致。
- permutation 直接逐条核对并复用旧 A/B/C jobs，使用已有简化诊断提示；完整 semantic set 使用原 frozen wire + task + schema prompt。因此下文两类结果分开比较。
- ModelAdapter 仅泛化架构校验、原生停止符和可审计模板元数据；未修改 frozen benchmark/gold/scorer/task definitions/Runtime/官方 Qwen baseline。32 项 Harness 测试通过（含 Gemma 错规模/4bit 拒绝检查）。

## Smoke

每个任务 1 条，共 Policy、Goal、Understanding 三条；操作 status=ok、raw 已保存、scorer 正常返回；严格输出失败原样保留。Smoke 只验证链路，未据此修改正式提示。Smoke 使用三条已曝光 benchmark 示例，后续正式首答独立生成；不把 smoke 加入正式分母。

## Policy permutation：240 次

A=原顺序；B=仅反转候选顺序；C=仅轮换候选 ID（双候选互换，三候选前移一格）；候选内容、题意、范围保持不变。每变体 N=80；58 双候选、22 三候选。语义身份为原候选 ID + 原 kind/args，非法输出没有可用选择，分母仍保留。

| 变体 | Gemma semantic accuracy | Qwen semantic accuracy | Gemma 合同合法 |
|---|---:|---:|---:|
| A | 18/80 (22.50%) | 45/80 (56.25%) | 37/80 |
| B | 19/80 (23.75%) | 40/80 (50.00%) | 47/80 |
| C | 27/80 (33.75%) | 41/80 (51.25%) | 45/80 |

| Pair | Gemma 相同 semantic choice | Qwen 相同 semantic choice |
|---|---:|---:|
| A/B | 36/80 (45.00%) | 21/80 (26.25%) |
| A/C | 11/80 (13.75%) | 68/80 (85.00%) |
| B/C | 10/80 (12.50%) | 17/80 (21.25%) |

三变体同一语义候选：Gemma 10/80 (12.50%)，Qwen 15/80；三变体全部正确：Gemma 6/80 (7.50%)，Qwen 8/80。
双候选稳定语义选择：Gemma 10/58 (17.24%)，Qwen 0/58。一致但错误也计入稳定，不能把 consistency 当 accuracy。

| 变体 | 第1候选 | 第2候选 | 第3候选 | a0 | a1 | a2 |
|---|---:|---:|---:|---:|---:|---:|
| A | 36/80 (45.00%) | 1/80 (1.25%) | 0/80 (0.00%) | 36/80 (45.00%) | 1/80 (1.25%) | 0/80 (0.00%) |
| B | 1/80 (1.25%) | 46/80 (57.50%) | 0/80 (0.00%) | 43/80 (53.75%) | 3/80 (3.75%) | 1/80 (1.25%) |
| C | 11/80 (13.75%) | 34/80 (42.50%) | 0/80 (0.00%) | 34/80 (42.50%) | 11/80 (13.75%) | 0/80 (0.00%) |

第三候选率以全部80例为分母（只有22例具第三候选）；非法输出不计任何位置/ID。position 与 ID 关联由 B/C 分离，不能仅凭 A 的分布归因。

| Stratum | 变体 | Gemma 正确 | Qwen 正确 |
|---|---|---:|---:|
| tool_vs_answer | A | 18/60 (30.00%) | 38/60 (63.33%) |
| tool_vs_answer | B | 19/60 (31.67%) | 30/60 (50.00%) |
| tool_vs_answer | C | 26/60 (43.33%) | 32/60 (53.33%) |
| multi_intent_order | A | 0/20 (0.00%) | 7/20 (35.00%) |
| multi_intent_order | B | 0/20 (0.00%) | 10/20 (50.00%) |
| multi_intent_order | C | 1/20 (5.00%) | 9/20 (45.00%) |

这些 strata 使用旧 probe 的标签口径：非 multi_intent_order 的60例归 tool_vs_answer，20例归 multi-intent。

预先锁定扩展门槛：任一 arm 在全部80例中 ≥95% 固定某位置或 ID 则停止扩大；本轮 catastrophic_shortcut=False，决定 `continue`。此门槛是成本控制门槛，不是 semantic prior 合格线。

### 原保守 parser 的额外诊断（不替代 strict）

为了区分围栏失败和选择语义，沿用既有 semantic-recoverability/v0.1 的唯一 outer payload 提取，不修 JSON、不选择多答案。官方分数与 results 的 strict 均保持原样。

| Arm | 可判定选择 | 诊断语义正确 | 第1/2/3位置 | a0/a1/a2 |
|---|---:|---:|---|---|
| A | 76/80 | 38/80 | {'1': 75, '2': 1, '3': 0} | {'a0': 75, 'a1': 1, 'a2': 0} |
| B | 80/80 | 37/80 | {'1': 2, '2': 72, '3': 6} | {'a0': 64, 'a1': 14, 'a2': 2} |
| C | 79/80 | 42/80 | {'1': 32, '2': 47, '3': 0} | {'a0': 47, 'a1': 32, 'a2': 0} |

诊断三变体同语义 16/80（Qwen15/80），三变体全正确 9/80（Qwen8/80），双候选稳定 10/58（Qwen0/58）。恢复后 A 的 a0 选择为75/76个可判定答案：明显 ID偏好；B仍64/80，C47/79。Gemma没有稳定表现出摆脱 shortcut 的整体优势。
严格有效选择中 a0 的条件比例 A=36/37、B=43/47、C=34/45；全80分母的低位置率不能掩盖这种偏好。Gemma的模式不同于Qwen C恒选第二位，但存在首候选/低ID先验；二候选在10题稳定只证明局部进步。

## 完整 semantic screening

primary 161 + secondary 39，共200唯一病例；semantic_all 为严格 replay，无额外200次推理。原始结果不剥围栏、不修 JSON，使用原 frozen scorer。

| Set/task | Gemma strict | Qwen strict | 差值 pp | Gemma S/F/T/U |
|---|---:|---:|---:|---|
| primary_semantic/goal_summary | 0/40 (0.00%) | 0/40 (0.00%) | +0.00 | 0/0/0/40 |
| primary_semantic/policy_select | 0/80 (0.00%) | 40/80 (50.00%) | -50.00 | 0/11/13/56 |
| primary_semantic/question_understanding | 0/41 (0.00%) | 0/41 (0.00%) | +0.00 | 0/0/0/41 |
| primary_semantic/total | 0/161 (0.00%) | 40/161 (24.84%) | -24.84 | 0/11/13/137 |
| secondary_semantic/question_understanding | 0/19 (0.00%) | 0/19 (0.00%) | +0.00 | 0/0/0/19 |
| secondary_semantic/reference_resolve | 0/20 (0.00%) | 0/20 (0.00%) | +0.00 | 0/0/0/20 |
| secondary_semantic/total | 0/39 (0.00%) | 0/39 (0.00%) | +0.00 | 0/0/0/39 |
| semantic_all/goal_summary | 0/40 (0.00%) | 0/40 (0.00%) | +0.00 | 0/0/0/40 |
| semantic_all/policy_select | 0/80 (0.00%) | 40/80 (50.00%) | -50.00 | 0/11/13/56 |
| semantic_all/question_understanding | 0/60 (0.00%) | 0/60 (0.00%) | +0.00 | 0/0/0/60 |
| semantic_all/reference_resolve | 0/20 (0.00%) | 0/20 (0.00%) | +0.00 | 0/0/0/20 |
| semantic_all/total | 0/200 (0.00%) | 40/200 (20.00%) | -20.00 | 0/11/13/176 |

| Task（semantic_all） | Gemma schema | contract | field micro | Qwen field micro | Unsupported 值病例 G/Q |
|---|---:|---:|---:|---:|---:|
| goal_summary | 0/40 | 0/40 | 0.00% | 0.83% | 0/39 |
| policy_select | 0/80 | 0/80 | 0.00% | 50.00% | 0/0 |
| question_understanding | 0/60 | 0/60 | 0.00% | 3.67% | 0/48 |

| Task/field | Gemma 正确 | Qwen 正确 |
|---|---:|---:|
| goal_summary/objective | 0/40 | 0/40 |
| goal_summary/success_criteria | 0/40 | 0/40 |
| goal_summary/title | 0/40 | 1/40 |
| policy_select/action_id | 0/80 | 40/80 |
| question_understanding/action | 0/60 | 0/60 |
| question_understanding/dimensions | 0/60 | 9/60 |
| question_understanding/entity_spans | 0/60 | 0/60 |
| question_understanding/intent | 0/60 | 2/60 |
| question_understanding/reference_id | 0/60 | 0/60 |

Goal negative/exclusive constraint 字面保留：Gemma {'hit': 0, 'total': 42, 'rate': 0.0}；Qwen {'hit': 0, 'total': 42, 'rate': 0.0}。全限制保留：Gemma {'hit': 0, 'total': 70, 'rate': 0.0}；Qwen {'hit': 0, 'total': 70, 'rate': 0.0}。
字段/negative/unsupported 指标复用原 field_analysis；它只严格解析 JSON，不把围栏恢复结果混入原字段成绩。unsupported 是 enum/候选/span/原文不支持 flag，Goal 同义改写需要人工审阅，不自动等同已证实幻觉。Reference 由原 frozen scorer 与官方诊断覆盖，不套用不支持该任务的三任务字段分析。
全量 severity：Gemma `{'S2': 200}`；Qwen `{'S2': 160, 'S0': 40}`。critical Gemma=0；Qwen=0。taxonomy `{'invalid_json:Expecting value: line 1 column 1 (char 0)': 200, 'format_only': 11}`。
S/F/T/U、strict/exact/recoverable、分 split、失败原文与来源分别保留于 semantic_all/diagnostics.json、official-report.json、failures.jsonl；恢复诊断不会替代 strict 成绩。

### 原保守提取后的字段诊断（非 official）

复用同一个 field_analysis，输入为既有保守 parser 唯一 payload；不更改官方 strict/失败原文。

| Task | Gemma 合同合法 | Gemma完整匹配 | Qwen完整匹配 | 字段micro G/Q | Unsupported病例 G/Q |
|---|---:|---:|---:|---:|---:|
| goal_summary | 0/40 | 0/40 | 0/40 | 0.00%/0.83% | 15/39 |
| policy_select | 24/80 | 11/80 | 40/80 | 13.75%/50.00% | 56/0 |
| question_understanding | 0/60 | 0/60 | 0/60 | 17.67%/3.67% | 33/48 |

逐字段诊断：

- goal_summary: Gemma {'objective': {'correct': 0, 'N': 40}, 'success_criteria': {'correct': 0, 'N': 40}, 'title': {'correct': 0, 'N': 40}}; Qwen {'objective': {'correct': 0, 'N': 40}, 'success_criteria': {'correct': 0, 'N': 40}, 'title': {'correct': 1, 'N': 40}}
- policy_select: Gemma {'action_id': {'correct': 11, 'N': 80}}; Qwen {'action_id': {'correct': 40, 'N': 80}}
- question_understanding: Gemma {'action': {'correct': 20, 'N': 60}, 'dimensions': {'correct': 6, 'N': 60}, 'entity_spans': {'correct': 0, 'N': 60}, 'intent': {'correct': 27, 'N': 60}, 'reference_id': {'correct': 0, 'N': 60}}; Qwen {'action': {'correct': 0, 'N': 60}, 'dimensions': {'correct': 9, 'N': 60}, 'entity_spans': {'correct': 0, 'N': 60}, 'intent': {'correct': 2, 'N': 60}, 'reference_id': {'correct': 0, 'N': 60}}

保守提取 Goal negative/exclusive retention Gemma {'hit': 0, 'total': 42, 'rate': 0.0}；Qwen {'hit': 0, 'total': 42, 'rate': 0.0}。全限制：Gemma {'hit': 0, 'total': 70, 'rate': 0.0}；Qwen {'hit': 0, 'total': 70, 'rate': 0.0}。这些是原文atom字面口径，不冒充语义幻觉人工金标。

## 端侧成本

单模型 request wall time 包含模板/tokenization、prefill、生成及 MLX synchronize；不是 decode-only tok/s。排除 smoke，无跨题 KV 复用。RSS/MLX peak 含加载，二者不可相加。Gemma permutation 未另做 synthetic warmup，Qwen permutation 有一次；完整 semantic 两者都使用原 Harness warmup，因此正式200例性能口径更可比。

| 口径 | Gemma | Qwen |
|---|---:|---:|
| permutation p50_ms | 918.047 | 619.457 |
| permutation p95_ms | 1079.196 | 712.633 |
| permutation generated_tokens_per_request_second | 12.376 | 12.858 |
| permutation load ms | 2287.470 | 1425.152 |
| permutation peak_process_rss MiB | 1428.06 | 824.42 |
| permutation peak_mlx_allocator MiB | 1476.96 | 1015.54 |
| semantic_all p50_ms | 2636.503 | 971.551 |
| semantic_all p95_ms | 5565.425 | 7871.458 |
| semantic_all generated_tokens_per_request_second | 29.874 | 37.302 |
| primary/secondary load ms | 2471.412 / 2440.574 | 1318.904 / 1526.900 |
| semantic max peak_process_rss MiB | 1281.47 | 811.36 |
| semantic max peak_mlx_allocator MiB | 1522.08 | 1109.49 |

设备同为 Mac17,5 / Apple A18 Pro / 8GiB；running_alone=false。两模型非交错配对，热状态/后台负载未控制，且模型 tokenizer 与输出长度不同；tok/s 和 wall latency 是实际该 workload 的成本，不是同等有效语义产出速度。
本轮没有运行 Electron/Chroma/embedding 共存恢复测试，也没有已批准的数值端侧 envelope；可以判断单模型是否加载/完成、量化内存增量，但不能宣称 Texa 共存 envelope 验收通过。

## 完整性与产物

冻结包内271个 pinned 文件及99个额外保护文件已核验，官方Qwen baseline、旧 diagnostic/permutation、除adapter外的Harness均未改变。

- results.jsonl：240次permutation + 200次semantic，共440条首答；phase分离，smoke及无效adapter尝试不计入。
- failures.jsonl：permutation strict失败及正式semantic失败，保留原raw。
- run.json：阶段门槛、模型身份、完成状态与性能索引；各子目录run.json保存原始测量。
- model-audit.json、permutation-metrics.json、permutation-recovery-diagnostics.json、field-diagnostics.json、field-recovery-diagnostics.json、performance-comparison.json：严格与恢复诊断分离。

严格字段unsupported=0只是JSON无法解析时没有可识别值，并不等于没有幻觉；保守提取的flag提供更多证据，但仍不是人工金标。

## 最后直接回答

1. **Gemma是否存在明显position / ID bias？存在。** 它没有复现Qwen C恒选第二位置80/80，但保守恢复后A可判定答案75/76选择a0，B为64/80，C为47/79。bias的具体形态不同，shortcut并未可靠消失。
2. **Permutation-invariant能力是否明显强于Qwen？没有。** strict三变体稳定10/80 vs15/80；保守恢复后16/80 vs15/80，三变体全正确9/80 vs8/80。双候选稳定10/58 vs0/58是局部改善，整体提升不足。
3. **Policy、Goal、Understanding分别如何？** 原frozen prompt下Policy strict 0/80 vs40/80（−50pp）；Goal 0/40 vs0/40；Understanding 0/60 vs0/60（primary均0/41）。保守恢复Policy仅11/80 vs40/80（−36.25pp）。Goal字段micro 0% vs0.83%，否定限制均0/42。Understanding字段micro 17.67% vs3.67%（+14pp），其中intent27/60 vs2/60、action20/60 vs0/60，但entity_spans/reference_id均0、完整合同均0/60；有局部标签能力，不足以接管理解。
4. **1B增量是否在可接受端侧envelope？单模型可运行，整体尚未验收。** 完整200例MLX峰值增加约413MiB，RSS峰值增加约470MiB；p50 2.637s vs0.972s（+1.665s），p95 5.565s vs7.871s（−2.306s），request-inclusive tok/s29.87 vs37.30（约−19.9%）。较低p95不等于更高有效产出，输出长度及失败形态不同；无Electron共存验收，不能正式判定Texa envelope通过。
5. **Gemma是否比Qwen更值得成为Texa Runtime训练foundation？本轮证据不支持。** 增加内存与典型延迟后，没有获得明显更强的整体semantic invariance；ID先验、Schema复制与输入回显和完整合同失败仍突出。暂不将Gemma替换为优先foundation，也不将Qwen原baseline解释为已经可靠。Understanding局部intent/action改善可留作研究线索，不能抵消Policy/Goal及完整理解合同的缺口。本轮到此完成，不训练、不调prompt。
