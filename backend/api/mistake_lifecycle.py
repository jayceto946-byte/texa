"""Protocol layer for mistake candidates, drafts and durable redo sessions."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import base64
import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone

from backend.services.mistake_lifecycle import project_mistake
from backend.api.mistakes import _image_store, _ocr_image_with_kimi
from backend.api import mistakes as legacy_mistakes
from memory.mistake_book import MistakeRecord
from utils.subject_catalog import subject_matches

from backend.api.mistakes import _mb
from memory.mistake_lifecycle import MistakeLifecycleStore

router = APIRouter(prefix="/mistakes", tags=["mistakes"])
review_router = APIRouter(prefix="/review/sessions", tags=["review"])


def _store(book_name: str) -> MistakeLifecycleStore:
    return MistakeLifecycleStore(_mb(book_name).store)


def _clean_draft_data(data: dict) -> dict:
    allowed = {"question_text", "user_answer", "correct_answer", "subject", "chapter", "source", "source_ref", "tags", "mistake_type", "notes", "ocr_text", "visual_ir", "content_complete", "diagnosis_status", "failure_confirmed"}
    if set(data) - allowed:
        raise HTTPException(status_code=422, detail="unsupported draft fields")
    for field in ("question_text", "user_answer", "correct_answer", "subject", "chapter", "source", "notes", "ocr_text"):
        if field in data and (not isinstance(data[field], str) or len(data[field]) > 30000):
            raise HTTPException(status_code=422, detail=f"invalid {field}")
    for field in ("tags", "mistake_type"):
        if field in data and (not isinstance(data[field], list) or len(data[field]) > 30 or any(not isinstance(value, str) or len(value) > 120 for value in data[field])):
            raise HTTPException(status_code=422, detail=f"invalid {field}")
    for field in ("content_complete", "failure_confirmed"):
        if field in data and type(data[field]) is not bool:
            raise HTTPException(status_code=422, detail=f"invalid {field}")
    if "visual_ir" in data and not isinstance(data["visual_ir"], dict):
        raise HTTPException(status_code=422, detail="invalid visual_ir")
    if "source_ref" in data and (not isinstance(data["source_ref"], dict) or len(json.dumps(data["source_ref"], ensure_ascii=False)) > 4000):
        raise HTTPException(status_code=422, detail="invalid source_ref")
    if "diagnosis_status" in data and data["diagnosis_status"] not in {"missing", "confirmed", "deferred"}:
        raise HTTPException(status_code=422, detail="invalid diagnosis_status")
    return data


def _error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "revision changed" in message:
        return HTTPException(status_code=409, detail=message)
    if "not found" in message:
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=422, detail=message)


class CandidateCreate(BaseModel):
    source_key: str = Field(min_length=1, max_length=240)
    snapshot: dict


class CandidateDecision(BaseModel):
    expected_revision: int = Field(ge=1)
    operation_id: str = Field(min_length=1, max_length=160)


class CandidateUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    changes: dict


class DraftCreate(BaseModel):
    data: dict = Field(default_factory=dict)


class DraftUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    data: dict


class DraftRecognize(BaseModel):
    expected_revision: int = Field(ge=1)
    attachment_id: str


class DraftSave(BaseModel):
    expected_revision: int = Field(ge=1)
    operation_id: str = Field(min_length=1, max_length=160)


class SessionCreate(BaseModel):
    mistake_ids: list[str] = Field(min_length=1, max_length=100)
    book_name: str = "default"


class SessionDraft(BaseModel):
    expected_revision: int = Field(ge=1)
    answer: str = Field(default="", max_length=30000)
    revealed: bool = False


class SessionResult(BaseModel):
    expected_revision: int = Field(ge=1)
    operation_id: str = Field(min_length=1, max_length=160)
    result: str
    hint_used: bool = False
    judgement_source: str = "user_confirmed"


class MistakeQuery(BaseModel):
    subject: str = ""
    search: str = ""
    filter: str = "all"
    cursor: str = ""
    limit: int = Field(default=30, ge=1, le=100)


class RecordPatch(BaseModel):
    expected_revision: int = Field(ge=1)
    operation_id: str = Field(min_length=1, max_length=160)
    changes: dict
    meaning_changed: bool = False


class RecordAction(BaseModel):
    expected_revision: int = Field(ge=1)
    operation_id: str = Field(min_length=1, max_length=160)
    action: str


def _cursor_decode(raw: str) -> tuple[str, str] | None:
    if not raw:
        return None
    try:
        value = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
        if isinstance(value, list) and len(value) == 2 and all(isinstance(item, str) for item in value):
            return value[0], value[1]
    except (ValueError, UnicodeDecodeError):
        pass
    raise HTTPException(status_code=422, detail="invalid cursor")


def _cursor_encode(created_at: str, rid: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([created_at, rid]).encode()).decode()


@router.post("/query")
def query_mistakes(req: MistakeQuery, book_name: str = "default"):
    if req.filter not in {"all", "pending", "due", "repeated", "mastered"}:
        raise HTTPException(status_code=422, detail="unsupported filter")
    store = _store(book_name)
    cursor = _cursor_decode(req.cursor)
    items: list[dict] = []
    last_key: tuple[str, str] | None = None
    exhausted = False
    with store.store._connect() as conn:
        while len(items) <= req.limit:
            sql = "SELECT id,data,created_at FROM mistakes WHERE 1=1"
            params: list[str | int] = []
            if cursor:
                sql += " AND (created_at<? OR (created_at=? AND id<?))"
                params.extend([cursor[0], cursor[0], cursor[1]])
            sql += " ORDER BY created_at DESC,id DESC LIMIT 100"
            rows = conn.execute(sql, params).fetchall()
            if not rows:
                exhausted = True
                break
            for rid, raw, created_at in rows:
                cursor = (created_at, rid)
                record = MistakeRecord.from_dict(json.loads(raw))
                if record.visibility != "active" or req.subject and not subject_matches(record.subject, req.subject):
                    continue
                needle = req.search.strip().lower()
                if needle and not any(needle in text.lower() for text in [record.question_text, record.ocr_text, record.explanation, *record.tags, *record.mistake_type]):
                    continue
                projection = project_mistake(record, store.list_attempts(record.id, limit=100000))
                if req.filter == "pending" and not projection["pending_reason"]:
                    continue
                if req.filter == "due" and (projection["review_status"] != "due" or projection["mastery_status"] == "mastered"):
                    continue
                if req.filter == "repeated" and not projection["repeat_wrong"]:
                    continue
                if req.filter == "mastered" and projection["mastery_status"] != "mastered":
                    continue
                items.append({**record.to_dict(), **projection, "next_review": record.sm2.get("next_review")})
                if len(items) <= req.limit:
                    last_key = (created_at, rid)
                if len(items) > req.limit:
                    break
            if len(items) > req.limit:
                break
            if len(rows) < 100:
                exhausted = True
                break
    next_cursor = _cursor_encode(*last_key) if len(items) > req.limit and last_key else None
    return {"success": True, "data": {"items": items[:req.limit], "next_cursor": next_cursor, "counts": None, "errors": {}, "exhausted": exhausted and not next_cursor}}


@router.get("/diagnosis")
def diagnose_mistakes(book_name: str = "default", subject: str = ""):
    store = _store(book_name)
    now = datetime.now(timezone.utc)
    recent_start = now - timedelta(days=30)
    prior_start = now - timedelta(days=60)
    records: dict[str, MistakeRecord] = {}
    attempts: dict[str, list[dict]] = {}
    with store.store._connect() as conn:
        for rid, raw in conn.execute("SELECT id,data FROM mistakes"):
            record = MistakeRecord.from_dict(json.loads(raw))
            if record.visibility == "active" and (not subject or subject_matches(record.subject, subject)):
                records[rid] = record
        if records:
            for rid, kind, raw, created_at in conn.execute("SELECT mistake_id,kind,data,created_at FROM mistake_attempts ORDER BY created_at,id"):
                if rid in records:
                    attempts.setdefault(rid, []).append({"kind": kind, "created_at": created_at, **json.loads(raw)})

    def window_rows(rows: list[dict], start: datetime, end: datetime) -> list[dict]:
        selected = []
        for row in rows:
            try:
                created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                created = created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created
            except (KeyError, ValueError):
                continue
            if start <= created < end and row.get("kind") == "redo" and row.get("answer", "").strip() and not row.get("hint_used") and row.get("result") in {"wrong", "partial", "independent_correct"} and row.get("judgement_source") in {"user_confirmed", "deterministic"}:
                selected.append(row)
        return selected

    groups: dict[str, dict] = {}
    reason_groups: dict[str, dict] = {}
    actions: list[dict] = []
    for rid, record in records.items():
        item_attempts = attempts.get(rid, [])
        recent = window_rows(item_attempts, recent_start, now)
        prior = window_rows(item_attempts, prior_start, recent_start)
        for tag in record.tags or ["未标注知识点"]:
            group = groups.setdefault(tag, {"name": tag, "mistake_ids": [], "recent_wrong": 0, "recent_attempts": 0, "recent_correct": 0})
            group["mistake_ids"].append(rid)
            group["recent_wrong"] += sum(row["result"] in {"wrong", "partial"} for row in recent)
            group["recent_attempts"] += len(recent)
            group["recent_correct"] += sum(row["result"] == "independent_correct" for row in recent)
        if record.diagnosis_status == "confirmed":
            for reason in record.mistake_type:
                group = reason_groups.setdefault(reason, {"name": reason, "mistake_ids": [], "example": ""})
                group["mistake_ids"].append(rid)
                group["example"] = group["example"] or record.notes[:180] or record.user_answer[:180]
        projection = project_mistake(record, item_attempts)
        priority = 0 if record.content_status == "needs_correction" else 1 if projection["review_status"] == "due" and projection["repeat_wrong"] else 2 if projection["review_status"] == "due" else 9
        if priority < 9:
            actions.append({"mistake_id": rid, "priority": priority, "reason": "校对关键材料" if priority == 0 else "复习反复出错的题" if priority == 1 else "完成到期重做"})

    cohort = [rid for rid, rows in attempts.items() if window_rows(rows, recent_start, now) and window_rows(rows, prior_start, recent_start)]
    recent_cohort = [row for rid in cohort for row in window_rows(attempts[rid], recent_start, now)]
    prior_cohort = [row for rid in cohort for row in window_rows(attempts[rid], prior_start, recent_start)]
    comparable = len(cohort) >= 3 and len(recent_cohort) >= 5 and len(prior_cohort) >= 5
    return {"success": True, "data": {
        "scope": {"book_name": book_name, "subject": subject, "recent_start": recent_start.date().isoformat(), "prior_start": prior_start.date().isoformat(), "end": now.date().isoformat()},
        "record_count": len(records), "groups": sorted(groups.values(), key=lambda item: (-item["recent_wrong"], -len(item["mistake_ids"]), item["name"])),
        "reasons": sorted(reason_groups.values(), key=lambda item: (-len(item["mistake_ids"]), item["name"])),
        "unconfirmed_diagnosis_count": sum(record.diagnosis_status != "confirmed" for record in records.values()),
        "comparison": {"cohort_mistake_ids": cohort, "prior_correct": sum(row["result"] == "independent_correct" for row in prior_cohort), "prior_total": len(prior_cohort), "recent_correct": sum(row["result"] == "independent_correct" for row in recent_cohort), "recent_total": len(recent_cohort), "comparable": comparable},
        "actions": sorted(actions, key=lambda item: (item["priority"], item["mistake_id"]))[:3],
        "legacy_quality_excluded": True,
    }}


@router.get("/counts")
def count_mistakes(book_name: str = "default", subject: str = "", search: str = ""):
    store = _store(book_name)
    counts = {"all": 0, "pending": 0, "due": 0, "repeated": 0, "mastered": 0}
    needle = search.strip().lower()
    with store.store._connect() as conn:
        rows = conn.execute("SELECT id,data FROM mistakes").fetchall()
    for rid, raw in rows:
        record = MistakeRecord.from_dict(json.loads(raw))
        if record.visibility != "active" or subject and not subject_matches(record.subject, subject):
            continue
        if needle and not any(needle in value.lower() for value in [record.question_text, record.ocr_text, record.explanation, *record.tags, *record.mistake_type]):
            continue
        projection = project_mistake(record, store.list_attempts(rid, limit=100000))
        counts["all"] += 1
        counts["pending"] += bool(projection["pending_reason"])
        counts["due"] += projection["review_status"] == "due" and projection["mastery_status"] != "mastered"
        counts["repeated"] += bool(projection["repeat_wrong"])
        counts["mastered"] += projection["mastery_status"] == "mastered"
    return {"success": True, "data": counts}


@router.get("/due")
def get_due_mistakes(subject: str = "", book_name: str = "default"):
    return legacy_mistakes.get_due_mistakes(subject=subject, book_name=book_name)


@router.get("/stats")
def get_legacy_stats(subject: str = "", book_name: str = "default"):
    return legacy_mistakes.get_stats(subject=subject, book_name=book_name)


@router.get("/weak-points")
def get_legacy_weak_points(subject: str = "", book_name: str = "default", top_n: int = 8):
    return legacy_mistakes.get_weak_points(subject=subject, book_name=book_name, top_n=top_n)


@router.post("/candidates")
def create_candidate(req: CandidateCreate, book_name: str = "default"):
    allowed = {"question_text", "user_answer", "correct_answer", "subject", "chapter", "source", "source_ref", "tags", "mistake_type", "notes", "ocr_text", "visual_ir", "content_complete", "diagnosis_status", "failure_confirmed", "stable_source_key"}
    if set(req.snapshot) - allowed or len(json.dumps(req.snapshot, ensure_ascii=False)) > 60000:
        raise HTTPException(status_code=422, detail="invalid candidate snapshot")
    _clean_draft_data({key: value for key, value in req.snapshot.items() if key != "stable_source_key"})
    try:
        return {"success": True, "data": _store(book_name).create_candidate(req.source_key, req.snapshot)}
    except ValueError as exc:
        raise _error(exc) from exc


@router.get("/candidates")
def list_candidates(book_name: str = "default", subject: str = "", limit: int = 30):
    rows = _store(book_name).list_candidates(limit=100000)
    return {"success": True, "data": [row for row in rows if not subject or subject_matches(str(row.get("subject") or ""), subject)][:max(1, min(limit, 100))]}


@router.patch("/candidates/{candidate_id}")
def update_candidate(candidate_id: str, req: CandidateUpdate, book_name: str = "default"):
    _clean_draft_data(req.changes)
    try:
        return {"success": True, "data": _store(book_name).update_candidate(candidate_id, expected_revision=req.expected_revision, changes=req.changes)}
    except ValueError as exc:
        raise _error(exc) from exc


@router.post("/candidates/{candidate_id}/accept")
def accept_candidate(candidate_id: str, req: CandidateDecision, book_name: str = "default"):
    try:
        return {"success": True, "data": _store(book_name).resolve_candidate(candidate_id, accept=True, expected_revision=req.expected_revision, operation_id=req.operation_id)}
    except ValueError as exc:
        raise _error(exc) from exc


@router.post("/candidates/{candidate_id}/dismiss")
def dismiss_candidate(candidate_id: str, req: CandidateDecision, book_name: str = "default"):
    try:
        return {"success": True, "data": _store(book_name).resolve_candidate(candidate_id, accept=False, expected_revision=req.expected_revision, operation_id=req.operation_id)}
    except ValueError as exc:
        raise _error(exc) from exc


@router.post("/drafts")
def create_draft(req: DraftCreate, book_name: str = "default"):
    return {"success": True, "data": _store(book_name).create_draft(_clean_draft_data(req.data))}


@router.get("/drafts")
def list_drafts(book_name: str = "default", limit: int = 20):
    return {"success": True, "data": _store(book_name).list_drafts(limit=max(1, min(limit, 100)))}


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str, book_name: str = "default"):
    draft = _store(book_name).get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    return {"success": True, "data": draft}


@router.patch("/drafts/{draft_id}")
def update_draft(draft_id: str, req: DraftUpdate, book_name: str = "default"):
    try:
        return {"success": True, "data": _store(book_name).update_draft(draft_id, _clean_draft_data(req.data), req.expected_revision)}
    except ValueError as exc:
        raise _error(exc) from exc


def _draft_attachment(draft: dict, attachment_id: str) -> dict:
    attachment = next((item for item in draft.get("attachments", []) if item.get("id") == attachment_id), None)
    if not attachment:
        raise HTTPException(status_code=404, detail="attachment not found")
    return attachment


@router.post("/drafts/{draft_id}/attachments")
def add_draft_attachment(draft_id: str, expected_revision: int = Form(...), file: UploadFile = File(...), book_name: str = "default"):
    store = _store(book_name)
    draft = store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    if draft["revision"] != expected_revision:
        raise HTTPException(status_code=409, detail="draft revision changed")
    original = work = None
    try:
        original, work = _image_store.save_draft_attachment(file, draft_id)
        attachment = {"id": "att_" + uuid.uuid4().hex[:20], "original_path": str(original), "work_path": str(work), "filename": file.filename or "image"}
        updated = store.update_draft(draft_id, {"attachments": [*draft.get("attachments", []), attachment]}, expected_revision)
        return {"success": True, "data": updated}
    except ValueError as exc:
        if original:
            _image_store.delete(original)
        if work and work != original:
            _image_store.delete(work)
        raise _error(exc) from exc


@router.get("/drafts/{draft_id}/attachments/{attachment_id}")
def get_draft_attachment(draft_id: str, attachment_id: str, book_name: str = "default"):
    draft = _store(book_name).get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    attachment = _draft_attachment(draft, attachment_id)
    path = Path(attachment["original_path"]).resolve()
    expected_root = (_image_store.image_root / "drafts" / draft_id).resolve()
    if not path.is_relative_to(expected_root) or not path.is_file():
        raise HTTPException(status_code=404, detail="attachment file not found")
    return FileResponse(path)


@router.post("/drafts/{draft_id}/recognize")
def recognize_draft(draft_id: str, req: DraftRecognize, book_name: str = "default"):
    draft = _store(book_name).get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    if draft["revision"] != req.expected_revision:
        raise HTTPException(status_code=409, detail="draft revision changed")
    attachment = _draft_attachment(draft, req.attachment_id)
    path = Path(attachment["work_path"]).resolve()
    expected_root = (_image_store.image_root / "drafts" / draft_id).resolve()
    if not path.is_relative_to(expected_root) or not path.is_file():
        raise HTTPException(status_code=404, detail="attachment file not found")
    try:
        visual = _ocr_image_with_kimi(path)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"识别暂不可用：{type(exc).__name__}") from exc
    return {"success": True, "data": {"draft_revision": req.expected_revision, "attachment_id": req.attachment_id,
        "ocr_text": visual.problem_text, "visual_ir": visual.to_dict(), "uncertainties": visual.uncertainties}}


@router.post("/drafts/{draft_id}/save")
def save_draft(draft_id: str, req: DraftSave, book_name: str = "default"):
    store = _store(book_name)
    draft = store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    if draft["revision"] != req.expected_revision:
        raise HTTPException(status_code=409, detail="draft revision changed")
    if not draft.get("question_text", "").strip() or not draft.get("content_complete", False):
        return {"success": True, "data": {"status": "draft", "draft_id": draft_id, "reason": "题干或关键材料仍需校对"}}
    snapshot = {key: value for key, value in draft.items() if key not in {"id", "revision", "updated_at"}}
    attachments = draft.get("attachments") or []
    if attachments and not snapshot.get("image_path"):
        snapshot["image_path"] = attachments[0]["original_path"]
    candidate = store.create_candidate(f"manual:{draft_id}", snapshot)
    try:
        receipt = store.resolve_candidate(candidate["id"], accept=True, expected_revision=candidate["revision"], operation_id=req.operation_id)
    except ValueError as exc:
        raise _error(exc) from exc
    return {"success": True, "data": receipt}


@router.get("/{mistake_id}/attempts")
def get_attempts(mistake_id: str, book_name: str = "default", before: str = "", limit: int = 30):
    book = _mb(book_name)
    if not book.get(mistake_id):
        raise HTTPException(status_code=404, detail="mistake not found")
    rows = MistakeLifecycleStore(book.store).list_attempts(mistake_id, before=before, limit=max(1, min(limit, 100)))
    return {"success": True, "data": {"items": rows, "next_cursor": rows[-1]["created_at"] if len(rows) == limit else None}}


@router.get("/{mistake_id}/attachments/{attachment_id}")
def get_mistake_attachment(mistake_id: str, attachment_id: str, book_name: str = "default"):
    record = _mb(book_name).get(mistake_id)
    if not record:
        raise HTTPException(status_code=404, detail="mistake not found")
    attachment = next((item for item in record.attachments if item.get("id") == attachment_id), None)
    if not attachment:
        raise HTTPException(status_code=404, detail="attachment not found")
    path = Path(attachment["original_path"]).resolve()
    if not path.is_relative_to(_image_store.image_root.resolve()) or not path.is_file():
        raise HTTPException(status_code=404, detail="attachment file not found")
    return FileResponse(path)


@router.patch("/{mistake_id}")
def patch_mistake(mistake_id: str, req: RecordPatch, book_name: str = "default"):
    try:
        return {"success": True, "data": _store(book_name).change_record(mistake_id, expected_revision=req.expected_revision, operation_id=req.operation_id, changes=req.changes, meaning_changed=req.meaning_changed)}
    except ValueError as exc:
        raise _error(exc) from exc


@router.post("/{mistake_id}/actions")
def act_on_mistake(mistake_id: str, req: RecordAction, book_name: str = "default"):
    actions = {
        "confirm_content": {"content_status": "ready"},
        "confirm_diagnosis": {"diagnosis_status": "confirmed"},
        "defer_diagnosis": {"diagnosis_status": "deferred"},
        "archive": {"visibility": "archived"},
        "restore": {"visibility": "active"},
        "mark_mastered": {"manual_mastered": True},
    }
    if req.action not in actions:
        raise HTTPException(status_code=422, detail="unsupported action")
    try:
        return {"success": True, "data": _store(book_name).change_record(mistake_id, expected_revision=req.expected_revision, operation_id=req.operation_id, changes=actions[req.action])}
    except ValueError as exc:
        raise _error(exc) from exc


@router.get("/{mistake_id}")
def get_mistake_detail(mistake_id: str, book_name: str = "default"):
    book = _mb(book_name)
    record = book.get(mistake_id)
    if not record:
        raise HTTPException(status_code=404, detail="mistake not found")
    attempts = MistakeLifecycleStore(book.store).list_attempts(mistake_id, limit=100000)
    return {"success": True, "data": {**record.to_dict(), **project_mistake(record, attempts),
        "next_review": record.sm2.get("next_review") if record.sm2 else None,
        "recent_attempts": attempts[:3], "attempts_next_cursor": attempts[2]["created_at"] if len(attempts) > 3 else None}}


@review_router.post("")
def create_review_session(req: SessionCreate):
    try:
        return {"success": True, "data": _store(req.book_name).create_review_session(req.mistake_ids, scope=req.book_name)}
    except ValueError as exc:
        raise _error(exc) from exc


@review_router.get("/{session_id}")
def get_review_session(session_id: str, book_name: str = "default"):
    session = _store(book_name).get_review_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="review session not found")
    current_id = session["items"][session["index"]] if session["index"] < len(session["items"]) else ""
    record = _mb(book_name).get(current_id) if current_id else None
    return {"success": True, "data": {**session, "current_item": {
        "id": record.id, "question_text": record.question_text,
        "correct_answer": record.correct_answer if session["revealed"] else "",
        "explanation": record.explanation if session["revealed"] else "",
        "source": record.source, "subject": record.subject,
        "chapter": record.chapter,
    } if record else None}}


@review_router.patch("/{session_id}")
def update_review_session(session_id: str, req: SessionDraft, book_name: str = "default"):
    try:
        return {"success": True, "data": _store(book_name).update_review_draft(session_id, expected_revision=req.expected_revision, answer=req.answer, revealed=req.revealed)}
    except ValueError as exc:
        raise _error(exc) from exc


@review_router.post("/{session_id}/results")
def submit_review_result(session_id: str, req: SessionResult, book_name: str = "default"):
    try:
        return {"success": True, "data": _store(book_name).submit_review_result(session_id, expected_revision=req.expected_revision, operation_id=req.operation_id, result=req.result, hint_used=req.hint_used, judgement_source=req.judgement_source)}
    except ValueError as exc:
        raise _error(exc) from exc
