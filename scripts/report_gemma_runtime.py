#!/usr/bin/env python3
"""Read-only report from completed Gemma run; never edits baseline artifacts."""
import sys
import collections
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from screen_gemma_runtime import read, save, lines, integrity
from evaluation.runtime_benchmark.scoring import Benchmark
from evaluation.runtime_benchmark.diagnostics import performance
from runtime_08b_probe_analysis import field_analysis, summarize

out=Path(sys.argv[1]).resolve();base=ROOT/'docs/validation/runtime-benchmark-v0.1'
b=Benchmark();m=read(out/'permutation-metrics.json');q=read(base/'policy-permutation-20261006/metrics.json')
state=read(out/'run.json');assert state['status']=='complete'
assert integrity()==read(out/'protected-before.json')
full=(out/'semantic_all/diagnostics.json').exists()
model=read(out/'permutation/run.json')['model'];audit=read(out/'model-audit.json')
pct=lambda x:f'{x:.2%}' if x is not None else '—'
frac=lambda a,n:f'{a}/{n} ({pct(a/n)})'
text=['# Gemma3-1B-IT-8bit-Screening','',
'2026-10-06（Asia/Shanghai）。本轮是已曝光、author-frozen 内部 foundation 横向筛选；不是 held-out 准确率或生产验收。没有训练、LoRA、prompt 调参或修改 Runtime。','',
'## 模型身份与执行合同','',
f'- exact repo：`{model["model_id"]}`，revision `{audit["revision"]}`。来源转换声明：`google/gemma-3-1b-it`（IT，非 Base）。[仓库](https://huggingface.co/mlx-community/gemma-3-1b-it-8bit)。',
f'- 单一权重缓存：`{model["local_path"]}`。snapshot 链接到 HF blobs；未另存 LM Studio 或项目权重副本。API gated=false，现有 credential=false，下载成功，没有绕过权限。',
f'- architecture `{model["architectures"]}`，model_type `{model["model_type"]}`；hidden_size 1152 / layers 26 / vocab 262144。名义 1B；按 tensor 形状重建唯一参数 {audit["reconstructed_unique_parameters"]:,}。转换导出同时保存相同 embedding/lm_head，物理 tensor 参数 {audit["reconstructed_parameter_count"]:,}；三个对应 weight/scales/biases 的 SHA256 均相同，详见 model-audit.json。未改权重或去重加载。',
f'- quantization `{model["quantization"]}`；实际加载 {model["verified_quantized_modules"]} 个量化模块，全部 bits=8/group_size=64。weight dtypes `{model["weight_dtypes"]}`；磁盘 tensor dtypes `{audit["tensor_dtypes"]}`。',
f'- 库：`{model["libraries"]}`。评分使用 venv310 / Python 3.10.21；推理复用既有 LM Studio Python 3.11.9，不安装依赖。',
f'- 原生 tokenizer/chat template 完整保存于 permutation/run.json，SHA256 `{model["chat_template_sha256"]}`；system 内容由原生模板并入首个 user turn，messages 文本逐项保持旧 screening 内容。thinking=false = not_applicable。',
'- 原转换仓库未提供 generation_config，MLX 只识别 `<eos>`，未识别 IT 原生 `<end_of_turn>`。发现后停止原无效尝试，raw 全保留在相邻 gemma3-1b-it-8bit-20261006 目录；其结果不作为有效模型评分。仅在 adapter/tokenizer 层注册停止符，未截取或修复 raw。[Gemma 3 技术报告](https://storage.googleapis.com/deepmind-media/gemma/Gemma3Report.pdf)说明 IT 使用 end_of_turn 结束生成。有效 run EOS IDs `[1,106]`。',
'- greedy / temperature=0 / batch=1 / seed=0，无 retry、self-correction、best-of 或 constrained decoding。Policy=128、Goal=384、Understanding=384、Reference=256 tokens，与基线一致。',
'- permutation 直接逐条核对并复用旧 A/B/C jobs，使用已有简化诊断提示；完整 semantic set 使用原 frozen wire + task + schema prompt。因此下文两类结果分开比较。',
'- ModelAdapter 仅泛化架构校验、原生停止符和可审计模板元数据；未修改 frozen benchmark/gold/scorer/task definitions/Runtime/官方 Qwen baseline。32 项 Harness 测试通过（含 Gemma 错规模/4bit 拒绝检查）。','',
'## Smoke','',
'每个任务 1 条，共 Policy、Goal、Understanding 三条；操作 status=ok、raw 已保存、scorer 正常返回；严格输出失败原样保留。Smoke 只验证链路，未据此修改正式提示。Smoke 使用三条已曝光 benchmark 示例，后续正式首答独立生成；不把 smoke 加入正式分母。','',
'## Policy permutation：240 次','',
'A=原顺序；B=仅反转候选顺序；C=仅轮换候选 ID（双候选互换，三候选前移一格）；候选内容、题意、范围保持不变。每变体 N=80；58 双候选、22 三候选。语义身份为原候选 ID + 原 kind/args，非法输出没有可用选择，分母仍保留。','',
'| 变体 | Gemma semantic accuracy | Qwen semantic accuracy | Gemma 合同合法 |',
'|---|---:|---:|---:|']
for a in 'ABC':
    s=m['summaries'][a];old=q['summaries'][a];text.append(f'| {a} | {frac(s["semantic_correct"],80)} | {frac(old["semantic_correct"],80)} | {s["contract_valid"]}/80 |')
text+=['','| Pair | Gemma 相同 semantic choice | Qwen 相同 semantic choice |','|---|---:|---:|']
for a,z in [('A','B'),('A','C'),('B','C')]:
    text.append(f'| {a}/{z} | {frac(m["pairs"][a+z],80)} | {frac(q["pairs"][a+"-"+z]["counts"]["same_semantic_action"],80)} |')
text+=['',f'三变体同一语义候选：Gemma {frac(m["three_variant_semantic_consistency"],80)}，Qwen {len(q["all_three_semantic_stable_ids"])}/80；三变体全部正确：Gemma {frac(m["three_variant_correct"],80)}，Qwen {len(q["all_three_correct_ids"])}/80。',
f'双候选稳定语义选择：Gemma {frac(m["binary_stable"],m["binary_N"])}，Qwen 0/58。一致但错误也计入稳定，不能把 consistency 当 accuracy。','',
'| 变体 | 第1候选 | 第2候选 | 第3候选 | a0 | a1 | a2 |','|---|---:|---:|---:|---:|---:|---:|']
for a in 'ABC':
    s=m['summaries'][a];text.append('| '+a+' | '+' | '.join(frac(s['position_preference'][str(i)],80) for i in (1,2,3))+' | '+' | '.join(frac(s['id_preference'][i],80) for i in ('a0','a1','a2'))+' |')
text+=['','第三候选率以全部80例为分母（只有22例具第三候选）；非法输出不计任何位置/ID。position 与 ID 关联由 B/C 分离，不能仅凭 A 的分布归因。','',
'| Stratum | 变体 | Gemma 正确 | Qwen 正确 |','|---|---|---:|---:|']
for g in ('tool_vs_answer','multi_intent_order'):
    for a in 'ABC':
        s=m['summaries'][a]['strata'][g];old=q['summaries'][a]['strata'][g];text.append(f'| {g} | {a} | {frac(s["correct"],s["N"])} | {frac(old["correct"],old["N"])} |')
text+=['','这些 strata 使用旧 probe 的标签口径：非 multi_intent_order 的60例归 tool_vs_answer，20例归 multi-intent。','',
f'预先锁定扩展门槛：任一 arm 在全部80例中 ≥95% 固定某位置或 ID 则停止扩大；本轮 catastrophic_shortcut={m["catastrophic_shortcut"]}，决定 `{state["permutation_gate"]}`。此门槛是成本控制门槛，不是 semantic prior 合格线。']
rec=read(out/'permutation-recovery-diagnostics.json')
text+=['','### 原保守 parser 的额外诊断（不替代 strict）','',
'为了区分围栏失败和选择语义，沿用既有 semantic-recoverability/v0.1 的唯一 outer payload 提取，不修 JSON、不选择多答案。官方分数与 results 的 strict 均保持原样。','',
'| Arm | 可判定选择 | 诊断语义正确 | 第1/2/3位置 | a0/a1/a2 |','|---|---:|---:|---|---|']
for a in 'ABC':
    r=rec['arms'][a];text.append(f'| {a} | {r["valid"]}/80 | {r["correct"]}/80 | {r["positions"]} | {r["ids"]} |')
text += ['',f'诊断三变体同语义 {rec["three_stable"]}/80（Qwen15/80），三变体全正确 {rec["all_correct"]}/80（Qwen8/80），双候选稳定 {rec["binary_stable"]}/58（Qwen0/58）。恢复后 A 的 a0 选择为75/76个可判定答案：明显 ID偏好；B仍64/80，C47/79。Gemma没有稳定表现出摆脱 shortcut 的整体优势。',
'严格有效选择中 a0 的条件比例 A=36/37、B=43/47、C=34/45；全80分母的低位置率不能掩盖这种偏好。Gemma的模式不同于Qwen C恒选第二位，但存在首候选/低ID先验；二候选在10题稳定只证明局部进步。']
if full:
    d=read(out/'semantic_all/diagnostics.json');qd=read(base/'p3-semantic-all-verified/diagnostics.json'); f=read(out/'field-diagnostics.json')
    qoutputs={x['case_id']:x for x in lines(base/'p3-semantic-all-verified/outputs.jsonl')}
    qdetails=[field_analysis(r,qoutputs[r['id']],b.scorer) for r in b.select('semantic_all') if r['task']!='reference_resolve']
    qs={t:summarize([v for v in qdetails if v['task']==t]) for t in f['by_task']}
    save(out/'qwen-comparison-diagnostics.json',qs)
    text+=['','## 完整 semantic screening','',
    'primary 161 + secondary 39，共200唯一病例；semantic_all 为严格 replay，无额外200次推理。原始结果不剥围栏、不修 JSON，使用原 frozen scorer。','',
    '| Set/task | Gemma strict | Qwen strict | 差值 pp | Gemma S/F/T/U |','|---|---:|---:|---:|---|']
    for tier in ('primary_semantic','secondary_semantic','semantic_all'):
        for task,s in [*d['screening'][tier]['by_task'].items(),('total',d['screening'][tier])]:
            old=qd['screening'][tier] if task=='total' else qd['screening'][tier]['by_task'][task]
            text.append(f'| {tier}/{task} | {frac(s["S"],s["N"])} | {frac(old["S"],old["N"])} | {(s["official_strict_accuracy"]-old["official_strict_accuracy"])*100:+.2f} | {s["S"]}/{s["F"]}/{s["T"]}/{s["U"]} |')
    text+=['','| Task（semantic_all） | Gemma schema | contract | field micro | Qwen field micro | Unsupported 值病例 G/Q |','|---|---:|---:|---:|---:|---:|']
    for task,s in f['by_task'].items():
        old=qs[task];text.append(f'| {task} | {s["schema_valid"]}/{s["N"]} | {s["contract_valid"]}/{s["N"]} | {pct(s["field_accuracy_micro"])} | {pct(old["field_accuracy_micro"])} | {s["unsupported_value_cases"]}/{old["unsupported_value_cases"]} |')
    text+=['','| Task/field | Gemma 正确 | Qwen 正确 |','|---|---:|---:|']
    for task,s in f['by_task'].items():
        for key,v in s['fields'].items():
            old=qs[task]['fields'][key];text.append(f'| {task}/{key} | {v["correct"]}/{v["N"]} | {old["correct"]}/{old["N"]} |')
    s=f['by_task']['goal_summary'];old=qs['goal_summary']
    text+=['',f'Goal negative/exclusive constraint 字面保留：Gemma {s["negative_retention"]}；Qwen {old["negative_retention"]}。全限制保留：Gemma {s["constraints_retention"]}；Qwen {old["constraints_retention"]}。',
    '字段/negative/unsupported 指标复用原 field_analysis；它只严格解析 JSON，不把围栏恢复结果混入原字段成绩。unsupported 是 enum/候选/span/原文不支持 flag，Goal 同义改写需要人工审阅，不自动等同已证实幻觉。Reference 由原 frozen scorer 与官方诊断覆盖，不套用不支持该任务的三任务字段分析。',
    f'全量 severity：Gemma `{d["screening"]["semantic_all"]["severity"]}`；Qwen `{qd["screening"]["semantic_all"]["severity"]}`。critical Gemma={d["screening"]["semantic_all"]["critical_count"]}；Qwen={qd["screening"]["semantic_all"]["critical_count"]}。taxonomy `{d["taxonomy"]}`。',
    'S/F/T/U、strict/exact/recoverable、分 split、失败原文与来源分别保留于 semantic_all/diagnostics.json、official-report.json、failures.jsonl；恢复诊断不会替代 strict 成绩。']
else:
    text+=['','## 完整 screening 未运行','', 'Policy 已触发近似固定位置/ID 门槛，停止扩大实验。Goal/Understanding 只有 smoke，不能据此报告相对 Qwen 的完整准确率或训练 foundation 优势。']
if full:
    fr=read(out/'field-recovery-diagnostics.json')
    text += ['','### 原保守提取后的字段诊断（非 official）','',
    '复用同一个 field_analysis，输入为既有保守 parser 唯一 payload；不更改官方 strict/失败原文。','',
    '| Task | Gemma 合同合法 | Gemma完整匹配 | Qwen完整匹配 | 字段micro G/Q | Unsupported病例 G/Q |','|---|---:|---:|---:|---:|---:|']
    for t,v in fr['gemma']['by_task'].items():
        ov=fr['qwen']['by_task'][t]
        text.append(f'| {t} | {v["contract_valid"]}/{v["N"]} | {v["complete_semantic_match"]}/{v["N"]} | {ov["complete_semantic_match"]}/{ov["N"]} | {pct(v["field_accuracy_micro"])}/{pct(ov["field_accuracy_micro"])} | {v["unsupported_value_cases"]}/{ov["unsupported_value_cases"]} |')
    text += ['','逐字段诊断：','']
    for t,v in fr['gemma']['by_task'].items():
        text.append(f'- {t}: Gemma {v["fields"]}; Qwen {fr["qwen"]["by_task"][t]["fields"]}')
    v=fr['gemma']['by_task']['goal_summary'];ov=fr['qwen']['by_task']['goal_summary']
    text += ['',f'保守提取 Goal negative/exclusive retention Gemma {v["negative_retention"]}；Qwen {ov["negative_retention"]}。全限制：Gemma {v["constraints_retention"]}；Qwen {ov["constraints_retention"]}。这些是原文atom字面口径，不冒充语义幻觉人工金标。']
text+=['','## 端侧成本','',
'单模型 request wall time 包含模板/tokenization、prefill、生成及 MLX synchronize；不是 decode-only tok/s。排除 smoke，无跨题 KV 复用。RSS/MLX peak 含加载，二者不可相加。Gemma permutation 未另做 synthetic warmup，Qwen permutation 有一次；完整 semantic 两者都使用原 Harness warmup，因此正式200例性能口径更可比。','',
'| 口径 | Gemma | Qwen |','|---|---:|---:|']
qp=performance([r for a in 'ABC' for r in lines(base/'policy-permutation-20261006'/f'arm-{a}/outputs.jsonl')])
gp=m['performance']
for key in ('p50_ms','p95_ms','generated_tokens_per_request_second'):
    text.append(f'| permutation {key} | {gp[key]:.3f} | {qp[key]:.3f} |')
grun=read(out/'permutation/run.json');qrun=read(base/'policy-permutation-20261006/run.json')
text.append(f'| permutation load ms | {grun["model"]["load_ms"]:.3f} | {qrun["model"]["load_ms"]:.3f} |')
for k in ('peak_process_rss','peak_mlx_allocator'):
    gb=grun['memory'][k]['bytes'];qb=qrun['memory'][k]['bytes'];text.append(f'| permutation {k} MiB | {gb/2**20:.2f} | {qb/2**20:.2f} |')
if full:
    gd=d['performance'];od=qd['performance']
    for key in ('p50_ms','p95_ms','generated_tokens_per_request_second'):
        text.append(f'| semantic_all {key} | {gd[key]:.3f} | {od[key]:.3f} |')
    gs=[read(out/(scope+'/run.json')) for scope in ('primary_semantic','secondary_semantic')]
    os=[read(base/folder/'run.json') for folder in ('p2-primary','p3-secondary')]
    text.append('| primary/secondary load ms | '+' / '.join(f'{s["model"]["load_ms"]:.3f}' for s in gs)+' | '+' / '.join(f'{s["model"]["load_ms"]:.3f}' for s in os)+' |')
    for k in ('peak_process_rss','peak_mlx_allocator'):
        text.append(f'| semantic max {k} MiB | {max(s["memory"][k]["bytes"] for s in gs)/2**20:.2f} | {max(s["memory"][k]["bytes"] for s in os)/2**20:.2f} |')
    perf={'gemma_permutation':gp,'qwen_permutation':qp,'gemma_semantic':gd,'qwen_semantic':od}
else:perf={'gemma_permutation':gp,'qwen_permutation':qp}
save(out/'performance-comparison.json',perf)
text+=['',
'设备同为 Mac17,5 / Apple A18 Pro / 8GiB；running_alone=false。两模型非交错配对，热状态/后台负载未控制，且模型 tokenizer 与输出长度不同；tok/s 和 wall latency 是实际该 workload 的成本，不是同等有效语义产出速度。',
'本轮没有运行 Electron/Chroma/embedding 共存恢复测试，也没有已批准的数值端侧 envelope；可以判断单模型是否加载/完成、量化内存增量，但不能宣称 Texa 共存 envelope 验收通过。','',
'## 直接回答','']
text = text[:text.index("## 直接回答")]
text.extend('## 完整性与产物\n\n冻结包内271个 pinned 文件及99个额外保护文件已核验，官方Qwen baseline、旧 diagnostic/permutation、除adapter外的Harness均未改变。\n\n- results.jsonl：240次permutation + 200次semantic，共440条首答；phase分离，smoke及无效adapter尝试不计入。\n- failures.jsonl：permutation strict失败及正式semantic失败，保留原raw。\n- run.json：阶段门槛、模型身份、完成状态与性能索引；各子目录run.json保存原始测量。\n- model-audit.json、permutation-metrics.json、permutation-recovery-diagnostics.json、field-diagnostics.json、field-recovery-diagnostics.json、performance-comparison.json：严格与恢复诊断分离。\n\n严格字段unsupported=0只是JSON无法解析时没有可识别值，并不等于没有幻觉；保守提取的flag提供更多证据，但仍不是人工金标。\n\n## 最后直接回答\n\n1. **Gemma是否存在明显position / ID bias？存在。** 它没有复现Qwen C恒选第二位置80/80，但保守恢复后A可判定答案75/76选择a0，B为64/80，C为47/79。bias的具体形态不同，shortcut并未可靠消失。\n2. **Permutation-invariant能力是否明显强于Qwen？没有。** strict三变体稳定10/80 vs15/80；保守恢复后16/80 vs15/80，三变体全正确9/80 vs8/80。双候选稳定10/58 vs0/58是局部改善，整体提升不足。\n3. **Policy、Goal、Understanding分别如何？** 原frozen prompt下Policy strict 0/80 vs40/80（−50pp）；Goal 0/40 vs0/40；Understanding 0/60 vs0/60（primary均0/41）。保守恢复Policy仅11/80 vs40/80（−36.25pp）。Goal字段micro 0% vs0.83%，否定限制均0/42。Understanding字段micro 17.67% vs3.67%（+14pp），其中intent27/60 vs2/60、action20/60 vs0/60，但entity_spans/reference_id均0、完整合同均0/60；有局部标签能力，不足以接管理解。\n4. **1B增量是否在可接受端侧envelope？单模型可运行，整体尚未验收。** 完整200例MLX峰值增加约413MiB，RSS峰值增加约470MiB；p50 2.637s vs0.972s（+1.665s），p95 5.565s vs7.871s（−2.306s），request-inclusive tok/s29.87 vs37.30（约−19.9%）。较低p95不等于更高有效产出，输出长度及失败形态不同；无Electron共存验收，不能正式判定Texa envelope通过。\n5. **Gemma是否比Qwen更值得成为Texa Runtime训练foundation？本轮证据不支持。** 增加内存与典型延迟后，没有获得明显更强的整体semantic invariance；ID先验、Schema复制与输入回显和完整合同失败仍突出。暂不将Gemma替换为优先foundation，也不将Qwen原baseline解释为已经可靠。Understanding局部intent/action改善可留作研究线索，不能抵消Policy/Goal及完整理解合同的缺口。本轮到此完成，不训练、不调prompt。\n'.splitlines())
(out/'Gemma3-1B-IT-8bit-Screening.md').write_text('\n'.join(text)+'\n')
state.update(experiment=read(out/'experiment.json'),model_audit='model-audit.json',permutation='permutation/run.json',performance='performance-comparison.json',report='Gemma3-1B-IT-8bit-Screening.md',results='results.jsonl',failures='failures.jsonl')
state.update(completed_requests=len(lines(out/'results.jsonl')), phase_counts={'permutation':240, 'semantic':200 if full else 0}, smoke_requests=3, loaded_model=model, download_revision=audit['revision'], config=read(out/'config.json'))
save(out/'run.json',state)
print(json.dumps({'gate':state['permutation_gate'],'stable':m['three_variant_semantic_consistency'],'binary_stable':m['binary_stable'],'full':full},indent=2))
