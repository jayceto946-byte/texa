"""Selection is authoritative; rollback preserves the source and supports reimport."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import exercises
from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
from ingestion.document_ir import CanonicalBook, DocumentBlock
from memory.exercise_bank import ExerciseBank, ExerciseRecord, PracticeSession
from memory.exercise_file_importer import ExtractedExerciseText
from memory.exercise_structure import exercise_units, header_metadata
from memory.exercise_candidate_projection import project_units, source_registry
from memory.exercise_chapters import heading
from memory.textbook_exercise_importer import analyze_learning_unit_candidates


def test_printed_chapter_and_section_are_not_replaced_by_small_focus_or_toc():
    def block(bid, text, page, kind='heading'):
        return DocumentBlock(bid, kind, text, ['default', '误分类的小考点'], page_start=page, page_end=page)
    book = CanonicalBook('default', 'test', [
        block('toc1','一、极限',1),block('toc2','二、导数',1),block('toc3','三、积分',1),
        block('chapter','第六章 微分方程',2),block('section','第六节 齐次方程',2),
        block('focus','考点一 换元法',2),block('q1','#001',2,'paragraph'),block('body1','1. 求方程的通解。',2,'paragraph'),
        block('focus2','考点二 积分因子',3),block('q2','#002',3,'paragraph'),block('body2','2. 求给定初值问题的解。',3,'paragraph'),
    ], 'test')
    units = exercise_units(book, unrestricted=True)
    assert len(units) == 2
    assert all(u['chapter'] == '第六章 微分方程' for u in units)
    assert all(u['classification_path'] == ['第六章 微分方程','第六节 齐次方程'] for u in units)
    proposals = project_units(units, source_registry(book, units, {b.block_id for b in book.blocks}), 'test', {})
    assert [p['projection']['structure']['authored_focus'] for p in proposals] == ['考点一 换元法','考点二 积分因子']
    assert book.blocks[-1].section_path == ['default','误分类的小考点']
    assert header_metadata('#001 函数极限 原稿第23页 · 2018数二 · 难度 0.65 · 建议 4 分钟')['authored_focus'] == '函数极限'
    assert heading('1. 求方程的通解') is None
    assert heading('6.1 可分离变量方程', native=True) == (2, '6.1 可分离变量方程')


def test_explicit_catalogue_ranges_classify_questions_without_inheriting_last_toc():
    rows = [DocumentBlock('table','table','| 章节与题号 |\n| 一·极限 001-002(2)+二·微分 003-003(1) |',['default'],page_start=1)]
    for n in range(1,5):
        rows += [DocumentBlock(f'q{n}','paragraph',f'#{n:03d} 同一个小考点',['default'],page_start=2+n),
                 DocumentBlock(f'b{n}','paragraph',f'{n}. 求给定函数的极限。',['default'],page_start=2+n)]
    units = exercise_units(CanonicalBook('default','test',rows,'test'),unrestricted=True)
    assert [u['chapter'] for u in units] == ['一·极限','一·极限','二·微分','未分章']


def test_selected_occurrences_import_all_then_rollback_and_reimport(tmp_path,monkeypatch):
    bank = ExerciseBank(tmp_path/'bank.db')
    store = ExerciseFileAnalysisStore(tmp_path)
    book = CanonicalBook('default','test',[
        item for n in range(613) for item in [
            DocumentBlock(f'q{n}','paragraph',f'#{n+1:03d} 考点{n%4}',['default'],page_start=n//3+1),
            DocumentBlock(f'b{n}','paragraph',f'({n+1}) 求给定函数在原点的导数。',['default'],page_start=n//3+1)]
    ],'test')
    source,sid,_ = store.create(ExtractedExerciseText('','zip',canonical_book=book),book_name='default')
    candidates = analyze_learning_unit_candidates(source.units,book_name='default',subject='数学',limit=613,
        source_blocks=source.source_blocks,canonical_hash=source.canonical_hash,scope=dict(chapter='',page_start=None,page_end=None,source_mode='file'),source_id=sid)
    for c in candidates[:300]: bank.add(ExerciseRecord(question_text=c.question_text))
    monkeypatch.setattr(exercises,'_bank',lambda name='default':bank)
    monkeypatch.setattr(exercises,'PROGRESS_PATH',tmp_path)
    monkeypatch.setattr(exercises,'_log_learning_event',lambda *a,**kw:None)
    from backend.services import exercise_candidate_review
    original = exercise_candidate_review.ExerciseCandidateReviewService
    monkeypatch.setattr(exercise_candidate_review,'ExerciseCandidateReviewService',lambda **kw:original(file_provider=store.load,**kw))
    app=FastAPI();app.include_router(exercises.router,prefix='/api');client=TestClient(app)
    payload=dict(candidate_contract_version=1,allow_duplicates=True,exercises=[dict(question_text=c.question_text,answer=c.answer,explanation=c.explanation,origin_id=c.id,candidate_context=dict(projection=c.projection,review=c.review,import_confirmed=True)) for c in candidates])
    first=client.post('/api/exercises/candidates/batch-add',json=payload)
    assert first.status_code == 200, first.text
    result=first.json()
    assert result['count'] == 613 and result['skipped'] == []
    assert bank.stats()['total'] == 913
    session=bank.save_practice_session(PracticeSession(exercise_ids=[r['id'] for r in result['data']]))
    rollback=client.post('/api/exercises/import-batches/rollback',json=dict(batch_id=result['batch_id']))
    assert rollback.json()['data']['status'] == 'rolled_back'
    assert bank.stats()['total'] == 300
    assert bank.get_practice_session(session.id).status == 'completed'
    assert len(store.load(sid,'default').units) == 613
    second=client.post('/api/exercises/candidates/batch-add',json=payload)
    assert second.status_code == 200, second.text
    assert second.json()['count'] == 613 and second.json()['skipped'] == []
    assert bank.stats()['total'] == 913
