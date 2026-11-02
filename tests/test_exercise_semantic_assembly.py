"""Raw MinerU labels are hints; review owns question assembly and source metadata."""
import json
from types import SimpleNamespace

import pytest

from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
from backend.services.exercise_candidate_review import ExerciseCandidateReviewService
from backend.services.exercise_review_coverage import candidate_coverage
from backend.services.import_semantic_review import _metadata, _structure, run_semantic_review
from ingestion.document_ir import CanonicalBook,DocumentBlock
from llm.configuration import resolve_model_role
from memory.exercise_candidate_projection import content_hash
from memory.exercise_file_importer import ExtractedExerciseText
from memory.textbook_exercise_importer import analyze_learning_unit_candidates


def block(bid,text,kind='paragraph',page=1):
    return DocumentBlock(bid,kind,text,['第一章'],page_start=page,page_end=page,source_kind='mineru')


def source(rows):
    return CanonicalBook('fixture','fixture',rows,'fixture',source_page_count=max(b.page_end or b.page_start or 0 for b in rows))


def review(book,tmp_path,reply):
    resolved=resolve_model_role('vision',dict(LLM_VISION_PROVIDER='deepseek',LLM_VISION_MODEL='deepseek-flash',LLM_VISION_API_KEY='fixture'))
    sent=[]
    def complete(*args,**kwargs):
        data=json.loads(kwargs['messages'][1]['content'][0]['text']);sent.append(data)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(reply(data),ensure_ascii=False)))],usage=dict(prompt_tokens=100,completion_tokens=20))
    reviewed,report=run_semantic_review(book,directory=tmp_path/'review',resolved=resolved,purpose='exercises',complete=complete)
    return reviewed,report,sent


def proposals(book,tmp_path):
    store=ExerciseFileAnalysisStore(tmp_path)
    extracted,sid,_=store.create(ExtractedExerciseText('','zip',canonical_book=book),book_name='fixture')
    candidates=analyze_learning_unit_candidates(extracted.units,book_name='fixture',subject='',limit=len(extracted.units),
        source_blocks=extracted.source_blocks,canonical_hash=extracted.canonical_hash,scope=dict(chapter='',page_start=None,page_end=None,source_mode='file'),
        profile_version=extracted.profile_version,source_id=sid)
    return candidates,store,sid


@pytest.mark.parametrize('metadata_kind',['heading','paragraph','formula'])
def test_semantic_assembly_ignores_mineru_labels_and_saves_metadata(tmp_path,metadata_kind):
    book=source([block('exam','2008年数学一',metadata_kind),block('focus','考点：导数定义',metadata_kind),
                 block('q','设函数 $f(x)=x^2$ 在实数域有定义。','heading'),
                 block('tail','求函数在原点的导数，并说明理由。','heading',page=2)])
    def reply(data):
        ids={b['text']:b['id'] for b in data['blocks']}
        q=ids[book.blocks[2].text]
        return dict(blocks=[dict(block_id=q,unit_start=True,unit_role='question'),
            *[dict(block_id=ids[b.text],unit_id=q,unit_role='context' if b.block_id in {'exam','focus'} else 'question',reason='同一道题的来源、考点或跨页续文') for b in book.blocks if b.block_id!='q']],
            metadata=[dict(block_id=q,exam_year='2008',exam_source='2008年数学一',authored_focus='导数定义',
                evidence=[dict(block_id=ids[book.blocks[i].text],quote=book.blocks[i].text) for i in (0,1)])])
    reviewed,report,sent=review(book,tmp_path,reply)
    assert sent[0]['blocks'][0]['type']==metadata_kind
    assert len(sent[0]['blocks'])==4 and not report['unresolved']
    assert report['metadata_updates']==3
    candidates,store,_=proposals(reviewed,tmp_path)
    assert len(candidates)==1
    c=candidates[0]
    assert c.question_text==book.blocks[2].text+'\n\n'+book.blocks[3].text
    assert '2008' not in c.question_text and '考点' not in c.question_text
    assert c.projection['structure']['authored_focus']=='导数定义'
    assert c.projection['structure']['exam_source']=='2008年数学一'
    assert c.projection['structure']['exam_year']=='2008'
    context=dict(projection=c.projection,review=dict(content_hash=content_hash(c.to_dict()),
        resolutions=[dict(issue_key=i['key'],decision='source_checked') for i in c.issues if i['category']=='content']))
    result=ExerciseCandidateReviewService(file_provider=store.load).prepare('fixture',[dict(origin_id=c.id,
        question_text=c.question_text,answer=c.answer,explanation=c.explanation,candidate_context=context)])[0]
    assert result['projection']['structure']['authored_focus']=='导数定义'
    assert all('structure_unit_role' not in b.attributes for b in book.blocks)


def test_reassigning_false_questions_is_accounted_without_deduplication(tmp_path):
    book=source([block('meta','1. 来源：2008年数学一'),block('q','2. 设函数在原点可导，求导数。'),
                 block('tail','3. 并利用定义证明结论。',page=2)])
    response=dict(blocks=[dict(block_id='q',unit_start=True,unit_role='question'),
        dict(block_id='meta',unit_id='q',unit_role='context',reason='误拆的来源栏，归回题目'),
        dict(block_id='tail',unit_id='q',unit_role='question',reason='这是同一题的第二个要求')])
    reviewed=_structure(book,response,{b.block_id:b.block_id for b in book.blocks},recover=False)
    coverage=candidate_coverage(book,reviewed)
    assert (coverage['before'],coverage['after'],coverage['removed'],coverage['unaccounted'])==(3,1,2,0)
    assert {v['reason'] for v in coverage['changes']}=={'reassembled_source'}
    c=proposals(reviewed,tmp_path)[0][0]
    assert '利用定义' in c.question_text and '2008' not in c.question_text
    assert len(reviewed.blocks)==3 and not any(b.attributes.get('structure_duplicate_of') for b in reviewed.blocks)


def test_same_raw_heading_splits_two_questions_and_binds_metadata_independently(tmp_path):
    book=source([block('raw','来源：2008年数学一\n第一题 求 $x^2$ 的导数。\n来源：2020年数学二\n第二题 求函数的导娄。\n解：由定义计算。','heading'),
                 block('focus','考点：导数定义','formula')])
    first='第一题 求 $x^2$ 的导数。';second='第二题 求函数的导娄。'
    def reply(data):
        raw=next(b['id'] for b in data['blocks'] if b['text'].startswith('来源：2008'))
        focus=next(b['id'] for b in data['blocks'] if b['text'].startswith('考点'))
        return dict(splits=[dict(block_id=raw,segments=[
            dict(starts_with='来源：2008年数学一',unit_role='context',unit_id=raw,unit_starts_with=first),
            dict(starts_with=first,unit_role='question',unit_start=True),
            dict(starts_with='来源：2020年数学二',unit_role='context',unit_id=raw,unit_starts_with=second),
            dict(starts_with=second,unit_role='question',unit_start=True),
            dict(starts_with='解：由定义计算。',unit_role='explanation',unit_id=raw,unit_starts_with=second)])],
            blocks=[dict(block_id=focus,unit_id=raw,unit_starts_with=second,unit_role='context',reason='第二题的原书考点')],
            edits=[dict(block_id=raw,find='导娄',replace='导数',reason='OCR错字')],
            metadata=[dict(block_id=raw,question_starts_with=first,exam_year='2008',exam_source='2008年数学一',evidence=[dict(block_id=raw,quote='2008年数学一')]),
                      dict(block_id=raw,question_starts_with=second,exam_year='2020',exam_source='2020年数学二',authored_focus='导数定义',
                        evidence=[dict(block_id=raw,quote='2020年数学二'),dict(block_id=focus,quote='导数定义')])])
    reviewed,report,_=review(book,tmp_path,reply)
    assert not report['unresolved'] and report['text_corrections']==1
    candidates,_,_=proposals(reviewed,tmp_path)
    assert len(candidates)==2
    a,b=candidates
    assert a.projection['structure']['exam_year']=='2008' and b.projection['structure']['exam_year']=='2020'
    assert a.projection['structure']['authored_focus']=='' and b.projection['structure']['authored_focus']=='导数定义'
    assert '导娄' not in b.question_text and '导数' in b.question_text
    assert '来源' not in a.question_text+b.question_text and not a.explanation and '由定义计算' in b.explanation
    assert ''.join(v.text for v in reviewed.blocks if v.attributes.get('source_parent_id')=='raw')==book.blocks[0].text.replace('导娄','导数')
    assert '导娄' in book.blocks[0].text


def test_metadata_updates_keep_existing_fields_and_require_provided_evidence(tmp_path):
    book=source([block('q','1. 计算导数。'),block('e','2008年数学一；考点：导数定义')])
    aliases={b.block_id:b.block_id for b in book.blocks};pending=[]
    _metadata(book,dict(metadata=[dict(block_id='q',exam_year='2008',exam_source='2008年数学一',evidence=[dict(block_id='e',quote='2008年数学一')])]),aliases,{'q'},pending)
    _metadata(book,dict(metadata=[dict(block_id='q',authored_focus='导数定义',evidence=[dict(block_id='e',quote='导数定义')])]),aliases,{'q'},pending)
    assert book.blocks[0].attributes['exercise_metadata']['exam_year']=='2008' and not pending
    _metadata(book,dict(metadata=[dict(block_id='q',authored_focus='导数定义',evidence=[dict(block_id='e',quote='导数定义')])]),aliases,{'e'},pending)
    assert not pending  # current-page metadata can belong to the previous context question
    _metadata(book,dict(metadata=[dict(block_id='q',authored_focus='伪造考点',evidence=[dict(block_id='e',quote='原文不存在')])]),aliases,{'q'},pending)
    assert pending and book.blocks[0].attributes['exercise_metadata']['authored_focus']=='导数定义'
    _metadata(book,dict(metadata=[dict(block_id='q',exam_year='',exam_source='',evidence=[dict(block_id='e',quote='2008年数学一')])]),aliases,{'q'},pending)
    c=proposals(book,tmp_path)[0][0]
    assert c.projection['structure']['exam_year']==c.projection['structure']['exam_source']==''
    _metadata(book,dict(metadata=[dict(block_id='q',exam_year='2008',evidence=[dict(block_id='not-in-input',quote='2008年数学一')])]),aliases,{'q'},pending)
    assert book.blocks[0].attributes['exercise_metadata']['exam_year']==''


def test_metadata_evidence_follows_real_lines_after_projection(tmp_path):
    book=source([block('meta','来源：2008年数学一\n考点：导数定义'),block('q','1. 计算函数的导数。')])
    book.blocks[1].attributes['exercise_metadata']=dict(exam_year='2008',authored_focus='导数定义',
        evidence=[dict(block_id='meta',quote='2008年数学一\n考点：导数定义')])
    candidates,store,sid=proposals(book,tmp_path)
    c=candidates[0]
    registry={b['block_id']:b for b in store.load(sid,'fixture').source_blocks}
    evidence=next(b for b in registry.values() if b['attributes'].get('exercise_metadata'))['attributes']['exercise_metadata']['evidence']
    assert len(evidence)==2
    assert all(e['quote'] in registry[e['block_id']]['text'] for e in evidence)
    assert {e['block_id'] for e in evidence}<={s['block_id'] for s in c.projection['parts']['context']}


@pytest.mark.parametrize('label,metadata',[
    ('（2008*17题）',dict(exam_year='2008',exam_source='（2008*17题）',original_number='17',authored_focus='')),
    ('2008·数二·多重积分',dict(exam_year='2008',exam_source='2008·数二',authored_focus='多重积分')),
])
def test_unlabelled_source_formats_are_semantic_inputs_not_rule_filters(tmp_path,label,metadata):
    from memory.exercise_structure import question_metadata
    book=source([block('label',label,'heading'),block('q','1. 设连续函数满足已知条件，计算其积分。')])
    assert question_metadata(label)['exam_year']==''
    def reply(data):
        ids={b['text']:b['id'] for b in data['blocks']};q=ids[book.blocks[1].text]
        return dict(blocks=[dict(block_id=q,unit_start=True,unit_role='question'),
            dict(block_id=ids[label],unit_id=q,unit_role='context',reason='无固定标签的题头资料')],
            metadata=[dict(block_id=q,**metadata,evidence=[dict(block_id=ids[label],quote=label)])])
    reviewed,report,sent=review(book,tmp_path,reply)
    assert any(b['text']==label for b in sent[0]['blocks']) and not report['unresolved']
    c=proposals(reviewed,tmp_path)[0][0]
    assert all(c.projection['structure'][key]==value for key,value in metadata.items())
    assert label not in c.question_text
