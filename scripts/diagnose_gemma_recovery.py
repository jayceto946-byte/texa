"""Existing conservative parser diagnostics only; no replacement official scores."""
import sys,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from screen_gemma_runtime import read,save,lines,variants
from evaluation.runtime_benchmark.scoring import Benchmark
from evaluation.runtime_benchmark.diagnostics import extract
from runtime_08b_probe_analysis import field_analysis,summarize
out=Path(sys.argv[1]);b=Benchmark();rows=[r for r in b.rows if r['task']=='policy_select'];mapping=read(out/'semantic-mapping.json')['variants'];pair={r['id']:{} for r in rows};sums={}
for a in 'ABC':
    for row,x in zip(rows,lines(out/'permutation'/f'arm-{a}/outputs.jsonl')):
        m=mapping[a][row['id']];changed=copy.deepcopy(row);changed['input']=variants(row,b.scorer.canonical)[a]['job']['input'];changed['gold']={'action_id':m['variant_gold_id']};ext=extract(x['raw_output'],b.scorer.json_strict);sc=b.scorer.evaluate(changed,ext['extracted_text']);local=b.scorer.json_strict(ext['extracted_text'])['action_id'] if sc['executable'] else None
        pair[row['id']][a]={'local_id':local,'semantic_id':m['local_to_semantic'].get(local),'position':m['local_to_position'].get(local),'valid':sc['executable'],'correct':sc['structured_match'],'recovery':ext}
    vals=[pair[r['id']][a] for r in rows]
    sums[a]={'N':80,'correct':sum(v['correct'] for v in vals),'valid':sum(v['valid'] for v in vals),'ids':{i:sum(v['local_id']==i for v in vals) for i in ('a0','a1','a2')},'positions':{str(i):sum(v['position']==i for v in vals) for i in (1,2,3)}}
stable=lambda r:all(pair[r['id']][a]['valid'] for a in 'ABC') and len({pair[r['id']][a]['semantic_id'] for a in 'ABC'})==1
m={'diagnostic_only':True,'changes_official_score':False,'extraction':'existing semantic-recoverability/v0.1, no repairs, unique outer payload only','arms':sums,'three_stable':sum(stable(r) for r in rows),'binary_stable':sum(stable(r) for r in rows if len(r['input']['admissible_actions'])==2),'all_correct':sum(all(pair[r['id']][a]['correct'] for a in 'ABC') for r in rows),'cases':pair}
save(out/'permutation-recovery-diagnostics.json',m);print({k:v for k,v in m.items() if k!='cases'})
if (out/'semantic_all/outputs.jsonl').exists():
    groups={}
    for label,path in [('gemma',out/'semantic_all/outputs.jsonl'),('qwen',ROOT/'docs/validation/runtime-benchmark-v0.1/p3-semantic-all-verified/outputs.jsonl')]:
        details=[]
        for x in lines(path):
            row=b.by_id[x['case_id']]
            if row['task']=='reference_resolve':continue
            ext=extract(x['raw_output'],b.scorer.json_strict)
            details.append({**field_analysis(row,{**x,'raw_output':ext['extracted_text']},b.scorer),'recovery':ext})
        groups[label]={'by_task':{t:summarize([d for d in details if d['task']==t]) for t in sorted({d['task'] for d in details})},'cases':details}
    save(out/'field-recovery-diagnostics.json',{'diagnostic_only':True,'changes_official_scores':False,**groups})
