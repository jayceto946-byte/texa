#!/usr/bin/env python3
"""Report measured state without inventing unrun model metrics."""
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.policy_sft_v0 import OUT,integrity,read,save

integrity()
stats=read('tokenizer-stats.json')
smoke=read('memory-smoke.json')
if smoke.get('placeholder'):
    archived=Path(smoke['historical_smoke_source']).parent
    original=json.loads((archived/'formal-state.json').read_text())
    history=smoke['historical_steps']
    shortcut=read('shortcut-audit.json')
    text='''# Policy-SFT-V0 Report

2026-10-07。**本轮因数据审计异常停止，未获得有效的容量结论。** 初版生成器使 topic 槽位高度关联 gold 动作；仅用 Train 标签做 topic-majority 即可达91.67%，不需要读用户请求。因此我主动中止这次无效训练，不把其loss或原始Dev对照当作语义学习证据。

没有发生OOM/NaN/Inf。旧正式run在58 microsteps / 7 optimizer updates停止，无checkpoint，无Hidden推理。旧数据、冻结合同、代码快照、原始输出和全部训练日志完整保存在同级 invalid-topic-label 目录，不覆盖、不删除、不混作修正数据的结果。修正依据仅来自Train结构审计，未使用Hidden模型结果。

## 已完成的修正数据

960 seed ×4排列=3840条chat JSONL，80个措辞家族。Train/Dev/Hidden为672/144/144 seed，即2688/576/576实例；整个模板家族和所有seed排列不跨split。覆盖tool-vs-answer、multi-intent、negation、correction、noisy wording、existing-data-vs-knowledge、tool distinction、quoted statement，二/三候选各一半。

现在同主题、同措辞模板、同候选集合/候选数有成对或三组有效请求，gold语义动作在组内均衡。候选内容和主题本身不能确定正确动作；必须根据request区分。所有split gold位置/ID严格分层平衡；Dev/Hidden的位置×ID联合格子完全相等，Train三候选格子相差至多1。

'''
    text+='训练前主题查表上界（标签结构审计，不是模型评分）：'+', '.join(
        f'{s} {v["topic_only_label_majority_upper_bound"]:.2%}' for s,v in shortcut['topic_bounds'].items())+'。\n'
    text+='''
输入采用现有Runtime Policy IR，模型只见system/user输入，assistant为最小action_id JSON；seed/family/gold/order映射元数据不送模型。原简化Policy提示原文保持不变，没有prompt tuning。request_input在生产仅为Runtime forced singleton，另存12个控制fixture，不虚构no_action或多候选澄清。

## 修正数据 tokenizer

| Split | p50 | p90 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
'''
    for split in ('train','dev','hidden'):
        s=stats['splits'][split];text+=f'| {split} | {s["p50"]} | {s["p90"]} | {s["p95"]} | {s["p99"]} | {s["max"]} |\n'
    text+=f'\n上限{stats["max_seq_length"]}由全量最大长度取整决定；0截断，candidate list/gold以及原生masking/generation prefix完整对齐。Hidden只做训练前长度和标签平衡检查，模型推理次数为0。\n'
    text+='''
## 已实际运行的五步 smoke（归档输入）

原始5步为末4层MLP/rank4/batch1/checkpoint/Adam lr1e-5，最长384-token批次。反向成功，所有loss、gradient、adapter和optimizer状态finite。该硬件链路测量有效，但不是修正数据的smoke，也不是能力评测；memory-smoke.json以not_run明确区分并链接原始证据。

| Step | loss | wall seconds | MLX peak GiB | RSS high-water GiB |
|---|---:|---:|---:|---:|
'''
    for r in history:text+=f'| {r["step"]} | {r["loss"]:.6f} | {r["wall_seconds"]:.3f} | {r["mlx_peak_bytes"]/2**30:.3f} | {r["max_rss_bytes"]/2**30:.3f} |\n'
    text+='\n物理统一内存8 GiB。MLX active allocator峰值约3.366 GiB，高水位RSS约0.756 GiB；二者不能相加，也不代表已直接测得系统总统一内存。父进程另以250ms采样RSS，原始数据在归档监控JSON。\n'
    text+='''
## 正式方案与未执行状态

train-config.yaml已建立：末8层、rank8、MLX直接scale16、dropout0、lr5e-5、batch1×accumulation8、完整长度384、checkpoint、mask_prompt，1epoch=2688 microsteps/336 updates。显式targets为MLP gate/up/down，全注意力q/k/v/o和实际linear_attn in_proj_qkv/z/a/b/out_proj；原始装配核实1,803,776个参数，不修改结构。每448 microsteps保留checkpoint并用完整Dev语义指标选模，之后同一checkpoint评完整Train，最后仅一次冻结Hidden。MLX scale直接乘BA，不误写为alpha/r。

修正版没有自动开启第二次训练。smoke/dev/hidden明确not_run；train-log记录停止与重建事件，真实旧5+58步日志留在归档。不存在可选择的checkpoint。Train、Dev、Hidden accuracy和两个gap均为null；不能将未测填成0%，也不能归因为0.8B容量不足。

预注册Hidden gate保留：accuracy>=85%、四排列consistency>=90%、binary consistency>=90%、negation/correction>=80%，候选数分层的预测位置/ID份额相对gold最大偏差<=10个百分点。指标定义、门槛、prompt、split、数据及配置均在训练前冻结；不按Hidden调参。

## 结论与完整性

**本轮只确认LoRA反向可运行；尚不能回答能否摆脱shortcut并学会语义选择。** 我修正并冻结了数据，按异常停止要求未继续训练。合成模板的主题槽位仍复用，标签未经独立人工盲审，未来通过也仅支持此合成合同下的容量可行，不能证明真实生产泛化。

既有模型文件未保存/修改，无下载、换Base或依赖安装；没有修改Runtime、旧Benchmark gold/scorer或其他任务。旧Benchmark/source release和既有raw的SHA256均未变化。准备与审计用venv310/Python3.10，GPU worker用既有已授权LM Studio Python3.11。完整spec、JSONL、metadata、tokenizer统计、配置和审计在本目录；无在后台继续运行的训练进程。
'''
    (OUT/'Policy-SFT-V0-Report.md').write_text(text)
    save('integrity.json',{'status':'passed','experiment_freeze_unchanged':True,'legacy_benchmark_unchanged':True,
                         'data_anomaly_stopped':True,'corrected_dataset_training_steps':0,'hidden_inference_count':0})
    print('Stopped-data-anomaly report updated:',OUT/'Policy-SFT-V0-Report.md')
    sys.exit(0)
formal=read('formal-state.json') if (OUT/'formal-state.json').exists() else {'status':'not_run'}
monitor=read('train-process-monitor.json') if (OUT/'train-process-monitor.json').exists() else {}
steps=smoke['steps']
gib=lambda b:f'{b/2**30:.3f} GiB'
if formal['status']=='failed':
    for name in ('dev-eval.json','hidden-eval.json'):
        value=read(name)
        if value.get('status')!='complete':
            save(name,{'status':'not_run','reason':'formal run stopped on exception; no retry or smaller configuration',
                       'formal_error':formal.get('error'),'accuracy':None})
dev=read('dev-eval.json');hidden=read('hidden-eval.json')
state='进行中' if formal['status']=='running' else '完成' if formal['status']=='complete' else '被异常阻断'
text=f'''# Policy-SFT-V0 Report

2026-10-07。状态：{state}。唯一实验对象为本地 Qwen3.5-0.8B-MLX-8bit / mlx-lm0.31.3 / mlx0.32.0。没有下载、换底座、修改 Runtime/Benchmark/gold/scorer 或训练其他任务。

## 数据与冻结

960 seed，80 个措辞家族，3840 条完整 chat JSONL。Train/Dev/Hidden：672/144/144 seed，2688/576/576 实例；家族与 seed 完全隔离。八类语义均覆盖，每 seed 四个排列（顺序、ID、组合）。各候选数分层的 gold 位置与 ID 严格平衡；Dev/Hidden 联合格子严格相等，Train 三候选格子相差至多1。完整 schema、标签映射、排列内容不变和 strict parser 审计通过，详见 data-audit.json。

标签为确定性合成配方，未经过独立人工盲审；80 家族×主题槽位并不等价于960个独立自然场景。Hidden 是新模板家族，但主题与语义操作词可复用。因此即使过 gate，也只支持这个合成候选合同下的容量可行，不能证明生产泛化。

现有 Policy prompt 原文冻结复用；没有 prompt tuning。blocking input 在生产仅生成 request_input 单候选，本实验另存12个 Runtime forced controls，不制造不真实的澄清选择；无独立 no_action。Hidden 未用于任何超参选择。数据/提示/gate hash 见 FREEZE.json，配置/tokenizer/code hash 见 TRAIN-FREEZE.json。

## Tokenizer

| Split | p50 | p90 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
'''
for split in ('train','dev','hidden'):
    s=stats['splits'][split]
    text+=f'| {split} | {s["p50"]} | {s["p90"]} | {s["p95"]} | {s["p99"]} | {s["max"]} |\n'
text+=f'''
max_seq_length={stats['max_seq_length']}，由全部完整实例最大值向上取32倍数得到。0条截断；gold、候选与原生 masking/generation prefix 对齐已检查。Hidden 此阶段只统计长度，不推理答案。

## 五步 smoke

状态：{smoke['status']}，完成{len(steps)}/5步。末4层 MLP/rank4/scale8/batch1/checkpoint/Adam lr1e-5，使用最长的5个不同 Train seed。该结果只证明反向与资源路径，不能作为能力成绩。

| Step | loss | wall seconds | finite gradients/state | MLX peak | peak RSS |
|---|---:|---:|---|---:|---:|
'''
for s in steps:
    text+=f'| {s["step"]} | {s["loss"]:.6f} | {s["wall_seconds"]:.3f} | {s["gradients_finite"] and s["parameters_optimizer_finite"]} | {gib(s["mlx_peak_bytes"])} | {gib(s["max_rss_bytes"])} |\n'
if steps:
    text+=f'\n物理统一内存 {gib(smoke["physical_unified_memory_bytes"])}；MLX peak最大 {gib(max(s["mlx_peak_bytes"] for s in steps))}，rusage高水位RSS {gib(max(s["max_rss_bytes"] for s in steps))}。二者不能相加；MLX为共享内存分配器指标，RSS不完整覆盖Metal内存，未声称测得系统总统一内存占用。父进程每250ms另采RSS，见smoke-process-monitor.json。\n'
text+=f'''
## 正式配置与状态

smoke通过后重新加载原始底座，丢弃smoke适配器。正式配置固定：末8层、rank8、MLX直接scale16、dropout0、lr5e-5、完整长度384、batch1×accumulation8、1个epoch（2688 microstep / 336 update），MLP和实际两类注意力投影。实际参数1,803,776，逐层keys见formal-model.json，不修改结构。每448 microstep保留checkpoint并评完整Dev，以accuracy/consistency/最早step确定唯一checkpoint。原始模型仅在Dev做冻结提示对照。

当前状态：{formal['status']}；已完成 microsteps：{formal.get('microsteps_completed',0)}/2688；checkpoint数：{len(formal.get('checkpoints',[]))}。Dev状态：{dev['status']}；Hidden状态：{hidden['status']}。
'''
if formal['status']=='failed':
    text+=f'\n异常：`{formal.get("error", "see train-console.log")}`。停止后没有缩小配置、重试、继续训练或运行Hidden。进程退出码：{monitor.get("exit_code")}，父进程采样RSS峰值：{gib(monitor.get("rss_peak_bytes",0))}。\n'
if 'raw_dev_baseline' in formal:
    b=formal['raw_dev_baseline']
    text+=f'\n原始模型Dev：accuracy {b["semantic_accuracy"]:.2%}、四排列consistency {b["permutation_consistency"]:.2%}、binary consistency {b["binary_consistency"]:.2%}，N={b["N"]} / {b["seeds"]} seed。该原始模型对照不调整训练配置。\n'
if formal['status']=='complete':
    m=hidden['metrics'];selected=read('selected-checkpoint.json')
    text+=f'\n唯一dev-selected checkpoint：{selected["path"]}，microstep={selected["microstep"]}。Hidden仅一次，选模先于Hidden推理。\n\n'
    text+='| 指标 | Hidden | gate |\n|---|---:|---:|\n'
    for key,value in hidden['gates'].items():text+=f'| {key} | {m[key]:.2%} | {"<=" if key.startswith("max_") else ">="}{value:.0%} |\n'
    text+=f'\nTrain {formal["train_accuracy"]:.2%} / Dev {formal["dev_accuracy"]:.2%} / Hidden {formal["hidden_accuracy"]:.2%}。Train-Dev gap {formal["train_dev_gap"]:.2%}，Dev-Hidden gap {formal["dev_hidden_gap"]:.2%}。预注册gate：{"GO" if formal["go"] else "NO-GO"}。完整类别与position/ID偏好分布、all-correct及分母见dev-eval.json、hidden-eval.json；无loss成功替代。\n'
    if formal['go']:text+='\n解释：支持0.8B在本合成合同和未见措辞模板上通过专项LoRA获得任务能力。不能单独证明真实场景无捷径或所有raw缺陷只有训练不足。\n'
    elif formal['train_accuracy']>=.85 and formal['hidden_accuracy']<.85:text+='\n解释：训练集高、Hidden不足，符合template/family overfit；容量与自然语义泛化仍未证明。\n'
    else:text+='\n解释：本配置未同时通过门槛；结合Train/Dev/Hidden区分学习不足与泛化不足，不将此归结为0.8B理论容量上限。\n'
else:
    text+='\nTrain/Dev-selected/Hidden accuracy及两个gap尚无可报告结果，以null/not_run记录，不用0%填补。当前不能回答“能否从shortcut学成语义selector”；smoke成功不等于任务学习成功。\n'
text+='\n## 完整性与执行\n\n既有Benchmark/scorer/raw文件hash验证未变，所有新数据、日志、统计与checkpoint隔离保存。准备与审计使用venv310/Python3.10，MLX子进程复用已有LM Studio Python3.11，无依赖重装。训练loop复用mlx-lm default_loss/ChatDataset/LoRA/grad_checkpoint，显式校验finite、记录每个microstep并保留greedy raw，不改旧评分器。\n'
(OUT/'Policy-SFT-V0-Report.md').write_text(text)
save('integrity.json',{'status':'passed','experiment_freeze_unchanged':True,'legacy_benchmark_unchanged':True})
print('Report updated:',OUT/'Policy-SFT-V0-Report.md')
