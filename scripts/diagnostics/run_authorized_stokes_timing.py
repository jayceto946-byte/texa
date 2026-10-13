"""Single explicitly authorized Stokes run, hard ¥0.60/3 request guard."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from urllib.parse import urlparse

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorized", action="store_true")
    if not parser.parse_args().authorized:
        parser.error("explicit single-run authorization flag required")
    SOURCE = Path('/Users/jichengqian/Documents/ChatGPT/texa')
    B = Path('/Users/jichengqian/.codex/worktrees/agent-early-output/texa')
    QA = Path('/private/tmp/texa-stream-diagnostics-20261013-authorized')
    if QA.exists():
        raise SystemExit('single run directory already exists; no automatic retry')
    QA.mkdir(mode=0o700)
    CODE = QA/'code'
    CODE.mkdir()
    for name in ['backend','graph','llm','knowledge','memory','utils','ingestion','agents']:
        shutil.copytree(SOURCE/name, CODE/name, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copy2(SOURCE/'config.py', CODE/'config.py')
    sys.path.insert(0,str(CODE))
    os.environ.update(ENV_PATH='/Users/jichengqian/Library/Application Support/kaoyan-assistant-desktop/.env', DATA_DIR=str(QA/'data'), PROGRESS_PATH=str(QA/'progress'), BOOKS_PATH=str(QA/'books'), VECTOR_DB_PATH=str(QA/'vector'), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')

    def save(name, data):
        target=QA/name; tmp=target.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');tmp.replace(target)

    spec=importlib.util.spec_from_file_location('diag', B/'scripts/diagnostics/provider_stream_timing.py')
    diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)
    from config import get_model_role_config
    from backend.services.agent_runtime.chat_binding import build_math_registry,stream_run
    from backend.services.agent_runtime.store import RuntimeStore
    from backend.services.agent_runtime.contracts import RunCommand
    from backend.services.agent_runtime.native_loop import PUBLIC_DELIVERY_INSTRUCTION
    from graph.generator import prepare_answer_generation
    from langchain_core.messages import messages_to_dict,SystemMessage
    from llm.agent_adapter import NativeToolAdapter
    from langchain_core.callbacks import BaseCallbackHandler
    import httpx

    role=get_model_role_config()
    if role.model!='qwen3.7-plus' or urlparse(role.endpoint).hostname!='dashscope.aliyuncs.com' or not role.credential_configured or role.options.get('extra_body',{}).get('enable_thinking') is not True:
        raise SystemExit('configured model/pricing/thinking mismatch; no call')
    old=json.loads((SOURCE/'docs/qa/evidence/agent-loop-performance/paired-2026-10-13/manifest.json').read_text())
    case=next(c for c in old['cases'] if c['id']=='stokes-A')
    ledger={'authorization':'user 授权 after single Stokes / 3 requests / ¥0.60 proposal','requests':[], 'input_bytes':0,'reserved_or_used_cny':0.0,'max_requests':3,'max_input_bytes':75000,'max_output_tokens':49182,'cost_cap_cny':0.60}
    probe=diag.StreamTimingProbe();lock=threading.RLock();pairs={}

    def guard(request):
        payload=json.loads(request.content)
        if request.url.host!='dashscope.aliyuncs.com' or not request.url.path.endswith('/chat/completions') or payload.get('model')!='qwen3.7-plus' or payload.get('enable_thinking') is not True or payload.get('max_completion_tokens')!=16384 or 'max_tokens' in payload or payload.get('tool_choice')!='auto' or payload.get('parallel_tool_calls') is not False:
            raise RuntimeError('request outside authorization')
        size=len(request.content);reserved=(size*2+(16384+10)*8)/1e6
        with lock:
            if len(ledger['requests'])>=3 or size>25000 or ledger['input_bytes']+size>75000 or ledger['reserved_or_used_cny']+reserved>0.60:
                raise RuntimeError('authorized budget exhausted')
            index=len(ledger['requests'])+1
            item={'index':index,'input_bytes':size,'reserved_cny':reserved,'status':'requested'}
            ledger['requests'].append(item);ledger['input_bytes']+=size;ledger['reserved_or_used_cny']+=reserved
            pairs[threading.get_ident()]=item
            save('ledger.json',ledger)
            print(json.dumps({'request':index,'reserved_total_cny':round(ledger['reserved_or_used_cny'],6)}),flush=True)

    class Receipt(BaseCallbackHandler):
        def on_llm_end(self, response, **kwargs):
            msg=response.generations[0][0].message;usage=msg.usage_metadata or {}
            with lock:
                item=pairs.get(threading.get_ident())
                if item:
                    item['status']='returned'
                    item['usage']={k:usage[k] for k in ['input_tokens','output_tokens','total_tokens'] if type(usage.get(k)) is int}
                    reasoning=(usage.get('output_token_details') or {}).get('reasoning')
                    if type(reasoning) is int:item['usage']['reasoning_tokens']=reasoning
                    if all(type(usage.get(k)) is int for k in ['input_tokens','output_tokens']):
                        cost=(usage['input_tokens']*2+usage['output_tokens']*8)/1e6
                        item['estimated_cost_cny']=cost;ledger['reserved_or_used_cny']+=cost-item['reserved_cny']
                save('ledger.json',ledger);save('timings.json',probe.records)
        def on_llm_error(self, error, **kwargs):
            with lock:
                item=pairs.get(threading.get_ident())
                if item:item['status']='error'
                save('ledger.json',ledger);save('timings.json',probe.records)

    class Model(diag.DiagnosticChatOpenAI):
        def _get_request_payload(self,*args,**kwargs):
            payload=super()._get_request_payload(*args,**kwargs)
            payload.pop('max_tokens',None);payload['max_completion_tokens']=16384
            if payload.get('tools'):payload['tool_choice']='auto'
            return payload

    client=httpx.Client(trust_env=False,timeout=180,event_hooks={'request':[guard,probe.request_hook],'response':[probe.response_hook]})
    def factory(resolved,temperature,**kwargs):
        return Model(timing_probe=probe,model=resolved.model,temperature=temperature,api_key=resolved.api_key,base_url=resolved.endpoint,streaming=True,timeout=180,max_retries=0,stream_usage=True,http_client=client,extra_body=dict(resolved.options.get('extra_body') or {}),callbacks=[Receipt()])
    registry=build_math_registry();adapter=NativeToolAdapter(role,registry,model_factory=factory);adapter.allow_native_attempt=True
    refs=tuple({k:s.runtime_metadata()[k] for k in ['id','version','schema_hash']} for s in [registry.get('symbolic_math'),registry.get('verify_math_result')])
    required=[{'id':'answer','kind':'content'},{'id':'numeric','kind':'numeric'}]
    store=RuntimeStore(QA/'progress/agent_runtime.db');owner='owner_stream_diagnostic'
    run=store.create(RunCommand('stream-diagnostic','stream-diagnostic','rtask_stream','conv_stream','turn_stream',case['question'],owner,budget_calls=2,budget_model_calls=3,required_outputs=required))['run']['id']
    state={'user_input':case['question'],'intent':'qa','answer_mode':'global_general','use_textbook_context':False,'support_type':'explicit_math_only','native_loop':True,'evidence_support':{'status':'not_applicable'},'required_outputs':required,'_native_limits':{'model_timeout_seconds':180,'run_timeout_seconds':600}}
    messages=prepare_answer_generation(state);messages.insert(0,SystemMessage(content=PUBLIC_DELIVERY_INSTRUCTION))
    store.save_native_messages(run,owner,messages_to_dict(messages));store.configure_chat(run,owner,state=state,candidates=refs,request_question=case['question'],book_name='',subject='数学')
    save('manifest.json',{'question':case['question'],'question_sha256':hashlib.sha256(case['question'].encode()).hexdigest(),'model':'qwen3.7-plus','enable_thinking':True,'temperature':0,'tool_choice':'auto','max_completion_tokens':16384,'model_timeout':180,'run_timeout':600,'required_outputs':required,'source_sha256':{str(p.relative_to(CODE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in CODE.rglob('*.py')},'diagnostic_sha256':hashlib.sha256((B/'scripts/diagnostics/provider_stream_timing.py').read_bytes()).hexdigest()})
    save('ledger.json',ledger)
    events=[];start=time.monotonic()
    async def consume():
        response=stream_run(store,run,owner,registry,adapter)
        try:
            async for data in response.body_iterator:
                e=json.loads(data[6:])['execution_event']
                # Persist timing/protocol summaries only, never prompt/delta text.
                events.append({'seq':e['seq'],'type':e['type'],'lifecycle':e['payload'].get('lifecycle'),'elapsed_ms':e['elapsed_ms'],'received_ms':round((time.monotonic()-start)*1000,3)})
        finally:await response.aclose()
    try:
        asyncio.run(consume())
        snap=store.snapshot(run)
        save('result.json',{'task_status':snap['task']['status'],'run_status':snap['run']['status'],'error_code':snap['run']['error_code'],'total_ms':round((time.monotonic()-start)*1000,3),'model_calls':snap['consumed_model_calls'],'tool_calls':len(snap['tool_calls']),'tool_statuses':[c['status'] for c in snap['tool_calls']],'verification':snap['run']['output'].get('verification') if snap['run']['output'] else None,'events':events})
        save('timings.json',probe.records)
        print(json.dumps({'finished':True,'status':snap['task']['status'],'requests':len(ledger['requests']),'cost_cny':ledger['reserved_or_used_cny'],'directory':str(QA)}),flush=True)
    except Exception as error:
        save('timings.json',probe.records);save('result.json',{'harness_error_type':type(error).__name__,'events':events})
        print(json.dumps({'harness_error_type':type(error).__name__}),flush=True)
    finally:
        # Do not close a timed-out stream still owned by a live worker.
        if all(r['termination']!='running' for r in probe.records):client.close()

if __name__ == "__main__":
    main()
