# Runtime-0.8B-Diagnostic-Probe

2026-10-06。`diagnostic_only=true`，exposed dev diagnostic；本轮不是新的正式 Benchmark 成绩。模型保持本地 Qwen3.5-0.8B MLX 8bit、greedy、temperature=0、thinking=false、batch=1、seed=0。没有训练、Runtime 改动或模型/依赖下载。

## 直接结论

1. **原 baseline 的低分同时来自输出合同负担和语义/执行判断缺陷。** Primary 的121条失败中，81条（66.9%，占161条的50.3%）是Goal/Understanding的格式、Schema或跨字段合同失败，40条是Policy合法候选选择错误。这是原失败形态分类，不能说81条的语义原本正确。移除完整Schema后，Goal/Understanding的Schema合法输出从3/81变成69/81，但两任务新增完整匹配仍为0；本轮没有证明这81条可以通过格式减负恢复语义成功。
2. **低合同负担下测得的完整语义交付仍为Goal 0/40、Understanding 0/41。** 部分字段存在有效信息：Goal title为23/40，Understanding intent为12/41、dimensions为7/41。它们是有界字段的gold匹配，不能合并成“模型完全不懂”，也不能当作完整任务成功。
3. **原Policy 50%的主要模式是候选位置偏好。** 80条中79次选a1；40个错例的可观察主类是28个工具/直接回答边界、11个先后顺序、1个存在相反顺序表述需复核的样本。新20条定向诊断由原12/20变为简化15/20，受约束14/20，显示部分语义可受清楚说明激活；选择a1的偏好仍很强。
4. **Rule与Qwen错误集合高度互补，但主要是相反槽位先验。** 两者同时正确0；Qwen-only 40；Rule-only 39；同时错误1。Rule在冻结包中80次全部选a0，Qwen几乎总选a1。知道gold后选择两者可得到79/80的oracle上界，当前没有不使用gold便能可靠选择两者的仲裁器，不能把98.75%当作可部署ensemble能力。
5. **当前相对更适合研究狭窄的Policy selection。** 有少量核心短语/intent抽取能力，但semantic extraction尚不能完成对象/动作交付；Goal transformation会添限制与示例产物；reference/context resolution没有新增正向证据，不适合交由它承担。
6. **证据不足以直接进入覆盖全部Runtime职责的LoRA/SFT。** Policy可成为后续最小训练可行性研究对象，但定向20题、已曝光且仍有槽位偏好，尚不能证明稳定foundation prior。Goal/Understanding的输出纪律、范围保持、复制示例和错误澄清同时失稳。本轮到解释低分为止，不开始训练。

这里的“0%”是本轮固定提示下、原gold/profile要求的完整交付匹配；不是开放语义能力或理论上限为零。一个格式示例也引入了可观测的内容复制，进一步限制“semantic ceiling”的解释。

## 条件、选择与评分资格

- A/B共用相同输入、相同gold、相同模型和预算：全部40 Goal、全部41 primary Understanding、10个Policy语言对共20题。Policy按family选取，原提示在该20题上为60%，高于全80题50%；不能将75%外推为80题的改进成绩。
- Goal仍用现有`title/objective/success_criteria`三字段。`constraints`不是该GoalSummary的既有字段，因此没有新增它；范围/否定/期限仍放在objective中，按原metadata atoms测保留。Understanding仍保留既有五字段和Unicode位置合同，没有新Runtime IR。
- A省略完整JSON Schema，使用简洁说明、允许枚举和一个独立合法格式示例。没有当前case的gold、metadata、caption、规则预测或few-shot答案。输入JSON未改写，候选未删减/重排。
- B使用既有`mlx_vlm.structured.build_json_schema_logits_processor`，通过`mlx_lm.stream_generate(logits_processors=[...])`接入。后端版本：mlx-vlm 0.6.5、llguidance 1.7.6；Backend schema来自原冻结文件，无case-specific gold、实体位置或候选筛选。Schema不作为B的模型文本。
- 完整Schema对Policy/Goal实际可运行；Understanding在首次编译时报告`ValueError: Unimplemented keys: ["uniqueItems"]`，未生成任何token。这一失败原样保留，后续40题未以该后端运行；不是模型0%成绩。另设B-json-only，原生`{"type":"object"}`语法约束，生成同样41个Understanding首答；它不保证五字段Schema。没有自行实现parser、删除uniqueItems冒称完整Schema支持、重试答案或self-correction。
- 每个条件每题一次生成，无跨题KV复用；raw逐条flush后评分。D仅对finish=length的条件扩大预算，复用其已保存的current raw。每条D使用与current完全相同的rendered prompt/解码类型，预算384→768。
- 评分仍在venv310/Python 3.10，MLX推理复用经授权的既有LM Studio Python 3.11环境。加载路径/8bit量化/weight dtypes/库版本/模板设置与baseline逐项一致。辅助Schema只约束既有输出结构/枚举，不按gold缩小语义候选。
- 原baseline记录和配置共48个文件运行前后SHA256相同；271个冻结文件及case/input/gold hashes再次校验通过。原raw、official report、gold/scorer和prompt version未覆盖。当前展示原raw上的新字段诊断，不重写任何正式成绩。

### 指标定义

`strict JSON valid`要求整个raw可被原json_strict读取；不剥围栏、不取子串、不修复。`schema valid`是原输出Schema；`contract valid`还检查候选、span及字段组合。`完整语义匹配`用未修改的frozen evaluate/structured_match，调用结果全标diagnostic_only，未生成新的official-report。

字段准确率：Goal title去首尾空白；objective原atoms多集合相等；success_criteria descriptions多集合相等。Understanding五字段按原合同逐项相等，dimensions忽略顺序。分母包含所有预定样本和所有要求字段，截断/无输出不悄悄剔除。

constraint/negative retention按gold原文atom在objective中的出现计算；negative集合是包含不/别/勿/禁止/只/仅/无需/暂缓的objective atoms，共42条（包括独占范围）。这是字面保留下界，同义改写可能被低估。out-of-profile或不在原输入中的值只标unsupported/needs_review，不一律声称已证实幻觉；明显复制无关示例产物另列。

## Probe A / B：格式合法与语义交付分开看

| 任务/条件 | N | 严格JSON | Schema合法 | 合同合法 | 完整语义匹配 | 字段micro | length |
|---|---:|---:|---:|---:|---:|---:|---:|
| goal_summary / 原提示/旧raw | 40 | 40/40 | 0/40 | 0/40 | 0/40 | 0.8% | 0/40 |
| goal_summary / 简化 | 40 | 39/40 | 39/40 | 39/40 | 0/40 | 22.5% | 1/40 |
| goal_summary / 简化+完整Schema | 40 | 37/40 | 37/40 | 37/40 | 0/40 | 25.0% | 3/40 |
| question_understanding / 原提示/旧raw | 41 | 33/41 | 3/41 | 0/41 | 0/41 | 3.4% | 8/41 |
| question_understanding / 简化 | 41 | 41/41 | 30/41 | 0/41 | 0/41 | 29.3% | 0/41 |
| question_understanding / 简化+完整Schema | 41预定、0生成 | 不支持 | 不支持 | — | — | — | — |
| question_understanding / 简化+JSON语法 | 41 | 41/41 | 21/41 | 0/41 | 0/41 | 8.3% | 0/41 |
| policy_select / 原提示/旧raw | 20 | 20/20 | 20/20 | 20/20 | 12/20 | 60.0% | 0/20 |
| policy_select / 简化 | 20 | 20/20 | 20/20 | 20/20 | 15/20 | 75.0% | 0/20 |
| policy_select / 简化+完整Schema | 20 | 20/20 | 20/20 | 20/20 | 14/20 | 70.0% | 0/20 |

Goal原提示40条都是合法JSON，主要错误是39条把Schema本身当作答案输出；减负后39/40可通过合同，但没有一条正确保留全部目标、限制和检查项。因此不能把Goal失败主要解释为JSON语法问题。约束解码在有限预算内也不能保证完整JSON：B的3条仍length，不是解析器修复后成功。

### Goal字段、限制与无关值

| 条件 | title | objective完整atoms | criteria完整atoms | 限制保留 | 否定/独占范围保留 | 原字段之外的key病例 | unsupported值病例 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 原提示 | 1/40 | 0/40 | 0/40 | 0/70 (0.0%) | 0/42 (0.0%) | 39/40 | 39/40 |
| 简化 | 23/40 | 0/40 | 4/40 | 26/70 (37.1%) | 9/42 (21.4%) | 0/40 | 39/40 |
| 简化+完整Schema | 25/40 | 0/40 | 5/40 | 25/70 (35.7%) | 7/42 (16.7%) | 0/40 | 37/40 |

A有26/40把独立示例的“列出反应式”写进实际success_criteria，B为18/40；这些40个原输入均未要求这个产物。A另有10条照搬“不讨论呼吸作用”、24条出现“周末前完成”（是否为无依据期限需结合原输入；计数不是全部幻觉数）。示例复制是明确新增干扰，不能把本轮称为0.8B的最佳可能语义上限。

例如TRB0-0085输入要求“只学第一章、不用其他教材、列出概念之间的联系”，A抓对检查项，却加入“不讨论呼吸作用；周末前完成”，丢掉不用其他教材。TRB0-0101输入限制“不要自己编题”，A抓对title/检查项，却替换为“不讨论其他内容；周末前完成”。A仅4条检查项完整匹配，逐条复核仍有明确限制丢失/添加；完整0/40不能只解释为同义改写受罚。

### Understanding字段与错误引用

| 条件 | action | intent | dimensions | entity_spans | reference_id |
|---|---:|---:|---:|---:|---:|---:|
| 原提示 | 0/41 | 1/41 | 6/41 | 0/41 | 0/41 |
| 简化 | 0/41 | 12/41 | 7/41 | 0/41 | 41/41 |
| 简化+JSON语法 | 0/41 | 11/41 | 6/41 | 0/41 | 0/41 |

A五字段micro为29.27%，其中41个reference_id成功只是正确留空；去掉这个全部相同字段，其他四字段仅19/164=11.59%。B-json-only五字段micro为8.29%；其他四字段17/164=10.37%。不能用留空成功证明历史指代能力。

A的41条全部选择clarify，实体位置从未匹配；样例出现start=end=0。B-json-only全部选择clarify并引用r0，样例entity_spans为空。原题明确提到当前对象且没有允许引用/澄清的gate；r0虽是既有候选，却不是本题合法引用。这是错误对象/动作使用，不是新造候选。

A有41/41 unsupported值/无效span flag；B-json-only有20/41 enum/type/grounding flag，其余错误引用不计“发明值”，但仍全部合同拒绝。两组没有额外字段。完整Schema Understanding后端不可用，不能宣称已经测得“全部Schema错误消除后”的Understanding上限。

### Policy小样本：有效说明能激活部分语义，但槽位偏好还在

原20题12/20；A 15/20；B 14/20。A只新增TRB0-0005、TRB0-0009、TRB0-0049三题正确，没有丢失旧正确题；B新增0005、0049。三题分别涉及改口、先查记录不凭印象、真实查记录而非通用技巧。A仍17/20选择a1，B为18/20；该20题始终选a1的基线是12/20。

因此0.8B有部分可响应明确提示的选择能力，不能称完全不理解；这里的主要变化来自更明确的任务/工具说明及去Schema提示，不能单独归因于JSON格式。定向样本、暴露状态和family相似性使15/20不能替代原40/80或充当训练验收。

## Probe C：40个原Policy错误审计

主类互斥、合计40。附加线索可重叠；识别出否定或引用语句不等于证明模型因该机制而错。由于原输出只有action_id，40例的认知根因均标root_cause_needs_review，不能可靠区分用户意图理解与候选工具描述理解。

| 类别 | 确认可观察主类 | 附加表面线索 | needs_review说明 |
|---|---:|---:|---|
| user intent misunderstanding | 0 | 0 | 40例认知根因待复核，0表示未可靠确认该原因 |
| tool vs direct-answer boundary | 28 | 1 | 按原gold比较可观察动作差异 |
| multi-intent priority/order | 11 | 0 | 按原gold比较可观察动作差异 |
| negation/correction failure | 0 | 21 | 线索归类，不能独立证明因果 |
| candidate-description misunderstanding | 0 | 0 | 40例认知根因待复核，0表示未可靠确认该原因 |
| reference/context misunderstanding | 0 | 6 | 线索归类，不能独立证明因果 |
| ambiguous / potentially disputable gold | 1 | 0 | TRB0-0066原文含相反顺序，保留gold待复核 |
| other | 0 | 0 | 按原gold比较可观察动作差异 |

无法区分认知根因时，`user intent misunderstanding` 与 `candidate-description misunderstanding` 均有 **40例 needs_review**，涉及同一组病例：TRB0-0001, TRB0-0003, TRB0-0005, TRB0-0007, TRB0-0009, TRB0-0011, TRB0-0013, TRB0-0015, TRB0-0017, TRB0-0019, TRB0-0021, TRB0-0023, TRB0-0027, TRB0-0029, TRB0-0031, TRB0-0035, TRB0-0037, TRB0-0039, TRB0-0041, TRB0-0043, TRB0-0045, TRB0-0047, TRB0-0049, TRB0-0051, TRB0-0053, TRB0-0055, TRB0-0057, TRB0-0059, TRB0-0061, TRB0-0063, TRB0-0065, TRB0-0066, TRB0-0068, TRB0-0069, TRB0-0072, TRB0-0073, TRB0-0074, TRB0-0075, TRB0-0077, TRB0-0079。这不是两类各有40个已证实错误。

各类case IDs：
- **user intent misunderstanding**：主类 无可靠确认；附加线索 无。
- **tool vs direct-answer boundary**：主类 TRB0-0001, TRB0-0003, TRB0-0005, TRB0-0007, TRB0-0009, TRB0-0011, TRB0-0013, TRB0-0015, TRB0-0017, TRB0-0019, TRB0-0021, TRB0-0023, TRB0-0027, TRB0-0029, TRB0-0031, TRB0-0035, TRB0-0037, TRB0-0039, TRB0-0041, TRB0-0043, TRB0-0045, TRB0-0047, TRB0-0049, TRB0-0051, TRB0-0053, TRB0-0055, TRB0-0057, TRB0-0059；附加线索 TRB0-0074。
- **multi-intent priority/order**：主类 TRB0-0061, TRB0-0063, TRB0-0065, TRB0-0068, TRB0-0069, TRB0-0072, TRB0-0073, TRB0-0074, TRB0-0075, TRB0-0077, TRB0-0079；附加线索 无。
- **negation/correction failure**：主类 无可靠确认；附加线索 TRB0-0005, TRB0-0007, TRB0-0009, TRB0-0017, TRB0-0021, TRB0-0029, TRB0-0037, TRB0-0039, TRB0-0041, TRB0-0045, TRB0-0049, TRB0-0051, TRB0-0053, TRB0-0055, TRB0-0057, TRB0-0069, TRB0-0072, TRB0-0073, TRB0-0074, TRB0-0075, TRB0-0079。
- **candidate-description misunderstanding**：主类 无可靠确认；附加线索 无。
- **reference/context misunderstanding**：主类 无可靠确认；附加线索 TRB0-0017, TRB0-0037, TRB0-0053, TRB0-0055, TRB0-0068, TRB0-0077。
- **ambiguous / potentially disputable gold**：主类 TRB0-0066；附加线索 无。
- **other**：主类 无可靠确认；附加线索 无。

原始输入、候选、gold、模型选择和每例理由全部在文末附录；机器记录见本报告的证据链接。TRB0-0066的gold按末句“先调题目列表”选择习题，是可解释的标注；将它标needs_review只表示前半句和末句有顺序冲突，不声明gold错误，也不从正式分母中删除。

### Qwen / Rule错误互补性

| 比较 | count / 80 |
|---|---:|
| overlap_correct | 0/80 |
| Qwen-only_correct | 40/80 |
| Rule-only_correct | 39/80 |
| both_wrong | 1/80 |

Rule来源是原冻结curator中的rule_prediction，本轮未执行已变化的生产Runtime规则。Rule原80题全部a0；Qwen为a1×79、a2×1；gold为a0×39、a1×41。两者同对0、独有对79、同错TRB0-0074。
这个分布强烈支持“不同候选位置先验造成表面互补”，尚未证明两者各自有互补的语义专长。Policy候选顺序不是随机重新排列，本轮也没有做候选重排探针；因此这里是基于观测的诊断推论，因果结论仍需其他独立实验。

## Probe D：只扩大length样本的预算

| 来源条件 | length样本 | 384预算JSON / 完整匹配 | 768预算JSON / 完整匹配 | 768仍length |
|---|---:|---:|---:|---:|
| original | 11 | 0 / 0 | 0 / 0 | 11/11 |
| A | 1 | 0 / 0 | 0 / 0 | 1/1 |
| B | 3 | 0 / 0 | 0 / 0 | 3/3 |

原11条均为Understanding：8 primary、3 secondary；secondary包含原locked intent冲突样本，不混入primary语义成绩。A新增length为Goal TRB0-0106；B新增Goal length为0082、0105、0106；B-json-only无length。所有正常stop病例均未扩大预算。
预算翻倍没有恢复任何完整输出。原Understanding在768预算下继续生成重复/越界实体数组或错误dimensions类型；Goal继续在objective中重复“不讨论其他采样方法”等限制。观测更符合“偏离合同后持续展开/重复”，而非短一点就可正确收尾的答案。不能证明任何更大预算都无用，但384→768没有支持预算不足是当前低分主因。

## 职责与训练价值判断

| 职责 | 本轮依据 | 当前判断 |
|---|---|---|
| Policy selection | 明确说明后20题60%→75%；原80题50%，a1偏好仍明显 | 四者中最值得有限研究；尚不可靠，也未达到稳定prior证据 |
| semantic extraction | Goal核心title 57.5%–62.5%；Understanding intent约27%–29%、dimension约15%–17%；实体/动作仍0 | 有零散信息提取；不足以承担五字段理解或可信限制抽取 |
| Goal transformation | 完整0/40；限制字面保留约36%–37%，否定/独占约17%–21%；复制无关产物 | 当前不适合整理可信Goal契约 |
| reference/context resolution | 原secondary旧resolver失败；新primary引用只应留空，无正向历史指代选择样本；JSON-only反而误用r0 | 没有支持接管的证据，也不能从本轮推断所有历史指代能力 |

当前不支持把大量U解释成“纯格式损失、训练一下JSON即可解决”。原Schema提示确实造成可观测的复制/结构负担；去掉它后，输出形状改善与语义交付改善分离。Goal示例污染、条件丢失、Understanding错误clarify/引用和Policy槽位偏好都需要实质验证。
证据不足以启动面向全部Runtime职责的LoRA/SFT；如果后续仅研究Policy训练，也需要打破候选槽位偏好、用独立family/未曝光数据检验否定/纠正/顺序能力，并单独确认训练收益。这些只是本次结论的条件，不是新增实施任务。

## 证据与完整性

- [诊断配置/预定病例/提示词版本](../validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/experiment.json)
- [A原始requests](../validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/arm-A/requests.jsonl)、[A raw](../validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/arm-A/outputs.jsonl)
- [B原生解码与uniqueItems错误记录](../validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/arm-B/run.json)、[B raw](../validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/arm-B/outputs.jsonl)
- [Understanding JSON-only raw](../validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/arm-B_json/outputs.jsonl)
- [预算选择规则与条件](../validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/budget-selection.json)、[D raw](../validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/arm-D/outputs.jsonl)
- [逐字段诊断指标](../validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/diagnostic-metrics.json)、[40例Policy机器审计](../validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/probe-C-audit.json)
- [baseline未改变校验](../validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/baseline-integrity.json)
- 记录类型全部diagnostic_only；原正式成绩仍是primary 40/161、semantic_all 40/200。无best-of、修复后official重评分、LoRA、dashboard、生产接入或Harness接口扩建。

## 附录：40个原Policy错误的逐例依据

每例input保持原字段；candidates即input.admissible_actions，下面直接包含在原input中。主类、附加线索、needs_review和理由均可追溯。认知根因的needs_review不因可观察动作主类明确而解除。

### 1. TRB0-0001 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "昨晚学着学着睡着了，帮我看看最近学习进度到哪了。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "昨晚学着学着睡着了，帮我看看最近学习进度到哪了。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 2. TRB0-0003 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "最近学习记录我找不着了，你帮我调出来瞅瞅。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "最近学习记录我找不着了，你帮我调出来瞅瞅。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 3. TRB0-0005 — tool vs direct-answer boundary

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "说反了，不是让你讲学习方法，是让你查最近学习活动。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "说反了，不是让你讲学习方法，是让你查最近学习活动。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 4. TRB0-0007 — tool vs direct-answer boundary

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "地铁太吵打字乱，最近那个学习进度，查一下，别急着评价。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "地铁太吵打字乱，最近那个学习进度，查一下，别急着评价。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 5. TRB0-0009 — tool vs direct-answer boundary

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "我想知道掌握得咋样，先看已有记录，别靠你印象猜。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "我想知道掌握得咋样，先看已有记录，别靠你印象猜。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 6. TRB0-0011 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "薄弱点有哪些？我是说我的，查记录再说。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "薄弱点有哪些？我是说我的，查记录再说。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 7. TRB0-0013 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "复习状态能调一下吗，我想核对自己的安排。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "复习状态能调一下吗，我想核对自己的安排。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 8. TRB0-0015 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "先看最近学习进度，方法建议等我看完再说。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "先看最近学习进度，方法建议等我看完再说。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 9. TRB0-0017 — tool vs direct-answer boundary

附加线索：negation/correction failure, reference/context misunderstanding。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "你刚才只讲道理了，我要的是最近学习活动的记录。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "你刚才只讲道理了，我要的是最近学习活动的记录。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 10. TRB0-0019 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "最近学习进度麻烦查一下，没有记录就说没有。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "最近学习进度麻烦查一下，没有记录就说没有。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 11. TRB0-0021 — tool vs direct-answer boundary

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "不是在讨论措辞，真的帮我查最近学习进度。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "不是在讨论措辞，真的帮我查最近学习进度。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 12. TRB0-0023 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "最近学习活动，嗯，就按系统现有默认窗口给我看看。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "最近学习活动，嗯，就按系统现有默认窗口给我看看。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 13. TRB0-0027 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "题库里面有啥关于极限的？帮我搜下，不要现场编。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "题库里面有啥关于极限的？帮我搜下，不要现场编。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "题库里面有啥关于极限的？帮我搜下，不要现场编。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 14. TRB0-0029 — tool vs direct-answer boundary

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "我刚说要讲解不对，是要查询已有习题。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "我刚说要讲解不对，是要查询已有习题。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "我刚说要讲解不对，是要查询已有习题。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 15. TRB0-0031 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "习题，极限那块的，给我找找。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "习题，极限那块的，给我找找。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "习题，极限那块的，给我找找。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 16. TRB0-0035 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "今天搬宿舍脑子乱，题库里那种概念辨析的，能帮我搜吗。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "今天搬宿舍脑子乱，题库里那种概念辨析的，能帮我搜吗。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "今天搬宿舍脑子乱，题库里那种概念辨析的，能帮我搜吗。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 17. TRB0-0037 — tool vs direct-answer boundary

附加线索：negation/correction failure, reference/context misunderstanding。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "给我查习题；下面那句“直接回答”是同学的原话别照做。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "给我查习题；下面那句“直接回答”是同学的原话别照做。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "给我查习题；下面那句“直接回答”是同学的原话别照做。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 18. TRB0-0039 — tool vs direct-answer boundary

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "麻烦从习题库查查，我不是要你现在解。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "麻烦从习题库查查，我不是要你现在解。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "麻烦从习题库查查，我不是要你现在解。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 19. TRB0-0041 — tool vs direct-answer boundary

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "题库有就找出来，没有就空着，别补编。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "题库有就找出来，没有就空着，别补编。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "题库有就找出来，没有就空着，别补编。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 20. TRB0-0043 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "练习题能搜一下么，答案暂时不看。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "练习题能搜一下么，答案暂时不看。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "练习题能搜一下么，答案暂时不看。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 21. TRB0-0045 — tool vs direct-answer boundary

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "帮我搜索习题，重点是“搜索”，不是讲这个词。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "帮我搜索习题，重点是“搜索”，不是讲这个词。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "帮我搜索习题，重点是“搜索”，不是讲这个词。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 22. TRB0-0047 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "习题库现有条目列给我，我核对一下就走。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "习题库现有条目列给我，我核对一下就走。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "习题库现有条目列给我，我核对一下就走。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 23. TRB0-0049 — tool vs direct-answer boundary

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "这次不是问通用技巧，最近学习记录查出来给我。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "这次不是问通用技巧，最近学习记录查出来给我。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 24. TRB0-0051 — tool vs direct-answer boundary

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "别讲最近学习进度这个词了，查我的记录。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "别讲最近学习进度这个词了，查我的记录。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 25. TRB0-0053 — tool vs direct-answer boundary

附加线索：negation/correction failure, reference/context misunderstanding。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "刚才复习方法先放下，现在查习题库现成题。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "刚才复习方法先放下，现在查习题库现成题。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "刚才复习方法先放下，现在查习题库现成题。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 26. TRB0-0055 — tool vs direct-answer boundary

附加线索：negation/correction failure, reference/context misunderstanding。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "我要执行的请求是查询习题，不是在念标题。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "我要执行的请求是查询习题，不是在念标题。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "我要执行的请求是查询习题，不是在念标题。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 27. TRB0-0057 — tool vs direct-answer boundary

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "最近学习活动给我——不是预测，是查现有的。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "最近学习活动给我——不是预测，是查现有的。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 28. TRB0-0059 — tool vs direct-answer boundary

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 generate_answer。实际请求读取已有数据，模型转为直接回答。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "习题库可以查吗？可以的话现在帮我查。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a1",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "习题库可以查吗？可以的话现在帮我查。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "习题库可以查吗？可以的话现在帮我查。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 29. TRB0-0061 — multi-intent priority/order

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 get_recent_progress。题目明确给出先后/优先关系，所选动作与冻结 gold 的首步不同。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "先查习题库，再看最近学习进度。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a1",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a2",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "先查习题库，再看最近学习进度。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "先查习题库，再看最近学习进度。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 30. TRB0-0063 — multi-intent priority/order

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 get_recent_progress。题目明确给出先后/优先关系，所选动作与冻结 gold 的首步不同。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "题库和最近学习活动都要，题库优先。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a1",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a2",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "题库和最近学习活动都要，题库优先。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "题库和最近学习活动都要，题库优先。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 31. TRB0-0065 — multi-intent priority/order

附加线索：无可靠线索。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 search_exercises。题目明确给出先后/优先关系，所选动作与冻结 gold 的首步不同。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "我想看掌握情况再找练习题，先调掌握记录。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a1",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a2",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "我想看掌握情况再找练习题，先调掌握记录。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "我想看掌握情况再找练习题，先调掌握记录。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 32. TRB0-0066 — ambiguous / potentially disputable gold

附加线索：无可靠线索。gold/歧义复核：True；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 get_recent_progress。前半句“看掌握情况再找练习题”和末句“先调题目列表”方向不同；gold采用末句，需要人工核对纠正优先约定，不改gold。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "我想看掌握情况再找练习题，先调题目列表。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a1",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a2",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "我想看掌握情况再找练习题，先调题目列表。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "我想看掌握情况再找练习题，先调题目列表。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 33. TRB0-0068 — multi-intent priority/order

附加线索：reference/context misunderstanding。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 get_recent_progress。题目明确给出先后/优先关系，所选动作与冻结 gold 的首步不同。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "最近学习进度、习题这两件事，先办后一个。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a1",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a2",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "最近学习进度、习题这两件事，先办后一个。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "最近学习进度、习题这两件事，先办后一个。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 34. TRB0-0069 — multi-intent priority/order

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 search_exercises。题目明确给出先后/优先关系，所选动作与冻结 gold 的首步不同。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "题库先别动，先把薄弱记录查出来，之后再查题。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a1",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a2",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "题库先别动，先把薄弱记录查出来，之后再查题。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "题库先别动，先把薄弱记录查出来，之后再查题。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 35. TRB0-0072 — multi-intent priority/order

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 get_recent_progress。题目明确给出先后/优先关系，所选动作与冻结 gold 的首步不同。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "帮我查练习题和最近学习进度；我改口，先查题。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a1",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a2",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "帮我查练习题和最近学习进度；我改口，先查题。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "帮我查练习题和最近学习进度；我改口，先查题。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 36. TRB0-0073 — multi-intent priority/order

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 get_recent_progress。题目明确给出先后/优先关系，所选动作与冻结 gold 的首步不同。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "习题库查完我才看复习状态，顺序别弄反。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a1",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a2",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "习题库查完我才看复习状态，顺序别弄反。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "习题库查完我才看复习状态，顺序别弄反。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 37. TRB0-0074 — multi-intent priority/order

附加线索：negation/correction failure, tool vs direct-answer boundary。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 generate_answer。题目明确给出先后/优先关系，所选动作与冻结 gold 的首步不同。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "复习状态查完我才看习题库，顺序别弄反。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a1",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a2",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "复习状态查完我才看习题库，顺序别弄反。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "复习状态查完我才看习题库，顺序别弄反。"
  },
  "gold": {
    "action_id": "a1"
  },
  "model_choice": {
    "action_id": "a2"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 38. TRB0-0075 — multi-intent priority/order

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 search_exercises。题目明确给出先后/优先关系，所选动作与冻结 gold 的首步不同。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "今天只先查掌握记录；练习题等下一步。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a1",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a2",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "今天只先查掌握记录；练习题等下一步。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "今天只先查掌握记录；练习题等下一步。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 39. TRB0-0077 — multi-intent priority/order

附加线索：reference/context misunderstanding。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 search_exercises；模型选择 get_recent_progress。题目明确给出先后/优先关系，所选动作与冻结 gold 的首步不同。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "查最近学习活动以及题库，后者先来。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a1",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a2",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "查最近学习活动以及题库，后者先来。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "查最近学习活动以及题库，后者先来。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

### 40. TRB0-0079 — multi-intent priority/order

附加线索：negation/correction failure。gold/歧义复核：False；认知根因复核：True。
gold 的下一步是 get_recent_progress；模型选择 search_exercises。题目明确给出先后/优先关系，所选动作与冻结 gold 的首步不同。

```json
{
  "input": {
    "admissible_actions": [
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "days": 7,
            "limit": 12,
            "subject": "数学"
          },
          "tool_id": "get_recent_progress"
        },
        "id": "a0",
        "kind": "call_tool"
      },
      {
        "args": {
          "input": {
            "book_name": "fixture",
            "chapter": "",
            "limit": 8,
            "query": "练习题和薄弱记录都想看，但先别查题，先看记录。",
            "status": "",
            "subject": "数学",
            "tag": ""
          },
          "tool_id": "search_exercises"
        },
        "id": "a1",
        "kind": "call_tool"
      },
      {
        "args": {},
        "id": "a2",
        "kind": "generate_answer"
      }
    ],
    "context": {
      "constraints": {
        "answer_mode": "global_general",
        "book_name": "fixture",
        "subject": "数学"
      },
      "goal": null,
      "resolved_query": "练习题和薄弱记录都想看，但先别查题，先看记录。"
    },
    "missing_inputs": [],
    "previous_result": null,
    "request": "练习题和薄弱记录都想看，但先别查题，先看记录。"
  },
  "gold": {
    "action_id": "a0"
  },
  "model_choice": {
    "action_id": "a1"
  },
  "rule_choice": {
    "action_id": "a0"
  }
}
```

