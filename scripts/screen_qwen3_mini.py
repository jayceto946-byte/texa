#!/usr/bin/env python3
"""Fixed 20-case mini screening; no full-run branch or gold-aware inference."""
import argparse,copy,hashlib,json,math,struct,subprocess,sys,collections
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from screen_gemma_runtime import read,save,lines,append,smoke
from probe_policy_permutation import variants
from evaluation.runtime_benchmark.scoring import Benchmark
from evaluation.runtime_benchmark.adapter import ProcessAdapter,snapshot_identity
from evaluation.runtime_benchmark.diagnostics import extract,performance
from evaluation.runtime_benchmark.reporting import jsonl

REPO='mlx-community/Qwen3-0.6B-8bit';REV='11de96878523501bcaa86104e3c186de07ff9068'
BASE=ROOT/'docs/validation/runtime-benchmark-v0.1/policy-permutation-20261006'
TOOL=(1,2,5,6,7,8,29,30,37,38)
MULTI=(61,62,67,68,69,70,71,72,79,80)
IDS=[f'TRB0-{i:04d}' for i in TOOL+MULTI]

def check_protected(out):
    hashes=read(out/'protected-before.json')
    assert all((ROOT/p).is_file() and hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha for p,sha in hashes.items())
    return len(hashes)

def audit(config,out):
    path=Path(config['model_path']);identity=snapshot_identity(path)
    assert identity['model_type']=='qwen3'
    assert 'base_model: Qwen/Qwen3-0.6B\n' in (path/'README.md').read_text()
    tok=read(path/'tokenizer_config.json');assert 'enable_thinking' in tok['chat_template'] and tok['eos_token']=='<|im_end|>'
    with (path/'model.safetensors').open('rb') as f:
        h=json.loads(f.read(struct.unpack('<Q',f.read(8))[0]))
    tensors={k:v for k,v in h.items() if k!='__metadata__'}
    count=0
    for k,v in tensors.items():
        if k.endswith(('.scales','.biases')):continue
        n=math.prod(v['shape']);count+=n*4 if v['dtype']=='U32' and k.endswith('.weight') else n
    assert 550_000_000 < count < 650_000_000, 'wrong parameter scale'
    cache=path.parent.parent
    result={'repo':REPO,'revision':REV,'local_path':str(path),'config':read(path/'config.json'),
        'parameter_count':count,'parameter_count_method':'reconstruct packed U32 8bit weight elements x4; exclude scales/biases; tied lm_head not separately exported',
        'post_trained_source':'Qwen/Qwen3-0.6B','not_base_attestation':'MLX revision README declares exact upstream post-trained source; native thinking/nonthinking template matches official Qwen card',
        'upstream_card':'https://huggingface.co/Qwen/Qwen3-0.6B',
        'weight_dtypes':dict(collections.Counter(v['dtype'] for v in tensors.values())),
        'tokenizer_class':tok['tokenizer_class'],'chat_template':tok['chat_template'],
        'chat_template_sha256':hashlib.sha256(tok['chat_template'].encode()).hexdigest(),
        'allocated_disk_bytes':int(subprocess.check_output(['du','-sk',str(cache)],text=True).split()[0])*1024,
        'snapshot_logical_bytes':sum(p.stat().st_size for p in path.iterdir() if p.is_file()),
        'cache_path':str(cache),'no_duplicate_weights':True,
        'files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'resolved_blob':str(p.resolve())} for p in path.iterdir() if p.is_file()}}
    save(out/'model-audit.json',result)

def prepare(out):
    assert not (out/'experiment.json').exists()
    b=Benchmark();rows=[b.by_id[i] for i in IDS]
    assert len(rows)==20 and len(set(IDS))==20
    assert sum('multi_intent_order' in r['tags'] for r in rows)==10
    assert collections.Counter(r['gold']['action_id'] for r in rows)=={'a0':10,'a1':10}
    config=read(ROOT/'docs/runtime-benchmark-v0.1/local-qwen35-8bit.config.json')
    config.update(model_id=REPO,model_path=str(Path.home()/'.cache/huggingface/hub'/('models--'+REPO.replace('/','--'))/'snapshots'/REV),template={'enable_thinking':False},v0_failure_exposed=True)
    audit(config,out);save(out/'config.json',config)
    selected=[]
    for r in rows:
        selected.append({'id':r['id'],'group':'multi_intent_order' if 'multi_intent_order' in r['tags'] else 'tool_vs_answer',
            'request':r['input']['request'],'tags':r['tags'],'gold':r['gold'],'candidate_count':len(r['input']['admissible_actions'])})
    save(out/'selection.json',{'locked_before_inference':True,'selected_cases':selected,'selection_rule':'five matched intent-contrast pairs per stratum; input/gold balance only, not existing model correctness',
        'coverage':'progress/exercise lookup, direct answer, explicit negation/correction, noisy wording, quoted instruction, ordering, priority, ordinal reference',
        'tool_group_pairs':[[1,2],[5,6],[7,8],[29,30],[37,38]],'multi_group_pairs':[[61,62],[67,68],[69,70],[71,72],[79,80]],
        'gold_semantic_id_counts':{'a0':10,'a1':10},'binary_cases':10,'ternary_cases':10,
        'limitations':'purposive exposed author-frozen mini set, deliberately oversamples multi-intent (50% vs original25%); not held-out or representative population accuracy'})
    mapping={}
    for arm in 'ABC':
        jobs=[variants(r,b.scorer.canonical)[arm]['job'] for r in rows]
        old={j['case_id']:j for j in lines(BASE/f'jobs-{arm}.jsonl')}
        assert all(j==old[j['case_id']] for j in jobs)
        jsonl(out/f'jobs-{arm}.jsonl',jobs)
        mapping[arm]={r['id']:variants(r,b.scorer.canonical)[arm]['mapping'] for r in rows}
    save(out/'semantic-mapping.json',{'variants':mapping})
    save(out/'experiment.json',{'repo':REPO,'revision':REV,'created_at':datetime.now(timezone.utc).isoformat(),'case_ids':IDS,
        'planned_smoke':3,'planned_policy':60,'no_full_benchmark':True,'freeze_sha256':b.freeze_hash,
        'prompt':'exact unchanged subset of existing exposed-dev permutation jobs',
        'generation':{'greedy':True,'temperature':0,'batch':1,'retry':False,'self_correction':False,'constrained_decoding':False,'max_new_tokens':128,'thinking':False},
        'jobs_sha256':{a:hashlib.sha256((out/f'jobs-{a}.jsonl').read_bytes()).hexdigest() for a in 'ABC'}})
    check_protected(out)
    print('Locked 20 cases: 10 per group, gold a0/a1 balanced 10/10.',flush=True)

def infer(out):
    check_protected(out);config=read(out/'config.json');exp=read(out/'experiment.json')
    assert all(hashlib.sha256((out/f'jobs-{a}.jsonl').read_bytes()).hexdigest()==exp['jobs_sha256'][a] for a in 'ABC')
    state={'status':'running','purpose':'policy_foundation_mini_screening','started_at':datetime.now(timezone.utc).isoformat(),'experiment':exp,'completed_requests':0,'config':config}
    save(out/'run.json',state)
    try:
        smoke(out)
        folder=out/'permutation';folder.mkdir(exist_ok=False)
        adapter=ProcessAdapter(config['inference_python'])
        try:
            state['model']=adapter.load({**config,'_stderr_path':str(folder/'inference-stderr.log')});save(out/'run.json',state)
            for arm in 'ABC':
                dest=folder/f'arm-{arm}';dest.mkdir()
                with (dest/'outputs.jsonl').open('x') as raw,(dest/'requests.jsonl').open('x') as req:
                    for i,job in enumerate(lines(out/f'jobs-{arm}.jsonl')):
                        result=adapter.generate(job['messages'],{'temperature':0,'max_new_tokens':128})
                        append(raw,{**result,'case_id':job['case_id'],'variant':arm,'task':job['task']})
                        append(req,{**job,'rendered_prompt':result['rendered_prompt']})
                        state['completed_requests']+=1;save(out/'run.json',state)
                        assert result['status']=='ok',result['error']
                        print(f'{arm} {i+1}/20',flush=True)
        finally:
            state['memory']=adapter.close()
        state.update(status='complete',protected_files=check_protected(out),protected_unchanged=True,finished_at=datetime.now(timezone.utc).isoformat())
    except BaseException as error:
        state.update(status='incomplete',error=type(error).__name__+': '+str(error));raise
    finally:
        save(out/'run.json',state)

def analyze_model(out,records,recover=False):
    b=Benchmark();mapping=read(out/'semantic-mapping.json')['variants'];pair={i:{} for i in IDS};details=[]
    assert len(records)==60
    for x in records:
        arm=x['variant'];r=b.by_id[x['case_id']];m=mapping[arm][r['id']]
        row=copy.deepcopy(r);row['input']=variants(r,b.scorer.canonical)[arm]['job']['input'];row['gold']={'action_id':m['variant_gold_id']}
        raw=x['raw_output'];extraction=extract(raw,b.scorer.json_strict) if recover else None
        score=b.scorer.evaluate(row,extraction['extracted_text'] if recover else raw)
        local=b.scorer.json_strict(extraction['extracted_text'] if recover else raw)['action_id'] if score['executable'] else None
        v={'valid':score['executable'],'correct':score['structured_match'],'semantic_id':m['local_to_semantic'].get(local),'position':m['local_to_position'].get(local),'local_id':local}
        pair[r['id']][arm]=v;details.append({**x,**v,'official':score,'recovery':extraction})
    sums={}
    for arm in 'ABC':
        vals=[pair[i][arm] for i in IDS]
        sums[arm]={'N':20,'semantic_correct':sum(v['correct'] for v in vals),'contract_valid':sum(v['valid'] for v in vals),
            'positions':{str(n):sum(v['position']==n for v in vals) for n in (1,2,3)},'ids':{i:sum(v['local_id']==i for v in vals) for i in ('a0','a1','a2')},
            'strata':{g:{'N':10,'correct':sum(pair[f'TRB0-{i:04d}'][arm]['correct'] for i in nums)} for g,nums in [('tool_vs_answer',TOOL),('multi_intent_order',MULTI)]}}
    stable=lambda i:all(pair[i][a]['valid'] for a in 'ABC') and len({pair[i][a]['semantic_id'] for a in 'ABC'})==1
    metrics={'diagnostic_recovery':recover,'arms':sums,'three_variant_consistency':sum(stable(i) for i in IDS),
        'three_variant_all_correct':sum(all(pair[i][a]['correct'] for a in 'ABC') for i in IDS),
        'binary_consistency':sum(stable(f'TRB0-{i:04d}') for i in TOOL),'binary_N':10,
        'pairwise_consistency':{l+r:sum(pair[i][l]['valid'] and pair[i][r]['valid'] and pair[i][l]['semantic_id']==pair[i][r]['semantic_id'] for i in IDS) for l,r in [('A','B'),('A','C'),('B','C')]},'paired_cases':pair}
    return metrics,details

def analyze(out):
    assert read(out/'run.json')['status']=='complete';check_protected(out)
    records=[];oldrecords=[]
    for arm in 'ABC':
        rs=lines(out/'permutation'/f'arm-{arm}/outputs.jsonl');req=lines(out/'permutation'/f'arm-{arm}/requests.jsonl');jobs=lines(out/f'jobs-{arm}.jsonl')
        assert len(rs)==len(req)==20
        for x,q,j in zip(rs,req,jobs):
            assert x['case_id']==q['case_id']==j['case_id'] and q['messages']==j['messages'] and q['rendered_prompt']==x['rendered_prompt']
        records+=rs
        old={x['case_id']:x for x in lines(BASE/f'arm-{arm}/outputs.jsonl')}
        oldrequests={x['case_id']:x for x in lines(BASE/f'arm-{arm}/requests.jsonl')}
        for j in jobs:
            assert oldrequests[j['case_id']]['messages']==j['messages']
            oldrecords.append(old[j['case_id']])
    g,det=analyze_model(out,records);q,qdet=analyze_model(out,oldrecords)
    gr,_=analyze_model(out,records,True);qr,_=analyze_model(out,oldrecords,True)
    result={'qwen3_06b':g,'qwen35_08b_paired':q,'recovery_diagnostic':{'qwen3_06b':gr,'qwen35_08b':qr},'performance':{'qwen3_06b':performance(records),'qwen35_08b_same_60_cases':performance(oldrecords)},
        'paired_outcomes':{a:{'both_correct':sum(g['paired_cases'][i][a]['correct'] and q['paired_cases'][i][a]['correct'] for i in IDS),
            'qwen3_only':sum(g['paired_cases'][i][a]['correct'] and not q['paired_cases'][i][a]['correct'] for i in IDS),
            'qwen35_only':sum(not g['paired_cases'][i][a]['correct'] and q['paired_cases'][i][a]['correct'] for i in IDS)} for a in 'ABC'}}
    save(out/'metrics.json',result);jsonl(out/'results.jsonl',det);jsonl(out/'failures.jsonl',[x for x in det if not x['correct']]);save(out/'paired-qwen35-records.json',qdet)
    save(out/'integrity.json',{'protected_files':check_protected(out),'unchanged':True,'freeze_sha256':Benchmark().freeze_hash})
    print(json.dumps({k:v for k,v in result.items() if k not in ('recovery_diagnostic',)},ensure_ascii=False)[:1000])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','infer','analyze']);p.add_argument('--out',required=True,type=Path);a=p.parse_args();globals()[a.mode](a.out.resolve())
