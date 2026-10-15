import sys, os, json, time
from pathlib import Path
from contextlib import asynccontextmanager
sys.path.insert(0,'/private/tmp/texa-delta-verification')
os.environ['ENV_PATH']='/dev/null'
os.environ['KAOYAN_TRUSTED_ORIGINS']='http://127.0.0.1:18776'
os.environ['DATA_DIR']='/private/tmp/texa-delta-electron-v2/data'
os.environ['PROGRESS_PATH']='/private/tmp/texa-delta-electron-v2/data/progress'
from backend import main
from backend.services.goals import execution
from backend.services.goals.store import GoalStore,DEFAULT_GOAL_DB_PATH
from backend.services.goals.service import GoalService
from backend.services.agent_runtime.locator import runtime_store
from backend.services.agent_runtime.contracts import FixedAction,ModelCapabilities
from backend.tools.registry import ToolRegistry
from backend.services.agent_runtime.write_tools import register_receipt_backed_write_tools
from backend.services.agent_runtime.progress_tool import register_recent_progress_runtime
from memory.learning_events import get_learning_event_store
registry=ToolRegistry();register_receipt_backed_write_tools(registry);register_recent_progress_runtime(registry,get_learning_event_store())
execution.prepare_registry=lambda _: (registry,tuple(spec.runtime_metadata() for spec in registry._tools.values()),None)
class Adapter:
 def capabilities(self):return ModelCapabilities(tool_calling='supported')
 def next_action(self,transcript,candidates):
  question=transcript[0]['content']
  if question=='review stored work': return FixedAction('finish',answer='protocol')
  if '停止' in question:
   time.sleep(8)
   return FixedAction('finish',answer='protocol')
  if len(transcript)==1:
   return FixedAction('call',tool_id='save_mistake',args={'book_name':'验证教材','question_text':'验证题目','user_answer':'待核对'})
  return FixedAction('finish',answer='protocol')
execution.build_adapter=lambda _: Adapter()
execution.generate_answer=lambda _: '已整理本次学习记录，结果可回看。'
execution.summarize_goal=lambda text,**kw: {'title':text[:80],'objective':text,'success_criteria':[]}
service=GoalService(GoalStore(DEFAULT_GOAL_DB_PATH),get_learning_event_store())
if not service.store.list(learner_id='local_default'):
 for gid,title,scope in [('g_stop','Electron 停止与重启验证',{}),('g_write','Electron 审批验证',{'book_name':'验证教材'})]:
  goal=service.create(learner_id='local_default',goal_id=gid,title=title,objective=title,scope=scope)
  service.activate(gid,expected_revision=1)

from backend.services.agent_runtime.contracts import RunCommand,RuntimeConflict
from backend.services.agent_runtime.write_service import RuntimeWriteService
from backend.services.pending_actions import get_pending_action_store
from backend.tools.registry import ToolContext
from backend.services.goals.service import goal_contract
from graph.main_graph import build_initial_state
from backend.services.answer_verification import derive_required_outputs
store = runtime_store(create=True)
for kind in ['revoked', 'receipt']:
 gid = 'delta_' + kind
 if service.store.get(gid): continue
 goal=service.create(learner_id='local_default',goal_id=gid,title='Delta '+kind,objective='review stored work')
 goal=service.activate(gid,expected_revision=1)
 snap=store.create(RunCommand('delta-'+kind,'req-'+kind,'rtask_delta_'+kind,'','','review stored work','owner',required_outputs=derive_required_outputs('review stored work'),budget_model_calls=8,trigger_kind='goal',trigger_id=gid))
 rid=snap['run']['id']
 state=build_initial_state('review stored work',book_name='math',subject='',use_textbook_context=False,answer_mode='global_general')
 state['_goal_contract']=goal_contract(goal)
 store.configure_chat(rid,'owner',state=state,candidates=tuple(spec.runtime_metadata() for spec in registry._tools.values()),request_question='review stored work',book_name='math',subject='',delivery='goal')
 service.store.link(gid,task_id=snap['task']['id'],run_id=rid)
 pending=get_pending_action_store()
 writer=RuntimeWriteService(store,registry,pending)
 proposed=writer.propose(rid,'owner',tool_id='save_mistake',args={'book_name':'math','question_text':'delta verification'},operation_key='save',context=ToolContext(book_name='math'))
 call=proposed['tool_calls'][0]
 store.confirm_approval(call['id'],actor_id='test',args_hash=call['args_hash'],scope={'book_name':'math','subject':''})
 if kind=='revoked':
  service.pause(gid,expected_revision=2)
 else:
  resumed=store.resume(snap['task']['id'],expected_revision=proposed['task_revision'],request_key='admit-'+kind,request_id='admit-'+kind,owner_token='admitter',turn_id='')
  store.start_approved_tool(resumed['run']['id'],'admitter',call['id'])
  service.update(gid,expected_revision=2,changes={'objective':'changed goal contract'})
  pending.confirm(call['id'])

@asynccontextmanager
async def lifespan(app):
 runtime_store(create=True).recover_unfinished()
 yield
 execution.stop_goal_runs()
main.app.router.lifespan_context=lifespan
main._warmup_state.update(status='ready',stage='ready',message='隔离验证环境',error='',failure=None)
# Skip local embedding/health scans in this harness, retaining real goal/chat/action routes.
from backend.api import system
system._check_embedding_runtime=lambda: {'status':'healthy','message':'测试环境'}
import uvicorn
uvicorn.run(main.app,host='127.0.0.1',port=18776,log_level='warning')
