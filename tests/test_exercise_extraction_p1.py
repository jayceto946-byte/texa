"""Regression cases for the five extraction P1 findings, using synthetic sources only."""
from copy import deepcopy
from io import BytesIO
import json
import zipfile

import fitz
import pytest
from PIL import Image

from ingestion.document_ir import CanonicalBook,DocumentBlock
from memory.exercise_file_importer import extract_docx_text,_extract_pdf_text_layer,ExtractedExerciseText
from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
from backend.services.import_semantic_review import _pair
from backend.services.exercise_page_recovery import recover_pages
from backend.services.exercise_candidate_review import ExerciseCandidateReviewService,CandidateAdmissionError
from memory.exercise_candidate_projection import project_units,content_hash


def test_word_math_tables_and_images_survive_source_snapshot(tmp_path):
    w='http://schemas.openxmlformats.org/wordprocessingml/2006/main';m='http://schemas.openxmlformats.org/officeDocument/2006/math'
    r='http://schemas.openxmlformats.org/officeDocument/2006/relationships';a='http://schemas.openxmlformats.org/drawingml/2006/main'
    xml=f'''<w:document xmlns:w="{w}" xmlns:m="{m}" xmlns:r="{r}" xmlns:a="{a}"><w:body>
    <w:p><w:r><w:t>1. 计算下列表达式并参考配图。</w:t></w:r><m:oMath><m:f><m:num><m:r><m:t>1</m:t></m:r></m:num><m:den><m:r><m:t>2</m:t></m:r></m:den></m:f><m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup><m:m><m:mr><m:e><m:r><m:t>a</m:t></m:r></m:e><m:e><m:r><m:t>b</m:t></m:r></m:e></m:mr><m:mr><m:e><m:r><m:t>c</m:t></m:r></m:e><m:e><m:r><m:t>d</m:t></m:r></m:e></m:mr></m:m></m:oMath><w:r><w:drawing><a:blip r:embed="rId1"/></w:drawing></w:r></w:p>
    <w:tbl><w:tr><w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr><w:p><w:r><w:t>合并表头</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>甲</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>乙</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'''
    image=BytesIO();Image.new('RGB',(40,40),'white').save(image,format='PNG')
    path=tmp_path/'source.docx'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('word/document.xml',xml)
        z.writestr('word/_rels/document.xml.rels',f'<Relationships><Relationship Id="rId1" Target="media/diagram.png"/></Relationships>')
        z.writestr('word/media/diagram.png',image.getvalue())
    parsed=extract_docx_text(path)
    assert r'\frac{1}{2}' in parsed.text and '{x}^{2}' in parsed.text
    assert r'\begin{matrix}a & b \\ c & d\end{matrix}' in parsed.text
    assert len({b.block_id for b in parsed.canonical_book.blocks})==len(parsed.canonical_book.blocks)
    table=next(b for b in parsed.canonical_book.blocks if b.block_type=='table')
    assert table.table_header==['合并表头','合并表头'] and table.table_rows==[['甲','乙']]
    store=ExerciseFileAnalysisStore(tmp_path/'progress');e,sid,_=store.create(parsed,book_name='fixture')
    figure=next(b for b in e.source_blocks if b['block_type']=='figure')
    asset,mime=store.asset(sid,figure['attributes']['asset_id'],'fixture')
    assert asset.is_file() and mime=='image/png'
    from backend.services.import_semantic_review import _text_input
    content,_,_= _text_input(parsed.canonical_book,parsed.canonical_book.blocks,asset_root=parsed.asset_root)
    assert any(x['type']=='image_url' for x in content)


def test_unsupported_word_math_is_visible_and_original_xml_retained(tmp_path):
    path=tmp_path/'unsupported.docx'
    with zipfile.ZipFile(path,'w') as z:z.writestr('word/document.xml','''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><w:body><w:p><w:r><w:t>1. 计算这个表达式。</w:t></w:r><m:oMath><m:unknown><m:t>12</m:t></m:unknown></m:oMath></w:p></w:body></w:document>''')
    parsed=extract_docx_text(path)
    assert '[Word公式待识别]' in parsed.text and parsed.warnings
    assert parsed.canonical_book.blocks[0].attributes['original_word_xml']


def test_empty_pdf_page_is_preserved_and_can_be_recovered_from_original(tmp_path):
    pdf=tmp_path/'mixed.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((40,40),'1. Read the next physical page.')
        doc.new_page()
        doc.save(pdf)
    parsed=_extract_pdf_text_layer(pdf)
    assert parsed.canonical_book.source_metadata['source_page_coverage']==[dict(page=1,status='parsed'),dict(page=2,status='missing')]
    assert any(b.attributes.get('missing_source_page') and b.page_start==2 for b in parsed.canonical_book.blocks)
    class Session:
        def call(self,key,system,content,**kw):
            assert key=='recover_page:2' and any(x['type']=='image_url' for x in content)
            return dict(page=2,status='transcribed',page_blocks=[dict(type='paragraph',text='2. 求函数 $x^2$ 的导数。',unit_start=True,unit_role='question')])
    reviewed,pending,interrupted=recover_pages(parsed.canonical_book,Session(),lambda *a:None,pdf_path=pdf,asset_root=tmp_path/'assets')
    assert not pending and not interrupted
    assert reviewed.source_metadata['source_page_coverage'][1]['status']=='recovered'
    assert parsed.canonical_book.source_metadata['source_page_coverage'][1]['status']=='missing'
    store=ExerciseFileAnalysisStore(tmp_path/'progress')
    e,_,_=store.create(ExtractedExerciseText('source','pdf',canonical_book=reviewed),book_name='fixture')
    assert len(e.units)==2 and any('求函数' in u['text'] for u in e.units)
    _,pending,_=recover_pages(parsed.canonical_book,Session(),lambda *a:None)
    assert pending[0]['page']==2 and '缺少' in pending[0]['reason']
    from ingestion.source_page_coverage import mark_page_coverage
    selected=deepcopy(parsed.canonical_book);selected.blocks=[b for b in selected.blocks if b.page_start==1]
    selected.source_metadata['selected_source_pages']=[1]
    assert mark_page_coverage(selected).source_metadata['source_page_coverage']==[dict(page=1,status='parsed')]


def test_pdf_two_columns_keep_complete_left_column_before_right(tmp_path):
    pdf=tmp_path/'columns.pdf'
    with fitz.open() as doc:
        page=doc.new_page()
        for text,x,y in [('Left first.',40,100),('Right first.',340,100),('Left continuation.',40,180),('Right continuation.',340,180)]:page.insert_text((x,y),text)
        doc.save(pdf)
    parsed=_extract_pdf_text_layer(pdf)
    assert [b.text.strip() for b in parsed.canonical_book.blocks]==['Left first.','Left continuation.','Right first.','Right continuation.']


def test_opposite_conditions_and_long_tail_are_never_hidden_as_duplicates():
    class NoCall:
        def call(self,*a,**k):pytest.fail('Different complete source conditions must not become a duplicate task')
    for left,right in [('x^2+y^2=1','x^2-y^2=1'),('x<y','x>y'),('1 2','12')]:
        stem=''.join(f'共同条件第{j}项保持原始内容。' for j in range(300))
        book=CanonicalBook('fixture','fixture',[DocumentBlock('a','paragraph','1. '+stem+left,['第一章']),DocumentBlock('b','paragraph','2. '+stem+right,['第一章'])],'fixture')
        reviewed,report=_pair(book,NoCall(),lambda *a:None)
        assert report['merged_questions']==0 and len(reviewed.blocks)==2


def test_pairing_uses_full_solutions_and_batches_repeated_questions():
    rows=[]
    for i in range(8):
        rows.extend([DocumentBlock(f'q{i}','paragraph',f'{i+1}. '+(''.join(f'附加条件第{j}条保持原始信息。' for j in range(300)))+'最后条件 $x>0$。',['第一章']),
                     DocumentBlock(f'a{i}','paragraph','解：'+('完整原解。'*100)+'原解尾部。',['第一章'])])
    class Session:
        calls=[]
        def call(self,key,system,content,**kw):
            payload=json.loads(content);self.calls.append(payload)
            assert len(content)<=30000 and payload['coverage']=='complete_source_text'
            assert all(u['question'].endswith('$x>0$。') and u['explanation'].endswith('原解尾部。') for u in payload['units'])
            ids=[u['id'] for u in payload['units']]
            return dict(groups=[dict(keep=ids[0],merge=ids[1:])])
    session=Session();_,report=_pair(CanonicalBook('fixture','fixture',rows,'fixture'),session,lambda *a:None)
    assert len(session.calls)>1 and report['merged_questions']==7


def split_fixture(tmp_path):
    store=ExerciseFileAnalysisStore(tmp_path)
    e,sid,_=store.create(ExtractedExerciseText('1. 第一问计算给定条件的结果。\n第二问计算另一个给定条件的结果。\n答案：原书给出的结果。','docx'),book_name='fixture')
    scope=dict(chapter='',page_start=None,page_end=None,source_mode='file')
    p=project_units(e.units,e.source_blocks,e.canonical_hash,scope,profile_version=e.profile_version,source_id=sid)[0]
    plans=[{r:[] for r in p['projection']['parts']} for _ in range(2)]
    question=p['projection']['parts']['question'];assert len(question)==2
    plans[0]['question']=[question[0]];plans[1]['question']=[question[1]]
    for role in ('answer','explanation','context','unassigned'):plans[1][role]=deepcopy(p['projection']['parts'][role])
    return store,e,p,plans


def split_item(p,plans,index):
    projection=deepcopy(p['projection']);projection.update(method='user_edited',parts=plans[index],split=dict(group_id='split-fixture',index=index,siblings=plans,shared_block_ids=[]))
    item=dict(origin_id=f'child-{index}',question_text='第一道完整的题目。' if index==0 else '第二道完整的题目。',answer='' if index==0 else p['answer'],explanation='',candidate_context=dict(projection=projection))
    resolutions=[dict(issue_key='edited_content:',decision='corrected')]+[dict(issue_key=i['key'],decision='source_checked') for i in p['issues'] if i['category']=='content']
    item['candidate_context']['review']=dict(content_hash=content_hash({**item,'projection':projection}),resolutions=resolutions)
    return item


def test_split_admission_preserves_nonoverlapping_source_ranges_and_receipt(tmp_path):
    from backend.exercise_candidate_schemas import CandidateContext
    store,e,p,plans=split_fixture(tmp_path)
    items=[split_item(p,plans,i) for i in range(2)]
    for item in items:item['candidate_context']=CandidateContext(**item['candidate_context']).model_dump()
    receipts=ExerciseCandidateReviewService(file_provider=store.load).prepare('fixture',items)
    assert len(receipts)==2 and receipts[0]['projection']['parts']!=receipts[1]['projection']['parts']
    assert receipts[1]['projection']['split']['index']==1
    assert receipts[0]['projection']['parts']['answer']==[]
    # The complete split plan makes admission valid even when a sibling is saved later.
    assert len(ExerciseCandidateReviewService(file_provider=store.load).prepare('fixture',[items[1]]))==1


def test_overlapping_or_missing_split_source_is_rejected(tmp_path):
    store,e,p,plans=split_fixture(tmp_path)
    plans[1]['question']=deepcopy(plans[0]['question'])
    with pytest.raises(CandidateAdmissionError,match='覆盖|重叠'):ExerciseCandidateReviewService(file_provider=store.load).prepare('fixture',[split_item(p,plans,0)])
    # Old copy-whole-source children cannot be admitted as separate source partitions.
    base=deepcopy(p['projection']);base['method']='user_edited'
    items=[]
    for i in range(2):
        item=split_item(p,plans,i);item['candidate_context']['projection']=deepcopy(base)
        item['candidate_context']['review']['content_hash']=content_hash({**item,'projection':base});items.append(item)
    with pytest.raises(CandidateAdmissionError,match='重复占用'):ExerciseCandidateReviewService(file_provider=store.load).prepare('fixture',items)
