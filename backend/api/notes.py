"""Notes protocol adapter: structured errors and lazily bound application service."""
import sqlite3
from fastapi import APIRouter, Depends, Response
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from memory.session_notes import NoteError
from backend.services.session_notes.service import get_notes_service, SessionNoteService
from backend.services.session_notes.jobs import start_generation
from .note_schemas import Preflight, Generation, CreateDraft, PatchDraft, SaveDraft, Status


class NotesRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def bounded(request):
            try:
                return await handler(request)
            except NoteError as exc:
                return JSONResponse(status_code=exc.status, content={"success": False, "code": exc.code, "message": str(exc)})
            except RequestValidationError as exc:
                return JSONResponse(status_code=422, content={"success": False, "code": "invalid_document", "message": "请求字段无效", "field_errors": [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]})
            except (sqlite3.Error, OSError, RuntimeError):
                return JSONResponse(status_code=503, content={"success": False, "code": "storage_unavailable", "message": "笔记存储暂不可用，当前修改尚未保存"})
        return bounded


router = APIRouter(prefix="/notes", tags=["notes"], route_class=NotesRoute)


def result(data):
    return {"success": True, "data": data}


@router.post("/preflight")
def preflight(req: Preflight, service: SessionNoteService = Depends(get_notes_service)):
    data, _ = service.preflight(req.selection.model_dump(), req.structure_hint, req.completed_only)
    return result(data)


@router.get("/turns")
def turn_ranges(conversation_id: str, cursor: int | None = None, limit: int = 40):
    from backend.conversation_memory import list_note_turns
    from backend.services.session_notes.sources import safe_text
    page = list_note_turns(conversation_id, before_seq=cursor, limit=limit)
    page["items"] = [{**item, "label": safe_text(item["label"] or "")} for item in page["items"]]
    return result(page)


@router.get("/chapters")
def chapter_options(book_id: str = "", service: SessionNoteService = Depends(get_notes_service)):
    return result(service.chapters.options(book_id))


@router.post("/generations", status_code=202)
def generation(req: Generation, service: SessionNoteService = Depends(get_notes_service)):
    if not req.retry_of_draft_id and req.selection is None:
        raise NoteError("invalid_selection", "请选择一个来源会话", 400)
    receipt = service.request_generation(req.model_dump(exclude_none=True))
    start_generation(service, receipt)
    return result(receipt)


@router.get("/drafts")
def drafts(conversation_id: str = "", cursor: str = "", limit: int = 30, service: SessionNoteService = Depends(get_notes_service)):
    return result(service.list_drafts(conversation_id=conversation_id, cursor=cursor, limit=limit))


@router.post("/drafts", status_code=201)
def create_draft(req: CreateDraft, service: SessionNoteService = Depends(get_notes_service)):
    if req.kind == "edit" and not req.note_id or req.kind == "manual" and not req.snapshot_id:
        raise NoteError("invalid_selection", "缺少笔记或来源编号", 400)
    return result(service.create_draft(**req.model_dump()))


@router.get("/drafts/{draft_id}")
def draft(draft_id: str, service: SessionNoteService = Depends(get_notes_service)):
    return result(service.draft(draft_id))


@router.patch("/drafts/{draft_id}")
def patch_draft(draft_id: str, req: PatchDraft, service: SessionNoteService = Depends(get_notes_service)):
    return result(service.patch_draft(draft_id, req.expected_draft_revision, req.content))


@router.post("/drafts/{draft_id}/discard")
def discard(draft_id: str, service: SessionNoteService = Depends(get_notes_service)):
    return result(service.discard(draft_id))


@router.post("/drafts/{draft_id}/save")
def save(draft_id: str, req: SaveDraft, response: Response, service: SessionNoteService = Depends(get_notes_service)):
    receipt = service.save(draft_id, req.model_dump())
    response.status_code = 201 if receipt["revision"] == 1 else 200
    return result(receipt)


@router.get("/drafts/{draft_id}/sources/{source_ref_id}")
def draft_source(draft_id: str, source_ref_id: str, service: SessionNoteService = Depends(get_notes_service)):
    return result(service.source(draft_id, source_ref_id, draft=True))


@router.get("")
def notes(cursor: str = "", limit: int = 30, q: str = "", subject: str = "", book_id: str = "", chapter_ref_id: str = "", conversation_id: str = "", status: str = "active", service: SessionNoteService = Depends(get_notes_service)):
    return result(service.store.list(cursor=cursor, limit=limit, q=q, subject=subject, book_id=book_id, chapter_ref_id=chapter_ref_id, conversation_id=conversation_id, status=status))


@router.get("/filters")
def filter_options(status: str = "active", service: SessionNoteService = Depends(get_notes_service)):
    return result(service.store.filter_options(status))


@router.get("/{note_id}")
def note(note_id: str, service: SessionNoteService = Depends(get_notes_service)):
    return result(service.detail(note_id))


@router.get("/{note_id}/revisions")
def revisions(note_id: str, cursor: int | None = None, limit: int = 30, service: SessionNoteService = Depends(get_notes_service)):
    return result(service.store.revisions(note_id, before=cursor, limit=limit))


@router.get("/{note_id}/revisions/{revision}")
def revision(note_id: str, revision: int, service: SessionNoteService = Depends(get_notes_service)):
    return result(service.detail(note_id, revision))


@router.patch("/{note_id}/status")
def status(note_id: str, req: Status, service: SessionNoteService = Depends(get_notes_service)):
    return result(service.status(note_id, req.model_dump()))


@router.get("/{note_id}/sources/{source_ref_id}")
def source(note_id: str, source_ref_id: str, revision: int | None = None, service: SessionNoteService = Depends(get_notes_service)):
    return result(service.source(note_id, source_ref_id, revision=revision))
