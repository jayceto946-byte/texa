#!/usr/bin/env python3
"""Validate release and adversarial scorer behavior, not model accuracy."""
import collections,copy,json,sys,re
from difflib import SequenceMatcher
from pathlib import Path
import jsonschema
from score import ROOT,verify_freeze,validate,evaluate,score,canonical

def main():
 rows=verify_freeze();assert len(rows)==300
 groups=collections.defaultdict(set);pairs=collections.defaultdict(set)
 for r in rows:
  groups[r['split_group']].add(r['split']);pairs[r['pair_id']].add(r['split'])
  jsonschema.Draft202012Validator(json.loads((ROOT/f"schemas/{r['task']}.input.schema.json").read_text())).validate(r['input'])
  validate(r['task'],r['gold'],r['input'])
  got=evaluate(r,canonical(r['gold']));assert got['exact'] and got['severity']=='S0',r['id']
 assert all(len(x)==1 for x in list(groups.values())+list(pairs.values()))
 for a_idx,a in enumerate(rows):
  for b in rows[a_idx+1:]:
   if a['split']==b['split']:continue
   x,y=(re.sub(r'[\W_]+','',z['question']) for z in (a,b))
   assert not x or SequenceMatcher(None,x,y).ratio()<.78,(a['id'],b['id'])
 for split in ('train','dev','test','hidden_test'):
  got=[json.loads(s) for s in (ROOT/f'datasets/{split}.inputs.jsonl').read_text().splitlines()]
  expected=[{'id':r['id'],'task':r['task'],'input':r['input']} for r in rows if r['split']==split]
  assert got==expected,split

 checks=[]
 def check(name,row,raw,**expected):
  result=evaluate(row,raw)
  for k,v in expected.items():assert result[k]==v,(name,result,k,v)
  checks.append(name)
 policy=next(r for r in rows if r['task']=='policy_select')
 check('duplicate keys rejected',policy,'{"action_id":"a0","action_id":"a1"}',schema_valid=False)
 check('fences rejected',policy,'```json\n'+canonical(policy['gold'])+'\n```',schema_valid=False)
 check('unknown action cannot execute',policy,'{"action_id":"made_up"}',executable=False)
 check('omission stays in denominator',policy,None,exact=False,severity='S2')
 check('extra authority field rejected',policy,canonical({**policy['gold'],'status':'completed'}),executable=False)
 goal=next(r for r in rows if r['task']=='goal_summary');p=copy.deepcopy(goal['gold'])
 p['objective']=p['objective'].replace('别扩到导数','扩到导数');check('negation reversal critical',goal,canonical(p),severity='S3')
 p=copy.deepcopy(goal['gold']);p['objective']+='；已完成全部课程';check('invented goal completion critical',goal,canonical(p),severity='S3')
 p=copy.deepcopy(goal['gold']);p['objective']='；'.join(reversed(goal['metadata']['objective_atoms']));check('lossless reordering',goal,canonical(p),severity='S1',structured_match=True)
 u=next(r for r in rows if r['task']=='question_understanding');p=copy.deepcopy(u['gold']);p['entity_spans'][0]['end']=100000;check('span out of input rejected',u,canonical(p),executable=False)
 ref=next(r for r in rows if r['task']=='reference_resolve' and r['gold']['state_operations'][0]['operation']=='clarify');p={'state_operations':[{'operation':'resolve_reference','value':ref['input']['candidate_references'][0]}]};check('ambiguous reference invented certainty',ref,canonical(p),severity='S3')
 report=score(rows,{r['id']:canonical(r['gold']) for r in rows});assert all(x['exact_match']==1 for x in report['by_task'].values())
 print(json.dumps({'cases_valid':len(rows),'groups':len(groups),'split_counts':dict(collections.Counter(r['split'] for r in rows)),'scorer_mutation_checks':checks,'gold_round_trip':'300/300; evaluator self-test only, not model accuracy'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
