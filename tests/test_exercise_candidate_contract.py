from copy import deepcopy
import json
from pathlib import Path

import pytest
from ingestion.document_ir import CanonicalBook, DocumentBlock, canonical_book_fingerprint
from ingestion.document_workflows import learning_units
from memory.exercise_candidate_projection import project_units, source_registry, content_hash


def fixture_case(case):
    blocks = [DocumentBlock(f'b{i}', b['type'], b['text'], ['第一章', '习题'], page_start=b['page'], page_end=b['page'],
                            attributes={**({'mineru_type': 'paragraph_title'} if b['mineru_title'] else {}),
                                        **({'asset_id': b['asset']} if b['asset'] else {})}) for i,b in enumerate(case['input_blocks'])]
    book = CanonicalBook('toy', 'toy', blocks, 'v1')
    units = [dict(unit_id=u.unit_id, kind=u.kind, text=u.text, chapter=u.section_path[0], page_start=u.blocks[0].page_start,
                  page_end=max(b.page_end for b in u.blocks), source_block_ids=[b.block_id for b in u.blocks], truncated=u.truncated) for u in learning_units(book)]
    registry = source_registry(book, units, {b.block_id for b in blocks})
    return book, units, registry, project_units(units, registry, canonical_book_fingerprint(book), dict(chapter='',page_start=None,page_end=None,source_mode='exercise_sections'))


CASES = json.loads(Path('docs/qa/question-extraction-quality-2026-10-17/regression-cases.json').read_text())['cases']


@pytest.mark.parametrize('case', CASES, ids=lambda c:c['id'])
def test_frozen_structural_probes_v1(case):
    book, units, registry, proposals = fixture_case(case)
    assert project_units(units, registry, canonical_book_fingerprint(book), dict(chapter='',page_start=None,page_end=None,source_mode='exercise_sections')) == proposals
    if case['id'] == 'R18':
        assert proposals == []
        return
    assert proposals
    if case['id'] == 'R05':
        assert proposals[0]['projection']['method'] == 'unresolved'
        assert proposals[0]['issues']
    else:
        for new, stem in zip(proposals, case['expected']['stems']):
            # Display wrappers are allowed; source tokens are never changed.
            actual = new['question_text'].replace('$$\n','').replace('\n$$','')
            assert (actual.rstrip() if case['id'] == 'R12' else actual) == stem
        if case['id'] in ('R02','R12','R13','R14','R15','R16'):
            assert proposals[0]['answer'] + proposals[0]['explanation'] == case['expected']['answers'][0]
        else:
            assert all(not p['answer'] and not p['explanation'] for p in proposals)
    for p in proposals:
        spans = [s for spans in p['projection']['parts'].values() for s in spans]
        assert set(s['block_id'] for s in spans) >= set(b for u in units if u['unit_id'] in p['projection']['unit_ids'] for b in u['source_block_ids'])
        if case['id'] != 'R12':
            assert len(spans) == len(set(s['block_id'] for s in spans))
        else:
            assert len(spans) == 2 and spans[0]['end'] == spans[1]['start']
    if case['id'] == 'R11':
        dep = proposals[0]['projection']['dependencies'][0]
        assert dep['asset_ids'] == ['toy-figure-A'] and dep['resolution'] == 'identified'
        assert any(i['code']=='missing_required_input' for i in proposals[0]['issues'])
    if case['id'] in ('R16','R19'):
        # Global learning-unit behavior is preserved, local projection repairs only.
        assert len(units) == (2 if case['id']=='R19' else 1)
        assert len(proposals) == 1


def test_unicode_hash_and_safe_source_snapshot():
    from memory.exercise_candidate_projection import snapshot
    block = DocumentBlock('b', 'paragraph', '中文😀\n$x$', ['章'], attributes={'source_file':'/private/key','asset_relpath':'secret','source_page_idx':1})
    snap = snapshot(block, 9)
    assert snap['order']==9 and snap['attributes']=={'source_page_idx':1}
    value = dict(question_text='中文😀\n$x$',answer='',explanation='',projection=None)
    assert content_hash(value) == 'c9902b649ae1e73c6ccdc4df4733b628aed0a7ee1ac85583a1c544a0fc617d58'


def test_table_empty_cells_and_unchanged_learning_material():
    case = deepcopy(CASES[0])
    book, units, _, _ = fixture_case(case)
    book.blocks.append(DocumentBlock('table','table','',['第一章','习题'],page_start=1,page_end=1,table_header=['','A','B'], table_rows=[['甲','1','2']]))
    units[0]['source_block_ids'].append('table')
    old = deepcopy(units)
    registry=source_registry(book,units,{b.block_id for b in book.blocks})
    p=project_units(units,registry,canonical_book_fingerprint(book),dict(chapter='',page_start=None,page_end=None,source_mode='exercise_sections'))[0]
    assert '|  | A | B |' in p['question_text']
    assert units == old

from backend.services.exercise_candidate_review import ExerciseCandidateReviewService, CandidateAdmissionError
from memory.textbook_exercise_importer import ExtractedTextbookExerciseText
from memory.exercise_bank import ExerciseBank, ExerciseRecord


def admission_fixture(case=CASES[0]):
    book, units, registry, proposals = fixture_case(case)
    extracted = ExtractedTextbookExerciseText(text='source',provider='canonical-learning-units',book_name='toy',units=units,
                                            canonical_hash=canonical_book_fingerprint(book),source_blocks=registry)
    service=ExerciseCandidateReviewService(extract_provider=lambda book_name,**kwargs: extracted)
    p=proposals[0]
    item=dict(origin_id='c1',question_text=p['question_text'],answer=p['answer'],explanation=p['explanation'],
              candidate_context=dict(projection=deepcopy(p['projection']),review=None))
    return service, item, extracted


def confirm(item, resolutions):
    item['candidate_context']['review'] = dict(content_hash=content_hash({**item,'projection':item['candidate_context']['projection']}),
                                              resolutions=[dict(issue_key=k,decision=v) for k,v in resolutions.items()])


def test_admission_normal_and_replayed_structure():
    service,item,_=admission_fixture()
    assert service.prepare('toy',[item])[0]['review_kind']=='system_proposed'
    confirm(item,{})
    assert service.prepare('toy',[item])[0]['review_kind']=='user_confirmed'
    item['question_text']+=' changed'
    with pytest.raises(CandidateAdmissionError) as e:service.prepare('toy',[item])
    assert e.value.status==409
    item['candidate_context']['review']=None
    with pytest.raises(CandidateAdmissionError):service.prepare('toy',[item])


@pytest.mark.parametrize('mutation', ['no_context','wrong_hash','foreign_block','omitted_block','overlap','bad_span','unknown_unit','fake_ready','removed_dependency'])
def test_forged_source_or_state_never_admitted(mutation):
    service,item,_=admission_fixture(CASES[10] if mutation=='removed_dependency' else CASES[1])
    p=item['candidate_context']['projection']
    if mutation=='no_context':item['candidate_context']=None
    elif mutation=='wrong_hash':p['canonical_hash']='0'*64
    elif mutation=='foreign_block':p['parts']['question'][0]['block_id']='other-book'
    elif mutation=='omitted_block':p['parts']['explanation']=[]
    elif mutation=='overlap':p['parts']['context']=deepcopy(p['parts']['question'])
    elif mutation=='bad_span':p['parts']['question'][0]['end']=100000
    elif mutation=='unknown_unit':p['unit_ids']=['unknown']
    elif mutation=='fake_ready':p['method']='whole_unit'
    elif mutation=='removed_dependency':p['dependencies']=[]
    with pytest.raises(CandidateAdmissionError):service.prepare('toy',[item])


def test_required_picture_not_bypassed_by_confirmation_or_embedded_claim():
    service,item,_=admission_fixture(CASES[10])
    p=item['candidate_context']['projection'];p['method']='user_edited'
    p['dependencies'][0]['resolution']='embedded'
    confirm(item,{'edited_content:':'corrected','missing_required_input:figure:图A':'source_checked'})
    with pytest.raises(CandidateAdmissionError):service.prepare('toy',[item])
    # An explicitly rewritten independent text question may exclude a non-required figure.
    item['question_text']='1. 计算两个数2和3的和。'
    p['dependencies'][0]['requirement']='reference'
    confirm(item,{'edited_content:':'corrected','missing_required_input:figure:图A':'not_applicable'})
    assert service.prepare('toy',[item])[0]['review_kind']=='user_confirmed'


def test_inline_edit_unicode_spans_and_confirmation():
    service,item,extracted=admission_fixture(CASES[11])
    p=item['candidate_context']['projection'];p['method']='user_edited'
    raw=extracted.source_blocks[0]['text'];at=raw.index('\n解')
    p['parts']['unassigned']=[]
    p['parts']['question']=[dict(block_id='b0',start=0,end=at)]
    p['parts']['explanation']=[dict(block_id='b0',start=at,end=None)]
    item['question_text']=raw[:at];item['explanation']=raw[at:]
    confirm(item,{'edited_content:':'corrected'})
    assert service.prepare('toy',[item])[0]['review_kind']=='user_confirmed'
    item['question_text']=raw
    confirm(item,{'edited_content:':'corrected','solution_in_stem:b0':'corrected'})
    with pytest.raises(CandidateAdmissionError):service.prepare('toy',[item])


def test_receipts_atomic_with_duplicate_and_rollback(tmp_path):
    service,item,_=admission_fixture()
    receipts=service.prepare('toy',[item])
    bank=ExerciseBank(tmp_path/'exercises.db')
    record=ExerciseRecord(question_text=item['question_text'],origin_id='c1')
    batch=bank.add_batch([record],candidate_receipts=receipts)
    assert batch['candidate_receipts'][0]['exercise_id']==record.id
    duplicate=bank.add_batch([ExerciseRecord(question_text=item['question_text'],origin_id='c1')],candidate_receipts=receipts)
    assert duplicate['candidate_receipts']==[] and duplicate['skipped'][0]['duplicate_of']==record.id
    bank.rollback_import_batch(batch['id'])
    assert bank.list_import_batches()[-1]['candidate_receipts']==batch['candidate_receipts']
    # SQL failure on batch insert rolls back the earlier exercise insert too.
    with bank.store._connect() as conn:
        conn.execute("CREATE TRIGGER fail_batch BEFORE INSERT ON exercise_import_batches BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with pytest.raises(Exception,match='injected failure'):
        bank.add_batch([ExerciseRecord(question_text='new',origin_id='c1')],candidate_receipts=receipts)
    assert not bank.list_all()


def test_api_version_routing_and_all_or_nothing(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import backend.api.exercises as api
    from backend.schemas import ExerciseBatchAddRequest
    service,item,_=admission_fixture()
    monkeypatch.setattr('backend.services.exercise_candidate_review.ExerciseCandidateReviewService', lambda:service)
    bank=ExerciseBank(tmp_path/'exercises.db');monkeypatch.setattr(api,'_bank',lambda _:bank)
    monkeypatch.setattr(api,'_log_learning_event',lambda *args,**kwargs:None)
    app=FastAPI();app.include_router(api.router);client=TestClient(app)
    assert client.post('/exercises/add',json=item).status_code==422
    assert client.post('/exercises/batch-add',json={'exercises':[item]}).status_code==422
    for version in (None,2,True,1.0,"1"):
        assert client.post('/exercises/candidates/batch-add',json=dict(exercises=[item],candidate_contract_version=version)).status_code==422
    invalid=deepcopy(item);invalid['origin_id']='bad';invalid['candidate_context']=None
    assert client.post('/exercises/candidates/batch-add',json=dict(exercises=[item,invalid],candidate_contract_version=1)).status_code==422
    assert bank.list_all()==[]
    response=client.post('/exercises/candidates/batch-add',json=dict(exercises=[item],candidate_contract_version=1)).json()
    assert response['count']==1 and response['candidate_receipts'][0]['review_kind']=='system_proposed'
    assert client.post('/exercises/add',json={'question_text':'manual legacy'}).json()['success']
    old=FastAPI(); old.include_router(api.router,include_in_schema=False)
    old.router.routes=[r for r in old.router.routes if getattr(r,'path','')!='/exercises/candidates/batch-add']
    assert TestClient(old).post('/exercises/candidates/batch-add',json=dict(exercises=[item],candidate_contract_version=1)).status_code==404


def test_v1_analysis_echo_and_model_rejection_without_bank_io(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import backend.api.exercises as api
    service,item,extracted=admission_fixture(CASES[1])
    monkeypatch.setattr(api,'extract_textbook_exercise_text',lambda *args,**kwargs:extracted)
    class EmptyBank:
        def list_all(self,**kwargs):return []
    monkeypatch.setattr(api,'_bank',lambda *args:EmptyBank())
    monkeypatch.setattr(api,'refine_low_confidence_candidates',lambda *args,**kwargs:pytest.fail('model call'))
    app=FastAPI();app.include_router(api.router);client=TestClient(app)
    response=client.post('/exercises/textbook-analyze',json={'book_name':'toy','candidate_contract_version':1}).json()
    assert response['candidate_contract_version']==1
    assert response['data'][0]['projection']['method']=='block_boundary'
    assert response['data'][0]['review'] is None
    assert client.post('/exercises/textbook-analyze',json={'book_name':'toy','candidate_contract_version':1,'use_llm':True}).status_code==422
    assert client.post('/exercises/textbook-analyze',json={'book_name':'toy','candidate_contract_version':99}).status_code==422


def test_v1_rejects_changed_source_and_image_paths_before_bank(monkeypatch):
    service,item,extracted=admission_fixture()
    item['image_path']='/private/fake-image.png'
    with pytest.raises(CandidateAdmissionError):service.prepare('toy',[item])
    item.pop('image_path')
    extracted.canonical_hash='b'*64
    with pytest.raises(CandidateAdmissionError) as e:service.prepare('toy',[item])
    assert e.value.status==409


def test_formula_only_unit_is_not_a_ready_question():
    case={'input_blocks':[{'text':'1.0 + x = y','type':'formula','page':1,'mineru_title':False,'asset':''}]}
    _,_,_,proposals=fixture_case(case)
    assert proposals[0]['projection']['method']=='unresolved'
    assert any(i['code']=='boundary_uncertain' for i in proposals[0]['issues'])


def test_prior_example_reference_is_not_complete_input_after_generic_confirmation():
    case={'input_blocks':[{'text':'1. 根据前例参数计算测量输出。','type':'paragraph','page':1,'mineru_title':False,'asset':''}]}
    service,item,_=admission_fixture(case)
    p=item['candidate_context']['projection'];p['method']='user_edited';p['dependencies'][0]['resolution']='embedded'
    item['question_text']='1. 计算例11.5中所述条件下的测量输出。'
    confirm(item,{'edited_content:':'corrected','missing_required_input:prior_context':'corrected'})
    with pytest.raises(CandidateAdmissionError):service.prepare('toy',[item])
    item['question_text']='1. 已知两个输入分别为2与3，求其和。'
    confirm(item,{'edited_content:':'corrected','missing_required_input:prior_context':'corrected'})
    assert service.prepare('toy',[item])[0]['review_kind']=='user_confirmed'


def test_empty_figure_block_and_table_conflict_stay_traceable():
    case={'input_blocks':[{'text':'1. 根据图A说明给定电路的工作过程。','type':'paragraph','page':1,'mineru_title':False,'asset':''},
                          {'text':'','type':'figure','page':1,'mineru_title':False,'asset':'existing-empty-figure'}]}
    book,units,registry,proposals=fixture_case(case)
    assert registry[1]['text']=='' and registry[1]['attributes']['asset_id']=='existing-empty-figure'
    assert any(s['block_id']=='b1' for spans in proposals[0]['projection']['parts'].values() for s in spans)
    book.blocks.append(DocumentBlock('table','table','| A | 1 |',['第一章','习题'],page_start=1,page_end=1,table_rows=[['A','2']]))
    units[0]['source_block_ids'].append('table')
    units[0]['text'] += '\n\n| A | 1 |'
    registry=source_registry(book,units,{b.block_id for b in book.blocks})
    proposal=project_units(units,registry,canonical_book_fingerprint(book),dict(chapter='',page_start=None,page_end=None,source_mode='exercise_sections'))[0]
    assert any(i['code']=='boundary_uncertain' and i['block_ids']==['table'] for i in proposal['issues'])
    assert '| A | 1 |' in proposal['question_text']


def test_adjacent_merge_accepted_only_with_new_explicit_confirmation():
    service,item,extracted=admission_fixture(CASES[5])
    proposals=project_units(extracted.units,extracted.source_blocks,extracted.canonical_hash,item['candidate_context']['projection']['scope'])
    p=item['candidate_context']['projection'];p['method']='user_edited'
    p['unit_ids']=[u for v in proposals for u in v['projection']['unit_ids']]
    p['parts']['question']=[s for v in proposals for s in v['projection']['parts']['question']]
    item['question_text']='\n\n'.join(v['question_text'] for v in proposals)
    with pytest.raises(CandidateAdmissionError):service.prepare('toy',[item])
    confirm(item,{'edited_content:':'corrected'})
    assert service.prepare('toy',[item])[0]['review_kind']=='user_confirmed'


def test_corrected_boundary_requires_actual_body_correction():
    service,item,_=admission_fixture(CASES[4])
    p=item['candidate_context']['projection'];p['method']='user_edited'
    confirm(item,{'edited_content:':'corrected','boundary_uncertain:b2':'corrected'})
    with pytest.raises(CandidateAdmissionError):service.prepare('toy',[item])
    item['question_text']='【例1.2】求 $2+3$。';item['explanation']='解：结果为5。'
    confirm(item,{'edited_content:':'corrected','boundary_uncertain:b2':'corrected'})
    assert service.prepare('toy',[item])[0]['review_kind']=='user_confirmed'
