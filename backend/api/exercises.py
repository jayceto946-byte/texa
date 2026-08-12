"""Exercises API: general question bank CRUD and mistake import."""
from __future__ import annotations

import re
import threading
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile

from backend.job_manager import get_job_manager
from backend.services.exercise_practice import PracticeAnswerService
from backend.schemas import (
    ExerciseAddRequest,
    ExerciseAnalyzeRequest,
    ExerciseAnswerGenerateRequest,
    ExerciseAnswerSaveRequest,
    ExerciseBatchAddRequest,
    ExerciseCandidateOut,
    ExerciseFromMistakeRequest,
    ExerciseImportRollbackRequest,
    ExerciseListRequest,
    ExercisePracticeRequest,
    ExercisePracticeSessionAnswerRequest,
    ExercisePracticeSessionCreateRequest,
    ExerciseToMistakeRequest,
    ExerciseRecordOut,
    ExerciseStatusRequest,
    TextbookExerciseAnalyzeRequest,
)
from config import DATA_DIR, PROGRESS_PATH
from memory.exercise_bank import ExerciseBank, ExerciseRecord, PracticeSession, get_exercise_bank, question_fingerprint
from memory.exercise_file_importer import extract_exercise_text
from memory.exercise_importer import analyze_candidates, attach_answers_by_number, refine_low_confidence_candidates, split_candidate_blocks
from memory.textbook_exercise_importer import extract_textbook_exercise_text
from memory.mistake_book import MistakeRecord, get_mistake_book
from memory.learning_events import LearningEvent, concept_names, get_learning_event_store
from utils.latex_sanitizer import sanitize_latex
from utils.resource_limits import MAX_EXERCISE_UPLOAD_BYTES, copy_stream_limited
from utils.subject_catalog import normalize_subject_value
from utils.thinking_filter import strip_thinking
from backend.services.learning_state import resolve_book_identity

router = APIRouter(prefix="/exercises", tags=["exercises"])
UPLOAD_DIR = DATA_DIR / "uploads" / "exercises"
EXERCISE_ANSWER_JOB_TYPE = "exercise_answer"
_answer_job_lock = threading.Lock()


def _log_learning_event(event_type: str, *, book_name: str = "default", record: ExerciseRecord | None = None, source_type: str = "exercise", source_id: str = "", payload: dict | None = None) -> None:
    try:
        identity = resolve_book_identity(book_name)
        get_learning_event_store().append(LearningEvent(
            event_type=event_type,
            book_id=identity["book_id"],
            book_name=book_name,
            chapter_id=str(record.chapter or "") if record else "",
            subject=record.subject if record else "",
            source_type=source_type,
            source_id=source_id or (record.id if record else ""),
            concept_names=concept_names(record.linked_concepts if record else []),
            payload=payload or {},
        ))
    except Exception as exc:
        print(f"[LearningEvent] exercise event failed: {exc}", flush=True)


def _safe_upload_name(filename: str) -> str:
    raw = Path(filename or "exercise_import").name
    stem = re.sub(r"[^\w\-.\u4e00-\u9fff]+", "_", Path(raw).stem).strip("._") or "exercise_import"
    suffix = Path(raw).suffix.lower()
    return f"{stem[:80]}{suffix}"


def _save_upload(file: UploadFile) -> Path:
    if not file.filename:
        raise ValueError("请选择要上传的文件")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".docx", ".pdf"}:
        raise ValueError("仅支持 .docx 和 .pdf 文件")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / _safe_upload_name(file.filename)
    base = dest.with_suffix("")
    suffix = dest.suffix
    counter = 1
    while dest.exists():
        dest = Path(f"{base}_{counter}{suffix}")
        counter += 1
    copy_stream_limited(file.file, dest, max_bytes=MAX_EXERCISE_UPLOAD_BYTES)
    return dest


def _bank(book_name: str = "default"):
    return get_exercise_bank(book_name, str(PROGRESS_PATH))


def _tags_from_text(tags: str) -> list[str]:
    return [item.strip() for item in tags.split(",") if item.strip()]


def _record_to_out(record: ExerciseRecord) -> ExerciseRecordOut:
    return ExerciseRecordOut(**record.to_dict())



def _candidate_to_add_payload(candidate) -> ExerciseAddRequest:
    return ExerciseAddRequest(
        question_text=candidate.question_text,
        answer=candidate.answer,
        explanation=candidate.explanation,
        source=candidate.source,
        subject=candidate.subject,
        chapter=candidate.chapter,
        tags=", ".join(candidate.tags),
        question_type=candidate.suggested_type,
        difficulty=candidate.difficulty,
        linked_concepts=candidate.linked_concepts,
        origin_type="import_candidate",
        origin_id=candidate.id,
        status="needs_review" if candidate.needs_review else "new",
        notes="; ".join(candidate.reasons),
    )


def _candidate_outputs(candidates, book_name: str) -> list[ExerciseCandidateOut]:
    bank = _bank(book_name)
    existing = {
        question_fingerprint(record.question_text): record.id
        for record in bank.list_all(limit=100000)
        if question_fingerprint(record.question_text)
    }
    output: list[ExerciseCandidateOut] = []
    for candidate in candidates:
        duplicate_of = existing.get(question_fingerprint(candidate.question_text), "")
        candidate.duplicate_of = duplicate_of
        if duplicate_of and "与题库现有题目重复" not in candidate.validation_issues:
            candidate.validation_issues.append("与题库现有题目重复")
        output.append(ExerciseCandidateOut(**candidate.to_dict()))
    return output


def _mistake_from_exercise(
    record: ExerciseRecord,
    user_answer: str = "",
    mistake_type: list[str] | None = None,
    mistake_id: str = "",
) -> MistakeRecord:
    mistake = MistakeRecord(
        question_text=record.question_text,
        user_answer=user_answer.strip(),
        correct_answer=record.answer,
        source=record.source,
        subject=record.subject,
        chapter=record.chapter,
        tags=record.tags,
        mistake_type=mistake_type or ["\u601d\u8def\u5361\u4f4f"],
        difficulty=record.difficulty,
        image_path=record.image_path,
        ocr_text=record.ocr_text,
        explanation=record.explanation,
        linked_concepts=record.linked_concepts,
        notes=f"\u7531\u4e60\u9898\u5e93\u8f6c\u5165\uff1a{record.id}",
    )
    if mistake_id:
        mistake.id = mistake_id
    return mistake


def _practice_answer_service(book_name: str = "default") -> PracticeAnswerService:
    bank = _bank(book_name)
    return PracticeAnswerService(
        bank=bank,
        book_name=book_name,
        mistake_book_provider=lambda: get_mistake_book(
            book_name,
            str(PROGRESS_PATH),
        ),
        mistake_factory=_mistake_from_exercise,
        log_event=lambda event_type, record, payload: _log_learning_event(
            event_type,
            book_name=book_name,
            record=record,
            payload=payload,
        ),
    )


def _practice_session_data(
    bank: ExerciseBank,
    session: PracticeSession,
) -> dict:
    data = session.to_dict()
    current = bank.current_session_record(session)
    data["current_exercise"] = _record_to_out(current).model_dump() if current else None
    data["summary"] = session.summary()
    return data

def _record_from_request(req: ExerciseAddRequest, book_name: str = "default") -> ExerciseRecord:
    return ExerciseRecord(
        question_text=req.question_text.strip(),
        answer=req.answer.strip(),
        explanation=sanitize_latex(strip_thinking(req.explanation.strip())) if req.explanation.strip() else "",
        source=req.source.strip(),
        subject=normalize_subject_value(req.subject, fallback=book_name),
        chapter=req.chapter.strip() or None,
        tags=_tags_from_text(req.tags),
        question_type=req.question_type.strip(),
        difficulty=max(1, min(5, int(req.difficulty or 3))),
        image_path=req.image_path,
        ocr_text=req.ocr_text.strip(),
        linked_concepts=req.linked_concepts,
        origin_type=req.origin_type.strip() or "manual",
        origin_id=req.origin_id.strip(),
        status=req.status.strip() or "new",
        notes=req.notes.strip(),
    )


@router.post("/add")
def add_exercise(req: ExerciseAddRequest, book_name: str = "default"):
    if not req.question_text.strip():
        return {"success": False, "message": "题干不能为空"}
    try:
        record = _record_from_request(req, book_name=book_name)
        rid = _bank(book_name).add(record)
        _log_learning_event("exercise_added", book_name=book_name, record=record, payload={"origin_type": record.origin_type, "status": record.status})
        return {"success": True, "id": rid, "data": _record_to_out(record), "message": "已保存到习题库"}
    except Exception as e:
        return {"success": False, "message": f"保存失败：{e}"}


def _list_exercise_records(req: ExerciseListRequest, bank) -> list[ExerciseRecord]:
    return bank.list_all(
        subject=req.subject or None,
        chapter=req.chapter or None,
        tag=req.tag or None,
        search_kw=req.search_kw,
        status=req.status,
        limit=req.limit,
    )


@router.post("/list")
def list_exercises(req: ExerciseListRequest, book_name: str = "default"):
    records = _list_exercise_records(req, _bank(book_name))
    return {"success": True, "data": [_record_to_out(r) for r in records]}


@router.post("/overview")
def get_exercise_overview(req: ExerciseListRequest, book_name: str = "default"):
    bank = _bank(book_name)
    records = _list_exercise_records(req, bank)
    errors = {}
    try:
        stats = bank.stats(subject=req.subject or None)
    except Exception as exc:
        print(f"[ExerciseOverview] stats unavailable: {exc}", flush=True)
        stats = None
        errors["stats"] = "习题统计暂不可用"
    try:
        active = bank.get_active_practice_session()
        practice_session = _practice_session_data(bank, active) if active else None
    except Exception as exc:
        print(f"[ExerciseOverview] practice session unavailable: {exc}", flush=True)
        practice_session = None
        errors["practice_session"] = "练习会话暂不可用"
    return {
        "success": True,
        "data": {
            "records": [_record_to_out(record) for record in records],
            "stats": stats,
            "practice_session": practice_session,
            "errors": errors,
        },
    }


@router.get("/stats")
def get_exercise_stats(book_name: str = "default", subject: str = ""):
    return {"success": True, "data": _bank(book_name).stats(subject=subject or None)}






@router.post("/upload-analyze")
def upload_and_analyze_exercises(
    file: UploadFile = File(...),
    answer_file: UploadFile | None = File(None),
    source: str = Form(""),
    subject: str = Form(""),
    chapter: str = Form(""),
    limit: int = Form(200),
    use_llm: bool = Form(False),
    llm_max_items: int = Form(20),
    book_name: str = "default",
):
    try:
        saved_path = _save_upload(file)
        extracted = extract_exercise_text(saved_path)
        answer_path = None
        answer_extracted = None
        if answer_file and answer_file.filename:
            answer_path = _save_upload(answer_file)
            answer_extracted = extract_exercise_text(answer_path)
        if not extracted.text.strip():
            return {
                "success": False,
                "message": "未提取到可切分文本。若这是扫描 PDF，需要先接入 OCR。",
                "file": str(saved_path),
                "extract": extracted.to_dict(),
            }
        effective_source = source.strip() or saved_path.name
        effective_subject = normalize_subject_value(subject, fallback=book_name)
        candidates = analyze_candidates(
            split_candidate_blocks(extracted.text, limit=limit),
            source=effective_source,
            subject=effective_subject,
            chapter=chapter.strip(),
            limit=limit,
        )
        if use_llm:
            candidates = refine_low_confidence_candidates(candidates, max_items=llm_max_items)
        paired_answers = attach_answers_by_number(candidates, answer_extracted.text) if answer_extracted and answer_extracted.text.strip() else 0
        data = _candidate_outputs(candidates, book_name)
        needs_llm_count = sum(1 for candidate in candidates if candidate.needs_llm)
        llm_refined_count = sum(1 for candidate in candidates if candidate.refined_by_llm)
        return {
            "success": True,
            "message": f"已从文件解析出 {len(data)} 道候选题",
            "data": data,
            "summary": {
                "total": len(data),
                "needs_llm": needs_llm_count,
                "auto_confident": len(data) - needs_llm_count,
                "llm_refined": llm_refined_count,
                "paired_answers": paired_answers,
            },
            "file": str(saved_path),
            "answer_file": str(answer_path) if answer_path else "",
            "answer_extract": answer_extracted.to_dict() if answer_extracted else None,
            "extract": extracted.to_dict(),
        }
    except Exception as exc:
        return {"success": False, "message": f"文件导入失败：{exc}"}

@router.post("/textbook-analyze")
def analyze_textbook_exercises(req: TextbookExerciseAnalyzeRequest, book_name: str = "default"):
    effective_book = req.book_name.strip() or book_name or "default"
    try:
        extracted = extract_textbook_exercise_text(
            effective_book,
            chapter=req.chapter.strip(),
            page_start=req.page_start,
            page_end=req.page_end,
            source_mode=req.source_mode.strip() or "exercise_sections",
        )
        if not extracted.text.strip():
            return {
                "success": False,
                "message": "未从教材中提取到可切分文本。请确认章节/页码范围，或先用 MinerU/OCR 导入扫描版教材。",
                "extract": extracted.to_dict(),
            }
        if not extracted.chapter.strip():
            return {
                "success": False,
                "message": "无法确定候选题所属章节。请缩小到单个章节的页码范围，或手动填写章节后重试。",
                "extract": extracted.to_dict(),
                "warnings": extracted.warnings or [],
            }
        effective_subject = normalize_subject_value(req.subject, fallback=effective_book)
        chapter = extracted.chapter or req.chapter.strip()
        page_label = ""
        if extracted.page_start:
            page_label = f" p{extracted.page_start}" if not extracted.page_end or extracted.page_end == extracted.page_start else f" p{extracted.page_start}-{extracted.page_end}"
        source = f"{effective_book} / {chapter or '教材抽题'}{page_label}"
        candidates = analyze_candidates(
            split_candidate_blocks(extracted.text, limit=req.limit),
            source=source,
            subject=effective_subject,
            chapter=chapter,
            limit=req.limit,
        )
        if req.use_llm:
            candidates = refine_low_confidence_candidates(candidates, max_items=req.llm_max_items)
        data = _candidate_outputs(candidates, effective_book)
        needs_llm_count = sum(1 for candidate in candidates if candidate.needs_llm)
        llm_refined_count = sum(1 for candidate in candidates if candidate.refined_by_llm)
        warnings = extracted.warnings or []
        return {
            "success": True,
            "message": f"已从教材抽取 {len(data)} 道候选题",
            "data": data,
            "summary": {
                "total": len(data),
                "needs_llm": needs_llm_count,
                "auto_confident": len(data) - needs_llm_count,
                "llm_refined": llm_refined_count,
            },
            "extract": extracted.to_dict(),
            "warnings": warnings,
        }
    except Exception as exc:
        return {"success": False, "message": f"教材抽题失败：{exc}"}
@router.post("/analyze-candidates")
def analyze_exercise_candidates(req: ExerciseAnalyzeRequest, book_name: str = "default"):
    source = req.source.strip()
    subject = normalize_subject_value(req.subject, fallback=book_name)
    chapter = req.chapter.strip()
    raw_candidates = req.candidates or split_candidate_blocks(req.raw_text, limit=req.limit)
    candidates = analyze_candidates(
        raw_candidates,
        source=source,
        subject=subject,
        chapter=chapter,
        known_concepts=req.known_concepts,
        limit=req.limit,
    )
    if req.use_llm:
        candidates = refine_low_confidence_candidates(
            candidates,
            known_concepts=req.known_concepts,
            max_items=req.llm_max_items,
        )
    data = _candidate_outputs(candidates, book_name)
    needs_llm_count = sum(1 for candidate in candidates if candidate.needs_llm)
    llm_refined_count = sum(1 for candidate in candidates if candidate.refined_by_llm)
    return {
        "success": True,
        "data": data,
        "summary": {
            "total": len(data),
            "needs_llm": needs_llm_count,
            "auto_confident": len(data) - needs_llm_count,
            "llm_refined": llm_refined_count,
        },
    }


@router.post("/batch-add")
def batch_add_exercises(req: ExerciseBatchAddRequest, book_name: str = "default"):
    bank = _bank(book_name)
    records = [
        _record_from_request(item, book_name=book_name)
        for item in req.exercises
        if item.question_text.strip()
    ]
    batch = bank.add_batch(records, source_label=req.source_label, allow_duplicates=req.allow_duplicates)
    saved_records = [bank.get(rid) for rid in batch["exercise_ids"]]
    saved = [_record_to_out(record) for record in saved_records if record]
    for record in saved_records:
        if record:
            _log_learning_event(
                "exercise_imported",
                book_name=book_name,
                record=record,
                payload={"origin_type": record.origin_type, "status": record.status, "batch_id": batch["id"]},
            )
    skipped_count = len(batch.get("skipped", []))
    message = f"已导入 {len(saved)} 道候选题"
    if skipped_count:
        message += f"，跳过 {skipped_count} 道重复题"
    return {
        "success": True,
        "data": saved,
        "count": len(saved),
        "skipped": batch.get("skipped", []),
        "batch_id": batch["id"],
        "message": message,
    }

@router.get("/import-batches")
def list_import_batches(book_name: str = "default", limit: int = 20):
    return {"success": True, "data": _bank(book_name).list_import_batches(limit=limit)}


@router.post("/import-batches/rollback")
def rollback_import_batch(req: ExerciseImportRollbackRequest, book_name: str = "default"):
    batch = _bank(book_name).rollback_import_batch(req.batch_id)
    if not batch:
        return {"success": False, "message": "未找到该导入批次"}
    return {
        "success": True,
        "data": batch,
        "message": f"已回滚导入批次，移除 {len(batch.get('exercise_ids', []))} 道习题",
    }


@router.post("/status")
def update_exercise_status(req: ExerciseStatusRequest, book_name: str = "default"):
    record = _bank(book_name).get(req.id)
    if not record:
        return {"success": False, "message": "未找到该习题"}
    record.status = req.status.strip() or "new"
    _bank(book_name).update(record)
    return {"success": True, "message": "状态已更新", "data": _record_to_out(record)}


@router.post("/practice-sessions")
def create_practice_session(req: ExercisePracticeSessionCreateRequest, book_name: str = "default"):
    bank = _bank(book_name)
    try:
        session = bank.create_practice_session(
            subject=req.subject,
            chapter=req.chapter,
            tag=req.tag,
            status=req.status,
            limit=req.limit,
            shuffle=req.shuffle,
        )
    except ValueError as exc:
        return {"success": False, "message": str(exc)}
    return {
        "success": True,
        "data": _practice_session_data(bank, session),
        "message": "练习会话已开始",
    }


@router.get("/practice-sessions/active")
def get_active_practice_session(book_name: str = "default"):
    bank = _bank(book_name)
    session = bank.get_active_practice_session()
    return {
        "success": True,
        "data": _practice_session_data(bank, session) if session else None,
    }


@router.get("/practice-sessions/{session_id}")
def get_practice_session(session_id: str, book_name: str = "default"):
    bank = _bank(book_name)
    session = bank.get_practice_session(session_id)
    if not session:
        return {"success": False, "message": "未找到练习会话"}
    return {"success": True, "data": _practice_session_data(bank, session)}


@router.post("/practice-sessions/{session_id}/answer")
def answer_practice_session(
    session_id: str,
    req: ExercisePracticeSessionAnswerRequest,
    book_name: str = "default",
):
    practice = _practice_answer_service(book_name)
    try:
        result = practice.answer_session(
            session_id,
            exercise_id=req.exercise_id,
            user_answer=req.user_answer,
            quality=req.quality,
            note=req.note,
            add_to_mistake=req.add_to_mistake,
        )
    except ValueError as exc:
        return {"success": False, "message": str(exc)}

    session_data = _practice_session_data(practice.bank, result.session)
    record_data = _record_to_out(result.record).model_dump()
    if result.mistake_error:
        return {
            "success": False,
            "message": f"作答已记录，但写入错题本失败，可重试：{result.mistake_error}",
            "retryable": True,
            "data": session_data,
            "record": record_data,
        }
    message = (
        "本轮练习已完成"
        if result.session.status == "completed"
        else "已记录，进入下一题"
    )
    return {
        "success": True,
        "data": session_data,
        "record": record_data,
        "mistake_id": result.mistake_id,
        "message": message,
    }


def _change_practice_session_status(session_id: str, status: str, book_name: str) -> dict:
    bank = _bank(book_name)
    try:
        session = bank.set_practice_session_status(session_id, status)
    except ValueError as exc:
        return {"success": False, "message": str(exc)}
    return {"success": True, "data": _practice_session_data(bank, session)}


@router.post("/practice-sessions/{session_id}/pause")
def pause_practice_session(session_id: str, book_name: str = "default"):
    return _change_practice_session_status(session_id, "paused", book_name)


@router.post("/practice-sessions/{session_id}/resume")
def resume_practice_session(session_id: str, book_name: str = "default"):
    return _change_practice_session_status(session_id, "active", book_name)


@router.post("/practice-sessions/{session_id}/abandon")
def abandon_practice_session(session_id: str, book_name: str = "default"):
    return _change_practice_session_status(session_id, "abandoned", book_name)

@router.post("/answer/generate")
def generate_exercise_answer(req: ExerciseAnswerGenerateRequest, book_name: str = "default"):
    """Generate an editable draft through the same grounded retrieval/generator path as QA."""
    record = _bank(book_name).get(req.id)
    if not record:
        return {"success": False, "message": "未找到该习题"}
    try:
        from config import get_llm
        from graph.generator import _build_generate_prompt, grounded_failure_message, has_textbook_evidence
        from graph.main_graph import build_initial_state
        from graph.retrieval_node import retrieve_node

        effective_book = book_name
        target_chapters = [record.chapter] if record.chapter else []
        prompt_question = (
            "请为下列习题生成可核对的标准答案。先给结论，再给必要步骤、公式条件和易错点；"
            "只使用检索到的教材证据，不足之处明确说明。\n\n题目：\n" + record.question_text
        )
        state = build_initial_state(
            user_input=record.question_text,
            book_name=effective_book,
            subject=record.subject,
            target_chapters=target_chapters,
            use_textbook_context=True,
        )
        state["intent"] = "application"
        state.update(retrieve_node(state))
        if not has_textbook_evidence(state):
            return {"success": False, "message": grounded_failure_message(state), "retrieval_status": state.get("retrieval_status", "unavailable")}
        state["user_input"] = prompt_question
        draft = get_llm(temperature=0.1).invoke(_build_generate_prompt(state)).content
        draft = sanitize_latex(strip_thinking(str(draft or "").strip()))
        if not draft:
            return {"success": False, "message": "模型未生成有效答案"}
        return {
            "success": True,
            "data": {
                "answer": draft,
                "evidence_count": len(state.get("evidence_items", [])),
                "sources": [
                    {
                        "chapter": item.get("chapter", ""),
                        "section_title": item.get("section_title", ""),
                        "page_idx": item.get("page_idx", -1),
                        "book_role": item.get("book_role", ""),
                    }
                    for item in state.get("evidence_items", [])[:6]
                ],
            },
            "message": "已生成教材 RAG 答案草稿，请检查修改后保存",
        }
    except Exception as exc:
        return {"success": False, "message": f"生成标准答案失败：{exc}"}


def _find_exercise_answer_job(exercise_id: str, book_name: str) -> dict | None:
    for job in get_job_manager().list_jobs(job_type=EXERCISE_ANSWER_JOB_TYPE, limit=200):
        if str(job.get("exercise_id") or "") == exercise_id and str(job.get("book_name") or "default") == book_name:
            return job
    return None


def _run_exercise_answer_job(job_id: str) -> None:
    jobs = get_job_manager()
    job = jobs.get_job(job_id, job_type=EXERCISE_ANSWER_JOB_TYPE)
    if not job:
        return
    with _answer_job_lock:
        try:
            jobs.update_job(job_id, status="running", stage="retrieving", progress=10, message="正在检索教材证据")
            response = generate_exercise_answer(
                ExerciseAnswerGenerateRequest(id=str(job.get("exercise_id") or "")),
                book_name=str(job.get("book_name") or "default"),
            )
            if not response.get("success"):
                message = str(response.get("message") or "标准答案生成失败")
                jobs.update_job(job_id, status="failed", stage="failed", progress=100, message=message, error=message)
                return
            jobs.update_job(
                job_id,
                status="completed",
                stage="completed",
                progress=100,
                message=str(response.get("message") or "标准答案草稿已生成"),
                result=response.get("data") or {},
            )
        except Exception as exc:
            jobs.update_job(job_id, status="failed", stage="failed", progress=100, message=f"标准答案生成失败：{exc}", error=str(exc))


@router.post("/answer/jobs")
def create_exercise_answer_job(req: ExerciseAnswerGenerateRequest, book_name: str = "default"):
    if not _bank(book_name).get(req.id):
        return {"success": False, "message": "未找到该习题"}
    active = _find_exercise_answer_job(req.id, book_name)
    if active and active.get("status") in {"queued", "running"}:
        return {"success": True, "message": "标准答案正在后台生成", "job_id": active["id"], "data": active}
    job = get_job_manager().create_job(
        EXERCISE_ANSWER_JOB_TYPE,
        {"exercise_id": req.id, "book_name": book_name},
        status="queued",
        stage="queued",
        progress=0,
        message="已加入标准答案生成队列",
    )
    threading.Thread(target=_run_exercise_answer_job, args=(job["id"],), daemon=True).start()
    return {"success": True, "message": "标准答案已转入后台生成", "job_id": job["id"], "data": job}


@router.get("/answer/jobs/latest")
def latest_exercise_answer_job(id: str, book_name: str = "default"):
    job = _find_exercise_answer_job(id, book_name)
    return {"success": True, "data": job}


@router.get("/answer/jobs/{job_id}")
def get_exercise_answer_job(job_id: str):
    job = get_job_manager().get_job(job_id, job_type=EXERCISE_ANSWER_JOB_TYPE)
    if not job:
        return {"success": False, "message": "未找到标准答案生成任务"}
    return {"success": True, "data": job}


@router.post("/answer/save")
def save_exercise_answer(req: ExerciseAnswerSaveRequest, book_name: str = "default"):
    record = _bank(book_name).get(req.id)
    if not record:
        return {"success": False, "message": "未找到该习题"}
    answer = sanitize_latex(strip_thinking(req.answer.strip()))
    if not answer:
        return {"success": False, "message": "标准答案不能为空"}
    record.answer = answer
    if req.explanation.strip():
        record.explanation = sanitize_latex(strip_thinking(req.explanation.strip()))
    _bank(book_name).update(record)
    _log_learning_event("exercise_answer_saved", book_name=book_name, record=record, payload={"answer_source": "rag_edited"})
    return {"success": True, "message": "标准答案已保存", "data": _record_to_out(record)}


@router.post("/practice")
def practice_exercise(req: ExercisePracticeRequest, book_name: str = "default"):
    bank = _bank(book_name)
    record = bank.record_practice(req.id, user_answer=req.user_answer, quality=req.quality, add_note=req.note)
    if not record:
        return {"success": False, "message": "未找到该习题"}

    _log_learning_event("exercise_practiced", book_name=book_name, record=record, payload={"quality": req.quality, "status": record.status, "add_to_mistake": req.add_to_mistake})
    mistake_id = ""
    if req.add_to_mistake:
        mb = get_mistake_book(book_name, str(PROGRESS_PATH))
        mistake_id = mb.add(_mistake_from_exercise(record, user_answer=req.user_answer))
        _log_learning_event("exercise_to_mistake", book_name=book_name, record=record, payload={"mistake_id": mistake_id, "trigger": "practice"})
    return {"success": True, "message": "练习结果已记录", "data": _record_to_out(record), "mistake_id": mistake_id}


@router.post("/to-mistake")
def exercise_to_mistake(req: ExerciseToMistakeRequest, book_name: str = "default"):
    record = _bank(book_name).get(req.id)
    if not record:
        return {"success": False, "message": "未找到该习题"}
    mb = get_mistake_book(book_name, str(PROGRESS_PATH))
    mistake_id = mb.add(_mistake_from_exercise(record, user_answer=req.user_answer, mistake_type=req.mistake_type))
    _log_learning_event("exercise_to_mistake", book_name=book_name, record=record, payload={"mistake_id": mistake_id, "trigger": "manual"})
    record.status = "needs_review"
    _bank(book_name).update(record)
    return {"success": True, "message": "已转入错题本", "id": mistake_id, "data": _record_to_out(record)}


@router.post("/from-mistake")
def add_from_mistake(req: ExerciseFromMistakeRequest, book_name: str = "default"):
    mb = get_mistake_book(book_name, str(PROGRESS_PATH))
    mistake = mb.get(req.mistake_id)
    if not mistake:
        return {"success": False, "message": "未找到该错题"}

    bank = _bank(book_name)
    existing = bank.find_by_origin("mistake", mistake.id)
    if existing:
        return {"success": True, "message": "该错题已在习题库中", "data": _record_to_out(existing), "id": existing.id}

    record = ExerciseRecord(
        question_text=mistake.question_text,
        answer=mistake.correct_answer,
        explanation=mistake.explanation,
        source=mistake.source,
        subject=mistake.subject or book_name,
        chapter=mistake.chapter,
        tags=mistake.tags,
        question_type="错题转入",
        difficulty=mistake.difficulty,
        image_path=mistake.image_path,
        ocr_text=mistake.ocr_text,
        linked_concepts=mistake.linked_concepts,
        origin_type="mistake",
        origin_id=mistake.id,
        status="needs_review",
        notes="由错题本转入",
    )
    rid = bank.add(record)
    _log_learning_event("exercise_added", book_name=book_name, record=record, payload={"origin_type": record.origin_type, "origin_id": record.origin_id})
    return {"success": True, "message": "已从错题转入习题库", "id": rid, "data": _record_to_out(record)}

@router.get("/{exercise_id}")
def get_exercise_detail(exercise_id: str, book_name: str = "default"):
    record = _bank(book_name).get(exercise_id)
    if not record:
        return {"success": False, "message": "未找到该习题"}
    return {"success": True, "data": _record_to_out(record)}


@router.delete("/{exercise_id}")
def delete_exercise(exercise_id: str, book_name: str = "default"):
    _bank(book_name).delete(exercise_id)
    return {"success": True, "message": f"已删除 {exercise_id}"}
