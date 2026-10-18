"""Finite real textbook tests; explicit disposable stores, read-only source files.

No production learning DB is opened or copied, no Chroma client is created.
Production BM25, Canonical expansion, EvidencePack, Runtime and domain services
are used. Full hybrid retrieval and image perception are not claimed.
"""
from __future__ import annotations
import argparse, asyncio, hashlib, json, time
from pathlib import Path
import accept_p1_reliability as harness
from accept_p1_reliability import QA, OUT, DESKTOP, old
BOOK='传感器原理及应用'
QUESTION_BLOCK='d09eb1bf265fc6309d79'
STEP='第一步：2%=2。\n第二步：最长=5*(1+2)=15m，最短=5*(1-2)=-5m。'
FINAL='最长15m，最短-5m。'
CASES={
 'A':('native','传感器的定义','依据教材1.1.2解释传感器的定义，说明输出是否必须是电量、输入输出关系的要求。无需描述插图。'),
 'B':('native','灵敏度 表1.1 铂电阻','依据教材例1.3及表1.1计算铂电阻温度计的灵敏度，保留单位和线性条件。可用工具核对关键数值；明确区分计算与独立验证。不描述未读取的图。'),
 'C':('native','最小二乘法拟合过程','依据教材1.3.1连续讲解最小二乘直线拟合：残差、平方和、两个偏导、k与b及适用条件。只使用实际可见教材；原式疑似错误或上下文缺失时指出，不猜图形。'),
 'D':('exercise','容差',''),
 'E1':('mistake','容差',STEP),
 'E2':('mistake','容差',FINAL),
}

def sources():
    from ingestion.document_ir import load_canonical_book,canonical_book_fingerprint
    from backend.services.figure_learning import FigureLearningService
    from ingestion import index_pipeline
    vector=DESKTOP/'data/vector_db';progress=DESKTOP/'data/progress'
    # This variable is used only by manifest_path/read here; never invoke any
    # vector/activation/write function against it.
    index_pipeline.VECTOR_DB_PATH=vector
    manifest=index_pipeline.load_index_manifest(BOOK)
    book=load_canonical_book(BOOK,progress_root=progress)
    assert canonical_book_fingerprint(book)==manifest['canonical_hash']
    version=next(v for v in manifest['versions'] if v['index_version']==manifest['index_version'])
    lexical_path=vector/version['lexical_path'];rows=json.loads(lexical_path.read_text())
    assert all(r['canonical_hash']==manifest['canonical_hash'] and r['index_version']==manifest['index_version'] for r in rows)
    service=FigureLearningService(progress_root=progress)
    files=[progress/BOOK/'canonical_document.jsonl',vector/'_index_manifests'/f'{BOOK}.json',lexical_path,
        DESKTOP/'mineru_output'/BOOK/'hybrid_auto_external/CGQ/structured_content.json']
    identity={'book_name':BOOK,'edition':'第2版','author':'彭杰纲','publisher':'电子工业出版社','year':2017,
        'isbn':'978-7-121-30967-0','canonical_hash':manifest['canonical_hash'],'index_version':manifest['index_version'],
        'block_count':len(book.blocks),'lexical_rows':len(rows),'chapter_count':manifest['chapter_collection_count'],
        'raw_resource_present':files[-1].is_file(),'files':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
        'kg':'absent; unknown/unclassified required','retrieval':'production BM25 on active lexical snapshot; no vector client',
        'image_input':'none; visual acceptance not claimed'}
    return book,rows,manifest,service,identity

def retrieve_for(rows,service,query):
    from ingestion.lexical_index import search_rows
    from graph.textbook_context import expand_textbook_context
    hits=search_rows(rows,query,k=2,chapters=['第1章 绪论'])
    items=[{**r,'text':r['content']} for r in hits[:1]]
    return expand_textbook_context(items,intent='teach',query=query,service=service)

def trace_pack(items):
    from graph.evidence_pack import build_evidence_pack
    pack=build_evidence_pack(items,intent='teach')
    trace={'anchors':[{'chunk_id':i['chunk_id'],'source_block_ids':i.get('source_block_ids'),
        'pages':[i.get('page_start'),i.get('page_end')],'learning_unit':i.get('learning_unit')} for i in items],
        'visible':[{'id':i.get('id'),'chunk_id':i.get('chunk_id'),'source_block_ids':i.get('source_block_ids'),
            'visible_chars':len(i.get('text','')),'visible_sha256':hashlib.sha256(i.get('text','').encode()).hexdigest(),
            'learning_unit':i.get('learning_unit')} for i in pack['verification_items']],
        'formula_tags':[tag for tag in ['1.5','1.6','1.7','1.8','1.9','1.10','1.11'] if tag in str(pack['verification_items'])],
        'table_1_1_visible':'307' in str(pack['verification_items']) and '328' in str(pack['verification_items'])}
    return pack,trace

def native(case,question,items,manifest,role,factory):
    from backend.services.agent_runtime.chat_binding import build_math_registry,stream_run
    from backend.services.agent_runtime.textbook_tool import register_textbook_search_runtime
    from backend.services.agent_runtime.store import RuntimeStore
    from backend.services.agent_runtime.contracts import RunCommand
    from llm.agent_adapter import NativeToolAdapter
    registry=build_math_registry();adapter=NativeToolAdapter(role,registry,model_factory=factory);adapter.allow_native_attempt=True
    refs=tuple({k:registry.runtime_tool(name).runtime_metadata()[k] for k in ('id','version','schema_hash')} for name in ('symbolic_math','verify_math_result'))
    scope={'id':'sensor-scope','book_name':BOOK,'subject':'传感器','resources':[{'book_name':BOOK,'is_primary':True,'is_selected':True}],
        'index_versions':{BOOK:manifest['index_version']}}
    register_textbook_search_runtime(registry,scope,versions=lambda _:manifest['index_version'],
        retrieve=lambda *a,**kw:{'evidence_items':items,'evidence_support':{'status':'supported'},'retrieval_status':'real_active_lexical_bm25_readonly'})
    meta=registry.runtime_tool('search_textbook').runtime_metadata()
    state={'user_input':question,'book_name':BOOK,'subject':'传感器','intent':'teach','use_textbook_context':True,
        'answer_mode':'textbook_grounded','native_loop':True,'_runtime_textbook_scope':scope,
        '_native_preparation_ref':{k:meta[k] for k in ('id','version','schema_hash')},
        '_native_limits':{'model_timeout_seconds':180,'run_timeout_seconds':600}}
    store=RuntimeStore(QA/'progress/runtime.db');owner='owner-'+case
    run=store.create(RunCommand(case,case,'task-'+case,'session-'+case,'turn-'+case,question,owner,
        budget_calls=4,budget_model_calls=5,required_outputs=[{'id':'answer','kind':'content'}]))['run']['id']
    store.configure_chat(run,owner,state=state,candidates=refs,request_question=question,book_name=BOOK,subject='传感器')
    events=[]
    async def consume():
        response=stream_run(store,run,owner,registry,adapter)
        async for chunk in response.body_iterator:events.append(json.loads(chunk[6:]))
        await response.aclose()
    asyncio.run(consume());snap=store.snapshot(run)
    return {'answer':(snap['run']['output'] or {}).get('answer',''),'task_status':snap['task']['status'],
        'run_status':snap['run']['status'],'error_code':snap['run']['error_code'],'tool_calls':snap['tool_calls'],
        'verification':snap['task'].get('verification'),'events':events}

def exercise(case,question,items):
    from backend.services import exercise_answers
    from backend.services.exercise_knowledge import save_answer_with_knowledge
    from memory.exercise_bank import ExerciseBank,ExerciseRecord
    from graph.evidence_pack import build_evidence_pack
    bank=ExerciseBank(QA/'sensor-exercises.db')
    record=ExerciseRecord(id=case,question_text=question,subject='传感器',chapter='第1章 绪论')
    bank.add(record);record=bank.get(record.id)
    evidence=build_evidence_pack(items,intent='application')['verification_items']
    exercise_answers.retrieve_node=lambda state:{'evidence_items':evidence,'evidence_support':{'status':'supported'},'retrieval_status':'real_active_lexical_bm25_readonly'}
    response=exercise_answers.generate_answer(record,book_name=BOOK)
    if not response.get('success'):return {'generation':response}
    job={'status':'completed','exercise_id':case,'book_name':BOOK,'result':response['data']}
    saved,status=save_answer_with_knowledge(bank,record,answer=response['data']['answer'],explanation='',book_name=BOOK,job=job)
    return {'generation':response,'save_status':status,'persisted':saved.to_dict(),'database':str(QA/'sensor-exercises.db')}

def mistake(case,question,answer,role,factory):
    from memory.mistake_book import MistakeBook,MistakeRecord
    from memory.mistake_lifecycle import MistakeLifecycleStore
    from backend.services.exercise_knowledge import explain_mistake
    from knowledge.exercise_structure import build_catalog
    mb=MistakeBook(QA/'sensor-mistakes.db')
    record=MistakeRecord(id=case,question_text=question,correct_answer='最长5.1m，最短4.9m。',subject='传感器',chapter='第1章 绪论')
    mb.add(record);life=MistakeLifecycleStore(mb.store)
    aid=life.append_occurrence_once(case,'synthetic-'+case,answer=answer,source_ref={'type':'exercise_attempt','operation_id':case})
    before_sm2=mb.get(case).sm2.copy()
    response=explain_mistake(mb,case,book_name=BOOK,invoke=lambda prompt:factory(role,1).invoke(prompt).content)
    attempts=life.list_attempts(case);result={'metadata_status':response['metadata_status'],'diagnosis_errors':response['diagnosis_errors'],
        'explanation':response['explanation'],'attempts':attempts,'weak_before_confirm':mb.get_weak_points(),
        'sm2_unchanged':mb.get(case).sm2==before_sm2,'record':response['record'].to_dict(),'database':str(QA/'sensor-mistakes.db')}
    if '-E1' in case and attempts[0].get('diagnosis',{}).get('errors'):
        # Explicit simulated human confirmation in disposable data only.
        r=mb.get(case);life.set_attempt_diagnosis(case,aid,expected_revision=r.revision,operation_id='confirm-'+case,
            catalog=build_catalog(r,book_name=BOOK),confirm=True,expected_diagnosis_digest=attempts[0]['diagnosis_digest'])
        r=mb.get(case);life.change_record(case,expected_revision=r.revision,operation_id='edit-'+case,changes={'question_text':question.replace('5','6',1)})
        result['after_edit']={'weak_points':mb.get_weak_points(),'attempts':life.list_attempts(case),'record':mb.get(case).to_dict()}
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=CASES);p.add_argument('--run-id',default='');p.add_argument('--prepare',action='store_true');args=p.parse_args()
    role=harness.setup()
    # Prove write isolation before importing domain storage or opening sources.
    import config
    assert Path(config.PROGRESS_PATH).resolve()==(QA/'progress').resolve()
    assert Path(config.DATA_DIR).resolve().is_relative_to(QA.resolve())
    book,rows,manifest,service,identity=sources();old.write(OUT/'sensor-identity.json',identity)
    if args.prepare:
        for key,(_,query,_) in CASES.items():
            _,trace=trace_pack(retrieve_for(rows,service,query));old.write(OUT/('sensor-preflight-'+key+'.json'),trace)
            print(key,[(i['chunk_id'],i['visible_chars'],(i.get('learning_unit') or {}).get('status')) for i in trace['visible']])
        return
    assert args.case;case='t1-sensor-'+args.case+('-'+args.run_id if args.run_id else '');assert not (OUT/(case+'.json')).exists()
    kind,query,question=CASES[args.case];items=retrieve_for(rows,service,query);pack,trace=trace_pack(items)
    question_text=next(b.text for b in book.blocks if b.block_id==QUESTION_BLOCK)
    factory=harness.meter(role,case);start=time.monotonic()
    if kind=='native':result=native(case,question,items,manifest,role,factory)
    elif kind=='exercise':result=exercise(case,question_text,items)
    else:result=mistake(case,question_text,question,role,factory)
    result.update(case=case,total_ms=round((time.monotonic()-start)*1000,2),source_question_block=QUESTION_BLOCK if kind!='native' else None,trace=trace)
    old.write(QA/(case+'.json'),result)
    if kind=='native':
        summary={k:v for k,v in result.items() if k not in {'answer','events','tool_calls'}}
        summary['answer_sha256']=hashlib.sha256(result['answer'].encode()).hexdigest()
        summary['tools']=[{'tool_id':c['tool_id'],'status':c['status'],'args':c['args'] if c['tool_id']!='search_textbook' else {},
            'math_result':c['result'] if c['tool_id']!='search_textbook' else None} for c in result['tool_calls']]
    else:
        summary={'case':case,'total_ms':result['total_ms'],'trace':trace,'source_question_block':QUESTION_BLOCK,
            'metadata_status':result.get('metadata_status') or result.get('generation',{}).get('data',{}).get('metadata_status'),
            'diagnosis_errors':result.get('diagnosis_errors'),'weak_before_confirm':result.get('weak_before_confirm'),
            'sm2_unchanged':result.get('sm2_unchanged'),'full_result_sha256':hashlib.sha256(json.dumps(result,default=str,ensure_ascii=False).encode()).hexdigest()}
        if kind=='exercise':summary['classification']=result.get('persisted',{}).get('knowledge_structure');summary['save_status']=result.get('save_status')
        else:
            summary['diagnosis']=[a.get('diagnosis') for a in result['attempts']]
            summary['edit_invalidated']=not result.get('after_edit',{}).get('weak_points') if 'after_edit' in result else None
    old.write(OUT/(case+'.json'),summary)
    assert identity['files']==sources()[-1]['files'],'production source changed during test'
    print(json.dumps({'case':case,'ms':result['total_ms'],'metadata_status':summary.get('metadata_status'),'run_status':result.get('run_status')},ensure_ascii=False))
if __name__=='__main__':main()
