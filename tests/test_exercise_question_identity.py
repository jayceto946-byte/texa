"""Question ownership regressions from the real 613 -> 436 review; no model IO."""
import json
from types import SimpleNamespace

from backend.services.exercise_file_analysis import file_book
from backend.services.exercise_review_coverage import candidate_coverage, restore_question_structure
from backend.services.import_review_session import ReviewSession
from backend.services.import_semantic_review import _structure, run_semantic_review
from ingestion.document_ir import CanonicalBook, DocumentBlock
from ingestion.document_structure import apply_structure_review
from llm.configuration import resolve_model_role
from memory.exercise_candidate_projection import project_units, source_registry
from memory.exercise_file_importer import ExtractedExerciseText
from memory.exercise_structure import exercise_units


def book(*rows):
    return CanonicalBook('fixture','fixture',list(rows),'fixture')


def block(bid,text,kind='paragraph',**attrs):
    return DocumentBlock(bid,kind,text,['fixture'],source_kind='mineru',attributes=attrs)


def proposals(source):
    normalized=file_book(ExtractedExerciseText('','zip',canonical_book=source),name=source.book_name)
    units=exercise_units(normalized,unrestricted=True)
    return project_units(units,source_registry(normalized,units,{b.block_id for b in normalized.blocks}),'fixture',{})


def model():
    return resolve_model_role('vision',dict(LLM_VISION_PROVIDER='deepseek',LLM_VISION_MODEL='deepseek-flash',LLM_VISION_API_KEY='fixture'))


def test_catalogue_identity_survives_annotation_guide_and_cross_question_owner():
    source=book(block('guide','今日复盘'),block('h1','#061 极限'),block('m1','原稿第1页 · 2024数二'),
                block('s1','(3) 求第一个函数的极限。'),block('h2','#062 导数'),
                block('s2','(5) 求第二个函数的导娄。'))
    decisions=[dict(block_id=bid,role='annotation',unit_role='context',unit_id=stem)
               for bid,stem in [('h1','s1'),('h2','s2')]]
    decisions += [dict(block_id='m1',role='front_matter',unit_role='context',unit_id='s1'),
                  dict(block_id='s1',unit_start=True,unit_role='question'),
                  dict(block_id='s2',unit_id='s1',unit_role='question')]
    reviewed=_structure(source,dict(blocks=decisions),{b.block_id:b.block_id for b in source.blocks},recover=False)
    p=proposals(reviewed)
    assert len(p)==2
    assert p[0]['question_text']=='(3) 求第一个函数的极限。'
    assert p[1]['question_text']=='(5) 求第二个函数的导娄。'
    assert p[0]['projection']['structure']['catalog_number']=='#061'
    assert p[1]['projection']['structure']['catalog_number']=='#062'
    assert reviewed.blocks[1].attributes['structure_role']=='body'


def test_equation_catalogues_are_independent_and_header_only_is_not_a_stem():
    source=book(block('h1','#015 极限'),block('q1','求第一个极限。'),
                block('h2',r'\# 0 1 6 \quad 0 / 0','formula'),block('q2','求第二个极限。'),
                block('h3','#017 极限',structure_unit_role='question',structure_unit_start=True))
    p=proposals(source)
    assert len(p)==3 and p[1]['projection']['structure']['catalog_number']=='#016'
    assert p[0]['question_text']=='求第一个极限。' and p[1]['question_text']=='求第二个极限。'
    assert p[2]['question_text']=='' and any(i['code']=='boundary_uncertain' for i in p[2]['issues'])


def test_invalid_metadata_and_invalid_json_do_not_discard_other_source_batches(tmp_path,monkeypatch):
    import backend.services.import_semantic_review as semantic
    source=book(block('q1','1. 求函数的导娄。'),block('q2','2. 求第二个函数的极限。'),block('q3','3. 求第三个函数的导娄。'))
    monkeypatch.setattr(semantic,'_batches',lambda blocks:[blocks[:1],blocks[1:2],blocks[2:]])
    calls=[]
    def complete(*args,**kwargs):
        calls.append(kwargs)
        data=json.loads(kwargs['messages'][1]['content'][0]['text'])
        if data['blocks'][0]['text'].startswith('2.'):
            value=[]
        else:
            bid=data['blocks'][0]['id']
            value=dict(edits=[dict(block_id=bid,find='导娄',replace='导数')],
                       metadata=[dict(block_id=bid,exam_year='2024')],blocks=[dict(block_id=17)])
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(value)))],usage={})
    reviewed,report=run_semantic_review(source,directory=tmp_path,resolved=model(),purpose='exercises',complete=complete)
    assert len(calls)==3 and '导数' in reviewed.blocks[0].text and '导数' in reviewed.blocks[2].text
    assert reviewed.blocks[1].text==source.blocks[1].text
    assert report['text_coverage']['completed_batches']==2 and len(report['failed_batches'])==1
    assert report['needs_retry'] and not reviewed.blocks[0].attributes.get('exercise_metadata')
    assert any(v.get('operation')=='metadata' for v in report['unresolved'] if isinstance(v,dict))


def test_old_paid_metadata_failure_is_revalidated_without_network(tmp_path):
    output=dict(edits=[dict(block_id='q',find='导娄',replace='导数')],metadata=[dict(block_id='q',exam_year='2024')])
    ledger=dict(identity=dict(version=8),calls=[dict(key='text8:0',status='failed',response_output=json.dumps(output),usage={'prompt_tokens':100,'completion_tokens':20},cost_cny=.01)])
    (tmp_path/'semantic_review.json').write_text(json.dumps(ledger))
    def forbidden(*args,**kwargs):raise AssertionError('must reuse the paid response')
    session=ReviewSession(model(),tmp_path,ledger['identity'],complete=forbidden)
    result=session.call('text8:0','system','{}')
    assert result['edits']==output['edits'] and result['metadata']==[] and result['unresolved']
    assert session.new_calls==0 and session.reused_calls==1
    saved=json.loads(session.path.read_text())['calls'][0]
    assert saved['original_status']=='failed' and saved['response_output']==json.dumps(output)


def test_unexplained_merge_restores_only_structure_and_keeps_corrected_text():
    source=book(block('q1','1. 求第一个函数的导娄。'),block('q2','2. 求第二个函数的极限。'),block('q3','3. 求第三个函数的积分。'))
    reviewed=apply_structure_review(source,[dict(block_id='q2',role='exercise',unit_role='question',unit_id='q1',unit_start=False,reason='合并相邻题干')],recover=False)
    reviewed.blocks[0].text=reviewed.blocks[0].text.replace('导娄','导数')
    report=candidate_coverage(source,reviewed)
    assert len(report['question_integrity']['mixed_candidates'])==1 and report['unaccounted']==2
    restored,receipt=restore_question_structure(source,reviewed)
    assert len(proposals(restored))==3 and receipt['coverage']['unaccounted']==0
    assert '导数' in restored.blocks[0].text
    assert restored.blocks[2].to_dict()==reviewed.blocks[2].to_dict()
    assert any(i['code']=='boundary_uncertain' for i in proposals(restored)[0]['issues'])


def test_same_block_lost_option_is_detected_and_restored_without_changing_count():
    source=book(block('raw','1. 求函数在原点的值。\n(A) 甲 (B) 乙 (C) 丙 (D) 丁'))
    split=source.blocks[0].text.index('(A)')
    reviewed=apply_structure_review(source,[dict(block_id='raw',segments=[
        dict(start=0,end=split,role='exercise',unit_start=True,unit_role='question'),
        dict(start=split,end=len(source.blocks[0].text),role='annotation')])],recover=False)
    assert len(proposals(reviewed))==1 and '(D)' not in proposals(reviewed)[0]['question_text']
    report=candidate_coverage(source,reviewed)
    assert report['before']==report['after']==1 and report['unaccounted']==1
    restored,receipt=restore_question_structure(source,reviewed)
    assert '(D) 丁' in proposals(restored)[0]['question_text'] and receipt['coverage']['unaccounted']==0


def test_explicit_same_block_split_remains_allowed():
    source=book(block('raw','1. 求第一个函数的极限。第二题 求第二个函数的导数。'))
    offset=source.blocks[0].text.index('第二题')
    reviewed=apply_structure_review(source,[dict(block_id='raw',segments=[
        dict(start=0,end=offset,role='exercise',unit_start=True,unit_role='question'),
        dict(start=offset,end=len(source.blocks[0].text),role='exercise',unit_start=True,unit_role='question')])],recover=False)
    assert len(proposals(reviewed))==2 and candidate_coverage(source,reviewed)['unaccounted']==0


def test_option_assigned_to_another_question_is_detected_even_with_two_candidates():
    source=book(block('q1','1. 求函数值。'),block('options','(A) 甲 (B) 乙 (C) 丙 (D) 丁'),
                block('q2','2. 求另一个函数的极限。'))
    reviewed=apply_structure_review(source,[dict(block_id='options',role='exercise',unit_role='question',unit_id='q2')],recover=False)
    report=candidate_coverage(source,reviewed)
    assert report['before']==report['after']==2 and report['unaccounted']==1
    restored,receipt=restore_question_structure(source,reviewed)
    p=proposals(restored)
    assert '(D) 丁' in p[0]['question_text'] and '(D)' not in p[1]['question_text']
    assert receipt['coverage']['unaccounted']==0


def test_source_upload_returns_all_questions_for_old_client_sending_500(tmp_path,monkeypatch):
    from backend.api import exercises
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    source=book(*[block(f'q{i}',f'{i+1}. 求给定函数的导数。') for i in range(613)])
    monkeypatch.setattr(exercises,'PROGRESS_PATH',tmp_path)
    monkeypatch.setattr(exercises,'_save_upload',lambda _:tmp_path/'fixture.zip')
    monkeypatch.setattr(exercises,'extract_exercise_text',lambda _:ExtractedExerciseText('source','zip',provider='fixture',canonical_book=source))
    monkeypatch.setattr(exercises,'_bank',lambda _:SimpleNamespace(list_all=lambda **kwargs:[]))
    app=FastAPI();app.include_router(exercises.router)
    response=TestClient(app).post('/exercises/upload-analyze?book_name=fixture',
        data=dict(candidate_contract_version=1,limit=500),files=dict(file=('fixture.zip',b'fixture'))).json()
    assert response['success'] and response['summary']['source_units']==613 and len(response['data'])==613
    from backend.services.exercise_candidate_review import ExerciseCandidateReviewService
    from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
    items=[dict(origin_id=c['id'],question_text=c['question_text'],answer=c['answer'],explanation=c['explanation'],
                candidate_context=dict(projection=c['projection'],review=None,import_confirmed=True)) for c in response['data']]
    receipts=ExerciseCandidateReviewService(file_provider=ExerciseFileAnalysisStore(tmp_path).load).prepare('fixture',items)
    assert len(receipts)==613
