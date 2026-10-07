#!/usr/bin/env python3
"""Gemma foundation screening: existing prompts, scorer and ModelAdapter only."""
import argparse
import collections
import copy
import hashlib
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from diagnose_runtime_08b import read, save, lines, append, PROMPT_VERSION
from probe_policy_permutation import variants, protected
from evaluation.runtime_benchmark.adapter import ProcessAdapter
from evaluation.runtime_benchmark.scoring import Benchmark
from evaluation.runtime_benchmark.prompting import PromptBuilder
from evaluation.runtime_benchmark.runner import run, replay
from evaluation.runtime_benchmark.diagnostics import performance
from evaluation.runtime_benchmark.reporting import jsonl
from runtime_08b_probe_analysis import field_analysis, summarize

REPO = 'mlx-community/gemma-3-1b-it-8bit'
REV = '7b963136f21d05ca8b367c93a9c47a7944ad281a'

def integrity():
    values = protected()
    # Adapter is intentionally generalized; frozen inputs and other harness modules are protected.
    for p in (ROOT/'evaluation/runtime_benchmark').glob('*.py'):
        if p.name != 'adapter.py':
            values[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    folder=ROOT/'docs/validation/runtime-benchmark-v0.1/policy-permutation-20261006'
    for p in folder.rglob('*'):
        if p.is_file(): values[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    return values

def prepare(out):
    b=Benchmark(); out.mkdir(parents=True, exist_ok=False)
    config=read(ROOT/'docs/runtime-benchmark-v0.1/local-qwen35-8bit.config.json')
    config.update(model_id=REPO, model_path=str(Path.home()/'.cache/huggingface/hub'/('models--'+REPO.replace('/','--'))/'snapshots'/REV), template={}, v0_failure_exposed=True)
    save(out/'config.json',config)
    save(out/'protected-before.json',integrity())
    save(out/'experiment.json',{'repo':REPO,'revision':REV,'policy_prompt_version':PROMPT_VERSION,
        'policy_requests':240,'semantic_requests':200,'gate':'stop if any arm selects a single position or ID >=95% of all 80 planned cases',
        'greedy':True,'temperature':0,'batch':1,'retry':False,'self_correction':False,'best_of':False,
        'thinking':'not_applicable','prompt_tuning':False,'freeze_sha256':b.freeze_hash,
        'comparison':'permutation uses unchanged existing diagnostic prompts; full semantic uses unchanged official frozen prompts'})
    old=ROOT/'docs/validation/runtime-benchmark-v0.1/policy-permutation-20261006'
    for arm in 'ABC':
        jobs=[variants(r,b.scorer.canonical)[arm]['job'] for r in b.rows if r['task']=='policy_select']
        assert jobs==lines(old/f'jobs-{arm}.jsonl')
        jsonl(out/f'jobs-{arm}.jsonl',jobs)
    save(out/'semantic-mapping.json',read(old/'semantic-mapping.json'))

def smoke(out):
    b=Benchmark(); builder=PromptBuilder(b); config=read(out/'config.json')
    folder=out/'smoke'; folder.mkdir(exist_ok=False)
    adapter=ProcessAdapter(config['inference_python']); state={'status':'running','purpose':'three_task_smoke','config':config}
    save(folder/'run.json',state)
    records=[]
    try:
        state['model']=adapter.load({**config,'_stderr_path':str(folder/'inference-stderr.log')})
        for task in ('policy_select','goal_summary','question_understanding'):
            row=next(r for r in b.select('primary_semantic') if r['task']==task)
            messages=builder.build({k:row[k] for k in ('id','task','input')})
            result=adapter.generate(messages,{'temperature':0,'max_new_tokens':config['max_new_tokens'][task]})
            records.append({**result,'case_id':row['id'],'task':task,'messages':messages})
            jsonl(folder/'outputs.jsonl',records)
            assert result['status']=='ok',result['error']
        state['scores']=[b.scorer.evaluate(b.by_id[r['case_id']],r['raw_output']) for r in records]
        state['status']='complete'
    finally:
        state['memory']=adapter.close(); save(folder/'run.json',state)
    print('Three-task smoke complete; no prompt changes.',flush=True)

def permutation(out):
    config=read(out/'config.json'); folder=out/'permutation'; folder.mkdir(exist_ok=False)
    adapter=ProcessAdapter(config['inference_python']); state={'status':'running','config':config,'completed_requests':0,'purpose':'policy_permutation'}
    save(folder/'run.json',state)
    try:
        state['model']=adapter.load({**config,'_stderr_path':str(folder/'inference-stderr.log')})
        save(folder/'run.json',state)
        for arm in 'ABC':
            dest=folder/f'arm-{arm}'; dest.mkdir()
            with (dest/'outputs.jsonl').open('x') as raw, (dest/'requests.jsonl').open('x') as req:
                for i,job in enumerate(lines(out/f'jobs-{arm}.jsonl')):
                    result=adapter.generate(job['messages'],{'temperature':0,'max_new_tokens':job['max_new_tokens']})
                    append(raw,{**result,'case_id':job['case_id'],'task':job['task'],'variant':arm})
                    append(req,{**job,'rendered_prompt':result['rendered_prompt']})
                    state['completed_requests']+=1
                    save(folder/'run.json',state)
                    assert result['status']=='ok',result['error']
                    print(f'Permutation {arm} {i+1}/80',flush=True)
        state['status']='complete'
    finally:
        state['memory']=adapter.close(); save(folder/'run.json',state)
    return analyze_permutation(out)

def analyze_permutation(out):
    b=Benchmark(); rows=[r for r in b.rows if r['task']=='policy_select']; mapping=read(out/'semantic-mapping.json')['variants']
    paired={r['id']:{} for r in rows}; summaries={}; all_records=[]; failures=[]
    for arm in 'ABC':
        records=lines(out/'permutation'/f'arm-{arm}'/'outputs.jsonl')
        assert len(records)==80
        for row,record in zip(rows,records):
            m=mapping[arm][row['id']]; local=None
            changed=copy.deepcopy(row); changed['input']=variants(row,b.scorer.canonical)[arm]['job']['input']; changed['gold']={'action_id':m['variant_gold_id']}
            score=b.scorer.evaluate(changed,record['raw_output'])
            if score['executable']:
                local=b.scorer.json_strict(record['raw_output'])['action_id']
            value={'local_id':local,'position':m['local_to_position'].get(local),'semantic_id':m['local_to_semantic'].get(local),
                   'valid':score['executable'],'correct':score['structured_match']}
            paired[row['id']][arm]=value
            enriched={**record,'phase':'permutation','official':score,**value}; all_records.append(enriched)
            if not score['structured_match']:failures.append(enriched)
        vals=[paired[r['id']][arm] for r in rows]
        summaries[arm]={'N':80,'semantic_correct':sum(v['correct'] for v in vals),
            'contract_valid':sum(v['valid'] for v in vals),
            'position_preference':{str(i):sum(v['position']==i for v in vals) for i in (1,2,3)},
            'id_preference':{i:sum(v['local_id']==i for v in vals) for i in ('a0','a1','a2')},
            'strata':{g:{'N':sum(('multi_intent_order' in r['tags'])==(g=='multi_intent_order') for r in rows),
                'correct':sum(paired[r['id']][arm]['correct'] for r in rows if ('multi_intent_order' in r['tags'])==(g=='multi_intent_order'))}
                for g in ('tool_vs_answer','multi_intent_order')}}
    stable=lambda r: all(paired[r['id']][a]['valid'] for a in 'ABC') and len({paired[r['id']][a]['semantic_id'] for a in 'ABC'})==1
    metrics={'summaries':summaries,'pairs':{x+y:sum(paired[r['id']][x]['valid'] and paired[r['id']][y]['valid'] and paired[r['id']][x]['semantic_id']==paired[r['id']][y]['semantic_id'] for r in rows) for x,y in [('A','B'),('A','C'),('B','C')]},
        'three_variant_semantic_consistency':sum(stable(r) for r in rows),
        'three_variant_correct':sum(all(paired[r['id']][a]['correct'] for a in 'ABC') for r in rows),
        'binary_stable':sum(stable(r) for r in rows if len(r['input']['admissible_actions'])==2),
        'binary_N':sum(len(r['input']['admissible_actions'])==2 for r in rows),'paired_cases':paired}
    metrics['catastrophic_shortcut']=any(max(s[k].values())/80>=.95 for s in summaries.values() for k in ('position_preference','id_preference'))
    records=all_records
    jsonl(out/'results.jsonl',records); jsonl(out/'failures.jsonl',failures)
    metrics['performance']=performance(records)
    save(out/'permutation-metrics.json',metrics)
    return metrics

def fields(out):
    b=Benchmark(); details=[]
    outputs=lines(out/'semantic_all/outputs.jsonl')
    for record in outputs:
        row=b.by_id[record['case_id']]
        if row['task']=='reference_resolve': continue
        details.append(field_analysis(row,record,b.scorer))
    save(out/'field-diagnostics.json',{'by_task':{t:summarize([d for d in details if d['task']==t]) for t in sorted({d['task'] for d in details})},'cases':details})
    jsonl(out/'results.jsonl',lines(out/'results.jsonl')+[{**r,'phase':'semantic','official':b.scorer.evaluate(b.by_id[r['case_id']],r['raw_output'])} for r in outputs])
    jsonl(out/'failures.jsonl',lines(out/'failures.jsonl')+[{**r,'phase':'semantic'} for r in lines(out/'semantic_all/failures.jsonl')])

def execute(out):
    state={'status':'running','experiment':read(out/'experiment.json')}; save(out/'run.json',state)
    try:
        smoke(out); metrics=permutation(out)
        state['permutation_gate']='stop_position_or_ID_shortcut' if metrics['catastrophic_shortcut'] else 'continue'
        save(out/'run.json',state)
        if not metrics['catastrophic_shortcut']:
            b=Benchmark(); config=read(out/'config.json')
            for scope in ('primary_semantic','secondary_semantic'):
                print('Starting '+scope,flush=True)
                s=run(b,scope,config,out/scope)
                assert s['status']=='complete',s['error']
            replay(b,[out/'primary_semantic',out/'secondary_semantic'],'semantic_all',out/'semantic_all')
            fields(out)
        assert integrity()==read(out/'protected-before.json'),'Protected baseline/harness changed'
        state.update(status='complete',protected_unchanged=True,checked_files=len(integrity()))
    except BaseException as error:
        state.update(status='incomplete',error=type(error).__name__+': '+str(error)); raise
    finally:
        save(out/'run.json',state)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','execute']);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    (prepare if a.mode=='prepare' else execute)(a.out.resolve())
