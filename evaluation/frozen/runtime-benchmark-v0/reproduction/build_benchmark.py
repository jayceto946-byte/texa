import sys,os,json,hashlib,copy,tempfile,socket,subprocess,re,ast
from pathlib import Path
from collections import Counter,defaultdict
from difflib import SequenceMatcher
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
OUT=Path(os.environ['BENCHMARK_OUT']).resolve()
assert not OUT.exists(), 'Reproduction output must be a new directory'
REPO=Path(os.environ['BENCHMARK_REPO']).resolve()
sys.path[:0]=[str(HERE),str(REPO)]
from author_cases import *
D=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
H=lambda x:hashlib.sha256(D(x).encode()).hexdigest()
def write(path,obj):
 p=OUT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def lines(path,rows):
 p=OUT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(D(x)+'\n' for x in rows))
rows=[];witnesses=[]
def add(task,family,question,inp,gold,basis,*,track='semantic',pair_kind='language_contrast',tags=(),meta=None):
 n=len(rows)+1
 r={'id':f'TRB0-{n:04d}','task':task,'family':family,'pair_id':family,'pair_kind':pair_kind,'question':question,'input':inp,'gold':gold,'basis':basis,'track':track,'tags':list(tags),'provenance':{'kind':'authored_synthetic_zh','human_adjudicated':False},'review_status':'author_frozen_pending_independent_review' if track=='semantic' else 'code_contract_verified','metadata':meta or {}}
 rows.append(r);return r

def main(tmp):
 for k,v in {'DATA_DIR':'data','PROGRESS_PATH':'progress','VECTOR_DB_PATH':'vectors','BOOKS_PATH':'books','CHAPTERS_PATH':'chapters','IMAGES_PATH':'images','MINERU_OUTPUT_PATH':'mineru','ENV_PATH':'empty.env'}.items():os.environ[k]=str(tmp/v)
 (tmp/'empty.env').touch()
 os.environ.update(PYTHONDONTWRITEBYTECODE='1',QUESTION_UNDERSTANDING_MODE='off',SEMANTIC_RESOLVER_ENABLED='0',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',ANONYMIZED_TELEMETRY='False')
 from backend.services.decision.policy_contracts import PolicyObservationV0,PolicyDecisionV0,PolicyOutcomeV0
 from backend.services.decision.policy import RulePolicyV0,select_decision,PolicyRejected
 from backend.services.decision.policy_projection import project_observation,matched_tool_refs,runtime_identity
 from evaluation.runtime_policy_v0 import fixture_runtime
 from backend.services.question_understanding import build_request,should_attempt
 from backend.services.session_context import SessionContextState,build_resolution_trace
 from graph.question_understanding import validate_interpretation,INTENTS,DIMENSIONS
 from backend.services.semantic_resolver import validate_semantic_operations,_candidate_values
 from backend.services.decision.contracts import DecisionContext
 from backend.services.decision.router import DecisionRouter
 from graph.retrieval_policy import decide_retrieval_action
 from graph.conversation_context import build_conversation_context_seed
 from backend.services.goals.execution import GoalSummary
 from backend.services.goals.store import GoalStore
 from backend.services.goals.service import GoalService
 parts=fixture_runtime(tmp/'policy',{'request':'查询习题和最近学习进度','book_name':'fixture','grounded':False})
 store,registry,state,refs,context=parts
 snap=store.task_snapshot('rtask_fixture')
 def observation(q):
  st={**state,'user_input':q}
  refs,_=matched_tool_refs(q,registry,grounded=False)
  return project_observation(request=q,resolved_query=q,registry=registry,context=context,identity=runtime_identity(snap),snapshot=snap,answer_state=st,candidate_tools=refs)
 def policy(q,target,family,tag):
  frozen=observation(q);o=frozen.envelope.payload
  matches=[a for a in o.admissible_actions if a.kind==target or a.kind=='call_tool' and a.args.tool_id==target]
  if not matches:raise ValueError(('unreachable target',q,target))
  gold={'action_id':matches[0].id}
  semkey=lambda a:a.args.tool_id if a.kind=='call_tool' else a.kind
  jud={a.id:('S0' if a.id==matches[0].id else 'S2') for a in o.admissible_actions}
  r=add('policy_select',family,q,o.model_dump(mode='json'),gold,'backend/services/decision/policy_projection.py::project_observation; docs/contracts/runtime-policy-evaluation-dataset-v0.md §3–4',tags=[tag,'colloquial','no_answer_generation'],meta={'execution_surface':'runtime_projection_harness','main_chat_takeover':'conditional_not_assumed','candidate_generation':'canonical_projection','candidate_count':len(o.admissible_actions),'model_invocation':'multi_candidate' if len(o.admissible_actions)>1 else 'forced','acceptable_actions':[gold['action_id']],'action_judgments':jud,'semantic_target':target,'rule_prediction':RulePolicyV0(o).model_dump(),'exclusions':frozen.exclusions})
  # Gold is authored target above, never baseline prediction.
  return r
 for fam,a,b,target in POLICY_PAIRS:
  policy(a,target,'P-'+fam,'tool_required');policy(b,'generate_answer','P-'+fam,'unnecessary_tool')
 for i,((a,b),(ta,tb)) in enumerate(zip(ORDER_PAIRS,ORDER_TOOLS)):
  policy(a,ta,f'P-order-{i:02}','multi_intent_order');policy(b,tb,f'P-order-{i:02}','multi_intent_order')
 for i,(q,obj,criteria,old,new) in enumerate(GOAL_PAIRS):
  for j in range(2):
   text=q if not j else q.replace(old,new)
   atoms=obj if not j else [x.replace(old,new) for x in obj]
   cs=criteria if not j else [x.replace(old,new) for x in criteria]
   gold={'title':atoms[0],'objective':'；'.join(atoms),'success_criteria':[{'description':x} for x in cs]}
   GoalSummary.model_validate(gold)
   for x in atoms+cs:
    assert x in text,(text,x)
   add('goal_summary',f'G-{i:02}',text,{'text':text},gold,'backend/services/goals/execution.py::summarize_goal / GoalSummary',tags=['constraints','extractive_transform','self_correction' if i in (2,7,12,13) else 'colloquial'],meta={'objective_atoms':atoms,'criteria_atoms':cs,'constraint_atoms':atoms[1:],'removed_noise':'all_other_source_spans','output_profile':'extractive_goal/v0','persisted_goal_status':'unchanged','added_by_runtime':['criterion ids']})
 for i,pair in enumerate(UNDERSTANDING_PAIRS):
  a,b,ia,da,ib,db,ea,*extra=pair
  eb=extra[0] if extra else ea
  for q,intent,dims,entities in [(a,ia,da,ea),(b,ib,db,eb)]:
   prior={'topic':'旧讨论对象','entities':['旧讨论对象'],'constraints':['只看上一轮条件']}
   trace=build_resolution_trace(q,[],initial_state=prior,understanding_mode='off',semantic_enabled=False)
   req=build_request(q,SessionContextState(**prior),trace)
   intended=intent
   if req['rule']['intent_locked']:intent=req['rule']['intent']
   # Explicit current noun spans, including self-correction's current object.
   spans=[{'start':q.index(e),'end':q.index(e)+len(e)} for e in entities]
   gold={'action':'continue','intent':intent,'dimensions':dims,'entity_spans':spans,'reference_id':''}
   validated=validate_interpretation(gold,req)
   reachable=should_attempt(q,trace)
   add('question_understanding',f'U-{i:02}',q,req,gold,'graph/question_understanding.py::validate_interpretation; backend/services/question_understanding.py::build_request',tags=['colloquial','current_vs_history','intent_dimension'],meta={'execution_surface':'existing_interface_unit','production_gate_eligible':reachable,'rule_intent_override':intended!=intent,'authored_semantic_intent':intended,'effective_intent':validated['intent'],'upstream_rule_trace':{k:trace[k] for k in ('method','resolution_action')},'rule_state_before':prior})
 for i,(a,b,candidates,target) in enumerate(REFERENCE_PAIRS):
  prior=SessionContextState(entities=candidates)
  vals=_candidate_values(prior)
  for j,q in enumerate((a,b)):
   g={'state_operations':[{'operation':'resolve_reference','value':target} if j==0 else {'operation':'clarify'}]}
   validate_semantic_operations(g,prior)
   add('reference_resolve',f'SR-{i:02}',q,{'question':q,'candidate_references':vals},g,'backend/services/semantic_resolver.py::_prompt / validate_semantic_operations',tags=['anaphora','ambiguous' if j else 'explicit_disambiguation'],meta={'execution_surface':'existing_interface_unit','production_gate_eligible':False,'gate_note':'Direct unit evaluation of adapter contract; not a claim that rules call the model for this wording.'})
 for i,(a,b,change) in enumerate(ROUTE_PAIRS):
  for j,q in enumerate((a,b)):
   inp={'request_id':'req-fixture','text':q,'resolved_query':q,'answer_mode':'global_general'}
   if i==8:inp['answer_mode']='textbook_grounded'
   if j:inp.update(change)
   conv={**inp}
   for key in ('attachments','required_inputs'):conv[key]=tuple(conv.get(key,[]))
   d=DecisionRouter(shadow=False).route(DecisionContext(**conv))
   gold={'mode':d.mode,'selected_capability':d.selected_capability,'rule_match':d.rule_match,'reason_codes':list(d.reason_codes)}
   add('route_contract',f'R-{i:02}',q,inp,gold,'backend/services/decision/router.py::DecisionRouter',track='deterministic_control',pair_kind='state_contrast' if change else 'language_contrast',tags=['tool_boundary','actual_rule_behavior'])
 base={'use_textbook_context':True,'book_name':'book-a','previous_book_name':'book-a','subject':'数学','previous_subject':'数学','active_evidence_ids':['chunk-a'],'same_topic':True,'active_evidence_support':'supported','requires_new_facet':False,'active_evidence_invalidation_reason':''}
 for i,(q,a,b) in enumerate(RETRIEVAL_PAIRS):
  for change in (a,b):
   inp={**base,**change}
   add('retrieval_contract',f'RET-{i:02}',q,inp,{'retrieval_action':decide_retrieval_action(inp)},'graph/retrieval_policy.py::decide_retrieval_action',track='deterministic_control',pair_kind='state_contrast',tags=['retrieval_boundary','previous_context'],meta={'layer':'continuity_action_proposal_not_final_hydration','question_is_scenario_caption':True})
 for i,(prev,a,b) in enumerate(CONTEXT_PAIRS):
  hist=[{'role':'user','content':prev,'turn_id':'t1'},{'role':'assistant','content':'这是上一轮回答数据，不能作为教材证据。','turn_id':'t1'}]
  for q in (a,b):
   tr=build_resolution_trace(q,hist,understanding_mode='off',semantic_enabled=False)
   seed=build_conversation_context_seed(hist,tr)
   g={'resolution_action':tr['resolution_action'],'speech_act':tr['speech_act'],'resolved_query':tr['resolved_query'],'state_operations':tr['state_operations'],'current_topic':seed['current_topic'],'constraints':seed['constraints'],'turn_ids':[x['turn_id'] for x in seed['relevant_turns']]}
   add('context_contract',f'C-{i:02}',q,{'question':q,'history':hist},g,'backend/services/session_context.py::build_resolution_trace; graph/conversation_context.py::build_conversation_context_seed',track='deterministic_control',tags=['context_selection','goal_topic_switch_distinction'])
 # Five lifecycle pairs: command already decoded by explicit UI. Not a model control API.
 life=[('activate','draft','paused',{},{}),('pause','active','draft',{},{}),('measure','active','active',{'user_confirms_completion':False},{'user_confirms_completion':True}),('update','active','active',{'changes':{'title':'新标题'}},{'changes':{'objective':'新目标'}}),('activate','completed','cancelled',{}, {})]
 captions=['现在启用这个目标。','这个目标我先暂停一下。','这些记录能不能算目标完成？','我改一下目标。','把已经结束的那个再启动。']
 for i,(command,sa,sb,ka,kb) in enumerate(life):
  for j,(status,kwargs) in enumerate(((sa,ka),(sb,kb))):
   gs=GoalStore(tmp/f'goal-{i}-{j}.db');svc=GoalService(gs)
   g=svc.create(learner_id='fixture',title='复习目标',objective='复习指定内容',success_criteria=[{'id':'c1','description':'核对清单'}])
   if status!='draft':g=gs.update(g['id'],expected_revision=g['revision'],changes={'status':status})
   inp={'command':command,'goal':g,'arguments':kwargs}
   # Strip identities/times that do not affect transition semantics.
   inp['goal']={k:g[k] for k in ('title','objective','scope','success_criteria','status','revision','progress','plan','next_action')}
   try:
    callargs={'expected_revision':g['revision'],**kwargs}
    if command=='measure':callargs['evidence_by_criterion']={'c1':['event-fixture']}
    res=getattr(svc,command)(g['id'],**callargs)
    gold={'accepted':True,'status':res['status'],'revision_delta':res['revision']-g['revision'],'plan_version':res['plan']['version'],'criterion_statuses':[x['status'] for x in res['progress']['criterion_results']]}
   except (ValueError,RuntimeError) as e:
    gold={'accepted':False,'status':g['status'],'revision_delta':0,'error_type':type(e).__name__}
   add('goal_lifecycle_control',f'GL-{i:02}',captions[i],inp,gold,'backend/services/goals/service.py::GoalService; backend/services/goals/store.py::update',track='deterministic_control',pair_kind='state_contrast',tags=['goal_state','no_model_authority'])
 # Strict decision/freshness controls: each uses a real frozen Observation.
 f=observation('请查习题库和最近学习进度')
 invalid_pairs=[('{"action_id":"a0"}','{"action_id":"invented"}'),('{"action_id":"a0"}','{"action_id":"a0","reason":"说明"}'),('{"action_id":"a0"}','{"action_id":"a0","action_id":"a1"}'),('{"action_id":"a0"}','```json\n{"action_id":"a0"}\n```'),('{"action_id":"a0"}','{"action_id":"a0"}')]
 for i,(a,b) in enumerate(invalid_pairs):
  for j,raw in enumerate((a,b)):
   records=[];calls=[];current=f
   stale=i==4 and j==1
   if stale:current=observation('请查最近学习进度')
   try:
    binding,attempt,attempts=select_decision(f,selector=lambda o:(calls.append(1) or raw),source='offline_injected',current=lambda:current,record=records.append)
    gold={'code':records[0].validation.code,'fallback_attempts':len(records)-1,'recorded_attempts':len(records),'execution_kind':binding['kind']}
   except PolicyRejected as e:gold={'code':e.code,'fallback_attempts':0,'recorded_attempts':len(records),'execution_kind':'not_started'}
   inp={'observation':f.envelope.payload.model_dump(mode='json'),'raw_output':raw,'fresh':not stale}
   add('decision_guard_control',f'DG-{i:02}','先查学习记录和习题；以下是待校验的模型输出。',inp,gold,'backend/services/decision/policy.py::select_decision / PolicyValidator',track='deterministic_control',pair_kind='protocol_contrast',tags=['fallback','adversarial','fault_injection'])
 assert len(rows)==300,len(rows)
 # Export source-derived schemas, not hand-invented action taxonomy.
 for cls in (PolicyObservationV0,PolicyDecisionV0,PolicyOutcomeV0,GoalSummary):write(Path('schemas')/(cls.__name__+'.json'),cls.model_json_schema())
 write('schemas/enums.json',{'policy_action_kinds':['generate_answer','call_tool','request_input'],'question_intents':sorted(INTENTS),'question_dimensions':sorted(DIMENSIONS),'goal_status':['draft','active','paused','completed','cancelled'],'retrieval_action':['none','reuse','delta','full']})
 # Near-duplicate grouping BEFORE split; comparisons at the authored question level.
 parent={r['family']:r['family'] for r in rows}
 def find(x):
  while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
  return x
 def union(a,b):
  a,b=find(a),find(b)
  if a!=b:parent[max(a,b)]=min(a,b)
 # Scope repeated decision frames to same cluster, including shared semantic prototype families.
 # These are shared linguistic mechanisms, not just common task labels.
 frame_groups=[['P-progress-check','P-progress-negation','P-progress-correction','P-progress-priority','P-progress-dialogue','P-progress-no-estimate','P-progress-quoted','P-progress-reference','P-progress-reversal','P-progress-selfrepair'],['P-exercise-correct','P-exercise-boundary','P-exercise-noncommand','P-exercise-checklist'],[f'P-order-{i:02}' for i in range(10)]]
 for group in frame_groups:
  for f2 in group[1:]:union(group[0],f2)
 norm=lambda s:re.sub(r'[\W_]+','',s)
 near=[]
 for i,a in enumerate(rows):
  for b in rows[i+1:]:
   if a['family']==b['family']:continue
   x,y=norm(a['question']),norm(b['question'])
   sim=SequenceMatcher(None,x,y).ratio()
   if x and (x==y or sim>=.78):
    union(a['family'],b['family']);near.append({'a':a['id'],'b':b['id'],'similarity':round(sim,4),'resolution':'co_grouped'})
 groups=defaultdict(list)
 for r in rows:r['split_group']=find(r['family']);groups[r['split_group']].append(r)
 # Greedy group packing, task-balanced objective, deterministic tie-breaking by hash.
 names=['train','dev','test','hidden_test'];target=dict(zip(names,[150,60,60,30]));counts=Counter();tc=defaultdict(Counter);task_counts=Counter(r['task'] for r in rows)
 for group,items in sorted(groups.items(),key=lambda kv:(-len(kv[1]),H(kv[0]))):
  def cost(s):
   size=counts[s]+len(items);over=max(0,size-target[s])
   return over*1000+(size/target[s])+sum((tc[s][t]+n)/(task_counts[t]*target[s]/300) for t,n in Counter(r['task'] for r in items).items())*.2
  split=min(names,key=lambda s:(cost(s),names.index(s)))
  counts[split]+=len(items)
  for r in items:r['split']=split;tc[split][r['task']]+=1
 for r in rows:
  r['input_hash']=H(r['input']);r['gold_hash']=H(r['gold']);r['case_hash']=H({k:v for k,v in r.items() if k!='case_hash'})
 lines('curator/cases.with-gold.jsonl',rows)
 for split in names:
  subset=[r for r in rows if r['split']==split]
  lines(f'datasets/{split}.inputs.jsonl',[{'id':r['id'],'task':r['task'],'input':r['input']} for r in subset])
  lines(f'curator/{split}.gold.jsonl',[{k:r[k] for k in ('id','task','gold','gold_hash','review_status','metadata')} for r in subset])
 write('split-manifest.json',{'version':'group-split/v0','seed':'texa-runtime-benchmark-v0-2026-10-06','requested_counts':target,'actual_counts':dict(counts),'task_counts':{s:dict(tc[s]) for s in names},'groups':{g:items[0]['split'] for g,items in groups.items()},'family_count':len(parent),'independent_group_count':len(groups),'semantic_test_locked':False,'hidden_test_custody':'curator-delivered; not secret from author or repository owner','fingerprints':{r['id']:r['case_hash'] for r in rows}})
 write('validation/leakage-report.json',{'exact_or_near_duplicate_cross_split':0,'threshold':.78,'method':'NFK-free Unicode word normalization + SequenceMatcher; explicit shared frame grouping; not a proof of all semantic independence','co_grouped_pairs':near,'pair_split_violation_count':0,'template_author_review':'draft; conservative explicit frame groups applied'})
 write('validation/dataset-summary.json',{'cases':len(rows),'tasks':dict(Counter(r['task'] for r in rows)),'splits':dict(counts),'tracks':dict(Counter(r['track'] for r in rows)),'pairs':len(parent),'contrast_gold_changed':sum(len({H(r['gold']) for r in rows if r['family']==f})>1 for f in parent),'policy_multi':sum(r['task']=='policy_select' and r['metadata']['candidate_count']>=2 for r in rows),'understanding_gate_eligible':sum(r['task']=='question_understanding' and r['metadata']['production_gate_eligible'] for r in rows),'understanding_rule_override_ids':[r['id'] for r in rows if r['task']=='question_understanding' and r['metadata']['rule_intent_override']]})
 # Runtime contract observations separate from authored semantic correctness.
 write('validation/rule-policy-baseline.json',{'scope':'draft semantic gold comparison; not model accuracy','count':80,'correct':sum(r['gold']==r['metadata']['rule_prediction'] for r in rows if r['task']=='policy_select'),'results':[{'id':r['id'],'gold':r['gold'],'prediction':r['metadata']['rule_prediction'],'correct':r['gold']==r['metadata']['rule_prediction'],'main_eligible':r['metadata']['candidate_count']>=2} for r in rows if r['task']=='policy_select']})
 # Source snapshot digest pins cover relevant implementation, specification and tests.
 patterns=['evaluation/policy_dataset_v0/canonical-tools-v0.json','tests/fixtures/session_notes/representative-v1.json','backend/services/**/*.py','backend/tools/*.py','backend/api/chat.py','backend/api/goals.py','backend/api/agent_goals.py','backend/conversation_memory.py','graph/*.py','llm/*.py','memory/*.py','evaluation/policy_dataset_v0/*.py','evaluation/fixtures/policy_dataset_v0/*','evaluation/runtime_policy_v0.py','evaluation/fixtures/runtime_policy_v0.json','docs/contracts/*','docs/*runtime*.md','docs/*understanding*.md','docs/*handoff*.md','docs/business-chain-*.md','tests/test_*runtime*.py','tests/test_*goal*.py','tests/test_*context*.py','tests/test_*followup*.py','tests/test_*understanding*.py','tests/test_*decision*.py','tests/test_*policy*.py','tests/test_*continuity*.py','tests/test_*notes*.py','tests/test_*mistake*.py','tests/test_*verification*.py','tests/test_*retrieval*.py','tests/test_*tool*.py','tests/test_*management*.py','AGENTS.md']
 paths=sorted({p for pat in patterns for p in REPO.glob(pat) if p.is_file()})
 pins={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
 write('audit/source-manifest.json',{'repo':str(REPO),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),'worktree_dirty':True,'source_hashes':pins,'snapshot_digest':H(pins),'scope':'code and synthetic fixture files only; no credentials or user databases','capture_date':'2026-10-06 Asia/Shanghai'})
 (OUT/'audit/git-status.txt').write_text(subprocess.check_output(['git','status','--short'],cwd=REPO,text=True))
 # Frozen excerpts have line provenance; source pins alone are not a read-completeness assertion.
 keyfiles=['backend/services/decision/policy_contracts.py','backend/services/decision/policy_projection.py','backend/services/decision/policy.py','backend/services/decision/router.py','backend/services/decision/resolver.py','graph/question_understanding.py','backend/services/question_understanding.py','backend/services/semantic_resolver.py','backend/services/goals/service.py','backend/services/goals/execution.py','graph/retrieval_policy.py','graph/conversation_context.py','backend/services/agent_runtime/contracts.py','backend/services/learning_task.py']
 for f in keyfiles:
  p=OUT/'audit/contract-source'/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((REPO/f).read_bytes())
 print(D({'cases':len(rows),'splits':dict(counts),'groups':len(groups)}))

if __name__=='__main__':
 with tempfile.TemporaryDirectory(prefix='texa-benchmark-build-') as td,patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')):
  main(Path(td))
