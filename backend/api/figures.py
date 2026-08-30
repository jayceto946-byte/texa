"""Read-only Canonical Figure APIs and the bounded Figure question stream."""
from __future__ import annotations

from contextlib import nullcontext
import json
import logging
from pathlib import Path
import re
from urllib.parse import quote
import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from backend.conversation_memory import append_message, ensure_turn_id, resolve_conversation_id_for_scope
from backend.rag_trace import new_request_id
from backend.schemas import FigureQuestionRequest
from backend.services.answer_verification import derive_required_outputs, verification_notice, verify_answer
from backend.services.execution_events import ExecutionEventEmitter, execution_sse_payload
from backend.services.figure_learning import (
    FigureIndexOutOfDateError,
    FigureLearningService,
    NormalizedBBox,
)
from backend.services.learning_task import (
    LearningTask,
    LearningTaskStore,
    get_learning_task_store,
    interrupt_learning_task,
    is_resumable_task_status,
    resume_learning_task,
)
from backend.services.multimodal_bridge import VisionModelBridge
from config import PROGRESS_PATH
from utils.citation_protocol import sanitize_citation_protocol
from utils.latex_sanitizer import sanitize_latex


router = APIRouter(tags=["visual-learning"])
logger = logging.getLogger(__name__)


def _service() -> FigureLearningService:
    return FigureLearningService(Path(PROGRESS_PATH))


def _task_store() -> LearningTaskStore:
    return get_learning_task_store()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FigureIndexOutOfDateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc).strip("'"))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


_CITATION_RE = re.compile(r"\[\[cite:(E[\w-]+)\]\]", re.IGNORECASE)


def _citation_provenance(answer: str, citation_trace: dict, sources: list[dict]) -> dict:
    valid_ids = {
        str(source.get("id") or "").upper()
        for source in sources if isinstance(source, dict) and source.get("id")
    }
    model_ids = list(dict.fromkeys(
        value.upper() for value in _CITATION_RE.findall(answer) if value.upper() in valid_ids
    ))
    invalid_removed = int(citation_trace.get("invalid_ids_removed") or 0)
    if "E1" in model_ids and invalid_removed == 0:
        status = "model_aligned"
        paragraph_alignment = "complete"
    elif model_ids:
        status = "partially_aligned"
        paragraph_alignment = "partial"
    else:
        status = "sources_attached"
        paragraph_alignment = "unverified"
    return {
        "status": status,
        "model_citation_ids": model_ids,
        "source_attachment_origin": "system",
        "paragraph_alignment": paragraph_alignment,
        "automatic_citation_inserted": False,
    }


def _display_question(task: LearningTask) -> str:
    page = task.artifacts.get("page")
    page_label = f"p.{page}" if page else "未标页"
    return f"📎 教材 Figure · {page_label}\n\n{task.goal}"


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


def _figure_stream(
    req: FigureQuestionRequest,
    *,
    existing_task: LearningTask | None = None,
    run_id: str = "",
):
    """Keep Figure → context → optional crop → multimodal answer bounded and resumable."""

    active_run_id = run_id or f"run_{uuid.uuid4().hex}"
    request_id = new_request_id()

    def events():
        service = _service()
        store = _task_store()
        answer_chunks: list[str] = []
        task = existing_task
        sources: list[dict] = []
        conversation_id = resolve_conversation_id_for_scope(
            req.conversation_id, req.subject, req.book_name,
        )
        turn_id = ensure_turn_id(req.turn_id)
        required_outputs = derive_required_outputs(
            req.question, intent="application", answer_mode="visual_grounded",
        )
        if task is None:
            task = store.create(
                task_type="figure_qa",
                goal=req.question,
                conversation_id=conversation_id,
                turn_id=turn_id,
                answer_mode="visual_grounded",
                required_outputs=required_outputs,
                artifacts={
                    "book_name": req.book_name,
                    "figure_id": req.figure_id,
                    "subject": req.subject,
                    "page": None,
                    "region": req.bbox,
                    "related_chunk_ids": [],
                    "source_ids": [],
                    "active_run_id": active_run_id,
                },
            )
        else:
            required_outputs = list(task.required_outputs or required_outputs)
            conversation_id = task.conversation_id or conversation_id
            turn_id = task.turn_id or turn_id
            task.artifacts.update({
                "book_name": req.book_name,
                "figure_id": req.figure_id,
                "subject": req.subject,
                "region": req.bbox,
                "active_run_id": active_run_id,
            })
            task = store.save_for_run(task, active_run_id)
        if not store.run_is_active(task.id, active_run_id):
            return

        def persist_execution_event(event: dict) -> None:
            updated = store.append_execution_event_for_run(task.id, active_run_id, event)
            if (
                updated is None
                or str(updated.artifacts.get("active_run_id") or "") != active_run_id
            ):
                raise ValueError("stale Figure execution run cannot persist events")
            if event.get("type") in {"final", "error"}:
                event_task_status = str((event.get("payload") or {}).get("task_status") or "")
                if not event_task_status or updated.status != event_task_status:
                    raise ValueError("Figure terminal event does not match the current task state")
            elif not store.run_is_active(task.id, active_run_id):
                raise ValueError("stale Figure execution run cannot persist events")
            task.artifacts["execution_events"] = list(
                updated.artifacts.get("execution_events") or []
            )[-40:]

        emitter = ExecutionEventEmitter(
            request_id=request_id,
            task_id=task.id,
            run_id=active_run_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            persist=persist_execution_event,
        )

        def emit_sse(
            event_type: str,
            *,
            phase: str,
            status: str,
            summary: str,
            operation_id: str,
            label: str,
            kind: str,
            payload: dict | None = None,
            extra: dict | None = None,
        ) -> str:
            if event_type not in {"final", "error"} and not store.run_is_active(
                task.id, active_run_id,
            ):
                raise ValueError("stale Figure execution run cannot emit events")
            execution_event = emitter.emit(
                event_type,
                phase=phase,
                status=status,
                summary=summary,
                operation_id=operation_id,
                label=label,
                kind=kind,
                payload=payload,
            )
            legacy_stage = {
                "output_delta": "generate",
                "final": "done",
                "error": "error",
            }.get(event_type, "activity")
            envelope = execution_sse_payload(execution_event, stage=legacy_stage)
            if event_type == "output_delta":
                envelope.update({
                    "chunk": execution_event["payload"]["text"],
                    "replace": execution_event["payload"]["replace"],
                    "done": False,
                })
            elif event_type in {"final", "error"}:
                envelope["done"] = True
            if extra:
                envelope.update(extra)
            return _sse(envelope)

        try:
            yield emit_sse(
                "progress",
                phase="evidence",
                status="started",
                summary="正在校验 active index 并读取 Figure 来源",
                operation_id="figure-context",
                label="读取教材 Figure 上下文",
                kind="evidence",
                payload={"figure_id": req.figure_id},
            )
            context = service.build_context(req.book_name, req.figure_id)
            figure = context.figure
            full_image = service.asset_path(req.book_name, req.figure_id)
            sources = service.evidence_sources(context)
            task.artifacts.update({
                "page": figure.get("page"),
                "related_chunk_ids": context.related_chunk_ids,
                "source_ids": [source.get("id") for source in sources],
            })
            task = store.save_for_run(task, active_run_id)
            if not store.run_is_active(task.id, active_run_id):
                return
            task = store.checkpoint_for_run(
                task, active_run_id, "figure_context_ready", detail=f"{len(sources)} sources",
            )
            if not store.run_is_active(task.id, active_run_id):
                return
            yield emit_sse(
                "state_transition",
                phase="evidence",
                status="completed",
                summary=f"已关联第 {figure.get('page') or '?'} 页及 {len(context.nearby_blocks)} 个邻近正文块",
                operation_id="figure-context",
                label="读取教材 Figure 上下文",
                kind="evidence",
                payload={
                    "figure_id": req.figure_id,
                    "related_chunk_ids": context.related_chunk_ids,
                    "index_version": figure.get("index_version") or "",
                },
                extra={"learning_task": task.to_dict(public=True)},
            )

            bbox = NormalizedBBox.from_values(req.bbox) if req.bbox is not None else None
            crop_manager = (
                service.cropped_region(req.book_name, req.figure_id, bbox)
                if bbox is not None and not bbox.covers_almost_full_image()
                else nullcontext((None, None))
            )
            with crop_manager as crop_result:
                crop_path, crop_metadata = crop_result
                if crop_path is not None:
                    yield emit_sse(
                        "tool_result",
                        phase="tool",
                        status="completed",
                        summary="已按图片自然尺寸生成临时局部图",
                        operation_id="crop-region",
                        label="裁取用户选区",
                        kind="tool",
                        payload=dict(crop_metadata or {}),
                    )
                yield emit_sse(
                    "progress",
                    phase="reasoning",
                    status="started",
                    summary=(
                        "正在同时核对完整 Figure、用户选区和邻近教材正文"
                        if crop_path else "正在核对完整 Figure 和邻近教材正文"
                    ),
                    operation_id="figure-vision",
                    label="理解 Figure 与选区",
                    kind="reasoning",
                )
                bridge = VisionModelBridge()
                for chunk in bridge.iter_figure_answer(
                    full_image,
                    user_question=req.question,
                    figure_context={
                        **context.to_dict(),
                        "user_region": crop_metadata,
                        "evidence_sources": sources,
                    },
                    cropped_region_path=crop_path,
                ):
                    if not store.run_is_active(task.id, active_run_id):
                        return
                    visible_chunk = str(chunk or "")
                    answer_chunks.append(visible_chunk)
                    task.artifacts["partial_output"] = "".join(answer_chunks)[-12000:]
                    task = store.save_for_run(task, active_run_id)
                    if not store.run_is_active(task.id, active_run_id):
                        return
                    yield emit_sse(
                        "output_delta",
                        phase="generation",
                        status="running",
                        summary="正在生成 Figure 讲解",
                        operation_id="figure-answer",
                        label="生成 Figure 讲解",
                        kind="generation",
                        payload={"text": visible_chunk, "replace": False},
                    )

            if not store.run_is_active(task.id, active_run_id):
                return
            answer = sanitize_latex("".join(answer_chunks).strip())
            if not answer:
                raise RuntimeError("多模态模型未返回可展示回答")
            answer, citation_trace = sanitize_citation_protocol(answer, sources)
            citation_provenance = _citation_provenance(answer, citation_trace, sources)
            answer_verification = verify_answer(
                answer,
                required_outputs=required_outputs,
                sources=sources,
                citation_trace=citation_trace,
                evidence_items=[{"id": source.get("id"), "text": source.get("text", "")} for source in sources],
            )
            notice = verification_notice(answer_verification)
            if notice and notice not in answer:
                answer = f"{answer.rstrip()}\n\n{notice}"
            streamed = "".join(answer_chunks).strip()
            if answer != streamed:
                yield emit_sse(
                    "output_delta",
                    phase="generation",
                    status="running",
                    summary="已完成 Figure 回答校验与格式整理",
                    operation_id="figure-answer",
                    label="生成 Figure 讲解",
                    kind="generation",
                    payload={"text": answer, "replace": True},
                )

            task.verification = answer_verification
            task.artifacts["answer"] = answer
            task.artifacts.pop("partial_output", None)
            completion_status = "completed" if answer_verification.get("status") == "passed" else "degraded"
            task = store.checkpoint_for_run(
                task, active_run_id, "verified", status=completion_status,
                detail=str(answer_verification.get("status") or "unknown"),
            )
            if task.status != completion_status:
                return

            assistant_message: dict = {}
            persistence_error = ""
            try:
                append_message(
                    conversation_id, "user", _display_question(task),
                    book_name=req.book_name, subject=req.subject, turn_id=turn_id,
                )
                assistant_message = append_message(
                    conversation_id, "assistant", answer,
                    book_name=req.book_name, subject=req.subject, turn_id=turn_id,
                    sources=sources, answer_mode="visual_grounded",
                    evidence_support_status=(
                        "grounded" if citation_provenance["status"] == "model_aligned" else "degraded"
                    ),
                    delivery_status="complete", learning_task=task.to_dict(public=True),
                    citation_provenance=citation_provenance,
                )
            except Exception as persistence_exc:
                persistence_error = str(persistence_exc)
                logger.exception("Figure conversation persistence failed")
            task.artifacts["message_id"] = assistant_message.get("id", "")
            store.save(task)
            yield emit_sse(
                "final",
                phase="final",
                status="completed",
                summary="回答已绑定本次 Figure/Page 来源",
                operation_id="figure-vision",
                label="理解 Figure 与选区",
                kind="reasoning",
                payload={
                    "task_status": task.status,
                    "figure_id": req.figure_id,
                    "index_version": figure.get("index_version") or "",
                    "citation_status": citation_provenance["status"],
                },
                extra={
                    "result": {
                        "success": True,
                        "explanation": answer,
                        "sources": sources,
                        "citation_trace": citation_trace,
                        "citation_provenance": citation_provenance,
                        "answer_verification": answer_verification,
                        "learning_task": task.to_dict(public=True),
                        "message_id": assistant_message.get("id", ""),
                        "conversation_id": conversation_id,
                        "turn_id": turn_id,
                        "figure_id": req.figure_id,
                        "region": bbox.to_list() if bbox is not None else None,
                    },
                    **({"persistence_error": persistence_error} if persistence_error else {}),
                },
            )
        except Exception as exc:
            if not store.run_is_active(task.id, active_run_id):
                return
            task.verification = {"status": "failed", "passed": False, "checks": []}
            task = store.checkpoint_for_run(
                task, active_run_id, "failed", status="failed", detail=str(exc),
            )
            if task.status != "failed":
                return
            persistence_error = ""
            try:
                append_message(
                    task.conversation_id, "user", _display_question(task),
                    book_name=req.book_name, subject=req.subject, turn_id=task.turn_id,
                )
                append_message(
                    task.conversation_id, "assistant", f"教材图片问答失败：{exc}",
                    book_name=req.book_name, subject=req.subject, turn_id=task.turn_id,
                    sources=sources, answer_mode="visual_grounded", evidence_support_status="failed",
                    delivery_status="error", learning_task=task.to_dict(public=True),
                )
            except Exception as persistence_exc:
                persistence_error = str(persistence_exc)
                logger.exception("Figure failure projection persistence failed")
            http_status = _http_error(exc).status_code
            error_code = (
                "figure_index_out_of_date"
                if isinstance(exc, FigureIndexOutOfDateError)
                else "figure_execution_failed"
            )
            yield emit_sse(
                "error",
                phase="error",
                status="failed",
                summary=str(exc),
                operation_id="figure-error",
                label="Figure 问答失败",
                kind="system",
                payload={
                    "task_status": task.status,
                    "error_code": error_code,
                    "http_status": http_status,
                    "figure_id": req.figure_id,
                },
                extra={
                    "message": str(exc),
                    "learning_task": task.to_dict(public=True),
                    "error_code": error_code,
                    "http_status": http_status,
                    **({"persistence_error": persistence_error} if persistence_error else {}),
                },
            )

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/visual-learning/figure-stream")
def answer_figure_question(req: FigureQuestionRequest):
    return _figure_stream(req)


@router.post("/visual-learning/tasks/{task_id}/interrupt")
def interrupt_figure_task(task_id: str, payload: dict | None = None):
    store = _task_store()
    task = store.get(task_id)
    if task is None or task.task_type != "figure_qa":
        raise HTTPException(status_code=404, detail="Figure learning task not found")
    data = payload or {}
    task = interrupt_learning_task(
        store,
        task,
        stage=str(data.get("stage") or "user_stopped"),
        partial_output=str(data.get("partial_output") or ""),
    )
    if is_resumable_task_status(task.status):
        book_name = str(task.artifacts.get("book_name") or "")
        subject = str(task.artifacts.get("subject") or "")
        sources: list[dict] = []
        try:
            context = _service().build_context(book_name, str(task.artifacts.get("figure_id") or ""))
            sources = _service().evidence_sources(context)
        except Exception:
            pass
        append_message(
            task.conversation_id, "user", _display_question(task),
            book_name=book_name, subject=subject, turn_id=task.turn_id,
        )
        append_message(
            task.conversation_id, "assistant",
            str(task.artifacts.get("partial_output") or "").strip() or "已停止教材图片问答。",
            book_name=book_name, subject=subject, turn_id=task.turn_id,
            sources=sources, answer_mode="visual_grounded", delivery_status="partial",
            learning_task=task.to_dict(public=True),
        )
    return {"success": True, "learning_task": task.to_dict(public=True)}


@router.post("/visual-learning/tasks/{task_id}/resume-stream")
def resume_figure_task_stream(task_id: str):
    store = _task_store()
    task = store.get(task_id)
    if task is None or task.task_type != "figure_qa":
        raise HTTPException(status_code=404, detail="Figure learning task not found")
    run_id = f"run_{uuid.uuid4().hex}"
    try:
        task = resume_learning_task(store, task, run_id=run_id)
        req = FigureQuestionRequest(
            book_name=str(task.artifacts.get("book_name") or ""),
            figure_id=str(task.artifacts.get("figure_id") or ""),
            question=task.goal,
            bbox=task.artifacts.get("region"),
            subject=str(task.artifacts.get("subject") or ""),
            conversation_id=task.conversation_id,
            turn_id=task.turn_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc
    return _figure_stream(req, existing_task=task, run_id=run_id)
