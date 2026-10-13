"""Disposable real API server for browser E2E; never load production config/data.
Startup/config metadata are synthetic. Optional workflow mode substitutes only model/parser inputs; Runtime, JobManager and stores stay real.
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
# Optional deterministic workflow inputs. Runtime, jobs and stores stay real.
if os.environ.get('TEXA_QA_WORKFLOWS') == '1':
    import time
    from backend.api import books
    original_import=books.import_textbook
    def fixture_import(pdf_path, book_name, **kwargs):
        if pdf_path.name.startswith('QA-CANCEL-') or pdf_path.name.startswith('QA-FAIL-'):
            for _ in range(100 if pdf_path.name.startswith('QA-CANCEL-') else 2):
                time.sleep(0.1)
                kwargs['on_progress']('qa_fixture','QA offline import checkpoint',10)
            raise RuntimeError('QA intentional offline import failure')
        return original_import(pdf_path,book_name,**kwargs)
    books.import_textbook=fixture_import
    from backend.api import notes
    from backend.services.session_notes.jobs import start_generation
    def fail_note(snapshot, **kwargs):
        if str(snapshot.get('conversation_id') or '').startswith('qa-readable-'):
            from backend.services.session_notes.generation import generate
            import json
            def call(payload, **options):
                sources=payload.get('messages') or [{'source_ref_id':entry['source_ref_id'],'content':'可导推出连续，连续未必可导。$|x|$ 是反例。'} for result in payload.get('extractions',[]) for entry in result['coverage']]
                blocks=[{'block_id':f'b{n}','type':'paragraph','role':'concept','data':{'markdown':source['content']},'source_ref_ids':[source['source_ref_id']],'evidence_ref_ids':[]} for n,source in enumerate(sources)]
                return json.dumps({'document':{'title':'可导与连续 · 对话整理','blocks':blocks},'coverage':[{'source_ref_id':source['source_ref_id'],'block_ids':[f'b{n}'],'disposition':'included'} for n,source in enumerate(sources)]},ensure_ascii=False)
            return generate(snapshot,call=call,**kwargs)
        raise RuntimeError('QA intentional offline generation failure')
    notes.start_generation=lambda service,receipt:start_generation(service,receipt,generator=fail_note)
    import graph.main_graph as qa_graph
    def fixture_stream(**kwargs):
        yield {'stage':'plan','intent':'qa','chapters':[],'fast_path':False}
        answer='离线夹具：可导推出连续，连续未必可导。'
        for chunk in answer:
            time.sleep(0.15)
            yield {'stage':'generate','chunk':chunk,'done':False}
        yield {'stage':'generate','chunk':'','done':True}
        yield {'stage':'done','state':{'final_output':answer},'enriched':False}
    qa_graph.run_graph_stream=fixture_stream
    from backend.api import exercises as qa_exercises
    answer_attempts={}
    original_answer=qa_exercises.generate_exercise_answer
    def fixture_answer(req, book_name='default'):
        record=qa_exercises._bank(book_name).get(req.id)
        if not record or not record.question_text.startswith('QA-ANSWER-'):
            return original_answer(req,book_name)
        time.sleep(2)
        answer_attempts[req.id]=answer_attempts.get(req.id,0)+1
        if 'FAIL' in record.question_text and answer_attempts[req.id]==1:
            return {'success':False,'message':'合成任务首次生成失败，可重试','reason':'qa_failure'}
        return {'success':True,'message':'合成答案草稿完成','data':{'answer':'$f\\prime(x)=3x^2$。\n\n'+('幂函数求导：降低一次幂并乘以原来的指数。\n\n'*24),'evidence_count':0}}
    qa_exercises.generate_exercise_answer=fixture_answer
    from backend.services.goals import execution as goal_execution
    from backend.services.agent_runtime.contracts import ModelCapabilities, FixedAction
    class FixtureGoalAdapter:
        def capabilities(self):
            return ModelCapabilities(tool_calling='supported')
        def next_action(self, transcript, candidates):
            time.sleep(3)
            return FixedAction('call', tool_id='get_recent_progress', args={}) if len(transcript)==1 else FixedAction('finish', answer='QA protocol')
    goal_execution.build_adapter=lambda registry:FixtureGoalAdapter()
    goal_execution.generate_answer=lambda state:'离线夹具：近期学习记录已读取，仅验证执行流程。'
    original_summary=goal_execution.summarize_goal
    def fixture_summary(text, **kwargs):
        import json
        return original_summary(text,generator=lambda messages:json.dumps({'title':text[:80],'objective':text,'success_criteria':[{'description':'读取近期学习记录'}]},ensure_ascii=False))
    goal_execution.summarize_goal=fixture_summary
if os.environ.get('TEXA_QA_COMPLEX') == '1':
    # Small, authored files exercise the real extraction pipeline without OCR/LLM.
    import zipfile
    import fitz
    from xml.sax.saxutils import escape
    assets=qa_root/'assets';assets.mkdir(exist_ok=True)
    for name, lines in {
        'questions.docx':['1. 求函数 f(x)=x^2 的导数。','2. 求函数 g(x)=x^3 的导数。'],
        'answers.docx':['1. 答案：2x','2. 答案：3x^2'],
    }.items():
        with zipfile.ZipFile(assets/name,'w') as archive:
            archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+''.join('<w:p><w:r><w:t>'+escape(line)+'</w:t></w:r></w:p>' for line in lines)+'</w:body></w:document>')
    pdf=fitz.open();page=pdf.new_page(width=600,height=360)
    page.insert_text((40,65),'1. Find the derivative of h(x)=x^4.',fontsize=18)
    page.insert_text((40,125),'2. Evaluate the integral of 2x from 0 to 1.',fontsize=18)
    pdf.save(assets/'questions.pdf');page.get_pixmap().save(assets/'question.png');pdf.close()
    if not (qa_root/'source-seeded.flag').exists():
        from backend.conversation_memory import append_message
        append_message('qa-source-inspector','user','请说明可导与连续的关系。',subject='数学',turn_id='qa-source-turn')
        append_message('qa-source-inspector','assistant','离线来源夹具：可导推出连续，连续未必可导。[1]',subject='数学',turn_id='qa-source-turn',sources=[{'id':'E1','book_name':'QA 合成教材','chapter':'第一章 函数与极限','section_path':['第一章 函数与极限','可导与连续'],'page_idx':12,'chunk_id':'qa-source-chunk'}])
        (qa_root/'source-seeded.flag').touch()
import uvicorn
if os.environ.get('TEXA_QA_NATIVE_MATH') == '1':
    # Model responses only are controlled. Math, Runtime, SSE and storage stay real.
    from backend.services.agent_runtime import chat_binding as native_binding
    from tests.test_native_math_loop import ScriptedMathModel, model_adapter, SUCCESS, call
    from langchain_core.messages import ToolMessage, HumanMessage
    class QAAdaptiveModel(ScriptedMathModel):
        def _response(self, messages):
            prompt = " ".join(m.content for m in messages if isinstance(m, HumanMessage))
            import re
            question = re.search(r"## 用户问题\s*\n([^\n]+)", prompt)
            prompt = question.group(1) if question else prompt
            if "计算 1/0" in prompt:
                self.responses = [call("symbolic_math", {"operation": "calculate", "expression": "1/0"}, "failure-1"),
                    {"content": "计算失败：除数不能为零，不能提供精确结果。"}]
            elif "计算 7" in prompt:
                self.responses = [{"content": "结果是 7。"}]
            elif "sin(x^x)" in prompt:
                self.responses = [call("symbolic_math", {"operation": "integrate", "expression": "sin(x^x)"}, "slow-1"),
                    {"content": "本次积分未能在预算内完成，暂不提供精确结果。"}]
            return super()._response(messages)
    def controlled_adapter(registry):
        return model_adapter(QAAdaptiveModel(responses=SUCCESS, delays=.7), registry)
    native_binding.build_adapter=controlled_adapter
if __name__ == '__main__':
    uvicorn.run(main.app,host='127.0.0.1',port=18041,log_level='warning')
