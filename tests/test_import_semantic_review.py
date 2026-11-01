from datetime import datetime, timezone
from types import SimpleNamespace
import json
import pytest
from ingestion.document_ir import CanonicalBook, DocumentBlock
from ingestion.document_workflows import canonical_outline
from ingestion.outline_recovery import recover_outline
from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore, select_physical_pages
from backend.services.import_semantic_review import _edits, _pair, run_semantic_review
from memory.exercise_file_importer import ExtractedExerciseText
from memory.exercise_structure import exercise_units
from llm.configuration import resolve_model_role
from llm.pricing import import_rates, usage_cost


def model():
    return resolve_model_role('vision',dict(LLM_VISION_PROVIDER='deepseek',LLM_VISION_MODEL='deepseek-flash',LLM_VISION_API_KEY='fixture'))


def source():
    def b(bid,text,page,path):return DocumentBlock(bid,'paragraph',text,path,page_start=page,page_end=page,source_kind='mineru')
    return CanonicalBook('习题','fixture',[b('a','1.1 测得电压2V，求误差。',2,['第一章','习题']),
        b('b','1.2 测得电压3V，求误差。',3,['第一章','习题']),
        b('c','1.1 测得电压2V，求误差。',20,['第一章','典型题解']),
        b('d','解：误差为0.1V。',20,['第一章','典型题解'])],'fixture',source_page_count=20)


def test_page_range_is_applied_to_source_before_review():
    raw=ExtractedExerciseText('source','zip',canonical_book=source())
    selected=select_physical_pages(raw,page_start=2,page_end=3)
    assert [b.block_id for b in selected.canonical_book.blocks]==['a','b']
    assert len(raw.canonical_book.blocks)==4
    with pytest.raises(ValueError):select_physical_pages(raw,page_start=21)
    with pytest.raises(ValueError):select_physical_pages(ExtractedExerciseText('word','docx'),page_start=2)


def test_llm_pairing_keeps_distinct_question_and_all_source_answers(tmp_path):
    class Session:
        def call(self,key,system,content,**kwargs):
            units=json.loads(content)['units']
            assert len(units)==3
            return dict(groups=[dict(keep=units[0]['id'],merge=[units[2]['id']],number='1.1')])
    book,report=_pair(source(),Session(),lambda *a:None)
    units=exercise_units(book,unrestricted=True)
    assert len(units)==2 and report['merged_questions']==1
    first=next(u for u in units if u['unit_id']=='a')
    assert '误差为0.1V' in first['text'] and first['pairing_reviewed']
    assert first['text'].count('测得电压2V')==1
    assert any(b.block_id=='c' and b.text.startswith('1.1') for b in book.blocks)
    store=ExerciseFileAnalysisStore(tmp_path)
    saved,_,_=store.create(ExtractedExerciseText('source','zip',canonical_book=book),book_name='习题')
    assert len(saved.units)==2 and any('误差为0.1V' in u['text'] for u in saved.units)


def test_text_cleanup_keeps_original_and_rejects_unaligned_replacement():
    book=source();book.blocks[0].text='题目来源 $\\frac{2024年}{数学一}$'
    corrections=_edits(book,[dict(block_id='b0',find='$\\frac{2024年}{数学一}$',replace='2024年数学一')],{'b0':'a'})
    assert book.blocks[0].text=='题目来源 2024年数学一'
    assert '\\frac' in book.blocks[0].attributes['original_ocr_text'] and len(corrections)==1
    with pytest.raises(ValueError):_edits(book,[dict(block_id='b0',find='不存在',replace='新内容')],{'b0':'a'})


def test_outline_model_changes_nodes_and_clears_old_manual_overlay(tmp_path):
    book=CanonicalBook('教材','fixture',[
        DocumentBlock('chapter','heading','第一章 基础',['第一章 基础'],page_start=1,page_end=1),
        DocumentBlock('fragment','heading','第二章练习后的分析',['第一章 基础'],page_start=2,page_end=2),
        DocumentBlock('body','paragraph','正文内容。',['第一章 基础'],page_start=2,page_end=2)],'fixture',source_page_count=2)
    book=recover_outline(book,force=True)
    def complete(*args,**kwargs):
        data=json.loads(kwargs['messages'][1]['content'][0]['text'])
        bid=next(b['id'] for b in data['blocks'] if b['text']=='第二章练习后的分析')
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(dict(blocks=[dict(block_id=bid,heading_level=0,role='body')]))))],usage=dict(prompt_tokens=100,completion_tokens=20))
    reviewed,report=run_semantic_review(book,directory=tmp_path,resolved=model(),purpose='outline',complete=complete)
    assert len(canonical_outline(reviewed))==1 and report['outline_changed']
    assert len(canonical_outline(book))==2


def test_cost_uses_cached_tokens_and_weekend_rate():
    rates=import_rates(model(),now=datetime(2026,11,1,tzinfo=timezone.utc))
    assert rates['input_price']==1 and rates['output_price']==4
    cost=usage_cost(dict(prompt_tokens=10000,prompt_cache_hit_tokens=5000,completion_tokens=1000),rates)
    assert cost==pytest.approx(.0091)


def test_semantic_duplicate_with_different_values_is_retained():
    class Session:
        def call(self,*args,**kwargs):return dict(groups=[dict(keep='b',merge=['c'],number='1.2')])
    book,report=_pair(source(),Session(),lambda *a:None)
    assert len(exercise_units(book,unrestricted=True))==3
    assert report['merged_questions']==0 and len(report['rejected_merges'])==1


def test_visual_review_cannot_change_exercise_heading(tmp_path):
    from PIL import Image
    from backend.services.import_semantic_review import _visual
    book=source()
    book.blocks.insert(0,DocumentBlock('heading','heading','习题',['第一章','习题'],page_start=2,page_end=2))
    book.blocks.append(DocumentBlock('figure','figure','手写批注',['第一章','习题'],page_start=2,page_end=2,
        attributes=dict(source_asset_relpath='annotation.png')))
    Image.new('RGB',(40,40),'white').save(tmp_path/'annotation.png')
    class Session:
        def call(self,*args,**kwargs):return dict(blocks=[dict(block_id='heading',role='overview',heading_level=0),dict(block_id='figure',role='annotation')])
    reviewed,_=_visual(book,Session(),lambda *a:None,asset_root=tmp_path,pdf_path=None)
    assert reviewed.blocks[0].block_type=='heading' and 'structure_role' not in reviewed.blocks[0].attributes
    assert len(exercise_units(reviewed,unrestricted=True))==3


def test_alternating_chapter_questions_and_partial_answers_keep_later_chapters(tmp_path):
    rows=[]
    for n,title in enumerate(('第一章','第二章'),1):
        rows += [DocumentBlock(f'q{n}','paragraph',f'{n}.1 测量电压{n}V，求误差。',[title,'习题'],source_kind='mineru',page_start=n*2,page_end=n*2),
                 DocumentBlock(f'a{n}','paragraph',f'{n}.1 解：误差为0.1V。',[title,'参考答案'],source_kind='mineru',page_start=n*2+1,page_end=n*2+1)]
    book=CanonicalBook('教材','fixture',rows,'fixture',source_page_count=5)
    store=ExerciseFileAnalysisStore(tmp_path)
    result,_,paired=store.create(ExtractedExerciseText('source','zip',canonical_book=book),book_name='教材')
    assert len(result.units)==2 and paired==2
    assert all(u['answer_block_ids'] for u in result.units)
    class Session:
        def call(self,key,system,content,**kwargs):
            units=json.loads(content)['units'];question=next(u for u in units if not u['answer_only']);answer=next(u for u in units if u['answer_only'])
            return dict(groups=[dict(keep=question['id'],merge=[answer['id']],number=question['number'])])
    reviewed,report=_pair(book,Session(),lambda *a:None)
    assert report['merged_questions']==2 and len(exercise_units(reviewed,unrestricted=True))==2


def test_failed_paid_request_requires_explicit_retry_and_retains_old_receipt(tmp_path):
    from backend.services.import_review_session import ReviewSession
    calls=[]
    def failed(*args,**kwargs):
        calls.append('failed');raise RuntimeError('secret-provider-details')
    first=ReviewSession(model(),tmp_path,dict(source='fixture'),complete=failed)
    with pytest.raises(ValueError):first.call('batch','system','{}')
    cached=ReviewSession(model(),tmp_path,dict(source='fixture'),complete=failed)
    with pytest.raises(ValueError):cached.call('batch','system','{}')
    assert calls==['failed']
    def completed(*args,**kwargs):
        calls.append('success')
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='{"blocks":[]}'))],usage=dict(prompt_tokens=100,completion_tokens=20))
    retry=ReviewSession(model(),tmp_path,dict(source='fixture'),complete=completed,retry_failed=True)
    assert retry.call('batch','system','{}')=={'blocks':[]}
    retry.call('batch','system','{}')
    assert calls==['failed','success'] and retry.report()['calls']==2
    assert retry.report()['usage_unknown']
    assert 'secret-provider-details' not in retry.path.read_text()


def test_independent_answer_cleanup_uses_shared_budget_and_distinct_receipt_keys(tmp_path):
    from backend.services.import_semantic_review import create_review_session
    calls=[]
    def complete(*args,**kwargs):
        data=json.loads(kwargs['messages'][1]['content'][0]['text']);calls.append(data)
        edits=[]
        if data.get('blocks') and '\\frac{2024' in data['blocks'][0]['text']:
            edits=[dict(block_id=data['blocks'][0]['id'],find='$\\frac{2024年}{数学一}$',replace='2024年数学一')]
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(dict(edits=edits,blocks=[],groups=[]),ensure_ascii=False)))],usage=dict(prompt_tokens=100,completion_tokens=20))
    book=source()
    session=create_review_session(book,directory=tmp_path,resolved=model(),purpose='exercises',complete=complete)
    run_semantic_review(book,directory=tmp_path,resolved=model(),purpose='exercises',session=session)
    before=session.report()['calls']
    answer=CanonicalBook('答案','fixture',[DocumentBlock('ans','paragraph','1.1 $\\frac{2024年}{数学一}$ 解：2。',['参考答案'],page_start=1,page_end=1)],'fixture',source_page_count=1)
    cleaned,report=run_semantic_review(answer,directory=tmp_path,resolved=model(),purpose='answer_text',session=session)
    assert '2024年数学一' in cleaned.blocks[0].text and '\\frac' not in cleaned.blocks[0].text
    assert report['calls']==before+1 and report['text_corrections']==1
    assert any(c['key'].startswith('answer_text:') for c in session.ledger['calls'])


def test_restoring_original_outline_keeps_model_receipts_and_original_pages(tmp_path):
    from copy import deepcopy
    from ingestion.document_ir import persist_canonical_book,canonical_book_fingerprint
    from backend.services.structure_review_jobs import review_directory,discard_review_candidate
    from backend.services.book_outline import reviewed_source_page
    from utils.json_io import atomic_write_json
    original=source();persist_canonical_book(original,progress_root=tmp_path)
    candidate=deepcopy(original);candidate.blocks[0].text='已校正题干'
    directory=review_directory(tmp_path,'book',original.book_name)
    persist_canonical_book(candidate,progress_root=directory/'candidate')
    atomic_write_json(directory/'candidate.json',dict(source_version=canonical_book_fingerprint(original)))
    atomic_write_json(directory/'semantic_review.json',dict(calls=['retained receipt']))
    assert reviewed_source_page(original.book_name,2,progress_root=tmp_path)['blocks'][0]['text']=='已校正题干'
    discard_review_candidate(dict(kind='book',reference=original.book_name,book_name=original.book_name),progress_root=tmp_path,books_root=tmp_path,jobs=None)
    assert reviewed_source_page(original.book_name,2,progress_root=tmp_path)['blocks'][0]['text']==original.blocks[0].text
    assert (directory/'semantic_review.json').exists() and (directory/'candidate.previous.json').exists()


def test_partial_model_failure_keeps_applied_text_and_marks_explicit_retry(tmp_path):
    blocks=[DocumentBlock('first','paragraph','OCR文字 '+('正文。'*3100),['教材'],page_start=1,page_end=1),
            DocumentBlock('second','paragraph','下一页正文。',['教材'],page_start=2,page_end=2)]
    book=CanonicalBook('教材','fixture',blocks,'fixture',source_page_count=2)
    count=[]
    def complete(*args,**kwargs):
        count.append(1)
        if len(count)>1:raise RuntimeError('network unavailable')
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(dict(edits=[dict(block_id='b0',find='OCR文字',replace='校正文字')]))))],usage=dict(prompt_tokens=100,completion_tokens=20))
    reviewed,report=run_semantic_review(book,directory=tmp_path,resolved=model(),purpose='exercises',complete=complete)
    assert reviewed.blocks[0].text.startswith('校正文字') and reviewed.blocks[1].text=='下一页正文。'
    assert book.blocks[0].text.startswith('OCR文字')
    assert report['status']=='partial' and report['needs_retry'] and len(count)==2


def test_word_snapshot_has_canonical_source_and_reviewed_snapshot_reuses_original_reference(tmp_path):
    store=ExerciseFileAnalysisStore(tmp_path)
    _,sid,_=store.create(ExtractedExerciseText('1. 计算测量误差。','docx'),book_name='教材')
    raw=json.loads((store.root/f'{sid}.json').read_text())['canonical_source']
    assert raw and raw['blocks'][0]['text'].startswith('1.')
    book=CanonicalBook(**{**raw,'blocks':[DocumentBlock.from_dict(b) for b in raw['blocks']]})
    book.source_metadata['review_origin_source_id']=sid
    _,next_id,_=store.create(ExtractedExerciseText('1. 计算测量误差。','docx',canonical_book=book),book_name='教材')
    assert store.review_reference(next_id,'教材')==sid
    with pytest.raises(ValueError):store.review_reference(next_id,'其他教材')


def test_measurement_rows_remain_in_reviewed_question_and_next_question_is_separate(tmp_path):
    from ingestion.document_workflows import learning_units
    book=CanonicalBook('教材','fixture',[
        DocumentBlock('first','paragraph','2.1 测定重量8次。\n236.45 236.37 236.51 236.34\n236.39 236.48 236.47 236.40',['第一章','习题'],
                      page_start=1,page_end=1,source_kind='mineru',attributes=dict(structure_unit_start=True)),
        DocumentBlock('ask','paragraph','求平均值及标准差。',['第一章','习题'],page_start=1,page_end=1,source_kind='mineru'),
        DocumentBlock('next','paragraph','2.2 测定电流5次。',['第一章','习题'],page_start=1,page_end=1,source_kind='mineru'),
        DocumentBlock('data','paragraph','168.41 168.54 168.59 168.40 168.50',['第一章','习题'],page_start=1,page_end=1,source_kind='mineru'),
    ],'fixture',source_page_count=1)
    assert len(learning_units(book))==2
    assert len(exercise_units(book,unrestricted=True))==2
    result,_,_=ExerciseFileAnalysisStore(tmp_path).create(ExtractedExerciseText('source','zip',canonical_book=book),book_name='教材')
    assert len(result.units)==2
    assert all(value in result.units[0]['text'] for value in ('236.45','236.40','求平均值'))
    assert '168.41' in result.units[1]['text'] and '236.45' not in result.units[1]['text']
    # Explicit model boundaries can override the numeric-row heuristic.
    book.blocks[-1].attributes['structure_unit_start']=True
    assert len(exercise_units(book,unrestricted=True))==3


def test_damaged_ocr_is_preserved_as_context_without_polluting_question_or_answer(tmp_path):
    from memory.exercise_candidate_projection import project_units
    book=source();book.blocks.insert(1,DocumentBlock('bad','paragraph','[Unreadable]',book.blocks[0].section_path,page_start=2,page_end=2))
    book.blocks.insert(2,DocumentBlock('loop','formula',r'\( '+r' = \frac{1}{2} S_n + 1'*160,book.blocks[0].section_path,page_start=2,page_end=2))
    result,_,_=ExerciseFileAnalysisStore(tmp_path).create(ExtractedExerciseText('source','zip',canonical_book=book),book_name='习题')
    candidates=project_units(result.units,result.source_blocks,result.canonical_hash,dict(source_mode='file'))
    first=candidates[0]
    assert first['question_text']==book.blocks[0].text
    assert any(i['code']=='source_ocr_damage' for i in first['issues'])
    assert len(first['projection']['parts']['context'])==2
    assert any(b['text']=='[Unreadable]' and b['attributes']['ocr_damage_reason'] for b in result.source_blocks)


def test_quality_review_uses_formula_crops_and_only_excludes_model_confirmed_annotations(tmp_path):
    from PIL import Image
    from backend.services.import_semantic_review import _quality_review
    book=source();book.blocks.insert(0,DocumentBlock('title','heading','第一章',[],page_start=2,page_end=2))
    book.blocks.insert(2,DocumentBlock('bad','formula',r'\text{若} '*300,['第一章','习题'],page_start=2,page_end=2,
        attributes=dict(original_visual_asset=dict(source_relpath='formula.jpg'))))
    Image.new('RGB',(40,40),'white').save(tmp_path/'formula.jpg')
    class Session:
        def call(self,key,system,content,**kw):
            assert any(p['type']=='image_url' for p in content)
            assert len(content[0]['text'])<5000
            return dict(blocks=[dict(block_id='bad',role='annotation',reason='手写批注'),dict(block_id='title',role='annotation'),
                                dict(block_id='a',role='unknown',reason='相邻片段无法确认')])
    reviewed,report=_quality_review(book,Session(),lambda *a:None,asset_root=tmp_path)
    assert report['excluded_ocr_noise']==1 and report['quarantined_ocr_blocks']==1
    assert report['unresolved'][0]['block_id']=='a'
    assert next(b for b in reviewed.blocks if b.block_id=='bad').text==r'\text{若} '*300
    assert 'structure_role' not in reviewed.blocks[0].attributes


@pytest.mark.parametrize('raw', [r'\(\frac{1}{2}\)',r'\[\frac{1}{2}\]',r'$\frac{1}{2}$',r'$$\frac{1}{2}$$',r'$x$ + $y$'])
def test_formula_serialization_does_not_nest_math_delimiters(raw):
    from memory.exercise_candidate_projection import serialize_block
    result=serialize_block(dict(block_type='formula',text=raw))
    assert r'\(' not in result and r'\[' not in result
    assert '$$\n$' not in result
    assert serialize_block(dict(block_type='formula',text=result))==result


def test_standalone_formula_and_table_math_need_no_frontend_delimiter_repair():
    from memory.exercise_candidate_projection import serialize_block
    from ingestion.source_markdown import table_markdown
    raw=r'1 0 0 \mathrm{Pa} - 0. 3 \mathrm{Pa}'
    assert serialize_block(dict(block_type='formula',text=raw))=='$$\n'+raw+'\n$$'
    table=r'| $x=1$$y=2$$z=3$ |'+'\n| --- |'
    assert '$x=1$ $y=2$ $z=3$' in table_markdown(table)
    html='<table><tr><td rowspan="2">对象</td><td colspan="2">读数</td></tr><tr><td>1</td><td>2</td></tr><tr><td>甲</td><td>3</td><td>4</td></tr></table>'
    result=table_markdown(html)
    assert result.splitlines()==['| 对象 | 读数 | 读数 |','| --- | --- | --- |','| 对象 | 1 | 2 |','| 甲 | 3 | 4 |']
    assert table_markdown(result)==result


def test_review_quote_includes_separate_answers_without_calling_model():
    from backend.services.import_semantic_review import semantic_review_estimate
    book = source()
    quote = semantic_review_estimate(book, model(), 'exercises')
    with_answers = semantic_review_estimate(book, model(), 'exercises', answer_book=book)
    assert quote['pages'] == [2, 3, 20]
    assert quote['estimated_cost']['high'] > quote['estimated_cost']['low'] > 0
    assert with_answers['source_characters'] == quote['source_characters'] * 2
    assert with_answers['max_calls'] > quote['max_calls']
    assert with_answers['estimated_cost']['high'] > quote['estimated_cost']['high']
    assert with_answers['includes_answer_file'] is True


def test_review_quote_does_not_invent_prices_for_custom_model():
    from dataclasses import replace
    from backend.services.import_semantic_review import semantic_review_estimate
    resolved = replace(model(), model='custom-vision')
    assert semantic_review_estimate(source(), resolved, 'exercises')['estimated_cost'] is None


def test_plan_endpoint_quotes_only_without_creating_paid_job(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import structure_reviews as api
    import backend.services.structure_review_jobs as jobs
    import config
    import llm.factory
    monkeypatch.setattr(jobs, 'resolve_source', lambda *a, **k: (source(), tmp_path, None))
    monkeypatch.setattr(config, 'get_model_role_config', lambda role: model())
    def forbidden(*args, **kwargs):
        pytest.fail('A quote must not start a job or call a paid model')
    monkeypatch.setattr(jobs, 'start_review', forbidden)
    monkeypatch.setattr(llm.factory, 'create_vision_completion', forbidden)
    app = FastAPI()
    app.include_router(api.router)
    response = TestClient(app).post('/structure-reviews/plan', json=dict(kind='book', reference='习题', book_name='习题', purpose='textbook'))
    assert response.status_code == 200
    data = response.json()['data']
    assert data['model'] == 'deepseek-flash' and data['provider']
    assert data['estimated_cost']['high'] > 0
    assert data['pages'] == [2, 3, 20]
