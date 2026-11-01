"""Explicit, bounded model work; no automatic paid calls during import."""
from typing import Literal
from fastapi import APIRouter, HTTPException, File, Form, UploadFile
from pydantic import BaseModel, Field

from backend.job_manager import get_job_manager
from config import PROGRESS_PATH, BOOKS_PATH

router = APIRouter(prefix='/structure-reviews', tags=['structure-review'])


@router.post('/source-pdf')
def associate_source_pdf(kind: Literal['book', 'import', 'file'] = Form(...), reference: str = Form(...),
                         book_name: str = Form(...), file: UploadFile = File(...)):
    import fitz
    from pathlib import Path
    import tempfile
    from backend.services.structure_review_jobs import resolve_source, review_directory
    from ingestion.document_ir import canonical_book_fingerprint
    from utils.resource_limits import copy_stream_limited, MAX_BOOK_PDF_BYTES
    from utils.json_io import atomic_write_json
    temporary = None
    try:
        target = _target(ReviewTarget(kind=kind, reference=reference, book_name=book_name))
        book, _, _ = resolve_source(target, progress_root=PROGRESS_PATH, books_root=BOOKS_PATH, jobs=get_job_manager())
        directory = review_directory(PROGRESS_PATH, kind, reference); directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.pdf', delete=False) as scratch:
            temporary = Path(scratch.name)
        copy_stream_limited(file.file, temporary, max_bytes=MAX_BOOK_PDF_BYTES)
        with fitz.open(temporary) as doc:
            if doc.page_count != book.source_page_count:
                raise ValueError('PDF物理页数与解析来源不一致，请选择对应原始PDF')
        temporary.replace(directory / 'source.pdf'); temporary = None
        atomic_write_json(directory / 'source_pdf.json', dict(source_version=canonical_book_fingerprint(book)))
        return dict(success=True, message='已关联原始PDF，原文件保持不变')
    except (ValueError, OSError) as exc:
        raise HTTPException(422, '无法关联原页：' + str(exc)) from None
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


class ReviewTarget(BaseModel):
    kind: Literal['book', 'import', 'file']
    reference: str = Field(min_length=1, max_length=120)
    book_name: str = Field(min_length=1, max_length=120)
    mode: Literal['suspect', 'all'] = 'suspect'
    max_pages: int = Field(default=24, ge=1, le=1000)
    max_cost_cny: float = Field(default=1, gt=0, le=1000)
    input_price: float | None = Field(default=None, ge=0, le=10000)
    output_price: float | None = Field(default=None, ge=0, le=10000)


def _target(request):
    return request.model_dump(include={'kind', 'reference', 'book_name'})


@router.post('/plan')
def plan_review(request: ReviewTarget):
    from backend.services.structure_review_jobs import resolve_source
    from backend.services.document_structure_review import review_plan
    from config import get_model_role_config
    from llm.factory import ensure_runtime_support
    from llm.types import Capability
    try:
        book, _, pdf = resolve_source(_target(request), progress_root=PROGRESS_PATH, books_root=BOOKS_PATH, jobs=get_job_manager())
        plan = review_plan(book, mode=request.mode, max_pages=request.max_pages)
        resolved = get_model_role_config('vision')
        ensure_runtime_support(resolved, Capability.VISION)
        return dict(success=True, data={**plan, 'model': resolved.model, 'ready': resolved.credential_configured,
                    'has_original_pages': bool(pdf), 'image_scope': '原始PDF页面与区域裁片' if pdf else 'OCR坐标与已有裁片；无完整原页',
                    'notice': '使用已配置的识图服务，所选页和必要邻页会发送给该服务并按用量计费；未审阅页面不视为已核实。'})
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from None


@router.post('')
def create_review(request: ReviewTarget):
    from backend.services.structure_review_jobs import start_review
    try:
        if request.input_price is None or request.output_price is None:
            raise ValueError('请填写所配置服务的输入、输出单价以计算审阅预算')
        job = start_review(_target(request), mode=request.mode, max_pages=request.max_pages,
                           progress_root=PROGRESS_PATH, books_root=BOOKS_PATH, jobs=get_job_manager(),
                           budget=request.model_dump(include={'max_cost_cny', 'input_price', 'output_price'}))
        return dict(success=True, data=job)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from None
