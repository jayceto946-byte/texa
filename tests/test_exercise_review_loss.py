"""Regression for sparse AI edits dropping untouched questions; no model calls."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore,file_book
from backend.services.exercise_review_coverage import candidate_coverage
from ingestion.document_ir import CanonicalBook,DocumentBlock
from ingestion.document_structure import apply_structure_review
from memory.exercise_candidate_projection import project_units
from memory.exercise_file_importer import ExtractedExerciseText
from memory.exercise_structure import exercise_units


def source(count=400):
    return CanonicalBook('fixture','fixture',[
        DocumentBlock(f'q{i}','paragraph',f'{i+1}. 求已知函数在原点的导数。',['第一章'],page_start=i//5+1,source_kind='mineru')
        for i in range(count)],'fixture')


def test_sparse_twenty_edits_preserve_four_hundred_questions_and_detect_old_loss():
    book=source()
    reviewed=apply_structure_review(book,[dict(block_id=f'q{i}',role='exercise') for i in range(20)],recover=False)
    report=candidate_coverage(book,reviewed)
    assert (report['before'],report['after'],report['unaccounted'])==(400,400,0)
    assert 'exercise_scope_policy' not in book.source_metadata
    reviewed.source_metadata['exercise_scope_policy']='regions'  # old whole-source filtering
    assert candidate_coverage(book,reviewed)['unaccounted']==380
    excluded=apply_structure_review(source(2),[dict(block_id='q0',role='overview',reason='来源是使用说明')],recover=False)
    accounted=candidate_coverage(source(2),excluded)
    assert (accounted['after'],accounted['removed'],accounted['unaccounted'])==(1,1,0)


def test_explicit_original_exercise_scope_stays_scoped():
    book=source(3)
    book.blocks[0].attributes['structure_role']='exercise'
    reviewed=apply_structure_review(book,[],recover=False)
    assert reviewed.source_metadata['exercise_scope_policy']=='regions'
    assert len(exercise_units(file_book(ExtractedExerciseText('','zip',canonical_book=reviewed),name='fixture'),unrestricted=True))==1


def test_catalogue_keeps_inherited_examples_subquestions_and_source_metadata(tmp_path):
    blocks=[DocumentBlock('guide','heading','刷题计划',['第一章'],source_kind='mineru'),
            DocumentBlock('plan','paragraph','1. 每天完成十道题并填写日期。',['第一章'],source_kind='mineru')]
    for i in (1,2):
        for suffix,text in [('header',f'#{i:03d} 函数性质'),('meta','原稿第 4 页 · 2008数一 · 建议12分钟'),
                            ('stem','设函数满足给定条件，求导。'),('sub','(1) 利用定义证明函数可导。'),
                            ('sub2','(2) 求导数在原点的值。')]:
            blocks.append(DocumentBlock(f'{i}-{suffix}','example',text,['第一章'],page_start=i,
                source_kind='mineru',attributes=dict(learning_unit_id='inherited-first-example')))
    book=CanonicalBook('fixture','fixture',blocks,'fixture')
    extracted,sid,_=ExerciseFileAnalysisStore(tmp_path).create(ExtractedExerciseText('','zip',canonical_book=book),book_name='fixture')
    assert len(extracted.units)==2
    proposals=project_units(extracted.units,extracted.source_blocks,extracted.canonical_hash,dict(source_mode='file'),source_id=sid)
    assert len(proposals)==2
    for p in proposals:
        assert '(1)' in p['question_text'] and '(2)' in p['question_text']
        assert '建议12分钟' not in p['question_text'] and '填写日期' not in p['question_text']
        assert p['projection']['structure']['exam_year']=='2008'
        assert p['projection']['structure']['exam_source']=='2008数一'


def test_local_rebuild_repairs_legacy_projection_and_preserves_paid_text(tmp_path):
    store=ExerciseFileAnalysisStore(tmp_path)
    book=source()
    _,original_id,_=store.create(ExtractedExerciseText('','zip',canonical_book=book),book_name='fixture')
    reviewed=apply_structure_review(book,[dict(block_id=f'q{i}',role='exercise') for i in range(20)],recover=False)
    reviewed.blocks[0].text='1. 已经付费校正的题干，求导数。'
    reviewed.source_metadata.update(exercise_scope_policy='regions',review_origin_source_id=original_id)
    legacy,legacy_id,_=store.create(ExtractedExerciseText('','zip',canonical_book=reviewed),book_name='fixture')
    assert len(legacy.units)==20
    next_id=store.rebuild(legacy_id,'fixture')
    recovered=store.load(next_id,'fixture')
    assert len(recovered.units)==400 and '已经付费校正' in recovered.units[0]['text']
    assert store.review_reference(next_id,'fixture')==original_id
    assert len(store.load(legacy_id,'fixture').units)==20  # immutable old snapshot
    with pytest.raises(ValueError):store.rebuild(legacy_id,'another-book')


def test_unexplained_collapse_blocks_job_adoption(tmp_path,monkeypatch):
    import backend.services.import_semantic_review as semantic
    import backend.services.structure_review_jobs as jobs_module
    book=source()
    reviewed=deepcopy(book)
    for b in reviewed.blocks[:20]:b.attributes['structure_role']='exercise'
    reviewed.source_metadata['exercise_scope_policy']='regions'
    report=dict(status='reviewed',unresolved=[],needs_retry=False)
    monkeypatch.setattr(semantic,'run_semantic_review',lambda *a,**k:(reviewed,report))
    monkeypatch.setattr(semantic,'create_review_session',lambda *a,**k:SimpleNamespace(report=lambda:{}))
    monkeypatch.setattr(jobs_module,'resolve_source',lambda *a,**k:(book,None,None))
    store=ExerciseFileAnalysisStore(tmp_path)
    _,sid,_=store.create(ExtractedExerciseText('','zip',canonical_book=book),book_name='fixture')
    completed=[]
    jobs=SimpleNamespace(raise_if_cancelled=lambda *a:None,update_job=lambda *a,**k:None,
        complete_job=lambda *a,**k:completed.append(k),fail_or_cancel_job=lambda *a,**k:pytest.fail(str(k)))
    job=dict(id='job',input=dict(target=dict(kind='file',reference=sid,book_name='fixture'),purpose='exercises',budget=dict(max_cost_cny=3)))
    jobs_module._run(job=job,book=book,assets=None,pdf=None,directory=tmp_path/'review',progress_root=tmp_path,books_root=tmp_path,jobs=jobs,resolved=None)
    result=completed[0]['result']
    assert result['adoption_blocked'] and result['adoption_required']
    assert result['report']['status']=='partial'
    assert result['report']['candidate_coverage']['unaccounted']==380
    assert len(store.load(sid,'fixture').units)==400


def test_candidate_reload_returns_all_units_and_rebuild_checks_owner(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import exercises
    monkeypatch.setattr(exercises,'PROGRESS_PATH',tmp_path)
    store=ExerciseFileAnalysisStore(tmp_path)
    _,sid,_=store.create(ExtractedExerciseText('','zip',canonical_book=source(501)),book_name='fixture')
    app=FastAPI();app.include_router(exercises.router)
    client=TestClient(app)
    loaded=client.get(f'/exercises/file-sources/{sid}/candidates',params=dict(book_name='fixture'))
    assert loaded.status_code==200 and len(loaded.json()['data']['candidates'])==501
    assert client.post(f'/exercises/file-sources/{sid}/rebuild',params=dict(book_name='another-book')).status_code==422


def test_empty_catalogue_stem_remains_visible_for_recovery(tmp_path):
    from memory.textbook_exercise_importer import analyze_learning_unit_candidates
    book=CanonicalBook('fixture','fixture',[DocumentBlock('h','paragraph','#001 函数性质',[],source_kind='mineru'),
        DocumentBlock('next','paragraph','#002 求导',[],source_kind='mineru'),
        DocumentBlock('body','paragraph','求函数在原点的导数。',[],source_kind='mineru')],'fixture')
    extracted,sid,_=ExerciseFileAnalysisStore(tmp_path).create(ExtractedExerciseText('','zip',canonical_book=book),book_name='fixture')
    candidates=analyze_learning_unit_candidates(extracted.units,book_name='fixture',subject='',limit=10,
        source_blocks=extracted.source_blocks,canonical_hash=extracted.canonical_hash,scope=dict(source_mode='file'),source_id=sid)
    assert len(candidates)==2 and candidates[0].question_text==''
    assert any(i['code']=='boundary_uncertain' for i in candidates[0].issues)
