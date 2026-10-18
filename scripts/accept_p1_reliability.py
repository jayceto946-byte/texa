"""Finite authorized DeepSeek acceptance. Credentials and private protocol stay in RAM.

Synthetic regression helpers are reused without their Qwen setup/meter. Production
learning databases are never opened. Textbook artifacts are read separately.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(os.environ.get('TEXA_ACCEPTANCE_SOURCE', str(ROOT)))
sys.path.insert(0, str(SOURCE_ROOT))
sys.path.insert(0, str(SOURCE_ROOT / 'scripts'))
import accept_p1_abc_teaching as old
QA = Path('/private/tmp/texa-p1-reliability')
OUT = ROOT / 'docs/qa/p1-reliability'
DESKTOP = Path.home() / 'Library/Application Support/kaoyan-assistant-desktop'

def setup():
    QA.mkdir(parents=True, exist_ok=True)
    os.environ.update(ENV_PATH=str(QA/'empty.env'), DATA_DIR=str(QA/'data'),
        PROGRESS_PATH=str(QA/'progress'), BOOKS_PATH=str(QA/'books'),
        VECTOR_DB_PATH=str(QA/'vector'), MINERU_OUTPUT_PATH=str(QA/'mineru'),
        HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TEXA_TEACHING_PROMPT_MODE='refined')
    from dotenv import dotenv_values
    from llm.configuration import resolve_model_role, model_settings_env_values, credential_env_name
    profiles=json.loads((DESKTOP/'data/model_profiles.json').read_text())
    profile=next(p for p in profiles if p['name']=='deepseek_v4.1_flash_test')
    env={k:v for k,v in dotenv_values(DESKTOP/'.env').items() if v is not None}
    public_settings=model_settings_env_values({**profile,'credentials':{}})
    resolved={**env, **public_settings}
    os.environ.update(public_settings)  # Process-only role/multimodal settings; no credentials or profile writes.
    role=resolve_model_role('reasoning', resolved)
    from urllib.parse import urlparse
    assert role.provider.provider_id=='deepseek' and role.model=='deepseek-flash'
    assert urlparse(role.endpoint).hostname=='api.deepseek.com'
    assert role.api_key and role.api_key==env[credential_env_name('deepseek')]
    import config
    config.get_model_role_config=lambda which='reasoning':resolve_model_role(which,resolved)
    old.QA=QA; old.OUT=OUT
    return role

def meter(role, case):
    import httpx
    from langchain_core.callbacks import BaseCallbackHandler
    from llm.factory import build_chat_model
    path=OUT/'usage.json'
    ledger=old.load(path, {'model':role.model,'provider':'deepseek','request_limit':30,'requests':[]})
    lock=threading.RLock(); current={}
    def guard(request):
        if request.url.host in {'localhost','127.0.0.1','::1'}:return
        assert request.url.host=='api.deepseek.com' and request.url.path.endswith('/chat/completions')
        data=json.loads(request.content)
        assert data['model']==role.model and data.get('max_tokens')==8192 and data.get('temperature')==1
        assert data.get('thinking')=={'type':'enabled'} and data.get('reasoning_effort')=='high'
        assert not any(isinstance(m.get('content'),list) for m in data['messages'])
        with lock:
            if len(ledger['requests'])>=30:raise RuntimeError('acceptance_request_limit')
            item={'index':len(ledger['requests'])+1,'case':case,'temperature':1,'status':'requested',
                'input_bytes':len(request.content),'public_input_sha256':hashlib.sha256(json.dumps([
                    {k:v for k,v in m.items() if k!='reasoning_content'} for m in data['messages']],
                    ensure_ascii=False,sort_keys=True).encode()).hexdigest()}
            ledger['requests'].append(item); current[threading.get_ident()]=(item,time.monotonic())
            old.write(path,ledger)
    original=httpx.Client.__init__
    def init(self,*a,**kw):
        hooks=dict(kw.pop('event_hooks',{}) or {});hooks['request']=[*hooks.get('request',[]),guard]
        kw.update(event_hooks=hooks,trust_env=False);return original(self,*a,**kw)
    httpx.Client.__init__=init
    class Receipt(BaseCallbackHandler):
        def on_llm_end(self,response,**kw):
            with lock:
                pair=current.get(threading.get_ident())
                if pair:
                    item,start=pair; m=response.generations[0][0].message
                    item.update(status='returned',usage=m.usage_metadata or {},
                        request_ms=round((time.monotonic()-start)*1000,2),finish_reason=m.response_metadata.get('finish_reason'))
                    from utils.thinking_filter import strip_thinking
                    public=QA/'public-responses'/f"{case}-{item['index']}.txt"
                    public.parent.mkdir(parents=True,exist_ok=True)
                    public.write_text(strip_thinking(m.content) if isinstance(m.content,str) else '')
                    item['response_model']=m.response_metadata.get('model_name')
                    old.write(path,ledger)
        def on_llm_error(self,error,**kw):
            with lock:
                pair=current.get(threading.get_ident())
                if pair:pair[0].update(status='error',error_type=type(error).__name__);old.write(path,ledger)
    def factory(resolved,temperature=0.1,**kw):
        kw.update(max_retries=0,stream_usage=True,request_timeout=180)
        return build_chat_model(resolved,1,**kw).model_copy(update={'callbacks':[Receipt()],'max_tokens':8192})
    import config
    config.get_llm=lambda temperature=0.1,**kw:factory(role,temperature,**kw)
    return factory

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);p.add_argument('--phase',choices=['before','after'],required=True)
    args=p.parse_args();role=setup();case='t1-'+args.phase+'-'+args.case
    assert not (OUT/(case+'.json')).exists() and not (OUT/(case+'.json.gz')).exists(), 'explicit unique run required'
    book,anchors=old.corpus();factory=meter(role,case);start=time.monotonic()
    try:
        kind,key,question=old.CASES[args.case]
        if kind=='runtime':result=old.native(case,question,key,anchors,role,factory)
        elif kind in {'exercise','candidate'}:result=old.exercise(case,book,anchors,question,candidate=kind=='candidate')
        elif kind=='mistake':result=old.mistake(case,question,role,factory)
        else:raise ValueError('unsupported case')
    except Exception as exc:
        import traceback
        result={'execution_status':'FAIL','error_type':type(exc).__name__,
            'frames':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)]}
    result.update(case=case,total_ms=round((time.monotonic()-start)*1000,2))
    old.write(QA/(case+'.json'),result)
    # Full synthetic public responses are safe; textbook runs use summary-only delivery.
    old.write(OUT/(case+'.json'),result)
    print(json.dumps({'case':case,'ms':result['total_ms'],'run_status':result.get('run_status'),
        'metadata_status':result.get('metadata_status'),'error_type':result.get('error_type')},ensure_ascii=False))
if __name__=='__main__':main()
