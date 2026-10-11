"""Disposable real API server for browser E2E; never load production config/data.
Only the main app startup warmup is stubbed; business APIs/store behavior is real.
"""
from pathlib import Path
import os,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
qa_root=Path(os.environ['TEXA_QA_DATA']).resolve()
if not str(qa_root).startswith('/private/tmp/') and not str(qa_root).startswith('/tmp/'):
    raise SystemExit('QA root must be disposable /tmp directory')
qa_root.mkdir(parents=True,exist_ok=True);empty=qa_root/'empty.env';empty.touch()
for key in list(os.environ):
    if any(part in key.upper() for part in ('API_KEY','API_SECRET','CREDENTIAL','ACCESS_TOKEN')):os.environ[key]=''
os.environ.update(ENV_PATH=str(empty),DATA_DIR=str(qa_root/'data'),PROGRESS_PATH=str(qa_root/'progress'),BOOKS_PATH=str(qa_root/'books'),VECTOR_DB_PATH=str(qa_root/'vector'),MINERU_OUTPUT_PATH=str(qa_root/'mineru'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',KAOYAN_TRUSTED_ORIGINS='http://127.0.0.1:18041')
import backend.main as main
from fastapi.staticfiles import StaticFiles
# Remove existing build mount only in this fixture process. Serve audited build.
main.app.router.routes=[r for r in main.app.router.routes if getattr(r,'name',None)!='static']
main._start_warmup=lambda:None
main._update_warmup(status="ready",stage="ready",message="QA synthetic warmup; real assets not loaded")
main.app.mount('/',main.SPAStaticFiles(directory=os.environ['TEXA_QA_DIST'],html=True),name='qa-static')
from backend.api import system
# Stub configuration metadata only; credentials never reach a provider.
model={'roles':{'reasoning':{'provider':'openai_compatible','model':'qa-offline','credential_id':'qa','endpoint_id':'qa'},'vision':{'provider':'openai_compatible','model':'qa-offline','credential_id':'qa','endpoint_id':'qa'}},'credentials':{'reasoning':{'configured':True,'required':False},'vision':{'configured':True,'required':False}},'endpoints':{'reasoning':{'base_url':'http://127.0.0.1:9','is_default':True},'vision':{'base_url':'http://127.0.0.1:9','is_default':True}},'providers':[],'models':[],'profiles':[],'multimodal_mode':'native','profile_name':'QA','active_profile_id':'qa'}
system.profiles_payload=lambda:model
# All actual network calls forbidden except local browser/backend socket operations.
import socket
_connect=socket.socket.connect
def local_connect(sock,address):
    if isinstance(address,tuple) and address[0] not in {'127.0.0.1','localhost','::1'}:raise RuntimeError('QA forbids external connections')
    return _connect(sock,address)
socket.socket.connect=local_connect
import uvicorn
uvicorn.run(main.app,host='127.0.0.1',port=18041,log_level='warning')
