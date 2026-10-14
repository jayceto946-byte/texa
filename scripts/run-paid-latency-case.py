"""One authorized paired case through native Runtime + actual SSE; no retries.

Synthetic inputs only. Usage/transport timings are counts; credentials and private
reasoning never enter artifacts. A disk ledger fences all 16 cases/64 requests.
"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'docs/qa/evidence/agent-loop-performance/paired-2026-10-13'
QA = Path('/private/tmp/texa-latency-paired-2026-10-13')


def utc():
    return datetime.now(timezone.utc).isoformat()


def write(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


def prepare():
    old = json.loads((ROOT/'docs/qa/evidence/native-tool-loop/paid-2026-10-13/extended-deadline/questions.json').read_text())
    questions = [
        {'id':'concept', 'question':'解释函数在一点可导与连续的关系，给出连续但不可导的反例，并说明反例为何不可导。'},
        {'id':'integral', 'question':'计算定积分 $\\int_0^1 x^2 e^x\\,dx$，给出完整的分部积分推导并核验结果。'},
        {'id':'stokes', 'question':old[1]['question']},
        {'id':'proof', 'question':'用中值定理证明：当 $x>0$ 时，$\\ln(1+x)<x$。说明中值定理的适用条件，以及不等式为何严格。'},
    ]
    arms = {'A': {'enable_thinking':True}, 'B':{'enable_thinking':True, 'thinking_budget':4096},
            'C':{'enable_thinking':False}, 'D':{'enable_thinking':True}}
    cases=[]
    for i,q in enumerate(questions):
        order = list(arms)[i:]+list(arms)[:i]
        for arm in order:
            cases.append({'id':q['id']+'-'+arm, 'question_id':q['id'], 'question':q['question'],
                'arm':arm, 'extra_body':arms[arm], 'tools':arm!='D'})
    manifest={'authorization':'user 执行 after 16-run/64-request/1,449,216-token/¥10 proposal',
        'model':'qwen3.7-plus', 'endpoint_host':'dashscope.aliyuncs.com', 'temperature':0,
        'max_completion_tokens':16384, 'model_timeout':180, 'run_timeout':600,
        'limits':{'runs':16,'requests':64,'input_bytes':400000,'output_tokens':1049216,'cost_cny':10,
                  'per_request_input_bytes':256000,'input_price':2,'output_price':8},
        'context':'empty frozen textbook/ConversationContextPack; synthetic full questions; no user textbook/history',
        'scope':'controlled availability comparison via real chat_binding.stream_run, not API routing/retrieval acceptance',
        'cases':cases}
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/'manifest.json'
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise RuntimeError('frozen manifest mismatch')
    write(path,manifest)
    return manifest


def main():
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--authorized',action='store_true')
    p.add_argument('--case');p.add_argument('--env-file',type=Path)
    args=p.parse_args();manifest=prepare()
    if args.prepare:
        print('Frozen 16 cases, empty shared textbook context, ¥10/64 request cap; no network calls.');return
    if not args.authorized or not args.env_file or not args.env_file.is_file():
        p.error('authorization and configured local env file required')
    case=next(c for c in manifest['cases'] if c['id']==args.case)
    stopped_path=OUT/'stopped-arms.json'
    if stopped_path.exists() and case['arm'] in json.loads(stopped_path.read_text()):
        raise RuntimeError('condition stopped after critical quality failure; no further paid requests')
    QA.mkdir(parents=True,exist_ok=True)
    # Serial process lock: prevent duplicate launches/ledger races.
    import fcntl
    process_lock=(QA/'execution.lock').open('w');fcntl.flock(process_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    os.environ.update(ENV_PATH=str(args.env_file.resolve()),DATA_DIR=str(QA/'data'),PROGRESS_PATH=str(QA/'progress'),
        BOOKS_PATH=str(QA/'books'),VECTOR_DB_PATH=str(QA/'vector'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    from config import get_model_role_config
    role=get_model_role_config()
    if role.model!=manifest['model'] or urlparse(role.endpoint).hostname!=manifest['endpoint_host'] or not role.credential_configured:
        raise RuntimeError('configured endpoint/model/credentials do not match approved pricing scope')
    ledger_path=OUT/'provider-receipts.json'
    ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {'runs_started':[], 'requests':[], 'input_bytes':0,'reserved_or_used_cny':0}
    if case['id'] in ledger['runs_started'] or len(ledger['runs_started'])>=16:
        raise RuntimeError('case already launched or run cap exhausted; no retry')
    ledger['runs_started'].append(case['id']);write(ledger_path,ledger)
    lock=threading.RLock();by_thread={};call_count=0
    def save():write(ledger_path,ledger)
    import httpx
    original_init=httpx.Client.__init__
    def guard(request):
        nonlocal call_count
        if request.url.host in {'127.0.0.1','localhost','::1'}:return
        if request.url.host!=manifest['endpoint_host'] or not request.url.path.endswith('/chat/completions'):
            raise RuntimeError('unapproved network destination')
        payload=json.loads(request.content);size=len(request.content)
        if payload.get('model')!=role.model or payload.get('max_completion_tokens')!=16384 or 'max_tokens' in payload:
            raise RuntimeError('payload output cap mismatch')
        for key,value in case['extra_body'].items():
            if payload.get(key)!=value:raise RuntimeError('reasoning parameter mismatch')
        if bool(payload.get('tools')) != case['tools']:raise RuntimeError('tool availability mismatch')
        reserve=size*2/1e6+(16384+10)*8/1e6
        with lock:
            if (len(ledger['requests'])>=64 or call_count>=(5 if case['tools'] else 1) or
                size>256000 or ledger['input_bytes']+size>400000 or ledger['reserved_or_used_cny']+reserve>10):
                raise RuntimeError('approved budget exhausted')
            call_count+=1;ledger['input_bytes']+=size;ledger['reserved_or_used_cny']+=reserve
            item={'index':len(ledger['requests'])+1,'case':case['id'],'started_at':utc(),'input_bytes':size,
                  'reserved_cny':reserve,'status':'requested','extra_body':case['extra_body'],'tool_choice':payload.get('tool_choice')}
            by_thread[threading.get_ident()]=(item,time.monotonic())
            ledger['requests'].append(item);save()
    def headers(response):
        with lock:
            pair=by_thread.get(threading.get_ident())
            if pair:
                item,at=pair;item['response_headers_ms']=round((time.monotonic()-at)*1000,2)
                item['http_status']=response.status_code;save()
    def init(self,*a,**k):
        hooks=dict(k.pop('event_hooks',{}) or {});hooks['request']=[*hooks.get('request',[]),guard];hooks['response']=[*hooks.get('response',[]),headers]
        k['event_hooks']=hooks;k['trust_env']=False;original_init(self,*a,**k)
    httpx.Client.__init__=init
    from langchain_openai import ChatOpenAI
    original_payload=ChatOpenAI._get_request_payload
    def payload(self,*a,**k):
        data=original_payload(self,*a,**k);data.pop('max_tokens',None);data['max_completion_tokens']=16384
        if not case['tools']:
            for key in ('tools','tool_choice','parallel_tool_calls'):data.pop(key,None)
        elif data.get('tools'):data['tool_choice']='auto'
        return data
    ChatOpenAI._get_request_payload=payload
    from langchain_core.callbacks import BaseCallbackHandler
    from utils.thinking_filter import ThinkingFilter
    class Receipt(BaseCallbackHandler):
        def __init__(self):self.public=ThinkingFilter()
        def on_chat_model_start(self,*a,**k):self.public=ThinkingFilter()
        def on_llm_new_token(self,token,**kwargs):
            with lock:
                pair=by_thread.get(threading.get_ident())
                if pair:
                    item,at=pair;elapsed=round((time.monotonic()-at)*1000,2)
                    item.setdefault('first_chunk_ms',elapsed)
                    msg=getattr(kwargs.get('chunk'),'message',None);text=getattr(msg,'content',None)
                    if isinstance(text,str) and self.public.filter(text).strip():item.setdefault('first_public_ms',elapsed)
        def on_llm_end(self,response,**kwargs):
            msg=response.generations[0][0].message
            with lock:
                pair=by_thread.get(threading.get_ident())
                if pair:
                    item,at=pair;usage=msg.usage_metadata or {}
                    item.update(status='returned',ended_at=utc(),request_ms=round((time.monotonic()-at)*1000,2),
                                usage=usage,finish_reason=msg.response_metadata.get('finish_reason'))
                    if all(isinstance(usage.get(key),int) for key in ('input_tokens','output_tokens')):
                        cost=(usage['input_tokens']*2+usage['output_tokens']*8)/1e6
                        item['estimated_cost_cny']=cost;ledger['reserved_or_used_cny']+=cost-item['reserved_cny']
                    save()
        def on_llm_error(self,error,**kwargs):
            with lock:
                pair=by_thread.get(threading.get_ident())
                if pair:
                    chain=[];cause=error
                    for _ in range(5):
                        if cause is None:break
                        entry={'type':type(cause).__name__}
                        if isinstance(getattr(cause,'errno',None),int):entry['errno']=cause.errno
                        chain.append(entry);cause=cause.__cause__ or cause.__context__
                    pair[0].update(status='error',error_type=type(error).__name__,cause_types=chain,ended_at=utc())
                save()
    from llm.factory import build_chat_model
    from llm.agent_adapter import NativeToolAdapter
    from backend.services.agent_runtime.chat_binding import build_math_registry,stream_run
    from backend.services.agent_runtime.store import RuntimeStore
    from backend.services.agent_runtime.contracts import RunCommand
    from graph.generator import prepare_answer_generation
    from langchain_core.messages import messages_to_dict,SystemMessage
    from backend.services.agent_runtime.native_loop import PUBLIC_DELIVERY_INSTRUCTION
    options={**role.options,'extra_body':{**dict(role.options.get('extra_body') or {}),**case['extra_body']}}
    options['extra_body'].pop('reasoning_effort',None)
    variant=replace(role,options=options)
    def factory(resolved,temperature,**kwargs):
        kwargs['stream_usage']=True
        return build_chat_model(resolved,temperature,**kwargs).model_copy(update={'callbacks':[Receipt()]})
    registry=build_math_registry();adapter=NativeToolAdapter(variant,registry,model_factory=factory);adapter.allow_native_attempt=True
    refs=tuple({k:spec.runtime_metadata()[k] for k in ('id','version','schema_hash')}
               for spec in (registry.get('symbolic_math'),registry.get('verify_math_result'))) if case['tools'] else ()
    store=RuntimeStore(QA/'progress/agent_runtime.db');identity=case['id'];owner='owner_'+identity
    required=[{'id':'answer','kind':'content'}]
    if case['question_id'] in {'integral','stokes'}:required.append({'id':'numeric','kind':'numeric'})
    run=store.create(RunCommand(identity,identity,'rtask_'+identity,'conv_'+identity,'turn_'+identity,case['question'],owner,
        budget_calls=3 if case['tools'] else 0,budget_model_calls=5 if case['tools'] else 1,required_outputs=required))['run']['id']
    state={'user_input':case['question'],'intent':'qa','answer_mode':'global_general','use_textbook_context':False,
        'support_type':'explicit_math_only','native_loop':True,'evidence_support':{'status':'not_applicable'},
        'required_outputs':required,'_native_limits':{'model_timeout_seconds':180,'run_timeout_seconds':600}}
    messages=prepare_answer_generation(state);messages.insert(0,SystemMessage(content=PUBLIC_DELIVERY_INSTRUCTION))
    prompt_hash=hashlib.sha256(json.dumps(messages_to_dict(messages),ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    store.save_native_messages(run,owner,messages_to_dict(messages))
    store.configure_chat(run,owner,state=state,candidates=refs,request_question=case['question'],book_name='',subject='数学')
    events=[];received=[];at=time.monotonic()
    async def consume():
        response=stream_run(store,run,owner,registry,adapter)
        async for data in response.body_iterator:
            event=json.loads(data[6:])['execution_event'];events.append(event)
            received.append({'seq':event['seq'],'type':event['type'],'received_ms':round((time.monotonic()-at)*1000,2)})
        await response.aclose()
    asyncio.run(consume())
    snapshot=store.snapshot(run)
    result={'case':case,'run_id':run,'prompt_hash':prompt_hash,'total_ms':round((time.monotonic()-at)*1000,2),
        'model_calls':snapshot['consumed_model_calls'],'tool_calls':snapshot['tool_calls'],
        'task_status':snapshot['task']['status'],'run_status':snapshot['run']['status'],'error_code':snapshot['run']['error_code'],
        'output':snapshot['run']['output'],'native_messages':snapshot['run']['checkpoint'].get('native_messages'),
        'events':events,'received':received}
    write(OUT/(identity+'.json'),result)
    if snapshot['run']['output']:
        (OUT/(identity+'.md')).write_text(snapshot['run']['output']['answer'])
    print(json.dumps({'case':identity,'status':result['task_status'],'model_calls':result['model_calls'],
                      'tools':len(result['tool_calls']),'total_ms':result['total_ms'],'cost_cny_total':ledger['reserved_or_used_cny']},ensure_ascii=False),flush=True)
    # Timeout worker can outlive run; give it bounded time for usage receipt, no retry.
    if result['error_code']=='model_deadline_exceeded':
        time.sleep(10)


if __name__=='__main__':main()
