"""Read-only Canonical Figure APIs and the bounded Figure question stream."""
from __future__ import annotations

from contextlib import nullcontext
import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from backend.conversation_memory import append_message, ensure_turn_id, resolve_conversation_id_for_scope
from backend.schemas import FigureQuestionRequest
from backend.services.figure_learning import FigureLearningService, NormalizedBBox
from backend.services.multimodal_bridge import VisionModelBridge
from config import PROGRESS_PATH
from utils.citation_protocol import sanitize_citation_protocol
from utils.latex_sanitizer import sanitize_latex


router = APIRouter(tags=["visual-learning"])


def _service() -> FigureLearningService:
    return FigureLearningService(Path(PROGRESS_PATH))


def _event(stage: str, **payload) -> str:
    return f"data: {json.dumps({'stage': stage, **payload}, ensure_ascii=False)}\n\n"


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc).strip("'"))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/books/{book_name}/figures")
def list_book_figures(
    book_name: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    query: str = Query("", max_length=200),
):
    try:
        return {"success": True, "data": _service().list_figures(
            book_name, offset=offset, limit=limit, query=query,
        )}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/books/{book_name}/figures/{figure_id}")
def get_book_figure(book_name: str, figure_id: str):
    try:
        service = _service()
        _book, _block, figure = service.get_figure(book_name, figure_id)
        context = service.build_context(book_name, figure_id)
        return {"success": True, "data": {**figure, **context.to_dict()}}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/books/{book_name}/figures/{figure_id}/image")
def get_book_figure_image(book_name: str, figure_id: str):
    try:
        path = _service().asset_path(book_name, figure_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".webp": "image/webp", ".bmp": "image/bmp", ".gif": "image/gif", ".tiff": "image/tiff",
    }
    return FileResponse(
        path,
        media_type=media_types.get(path.suffix.lower(), "application/octet-stream"),
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(path.name)}"},
    )


@router.post("/visual-learning/figure-stream")
def answer_figure_question(req: FigureQuestionRequest):
    """Keep Figure → context → optional crop → multimodal answer bounded and observable."""

    def events():
        service = _service()
        answer_chunks: list[str] = []
        try:
            context = service.build_context(req.book_name, req.figure_id)
            figure = context.figure
            full_image = service.asset_path(req.book_name, req.figure_id)
            source = {
                "id": "E1",
                "figure_id": req.figure_id,
                "book_name": req.book_name,
                "chapter": (figure.get("section_path") or [req.book_name])[0],
                "section_title": (figure.get("section_path") or [req.book_name])[-1],
                "section_path": figure.get("section_path") or [],
                "page_idx": figure.get("page_idx"),
                "caption": figure.get("caption") or "",
                "label": f"Figure {req.figure_id}",
                "asset_url": figure.get("image_url") or "",
                "pdf_url": figure.get("pdf_url") or "",
            }
            yield _event("activity", activity={
                "id": "figure-context", "kind": "evidence", "label": "读取教材 Figure 上下文",
                "status": "completed",
                "detail": f"已关联第 {figure.get('page') or '?'} 页及 {len(context.nearby_blocks)} 个邻近正文块",
                "meta": {"figure_id": req.figure_id, "related_chunk_ids": context.related_chunk_ids},
            })

            bbox = NormalizedBBox.from_values(req.bbox) if req.bbox is not None else None
            crop_manager = (
                service.cropped_region(req.book_name, req.figure_id, bbox)
                if bbox is not None and not bbox.covers_almost_full_image()
                else nullcontext((None, None))
            )
            with crop_manager as crop_result:
                crop_path, crop_metadata = crop_result
                if crop_path is not None:
                    yield _event("activity", activity={
                        "id": "crop-region", "kind": "tool", "label": "裁取用户选区",
                        "status": "completed", "detail": "已按图片自然尺寸生成临时局部图",
                        "meta": crop_metadata,
                    })
                yield _event("activity", activity={
                    "id": "figure-vision", "kind": "reasoning", "label": "理解 Figure 与选区",
                    "status": "active",
                    "detail": "正在同时核对完整 Figure、用户选区和邻近教材正文" if crop_path else "正在核对完整 Figure 和邻近教材正文",
                })
                bridge = VisionModelBridge()
                for chunk in bridge.iter_figure_answer(
                    full_image,
                    user_question=req.question,
                    figure_context={**context.to_dict(), "user_region": crop_metadata},
                    cropped_region_path=crop_path,
                ):
                    answer_chunks.append(chunk)
                    yield _event("generate", chunk=chunk, done=False)

            answer = sanitize_latex("".join(answer_chunks).strip())
            if not answer:
                raise RuntimeError("多模态模型未返回可展示回答")
            if "[[cite:E1]]" not in answer:
                page_label = f"p.{int(figure['page'])}" if figure.get("page") else "未标页"
                answer = f"{answer}\n\n来源：{req.book_name} · {page_label} · Figure {req.figure_id} [[cite:E1]]"
            answer, citation_trace = sanitize_citation_protocol(answer, [source])
            streamed = "".join(answer_chunks).strip()
            if answer != streamed:
                yield _event("generate", chunk=answer, replace=True, done=False)

            conversation_id = resolve_conversation_id_for_scope(
                req.conversation_id, req.subject, req.book_name,
            )
            turn_id = ensure_turn_id(req.turn_id)
            append_message(
                conversation_id, "user", req.question,
                book_name=req.book_name, subject=req.subject, turn_id=turn_id,
            )
            assistant_message = append_message(
                conversation_id, "assistant", answer,
                book_name=req.book_name, subject=req.subject, turn_id=turn_id,
                sources=[source], answer_mode="visual_grounded", evidence_support_status="grounded",
            )
            yield _event("done", done=True, result={
                "success": True,
                "explanation": answer,
                "sources": [source],
                "citation_trace": citation_trace,
                "message_id": assistant_message.get("id", ""),
                "conversation_id": conversation_id,
                "turn_id": turn_id,
                "figure_id": req.figure_id,
                "region": bbox.to_list() if bbox is not None else None,
            }, activity={
                "id": "figure-vision", "kind": "reasoning", "label": "理解 Figure 与选区",
                "status": "completed", "detail": "回答已绑定本次 Figure/Page 来源",
            })
        except Exception as exc:
            yield _event("error", done=True, message=str(exc), activity={
                "id": "figure-error", "kind": "system", "label": "Figure 问答失败",
                "status": "failed", "detail": str(exc),
            })

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
