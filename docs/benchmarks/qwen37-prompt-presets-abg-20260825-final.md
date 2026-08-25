# Qwen 3.7 Plus：Legacy / Refined / Minimal Prompt 对照

日期：2026-08-25

## 结论

在本轮固定的 A、B、G Texa workload 上，建议将 **Refined Teaching Prompt** 作为 Qwen 3.7 Plus 的下一阶段默认候选，先做小流量试运行；Legacy 保留为可回滚 preset，Minimal 继续作为实验基线。

Refined 相比 Legacy 的总延迟中位数由 `37.012s` 降到 `20.794s`（`-43.8%`），推理 token 由 `104,659` 降到 `51,761`（`-50.5%`），正文字符中位数由 `643` 降到 `301.5`。逐题复核未发现 A/B 教材事实或引用的实质性退化；相反，在 G 组错误或不完整的上游 context 上，Refined 更少把旁支证据扩写成看似完整的答案。

这不证明 Refined 在所有 Texa intent 上都优于 Legacy。本轮只比较 Qwen 3.7 Plus，且只覆盖 A/B/G；Quiz、结构化输出、工具调用、视觉路径没有纳入这次 Prompt 对照。

## 1. 当前 Teaching Prompt 架构审查

教材问答的主调用链为 `main graph / generator → _build_generate_messages()`。Resolver、ConversationContextPack、检索和 EvidencePack 在生成 Prompt 之前完成；Prompt 只能约束如何使用这些输入，不能修复错误的指代解析或检索主题。

Teach / summarize 还有独立的 `chapter_subgraph → TEACH_PROMPT` 路径。两条路径原本重复规定定义、直观例子、问题主线、例题、引用、LaTeX 和粗体格式。

Legacy 的有效重点可以归并为六类：

1. 教材事实只来自本轮 EvidencePack，工具事实只来自实际返回结果；证据不足必须说明。
2. 引用必须使用真实 `[[cite:E#]]`，禁止暴露教材路径和内部 ID。
3. 保留工具警告、验证失败和待确认状态。
4. 定义、列举、关系、公式、计算和推导需要回答完整，但不能用模型记忆补教材缺口。
5. 教材例题题干不完整时不得冒充原题；构造例题必须标注。
6. 公式使用闭合 LaTeX，粗体保持克制。

Legacy 繁杂主要来自重复和流程化，而不是上述边界本身：

- 事实边界同时出现在角色前言、通用要求、证据不足规则和 intent 尾指令中。
- “关系题”在通用要求和 `output_instruction` 中重复规定固定讲解顺序。
- 直观例子、以题讲知识点和例题自检互相叠加，容易诱导模型无论问题大小都展开教学流程。
- 中英规则混排，多项编号重复为 `0.`，降低可读性和维护性。
- `GENERATE_PROMPT` 模板 `1643` 字符，例题自检另有 `317` 字符；Teach 模板还有 `573` 字符的相似规则。

## 2. Refined Prompt 接入

新增 `refined-teaching-v1-2026-08-25`，正文 `439` 字符。它保留上述六类产品合同，但取消固定 CoT、强制教学步骤和 intent 专属长尾规则。

切换方式：

```powershell
$env:TEXA_TEACHING_PROMPT_MODE = "legacy"  # 默认与回滚
$env:TEXA_TEACHING_PROMPT_MODE = "refined"
$env:TEXA_TEACHING_PROMPT_MODE = "minimal"
```

`fine-tune`、`fine_tune` 和 `finetune` 作为 `refined` 的兼容别名。“Fine-tune Prompt”这里只表示人工精炼的 preset，不是模型权重微调。

Generator 与 Teach 子图都支持三套 preset；Compact preset 使用相同的有界 Context Pack、EvidencePack、工具结果和学习记录。Teach 子图的 context telemetry 也按实际 preset 记录，不再把 Compact Prompt 误记成 Legacy 长度。

## 3. 对照方法

- 模型：仅 `qwen3.7-plus`。
- 参数：`temperature=0.1`、thinking 开启、请求 `max_tokens=4096`。
- workload：A 4 个、B 5 个、G 12 轮；G 中第 9、11、12 轮被 Evidence gate 拒绝，不发生模型调用，因此实际为 18 个模型 case。
- 重复：每个 case 每套 preset 3 次，共 162 条；其中 Minimal 54 条的 message SHA-256 与上一轮完全一致，直接复用，新增调用为 108 次。
- 单变量控制：复用上一轮冻结的 production context packet；三套 preset 使用完全相同的 human payload，只替换 system policy。Legacy system 规则取当前代码。这样测的是 policy 文本影响，不把重新检索漂移混入实验。
- TTFT：记录首个流式 delta，可能是 reasoning delta，不等同于用户看到首个正文字符的时间。
- 原始回答、system prompt、token、reasoning、TTFT、总延迟、finish reason、引用评分均完整保存。

Prompt 中位字符数：

| Preset | System | System + frozen human |
|---|---:|---:|
| Legacy | 1250 | 3444 |
| Refined | 439 | 2587.5 |
| Minimal | 151 | 2299.5 |

## 4. 总体结果

| 指标（54 条/preset） | Legacy | Refined | Minimal |
|---|---:|---:|---:|
| 总延迟中位 | 37.012s | **20.794s** | 21.162s |
| P90 总延迟 | 61.564s | **30.674s** | 35.214s |
| TTFT 中位 | 1.003s | 0.936s | **0.918s** |
| 正文字符中位 | 643 | **301.5** | 463 |
| 输入 token | 146,406 | 125,952 | **115,962** |
| 输出 token | 125,295 | **61,265** | 69,088 |
| reasoning token | 104,659 | **51,761** | 54,984 |
| 无效引用 | 0 | 0 | 0 |
| 按标价估算 | ¥1.2501 | **¥0.6900** | ¥0.7254 |

成本按华北 2（北京）、单次输入不超过 256K 的原价估算：输入 ¥2/百万 token、输出（含 thinking）¥8/百万 token。免费额度下的实际账单可能为 `¥0`，表内数字不是本账户扣款记录。

## 5. 分组结果

| 组别 | Preset | 总延迟中位 | TTFT 中位 | 正文字符中位 | reasoning token | 估算成本 |
|---|---|---:|---:|---:|---:|---:|
| A 教材 RAG | Legacy | 34.691s | 1.225s | 544 | 20,718 | ¥0.2739 |
| A 教材 RAG | Refined | 21.626s | 1.005s | 385 | 10,222 | ¥0.1622 |
| A 教材 RAG | Minimal | **19.678s** | **0.917s** | 485 | **9,413** | **¥0.1460** |
| B Conversation | Legacy | 33.357s | 1.007s | 574 | 23,242 | ¥0.3153 |
| B Conversation | Refined | **16.641s** | 1.037s | **338** | **11,624** | **¥0.1833** |
| B Conversation | Minimal | 20.345s | **0.980s** | 440 | 12,882 | ¥0.2015 |
| G Session | Legacy | 42.437s | 0.973s | 664 | 60,699 | ¥0.6609 |
| G Session | Refined | 22.630s | **0.856s** | **290** | **29,915** | **¥0.3445** |
| G Session | Minimal | **22.372s** | 0.889s | 470 | 32,689 | ¥0.3779 |

## 6. 回答质量与文风

### A：普通教材 RAG

三套 preset 都能正确回答电容动态测量、热敏电阻特点、压电静态测量和标准差方法公式追问，并且没有无效引用。Legacy 更常加入“直观例子”和额外分层；Refined 保留结论、原因、必要公式和证据边界，但删除非必要类比；Minimal 介于两者之间。

关键词 scorer 给出的必需点 recall 为 Legacy `1.000`、Refined `0.963`、Minimal `0.963`。差异来自同义表达的字面误判：例如某次使用“不适合静态测量”而非金标字符串“不能用于静态测量”。逐题复核未确认实质事实漏项。

### B：Conversation Resolver

Resolver 输入与 resolved query 固定，因此三套 Prompt 不改变指代解析正确率。Refined 在“高频动态测量是否适合”这类短追问上直接给结论和证据，明显比 Legacy 的类比扩写更合适。

关键词 recall 的 Legacy / Refined / Minimal 为 `1.000 / 0.833 / 0.778`，主要是假阴性：“不宜用于高频动态测量”没有命中金标的“不宜于高频动态测量”。三套回答的语义结论均正确。这个 scorer 需要在后续改为归一化短语或人工判分，不能拿当前数字宣称 Legacy 更准确。

### G：持续学习 Session

上游 Resolver / retrieval 在第 6～8、10 轮已经发生主题偏移或指代混合；三套 Prompt 都无法恢复不存在于 context packet 的正确语义。

Prompt 的差异体现在失败方式：

- Legacy 往往把错误检索到的“函数随机误差”“方法误差”等旁支材料完整展开。第 5 轮还自动构造了一道长补充例题，使原本只需列出四种方法的回答显著膨胀。
- Minimal 有时会根据相邻证据主动补出一个看似合理的处理步骤；在第 10 轮，它继续回答“先算平均值和残差”，但该轮冻结证据并不足以确定用户真正指代。
- Refined 在证据与问题不匹配时更倾向于短答或明确证据不足。第 10 轮有 1 次拒答没有引用；这是合理行为，因为正文没有提出教材事实，不属于引用失败。

因此，G 组结果说明缩短 Prompt 不能修复 Resolver，但可以减少错误 context 被模型放大的程度。

### 文风量化

| 指标（每条均值） | Legacy | Refined | Minimal |
|---|---:|---:|---:|
| Markdown 标题数 | 0.83 | **0.00** | 0.15 |
| 粗体片段数 | 4.78 | **3.04** | 4.57 |
| 列表项数 | 3.28 | **2.35** | 3.09 |
| 泛化鼓励语总数 | 5 | **0** | 1 |

Refined 仍会用粗体和列表组织答案，但基本不使用 `#` 标题，整体更接近短教材答疑。若后续认为长计算题需要标题，应基于题型增加轻量格式条件，而不是恢复 Legacy 的整套教学流程。

## 7. Qwen 的 Prompt 特异性表现

Qwen 对流程化 Teaching Prompt 很敏感。Legacy 不只增加约 14% 输入 token，还让输出 token 增加约 104%、reasoning token 增加约 102%（均相对 Refined）；说明主要耗时不是读取更长 Prompt，而是模型把多个教学要求逐项执行。

Minimal 并不必然最短。它缺少“严谨、简洁”和“不要套用固定教学流程”等明确约束，正文中位数比 Refined 长约 54%。对 Qwen 而言，少量非流程化的风格与证据边界规则，比完全开放的 Minimal 更能控制解释密度。

## 8. 建议

1. 将 `refined` 设为 Qwen 3.7 Plus 的小流量默认候选，Legacy 保留一键回滚，Minimal 保留为 benchmark control。
2. 不再为 Qwen 添加模型专属 CoT、固定教学步骤或 intent 长 prompt；先验证 Refined 在真实负反馈中的表现。
3. 下一轮补测 C/D/E：证据不足、工具状态和结构化输出是 Refined 保留合同后最需要确认的边界。
4. 单独修复 G 组 Resolver / retrieval 的第 6～8、10 轮漂移；不要用更长生成 Prompt 掩盖上游错误。
5. 将 lexical required-point scorer 改为同义短语归一化或人工 rubric，避免“于/用于”“不能/不适合”制造虚假回归。

## 9. 产物

- 原始实验 JSON：`benchmark_results/qwen37_prompt_presets_abg_20260825.json`
- 冻结 fixture：`benchmark_results/qwen37_prompt_presets_abg_fixture_20260825.json`
- 聚合分析：`benchmark_results/qwen37_prompt_presets_abg_analysis_20260825.json`
- 三套 Prompt、18 个 case、3 次重复的完整原文：`benchmark_results/qwen37_prompt_presets_abg_raw_20260825.md`
- 运行脚本：`scripts/benchmark_qwen_prompt_presets.py`
- 分析脚本：`scripts/analyze_qwen_prompt_presets.py`

