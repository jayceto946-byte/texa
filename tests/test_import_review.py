from pathlib import Path
from types import SimpleNamespace

from backend.job_manager import JobManager
from backend.services.book_import_review import save_import_draft, preview_import_draft, start_confirmation
from ingestion.document_ir import persist_canonical_book
from ingestion.mineru_importer import BookImportResult
from test_outline_editing import source


def test_parse_only_and_review_do_not_publish_a_book_or_open_a_vector_store(monkeypatch, tmp_path):
    from ingestion import mineru_importer
    from ingestion.document_adapters import MinerUAdapter
    book = source()
    monkeypatch.setattr(MinerUAdapter,'from_output_dir',lambda *a,**k:book)
    def no_store():
        raise AssertionError('确认前不得打开向量库')
    monkeypatch.setattr(mineru_importer,'get_vector_store',no_store)
    output=tmp_path/'output'; output.mkdir()
    parsed=mineru_importer.import_textbook_from_mineru_output(output,book.book_name,prepare_only=True)
    assert parsed.indexed_chunks==0
    jobs=JobManager(tmp_path/'jobs.db')
    job=jobs.create_job('book_import',{'book_name':book.book_name},status='running')
    job=save_import_draft(job['id'],parsed,jobs=jobs,progress_root=tmp_path/'progress')
    assert job['status']=='waiting_for_review'
    assert not (tmp_path/book.book_name/'canonical_document.jsonl').exists()
    assert not (tmp_path/book.book_name/'_chapters.json').exists()
    assert jobs.mark_running_interrupted()==0
    candidate,proposal=preview_import_draft(job,progress_root=tmp_path/'progress')
    assert proposal['base_version']==job['id']
    assert candidate.book_name==book.book_name


def test_confirmation_validates_edits_once_and_repeated_requests_share_one_job(monkeypatch,tmp_path):
    from ingestion import index_pipeline
    monkeypatch.setattr(index_pipeline,'VECTOR_DB_PATH',tmp_path/'vector')
    book=source()
    jobs=JobManager(tmp_path/'jobs.db')
    job=jobs.create_job('book_import',{'book_name':book.book_name},status='running')
    output=tmp_path/'output'; output.mkdir()
    save_import_draft(job['id'],BookImportResult(book.book_name,[],False,canonical_book=book,output_dir=str(output)),jobs=jobs,progress_root=tmp_path)
    edit=SimpleNamespace(model_dump=lambda:dict(node_id='new',created=True,title='第二章 方法',level=1,page=3,anchor_block_id='4'))
    request=SimpleNamespace(base_version=job['id'],examples=[],max_depth=2,edits=[edit])
    calls=[]
    def start(job,result):
        calls.append(result)
    a=start_confirmation(job['id'],request,jobs=jobs,progress_root=tmp_path,start_worker=start)
    b=start_confirmation(job['id'],request,jobs=jobs,progress_root=tmp_path,start_worker=start)
    assert a['id']==b['id'] and a['status']=='running' and len(calls)==1
    assert [c['title'] for c in calls[0].chapters]==['第一章 基础','第二章 方法','第三章 应用']


def test_waiting_review_can_be_cancelled_without_a_running_worker(tmp_path):
    jobs=JobManager(tmp_path/'jobs.db')
    job=jobs.create_job('book_import',status='waiting_for_review')
    final=jobs.request_cancel(job['id'])
    assert final['status']=='cancelled' and final['completed_at']
    assert not jobs.claim_job(job['id'],from_statuses=('waiting_for_review',))
    from backend.job_manager import JobCancelled
    import pytest
    running=jobs.create_job('book_import',status='running')
    jobs.request_cancel(running['id'])
    with pytest.raises(JobCancelled):
        jobs.wait_for_review(running['id'],result={},message='review')


def test_source_images_remain_available_after_draft_is_saved(monkeypatch,tmp_path):
    from test_mineru_structured_content import source as image_source
    from ingestion.mineru_importer import import_textbook_from_mineru_output
    from ingestion.document_assets import materialize_document_assets
    output=image_source(tmp_path)
    parsed=import_textbook_from_mineru_output(output,'images',prepare_only=True)
    jobs=JobManager(tmp_path/'jobs.db')
    job=jobs.create_job('book_import',{'book_name':'images'},status='running')
    save_import_draft(job['id'],parsed,jobs=jobs,progress_root=tmp_path/'progress')
    materialize_document_assets(parsed.canonical_book,source_root=Path(parsed.output_dir),progress_root=tmp_path/'candidate')
    figures=[b for b in parsed.canonical_book.blocks if b.block_type=='figure']
    assert figures and all(b.attributes['asset_status']=='ready' for b in figures)
    assert Path(parsed.output_dir,'structured_content.json').exists()
