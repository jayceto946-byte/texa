#!/usr/bin/env python3
"""One-off paired diagnostic; never writes frozen cases or official scores."""
import argparse
import collections
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from diagnose_runtime_08b import read, save, lines, append, simplified, baseline_hashes, PROMPT_VERSION


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected():
    hashes = baseline_hashes()
    folder = ROOT / 'docs/validation/runtime-benchmark-v0.1/diagnostic-probe-20261006'
    for p in folder.rglob('*'):
        if p.is_file():
            hashes[str(p.relative_to(ROOT))] = sha(p)
    for name in ('Runtime-0.8B-Diagnostic-Probe.md', 'Screening-Results-2026-10-06.md'):
        p = ROOT / 'docs/runtime-benchmark-v0.1' / name
        hashes[str(p.relative_to(ROOT))] = sha(p)
    return hashes


def variants(row, canonical):
    original = row['input']
    actions = original['admissible_actions']
    ids = [a['id'] for a in actions]
    assert ids == [f'a{i}' for i in range(len(actions))]
    assert len(actions) in (2, 3)
    # Stable semantic identity = original local ID plus exact original kind/args.
    # It identifies the same candidate within a case, not just its broad kind.
    assert len({canonical({k:v for k,v in a.items() if k != 'id'}) for a in actions}) == len(actions)
    result = {}
    for arm in ('A', 'B', 'C'):
        inp = copy.deepcopy(original)
        mapping = {a: a for a in ids}
        if arm == 'B':
            inp['admissible_actions'].reverse()
        elif arm == 'C':
            mapping = {ids[(i + 1) % len(ids)]: old for i, old in enumerate(ids)}
            for i, candidate in enumerate(inp['admissible_actions']):
                candidate['id'] = ids[(i + 1) % len(ids)]
        positions = {a['id']: i+1 for i,a in enumerate(inp['admissible_actions'])}
        gold_id = next(local for local, semantic in mapping.items() if semantic == row['gold']['action_id'])
        result[arm] = {
            'job': {'case_id': row['id'], 'task': 'policy_select', 'input': inp,
                    'messages': simplified('policy_select', inp, canonical), 'max_new_tokens': 128,
                    'diagnostic_only': True},
            'mapping': {'local_to_semantic': mapping, 'local_to_position': positions,
                        'gold_semantic': row['gold']['action_id'], 'variant_gold_id': gold_id}}
        assert {k:v for k,v in inp.items() if k != 'admissible_actions'} == {k:v for k,v in original.items() if k != 'admissible_actions'}
        for candidate in inp['admissible_actions']:
            source = actions[ids.index(mapping[candidate['id']])]
            assert {k:v for k,v in candidate.items() if k != 'id'} == {k:v for k,v in source.items() if k != 'id'}
        if arm == 'B':
            assert inp['admissible_actions'] == list(reversed(actions))
            assert gold_id == row['gold']['action_id']
        if arm == 'C':
            assert all(mapping[a['id']] == ids[i] for i,a in enumerate(inp['admissible_actions']))
    return result


def prepare(out):
    from evaluation.runtime_benchmark.scoring import Benchmark
    from evaluation.runtime_benchmark.prompting import smoke_case
    b = Benchmark()
    rows = [r for r in b.rows if r['task'] == 'policy_select']
    assert len(rows) == 80
    out.mkdir(parents=True, exist_ok=False)
    all_variants = {r['id']: variants(r, b.scorer.canonical) for r in rows}
    mappings = {arm: {r['id']: all_variants[r['id']][arm]['mapping'] for r in rows} for arm in ('A','B','C')}
    for arm in ('A','B','C'):
        with (out / f'jobs-{arm}.jsonl').open('x') as f:
            for row in rows:
                append(f, all_variants[row['id']][arm]['job'])
    # Gold and maps remain outside model requests and are read only by analysis.
    save(out / 'semantic-mapping.json', {'diagnostic_only':True, 'variants':mappings})
    config = read(ROOT / 'docs/validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/config.json')
    save(out / 'config.json', config)
    save(out / 'protected-before.json', protected())
    save(out / 'experiment.json', {'diagnostic_only':True, 'exposed_dev':True,
         'prompt_version': PROMPT_VERSION, 'freeze_sha256':b.freeze_hash,
         'cases': [r['id'] for r in rows], 'candidate_counts': dict(collections.Counter(len(r['input']['admissible_actions']) for r in rows)),
         'C_id_permutation': 'original ai -> a((i+1) mod candidate_count); two candidates swap, three cycle forward',
         'jobs_sha256':{arm:sha(out/f'jobs-{arm}.jsonl') for arm in ('A','B','C')},
         'warmup_messages':simplified('policy_select',smoke_case()['input'],b.scorer.canonical),
         'no_retry': True, 'no_constrained_decoding':True})
    print('Prepared 80 x 3 paired diagnostic requests; all transformation assertions passed.')


def infer(out):
    from evaluation.runtime_benchmark.adapter import MLXAdapter
    experiment = read(out/'experiment.json')
    config = read(out/'config.json')
    state = {'diagnostic_only':True,'status':'running','config':config,'prompt_version':PROMPT_VERSION,'planned_requests':240}
    assert all(sha(out/f'jobs-{a}.jsonl') == experiment['jobs_sha256'][a] for a in ('A','B','C'))
    save(out/'run.json',state)
    adapter = MLXAdapter()
    try:
        state['model'] = adapter.load(config)
        state['warmup'] = adapter.generate(experiment['warmup_messages'], {'max_new_tokens':128,'temperature':0})
        assert state['warmup']['status'] == 'ok'
        save(out/'run.json',state)
        for arm in ('A','B','C'):
            folder = out/f'arm-{arm}'
            folder.mkdir(exist_ok=False)
            with (folder/'requests.jsonl').open('x') as req, (folder/'outputs.jsonl').open('x') as raw:
                for i,job in enumerate(lines(out/f'jobs-{arm}.jsonl')):
                    result = adapter.generate(job['messages'], {'max_new_tokens':128,'temperature':0})
                    append(raw, {**result,'case_id':job['case_id'],'task':'policy_select','variant':arm,'diagnostic_only':True,'max_new_tokens':128})
                    append(req, {**job,'rendered_prompt':result['rendered_prompt']})
                    state['completed_requests'] = state.get('completed_requests',0)+1
                    print(f'{arm} {i+1}/80 {job["case_id"]}',flush=True)
                    if result['status'] != 'ok':
                        raise RuntimeError(result['error'])
            save(out/'run.json',state)
        state['status'] = 'complete'
    except (Exception,KeyboardInterrupt) as error:
        state.update(status='incomplete',error=type(error).__name__+': '+str(error))
    finally:
        if hasattr(adapter,'mx'):
            state['memory'] = adapter.close()
        save(out/'run.json',state)
    return 0 if state['status']=='complete' else 1


def analyze(out):
    import jsonschema
    from evaluation.runtime_benchmark.scoring import Benchmark
    b = Benchmark()
    rows = [r for r in b.rows if r['task']=='policy_select']
    experiment = read(out/'experiment.json')
    mapping = read(out/'semantic-mapping.json')['variants']
    before = read(out/'protected-before.json')
    assert protected() == before, 'existing baseline/diagnostic modified'
    save(out/'integrity.json', {'diagnostic_only':True,'unchanged':True,'checked_files':len(before),'freeze_sha256':b.freeze_hash})
    run = read(out/'run.json')
    assert run['status']=='complete' and run['completed_requests']==240
    assert run['config']==read(out/'config.json')==read(ROOT/'docs/validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/config.json')
    old_jobs=lines(ROOT/'docs/validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/jobs-A.jsonl')
    old_system=next(j['messages'][0] for j in old_jobs if j['task']=='policy_select')
    previous = read(ROOT/'docs/validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/arm-A/run.json')['model']
    for key in ('local_path','quantization','weight_dtypes','libraries','template_settings'):
        assert previous[key] == run['model'][key], key
    parsed = {}; summary = {}
    for arm in ('A','B','C'):
        assert sha(out/f'jobs-{arm}.jsonl') == experiment['jobs_sha256'][arm]
        raw = lines(out/f'arm-{arm}/outputs.jsonl')
        req = lines(out/f'arm-{arm}/requests.jsonl')
        assert len(raw)==len(req)==80 and [r['case_id'] for r in raw] == experiment['cases']
        parsed[arm] = {}
        for row, output, request in zip(rows,raw,req):
            expected = variants(row,b.scorer.canonical)[arm]
            assert mapping[arm][row['id']] == expected['mapping']
            assert all(request[k]==v for k,v in expected['job'].items())
            assert request['messages'][0]==old_system
            assert output['rendered_prompt']==request['rendered_prompt']
            assert output['diagnostic_only'] and output['status']=='ok'
            choice = None; strict = False; valid = False
            try:
                value = b.scorer.json_strict(output['raw_output']); strict=True
                b.scorer.validate('policy_select',value,request['input']); valid=True
                choice=value['action_id']
            except (ValueError,TypeError,KeyError,jsonschema.ValidationError) as error:
                # No repair/substrings: invalid output has no usable selection.
                if valid: raise error
            m=mapping[arm][row['id']]
            parsed[arm][row['id']] = {'local_id':choice,'semantic_id':m['local_to_semantic'].get(choice),
                  'position':m['local_to_position'].get(choice),'gold_semantic':m['gold_semantic'],
                  'correct':valid and m['local_to_semantic'][choice]==m['gold_semantic'],
                  'strict_json':strict,'valid':valid,'finish_reason':output['finish_reason']}
        values=list(parsed[arm].values())
        summary[arm]={'N':80,'semantic_correct':sum(v['correct'] for v in values),
             'strict_json':sum(v['strict_json'] for v in values),'valid':sum(v['valid'] for v in values),
             'length':sum(v['finish_reason']=='length' for v in values),
             'id_preference':{i:sum(v['local_id']==i for v in values) for i in ('a0','a1','a2')},
             'position_preference':{str(i):sum(v['position']==i for v in values) for i in (1,2,3)},
             'strata':{}}
        summary[arm]['candidate_count_strata']={str(n):{
            'N':sum(len(r['input']['admissible_actions'])==n for r in rows),
            'correct':sum(parsed[arm][r['id']]['correct'] for r in rows if len(r['input']['admissible_actions'])==n),
            'id_preference':dict(collections.Counter(parsed[arm][r['id']]['local_id'] for r in rows if len(r['input']['admissible_actions'])==n)),
            'position_preference':dict(collections.Counter(str(parsed[arm][r['id']]['position']) for r in rows if len(r['input']['admissible_actions'])==n))}
            for n in (2,3)}
        summary[arm]['fixed_bias_reference_correct']={
            'always_a1':sum(mapping[arm][r['id']]['local_to_semantic']['a1']==r['gold']['action_id'] for r in rows),
            'always_second':sum(next(semantic for local,semantic in mapping[arm][r['id']]['local_to_semantic'].items() if mapping[arm][r['id']]['local_to_position'][local]==2)==r['gold']['action_id'] for r in rows)}
        for group in ('tool_vs_answer','multi_intent_order'):
            selected=[r for r in rows if ('multi_intent_order' in r['tags']) == (group=='multi_intent_order')]
            summary[arm]['strata'][group]={'N':len(selected),'correct':sum(parsed[arm][r['id']]['correct'] for r in selected)}
    pairs={}
    for left,right in (('A','B'),('A','C'),('B','C')):
        counts={}; ids={}
        for name,key in (('same_semantic_action','semantic_id'),('same_action_id','local_id'),('same_candidate_position','position')):
            ids[name]=[r['id'] for r in rows if parsed[left][r['id']]['valid'] and parsed[right][r['id']]['valid'] and parsed[left][r['id']][key]==parsed[right][r['id']][key]]
            counts[name]=len(ids[name])
        ids['changed_semantic_action']=[r['id'] for r in rows if parsed[left][r['id']]['valid'] and parsed[right][r['id']]['valid'] and parsed[left][r['id']]['semantic_id']!=parsed[right][r['id']]['semantic_id']]
        counts['changed_semantic_action']=len(ids['changed_semantic_action'])
        counts['invalid_in_pair']=sum(not(parsed[left][r['id']]['valid'] and parsed[right][r['id']]['valid']) for r in rows)
        matrices={key:dict(collections.Counter(f'{parsed[left][r["id"]][key]} -> {parsed[right][r["id"]][key]}' for r in rows)) for key in ('local_id','position','semantic_id')}
        pairs[left+'-'+right]={'counts':counts,'case_ids':ids,'transitions':matrices}
        pairs[left+'-'+right]['candidate_count_strata']={str(n):{
            'N':sum(len(r['input']['admissible_actions'])==n for r in rows),
            **{name:sum(r['id'] in selected for r in rows if len(r['input']['admissible_actions'])==n) for name,selected in ids.items()}}
            for n in (2,3)}
    stable=[r['id'] for r in rows if all(parsed[a][r['id']]['valid'] for a in ('A','B','C')) and len({parsed[a][r['id']]['semantic_id'] for a in ('A','B','C')})==1]
    all_correct=[r['id'] for r in rows if all(parsed[a][r['id']]['correct'] for a in ('A','B','C'))]
    stable_strata={g:{'N':summary['A']['strata'][g]['N'], 'stable_correct_ids':[r['id'] for r in rows if r['id'] in all_correct and ('multi_intent_order' in r['tags'])==(g=='multi_intent_order')]} for g in ('tool_vs_answer','multi_intent_order')}
    old=lines(ROOT/'docs/validation/runtime-benchmark-v0.1/diagnostic-probe-20261006/arm-A/outputs.jsonl')
    oldpolicy=[r for r in old if r['task']=='policy_select']
    newraw={r['case_id']:r for r in lines(out/'arm-A/outputs.jsonl')}
    replay_matches=[r['case_id'] for r in oldpolicy if r['raw_output']==newraw[r['case_id']]['raw_output']]
    metrics={'diagnostic_only':True,'summaries':summary,'pairs':pairs,'all_three_semantic_stable_ids':stable,
         'all_three_correct_ids':all_correct,'stable_strata':stable_strata,'prior_20_raw_match_ids':replay_matches,
         'paired_cases':{r['id']:{a:parsed[a][r['id']] for a in ('A','B','C')} for r in rows}}
    metrics['all_three_correct_strata']={str(n):[r['id'] for r in rows if len(r['input']['admissible_actions'])==n and r['id'] in all_correct] for n in (2,3)}
    metrics['all_three_same_id_ids']=[r['id'] for r in rows if all(parsed[a][r['id']]['valid'] for a in ('A','B','C')) and len({parsed[a][r['id']]['local_id'] for a in ('A','B','C')})==1]
    metrics['all_three_same_position_ids']=[r['id'] for r in rows if all(parsed[a][r['id']]['valid'] for a in ('A','B','C')) and len({parsed[a][r['id']]['position'] for a in ('A','B','C')})==1]
    save(out/'metrics.json',metrics)
    print(json.dumps({k:v for k,v in metrics.items() if k!='paired_cases'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','infer','analyze'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.mode=='prepare': prepare(args.out)
    elif args.mode=='infer': raise SystemExit(infer(args.out))
    else: analyze(args.out)
