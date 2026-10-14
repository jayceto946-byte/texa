#!/usr/bin/env python3
"""Generate the mini report from locked selection and unmodified scorer results."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from screen_qwen3_mini import read,save,lines,check_protected,BASE
out=Path(sys.argv[1]).resolve();d=read(out/'metrics.json');g=d['qwen3_06b'];q=d['qwen35_08b_paired'];run=read(out/'run.json');model=run['model'];audit=read(out/'model-audit.json');cleanup=read(out/'gemma-cleanup.json');oldrun=read(BASE/'run.json')
assert run['status']=='complete' and run['completed_requests']==60
nprotected=check_protected(out)
pct=lambda a,n:f'{a}/{n} ({a/n:.1%})'
text=['# Qwen3-0.6B-8bit-Mini-Screening','',
'2026-10-06（Asia/Shanghai）。已完成3个smoke + 20病例×A/B/C=60次Policy首答。本轮只做轻量foundation筛选，到此停止；没有运行完整80 Policy或200 semantic，没有训练、LoRA或prompt调参。','',
'## Gemma清理与结果保留','',
f'删除前校验指定repo缓存、Gemma架构/8bit、README来源与原model-audit中的README/config/权重SHA256。仅删除 `{cleanup["cache_path"]}`；目录删除后不存在。释放allocated磁盘空间 {cleanup["released_allocated_bytes"]:,} bytes（{cleanup["released_allocated_bytes"]/2**30:.3f} GiB）。卷空闲空间变化 {cleanup["observed_volume_free_delta_bytes"]:,} bytes另列，可能受后台写入影响。',
'Gemma全部报告、raw、结果、失败、run与无效adapter尝试完整保留，旧Qwen结果未覆盖。Gemma+Qwen基线及其他Harness保护文件共175个hash前后相同。清理收据见gemma-cleanup.json。','',
'## 模型身份','',
f'- exact repo：`{audit["repo"]}`，revision `{audit["revision"]}`；[MLX仓库](https://huggingface.co/mlx-community/Qwen3-0.6B-8bit)。',
f'- local snapshot：`{audit["local_path"]}`。只保存单一HF cache snapshot/blobs，没有重复权重。',
'- 转换来源为 [Qwen/Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B)，是支持thinking/nonthinking的post-trained模型，Base是独立checkpoint。不是Base、4bit或GGUF；仓库不存在/错架构时本脚本直接拒绝，没有备选模型分支。',
f'- model_type `{model["model_type"]}` / architecture `{model["architectures"]}`；参数 {audit["parameter_count"]:,}，hidden_size=1024、layers=28、vocab=151936、intermediate_size=3072。参数口径：8bit packed U32元素×4，排除scales/biases；tie_word_embeddings=true，无另存lm_head。',
f'- quantization `{model["quantization"]}`；实际加载量化模块 {model["verified_quantized_modules"]} 个，全部bits=8/group_size=64；加载dtypes `{model["weight_dtypes"]}`，磁盘tensor类型 `{audit["weight_dtypes"]}`。',
f'- cache allocated disk {audit["allocated_disk_bytes"]:,} bytes（{audit["allocated_disk_bytes"]/2**20:.2f} MiB）；snapshot逻辑大小 {audit["snapshot_logical_bytes"]:,} bytes。',
f'- tokenizer_class `{audit["tokenizer_class"]}`；原生模板全文与hash分别见model-audit.json/run.json，chat-template SHA256 `{model["chat_template_sha256"]}`。',
f'- native enable_thinking=false，与Qwen3.5相同；EOS IDs `{model["eos_token_ids"]}`（<|im_end|>），未添加停止符、剥thinking或修复raw。system/task messages原内容不变，仅模型原生模板负责渲染。',
f'- 库 `{model["libraries"]}`；推理Python `{model["python"].splitlines()[0]}`，复用既有LM Studio环境。评分与脚本使用venv310/Python3.10.21；没有安装/更新依赖。',
'- adapter只新增Qwen3-0.6B架构校验和load_surface元数据，不fork evaluator，不修改Benchmark/gold/scorer/task definitions/Runtime。33项Harness测试通过，包括错规模/4bit拒绝检查。','',
'## 固定病例与执行边界','',
'病例在首次推理前锁定，按输入覆盖与gold平衡选择，不按旧模型正确/错误筛选。10个tool-vs-answer + 10个multi-intent；gold semantic action a0/a1各10，binary/ternary各10。它是已曝光、目的性抽样mini set，multi-intent从原80例的25%被有意提高到50%，不代表原80例总体准确率，更不是held-out测试。','',
'- tool-vs-answer：0001/0002、0005/0006、0007/0008、0029/0030、0037/0038；覆盖progress/exercise lookup、direct answer、negation、correction、noisy wording及引用指令。',
'- multi-intent：0061/0062、0067/0068、0069/0070、0071/0072、0079/0080；覆盖先后顺序、前后项引用、否定与改口。完整请求、tags、gold见selection.json。',
'- A=原layout；B=仅逆序；C=仅轮换ID。直接调用既有variants及semantic-identity映射，并与旧probe对应jobs逐条相等核验。派生评分gold只在离线内存中按映射变换，不修改冻结gold。',
'- 使用旧permutation的相同简化语义提示，128 token上限；greedy、temperature=0、batch=1、seed=0、no retry、no self-correction、no constrained decoding。每题独立KV，raw先flush再评分。',
'- Qwen3.5对照取旧240次probe中同20病例×3变体的既有首答，不重新推理。两边采用同一个未修改frozen scorer与strict parser。','',
'## Smoke：仅链路验证','',
'Policy×1、Goal×1、Understanding×1均status=ok；native template、raw保存、scorer均正常。Policy输出匹配；Goal success_criteria项类型错误；Understanding invalid_span。错误原样保存，不据此改prompt，不把smoke当Goal/Understanding质量筛选结果。完整schema prompt与permutation简化prompt是旧Harness的不同条件，不能混合成绩。','',
'## Paired Policy结果','',
'| Arm | Qwen3-0.6B semantic accuracy | Qwen3.5-0.8B same cases | Qwen3合同合法 | Qwen3.5合同合法 |','|---|---:|---:|---:|---:|']
for a in 'ABC':
    v=g['arms'][a];ov=q['arms'][a];text.append(f'| {a} | {pct(v["semantic_correct"],20)} | {pct(ov["semantic_correct"],20)} | {v["contract_valid"]}/20 | {ov["contract_valid"]}/20 |')
text+=['','60个strict输出均合法，保守恢复诊断与strict完全一致，没有围栏/JSON修复造成的隐藏提升。aggregate correct为Qwen3 30/60 vsQwen3.5 31/60；这些是20个病例的重复变体，不能当60个独立病例。','',
'| 语义指标 | Qwen3-0.6B | Qwen3.5对应病例 |','|---|---:|---:|']
for key,n in [('three_variant_consistency',20),('three_variant_all_correct',20),('binary_consistency',10)]:
    text.append(f'| {key} | {pct(g[key],n)} | {pct(q[key],n)} |')
for key in ('AB','AC','BC'):
    text.append(f'| {key} pair semantic consistency | {pct(g["pairwise_consistency"][key],20)} | {pct(q["pairwise_consistency"][key],20)} |')
text+=['',f'三候选一致性：Qwen3 {g["three_variant_consistency"]-g["binary_consistency"]}/10 vsQwen3.5 {q["three_variant_consistency"]-q["binary_consistency"]}/10。一致但错误也计consistency，all-correct单列。新模型7/20三变体一致（35%）vs8/20（40%）；all-correct5/20 vs4/20只差1例，不构成明显优势。','',
'| Model/Arm | first | second | third | a0 | a1 | a2 |','|---|---:|---:|---:|---:|---:|---:|']
for label,m in [('Qwen3',g),('Qwen3.5',q)]:
    for a in 'ABC':
        v=m['arms'][a];text.append('| '+label+'/'+a+' | '+' | '.join(pct(v['positions'][str(i)],20) for i in (1,2,3))+' | '+' | '.join(pct(v['ids'][i],20) for i in ('a0','a1','a2'))+' |')
text+=['','位置/ID比例均以20个预定病例为分母；只有10例含第三候选。原Qwen3.5 C组20/20恒选第二位置，本轮Qwen3 C位置11/6/3，确实摆脱这个特定恒选模式。但B组a0=16/20、第二位14/20，且AB仅7/20保持语义，仍有明显layout/ID敏感性，不能宣布semantic shortcut已经消失。','',
'| Group/Arm | Qwen3正确 | Qwen3.5同病例正确 |','|---|---:|---:|']
for group in ('tool_vs_answer','multi_intent_order'):
    for a in 'ABC':
        v=g['arms'][a]['strata'][group];ov=q['arms'][a]['strata'][group];text.append(f'| {group}/{a} | {pct(v["correct"],10)} | {pct(ov["correct"],10)} |')
text+=['','tool组跨变体合计18/30 vs16/30；multi-intent12/30 vs15/30。原layout multi-intent仅2/10 vs5/10。此分组内重复变体仍非独立样本。','',
'Paired gain/loss（相同病例逐条比较）：','',
'| Arm | both correct | Qwen3-only | Qwen3.5-only |','|---|---:|---:|---:|']
for a,v in d['paired_outcomes'].items():text.append(f'| {a} | {v["both_correct"]} | {v["qwen3_only"]} | {v["qwen35_only"]} |')
text+=['','## 基础端侧记录','',
'延迟对照使用完全相同60请求的旧Qwen3.5 token/time，不用其完整200例或全240例延迟替代。p50/p95为nearest-rank；包含模板/tokenization/prefill/生成/同步，tok/s为request-inclusive，不是decode-only。smoke排除。','',
'| 指标 | Qwen3-0.6B | Qwen3.5-0.8B | 变化 |','|---|---:|---:|---:|']
perf=d['performance'];gp=perf['qwen3_06b'];qp=perf['qwen35_08b_same_60_cases']
for key in ('p50_ms','p95_ms','generated_tokens_per_request_second'):
    gv=gp[key];qv=qp[key];text.append(f'| {key} | {gv:.3f} | {qv:.3f} | {(gv/qv-1):+.1%} |')
gl=model['load_ms'];ql=oldrun['model']['load_ms'];text.append(f'| model load ms | {gl:.3f} | {ql:.3f} | {(gl/ql-1):+.1%} |')
for key in ('peak_process_rss','peak_mlx_allocator'):
    gv=run['memory'][key]['bytes'];qv=oldrun['memory'][key]['bytes'];text.append(f'| {key} MiB | {gv/2**20:.2f} | {qv/2**20:.2f} | {(gv-qv)/2**20:+.2f} MiB ({(gv/qv-1):+.1%}) |')
text+=['',
'同设备Mac17,5 / Apple A18 Pro / 8GiB、相同MLX版本。load来自既有原probe run，peak是进程生命周期：本轮60次vs旧240次，旧Qwen3.5有一次synthetic warmup，本轮没有额外warmup；两者非交错同期配对，running_alone=false。原peak无法按20病例重建，不能把peak差归因成纯参数规模效应。',
'较小模型MLX allocator峰值降低，但本轮RSS峰值反而升高。RSS与MLX allocator不可相加；不以权重较小推断进程总内存更小。没有Electron/Chroma共存测试，也没有重跑来挑更好数字。','',
'## 产物与核验','',
f'- {nprotected}个保护文件SHA256前后相同，Gemma实验全保留；冻结包由原Benchmark校验。',
'- 60个请求全部完成，0 operational errors、0 missing、0重试；results.jsonl/failures.jsonl保留严格scorer结果与原raw。',
'- selection.json、jobs-A/B/C.jsonl、semantic-mapping.json、paired-qwen35-records.json和metrics.json可逐条审计选题、提示、语义映射和paired结果。',
'- 模型身份/文件hash/native template见model-audit.json；实际加载、dtypes、库版本与memory API见run.json；smoke原文单独保存。','',
'## 最后直接回答','',
'1. **是否存在明显position/ID shortcut？没有复现Qwen3.5 C恒选第二位的灾难性模式，但仍有明显偏置与layout敏感性。** B组80%选a0、70%选第二位，AB语义一致仅35%；不能判定shortcut已解决。',
'2. **Permutation semantic consistency是否明显强于Qwen3.5？没有。** 三变体7/20 vs8/20；all-correct5/20 vs4/20。双候选4/10 vs0/10改善，但三候选3/10 vs8/10退步，整体没有提升。',
'3. **更小Qwen是否显示更好Runtime prior？未证实。** 输出合同60/60合法、部分二候选语义更稳定是积极信号，但整体准确率30/60 vs31/60，多意图12/30 vs15/30，尚不足以优先作为foundation。Goal/Understanding只做链路smoke，无完整质量结论。',
f'4. **性能/内存变化？** p50 {gp["p50_ms"]/1000:.3f}s vs{qp["p50_ms"]/1000:.3f}s，p95 {gp["p95_ms"]/1000:.3f}s vs{qp["p95_ms"]/1000:.3f}s；request-inclusive {gp["generated_tokens_per_request_second"]:.2f} vs{qp["generated_tokens_per_request_second"]:.2f} tok/s。load约0.492s vs1.425s。MLX peak减少约217MiB，RSS peak反而增加约346MiB，不能概括为全面更省内存。',
'5. **是否值得继续跑80 Policy/200 semantic？当前不建议优先扩大，尤其不直接跑200。** 本轮没有整体语义优势，13/20病例不能保持三变体同语义；局部二候选信号不足以抵消多意图/三候选退步。保留结果作为横向比较，到此停止。本结论是研究优先级判断，不证明更小Qwen任何训练都不会改善。']
(out/'Qwen3-0.6B-8bit-Mini-Screening.md').write_text('\n'.join(text)+'\n')
run.update(download_revision=audit['revision'],model_audit='model-audit.json',selection='selection.json',results='results.jsonl',failures='failures.jsonl',metrics='metrics.json',report='Qwen3-0.6B-8bit-Mini-Screening.md',decision='stop_after_mini_no_expansion',total_generations=63,training=False,prompt_tuning=False)
save(out/'run.json',run)
print('Report written; stopped after 3 smoke + 60 Policy.')
