import sys, os, json, time
from pathlib import Path
from contextlib import asynccontextmanager
sys.path.insert(0,'/private/tmp/texa-checkpoint-acceptance')
os.environ['ENV_PATH']='/dev/null'
os.environ['KAOYAN_TRUSTED_ORIGINS']='http://127.0.0.1:18774'
os.environ['DATA_DIR']='/private/tmp/texa-final-electron/data'
os.environ['PROGRESS_PATH']='/private/tmp/texa-final-electron/data/progress'
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
uvicorn.run(main.app,host='127.0.0.1',port=18774,log_level='warning')
