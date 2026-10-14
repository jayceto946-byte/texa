#!/usr/bin/env python3
"""Isolated, local-only Policy SFT experiment. Never changes Runtime or benchmark.

prepare: venv310; tokenize/smoke/train: existing LM Studio MLX interpreter.
No hidden inference is allowed before the dev-selected checkpoint is committed.
"""
import argparse
import collections
import copy
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'docs/validation/policy-sft-v0-20261007'
MODEL = '/Users/jichengqian/.lmstudio/models/lmstudio-community/Qwen3.5-0.8B-MLX-8bit'
KEYS_MLP = ['mlp.gate_proj', 'mlp.up_proj', 'mlp.down_proj']
KEYS_ALL = KEYS_MLP + ['self_attn.q_proj', 'self_attn.k_proj', 'self_attn.v_proj', 'self_attn.o_proj',
    'linear_attn.in_proj_qkv', 'linear_attn.in_proj_z', 'linear_attn.in_proj_a',
    'linear_attn.in_proj_b', 'linear_attn.out_proj']
GATES = {'semantic_accuracy': .85, 'permutation_consistency': .90,
         'binary_consistency': .90, 'negation_correction_accuracy': .80,
         'max_position_id_distribution_deviation': .10}


def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def save(name, x):
    (OUT / name).write_text(json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def read(name):
    return json.loads((OUT / name).read_text())


def rows(name):
    return [json.loads(s) for s in (OUT / name).read_text().splitlines()]


def write_rows(name, values):
    (OUT / name).write_text(''.join(canonical(v) + '\n' for v in values))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def append(name, x):
    with (OUT / name).open('a') as f:
        f.write(canonical(x) + '\n'); f.flush()


def protected():
    manifest = json.loads((ROOT / 'docs/runtime-benchmark-v0.1/case-scope-manifest.json').read_text())
    directories = [ROOT / 'evaluation/runtime_benchmark', ROOT / 'docs/runtime-benchmark-v0.1',
                   ROOT / 'docs/validation/runtime-benchmark-v0.1', Path(manifest['source_release'])]
    return {str(p): sha(p) for d in directories for p in sorted(d.rglob('*'))
            if p.is_file() and '__pycache__' not in str(p) and p.suffix != '.pyc'}


def integrity():
    freeze = read('FREEZE.json')
    for name, expected in freeze['sha256'].items():
        assert sha(OUT / name) == expected, 'experiment freeze mismatch: ' + name
    assert protected() == read('protected-before.json'), 'existing benchmark changed'


# Template families are allocated to splits BEFORE topic substitution/permutation.
# Each category has 10 independent surface families, 12 semantic instances/family.
TEMPLATES = {
 'tool_vs_answer': [
  '请{op}，{other}留到下次。', '{op}就够了，暂时不用{other}。',
  '这轮要做的是{op}；{other}不是这次的任务。', '只需要{op}，不用顺带{other}。',
  '目标很简单：{op}。别额外{other}。', '我需要{op}，目前不需要{other}。',
  '把这一次用于{op}，以后再考虑{other}。', '现在请{op}，别急着{other}。',
  '本轮范围是{op}，请不要扩展到{other}。', '安排给你的事情只有{op}；{other}以后再说。'],
 'multi_intent': [
  '先{op}，再{other}。', '{other}也要做，不过第一步是{op}。',
  '顺序定为{op}在前，{other}在后。', '做完{op}之后才{other}。',
  '下一步先{op}；完成它再开始{other}。', '我想{other}，前提是先{op}。',
  '两件事都需要：首先{op}，其次{other}。', '请按这个次序来：{op}，然后{other}。',
  '后面准备{other}，现在优先{op}。', '{op}尚未完成，{other}必须排在它后面。'],
 'negation': [
  '别{other}，请{op}。', '不要{other}，我要的是{op}。',
  '并不是让你{other}，而是请你{op}。', '这次不需要{other}，只需{op}。',
  '拒绝{other}这个安排；现在{op}。', '{other}不在本次范围内，{op}才是。',
  '我没要求{other}；我要求{op}。', '不必{other}，直接{op}即可。',
  '先把{other}排除，留下{op}。', '取消{other}这一步，目前只{op}。'],
 'correction': [
  '原本想{other}，改成{op}。', '刚说要{other}，更正一下，现在{op}。',
  '撤回{other}的要求，新的要求是{op}。', '之前的{other}不算了，请{op}。',
  '我改变主意了：不做{other}，改做{op}。', '更新任务，{op}替代刚才的{other}。',
  '旧安排是{other}，最终决定{op}。', '上一个要求{other}作废，这一轮{op}。',
  '修正刚才的话，接下来{op}，不是{other}。', '以这句为准：{op}。前面说的{other}撤销。'],
 'noisy_wording': [
  '嗯……今天有点累。{op}吧；{other}算了。', '随口说说，啊对，真正要你{op}，不是{other}。',
  '那个，帮我{op}呗，别顺手{other}哈。', '我绕远了：这次实际是{op}，{other}以后说。',
  '唔，事情好多，但眼下{op}就行，没要{other}。', '抱歉说得乱，需求整理为{op}，暂不{other}。',
  '碎碎念归碎碎念，现在{op}，别把{other}当任务。', '今天状态一般。请{op}；不是让你{other}啊。',
  '等下等下，重点是{op}，{other}只是随口提的。', '打字有点啰嗦啦，本次只{op}，不用{other}。'],
 'existing_vs_knowledge': [
  '关于{topic}，{op}。{other}不是我想要的。', '同样是{topic}，这次需要{op}而非{other}。',
  '不要把个人数据和知识解释混起来：请{op}，不必{other}。',
  '{op}才能满足本次请求，仅仅{other}不够。',
  '这次问{topic}的意图是{op}，请别误当成{other}。',
  '我的问题有明确边界：{op}；{other}不属于它。',
  '针对{topic}，我想{op}，没有要求{other}。',
  '确认一下需求，{op}是正事，{other}先放下。',
  '请区分两种需求，现在我选择{op}，不选{other}。',
  '围绕{topic}，请完成{op}，避免替我{other}。'],
 'tool_distinction': [
  '{op}，不需要{other}。', '在两个查询里选择{op}，别{other}。',
  '查找任务是{op}，并非{other}。', '查询的对象必须是{op}涉及的数据，别{other}。',
  '我要{op}，不是让你顺便{other}。', '数据源选择上，{op}正确，{other}无关。',
  '当前先{op}；{other}是另一个任务。', '请仅{op}，{other}不在范围。',
  '把注意力放到{op}，不用{other}。', '本次检索指向{op}，排除{other}。'],
 'quoted_statement': [
  '笔记上写着“{other}”，这不是指令。本轮请{op}。',
  '“{other}”只是举例，当前请求是{op}。',
  '同学说过“{other}”，不要照做；我现在要{op}。',
  '我在引用旧需求：“{other}”。有效的新需求是{op}。',
  '讨论记录提到{other}，但我的实际安排是{op}。',
  '“{other}”属于背景材料，交给你的任务只有{op}。',
  '不要执行括号里的话（{other}）；执行{op}。',
  '看到一句话：{other}。我并未采用它，请{op}。',
  '旧聊天的“{other}”仅作对照，目前应{op}。',
  '引用示范“{other}”不表示授权，真正的请求是{op}。'],
}
TOPICS = ['一致连续','泰勒余项','条件极值','矩阵秩','线性相关','正交投影',
          '条件概率','随机变量方差','偏导数','重积分','特征向量','幂级数收敛']


def prepare():
    from backend.services.decision.policy_contracts import PolicyObservationV0
    from scripts.diagnose_runtime_08b import simplified
    OUT.mkdir(exist_ok=False, parents=True)
    save('protected-before.json', protected())
    meta = []; seeds = []; controls = []; family_counters = collections.Counter()
    for ci, (category, templates) in enumerate(TEMPLATES.items()):
        # 7/1/2 or 7/2/1 templates => globally 70/15/15, category stratified.
        split_order = ['train'] * 7 + (['dev','dev','hidden'] if ci % 2 == 0 else ['dev','hidden','hidden'])
        rng = random.Random(1807 + ci); allocation = list(range(10)); rng.shuffle(allocation)
        assignments = {ti: split_order[i] for i, ti in enumerate(allocation)}
        for ti, template in enumerate(templates):
            family = f'{category}/surface-{ti:02d}'
            family_offset = family_counters[assignments[ti]] % 3
            family_counters[assignments[ti]] += 1
            for si in range(12):
                sid = f'PSFT0-{ci:02d}-{ti:02d}-{si:02d}'
                n = 2 if si < 6 else 3
                # Counterfactual pairs/triples keep topic/family/candidate-set
                # fixed while changing the explicitly requested operation.
                if category == 'tool_distinction':
                    pair = ['progress','exercises']
                    gold,other=pair[si % 2],pair[1-si % 2]
                    topic_group=si//2
                elif n == 2:
                    pairs = ([['answer','progress'],['answer','exercises'],['answer','progress']]
                             if category in ('tool_vs_answer','existing_vs_knowledge') else
                             [['answer','progress'],['answer','exercises'],['progress','exercises']])
                    pair=pairs[(si//2+ti+ci)%3]
                    gold,other=pair[si % 2],pair[1-si % 2]
                    topic_group=si//2
                else:
                    gold=['answer','progress','exercises'][(si-6)%3]
                    alternatives=[x for x in ('answer','progress','exercises') if x!=gold]
                    other=alternatives[(ti+si//3)%2]
                    topic_group=3+(si-6)//3
                topic=TOPICS[(topic_group+(ti+ci)*5)%len(TOPICS)]
                ops = {'answer': f'直接解释{topic}的基本含义，不查个人记录',
                       'progress': f'查询我最近七天的学习记录和进度，关注{topic}',
                       'exercises': f'从已有习题库找{topic}的题目'}
                request = template.format(op=ops[gold], other=ops[other], topic=topic)
                actions = {'answer': {'kind':'generate_answer','args':{}},
                    'progress': {'kind':'call_tool','args':{'tool_id':'get_recent_progress','input':{
                        'days':7,'limit':12,'subject':'数学','book_name':'高等数学'}}},
                    'exercises': {'kind':'call_tool','args':{'tool_id':'search_exercises','input':{
                        'book_name':'高等数学','subject':'数学','chapter':'','query':topic,'limit':8}}}}
                # Binary subset balanced gold position/ID, ternary subset likewise.
                selected = [gold, other] if n == 2 else ['answer','progress','exercises']
                base_order = [x for x in selected if x != gold]
                gp = si % n
                base_order.insert(gp, gold)
                gid = (si // 2) % 2 if n == 2 else ((si - 6) // 2 + family_offset) % 3
                ids = [f'a{i}' for i in range(n)]
                base_map = {sem: ids[(j - gp + gid) % n] for j, sem in enumerate(base_order)}
                seed = {'seed_id':sid,'semantic_family':category,'family_id':family,
                    'gold_semantic_action':gold,'surface_variant':ti,'split':assignments[ti],
                    'request':request,'candidate_count':n,'topic':topic,
                    'gold_basis':'explicit active operation; negation/update/priority/quotation applied',
                    'synthetic':True,'human_adjudicated':False}
                seeds.append(seed)
                for variant in range(4):
                    # A original, B order only, C ID only, D combined.
                    shift_order = 0 if variant in (0,2) else (1 if variant == 1 or n == 2 else 2)
                    order = base_order[shift_order:] + base_order[:shift_order]
                    shift_id = 0 if variant in (0,1) else (1 if variant == 2 or n == 2 else 2)
                    mapping = {ids[(int(v[1:]) + shift_id) % n]: sem for sem,v in base_map.items()}
                    sem_to_local = {sem:local for local,sem in mapping.items()}
                    inp = {'request':request,'context':{'resolved_query':request,'goal':None,
                        'constraints':{'answer_mode':'global_general','subject':'数学','book_name':'高等数学'}},
                        'admissible_actions':[{'id':sem_to_local[sem],**copy.deepcopy(actions[sem])} for sem in order],
                        'missing_inputs':[],'previous_result':None}
                    PolicyObservationV0.model_validate(inp)
                    messages = simplified('policy_select', inp, canonical)
                    gold_id = sem_to_local[gold]
                    messages.append({'role':'assistant','content':canonical({'action_id':gold_id})})
                    meta.append({**seed,'instance_id':sid + '-' + 'ABCD'[variant],
                        'permutation':'ABCD'[variant],'candidate_order':order,'action_id_mapping':mapping,
                        'gold_id':gold_id,'gold_position':order.index(gold)+1,'input':inp,'messages':messages})
    for i in range(12):
        topic = TOPICS[i]
        controls.append({'seed_id':f'PSFT0-GATE-{i:02d}','request':f'请根据缺失的附表求{topic}题的结果。',
            'admissible_actions':[{'id':'a0','kind':'request_input','args':{}}],
            'missing_inputs':[{'kind':'attachment','blocking':True,'status':'missing'}],
            'expected':'a0','mode':'Runtime forced singleton, no model call, excluded from SFT/semantic metrics'})
    assert len(seeds) == 960 and len(meta) == 3840
    # A seed/family/topic/candidate-set shortcut must not earn a high score.
    conditioned = collections.defaultdict(collections.Counter)
    for seed in seeds:
        sample=next(r for r in meta if r['seed_id']==seed['seed_id'])
        key=(seed['family_id'],seed['topic'],seed['candidate_count'],
             tuple(sorted(sample['candidate_order'])))
        conditioned[key][seed['gold_semantic_action']]+=1
    assert all(len(c)>=2 and len(set(c.values()))==1 for c in conditioned.values())
    shortcuts={}
    for split in ('train','dev','hidden'):
        groups=collections.defaultdict(collections.Counter)
        for seed in seeds:
            if seed['split']==split:groups[seed['topic']][seed['gold_semantic_action']]+=1
        upper=sum(max(c.values()) for c in groups.values())/sum(sum(c.values()) for c in groups.values())
        assert upper<=.55,'topic-only shortcut could exceed 55%'
        shortcuts[split]={'topic_only_label_majority_upper_bound':upper,
            'note':'pre-training structural label audit, not model evaluation'}
    save('shortcut-audit.json',{'status':'passed','topic_bounds':shortcuts,
        'family_topic_candidate_set_conditioned_gold_balanced':True,
        'counterfactual_pairs_and_triples':True})
    write_rows('seeds.jsonl', seeds); write_rows('runtime-gate-controls.jsonl', controls)
    balance = {}
    for split in ('train','dev','hidden'):
        selected = [r for r in meta if r['split'] == split]
        write_rows(split+'-metadata.jsonl', selected)
        write_rows({'train':'train','dev':'valid','hidden':'hidden'}[split]+'.jsonl',
                   [{'messages':r['messages']} for r in selected])
        balance[split] = {'seeds':len(selected)//4,'instances':len(selected),'by_candidate_count':{}}
        for n in (2,3):
            group = [r for r in selected if r['candidate_count'] == n]
            positions = collections.Counter(r['gold_position'] for r in group)
            ids = collections.Counter(r['gold_id'] for r in group)
            assert len(set(positions.values())) == len(set(ids.values())) == 1
            balance[split]['by_candidate_count'][str(n)] = {'N':len(group),
                'gold_position':dict(positions),'gold_id':dict(ids),
                'position_id_joint':dict(collections.Counter(f'{r["gold_position"]}/{r["gold_id"]}' for r in group))}
    assert not (set(r['request'] for r in meta if r['split']=='train') &
                set(r['request'] for r in meta if r['split']!='train'))
    save('balance.json',balance)
    prompt = meta[0]['messages'][0]['content']
    (OUT/'system-prompt.txt').write_text(prompt)
    save('experiment.json',{'version':'Policy-SFT-V0','seed':1807,'model_path':MODEL,
        'epochs':1,'effective_batch':8,'dev_eval_every_microsteps':448,
        'prompt':'exact existing simplified Policy prompt; unchanged across training/evaluation',
        'gates':GATES,'hidden_use':'once, after dev selection; never baseline/tuning',
        'split_unit':'entire category/surface template family, all 12 topics and permutations together',
        'decode':{'temperature':0,'max_tokens':64,'enable_thinking':False},
        'checkpoint_selection':'max dev semantic_accuracy, then consistency, then earliest step',
        'gold_provenance':'counterfactual deterministic synthetic recipes; no LLM labeling or benchmark gold copied',
        'no_action_supported':False,'request_input':'forced singleton only, separate controls',
        'smoke_selection':'5 longest train instances from distinct seeds, deterministic',
        'bias_gate':'within each candidate-count stratum, maximum absolute predicted-versus-gold position/ID share deviation <= 0.10; invalid outputs retain denominator',
        'metrics_definition':{'permutation_consistency':'all 4 valid predictions map to the same semantic candidate per seed',
          'binary_consistency':'same definition on 2-candidate seeds',
          'three_variant_all_correct':'A/B/C all semantically correct per seed; D separately contributes to 4-variant metrics'},
        'limit':'synthetic unseen-template/topic combinations, not independent human/production generalization'})
    files = [p for p in OUT.iterdir() if p.is_file() and p.name!='protected-before.json']
    save('FREEZE.json',{'version':'Policy-SFT-V0','frozen_before_training':True,
         'sha256':{p.name:sha(p) for p in files}})
    for name in ('dev-eval.json','hidden-eval.json'):
        save(name,{'status':'not_run','reason':'waiting for tokenizer and 5-step smoke'})
    (OUT/'train-log.jsonl').touch()
    print(canonical(balance), flush=True)


def tokenizer_stats():
    integrity()
    from transformers import AutoTokenizer
    import numpy as np
    tokenizer = AutoTokenizer.from_pretrained(MODEL,local_files_only=True,trust_remote_code=False)
    lengths = {}; records = []
    for split in ('train','dev','hidden'):
        group = []
        for row in rows(split+'-metadata.jsonl'):
            msgs = row['messages']
            tokens = tokenizer.apply_chat_template(msgs, tokenize=True, return_dict=False, enable_thinking=False)
            prefix = tokenizer.apply_chat_template(msgs[:-1], tokenize=True,
                        add_generation_prompt=True,return_dict=False,enable_thinking=False)
            assert tokens[:len(prefix)] == prefix, 'masked training prefix differs from generation prefix'
            assert len(tokens) > len(prefix)
            suffix = tokenizer.decode(tokens[len(prefix):])
            assert msgs[-1]['content'] in suffix, 'gold missing from supervised suffix'
            group.append(len(tokens))
            records.append({'instance_id':row['instance_id'],'seed_id':row['seed_id'],'split':split,
                'total_tokens':len(tokens),'prompt_tokens':len(prefix),'supervised_tokens':len(tokens)-len(prefix)})
        lengths[split] = {f'p{p}':float(np.percentile(group,p)) for p in (50,90,95,99)}
        lengths[split].update(max=max(group),min=min(group),N=len(group))
    # Hidden lengths only, no model answers/results. Bound all complete instances.
    limit = 32 * math.ceil(max(x['max'] for x in lengths.values()) / 32)
    write_rows('token-lengths.jsonl',records)
    save('tokenizer-stats.json',{'status':'complete','splits':lengths,'max_seq_length':limit,
        'truncated_instances':0,'all_gold_and_candidates_complete':True,
        'length_policy':'ceil(all-split maximum/32)*32; hidden inspected for lengths only',
        'tokenizer_files_sha256':{p.name:sha(p) for p in Path(MODEL).glob('*')
            if p.is_file() and ('tokenizer' in p.name or p.name=='chat_template.jinja')},
        'prefix_alignment_checked':True})
    import yaml
    common = {'model':MODEL,'fine_tune_type':'lora','batch_size':1,'max_seq_length':limit,
        'grad_checkpoint':True,'mask_prompt':True,'seed':1807,'optimizer':'adam',
        'data':str(OUT),'train':True,'report_to':None,'drop_last':False}
    smoke = {**common,'num_layers':4,'lora_parameters':{'rank':4,'scale':8.,'dropout':0.,'keys':KEYS_MLP},
         'learning_rate':1e-5,'iters':5,'grad_accumulation_steps':1,'adapter_path':str(OUT/'smoke-adapter')}
    formal = {**common,'num_layers':8,'lora_parameters':{'rank':8,'scale':16.,'dropout':0.,'keys':KEYS_ALL},
         'learning_rate':5e-5,'iters':len(rows('train-metadata.jsonl')),'grad_accumulation_steps':8,
         'steps_per_eval':448,'save_every':448,'adapter_path':str(OUT/'checkpoints'),
         'epochs':1,'scale_semantics':'MLX directly multiplies BA by scale, not alpha/r',
         'execution':'custom instrumented loop using mlx-lm default_loss and grad_checkpoint; iters=microsteps'}
    for name,x in [('smoke-config.yaml',smoke),('train-config.yaml',formal)]:
        (OUT/name).write_text(yaml.safe_dump(x,allow_unicode=True,sort_keys=False))
    save('TRAIN-FREEZE.json',{'sha256':{name:sha(OUT/name) for name in
            ('tokenizer-stats.json','token-lengths.jsonl','smoke-config.yaml','train-config.yaml')}})
    print(canonical(read('tokenizer-stats.json')), flush=True)


def rss():
    import subprocess
    current = int(subprocess.check_output(['ps','-o','rss=','-p',str(os.getpid())],text=True).strip())*1024
    return {'rss_bytes':current,'max_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def memory(mx):
    return {**rss(),'mlx_active_bytes':mx.get_active_memory(),'mlx_cache_bytes':mx.get_cache_memory(),
        'mlx_peak_bytes':mx.get_peak_memory(),
        'unified_memory_note':'MLX GPU allocations share physical memory with RSS; do not sum them'}


def model_setup(config):
    import importlib.metadata
    for key,expected in {'mlx':'0.32.0','mlx-lm':'0.31.3','transformers':'5.14.1'}.items():
        assert importlib.metadata.version(key)==expected,(key,'version mismatch')
    import mlx.core as mx
    from mlx_lm import load
    from mlx.utils import tree_flatten
    from mlx_lm.tuner.utils import linear_to_lora_layers
    from mlx_lm.tuner.trainer import grad_checkpoint
    mx.random.seed(config['seed'])
    model,tok=load(MODEL,lazy=False)
    assert len(model.layers)==24
    quant = [m for _,m in model.named_modules() if hasattr(m,'bits')]
    assert quant and all(m.bits==8 and m.group_size==64 for m in quant)
    model.freeze()
    linear_to_lora_layers(model,config['num_layers'],config['lora_parameters'])
    params=tree_flatten(model.trainable_parameters())
    assert params and all('lora_' in k for k,v in params)
    targets=[{'layer_index':i,'modules':[k for k,m in model.layers[i].named_modules()
        if type(m).__name__=='LoRALinear']} for i in range(24-config['num_layers'],24)]
    assert all(t['modules'] for t in targets)
    mx.eval(model.parameters()); mx.synchronize()
    grad_checkpoint(model.layers[0])
    return model,tok,{'trainable_parameters':sum(v.size for k,v in params),
        'trainable_tensors':len(params),'targets':targets,'quantized_modules':len(quant)}


def dataset(tok,metadata):
    from mlx_lm.tuner.datasets import ChatDataset,CacheDataset
    ds = CacheDataset(ChatDataset([{'messages':r['messages']} for r in metadata],tok,mask_prompt=True))
    # Native Qwen3.5 template defaults thinking to false; enforce alignment anyway.
    limit=read('tokenizer-stats.json')['max_seq_length']
    for i in range(len(ds)):
        tokens,offset=ds[i]
        assert len(tokens)<=limit and offset<len(tokens)
        explicit=tok.apply_chat_template(metadata[i]['messages'],return_dict=False,enable_thinking=False)
        assert tokens==explicit,'native trainer template differs from frozen tokenizer statistics'
    return ds


def finite(mx,values):
    from mlx.utils import tree_flatten
    flags=[mx.all(mx.isfinite(v)) for k,v in tree_flatten(values)]
    return bool(mx.all(mx.stack(flags)).item()) if flags else True


def smoke():
    integrity()
    import yaml
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
    from mlx_lm.tuner.trainer import default_loss,iterate_batches
    config=yaml.safe_load((OUT/'smoke-config.yaml').read_text())
    if (OUT/'memory-smoke.json').exists():
        prior=read('memory-smoke.json')
        assert prior.get('status')=='not_run' and prior.get('placeholder') is True, 'smoke may only run once; do not retry/shrink'
    state={'status':'running','requested_steps':5,'steps':[],'config':config,
           'started_at':time.time(),'purpose':'backward/finite/memory/time only, no capability inference'}
    save('memory-smoke.json',state)
    try:
        model,tok,identity=model_setup(config); state['model']=identity
        import subprocess
        state['physical_unified_memory_bytes']=int(subprocess.check_output(['sysctl','-n','hw.memsize']))
        state['baseline_memory']=memory(mx); save('memory-smoke.json',state)
        lengths={r['instance_id']:r['total_tokens'] for r in rows('token-lengths.jsonl')}
        selected=[]; used=set()
        for row in sorted(rows('train-metadata.jsonl'),key=lambda r:(-lengths[r['instance_id']],r['instance_id'])):
            if row['seed_id'] not in used:
                selected.append(row); used.add(row['seed_id'])
            if len(selected)==5: break
        state['selected_instances']=[r['instance_id'] for r in selected]
        ds=dataset(tok,selected)
        opt=optim.Adam(learning_rate=config['learning_rate'])
        loss_grad=nn.value_and_grad(model,default_loss)
        model.train(); mx.reset_peak_memory()
        batches=iterate_batches(ds,batch_size=1,max_seq_length=config['max_seq_length'],loop=False)
        for step,batch in enumerate(batches,1):
            started=time.perf_counter()
            (loss,ntoks),grad=loss_grad(model,*batch)
            mx.eval(loss,ntoks,grad); mx.synchronize()
            loss_value=float(loss.item()); grad_ok=finite(mx,grad)
            assert math.isfinite(loss_value) and grad_ok,'NaN/Inf in loss or gradients'
            opt.update(model,grad); mx.eval(model.parameters(),opt.state); mx.synchronize()
            params_ok=finite(mx,model.trainable_parameters()) and finite(mx,opt.state)
            assert params_ok,'NaN/Inf in adapter or optimizer state'
            row={'step':step,'loss':loss_value,'gradients_finite':grad_ok,'parameters_optimizer_finite':params_ok,
                 'wall_seconds':time.perf_counter()-started,'supervised_tokens':int(ntoks.item()),**memory(mx)}
            state['steps'].append(row); save('memory-smoke.json',state)
            append('train-log.jsonl',{'phase':'smoke',**row}); print(canonical(row),flush=True)
            del grad
        assert len(state['steps'])==5
        state['status']='passed'; state['ended_at']=time.time();save('memory-smoke.json',state)
    except BaseException as error:
        state.update(status='failed',error=type(error).__name__+': '+str(error),ended_at=time.time())
        save('memory-smoke.json',state)
        raise


def evaluate(model,tok,metadata,label):
    from mlx_lm import stream_generate
    from mlx_lm.sample_utils import make_sampler
    from backend.services.decision.policy_contracts import parse_decision
    model.eval(); predictions=[]
    for i,row in enumerate(metadata):
        prompt=tok.apply_chat_template(row['messages'][:-1],tokenize=True,return_dict=False,add_generation_prompt=True,enable_thinking=False)
        raw=''; last=None
        for response in stream_generate(model,tok,prompt,max_tokens=64,sampler=make_sampler(temp=0.)):
            raw+=response.text;last=response
        valid=False; local=None
        try:
            local=parse_decision(raw).action_id
            valid=local in row['action_id_mapping'] and last.finish_reason!='length'
        except (ValueError,TypeError): pass
        semantic=row['action_id_mapping'].get(local) if valid else None
        position=row['candidate_order'].index(semantic)+1 if valid else None
        result={'instance_id':row['instance_id'],'seed_id':row['seed_id'],'semantic_family':row['semantic_family'],
            'candidate_count':row['candidate_count'],'permutation':row['permutation'],'raw_output':raw,
            'finish_reason':last.finish_reason if last else None,'valid':valid,'local_id':local,
            'semantic':semantic,'position':position,'correct':valid and semantic==row['gold_semantic_action'],
            'gold_position':row['gold_position'],'gold_id':row['gold_id']}
        predictions.append(result)
        append(label+'-raw.jsonl',result)
        if (i+1)%64==0:print(f'{label}: {i+1}/{len(metadata)}',flush=True)
    byseed=collections.defaultdict(list)
    for r in predictions:byseed[r['seed_id']].append(r)
    def consistent(v):return len(v)==4 and all(x['valid'] for x in v) and len({x['semantic'] for x in v})==1
    def accuracy(v):return sum(r['correct'] for r in v)/len(v) if v else None
    binary=[v for v in byseed.values() if v[0]['candidate_count']==2]
    bias={};deviations=[]
    for n in (2,3):
        group=[r for r in predictions if r['candidate_count']==n]
        pos=collections.Counter(r['position'] for r in group);ids=collections.Counter(r['local_id'] if r['valid'] else None for r in group)
        gp=collections.Counter(r['gold_position'] for r in group);gi=collections.Counter(r['gold_id'] for r in group)
        deviation=max([abs(pos[k]/len(group)-gp[k]/len(group)) for k in range(1,n+1)]+
                      [abs(ids[k]/len(group)-gi[k]/len(group)) for k in [f'a{i}' for i in range(n)]])
        deviations.append(deviation)
        bias[str(n)]={'N':len(group),'predicted_position':{str(k):v for k,v in pos.items()},
          'predicted_action_id':{str(k):v for k,v in ids.items()},'gold_position':dict(gp),
          'gold_action_id':dict(gi),'maximum_share_deviation':deviation}
    metrics={'N':len(predictions),'seeds':len(byseed),'semantic_accuracy':accuracy(predictions),
      'permutation_consistency':sum(consistent(v) for v in byseed.values())/len(byseed),
      'binary_consistency':sum(consistent(v) for v in binary)/len(binary),
      'three_variant_all_correct':sum(all(x['correct'] for x in v if x['permutation'] in 'ABC') for v in byseed.values())/len(byseed),
      'four_variant_all_correct':sum(all(x['correct'] for x in v) for v in byseed.values())/len(byseed),
      'valid_rate':sum(r['valid'] for r in predictions)/len(predictions),
      'strata':{c:{'N':len(v:=[r for r in predictions if r['semantic_family']==c]),'accuracy':accuracy(v)} for c in TEMPLATES},
      'negation_correction_accuracy':accuracy([r for r in predictions if r['semantic_family'] in ('negation','correction')]),
      'tool_vs_answer_accuracy':accuracy([r for r in predictions if r['semantic_family']=='tool_vs_answer']),
      'multi_intent_accuracy':accuracy([r for r in predictions if r['semantic_family']=='multi_intent']),
      'bias':bias,'max_position_id_distribution_deviation':max(deviations)}
    save(label+'.json',metrics);print(label,canonical(metrics),flush=True)
    return metrics


def train():
    integrity()
    assert read('memory-smoke.json')['status']=='passed','smoke must pass before formal training'
    assert not (OUT/'formal-state.json').exists(),'no automatic formal retry'
    import yaml
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
    from mlx.utils import tree_flatten,tree_map
    from mlx_lm.tuner.trainer import default_loss,iterate_batches
    config=yaml.safe_load((OUT/'train-config.yaml').read_text())
    for name,expected in read('TRAIN-FREEZE.json')['sha256'].items():assert sha(OUT/name)==expected
    state={'status':'running','microsteps_completed':0,'checkpoints':[],'config':config}
    save('formal-state.json',state)
    try:
        model,tok,identity=model_setup(config);save('formal-model.json',identity)
        training=rows('train-metadata.jsonl');dev=rows('dev-metadata.jsonl')
        # Fresh adapters have B=0, so this is the unchanged raw checkpoint.
        baseline=evaluate(model,tok,dev,'raw-dev-baseline')
        state['raw_dev_baseline']=baseline;save('formal-state.json',state)
        # One complete deterministic shuffled epoch; no shortest-first sampling.
        random.Random(1807).shuffle(training)
        ds=dataset(tok,training)
        # Preserve exact desired order instead of native iterator's length sort.
        def batches():
            for i in range(len(ds)):
                tokens,offset=ds[i]
                yield mx.array([tokens]),mx.array([[offset,len(tokens)-1]])
        opt=optim.Adam(learning_rate=config['learning_rate']);loss_grad=nn.value_and_grad(model,default_loss)
        accum=None;model.train();mx.reset_peak_memory()
        folder=OUT/'checkpoints';folder.mkdir(exist_ok=False)
        for step,batch in enumerate(batches(),1):
            tic=time.perf_counter();(loss,ntoks),grad=loss_grad(model,*batch)
            mx.eval(loss,grad);assert math.isfinite(float(loss.item())) and finite(mx,grad),'nonfinite loss/grad'
            accum=grad if accum is None else tree_map(lambda a,b:a+b,accum,grad)
            updated=step%8==0
            if updated:
                opt.update(model,tree_map(lambda x:x/8,accum));accum=None
            mx.eval(model.parameters(),opt.state,accum);mx.synchronize()
            if updated:
                assert finite(mx,model.trainable_parameters()) and finite(mx,opt.state),'nonfinite parameters/state'
            append('train-log.jsonl',{'phase':'formal','microstep':step,'optimizer_step':step//8,
                'updated':updated,'loss':float(loss.item()),'wall_seconds':time.perf_counter()-tic,**memory(mx)})
            state['microsteps_completed']=step
            if step%32==0:save('formal-state.json',state);print(f'train {step}/{len(ds)} loss {loss.item():.4f}',flush=True)
            if step%448==0 or step==len(ds):
                assert updated
                cp=folder/f'step-{step:04d}';cp.mkdir()
                mx.save_safetensors(str(cp/'adapters.safetensors'),dict(tree_flatten(model.trainable_parameters())))
                (cp/'adapter_config.json').write_text(canonical(config)+'\n')
                score=evaluate(model,tok,dev,f'dev-step-{step:04d}')
                state['checkpoints'].append({'microstep':step,'path':str(cp),'metrics':score})
                save('formal-state.json',state);model.train();mx.clear_cache()
        assert accum is None
        best=max(state['checkpoints'],key=lambda x:(x['metrics']['semantic_accuracy'],x['metrics']['permutation_consistency'],-x['microstep']))
        selected={'selection_source':'dev only','microstep':best['microstep'],'path':best['path'],
                  'adapter_sha256':sha(Path(best['path'])/'adapters.safetensors'),'config_sha256':sha(OUT/'train-config.yaml')}
        save('selected-checkpoint.json',selected)  # committed BEFORE hidden is loaded
        save('dev-eval.json',{'status':'complete','selected_checkpoint':selected,'metrics':best['metrics'],
            'all_checkpoints':state['checkpoints']})
        model.load_weights(str(Path(best['path'])/'adapters.safetensors'),strict=False)
        train_metrics=evaluate(model,tok,rows('train-metadata.jsonl'),'train-eval')
        assert read('selected-checkpoint.json')==selected
        save('hidden-started.json',{'selected_checkpoint':selected,'started_at':time.time(),'single_pass':True})
        hidden=evaluate(model,tok,rows('hidden-metadata.jsonl'),'hidden-once')
        passed=all(hidden[k]<=v if k.startswith('max_') else hidden[k]>=v for k,v in GATES.items())
        save('hidden-eval.json',{'status':'complete','selected_checkpoint':selected,'metrics':hidden,
          'gates':GATES,'go':passed,'single_pass':True})
        state.update(status='complete',train_accuracy=train_metrics['semantic_accuracy'],
             dev_accuracy=best['metrics']['semantic_accuracy'],hidden_accuracy=hidden['semantic_accuracy'],
             train_dev_gap=train_metrics['semantic_accuracy']-best['metrics']['semantic_accuracy'],
             dev_hidden_gap=best['metrics']['semantic_accuracy']-hidden['semantic_accuracy'],go=passed)
        save('formal-state.json',state);integrity()
    except BaseException as error:
        state.update(status='failed',error=type(error).__name__+': '+str(error));save('formal-state.json',state);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['prepare','tokenize','smoke','train'])
    args=parser.parse_args()
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
    {'prepare':prepare,'tokenize':tokenizer_stats,'smoke':smoke,'train':train}[args.phase]()
