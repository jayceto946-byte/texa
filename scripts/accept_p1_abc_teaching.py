"""Authorized small real-provider acceptance on synthetic inputs, not a benchmark.

Uses the saved default profile only in memory. No profile/credential writer,
production library, judge model, forced tool_choice or automatic paid retry.
The source-anchor selection is a fixture; expansion/packing/Runtime/math/storage
are production code. Results and usage are real; private reasoning is stripped.
"""
from __future__ import annotations
import argparse, asyncio, fcntl, hashlib, json, os, sys, threading, time
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
QA=Path('/private/tmp/texa-p1-abc-teaching-20261018')
OUT=ROOT/'docs/qa/p1-abc-integration/real-teaching-2026-10-18'
BOOK='p1-acceptance-synthetic'
EXTREMA=r'已知函数 $f(x)=x^3-3x$，求它在闭区间 $[-3,3]$ 上的最大值与最小值，并给出完整过程。'
STEP_ANSWER='第一步：求导得 f\'(x)=3x^2-3。\n第二步：令导数为零，得 x=-1 或 x=1。\n第三步：只比较 f(-1)=2 和 f(1)=-2，故最大值2，最小值-2。'
FINAL_ONLY='最大值2，最小值-2。'
def structured(problem):return '<math-context>'+json.dumps(problem,ensure_ascii=False)+'</math-context>\n核验关键步骤并解释。'
CASES={
 'A1':('runtime','rolle','请依据教材完整解释罗尔定理，说明全部适用条件、结论，以及省略端点条件为什么不成立。'),
 'A2':('runtime','mean','请依据教材连续的原文块讲解拉格朗日中值定理的证明，写出辅助函数、两端点值、导数和最后结论。'),
 'A3':('runtime','figure','请根据教材例题的图1.1计算阴影面积。'),
 'B1':('runtime',None,structured({'variable':'x','domain':'real','conditions':['x!=1'],'premise':{'left':'(x^2-1)/(x-1)'}})),
 'B2':('runtime',None,structured({'variable':'x','domain':'real','premise':{'left':'sqrt(x)','right':'-1'}})),
 'B3':('runtime',None,'实数范围内，把 sqrt(x^2) 直接化为 x 这一步是否成立？请核验，并区分所列步骤的验证与整题证明。'),
 'C1':('exercise','extrema',EXTREMA),
 'C2':('mistake','extrema',STEP_ANSWER),
 'C3':('mistake','extrema',FINAL_ONLY),
 'AB':('runtime','extrema','请先依据教材讲解闭区间最值的完整流程，再计算 f(x)=x^3-3x 在[-3,3]的最值并核验关键数学结果。'),
 'AC':('candidate','extrema',EXTREMA),
 'ABC':('edit','extrema','修改已生成知识结构的题目及已确认诊断的错题，检查旧状态失效。'),
}
def write(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=lambda v:v.model_dump() if hasattr(v,'model_dump') else str(v))+'\n');temp.replace(path)
def load(path,default):
 if path.exists():return json.loads(path.read_text())
 packed=path.with_suffix(path.suffix+'.gz')
 if packed.exists():
  import gzip
  return json.loads(gzip.decompress(packed.read_bytes()))
 return default

def setup():
 QA.mkdir(parents=True,exist_ok=True)
 os.environ.update(ENV_PATH=str(QA/'empty.env'),DATA_DIR=str(QA/'data'),PROGRESS_PATH=str(QA/'progress'),
   BOOKS_PATH=str(QA/'books'),VECTOR_DB_PATH=str(QA/'vector'),MINERU_OUTPUT_PATH=str(QA/'mineru'),
   HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TEXA_TEACHING_PROMPT_MODE='refined')
 from dotenv import dotenv_values
 from llm.configuration import resolve_model_role,model_settings_env_values,credential_env_name
 directory=Path.home()/'Library/Application Support/kaoyan-assistant-desktop'
 env={k:v for k,v in dotenv_values(directory/'.env').items() if v is not None}
 profiles=json.loads((directory/'data/model_profiles.json').read_text())
 profile=next(p for p in profiles if p['id']=='default')
 values=model_settings_env_values({**profile,'credentials':{}})
 resolved={**env,**values}
 role=resolve_model_role('reasoning',resolved)
 cid=profile['roles']['reasoning'].get('credential_id') or role.provider.provider_id
 if role.model!='qwen3.7-plus' or role.provider.provider_id!='qwen' or urlparse(role.endpoint).hostname!='dashscope.aliyuncs.com' or not role.credential_configured:
  raise RuntimeError('saved default Qwen profile unavailable; no substitution')
 # Require the actual Qwen credential source, rather than a role-key fallback.
 dedicated=env.get(credential_env_name(cid)) or env.get('DASHSCOPE_API_KEY') or env.get('QWEN_API_KEY')
 if not dedicated or role.api_key!=dedicated:raise RuntimeError('dedicated Qwen credential source not established')
 import config
 config.get_model_role_config=lambda which='reasoning':resolve_model_role(which,resolved)
 return role

def corpus():
 from ingestion.document_ir import CanonicalBook,DocumentBlock,canonical_book_fingerprint,persist_canonical_book
 def section(key,title,rows):
  path=[title];return [DocumentBlock(key+'-h','heading',title,path,1,1,source_kind='pdf',source_file='synthetic.md')]+[
   DocumentBlock(key+'-'+str(i),kind,text,path,1,1,source_kind='pdf',source_file='synthetic.md') for i,(kind,text) in enumerate(rows)]
 blocks=[]
 blocks+=section('rolle','第一章 罗尔定理',[
  ('paragraph',r'设实数 $a<b$。函数 $f$ 在 $[a,b]$ 上连续，在 $(a,b)$ 上可导，并且 $f(a)=f(b)$。'),
  ('formula',r'则存在 $\xi\in(a,b)$，使 $f\prime(\xi)=0$。'),
  ('paragraph',r'若省去端点相等条件，$f(x)=x$ 在 $[0,1]$ 上满足连续和内部可导，但导数处处为1，结论不成立。')])
 blocks+=section('mean','第二章 中值定理证明',[
  ('paragraph',r'设 $a<b$，$f$ 在闭区间 $[a,b]$ 连续，在开区间 $(a,b)$ 可导。'),
  ('formula',r'令 $k=\frac{f(b)-f(a)}{b-a}$，构造 $g(x)=f(x)-f(a)-k(x-a)$。'),
  ('paragraph',r'$g$ 在闭区间连续、开区间可导，且 $g(a)=0$、$g(b)=f(b)-f(a)-k(b-a)=0$。'),
  ('paragraph',r'对 $g$ 应用罗尔定理，存在 $\xi\in(a,b)$ 使 $g\prime(\xi)=0$。'),
  ('formula',r'$g\prime(x)=f\prime(x)-k$，所以 $f\prime(\xi)=\frac{f(b)-f(a)}{b-a}$。')])
 blocks+=section('figure','第三章 缺图例题',[
  ('example','例3.1：根据图1.1计算阴影部分的面积，长度单位为cm。'),
  ('figure','图1.1 阴影区域示意（本合成样本未提供图片像素，也未给出几何形状和尺寸）。')])
 blocks+=section('extrema','第四章 闭区间最值',[
  ('paragraph',r'函数在闭区间连续则能取得最大值最小值。若内部可导，先求导数为零的内部驻点，再比较驻点和两个端点的函数值；若有内部不可导点也需纳入。'),
  ('formula',r'对 $f(x)=x^3-3x$，有 $f\prime(x)=3x^2-3$，驻点为 $x=-1,1$。'),
  ('paragraph',r'在 $[-3,3]$ 上，$f(-3)=-18$，$f(-1)=2$，$f(1)=-2$，$f(3)=18$。所以最大值18，最小值-18。'),
  ('exercise','1. '+EXTREMA)])
 book=CanonicalBook(BOOK,'pdf',blocks,'self-authored-acceptance-v1')
 fingerprint=canonical_book_fingerprint(book);persist_canonical_book(book)
 # Synthetic-only manifest provider; no production map/index activation.
 manifest={'index_version':'acceptance-v1','canonical_hash':fingerprint}
 import ingestion.index_pipeline as pipeline
 import backend.services.figure_learning as figures
 pipeline.load_index_manifest=lambda name:manifest if name==BOOK else {}
 figures.load_index_manifest=pipeline.load_index_manifest
 anchors={key:{'book_name':BOOK,'chunk_id':key+'-anchor','chapter':next(b.section_path[0] for b in blocks if b.block_id==key+'-0'),
   'section_path':next(b.section_path for b in blocks if b.block_id==key+'-0'),'role':'derivation' if key=='mean' else 'definition' if key=='rolle' else 'example',
   'provenance_schema':'texa.provenance/v1','index_version':'acceptance-v1','canonical_hash':fingerprint,
   'source_block_ids':[key+'-0'],'text':next(b.text for b in blocks if b.block_id==key+'-0')} for key in ('rolle','mean','figure','extrema')}
 kg_dir=QA/'mineru'/BOOK/'hybrid_auto';kg_dir.mkdir(parents=True,exist_ok=True)
 concepts=[('closed_extrema','闭区间最值','concept'),('derivative','导数','concept'),('stationary','驻点','concept'),('endpoint','端点比较','property'),('extreme_value_theorem','最值定理','theorem')]
 write(kg_dir/(BOOK+'_knowledge_graph.json'),{'meta':{'version':'acceptance-synthetic-v1'},'concepts':[{'concept_id':cid,'canonical_name':name,'aliases':[],'roles':[kind]} for cid,name,kind in concepts],
  'occurrences':[{'concept_id':cid,'chunk_id':'extrema-anchor'} for cid,_,_ in concepts],'relations':[],'formulas':[]})
 write(kg_dir/(BOOK+'_middle_chunks.json'),[{'chunk_id':'extrema-anchor','section_title':'第四章 闭区间最值','content':'闭区间最值、导数、驻点与端点比较。'}])
 return book,anchors

def install_meter(role,case):
 import httpx
 ledger_path=OUT/'provider-receipts.json'
 ledger=load(ledger_path,{'authorization':'user: 授权真实教学测试。','profile':'saved default','provider':'qwen','model':role.model,
   'limits':{'cases':12,'requests':40,'per_request_output_tokens':16384,'total_output_tokens':262144,'input_bytes':1000000},'cases_started':[],'requests':[],'input_bytes':0})
 if case in ledger['cases_started']:raise RuntimeError('case already started; no automatic paid retry')
 ledger['cases_started'].append(case);write(ledger_path,ledger)
 lock=threading.RLock();current={}
 def guard(request):
  if request.url.host in {'127.0.0.1','localhost','::1'}:return
  if request.url.host!='dashscope.aliyuncs.com' or not request.url.path.endswith('/chat/completions'):raise RuntimeError('remote destination blocked')
  payload=json.loads(request.content);size=len(request.content)
  if payload.get('model')!=role.model or payload.get('max_completion_tokens')!=16384:raise RuntimeError('wrong model/output cap')
  if any(isinstance(m.get('content'),list) for m in payload.get('messages',[])):raise RuntimeError('this acceptance sends text only, no image bytes')
  with lock:
   output=sum(r.get('usage',{}).get('output_tokens',16384) for r in ledger['requests'])
   per=sum(r['case']==case for r in ledger['requests'])
   if len(ledger['requests'])>=40 or per>=5 or output+16384>262144 or ledger['input_bytes']+size>1000000:raise RuntimeError('acceptance budget exhausted')
   item={'index':len(ledger['requests'])+1,'case':case,'input_bytes':size,'status':'requested','started_at':time.time()}
   ledger['requests'].append(item);ledger['input_bytes']+=size;current[threading.get_ident()]=(item,time.monotonic());write(ledger_path,ledger)
 original=httpx.Client.__init__
 def init(self,*a,**kw):
  hooks=dict(kw.pop('event_hooks',{}) or {});hooks['request']=[*hooks.get('request',[]),guard];kw['event_hooks']=hooks;kw['trust_env']=False;return original(self,*a,**kw)
 httpx.Client.__init__=init
 from langchain_openai import ChatOpenAI
 original_payload=ChatOpenAI._get_request_payload
 def payload(self,*a,**kw):
  data=original_payload(self,*a,**kw);data.pop('max_tokens',None);data['max_completion_tokens']=16384;return data
 ChatOpenAI._get_request_payload=payload
 from langchain_core.callbacks import BaseCallbackHandler
 class Receipt(BaseCallbackHandler):
  def on_llm_end(self,response,**kwargs):
   message=response.generations[0][0].message
   with lock:
    pair=current.get(threading.get_ident())
    if pair:
     item,at=pair;item.update(status='returned',usage=message.usage_metadata or {},request_ms=round((time.monotonic()-at)*1000,2),finish_reason=message.response_metadata.get('finish_reason'));write(ledger_path,ledger)
  def on_llm_error(self,error,**kwargs):
   with lock:
    pair=current.get(threading.get_ident())
    if pair:pair[0].update(status='error',error_type=type(error).__name__);write(ledger_path,ledger)
 from llm.factory import build_chat_model
 def factory(resolved,temperature=0.1,**kw):
  kw.update(max_retries=0,stream_usage=True,request_timeout=180)
  return build_chat_model(resolved,temperature,**kw).model_copy(update={'callbacks':[Receipt()],'native_output_token_limit':16384,'max_tokens':16384})
 import config
 config.get_llm=lambda temperature=0.1,**kw:factory(role,temperature,**kw)
 return factory

def native(case,question,key,anchors,role,factory):
 from backend.services.agent_runtime.chat_binding import build_math_registry,stream_run
 from backend.services.agent_runtime.textbook_tool import register_textbook_search_runtime
 from backend.services.agent_runtime.contracts import RunCommand
 from backend.services.agent_runtime.store import RuntimeStore
 from llm.agent_adapter import NativeToolAdapter
 registry=build_math_registry();adapter=NativeToolAdapter(role,registry,model_factory=factory);adapter.allow_native_attempt=True
 refs=tuple({k:registry.runtime_tool(name).runtime_metadata()[k] for k in ('id','version','schema_hash')} for name in ('symbolic_math','verify_math_result'))
 state={'user_input':question,'book_name':BOOK if key else '', 'subject':'数学','intent':'qa','use_textbook_context':bool(key),
   'answer_mode':'textbook_grounded' if key else 'global_general','evidence_support':{'status':'not_applicable'} if not key else {},
   'native_loop':True,'_native_limits':{'model_timeout_seconds':180,'run_timeout_seconds':600}}
 if key:
  scope={'id':'acceptance-scope','book_name':BOOK,'subject':'数学','resources':[{'book_name':BOOK,'is_primary':True,'is_selected':True}], 'index_versions':{BOOK:'acceptance-v1'}}
  register_textbook_search_runtime(registry,scope,versions=lambda name:'acceptance-v1',retrieve=lambda *a,**kw:{'evidence_items':[anchors[key]],'evidence_support':{'status':'supported'},'retrieval_status':'synthetic-anchor-fixture'})
  meta=registry.runtime_tool('search_textbook').runtime_metadata();state.update(_native_preparation_ref={k:meta[k] for k in ('id','version','schema_hash')},_runtime_textbook_scope=scope)
 store=RuntimeStore(QA/'progress/runtime.db');owner='owner_'+case
 run=store.create(RunCommand(case,case,'task_'+case,'session_'+case,'turn_'+case,question,owner,budget_calls=4,budget_model_calls=5,required_outputs=[{'id':'answer','kind':'content'}]))['run']['id']
 store.configure_chat(run,owner,state=state,candidates=refs,request_question=question,book_name=state['book_name'],subject='数学')
 events=[]
 async def consume():
  response=stream_run(store,run,owner,registry,adapter)
  async for chunk in response.body_iterator:
   payload=json.loads(chunk[6:]);events.append(payload)
  await response.aclose()
 asyncio.run(consume());snap=store.snapshot(run)
 return {'kind':'actual Runtime/SSE + real provider','question':question,'answer':(snap['run']['output'] or {}).get('answer',''),
  'task_status':snap['task']['status'],'run_status':snap['run']['status'],'error_code':snap['run']['error_code'],
  'model_calls':snap['consumed_model_calls'],'tool_calls':snap['tool_calls'],'verification':snap['task'].get('verification'),
  'native_messages':snap['run']['checkpoint'].get('native_messages'),'events':events}

def exercise(case,book,anchors,question,candidate=False):
 from backend.api import exercises as api
 from backend.services import exercise_answers
 from backend.schemas import ExerciseAnswerSaveRequest,ExerciseBatchAddRequest
 from memory.exercise_bank import ExerciseRecord
 bank=api._bank(BOOK)
 if candidate:
  from memory.exercise_candidate_projection import source_registry
  from memory.textbook_exercise_importer import analyze_learning_unit_candidates,ExtractedTextbookExerciseText
  from memory import textbook_exercise_importer as importer
  block=next(b for b in book.blocks if b.block_type=='exercise')
  unit={'unit_id':'acceptance-exercise','kind':'exercise','text':block.text,'chapter':block.section_path[0], 'page_start':1,'page_end':1,'source_block_ids':[block.block_id],'truncated':False}
  registry=source_registry(book,[unit],{block.block_id});from ingestion.document_ir import canonical_book_fingerprint
  fingerprint=canonical_book_fingerprint(book);scope={'chapter':'','page_start':None,'page_end':None,'source_mode':'exercise_sections'}
  candidates=analyze_learning_unit_candidates([unit],book_name=BOOK,subject='数学',limit=1,source_blocks=registry,canonical_hash=fingerprint,scope=scope)
  item=candidates[0];request=api._candidate_to_add_payload(item).model_dump();request['candidate_context']={'projection':item.projection,'review':None}
  extracted=ExtractedTextbookExerciseText(text=block.text,provider='canonical-learning-units',book_name=BOOK,units=[unit],source_blocks=registry,canonical_hash=fingerprint)
  importer.extract_textbook_exercise_text=lambda *a,**kw:extracted
  receipt=api.batch_add_reviewed_candidates(ExerciseBatchAddRequest(candidate_contract_version=1,exercises=[request]),book_name=BOOK)
  record=bank.get(receipt['data'][0].id)
 else:
  record=ExerciseRecord(id=case,question_text=question,subject='数学',chapter='第四章 闭区间最值');bank.add(record);record=bank.get(record.id);receipt=None
 exercise_answers.retrieve_node=lambda state:{'evidence_items':[anchors['extrema']],'evidence_support':{'status':'supported'},'retrieval_status':'synthetic-anchor-fixture'}
 response=exercise_answers.generate_answer(record,book_name=BOOK)
 if not response.get('success'):return {'generation':response,'exercise_id':record.id,'import_receipt':receipt}
 from backend.job_manager import get_job_manager
 jobs=get_job_manager();job=jobs.create_job(api.EXERCISE_ANSWER_JOB_TYPE,{'exercise_id':record.id,'book_name':BOOK},status='running')
 jobs.update_job(job['id'],status='completed',result=response['data'])
 saved=api.save_exercise_answer(ExerciseAnswerSaveRequest(id=record.id,answer=response['data']['answer'],knowledge_job_id=job['id']),book_name=BOOK)
 return {'kind':'actual exercise generation/metadata/Job/API save + real provider','question':record.question_text,'generation':response,'save':saved,'exercise_id':record.id,'import_receipt':receipt,'persisted':bank.get(record.id).to_dict()}

def mistake(case,answer,role,factory):
 from backend.api import mistakes as api
 from memory.mistake_book import MistakeRecord
 from memory.mistake_lifecycle import MistakeLifecycleStore
 from backend.services.exercise_knowledge import explain_mistake
 from utils.thinking_filter import strip_thinking
 mb=api._mb(BOOK);record=MistakeRecord(id=case,question_text=EXTREMA,correct_answer='最大值18，在x=3处取得；最小值-18，在x=-3处取得。',subject='数学',chapter='第四章 闭区间最值')
 mb.add(record);lifecycle=MistakeLifecycleStore(mb.store)
 aid=lifecycle.append_occurrence_once(record.id,'acceptance-'+case,answer=answer,source_ref={'type':'exercise_attempt','operation_id':case})
 public=[]
 def invoke(prompt):
  raw=factory(role,0.1).invoke(prompt).content;public.append(strip_thinking(raw));return raw
 response=explain_mistake(mb,record.id,book_name=BOOK,invoke=invoke)
 return {'kind':'actual mistake explanation/metadata/storage + real provider','question':EXTREMA,'student_answer':answer,'raw_public_response':public,'explanation':response['explanation'],'metadata_status':response['metadata_status'],
   'diagnosis_errors':response['diagnosis_errors'],'record':response['record'].to_dict(),'attempt_id':aid,'attempts':lifecycle.list_attempts(record.id),'weak_points':mb.get_weak_points()}

def edit():
 from backend.api import exercises, mistakes
 from memory.mistake_lifecycle import MistakeLifecycleStore
 from knowledge.exercise_structure import build_catalog
 ac=load(OUT/'AC.json',{});c2=load(OUT/'C2.json',{})
 bank=exercises._bank(BOOK);record=bank.get(ac.get('exercise_id',''))
 mb=mistakes._mb(BOOK);mistake_record=mb.get('C2');lifecycle=MistakeLifecycleStore(mb.store)
 result={'kind':'local version checks on real-model-generated artifacts','remote_model_required':False,'checks':{}}
 if not record or record.knowledge_structure.get('status')!='proposed':
  result['checks']['exercise_classification_invalidation']='NOT VERIFIED: no saved proposed real classification'
 else:
  record.question_text=record.question_text.replace('[-3,3]','[-4,4]');bank.update(record)
  result['checks']['exercise_classification_invalidation']=bank.get(record.id).knowledge_structure.get('status')=='stale'
 attempts=lifecycle.list_attempts('C2');attempt=next((a for a in attempts if a.get('diagnosis')),None)
 if not attempt:
  result['checks']['diagnosis_invalidation']='NOT VERIFIED: no accepted real-model evidence'
 else:
  before_sm2=mistake_record.sm2.copy();c=lifecycle.set_attempt_diagnosis('C2',attempt['id'],expected_revision=mistake_record.revision,operation_id='acceptance-confirm',catalog=build_catalog(mistake_record,book_name=BOOK),confirm=True,expected_diagnosis_digest=attempt['diagnosis_digest'])
  weak_before=mb.get_weak_points();r=mb.get('C2')
  changed=lifecycle.change_record('C2',expected_revision=r.revision,operation_id='acceptance-edit',changes={'question_text':EXTREMA.replace('[-3,3]','[-4,4]')})
  result.update(weak_before=weak_before,weak_after=mb.get_weak_points(),change_receipt=changed)
  result['checks']['diagnosis_invalidation']=not mb.get_weak_points() and mb.get('C2').content_revision>r.content_revision
  result['checks']['sm2_unchanged']=mb.get('C2').sm2==before_sm2
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--authorized',action='store_true');p.add_argument('--case',choices=CASES)
 args=p.parse_args()
 if not args.prepare and (not args.authorized or not args.case):p.error('explicit authorization and one case required')
 role=setup();book,anchors=corpus()
 manifest={'model':role.model,'provider':role.provider.provider_id,'profile_id':'default','authorization':'2026-10-18 user: 授权真实教学测试。',
   'scope':'self-authored synthetic Canonical IR/KG/questions and disposable SQL; real provider, Runtime, math and metadata; retrieval anchors are fixture-selected; production retrieval/real vision not claimed',
   'cases':{key:{'kind':v[0],'source_section':v[1],'input':v[2]} for key,v in CASES.items()},
   'limits':{'cases':12,'requests':40,'per_request_output_tokens':16384,'total_output_tokens':262144,'input_bytes':1000000,'paid_retries':0}}
 write(OUT/'manifest.json',manifest)
 if args.prepare:
  from backend.services.exercise_knowledge import prepare_analysis
  from memory.exercise_bank import ExerciseRecord
  catalog=prepare_analysis(ExerciseRecord(question_text=EXTREMA,chapter='第四章 闭区间最值'),book_name=BOOK)['catalog']
  write(OUT/'preflight.json',{'provider':role.provider.provider_id,'model':role.model,'credential_source_verified':True,'candidate_ids':[c['concept_id'] for c in catalog['candidates']],'canonical_blocks':len(book.blocks),'no_remote_requests':True})
  if len(catalog['candidates'])!=5:raise RuntimeError('synthetic chapter catalog incomplete')
  print('Preflight PASS; no remote calls; five canonical IDs and self-authored corpus ready.');return
 QA.mkdir(exist_ok=True);lock=(QA/'execution.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 factory=install_meter(role,args.case);start=time.monotonic()
 try:
  kind,key,question=CASES[args.case]
  if kind=='runtime':result=native(args.case,question,key,anchors,role,factory)
  elif kind in {'exercise','candidate'}:result=exercise(args.case,book,anchors,question,candidate=kind=='candidate')
  elif kind=='mistake':result=mistake(args.case,question,role,factory)
  else:result=edit()
 except Exception as exc:
  import traceback
  result={'execution_status':'FAIL','error_type':type(exc).__name__,'error_frames':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)]}
 result.update(case=args.case,total_ms=round((time.monotonic()-start)*1000,2));write(OUT/(args.case+'.json'),result)
 print(json.dumps({'case':args.case,'total_ms':result['total_ms'],'run_status':result.get('run_status'),'execution_status':result.get('execution_status','returned'),'error_type':result.get('error_type')},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
