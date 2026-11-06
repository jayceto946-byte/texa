"""Persisted OCR metadata filters and original-PDF association, without models."""
from copy import deepcopy

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import exercises, structure_reviews
from backend.schemas import ExerciseListRequest, ExercisePracticeSessionCreateRequest
from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
from backend.services.structure_review_jobs import resolve_source, review_directory
from ingestion.document_ir import CanonicalBook, DocumentBlock
from llm.configuration import resolve_model_role
from memory.exercise_bank import ExerciseBank, ExerciseRecord
from memory.exercise_file_importer import ExtractedExerciseText


def test_existing_metadata_filters_apply_before_limit_and_practice_uses_same_scope(tmp_path,monkeypatch):
    bank=ExerciseBank(tmp_path/'bank.db')
    for name,source,focus in [('old','2024数二','导数定义'),('recent','2024数二','函数极限'),('other','2023数一','导数定义')]:
        bank.add(ExerciseRecord(question_text=name,subject='数学/高等数学',chapter='第一章',tags=['原有标签'],
            extra_fields=dict(source_structure=dict(exam_source=source,authored_focus=focus))))
    bank.add(ExerciseRecord(question_text='legacy',subject='数学/高等数学',chapter='第一章'))
    monkeypatch.setattr(exercises,'_bank',lambda _:bank)
    result=exercises.get_exercise_overview(ExerciseListRequest(subject='数学',exam_source='2024数二',authored_focus='导数定义',limit=1))
    assert [r.question_text for r in result['data']['records']]==['old']
    assert result['data']['source_facets']==dict(exam_source={'2024数二':2,'2023数一':1},authored_focus={'导数定义':2,'函数极限':1})
    started=exercises.create_practice_session(ExercisePracticeSessionCreateRequest(subject='数学',exam_source='2024数二',authored_focus='导数定义'))
    assert started['success']
    session=bank.get_active_practice_session()
    assert [bank.get(rid).question_text for rid in session.exercise_ids]==['old']
    assert session.filters['exam_source']=='2024数二' and session.filters['authored_focus']=='导数定义'
    assert bank.get(session.exercise_ids[0]).tags==['原有标签']


def pdf_bytes(pages):
    with fitz.open() as document:
        for i in range(pages):document.new_page().insert_text((40,40),f'Original page {i+1}')
        return document.tobytes()


def test_pdf_association_from_reviewed_candidate_is_used_by_plan_and_original_pages(tmp_path,monkeypatch):
    source=CanonicalBook('fixture','fixture',[
        DocumentBlock('q1','paragraph','1. 求第一个函数的导数。',['fixture'],page_start=1,page_end=1),
        DocumentBlock('q2','paragraph','2. 求第二个函数的极限。',['fixture'],page_start=2,page_end=2)],'fixture',source_page_count=2)
    store=ExerciseFileAnalysisStore(tmp_path)
    _,origin,_=store.create(ExtractedExerciseText('source','zip',canonical_book=source),book_name='fixture')
    reviewed=deepcopy(source);reviewed.source_metadata['review_origin_source_id']=origin
    _,current,_=store.create(ExtractedExerciseText('source','zip',canonical_book=reviewed),book_name='fixture')
    monkeypatch.setattr(structure_reviews,'PROGRESS_PATH',tmp_path)
    monkeypatch.setattr(structure_reviews,'BOOKS_PATH',tmp_path/'books')
    monkeypatch.setattr(structure_reviews,'get_job_manager',lambda:None)
    import config
    monkeypatch.setattr(config,'get_model_role_config',lambda _:resolve_model_role('vision',dict(LLM_VISION_PROVIDER='deepseek',LLM_VISION_MODEL='deepseek-flash',LLM_VISION_API_KEY='fixture')))
    app=FastAPI();app.include_router(structure_reviews.router,prefix='/api');client=TestClient(app)
    target=dict(kind='file',reference=current,book_name='fixture')
    result=client.post('/api/structure-reviews/source-pdf',data=target,files=dict(file=('原始教材.pdf',pdf_bytes(2),'application/pdf')))
    assert result.status_code==200,result.json()
    assert result.json()['data']==dict(filename='原始教材.pdf',pages=2,reference=origin)
    plan=client.post('/api/structure-reviews/plan',json={**target,'purpose':'exercises'}).json()['data']
    assert plan['has_original_pages'] and plan['source_pdf']==dict(filename='原始教材.pdf',pages=2)
    _,_,path=resolve_source(target,progress_root=tmp_path,books_root=tmp_path/'books',jobs=None)
    assert path==review_directory(tmp_path,'file',origin)/'source.pdf'
    image=client.get('/api/structure-reviews/source-page',params={**target,'page':2})
    assert image.status_code==200 and image.headers['content-type']=='image/png'
    failed=client.post('/api/structure-reviews/source-pdf',data=target,files=dict(file=('其他版本.pdf',pdf_bytes(3),'application/pdf')))
    assert failed.status_code==422 and 'PDF共3页' in failed.json()['detail'] and '来源共2页' in failed.json()['detail']
    assert client.post('/api/structure-reviews/plan',json={**target,'purpose':'exercises'}).json()['data']['source_pdf']['filename']=='原始教材.pdf'
