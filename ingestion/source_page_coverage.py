"""Keep missing physical pages visible to source review instead of inferring 'no question'."""
from ingestion.document_ir import DocumentBlock


def mark_page_coverage(book):
    if not book.source_page_count:return book
    selected=book.source_metadata.get('selected_physical_pages') or {}
    start,end=selected.get('start') or 1,selected.get('end') or book.source_page_count
    previous={r['page']:r for r in book.source_metadata.get('source_page_coverage',[])}
    pages={b.page_start for b in book.blocks if b.page_start and b.block_type!='figure' and b.text.strip() and not b.attributes.get('missing_source_page')}
    placeholders={b.page_start for b in book.blocks if b.attributes.get('missing_source_page')}
    coverage=[]
    selected_pages=book.source_metadata.get('selected_source_pages')
    for page in (selected_pages if selected_pages is not None else range(start,end+1)):
        old=previous.get(page,{})
        status=old.get('status') if old.get('status') in {'recovered','blank','unreadable'} else ('parsed' if page in pages else 'missing')
        coverage.append(dict(page=page,status=status))
        if status in {'missing','unreadable'} and page not in placeholders:
            book.blocks.append(DocumentBlock(f'missing-page-{page}','paragraph','[待识别原页]',[book.book_name],page_start=page,page_end=page,
                source_kind='page_coverage',attributes=dict(missing_source_page=True,ocr_quality_pending='本页尚无可用OCR正文')))
    book.source_metadata['source_page_coverage']=coverage
    book.blocks.sort(key=lambda b:b.page_start or 0)
    return book
