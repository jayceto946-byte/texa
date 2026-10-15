"""Disposable Electron QA server: real Focus/Goal commands, fake neighbouring read models.
DATA_DIR must be a temporary directory. No model, vector store or production DB is opened.
"""
from pathlib import Path
import os
import sys
import time
import json
import asyncio
from urllib.request import Request as URLRequest, urlopen
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from backend.services.goals.store import GoalStore
from backend.services.goals.service import GoalService
from backend.services.goals.focus import FocusStore, FocusCheckpointWorker
from backend.api.focus import router as focus_router,store as focus_dependency
from backend.api.goals import router as goal_router,get_goal_service

root=Path(__file__).resolve().parents[3]
data_dir=Path(os.environ['DATA_DIR']).resolve()
if not str(data_dir).startswith('/private/tmp/texa-focus-qa'):
    raise RuntimeError('Use a disposable /private/tmp/texa-focus-qa directory')
data_dir.mkdir(parents=True,exist_ok=True)
goals=GoalStore(data_dir/'goals.db')
if not goals.list(learner_id='local_default'):
    goal=goals.create(learner_id='local_default',goal_id='goal-qa',title='学习偏导数',objective='掌握概念、计算及基础应用',scope={'subject':'数学/高数'},success_criteria=[{'id':'c1','description':'理解偏导数定义，能够说明几何意义'},{'id':'c2','description':'掌握基础计算方法'},{'id':'c3','description':'独立完成典型题'}])
    goals.update(goal['id'],expected_revision=1,changes={'status':'active'})
offset=[0.0]
focus=FocusStore(data_dir/'goals.db',clock=lambda:time.monotonic()+offset[0],wall_clock=lambda:time.time()+offset[0],allow_migration=True)
service=GoalService(goals)
# The QA server never creates Runtime or learning-event stores.
service._interrupt_runs=lambda _id:None
import backend.services.goals.focus as focus_module
focus_module.existing_focus_store=lambda _path:focus
if not focus.snapshot()['tasks']:
    for title in ['整理偏导数定义与几何意义','阅读教材指定章节并整理一个反例','独立完成已选例题并核对步骤','整理容易混淆的概念','回顾单变量求导规则','记录一道典型题的解法']:
        focus.command({'operation':'create','operation_id':'seed-'+title,'expected_revision':focus.snapshot()['revision'],'goal_id':'goal-qa','title':title})
    tasks=focus.snapshot()['tasks']
    for task in tasks[-2:]:focus.command({'operation':'complete','operation_id':'complete-'+task['id'],'expected_revision':focus.snapshot()['revision'],'task_id':task['id']})

focus_module._stores[str((data_dir/'goals.db').resolve())]=focus
worker=FocusCheckpointWorker()
app=FastAPI()

@app.on_event('startup')
def start_checkpoints():
    worker.start()

@app.on_event('shutdown')
def stop_checkpoints():
    worker.stop()
app.state.drop_next_reply=False

@app.middleware('http')
async def delay_committed_reply(request,call_next):
    drop=request.url.path=='/api/focus/commands' and app.state.drop_next_reply
    if drop:app.state.drop_next_reply=False
    response=await call_next(request)
    if drop:await asyncio.sleep(8)
    return response

@app.post('/qa/drop-next-reply')
def drop_reply():
    app.state.drop_next_reply=True
    return {'fixture':True}

app.dependency_overrides[focus_dependency]=lambda:focus
app.dependency_overrides[get_goal_service]=lambda:service

@app.get('/api/goals/{goal_id}/runtime')
def runtime(goal_id:str):
    return {'success':True,'data':None,'goal':goals.get(goal_id)}

app.include_router(focus_router,prefix='/api')
app.include_router(goal_router,prefix='/api')

@app.post('/qa/advance')
def advance(payload:dict):
    seconds=float(payload['seconds'])
    while seconds>0:
        step=min(30,seconds);offset[0]+=step;seconds-=step;focus.checkpoint()
    return focus.snapshot()

@app.get('/api/notes/filters')
def note_filters():
    return {'success':True,'data':{'chapter_refs':[],'books':[]}}

@app.get('/api/notes')
def note_list():
    return {'success':True,'data':{'items':[],'next_cursor':None}}

@app.get('/api/review/sessions')
def no_active_review():
    return {'success':True,'data':None}

@app.get('/qa/snapshot')
def inspect():
    return {'focus':focus.snapshot(),'history':focus.history(),'goals':goals.list(learner_id='local_default')}

@app.api_route('/{path:path}',methods=['GET','POST'])
async def fallback(path:str,request:Request):
    if path.startswith('api/') or path=='health':
        body=await request.body()
        req=URLRequest('http://127.0.0.1:18053'+request.scope['raw_path'].decode('ascii')+('?' + request.url.query if request.url.query else ''),data=body or None,method=request.method,headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=5) as response:
                raw=response.read();value=json.loads(raw)
                if path=='api/chat/conversations' and isinstance(value.get('data'),list):
                    value['data']={'items':[dict(item,management={'state':'active','pinned':False,'revision':0}) for item in value['data']],'has_more':False,'next_cursor':None}
                if path=='api/kg/learning-summary':
                    for item in value.get('data',{}).get('review_queue',[]):
                        for field in ('reasons','recent_questions','related_mistakes','textbook_snippets'):item.setdefault(field,[])
                if path.endswith('/management'):value={'success':True,'data':{'state':'active','pinned':False,'revision':0}}
                return JSONResponse(value)
        except Exception:
            return JSONResponse({'success':True,'data':[]})
    candidate=(root/'frontend/dist'/path).resolve()
    if not candidate.is_relative_to(root/'frontend/dist'):
        return Response(status_code=404)
    return FileResponse(candidate if candidate.is_file() else root/'frontend/dist/index.html')
