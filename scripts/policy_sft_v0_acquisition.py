#!/usr/bin/env python3
"""Execute corrected frozen Policy data, without editing the frozen generator/scorer.

The user-authorized continuation changes execution sequencing and checkpoint
ranking only. Dataset, prompts, targets, hyperparameters and Hidden gates stay pinned.
"""
import collections
from functools import partial
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import policy_sft_v0 as frozen
OUT=frozen.OUT


def guard():
    for name,expected in frozen.read('FREEZE.json')['sha256'].items():
        assert frozen.sha(OUT/name)==expected, 'data/prompt/split/gate freeze mismatch: '+name
    for name,expected in frozen.read('TRAIN-FREEZE.json')['sha256'].items():
        assert frozen.sha(OUT/name)==expected, 'config/source freeze mismatch: '+name
    # macOS Finder metadata is unrelated to experiment data; no scientific file
    # may change. Keep the previous snapshot intact rather than rewriting it.
    actual=frozen.protected(); previous=frozen.read('protected-before.json')
    for path,expected in previous.items():
        if Path(path).name=='.DS_Store':continue
        assert actual.get(path)==expected, 'existing benchmark/scorer/output changed: '+path
    assert {p for p in actual if Path(p).name!='.DS_Store'}=={
        p for p in previous if Path(p).name!='.DS_Store'}, 'benchmark scientific inventory changed'
    if (OUT/'ACQUISITION-FREEZE.json').exists():
        for path,expected in frozen.read('ACQUISITION-FREEZE.json')['sha256'].items():
            assert frozen.sha(ROOT/path)==expected, 'execution source changed: '+path
    import yaml
    cfg=yaml.safe_load((OUT/'train-config.yaml').read_text())
    assert cfg['num_layers']==8 and cfg['lora_parameters']=={
        'rank':8,'scale':16.,'dropout':0.,'keys':frozen.KEYS_ALL}
    assert cfg['learning_rate']==5e-5 and cfg['batch_size']==1 and cfg['grad_accumulation_steps']==8
    assert cfg['iters']==2688 and cfg['max_seq_length']==384 and cfg['grad_checkpoint'] and cfg['mask_prompt']
    assert frozen.read('experiment.json')['gates']==frozen.GATES
    return cfg


def claim(phase):
    marker=OUT/f'acquisition-{phase}-started.json'
    with marker.open('x') as handle:
        handle.write(frozen.canonical({'phase':phase,'started_at':time.time(),'no_automatic_retry':True})+'\n')


def base_model():
    import mlx.core as mx
    from mlx_lm import load
    from mlx.utils import tree_flatten
    for key,expected in {'mlx':'0.32.0','mlx-lm':'0.31.3','transformers':'5.14.1'}.items():
        assert importlib.metadata.version(key)==expected, key+' version mismatch'
    mx.random.seed(1807)
    model,tok=load(frozen.MODEL,lazy=False)
    quant=[m for _,m in model.named_modules() if hasattr(m,'bits')]
    assert len(model.layers)==24 and quant and all(m.bits==8 and m.group_size==64 for m in quant)
    assert not any('lora_' in k for k,v in tree_flatten(model.parameters()))
    mx.eval(model.parameters());mx.synchronize()
    return model,tok,{'path':frozen.MODEL,'loaded_quantized_modules':len(quant),'no_adapter_loaded':True,
        'libraries':{key:importlib.metadata.version(key) for key in ('mlx','mlx-lm','transformers')},
        'model_config_sha256':frozen.sha(Path(frozen.MODEL)/'config.json')}


def augmented_eval(model,tok,metadata,label,baseline=None):
    # Identical frozen inference and strict semantic scorer. Supplemental fields
    # are aliases/descriptive comparisons, never change validity or correctness.
    assert len(metadata) in (576,2688)
    assert not (OUT/(label+'-raw.jsonl')).exists(), 'no repeated evaluation pass: '+label
    result=frozen.evaluate(model,tok,metadata,label)
    result.update(status='complete',four_permutation_consistency=result['permutation_consistency'],
                  contract_validity=result['valid_rate'],
                  metric_note='frozen permutation_consistency already means all four valid semantic choices agree')
    pred=frozen.rows(label+'-raw.jsonl')
    result['fixed_layout_A_accuracy']=sum(r['correct'] for r in pred if r['permutation']=='A')/(len(pred)//4)
    result['position_distribution']={n:v['predicted_position'] for n,v in result['bias'].items()}
    result['action_id_distribution']={n:v['predicted_action_id'] for n,v in result['bias'].items()}
    if baseline:
        raw={r['instance_id']:r for r in frozen.rows(baseline+'-raw.jsonl')}
        assert set(raw)=={r['instance_id'] for r in pred}
        counts=collections.Counter(('both_correct' if r['correct'] and raw[r['instance_id']]['correct'] else
            'trained_only_correct' if r['correct'] else 'raw_only_correct' if raw[r['instance_id']]['correct'] else
            'both_wrong') for r in pred)
        base=frozen.read(baseline+'.json')
        result['paired_raw_comparison']={'N':len(pred),'counts':dict(counts),
            'semantic_accuracy_delta':result['semantic_accuracy']-base['semantic_accuracy'],
            'four_permutation_consistency_delta':result['permutation_consistency']-base['permutation_consistency'],
            'binary_consistency_delta':result['binary_consistency']-base['binary_consistency']}
    frozen.save(label+'.json',result)
    return result


def baseline():
    guard();claim('baseline')
    state={'status':'running','dataset_freeze_sha256':frozen.sha(OUT/'FREEZE.json'),'hidden_inference_count':0}
    frozen.save('raw-baseline-state.json',state)
    try:
        model,tok,identity=base_model();frozen.save('raw-baseline-model.json',identity)
        dev=frozen.rows('dev-metadata.jsonl')
        frozen.dataset(tok,dev)  # tokenizer/alignment/full-gold checks, no hidden
        result=augmented_eval(model,tok,dev,'raw-dev-baseline')
        state.update(status='complete',metrics=result,model=identity,ended_at=time.time())
        frozen.save('raw-baseline-state.json',state);guard()
    except BaseException as error:
        state.update(status='failed',error=type(error).__name__+': '+str(error));frozen.save('raw-baseline-state.json',state);raise


def engine(model,config):
    """Native MLX-LM compiled stateful accumulation, with finite checks outside.

    Pad to the frozen maximum (384), never truncate, to keep compiled graph
    shapes constant; causal padding cannot affect the supervised prefix.
    """
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
    from mlx.utils import tree_map
    from mlx_lm.tuner.trainer import default_loss
    opt=optim.Adam(learning_rate=config['learning_rate'])
    opt.init(model.trainable_parameters())
    mx.eval(opt.state)
    loss_grad=nn.value_and_grad(model,default_loss)
    state=[model.state,opt.state,mx.random.state]

    @partial(mx.compile,inputs=state,outputs=state)
    def step(batch,previous_grad,do_update):
        (loss,ntoks),grad=loss_grad(model,*batch)
        grad=grad if previous_grad is None else tree_map(lambda a,b:a+b,grad,previous_grad)
        # Verify each microgradient independently, not only the accumulated one.
        if do_update:
            opt.update(model,tree_map(lambda x:x/8,grad))
        return loss,ntoks,grad

    def batch(ds,index):
        tokens,offset=ds[index]
        assert len(tokens)<=384 and offset<len(tokens), 'tokenizer truncation/empty gold'
        padded=tokens+[0]*(384-len(tokens))
        return mx.array([padded]),mx.array([[offset,len(tokens)-1]])
    return opt,step,batch


def corrected_smoke():
    config=guard();assert frozen.read('raw-baseline-state.json')['status']=='complete'
    claim('smoke')
    import mlx.core as mx
    state={'status':'running','requested_microsteps':5,'steps':[],
           'config':config,'optimizer_updates':0,'started_at':time.time(),
           'purpose':'formal configuration backward/finite/resource checks, not task acquisition',
           'dataset_freeze_sha256':frozen.sha(OUT/'FREEZE.json')}
    frozen.save('corrected-memory-smoke.json',state)
    try:
        model,tok,identity=frozen.model_setup(config);state['model']=identity
        state['physical_unified_memory_bytes']=int(subprocess.check_output(['sysctl','-n','hw.memsize']))
        lengths={r['instance_id']:r['total_tokens'] for r in frozen.rows('token-lengths.jsonl')}
        selected=[];seen=set()
        for row in sorted(frozen.rows('train-metadata.jsonl'),key=lambda r:(-lengths[r['instance_id']],r['instance_id'])):
            if row['seed_id'] not in seen:selected.append(row);seen.add(row['seed_id'])
            if len(selected)==5:break
        state['selected_instances']=[r['instance_id'] for r in selected]
        ds=frozen.dataset(tok,selected)
        opt,step,batch=engine(model,config);accum=None;model.train();mx.reset_peak_memory()
        frozen.save('corrected-memory-smoke.json',state)
        for index in range(5):
            tic=time.perf_counter();loss,ntoks,grad=step(batch(ds,index),accum,False)
            mx.eval(model.state,opt.state,loss,ntoks,grad);mx.synchronize()
            loss_value=float(loss.item())
            assert math.isfinite(loss_value),'NaN/Inf loss'
            grad_ok=frozen.finite(mx,grad)
            adapter_ok=frozen.finite(mx,model.trainable_parameters())
            optimizer_ok=frozen.finite(mx,opt.state)
            assert grad_ok and adapter_ok and optimizer_ok,'NaN/Inf gradient/adapter/optimizer'
            accum=grad
            row={'microstep':index+1,'optimizer_update':False,'loss':loss_value,
                'gradient_finite':grad_ok,'adapter_finite':adapter_ok,'optimizer_state_finite':optimizer_ok,
                'wall_seconds':time.perf_counter()-tic,'supervised_tokens':int(ntoks.item()),**frozen.memory(mx)}
            state['steps'].append(row);frozen.save('corrected-memory-smoke.json',state)
            frozen.append('train-log.jsonl',{'phase':'corrected_smoke',**row});print(frozen.canonical(row),flush=True)
        assert int(opt.step.item())==0,'5 microsteps with accumulation8 must not update'
        state.update(status='passed',ended_at=time.time(),weights_discarded=True)
        frozen.save('corrected-memory-smoke.json',state);guard()
    except BaseException as error:
        state.update(status='failed',error=type(error).__name__+': '+str(error))
        frozen.save('corrected-memory-smoke.json',state);raise


def formal():
    config=guard()
    assert frozen.read('corrected-memory-smoke.json')['status']=='passed'
    assert frozen.read('raw-baseline-state.json')['status']=='complete'
    claim('train')
    import mlx.core as mx
    from mlx.utils import tree_flatten
    state={'status':'running','config':config,'microsteps_completed':0,'optimizer_updates':0,
           'checkpoints':[],'fresh_adapter':True,'hidden_inference_count':0,'started_at':time.time()}
    frozen.save('acquisition-state.json',state)
    frozen.save('checkpoint-dev-evals.json',{'status':'running','checkpoints':[]})
    try:
        # New process/model/Adam; no smoke parameters or gradient accumulation.
        model,tok,identity=frozen.model_setup(config);frozen.save('acquisition-model.json',identity)
        training=frozen.rows('train-metadata.jsonl');random.Random(1807).shuffle(training)
        ds=frozen.dataset(tok,training);dev=frozen.rows('dev-metadata.jsonl')
        opt,step,batch=engine(model,config);accum=None;model.train();mx.reset_peak_memory()
        folder=OUT/'acquisition-checkpoints';folder.mkdir(exist_ok=False)
        all_losses=[];window_losses=[]
        for index in range(2688):
            microstep=index+1;update=microstep%8==0;tic=time.perf_counter()
            loss,ntoks,grad=step(batch(ds,index),accum,update)
            mx.eval(model.state,opt.state,loss,ntoks,grad);mx.synchronize()
            value=float(loss.item());assert math.isfinite(value),'NaN/Inf loss'
            assert frozen.finite(mx,grad),'NaN/Inf gradient'
            assert frozen.finite(mx,model.trainable_parameters()) and frozen.finite(mx,opt.state),'NaN/Inf adapter/state'
            accum=None if update else grad
            all_losses.append(value);window_losses.append(value)
            record={'phase':'acquisition','microstep':microstep,'optimizer_updates':int(opt.step.item()),
                    'updated':update,'loss':value,'all_finite':True,'wall_seconds':time.perf_counter()-tic,
                    'supervised_tokens':int(ntoks.item()),**frozen.memory(mx)}
            frozen.append('train-log.jsonl',record)
            state.update(microsteps_completed=microstep,optimizer_updates=int(opt.step.item()))
            if microstep%16==0:
                frozen.save('acquisition-state.json',state)
                print(f'train {microstep}/2688 updates={opt.step.item()} loss={value:.5f} step_s={record["wall_seconds"]:.3f}',flush=True)
            if microstep%448==0:
                assert update and accum is None
                cp=folder/f'step-{microstep:04d}';cp.mkdir()
                mx.save_safetensors(str(cp/'adapters.safetensors'),dict(tree_flatten(model.trainable_parameters())))
                (cp/'adapter_config.json').write_text(frozen.canonical(config)+'\n')
                score=augmented_eval(model,tok,dev,f'acquisition-dev-step-{microstep:04d}',baseline='raw-dev-baseline')
                checkpoint={'microstep':microstep,'optimizer_updates':int(opt.step.item()),'path':str(cp),
                    'adapter_sha256':frozen.sha(cp/'adapters.safetensors'),
                    'train_loss_epoch_mean':sum(all_losses)/len(all_losses),
                    'train_loss_window_mean':sum(window_losses)/len(window_losses),'metrics':score}
                state['checkpoints'].append(checkpoint);window_losses=[]
                frozen.save('checkpoint-dev-evals.json',{'status':'running','checkpoints':state['checkpoints']})
                frozen.save('acquisition-state.json',state);model.train();mx.clear_cache()
        assert int(opt.step.item())==336 and accum is None
        def ranking(c):
            m=c['metrics']
            return (m['semantic_accuracy'],m['permutation_consistency'],m['binary_consistency'],
                    m['negation_correction_accuracy'],-m['max_position_id_distribution_deviation'],-c['microstep'])
        best=max(state['checkpoints'],key=ranking)
        selected={'selection_source':'dev only','microstep':best['microstep'],'path':best['path'],
            'adapter_sha256':best['adapter_sha256'],'training_config_sha256':frozen.sha(OUT/'train-config.yaml'),
            'dataset_freeze_sha256':frozen.sha(OUT/'FREEZE.json'),
            'ranking':['semantic_accuracy','permutation_consistency','binary_consistency',
                       'negation_correction_accuracy','lowest_position_id_deviation','earliest_step'],
            'selected_before_train_replay_and_hidden':True,'selected_at':time.time()}
        with (OUT/'dev-best-checkpoint.json').open('x') as h:h.write(frozen.canonical(selected)+'\n')
        frozen.save('checkpoint-dev-evals.json',{'status':'complete','checkpoints':state['checkpoints'],'selected':selected})
        frozen.save('dev-eval.json',{'status':'complete','selected_checkpoint':selected,'metrics':best['metrics']})
        model.load_weights(str(Path(best['path'])/'adapters.safetensors'),strict=False)
        mx.eval(model.parameters());mx.synchronize()
        replay=augmented_eval(model,tok,frozen.rows('train-metadata.jsonl'),'train-replay')
        assert frozen.read('dev-best-checkpoint.json')==selected
        guard()
        # Create the once-only receipt before reading any Hidden instances.
        with (OUT/'acquisition-hidden-started.json').open('x') as h:
            h.write(frozen.canonical({'selected':selected,'started_at':time.time(),'single_pass':True})+'\n')
        hidden=augmented_eval(model,tok,frozen.rows('hidden-metadata.jsonl'),'acquisition-hidden-once')
        go=all(hidden[k]<=v if k.startswith('max_') else hidden[k]>=v for k,v in frozen.GATES.items())
        frozen.save('hidden-eval.json',{'status':'complete','metrics':hidden,'selected_checkpoint':selected,
                      'gates':frozen.GATES,'go':go,'single_pass':True})
        state.update(status='complete',selected=selected,train_accuracy=replay['semantic_accuracy'],
            dev_accuracy=best['metrics']['semantic_accuracy'],hidden_accuracy=hidden['semantic_accuracy'],
            train_dev_gap=replay['semantic_accuracy']-best['metrics']['semantic_accuracy'],
            dev_hidden_gap=best['metrics']['semantic_accuracy']-hidden['semantic_accuracy'],
            go=go,hidden_inference_count=576,ended_at=time.time())
        frozen.save('acquisition-state.json',state);guard()
    except BaseException as error:
        state.update(status='failed',error=type(error).__name__+': '+str(error));frozen.save('acquisition-state.json',state);raise


def monitor(phase):
    guard()
    path=OUT/f'acquisition-{phase}-monitor.json';assert not path.exists(),'no automatic retry'
    worker='/Users/jichengqian/.lmstudio/extensions/backends/vendor/_amphibian/app-mlx-generate-mac14-arm64@34/bin/python'
    env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false'}
    start=time.time()
    with (OUT/f'acquisition-{phase}-console.log').open('x') as log:
        process=subprocess.Popen([worker,__file__,phase],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        state={'phase':phase,'pid':process.pid,'status':'running','started_at':start,'rss_peak_bytes':0,'samples':0}
        while process.poll() is None:
            try:
                value=int(subprocess.check_output(['ps','-o','rss=','-p',str(process.pid)],text=True,stderr=subprocess.DEVNULL).strip())*1024
                state.update(rss_peak_bytes=max(state['rss_peak_bytes'],value),last_rss_bytes=value,samples=state['samples']+1)
            except (ValueError,subprocess.CalledProcessError):pass
            path.write_text(json.dumps(state,indent=2)+'\n');time.sleep(.25)
        state.update(status='complete' if process.returncode==0 else 'failed',exit_code=process.returncode,
                     elapsed_seconds=time.time()-start)
        path.write_text(json.dumps(state,indent=2)+'\n')
        if process.returncode:
            name={'baseline':'raw-baseline-state.json','smoke':'corrected-memory-smoke.json','train':'acquisition-state.json'}[phase]
            result=frozen.read(name) if (OUT/name).exists() else {}
            result.update(status='failed',process_exit_code=process.returncode,process_monitor=state,no_retry=True)
            if 'error' not in result:result['error']='worker aborted; inspect console; MLX peak may be unavailable'
            frozen.save(name,result)
        print(json.dumps(state,indent=2),flush=True)
    return 0 if process.returncode==0 else 1


if __name__=='__main__':
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
    import argparse
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['baseline','smoke','train']);p.add_argument('--monitor',action='store_true')
    a=p.parse_args()
    if a.monitor:sys.exit(monitor(a.phase))
    {'baseline':baseline,'smoke':corrected_smoke,'train':formal}[a.phase]()
