"""Source insertion, scope and candidate replay using original-page fixture pixels."""
import json
from types import SimpleNamespace

import fitz
import pytest

from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
from backend.services.exercise_review_coverage import candidate_coverage
from backend.services.exercise_visual_review import apply_additions, page_input, page_packages
from backend.services.import_review_session import validate_review_response
from backend.services.import_semantic_review import run_semantic_review, semantic_review_plan
from ingestion.document_ir import CanonicalBook, DocumentBlock
from memory.exercise_candidate_projection import project_units
from memory.exercise_file_importer import ExtractedExerciseText


def source():
    return CanonicalBook('习题', 'mineru', [
        DocumentBlock('q1', 'paragraph', '1. 求函数的导数。', ['习题'], page_start=1, page_end=1, source_kind='mineru'),
        DocumentBlock('q3', 'paragraph', '3. 已知矩阵，求其秩。', ['习题'], page_start=1, page_end=1, source_kind='mineru'),
        DocumentBlock('continuation', 'paragraph', '并说明秩与参数的关系。', ['习题'], page_start=2, page_end=2, source_kind='mineru'),
    ], 'fixture', source_page_count=2)


def original_pdf(tmp_path):
    path = tmp_path/'original.pdf'
    with fitz.open() as doc:
        for _ in range(2):
            page = doc.new_page(width=600, height=800)
            page.insert_text((40,50), '1. Differentiate.   2. Find x.   3. Matrix rank.')
            page.draw_rect(fitz.Rect(60,400,220,550), color=(0,0,0))
        doc.save(path)
    return path


def inventory(page, ids):
    return dict(page=page, status='reviewed', questions=[dict(start_id=start, source_ids=members,
        parts=dict(stem='present',options='not_applicable',subquestions='not_applicable',
            figures_tables='not_applicable',original_solution='missing')) for start,members in ids])


def test_page_omission_reaches_saved_and_rebuilt_candidates_with_real_figure(tmp_path):
    raw = source(); pdf = original_pdf(tmp_path); store = ExerciseFileAnalysisStore(tmp_path/'progress')
    _, origin, _ = store.create(ExtractedExerciseText('', 'zip', canonical_book=raw),book_name=raw.book_name)
    calls = []
    def complete(resolved, **kwargs):
        data = json.loads(kwargs['messages'][1]['content'][0]['text']); calls.append(data)
        assert data['review_pages'] == [1,2] and len(data['original_images'])==2
        assert sum(part['type']=='image_url' for part in kwargs['messages'][1]['content'])==2
        assert '3.' in data['blocks'][1]['text']
        result = dict(additions=[
            dict(local_id='n1', page=1, image_ref='original-page:1', type='paragraph', text='2. 根据图A，求参数的值。',
                before_id='b1', unit_start=True, unit_role='question', bbox=[.1,.2,.8,.3]),
            dict(local_id='n2', page=1, image_ref='original-page:1', type='figure', text='图A',
                after_id='n1', unit_id='n1', unit_role='question', bbox=[.1,.5,.4,.7]),
        ], page_inventory=[inventory(1,[('b0',['b0']),('n1',['n1','n2']),('b1',['b1'])]),
                            inventory(2,[('b1',['b2'])])])
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(result)))],
            usage=dict(prompt_tokens=600,completion_tokens=400))
    from llm.configuration import resolve_model_role
    resolved = resolve_model_role('vision', dict(LLM_VISION_PROVIDER='deepseek',LLM_VISION_MODEL='deepseek-flash',LLM_VISION_API_KEY='fixture'))
    reviewed, report = run_semantic_review(raw,directory=tmp_path/'review',resolved=resolved,purpose='exercises',
        pdf_path=pdf,asset_root=store.root/'assets',complete=complete)
    assert len(calls)==1 and report['source_additions']==2
    assert report['page_content_coverage']['reviewed_pages']==[1,2]
    assert report['page_content_coverage']['completeness_verified'] is False
    assert report['status']=='partial'  # no original solution must remain visible
    assert [b.block_id for b in raw.blocks]==['q1','q3','continuation']
    assert candidate_coverage(raw,reviewed)['unaccounted']==0
    reviewed.source_metadata['review_origin_source_id']=origin
    result, sid, _ = store.create(ExtractedExerciseText('', 'zip', canonical_book=reviewed),book_name=raw.book_name)
    proposals=project_units(result.units,result.source_blocks,result.canonical_hash,dict(source_mode='file',chapter='',page_start=None,page_end=None),source_id=sid)
    assert len(proposals)==3
    added=next(p for p in proposals if '根据图A' in p['question_text'])
    assert not added['answer'] and not added['explanation']
    dep=next(d for d in added['projection']['dependencies'] if d['kind']=='figure')
    assert dep['resolution']=='embedded'
    path, mime=store.asset(sid,dep['asset_ids'][0],raw.book_name)
    assert path.is_file() and mime=='image/png'
    assert any(b['attributes'].get('visual_source',{}).get('page')==1 for b in result.source_blocks)
    again=store.load(store.rebuild(sid,raw.book_name),raw.book_name)
    assert len(again.units)==3
    # Re-running the same original replays durable requests without a second paid call.
    rerun, report2=run_semantic_review(raw,directory=tmp_path/'review',resolved=resolved,purpose='exercises',
        pdf_path=pdf,asset_root=store.root/'assets',complete=lambda *a,**k:pytest.fail('must reuse receipt'))
    assert report2['reused_calls']==1 and len(rerun.blocks)==len(reviewed.blocks)


def test_insert_scope_invalid_owner_and_unknown_region_are_local(tmp_path):
    book=source(); aliases={'b0':'q1','b1':'q3'}
    response=dict(additions=[
        dict(local_id='n1',page=2,image_ref='original-page:2',type='paragraph',text='伪来源',unit_start=True),
        dict(local_id='n2',page=1,image_ref='original-page:1',type='paragraph',text='2. 未定位的完整题目。',unit_start=True),
        dict(local_id='n3',page=1,image_ref='original-page:1',type='paragraph',text='漏选项',unit_id='not-supplied'),
    ])
    inserted,pending=apply_additions(book,response,aliases,[1],[1])
    assert [r['block_id'] for r in inserted]==['visual-p1-n2']
    assert len(pending)==4 and book.blocks[-2].attributes['visual_source']['bbox'] is None
    assert '伪来源' not in '\n'.join(b.text for b in book.blocks)
    no_image=source()
    assert not apply_additions(no_image,dict(additions=[response['additions'][1]]),{'b0':'q1'},[1],[])[0]
    assert len(no_image.blocks)==3


def test_packages_keep_full_page_excluded_observations_and_context(tmp_path):
    book=source()
    book.blocks.append(DocumentBlock('q4','paragraph','4. 计算定积分。',['习题'],page_start=3,page_end=3))
    book.source_page_count=3
    assert page_packages(book)==[[1,2],[3]]
    content, aliases, _, coverage=page_input(book,[1,2],pdf_path=original_pdf(tmp_path))
    data=json.loads(content[0]['text'])
    assert data['context_blocks'][0]['text']=='4. 计算定积分。'
    assert coverage['full_page_images']==[1,2] and aliases['b3']=='q4'
    plan=semantic_review_plan(book,'exercises',has_original_pages=True)
    assert plan['mode']=='page_visual' and plan['page_packages']==[[1,2],[3]]


@pytest.mark.parametrize('response', [dict(additions={}),dict(additions=[dict(local_id='n1',text=None)]),
    dict(page_inventory=[dict(page=1,questions=[dict(start_id='b0',source_ids='b0')])])])
def test_invalid_page_response_keeps_failed_receipt_contract(response):
    with pytest.raises(ValueError): validate_review_response(response)


def test_missing_page_and_page_local_failure_retain_successful_insertions(tmp_path):
    book=CanonicalBook('习题','mineru',[], 'fixture', source_page_count=2)
    class Session:
        def call(self,key,system,content,**kw):
            data=json.loads(content[0]['text']);page=data['review_pages'][0]
            if page==2:raise ValueError('预算已用尽')
            return dict(additions=[dict(local_id='n1',page=1,image_ref='original-page:1',type='paragraph',
                text='1. 原页完全漏识的题目。',unit_start=True,bbox=[.1,.1,.9,.3])],
                page_inventory=[inventory(1,[('n1',['n1'])])])
        def report(self):return dict(calls=2)
    reviewed,report=run_semantic_review(book,directory=tmp_path,resolved=None,purpose='exercises',
        session=Session(),pdf_path=original_pdf(tmp_path))
    assert report['needs_retry'] and report['source_additions']==1
    assert next(b for b in reviewed.blocks if b.block_id=='visual-p1-n1').text=='1. 原页完全漏识的题目。'
    assert report['source_page_coverage']==[dict(page=1,status='recovered'),dict(page=2,status='missing')]
    assert report['page_content_coverage']['reviewed_pages']==[1]
