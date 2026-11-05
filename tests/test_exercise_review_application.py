"""Apply model decisions without inventing questions or losing exclusion provenance."""
from copy import deepcopy

from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore, file_book
from backend.services.exercise_review_coverage import candidate_coverage
from backend.services.import_semantic_review import _structure
from ingestion.document_ir import CanonicalBook, DocumentBlock
from ingestion.document_structure import apply_structure_review
from memory.exercise_file_importer import ExtractedExerciseText
from memory.exercise_structure import exercise_units


def source():
    return CanonicalBook('习题', 'mineru', [
        DocumentBlock('q1','paragraph','1. 求函数在原点的导数。',['第一章','习题'],page_start=1,source_kind='mineru'),
        DocumentBlock('q2','paragraph','2. 求给定矩阵的秩。',['第一章','习题'],page_start=1,source_kind='mineru'),
    ], 'fixture')


def units(book):
    return exercise_units(file_book(ExtractedExerciseText('', 'zip', canonical_book=book),name=book.book_name),unrestricted=True)


def test_context_cannot_start_questions_and_legacy_rebuild_keeps_real_questions(tmp_path):
    book=source()
    context=DocumentBlock('context','paragraph','3.4 温控器的工作原理。',['第一章'],page_start=1,source_kind='mineru',
        attributes=dict(structure_role='body',structure_unit_start=True,structure_unit_id='context',structure_unit_role='context'))
    book.blocks.insert(0,context)
    assert len(units(book))==2  # old saved source is safe even before reapplying decisions
    reviewed=apply_structure_review(book,[dict(block_id='context',role='body',unit_start=True,unit_id='context',unit_role='context')],recover=False)
    assert reviewed.blocks[0].attributes['structure_unit_start'] is False
    assert 'structure_unit_id' not in reviewed.blocks[0].attributes
    assert reviewed.blocks[0].text==context.text and context.attributes['structure_unit_start'] is True
    stored,sid,_=ExerciseFileAnalysisStore(tmp_path).create(ExtractedExerciseText('', 'zip', canonical_book=reviewed),book_name=book.book_name)
    assert len(stored.units)==2 and all(u['text'].strip() for u in stored.units)


def test_context_split_preserves_source_without_creating_an_empty_question():
    book=source();block=book.blocks[0];block.text='题头与出处\n1. 求函数在原点的导数。'
    boundary=block.text.index('1.')
    reviewed=apply_structure_review(book,[dict(block_id='q1',segments=[
        dict(start=0,end=boundary,role='body',unit_role='context',unit_start=True,unit_id='q1'),
        dict(start=boundary,end=len(block.text),role='exercise',unit_role='question',unit_start=True),
    ])],recover=False)
    assert ''.join(b.text for b in reviewed.blocks[:2])==block.text
    assert len(units(reviewed))==2
    assert reviewed.blocks[0].attributes['structure_unit_start'] is False
    assert reviewed.blocks[0].attributes['structure_unit_id']==reviewed.blocks[1].block_id
    assert '题头与出处' in units(reviewed)[0]['text']


def test_exclusion_without_explanation_has_a_factual_receipt_but_raw_loss_still_blocks():
    original=source()
    response=dict(blocks=[dict(block_id='b0',role='annotation')])
    context=dict(kind='semantic_review',request_key='pages7:3',original_page_images=[1])
    reviewed=_structure(original,response,{'b0':'q1'},recover=False,review_context=context)
    block=reviewed.blocks[0];receipt=block.attributes['structure_review_receipt']
    assert receipt['reason_origin']=='classification' and '未提供详细理由' in receipt['reason']
    assert receipt['block_id']=='q1' and receipt['page']==1 and receipt['previous_role']=='exercise'
    assert receipt['review_context']==context and receipt['decision']['role']=='annotation'
    assert block.text==original.blocks[0].text
    accounted=candidate_coverage(original,reviewed)
    assert (accounted['after'],accounted['removed'],accounted['unaccounted'])==(1,1,0)
    assert accounted['changes'][0]['reason']=='excluded_source'
    raw_loss=deepcopy(original);raw_loss.blocks[0].attributes['structure_role']='annotation'
    assert candidate_coverage(original,raw_loss)['unaccounted']==1


def test_explicit_exclusion_reason_is_preserved_exactly():
    reviewed=apply_structure_review(source(),[dict(block_id='q1',role='annotation',reason='原页是透印，不是题目')],recover=False)
    receipt=reviewed.blocks[0].attributes['structure_review_receipt']
    assert receipt['reason_origin']=='provided' and receipt['reason']=='原页是透印，不是题目'


def test_ocr_quarantine_does_not_demote_an_existing_question_to_context():
    from backend.services.import_semantic_review import _prepare_roles
    book=source();book.blocks[0].attributes['ocr_quality_pending']='公式仍需核对'
    reviewed=_prepare_roles(book)
    assert len(units(reviewed))==2
    assert candidate_coverage(book,reviewed)['unaccounted']==0
    assert reviewed.blocks[0].attributes['ocr_quality_pending']=='公式仍需核对'
    assert reviewed.blocks[0].attributes.get('structure_unit_role')!='context'


def test_visual_types_are_normalized_to_semantic_roles_without_changing_source_types():
    book=source()
    book.blocks.extend([
        DocumentBlock('body','paragraph','温度开关的正文。',['第一章'],page_start=1,attributes=dict(structure_role='body')),
        DocumentBlock('reference','figure','正文图',['第一章'],page_start=1),
        DocumentBlock('question_figure','figure','图1.1',['第一章','习题'],page_start=1),
    ])
    response=dict(blocks=[dict(block_id='r',role='figure',unit_id='body',unit_role='figure'),
        dict(block_id='f',role='figure',unit_id='q1',unit_role='question'),
        dict(block_id='q2',role='exercise',unit_role='figure')])
    reviewed=_structure(book,response,{b.block_id:b.block_id for b in book.blocks}|{'r':'reference','f':'question_figure'},recover=False)
    by_id={b.block_id:b for b in reviewed.blocks}
    assert by_id['reference'].attributes['structure_role']=='body'
    assert by_id['reference'].attributes['structure_unit_role']=='context'
    assert by_id['question_figure'].attributes['structure_role']=='exercise'
    assert by_id['question_figure'].attributes['structure_unit_id']=='q1'
    assert by_id['question_figure'].block_type=='figure'
    assert by_id['question_figure'].attributes['structure_review_receipt']['requested_role']=='figure'
    assert 'structure_unit_role' not in by_id['q2'].attributes
    assert any('来源类型不符' in v.get('reason','') for v in response['unresolved'])
    projected=units(reviewed)
    assert len(projected)==2 and '图1.1' in projected[0]['text'] and '正文图' not in projected[0]['text']
