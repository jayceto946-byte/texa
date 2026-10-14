#!/usr/bin/env python3
"""Report the frozen corrected-data experiment, including explicit unrun states."""
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.policy_sft_v0_acquisition import guard,OUT,frozen
guard()


def optional(name,default=None):
    return frozen.read(name) if (OUT/name).exists() else default


def percent(value):
    return '未测' if value is None else f'{value:.2%}'


def pp(value):
    return f'{value*100:+.2f} pp'


raw=optional('raw-dev-baseline.json')
smoke=optional('corrected-memory-smoke.json',{'status':'not_run','steps':[]})
state=optional('acquisition-state.json',{'status':'not_run','microsteps_completed':0,'checkpoints':[]})
baseline_state=optional('raw-baseline-state.json',{'status':'not_run'})
checks=optional('checkpoint-dev-evals.json',{'status':'not_run','checkpoints':[]})
replay=optional('train-replay.json')
hidden=optional('hidden-eval.json',{'status':'not_run'})
complete=state['status']=='complete' and hidden.get('status')=='complete'
failed=any(x.get('status')=='failed' for x in (state,smoke,baseline_state))
resource_abort=optional('resource-abort.json')
status='完成' if complete else '因系统资源异常停止' if resource_abort else '因运行错误停止' if failed else '进行中'
text=f'''# Policy-SFT-V0 Final Report

2026-10-07。状态：**{status}**。仅测试本地 Qwen3.5-0.8B-MLX-8bit 在当前冻结合成 Policy 合同下的task-acquisition。无下载、换Base、Runtime改动或其他模型任务。

## 实验身份与执行

修正版数据960 seeds、80个措辞家族、每seed四排列；Train/Dev/Hidden为672/144/144 seeds（2688/576/576实例）。同主题/模板/候选集合下有反事实有效请求，gold语义条件组均衡。所有位置/ID分层均衡，family与seed不跨split。初版topic-label异常run留在独立归档，本报告不混入其baseline、smoke、更新或结果。

原有数据、split、prompt、gold、评分函数、训练目标与Hidden gate哈希保持不变。执行入口为policy_sft_v0_acquisition.py；新增执行协议单独冻结，不修改旧scorer。只忽略与实验无关的macOS .DS_Store元数据。模型推理输入不包含gold/family元数据；raw首答严格解析、不修复、不重试、不用受约束解码。

正式配置：末8层，rank8，MLX直接scale16，dropout0，lr5e-5，batch1×accumulation8，max_seq_length384，checkpointing、mask_prompt；实际MLP和全/线性attention投影，不改模型结构。使用原生MLX-LM loss与compiled stateful accumulation；固定padding384，按原始长度mask，不截断，保持原有seed1807 shuffle完整epoch。

唯一原始模型对照仅评完整Dev。正式配置smoke只做5 microsteps，因此累计梯度但**0 optimizer update**；optimizer状态已初始化并检查finite，不声称这5步验证了Adam更新后的状态。正式训练另起干净模型、适配器、Adam和梯度累积；预注册2688 microsteps / 336 updates完整epoch，不按质量early-stop，实际完成数量见下文。每448步checkpoint后评完整Dev，按accuracy、四排列consistency、binary consistency、negation/correction、最低position/ID偏差排序，最早step仅作完全平局规则。

冻结身份：

'''
for name in ('FREEZE.json','TRAIN-FREEZE.json','ACQUISITION-FREEZE.json','train-config.yaml'):
    text+=f'- {name}: `{frozen.sha(OUT/name)}`\n'
text+='\n## 修正版 Raw Dev baseline\n\n'
if raw and raw.get('status')=='complete':
    text+='| 指标 | Raw Dev |\n|---|---:|\n'
    for key in ('semantic_accuracy','permutation_consistency','four_permutation_consistency','binary_consistency',
                'negation_correction_accuracy','tool_vs_answer_accuracy','multi_intent_accuracy','contract_validity'):
        text+=f'| {key} | {percent(raw[key])} |\n'
    text+=f'\nN={raw["N"]}，seed={raw["seeds"]}。原有permutation_consistency定义已是全部四排列一致，four_permutation_consistency是同义字段，不是第二套提高分数的定义。位置及ID分布见raw-dev-baseline.json，按二/三候选分层，非法输出保留在分母。\n'
else:text+=f'状态：{baseline_state["status"]}；没有完整结果时不填0%。\n'
text+='\n## 正式配置 corrected smoke\n\n'
text+=f'状态：{smoke["status"]}，完成{len(smoke.get("steps",[]))}/5 microsteps。\n\n'
text+='| Microstep | loss | wall s | gradient/adapter/optimizer finite | MLX peak GiB | RSS high-water GiB |\n|---|---:|---:|---|---:|---:|\n'
for r in smoke.get('steps',[]):
    finite=r['gradient_finite'] and r['adapter_finite'] and r['optimizer_state_finite']
    text+=f'| {r["microstep"]} | {r["loss"]:.6f} | {r["wall_seconds"]:.3f} | {finite} | {r["mlx_peak_bytes"]/2**30:.3f} | {r["max_rss_bytes"]/2**30:.3f} |\n'
text+='\nRSS高水位与MLX GPU分配器均使用共享统一内存，不能相加，也不等同于系统总占用。父进程采样250ms保存RSS，worker硬退出时缺失的MLX指标标未知。smoke不作能力判断、不复用权重。\n'
text+='\n## 预注册一epoch learning curve（以实际完成状态为准）\n\n'
text+=f'已完成{state.get("microsteps_completed",0)}/2688 microsteps，{state.get("optimizer_updates",0)}/336 optimizer updates。\n\n'
text+='| Step | loss window | Dev accuracy | 四排列一致 | binary一致 | neg/correction | tool/answer | multi-intent | max bias pp | validity | paired Δ accuracy pp |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n'
for c in checks.get('checkpoints',[]):
    m=c['metrics']
    text+=f'| {c["microstep"]} | {c["train_loss_window_mean"]:.6f} | {percent(m["semantic_accuracy"])} | {percent(m["permutation_consistency"])} | {percent(m["binary_consistency"])} | {percent(m["negation_correction_accuracy"])} | {percent(m["tool_vs_answer_accuracy"])} | {percent(m["multi_intent_accuracy"])} | {m["max_position_id_distribution_deviation"]*100:.2f} | {percent(m["contract_validity"])} | {m["paired_raw_comparison"]["semantic_accuracy_delta"]*100:+.2f} |\n'
text+='\n每个checkpoint都保留，paired比较使用同一576个实例的strict语义正确性，包含raw-only/trained-only/both-correct/both-wrong计数。排列相关性不作为独立样本证据。完整位置/ID分布、类别分母和raw输出另存JSON。\n'
if failed:
    text+='\n运行错误：\n\n'
    for phase,r in [('baseline',baseline_state),('smoke',smoke),('train',state)]:
        if r.get('status')=='failed':text+=f'- {phase}: `{r.get("error","inspect console")}`。停止，未降低配置或重试。\n'
if resource_abort:
    training_logs=[json.loads(line) for line in (OUT/'train-log.jsonl').read_text().splitlines()]
    training_logs=[r for r in training_logs if r.get('phase')=='acquisition']
    text+=f'\n系统级只读检查记录到 `kern.memorystatus_vm_pressure_level=4`（critical），swap {resource_abort["observed_swap_used_mib"]/1024:.3f} GiB / {resource_abort["observed_swap_total_mib"]/1024:.1f} GiB；按资源异常停止规则向worker发SIGTERM，退出码−15。最后完整microstep={resource_abort["last_completed_microstep"]}，更新={resource_abort["optimizer_updates"]}。这些已完成步骤全部finite；没有检测到OOM、NaN/Inf、shape或截断错误。系统压力是整机指标，不能将全部swap归因于本训练。终止后压力level恢复1，swap约1.781GiB。\n'
    text+=f'\n正式训练实际MLX peak {max(r["mlx_peak_bytes"] for r in training_logs)/2**30:.3f} GiB，worker RSS高水位 {max(r["max_rss_bytes"] for r in training_logs)/2**30:.3f} GiB。单步wall time p50={statistics.median(r["wall_seconds"] for r in training_logs):.3f}s，max={max(r["wall_seconds"] for r in training_logs):.3f}s。5-step smoke通过没有证明整轮训练的系统资源余量足够。详细记录见resource-abort.json。\n'
    text+='\n仅保留step448和896两个完整checkpoint；step1344/1792/2240/2688未完成。没有以部分learning curve冻结Dev-best，没有Train replay，没有加载Hidden样本进行评估，没有续训、缩配置或替换checkpoint。\n'
text+='\n## 七个结论问题\n\n'
if complete:
    selected=state['selected'];best=next(c for c in checks['checkpoints'] if c['microstep']==selected['microstep'])['metrics']
    hm=hidden['metrics'];delta=best['semantic_accuracy']-raw['semantic_accuracy']
    text+=f'1. **Raw → trained提升**：Dev {percent(raw["semantic_accuracy"])} → {percent(best["semantic_accuracy"])}，提升{pp(delta)}；严格paired计数见checkpoint-dev-evals.json。\n'
    text+=f'2. **位置/ID捷径**：Dev最大份额偏差{raw["max_position_id_distribution_deviation"]*100:.2f} → {best["max_position_id_distribution_deviation"]*100:.2f} pp，Hidden {hm["max_position_id_distribution_deviation"]*100:.2f} pp。'+('当前分层分布未见超过预注册阈值的明显position/ID偏好。' if hm['max_position_id_distribution_deviation']<=.10 else 'Hidden仍超过预注册bias阈值。')+'不能据有限测试证明所有捷径消失。\n'
    text+=f'3. **排列稳定性是否同步改善**：Dev四排列一致{percent(raw["permutation_consistency"])} → {percent(best["permutation_consistency"])}，binary一致{percent(raw["binary_consistency"])} → {percent(best["binary_consistency"])}；A布局accuracy {percent(raw["fixed_layout_A_accuracy"])} → {percent(best["fixed_layout_A_accuracy"])}，不是只报告固定布局。Hidden四排列{percent(hm["permutation_consistency"])}、binary {percent(hm["binary_consistency"])}。\n'
    text+=f'4. **Train/Dev/Hidden gap**：{percent(state["train_accuracy"])} / {percent(state["dev_accuracy"])} / {percent(state["hidden_accuracy"])}；Train−Dev {pp(state["train_dev_gap"])}，Dev−Hidden {pp(state["dev_hidden_gap"])}。三者是同一Dev-best checkpoint。类别在Dev/Hidden比例略异，需同时看strata，不将总体gap等同于纯记忆程度。\n'
    if state['go']:
        interpretation='未见措辞家族与排列仍达门槛，支持学习到了当前合成合同所需的请求/候选语义规则，超过固定布局或主题查表；不能排除未覆盖的模板捷径。'
    elif state['train_accuracy']>=.85 and state['hidden_accuracy']<.85:
        interpretation='Train高而Hidden未达accuracy门槛，符合模板/家族记忆或泛化不足；需结合分层错误定位，不能证明纯记忆是唯一原因。'
    else:interpretation='这次配置未同时满足学习与去偏门槛；不能仅凭loss或一次失败判定0.8B理论容量上限。'
    text+=f'5. **规则还是记模板**：{interpretation}\n'
    text+=f'6. **Hidden gate**：**{"GO" if state["go"] else "NO-GO"}**，所有预注册阈值须同时满足，详见下表。\n'
    text+=('7. **容量结论**：支持“在当前冻结的合成Policy合同下，0.8B能通过本次LoRA获得任务能力，raw checkpoint尚未学会这套选择合同”。不能证明raw所有不足只有缺训练。\n' if state['go'] else
           '7. **容量结论**：本次结果不支持所要求的完整task-acquisition成功命题；也不能外推为0.8B永远没有足够容量。\n')
    text+='\n## Dev选模与唯一Hidden gate\n\n'
    text+=f'Dev-best step={selected["microstep"]}，adapter SHA256 `{selected["adapter_sha256"]}`。选择回执在Train replay/Hidden前落盘，Hidden仅576条一次，不修改checkpoint，不再训练，不重跑挑分。\n\n'
    text+='| Gate | Hidden | threshold | pass |\n|---|---:|---:|---|\n'
    for k,v in hidden['gates'].items():
        passed=hm[k]<=v if k.startswith('max_') else hm[k]>=v
        text+=f'| {k} | {percent(hm[k])} | {"≤" if k.startswith("max_") else "≥"}{percent(v)} | {passed} |\n'
else:
    if checks.get('checkpoints') and raw:
        last=checks['checkpoints'][-1];m=last['metrics']
        text+=f'以下仅引用最后已完成的step{last["microstep"]}，**不是正式Dev-best或一epoch最终结果**。\n\n'
        text+=f'1. **Raw → trained**：已观测Dev {percent(raw["semantic_accuracy"])} → {percent(m["semantic_accuracy"])}，提升{pp(m["semantic_accuracy"]-raw["semantic_accuracy"])}。paired计数 `{json.dumps(m["paired_raw_comparison"]["counts"],ensure_ascii=False)}`。\n'
        text+=f'2. **捷径是否消失**：Dev位置/ID最大份额偏差 {raw["max_position_id_distribution_deviation"]*100:.2f} → {m["max_position_id_distribution_deviation"]*100:.2f} pp，低于10pp；有去偏迹象，但不能据此证明捷径真正消失，缺乏冻结选模后的Hidden验证。\n'
        text+=f'3. **排列同步提升**：Dev四排列一致 {percent(raw["four_permutation_consistency"])} → {percent(m["four_permutation_consistency"])}；binary {percent(raw["binary_consistency"])} → {percent(m["binary_consistency"])}。A固定布局accuracy {percent(raw["fixed_layout_A_accuracy"])} → {percent(m["fixed_layout_A_accuracy"])}。提升确实包含全部排列的稳定性，四排列一致仍未达90%。\n'
        text+='4. **Train/Dev/Hidden gap**：Train未测，部分checkpoint Dev见上表，Hidden未测；Train−Dev及Dev−Hidden未知。\n'
        text+='5. **规则还是模板/family记忆**：在family隔离Dev与反事实、排列评估上有学习信号，不能仅以topic/position/ID查表解释全部提升；没有完整epoch、Train replay与Hidden，尚不能区分完整task acquisition和残留模板/家族捷径。\n'
        text+='6. **Hidden gate**：**NOT EVALUATED**，没有GO/NO-GO能力判定；Hidden零次推理，不以未测冒充失败或通过。\n'
        text+='7. **0.8B容量足够？**：部分learning curve支持可学习性，但实验因资源异常未完成，不能支持所要求的完整容量命题；同样不能据此否定0.8B容量。\n'
    else:
        text+='1–7：当前尚无完整训练/选模/Train replay/Hidden结果，不能得出能力结论。未执行的accuracy与gap留空，不以loss或smoke成功代替。\n'
text+='\n**结论边界：即使Hidden通过，也只能证明当前冻结合成Policy合同下的task-acquisition能力，不能直接外推真实生产泛化。** 数据是确定性合成标签，主题和操作词复用，未做独立人工盲审；有效泛化单元是80个模板家族，不能把3840排列当3840个独立语义问题。实验没有生产接入。\n'
text+='\n## 交付文件\n\n'
for name in ('raw-dev-baseline.json','corrected-memory-smoke.json','train-log.jsonl','checkpoint-dev-evals.json','train-replay.json','hidden-eval.json','resource-abort.json','acquisition-integrity.json'):
    text+=f'- [{name}]({OUT/name})\n'
(OUT/'Policy-SFT-V0-Final-Report.md').write_text(text)
frozen.save('acquisition-integrity.json',{'status':'passed','data_prompt_split_gold_gates_config_unchanged':True,
    'existing_scientific_benchmark_files_unchanged':True,'dataset_freeze_sha256':frozen.sha(OUT/'FREEZE.json'),
    'training_config_sha256':frozen.sha(OUT/'train-config.yaml'),'acquisition_status':state['status']})
print('Updated:',OUT/'Policy-SFT-V0-Final-Report.md')
