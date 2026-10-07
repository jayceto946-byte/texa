#!/usr/bin/env python3
"""Offline frozen-gold evaluator. No LLM judge, no network, no repo import."""
import argparse,collections,hashlib,importlib.util,json,re,sys
from pathlib import Path
import jsonschema
ROOT=Path(__file__).resolve().parents[1]
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def load(path):return json.loads(Path(path).read_text())
def json_strict(raw):
 def pairs(items):
  d={}
  for k,v in items:
   if k in d:raise ValueError('duplicate_key')
   d[k]=v
  return d
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite')))
def records(path):return [json_strict(s) for s in Path(path).read_text().splitlines() if s.strip()]
def verify_freeze():
 manifest=load(ROOT/'FREEZE.json')
 for p,h in manifest['sha256'].items():
  if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h:raise ValueError('freeze_mismatch:'+p)
 rows=records(ROOT/'curator/cases.with-gold.jsonl')
 for r in rows:
  assert digest(r['gold'])==r['gold_hash'],r['id']
  assert digest(r['input'])==r['input_hash'],r['id']
  assert digest({k:v for k,v in r.items() if k!='case_hash'})==r['case_hash'],r['id']
 return rows
# This validator is the pinned, pure production function, not a redesign.
p=ROOT/'audit/contract-source/graph/question_understanding.py'
spec=importlib.util.spec_from_file_location('frozen_understanding',p);under=importlib.util.module_from_spec(spec);spec.loader.exec_module(under)
def validate(task,pred,inp):
 jsonschema.Draft202012Validator(load(ROOT/f'schemas/{task}.output.schema.json')).validate(pred)
 if task=='policy_select' and pred['action_id'] not in {a['id'] for a in inp['admissible_actions']}:raise ValueError('unknown_action_id')
 if task=='question_understanding':under.validate_interpretation(pred,inp)
 if task=='reference_resolve':
  op=pred['state_operations'][0]
  if op['operation']=='resolve_reference' and op['value'] not in inp['candidate_references']:raise ValueError('out_of_candidate_reference')
def effective(task,p,inp):
 p=json.loads(canonical(p))
 if task=='question_understanding':
  p['dimensions']=sorted(p['dimensions'])
  if inp['rule'].get('intent_locked'):p['intent']=inp['rule']['intent']
 return p
def goal_metrics(row,p):
 m=row['metadata']; expected=m['objective_atoms']; wanted=m['criteria_atoms']; constraints=m['constraint_atoms']
 # Closed extractive profile: only whitespace and separators normalize, never negation or quantities.
 split=lambda t:[x.strip() for x in re.split(r'[；;\n]+',t) if x.strip()]
 got=split(p['objective']); criteria=[x['description'].strip() for x in p['success_criteria']]
 retention=lambda required,actual:sum(x in actual for x in required)/len(required) if required else 1.0
 retained=retention(expected,got); cr=retention(wanted,criteria); con=retention(constraints,got)
 unknown=[x for x in got if x not in expected]+[x for x in criteria if x not in wanted]
 title_ok=p['title'].strip()==expected[0]
 text=''.join([p['title'],p['objective'],*criteria]); source=row['input']['text']
 # Proven unsupported spans vs unrecognized paraphrases are kept distinct.
 unsupported=[x for x in unknown if x not in source]
 return {'semantic_fidelity':(retained+cr)/2,'required_field_retention':(retained+cr)/2,'constraint_retention':con,'unsupported_atom_count':len(unsupported),'out_of_profile_atom_count':len(unknown),'hallucination_check':'closed_profile_only','compression_ratio':len(text)/len(source),'title_supported':title_ok,'profile_complete':retained==cr==con==1 and not unknown and title_ok,'objective_atoms':got,'criterion_atoms':criteria}
def evaluate(row,raw):
 task=row['task'];g=row['gold'];inp=row['input']
 result={'id':row['id'],'task':task,'track':row['track'],'pair_id':row['pair_id'],'exact':False,'structured_match':False,'schema_valid':False,'executable':False,'severity':'S2','critical_failure':False,'reason':'missing_prediction'}
 if raw is None:return result
 try:p=json_strict(raw)
 except (ValueError,TypeError) as e:return {**result,'reason':'invalid_json:'+str(e)[:100]}
 try:
  jsonschema.Draft202012Validator(load(ROOT/f'schemas/{task}.output.schema.json')).validate(p);result['schema_valid']=True
  validate(task,p,inp);result['executable']=True
 except (ValueError,jsonschema.ValidationError,TypeError,KeyError) as e:
  # Rejected output cannot mutate production state. Record attempted authority escalation separately.
  forbidden=isinstance(p,dict) and bool(set(p)&{'status','scope','goal_status','user_confirms_completion'}) and task in {'policy_select','goal_summary','question_understanding','reference_resolve'}
  return {**result,'reason':'contract_rejected:'+str(e).splitlines()[0][:140],'attempted_authority_escalation':forbidden}
 result['exact']=canonical(p)==canonical(g)
 result['structured_match']=effective(task,p,inp)==effective(task,g,inp)
 if result['structured_match']:return {**result,'severity':'S0' if result['exact'] else 'S1','reason':'matched'}
 severity='S2';reason='decision_mismatch'
 if task=='goal_summary':
  met=goal_metrics(row,p);result.update(met)
  if met['profile_complete']:severity='S1';reason='lossless_extract_order_or_whitespace_variant';result['structured_match']=True
  elif met['constraint_retention']<1 or row['metadata']['objective_atoms'][0] not in met['objective_atoms']:severity='S3';reason='goal_constraint_loss'
  elif met['out_of_profile_atom_count'] or not met['title_supported']:severity='S3';reason='goal_unverified_new_atom_in_closed_profile'
  else:reason='goal_required_atom_loss'
 elif task=='question_understanding':
  if p['entity_spans']!=g['entity_spans'] or p['reference_id']!=g['reference_id']:
   severity='S3';reason='wrong_object_or_reference'
 elif task=='reference_resolve':
  if p['state_operations'][0]['operation']=='resolve_reference':severity='S3';reason='wrong_reference_state_update'
  else:reason='unnecessary_clarification'
 elif task=='goal_lifecycle_control':
  if p.get('status')!=g.get('status') or p.get('accepted')!=g.get('accepted'):severity='S3';reason='wrong_transition_prediction_control_only'
 elif task=='context_contract':
  if any(p[k]!=g[k] for k in ['resolved_query','constraints','current_topic','state_operations']):severity='S3';reason='wrong_context_state_control_only'
 elif task=='retrieval_contract':
  if p['retrieval_action']=='reuse' and g['retrieval_action'] in {'full','none'}:severity='S3';reason='invalid_evidence_reuse_prediction_control_only'
 elif task=='decision_guard_control':
  if g['execution_kind']=='not_started' and p['execution_kind']!='not_started':severity='S3';reason='would_accept_stale_control_only'
 if task=='goal_summary' and 'semantic_fidelity' not in result:result.update(goal_metrics(row,p))
 return {**result,'severity':severity,'critical_failure':severity=='S3','reason':reason}
def score(rows,preds):
 results=[]
 for r in rows:
  res=evaluate(r,preds.get(r['id']))
  if r['task']=='goal_summary' and res['executable'] and 'semantic_fidelity' not in res:res.update(goal_metrics(r,json_strict(preds[r['id']])))
  results.append(res)
 def summary(rs):
  n=len(rs);pairs=collections.defaultdict(list)
  for r in rs:pairs[r['pair_id']].append(r['structured_match'])
  return {'n':n,'exact_match':sum(r['exact'] for r in rs)/n if n else None,'structured_match':sum(r['structured_match'] for r in rs)/n if n else None,'schema_validity':sum(r['schema_valid'] for r in rs)/n if n else None,'executability':sum(r['executable'] for r in rs)/n if n else None,'severity':dict(collections.Counter(r['severity'] for r in rs)),'critical_failure_rate':sum(r['critical_failure'] for r in rs)/n if n else None,'complete_pairs':sum(len(v)==2 for v in pairs.values()),'pair_both_correct':sum(len(v)==2 and all(v) for v in pairs.values())}
 return {'scoring_version':'runtime-benchmark-v0/1','no_llm_judge':True,'semantic_test_locked':False,'by_track':{k:summary([r for r in results if r['track']==k]) for k in sorted({r['track'] for r in results})},'by_task':{k:summary([r for r in results if r['task']==k]) for k in sorted({r['task'] for r in results})},'primary_semantic_without_upstream_conflicts':summary([x for x in results if x['track']=='semantic' and not next(r for r in rows if r['id']==x['id'])['metadata'].get('rule_intent_override')]), 'upstream_locked_conflicts': [r['id'] for r in rows if r['metadata'].get('rule_intent_override')], 'understanding_free_intent':summary([x for x in results if x['task']=='question_understanding' and not next(r for r in rows if r['id']==x['id'])['input']['rule'].get('intent_locked')]), 'goal_metric_means':{k:sum(r.get(k,0) for r in results if r['task']=='goal_summary')/sum(r['task']=='goal_summary' for r in results) for k in ['semantic_fidelity','required_field_retention','constraint_retention'] if any(r['task']=='goal_summary' for r in results)}, 'goal_compression_valid_outputs':{'n':sum('compression_ratio' in r for r in results),'mean':sum(r.get('compression_ratio',0) for r in results)/sum('compression_ratio' in r for r in results) if any('compression_ratio' in r for r in results) else None}, 'results':results}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('predictions',type=Path);ap.add_argument('--split',choices=['train','dev','test','hidden_test','all'],required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 rows=verify_freeze();rows=[r for r in rows if a.split=='all' or r['split']==a.split];ids={r['id'] for r in rows};preds={}
 for item in records(a.predictions):
  if set(item)!={'id','raw_output'} or type(item['raw_output'])!=str:raise ValueError('prediction requires id and raw_output string only')
  if item['id'] not in ids:raise ValueError('unknown_or_wrong_split_id:'+item['id'])
  if item['id'] in preds:raise ValueError('duplicate_prediction:'+item['id'])
  preds[item['id']]=item['raw_output']
 report=score(rows,preds);report.update(split=a.split,missing_predictions=len(ids-set(preds)))
 # Reports may not overwrite release files.
 if a.output.resolve().is_relative_to(ROOT):raise ValueError('write report outside frozen release directory')
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))
if __name__=='__main__':main()
