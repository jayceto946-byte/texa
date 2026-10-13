"""Offline Electron replay with production API/SQL/SSE and Mock HTTP only."""
from pathlib import Path
import runpy,sys,json,os
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
fixture=runpy.run_path(str(ROOT/'scripts/qa-deepseek-production-server.py'),run_name='qa_replay')
os.environ['KAOYAN_TRUSTED_ORIGINS']='http://127.0.0.1:18042'
from llm import factory
from openai import OpenAI
import httpx
from tests.test_deepseek_production import completion
rows={r['case']:r for r in json.loads((ROOT/'docs/qa/evidence/deepseek-production/paid/FINAL-ACCEPTANCE.json').read_text())['cases']}
original=fixture['original_factory']
def controlled(resolved,temperature,**kwargs):
 def transport(request):
  body=json.loads(request.content);q='\n'.join(str(m.get('content','')) for m in body['messages'] if m['role']=='user')
  if '多项式除法' in q:
   row=rows['S5']
   calls=[{'id':t['operation_key'].split('native-1-')[1],'name':t['tool_id'],'args':t['args']} for t in row['tools']]
   chunks=completion(row['raw_final_public_model_answer'],reasoning='') if any(m['role']=='tool' for m in body['messages']) else completion('',calls)
  else:chunks=completion(rows['S6.turn2' if '第二轮只输出三行' in q else 'S6.turn1']['raw_final_public_model_answer'])
  return httpx.Response(200,headers={'content-type':'text/event-stream'},content=''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n')
 client=OpenAI(api_key='qa-fake-key',base_url='https://example.invalid/v1',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(transport)))
 return original(resolved,temperature,**kwargs).model_copy(update={'client':client.chat.completions})
factory.register_chat_transport('openai_compatible',controlled,capabilities=factory.transport_capabilities('openai_compatible'))
if __name__=='__main__':
 import uvicorn
 uvicorn.run(fixture['fixture']['main'].app,host='127.0.0.1',port=18042,log_level='warning')
