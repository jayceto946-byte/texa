"""Authorized production API/Electron acceptance; no raw provider bodies persisted."""
from __future__ import annotations
import hashlib, json, os, sys, threading, time
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PLAN = ROOT / 'docs/qa/evidence/deepseek-production/PAID-ACCEPTANCE-PLAN.json'
OUT = ROOT / 'docs/qa/evidence/deepseek-production/paid'
QA = Path('/private/tmp/texa-deepseek-production-paid')

def write(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    tmp.replace(path)

def utc(): return datetime.now(timezone.utc).isoformat()

def persist_qa_config(writer, values):
    writer({k: v for k, v in values.items()
            if not any(secret in k.upper() for secret in ('API_KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'PRIVATE_KEY', 'AUTHORIZATION'))})

class Budget:
    def __init__(self, plan, approval, path):
        self.plan = json.loads(plan.read_text())
        if not approval.get('approved') or approval.get('plan_sha256') != hashlib.sha256(plan.read_bytes()).hexdigest():
            raise PermissionError('acceptance approval missing')
        self.path, self.lock, self.case = path, threading.RLock(), None
        self.rows = json.loads(path.read_text()) if path.exists() else []
        self.by_thread = {}
    def before(self, request):
        if request.url.host in {'127.0.0.1','localhost','::1'}: return
        model = {'api.deepseek.com':'deepseek-flash','dashscope.aliyuncs.com':'qwen3.7-plus'}.get(request.url.host)
        if not model or not request.url.path.endswith('/chat/completions'):
            raise PermissionError('unapproved network destination')
        body = json.loads(request.content)
        output = body.get('max_tokens', body.get('max_completion_tokens'))
        size = len(request.content) + 2048
        with self.lock:
            case = next((c for c in self.plan['cases'] if c['id']==self.case), None)
            if not case or body.get('model') != model or size > 32768:
                raise PermissionError('acceptance case/input/model denied')
            if (case['id']=='qwen-smoke') != (model=='qwen3.7-plus'):
                raise PermissionError('acceptance model differs from case')
            cap = case.get('output_cap_per_request', case.get('output_cap'))
            if not isinstance(output,int) or not 0 < output <= cap:
                raise PermissionError('output cap missing/exceeded')
            own = [r for r in self.rows if r['model']==model]
            current = [r for r in own if r['case']==self.case]
            if any(r['status'] in {'error','unknown','reserved'} for r in current):
                raise PermissionError('prior request has no complete usage; no retry')
            caps = self.plan.get('caps', {})
            request_cap = min(1, caps.get('qwen_requests', 1)) if model=='qwen3.7-plus' else min(10, caps.get('deepseek_requests', 10))
            if len(current)>=case['requests'] or len(own)>=request_cap:
                raise PermissionError('request count exhausted')
            if sum(r['output_cap'] for r in current)+output > case['requests']*cap:
                raise PermissionError('case output exhausted')
            if sum(32768+r['output_cap'] for r in self.rows)+32768+output > min(421888, caps.get('total_tokens', 421888)):
                raise PermissionError('total token reservation exhausted')
            currency = 'CNY' if model=='qwen3.7-plus' else 'USD'
            rates = (2,8) if currency=='CNY' else (.3,1.2)
            reserved = (32768*rates[0]+(output+10)*rates[1])/1e6
            if sum(r['reserved_cost'] for r in own)+reserved > (min(.25, caps.get('cost_cny', .25)) if currency=='CNY' else min(.20, caps.get('cost_usd', .20))):
                raise PermissionError('currency reservation exhausted')
            assistants = [m for m in body['messages'] if m['role']=='assistant']
            row={'index':len(self.rows)+1,'model':model,'case':self.case,'started_at':utc(),
                 'input_bytes_upper':size,'input_cap':32768,'output_cap':output,'currency':currency,
                 'reserved_cost':reserved,'status':'reserved','wire_roles':[m['role'] for m in body['messages']],
                 'tool_reply_ids':[m.get('tool_call_id') for m in body['messages'] if m['role']=='tool'],
                 'assistant_reasoning_present':[isinstance(m.get('reasoning_content'),str) for m in assistants],
                 'assistant_tool_ids':[[t['id'] for t in m.get('tool_calls',[])] for m in assistants],
                 'tools_offered':[t['function']['name'] for t in body.get('tools',[])]}
            self.rows.append(row);self.by_thread[threading.get_ident()]=(row,time.monotonic());write(self.path,self.rows)
    def headers(self,response):
        with self.lock:
            pair=self.by_thread.get(threading.get_ident())
            if pair:
                pair[0].update(http_status=response.status_code,headers_ms=round((time.monotonic()-pair[1])*1000,2))
                write(self.path,self.rows)
    def select(self,case):
        with self.lock:
            if case not in {c['id'] for c in self.plan['cases']}: raise ValueError('unknown case')
            self.case=case

def main():
    if '--authorized' not in sys.argv: raise SystemExit('explicit approved execution flag required')
    approval=json.loads((OUT/'APPROVAL.json').read_text())
    budget=Budget(PLAN,approval,OUT/'REQUEST-RECEIPTS.json')
    if budget.rows: raise SystemExit('paid execution already started; server cannot restart/retry')
    import fcntl
    lock=(QA/'paid.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    from dotenv import dotenv_values
    source=dotenv_values(Path.home()/'Library/Application Support/kaoyan-assistant-desktop/.env')
    for name in list(os.environ):
        if any(k in name.upper() for k in ('API_KEY','API_SECRET','CREDENTIAL','ACCESS_TOKEN')): os.environ.pop(name,None)
    for provider in ('QWEN','DEEPSEEK'):
        name=f'LLM_CREDENTIAL_{provider}_API_KEY'
        if not source.get(name): raise SystemExit('required credential missing')
        os.environ[name]=source[name]
    env=QA/'local.env';env.touch();env.chmod(0o600)
    os.environ.update(ENV_PATH=str(env),DATA_DIR=str(QA/'data'),PROGRESS_PATH=str(QA/'progress'),
        BOOKS_PATH=str(QA/'books'),VECTOR_DB_PATH=str(QA/'vector'),MINERU_OUTPUT_PATH=str(QA/'mineru'),
        HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',EMBEDDING_LOCAL_FILES_ONLY='1',
        LLM_REASONING_PROVIDER='qwen',LLM_REASONING_MODEL='qwen3.7-plus',LLM_REASONING_CREDENTIAL_ID='qwen',
        KAOYAN_TRUSTED_ORIGINS='http://127.0.0.1:18041')
    # Guard every HTTP client before importing runtime/model dependencies.
    import httpx
    original=httpx.Client.__init__
    def init(self,*a,**k):
        hooks=dict(k.pop('event_hooks',{}) or {})
        hooks['request']=[*hooks.get('request',[]),budget.before]
        hooks['response']=[*hooks.get('response',[]),budget.headers]
        k.update(event_hooks=hooks,trust_env=False);original(self,*a,**k)
    httpx.Client.__init__=init
    original_async=httpx.AsyncClient.__init__
    async def before(request): budget.before(request)
    async def headers(response): budget.headers(response)
    def init_async(self,*a,**k):
        hooks=dict(k.pop('event_hooks',{}) or {});hooks['request']=[*hooks.get('request',[]),before];hooks['response']=[*hooks.get('response',[]),headers]
        k.update(event_hooks=hooks,trust_env=False);original_async(self,*a,**k)
    httpx.AsyncClient.__init__=init_async
    from langchain_core.callbacks import BaseCallbackHandler
    from utils.thinking_filter import ThinkingFilter
    class Receipt(BaseCallbackHandler):
        def __init__(self):self.filter=ThinkingFilter()
        def on_chat_model_start(self,*a,**k):
            self.filter=ThinkingFilter()
            with budget.lock:budget.by_thread.pop(threading.get_ident(),None)
        def on_llm_new_token(self,token,**kwargs):
            pair=budget.by_thread.get(threading.get_ident())
            content=getattr(getattr(kwargs.get('chunk'),'message',None),'content',None)
            if pair:
                pair[0].setdefault('first_chunk_ms',round((time.monotonic()-pair[1])*1000,2))
                if isinstance(content,str) and self.filter.filter(content).strip():pair[0].setdefault('first_public_ms',round((time.monotonic()-pair[1])*1000,2))
        def on_llm_end(self,response,**kwargs):
            with budget.lock:
                pair=budget.by_thread.get(threading.get_ident())
                if not pair:return
                row,at=pair;msg=response.generations[0][0].message;usage=msg.usage_metadata or {}
                numeric={k:usage[k] for k in ('input_tokens','output_tokens','total_tokens') if isinstance(usage.get(k),int)}
                numeric['reasoning_tokens']=(usage.get('output_token_details') or {}).get('reasoning')
                if isinstance(numeric.get('reasoning_tokens'), int) and isinstance(numeric.get('output_tokens'), int) and not msg.tool_calls:
                    numeric['final_content_tokens']=numeric['output_tokens']-numeric['reasoning_tokens']
                numeric['cached_input_tokens']=(usage.get('input_token_details') or {}).get('cache_read',0)
                row.update(status='returned' if all(k in numeric for k in ('input_tokens','output_tokens')) else 'unknown',usage=numeric,
                    elapsed_ms=round((time.monotonic()-at)*1000,2),ended_at=utc(),finish_reason=msg.response_metadata.get('finish_reason'))
                if row['status']=='returned':
                    inp,out=numeric['input_tokens'],numeric['output_tokens'];cached=numeric['cached_input_tokens'] or 0
                    if inp>32768 or out>row['output_cap']:row['status']='cap_violation';budget.case=None
                    else:
                        if row['currency']=='USD':
                            dt=datetime.fromisoformat(row['started_at']);peak=dt.weekday()<5 and (1<=dt.hour<4 or 6<=dt.hour<10)
                            scale=1 if peak else .5
                            row.update(tariff_band='peak' if peak else 'offpeak',estimated_cost=((inp-cached)*.3+cached*.006+out*1.2)*scale/1e6)
                        else:row.update(tariff_band='undiscounted_list',estimated_cost=((inp-cached)*2+cached*.4+out*8)/1e6)
                write(budget.path,budget.rows)
        def on_llm_error(self,error,**kwargs):
            with budget.lock:
                pair=budget.by_thread.get(threading.get_ident())
                if pair:pair[0].update(status='error',error_type=type(error).__name__,ended_at=utc());write(budget.path,budget.rows)
    from llm import factory
    original_factory=factory._chat_transports['openai_compatible']
    def observed(resolved,temperature,**kwargs):
        kwargs.update(max_retries=0,stream_usage=True,request_timeout=180)
        case = next((c for c in budget.plan['cases'] if c['id'] == budget.case), None)
        cap = case.get('output_cap_per_request', case.get('output_cap')) if case else 8192
        return original_factory(resolved,temperature,**kwargs).model_copy(update={'callbacks':[Receipt()],'max_tokens':cap})
    factory.register_chat_transport('openai_compatible',observed,capabilities=factory.transport_capabilities('openai_compatible'))
    import backend.main as app_module
    from backend.api import system
    original_write_env = system._write_env_values
    def write_public_config(values):
        # The ordinary profile writer migrates existing credentials to .env.
        # QA credentials are inherited in RAM; never duplicate them on disk.
        persist_qa_config(original_write_env, values)
    system._write_env_values = write_public_config
    from llm.configuration import model_settings_payload
    for provider,model,name in [('qwen','qwen3.7-plus','验收 Qwen 默认'),('deepseek','deepseek-flash','验收 Flash 可选')]:
        payload=model_settings_payload({});payload.update(id='paid-'+provider,name=name,multimodal_mode='native')
        for role in ('reasoning','vision'):
            payload['roles'][role].update(provider=provider,model=model,credential_id=provider)
            payload['endpoints'][role]['base_url']='https://api.deepseek.com' if provider=='deepseek' else 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        result=system.save_model_profile({'profile':payload,'activate':provider=='qwen'})
        if not result['success']:raise SystemExit('isolated profile failed')
    # Free production retrieval; no paid case is selected yet.
    from backend.services.agent_runtime.textbook_tool import freeze_textbook_scope,register_textbook_search_runtime
    from backend.tools.registry import ToolRegistry,ToolContext
    try:
        scope=freeze_textbook_scope('传感器原理及应用','物理');reg=ToolRegistry();register_textbook_search_runtime(reg,scope)
        question=budget.plan['cases'][0]['questions'][0]
        result=reg.runtime_tool('search_textbook').handler(ToolContext(book_name='传感器原理及应用',subject='物理'),{'query':question,'chapter':''})
        write(OUT/'RETRIEVAL-PREFLIGHT.json',{'success':result.success,'scope':scope,'result':result.to_dict(),'model_requests':len(budget.rows)})
    except Exception as exc:write(OUT/'RETRIEVAL-PREFLIGHT.json',{'success':False,'error_type':type(exc).__name__,'model_requests':len(budget.rows)})
    from fastapi import HTTPException
    @app_module.app.post('/__acceptance__/case/{case}')
    def select(case:str):
        if case=='S1' and not json.loads((OUT/'RETRIEVAL-PREFLIGHT.json').read_text()).get('success'):raise HTTPException(409,'real textbook retrieval unavailable')
        budget.select(case);return {'case':case}
    @app_module.app.get('/__acceptance__/status')
    def status():return {'case':budget.case,'receipts':budget.rows,'retrieval':json.loads((OUT/'RETRIEVAL-PREFLIGHT.json').read_text()).get('success')}
    app_module._start_warmup=lambda:None
    app_module._update_warmup(status='ready',stage='ready',message='isolated paid acceptance; production retrieval preflight recorded')
    app_module.app.router.routes=[r for r in app_module.app.router.routes if getattr(r,'name',None)!='static']
    app_module.app.mount('/',app_module.SPAStaticFiles(directory=str(ROOT/'frontend/dist'),html=True),name='paid-static')
    import uvicorn
    uvicorn.run(app_module.app,host='127.0.0.1',port=18041,log_level='warning')
if __name__=='__main__':main()
