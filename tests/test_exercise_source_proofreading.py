"""Source correction/admission contracts. Model responses are fixtures, no paid calls."""
import json
from types import SimpleNamespace

import pytest

from backend.services.exercise_candidate_review import ExerciseCandidateReviewService, CandidateAdmissionError
from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
from backend.services.import_semantic_review import _batches, _text_input, run_semantic_review
from ingestion.document_ir import CanonicalBook, DocumentBlock, persist_canonical_book, canonical_book_fingerprint
from llm.configuration import resolve_model_role
from memory.exercise_candidate_projection import content_hash, project_units
from memory.exercise_file_importer import ExtractedExerciseText


def model():
    return resolve_model_role('vision',dict(LLM_VISION_PROVIDER='deepseek',LLM_VISION_MODEL='deepseek-flash',LLM_VISION_API_KEY='fixture'))


def response(value):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(value,ensure_ascii=False)))],usage=dict(prompt_tokens=100,completion_tokens=20))


def test_whole_cross_page_question_and_raw_neighbours_are_sent():
    blocks=[DocumentBlock('q1','paragraph','1. '+('题干。'*2950),[],page_start=1),
            DocumentBlock('tail','paragraph','最后一个子问和选项。',[],page_start=2),
            DocumentBlock('q2','paragraph','2. 下一题。'+('正文。'*50),[],page_start=2)]
    book=CanonicalBook('fixture','fixture',blocks,'fixture')
    batches=list(_batches(blocks,limit=8800))
    assert [b.block_id for b in batches[0]]==['q1','tail']
    content,aliases,_=_text_input(book,batches[0])
    payload=json.loads(content[0]['text'])
    assert payload['blocks'][1]['text']=='最后一个子问和选项。'
    assert payload['context_blocks'][0]['text'].startswith('2. 下一题')
    assert set(aliases.values())=={'q1','tail','q2'}


@pytest.mark.parametrize('with_pdf',[False,True])
def test_formula_correction_requires_visual_source_and_is_reviewed_before_admission(tmp_path,with_pdf):
    import fitz
    from backend.exercise_candidate_schemas import CandidateContext
    original=CanonicalBook('fixture','fixture',[DocumentBlock('q','paragraph',
        '1. （2024年数学一 填空题）计算 $x^2$ 的导数。', ['第一章'],page_start=1,page_end=1,source_kind='mineru')],'fixture',source_page_count=1)
    pdf=tmp_path/'source.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((40,40),'1. Find the derivative of x^3.')
        doc.save(pdf)
    captured=[]
    def complete(*args,**kwargs):
        content=kwargs['messages'][1]['content'];data=json.loads(content[0]['text'])
        if 'units' in data:return response(dict(groups=[]))
        captured.append(content)
        return response(dict(edits=[dict(block_id='b0',find='$x^2$',replace='$x^3$',evidence='image')],
            metadata=[dict(block_id='b0',exam_year='2024',exam_source='2024年数学一',question_type='填空题',
                evidence=[dict(block_id='b0',quote='2024年数学一 填空题')])]))
    reviewed,report=run_semantic_review(original,directory=tmp_path/'review',resolved=model(),purpose='exercises',complete=complete,pdf_path=pdf if with_pdf else None)
    assert any(p['type']=='image_url' for p in captured[0])==with_pdf
    assert ('$x^3$' in reviewed.blocks[0].text)==with_pdf
    assert original.blocks[0].text.endswith('$x^2$ 的导数。')
    store=ExerciseFileAnalysisStore(tmp_path)
    extracted,sid,_=store.create(ExtractedExerciseText('source','pdf',canonical_book=reviewed),book_name='fixture')
    scope=dict(chapter='',page_start=None,page_end=None,source_mode='file')
    candidate=project_units(extracted.units,extracted.source_blocks,extracted.canonical_hash,scope,
        profile_version=extracted.profile_version,source_id=sid)[0]
    structure=candidate['projection']['structure']
    assert (structure['exam_year'],structure['question_type'],structure['exam_source'])==('2024','填空题','2024年数学一')
    context=CandidateContext(projection=candidate['projection']).model_dump()
    item=dict(origin_id='candidate',question_text=candidate['question_text'],answer=candidate['answer'],explanation=candidate['explanation'],candidate_context=context)
    service=ExerciseCandidateReviewService(file_provider=store.load)
    if with_pdf:
        assert report['text_corrections']==1
        assert extracted.source_blocks[0]['attributes']['original_ocr_text']==original.blocks[0].text
        with pytest.raises(CandidateAdmissionError,match='待核对'):service.prepare('fixture',[item])
        item['candidate_context']['review']=dict(content_hash=content_hash({**item,'projection':context['projection']}),
            resolutions=[dict(issue_key=i['key'],decision='source_checked') for i in candidate['issues'] if i['category']=='content'])
    else:
        assert report['unresolved'] and report['text_corrections']==0
    receipt=service.prepare('fixture',[item])[0]
    assert receipt['projection']['structure']['exam_year']=='2024'


def test_textbook_snapshot_keeps_unextracted_raw_material_and_leaves_index_source_unchanged(tmp_path,monkeypatch):
    from PIL import Image
    import memory.textbook_exercise_importer as importer
    from backend.services.structure_review_jobs import resolve_source
    raw=CanonicalBook('fixture','fixture',[
        DocumentBlock('intro','paragraph','这一段尚未分题的原始条件。',['第一章'],page_start=1,page_end=1),
        DocumentBlock('example','example','例1 计算已知函数在原点的导数。\n解：根据定义计算。',['第一章'],page_start=1,page_end=1),
        DocumentBlock('formula','formula','x^2',['第一章'],page_start=1,page_end=1,
                      attributes=dict(original_visual_asset=dict(source_relpath='expired.png',asset_relpath='figures/formula.png'))),
        DocumentBlock('exercise','paragraph','1. 这是一道课后习题。',['第一章','习题'],page_start=1,page_end=1),
        DocumentBlock('outside','example','例2 不在所选范围内。',['第二章'],page_start=3,page_end=3)],'fixture',source_page_count=3)
    (tmp_path/'fixture'/'figures').mkdir(parents=True)
    Image.new('RGB',(40,40),'white').save(tmp_path/'fixture'/'figures'/'formula.png')
    persist_canonical_book(raw,progress_root=tmp_path)
    monkeypatch.setattr(importer,'PROGRESS_PATH',tmp_path)
    extracted=importer.extract_textbook_exercise_text('fixture',page_start=1,page_end=1,source_mode='examples',candidate_contract_version=1)
    assert '尚未分题' not in extracted.text
    store=ExerciseFileAnalysisStore(tmp_path)
    sid=store.textbook_review_source(extracted)
    selected,_,_=resolve_source(dict(kind='file',reference=sid,book_name='fixture'),progress_root=tmp_path,books_root=tmp_path,jobs=None)
    assert {b.block_id for b in selected.blocks}=={'intro','example','formula','exercise'}
    assert len(store.load(sid,'fixture').units)==1 and store.load(sid,'fixture').units[0]['kind']=='example'
    assert selected.source_metadata['review_source_mode']=='examples'
    content,_,visual_ids=_text_input(selected,selected.blocks,asset_root=store.root/'assets')
    assert any(p['type']=='image_url' for p in content) and 'formula' in visual_ids
    from ingestion.document_ir import load_canonical_book
    assert canonical_book_fingerprint(load_canonical_book('fixture',progress_root=tmp_path))==canonical_book_fingerprint(raw)


def test_malformed_model_result_is_retryable_and_old_version_receipts_are_retained(tmp_path):
    from backend.services.import_review_session import ReviewSession
    session=ReviewSession(model(),tmp_path,dict(version=1),complete=lambda *a,**k:response(dict(edits=[dict(block_id='x')])) )
    with pytest.raises(ValueError,match='JSON'):session.call('text','system','{}')
    assert session.report()['failures'][0]['reason']=='模型未返回可用的JSON校对结果'
    next_session=ReviewSession(model(),tmp_path,dict(version=2),complete=lambda *a,**k:response({}))
    next_session.call('text','system','{}')
    previous=list(tmp_path.glob('semantic_review.previous-*.json'))
    assert len(previous)==1 and json.loads(previous[0].read_text())['calls'][0]['status']=='failed'
