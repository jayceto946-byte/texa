from io import BytesIO
from types import SimpleNamespace
from fastapi import UploadFile


def test_local_pdf_stays_staged_until_its_outline_is_confirmed(monkeypatch, tmp_path):
    import fitz
    import config
    import backend.api.books as books
    from backend.job_manager import JobManager
    from ingestion import mineru_importer
    monkeypatch.setattr(books,'BOOKS_PATH',tmp_path/'books')
    monkeypatch.setattr(books,'BOOK_UPLOAD_DIR',tmp_path/'uploads')
    monkeypatch.setattr(books,'PROGRESS_PATH',tmp_path/'progress')
    monkeypatch.setattr(books,'_known_book_names',lambda **k:[])
    monkeypatch.setattr(config,'MINERU_OUTPUT_PATH',tmp_path/'mineru')
    jobs=JobManager(tmp_path/'jobs.db');monkeypatch.setattr(books,'_job_manager',jobs)
    def forbidden(*a,**k):
        raise AssertionError('确认目录前不得发布教材或建立索引')
    monkeypatch.setattr(books,'_set_current_book',forbidden)
    monkeypatch.setattr(mineru_importer,'get_vector_store',forbidden)
    class InlineThread:
        def __init__(self,target,args,**kwargs): self.target,self.args=target,args
        def start(self): self.target(*self.args)
    monkeypatch.setattr(books,'threading',SimpleNamespace(Thread=InlineThread))
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((72,72),'Chapter 1 Foundations\nThis is the retained source paragraph.')
        pdf=doc.tobytes()
    result=books.import_book_local(UploadFile(filename='demo.pdf',file=BytesIO(pdf)),toc_pages='',subject='数学',extract_concepts=False)
    job=jobs.get_job(result['job_id'])
    assert job['status']=='waiting_for_review',job
    assert (tmp_path/'uploads/demo.pdf').read_bytes()==pdf
    assert not (tmp_path/'books/demo.pdf').exists()
    assert (tmp_path/'progress/_import_drafts'/job['id']/'demo/canonical_document.jsonl').exists()


def test_failed_confirmation_preserves_pdf_and_parsed_source_for_retry(monkeypatch,tmp_path):
    from backend.services.book_import_review import rollback_failed_confirmation
    from ingestion import index_pipeline
    monkeypatch.setattr(index_pipeline,'load_index_manifest',lambda _:dict(index_version='owned'))
    final=tmp_path/'books/demo.pdf';final.parent.mkdir();final.write_bytes(b'pdf')
    source=tmp_path/'draft/source/structured_content.json';source.parent.mkdir(parents=True);source.write_text('{}')
    staged=tmp_path/'uploads/demo.pdf';cleanup=[]
    rollback_failed_confirmation('demo','owned',cleanup=lambda *args:cleanup.append(args),staged_pdf=staged,final_pdf=final)
    assert staged.read_bytes()==b'pdf' and not final.exists()
    assert source.exists() and cleanup==[('demo',None)]
    rollback_failed_confirmation('demo','someone-else',cleanup=lambda *args:cleanup.append(args))
    assert len(cleanup)==1
