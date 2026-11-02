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
    max_cost_cny: float = Field(default=3, gt=0, le=1000)
    purpose: Literal['outline','exercises','textbook'] | None = None
    retry_failed: bool = False
    input_price: float | None = Field(default=None, ge=0, le=10000)
    output_price: float | None = Field(default=None, ge=0, le=10000)


def _target(request):
    return request.model_dump(include={'kind', 'reference', 'book_name'})


@router.post('/plan')
def plan_review(request: ReviewTarget):
    from backend.services.structure_review_jobs import resolve_source
    from backend.services.import_semantic_review import semantic_review_estimate
    from config import get_model_role_config
    from llm.factory import ensure_runtime_support
    from llm.types import Capability
    try:
        book, _, pdf = resolve_source(_target(request), progress_root=PROGRESS_PATH, books_root=BOOKS_PATH, jobs=get_job_manager())
        resolved = get_model_role_config('vision')
        ensure_runtime_support(resolved, Capability.VISION)
        answer_book = None
        if request.kind == 'file':
            from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore, file_book
            answer = ExerciseFileAnalysisStore(PROGRESS_PATH).answer_source(request.reference, request.book_name)
            if answer:
                answer_book = answer.canonical_book or file_book(answer, name=request.book_name, prefix='answer')
        plan = semantic_review_estimate(book, resolved, request.purpose or ('exercises' if request.kind=='file' else 'textbook'), answer_book=answer_book, has_original_pages=bool(pdf))
        from llm.registry import get_model
        model_spec = get_model(resolved.provider.provider_id, resolved.model)
        return dict(success=True, data={**plan, 'model': resolved.model, 'model_label': model_spec.label.split('（')[0] if model_spec else resolved.model, 'ready': resolved.credential_configured,
                    'provider': resolved.provider.label, 'max_cost_cny': request.max_cost_cny,
                    'has_original_pages': bool(pdf), 'image_scope': '原始PDF页面与区域裁片' if pdf else 'OCR坐标与已有裁片；无完整原页',
                    'notice': '使用已配置的识图服务，所选页和必要邻页会发送给该服务并按用量计费；未审阅页面不视为已核实。'})
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from None


@router.post('')
def create_review(request: ReviewTarget):
    from backend.services.structure_review_jobs import start_review
    try:
        purpose=request.purpose or ('exercises' if request.kind=='file' else 'outline')
        if request.kind=='file' and purpose!='exercises' or request.kind!='file' and purpose=='exercises':
            raise ValueError('整理类型与来源不一致')
        job = start_review(_target(request), mode=request.mode, max_pages=request.max_pages,
                           progress_root=PROGRESS_PATH, books_root=BOOKS_PATH, jobs=get_job_manager(),
                           budget=dict(max_cost_cny=request.max_cost_cny),purpose=purpose,retry_failed=request.retry_failed)
        return dict(success=True, data=job)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from None


@router.post('/reset')
def reset_review(request: ReviewTarget):
    from backend.services.structure_review_jobs import discard_review_candidate
    try:
        discard_review_candidate(_target(request),progress_root=PROGRESS_PATH,books_root=BOOKS_PATH,jobs=get_job_manager())
        return dict(success=True,message='已恢复原始识别结果，模型回执仍保留')
    except (ValueError,OSError) as exc:
        raise HTTPException(422,str(exc)) from None
