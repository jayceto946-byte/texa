"""Mistakes API: CRUD, review, provider-neutral vision and explanations."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from fastapi.responses import FileResponse, StreamingResponse

from backend.services.mistake_images import MistakeImageStore
from backend.services.multimodal_bridge import KimiVisionBridge, VisualProblemIR, build_solution_prompt
from backend.services.learning_task import (
    blocking_required_inputs,
    get_learning_task_store,
    mark_required_inputs,
)
from backend.services.answer_verification import (
    derive_required_outputs,
    verification_notice,
    verify_answer,
)

from backend.schemas import (
    MistakeAddRequest,
    MistakeExplainRequest,
    MistakeChatRequest,
    MistakeListRequest,
    MistakeRecordOut,
    MistakeReviewRequest,
    MistakeStatsOut,
    WeakPointOut,
)
from config import IMAGES_PATH, PROGRESS_PATH
from memory.mistake_book import MistakeRecord, get_mistake_book
from memory.learning_events import LearningEvent, concept_names, get_learning_event_store
from utils.latex_sanitizer import sanitize_latex
from utils.subject_catalog import normalize_subject_value
from utils.thinking_filter import ThinkingFilter, strip_thinking
from backend.services.learning_state import resolve_book_identity

router = APIRouter(prefix="/mistakes", tags=["mistakes"])

ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
OCR_MAX_SIDE = int(os.getenv("MISTAKE_OCR_MAX_SIDE", "1600"))
OCR_JPEG_QUALITY = int(os.getenv("MISTAKE_OCR_JPEG_QUALITY", "86"))
KIMI_VISION_MODEL = os.getenv("KIMI_VISION_MODEL", "kimi-k2.5")
PENDING_IMAGE_MAX_AGE_SECONDS = 24 * 60 * 60

_image_store = MistakeImageStore(
    images_path=Path(IMAGES_PATH),
    allowed_extensions=frozenset(ALLOWED_IMAGE_EXTS),
    max_image_bytes=MAX_IMAGE_BYTES,
    ocr_max_side=OCR_MAX_SIDE,
    ocr_jpeg_quality=OCR_JPEG_QUALITY,
    pending_max_age_seconds=PENDING_IMAGE_MAX_AGE_SECONDS,
)


def _log_learning_event(event_type: str, *, book_name: str = "default", record: MistakeRecord | None = None, payload: dict | None = None) -> None:
    try:
        identity = resolve_book_identity(book_name)
        get_learning_event_store().append(LearningEvent(
            event_type=event_type,
            book_id=identity["book_id"],
            book_name=book_name,
            chapter_id=str(record.chapter or "") if record else "",
            subject=record.subject if record else "",
            source_type="mistake",
            source_id=record.id if record else "",
            concept_names=concept_names(record.linked_concepts if record else []),
            payload=payload or {},
        ))
    except Exception as exc:
        print(f"[LearningEvent] mistake event failed: {exc}", flush=True)


def _mb(book_name: str = "default"):
    return get_mistake_book(book_name, str(PROGRESS_PATH))


def _record_to_out(record: MistakeRecord) -> MistakeRecordOut:
    return MistakeRecordOut(
        id=record.id,
        book_id=record.book_id,
        question_text=record.question_text,
        user_answer=record.user_answer,
        correct_answer=record.correct_answer,
        source=record.source,
        subject=record.subject,
        chapter=record.chapter,
        tags=record.tags,
        mistake_type=record.mistake_type,
        difficulty=record.difficulty,
        created_at=record.created_at,
        image_path=record.image_path,
        ocr_text=record.ocr_text,
        visual_ir=record.visual_ir,
        explanation=record.explanation,
        linked_concepts=record.linked_concepts,
        review_history=record.review_history,
        next_review=record.sm2.get("next_review") if record.sm2 else None,
        interval=record.sm2.get("interval") if record.sm2 else None,
    )


def _tags_from_text(tags: str) -> list[str]:
    return [item.strip() for item in tags.split(",") if item.strip()]


def _record_from_request(req: MistakeAddRequest, book_name: str = "default") -> MistakeRecord:
    return MistakeRecord(
        question_text=req.question_text.strip(),
        user_answer=req.user_answer.strip(),
        correct_answer=req.correct_answer.strip(),
        source=req.source.strip(),
        subject=normalize_subject_value(req.subject, fallback=book_name),
        chapter=req.chapter.strip() or None,
        tags=_tags_from_text(req.tags),
        mistake_type=req.mistake_type,
        difficulty=max(1, min(5, int(req.difficulty or 3))),
        image_path=req.image_path,
        ocr_text=req.ocr_text.strip(),
        visual_ir=dict(req.visual_ir or {}),
        explanation=sanitize_latex(strip_thinking(req.explanation.strip())) if req.explanation.strip() else "",
    )


def _parse_keyword_json(text: str) -> list[str]:
    cleaned = strip_thinking(text or "").strip()
    match = re.search(r"\[[\s\S]*\]", cleaned)
    if match:
        cleaned = match.group(0)
    try:
        data = json.loads(cleaned)
    except Exception:
        data = [line.strip(" -??,\t") for line in cleaned.splitlines() if line.strip()]

    keywords: list[str] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                name = item.strip()
            elif isinstance(item, dict):
                name = str(item.get("name") or item.get("concept") or "").strip()
            else:
                name = ""
            if name and name not in keywords:
                keywords.append(name)
            if len(keywords) >= 3:
                break
    return keywords


def _extract_mistake_keywords_with_llm(record: MistakeRecord, explanation: str = "") -> list[str]:
    try:
        from config import get_llm

        prompt = f"""Extract 1 to 3 key academic concepts or method names from this mistaken problem.

Rules:
1. Return only concepts that are central to the problem, not generic words such as method, step, condition, or problem.
2. Prefer standard textbook / knowledge-graph terminology.
3. Output only a JSON array of strings, for example ["limit", "L'Hopital rule"]. Do not explain.

Question:
{record.question_text[:1600]}

Correct answer:
{record.correct_answer[:600] or "not provided"}

Explanation:
{explanation[:1600] or record.explanation[:1600] or "not generated"}
"""
        result = get_llm().invoke(prompt).content
        return _parse_keyword_json(result)
    except Exception as e:
        print(f"[MistakeConcepts] LLM keyword extraction failed: {e}", flush=True)
        return []


def _dedupe_concepts(concepts: list[dict], limit: int = 3) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for item in concepts:
        name = str(item.get("name", "")).strip()
        cid = str(item.get("concept_id", "")).strip()
        key = cid or name
        if not name or key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _link_mistake_concepts(
    record: MistakeRecord,
    explanation: str = "",
    book_name: str = "default",
    *,
    allow_llm_fallback: bool = True,
) -> list[dict]:
    try:
        from knowledge.concept_linker import ConceptLinker

        linker = ConceptLinker(book_name)
        if not getattr(linker.kg, "_is_local", False):
            return []

        question = "\n".join(part for part in [record.question_text, record.correct_answer] if part)
        concepts = linker.link(
            question=question,
            answer=explanation or record.explanation,
            tags=record.tags,
            intent="mistake",
            limit=3,
        )
        for item in concepts:
            item["confidence"] = max(float(item.get("confidence", 0) or 0), 0.999)
            item["source"] = "mistake_linker"

        if not concepts and allow_llm_fallback:
            for keyword in _extract_mistake_keywords_with_llm(record, explanation):
                linked = linker.link(matched_concepts=[keyword], question=keyword, intent="mistake", limit=1)
                if not linked:
                    linked = linker.link(question=keyword, intent="mistake", limit=1)
                for item in linked:
                    item = dict(item)
                    item["confidence"] = 1.0
                    item["source"] = "mistake_llm"
                    item["evidence"] = keyword
                    concepts.append(item)

        return _dedupe_concepts(concepts, limit=3)
    except Exception as e:
        print(f"[MistakeConcepts] KG linking failed: {e}", flush=True)
        return []


def _persist_mistake_concepts(record: MistakeRecord, explanation: str = "", book_name: str = "default") -> list[dict]:
    concepts = _link_mistake_concepts(record, explanation=explanation, book_name=book_name)
    if not concepts:
        return []
    record.linked_concepts = concepts
    try:
        from knowledge.concept_memory import ConceptMemory

        ConceptMemory(book_name).log_weakness(concepts, record.question_text, "mistake", source="mistake", subject=record.subject)
    except Exception as e:
        print(f"[ConceptMemory] mistake record failed: {e}", flush=True)
    return concepts



def _ocr_image_with_kimi(image_path: Path, *, user_question: str = "", subject: str = "") -> VisualProblemIR:
    """Compatibility entrypoint for OCR plus visual-semantic extraction."""
    return KimiVisionBridge().analyze(image_path, user_question=user_question, subject=subject)

def _build_image_solution_prompt(ocr_text: str, user_answer: str = "", subject: str = "", tags: str = "") -> str:
    return build_solution_prompt(
        VisualProblemIR(problem_text=ocr_text, visual_type="text_only"),
        user_answer=user_answer, subject=subject, tags=tags,
    )

def _solve_ocr_text(ocr_text: str, user_answer: str = "", subject: str = "", tags: str = "") -> str:
    from config import get_llm

    prompt = _build_image_solution_prompt(ocr_text, user_answer=user_answer, subject=subject, tags=tags)
    result = get_llm().invoke(prompt).content
    return sanitize_latex(strip_thinking(result))


def _solve_visual_ir(
    visual_ir: VisualProblemIR,
    *,
    user_question: str = "",
    user_answer: str = "",
    subject: str = "",
    tags: str = "",
    supplemental_visual_irs: list[VisualProblemIR] | None = None,
    answer_policy: str = "exact",
) -> str:
    prompt = build_solution_prompt(
        visual_ir, user_question=user_question, user_answer=user_answer,
        subject=subject, tags=tags, supplemental_visual_irs=supplemental_visual_irs,
        answer_policy=answer_policy,
    )
    return sanitize_latex(strip_thinking(
        _get_image_reasoning_llm(
            request_timeout=420,
            max_retries=0,
        ).invoke(prompt).content
    ))


def _iter_visual_solution_chunks(
    visual_ir: VisualProblemIR,
    *,
    user_question: str = "",
    user_answer: str = "",
    subject: str = "",
    tags: str = "",
    supplemental_visual_irs: list[VisualProblemIR] | None = None,
    answer_policy: str = "exact",
):
    """Stream only user-visible answer text; provider thinking is never emitted."""

    prompt = build_solution_prompt(
        visual_ir, user_question=user_question, user_answer=user_answer,
        subject=subject, tags=tags, supplemental_visual_irs=supplemental_visual_irs,
        answer_policy=answer_policy,
    )
    thinking_filter = ThinkingFilter()
    for chunk in _get_image_reasoning_llm(
        request_timeout=420,
        max_retries=0,
    ).stream(prompt):
        clean = thinking_filter.filter(str(getattr(chunk, "content", "") or ""))
        if clean:
            yield clean
    tail = thinking_filter.flush()
    if tail:
        yield tail


def _get_image_reasoning_llm(**kwargs):
    """Use the integrated model for native mode, or the reasoning role for split mode."""
    import os
    from config import get_llm, get_model_role_config
    from llm.factory import build_chat_model

    if os.getenv("LLM_MULTIMODAL_MODE", "split").strip().lower() == "native":
        return build_chat_model(get_model_role_config("vision"), 1, **kwargs)
    return get_llm(**kwargs)


@router.post("/add")
def add_mistake(req: MistakeAddRequest, book_name: str = "default"):
    committed_image: str | None = None
    image_was_moved = False
    try:
        committed_image, image_was_moved = _image_store.commit_pending(req.image_path)
        record = _record_from_request(req, book_name=book_name)
        record.image_path = committed_image
        _persist_mistake_concepts(record, explanation=record.explanation, book_name=book_name)
        mid = _mb(book_name).add(record)
        _log_learning_event("mistake_added", book_name=book_name, record=record, payload={"difficulty": record.difficulty, "mistake_type": record.mistake_type, "tags": record.tags})
        return {"success": True, "id": mid, "data": _record_to_out(record), "message": f"已保存（{mid}）"}
    except Exception as e:
        if image_was_moved:
            _image_store.delete(committed_image)
        return {
            "success": False,
            "message": f"保存失败：{e}。如果提示 disk I/O error，请检查 data/progress 的 SQLite 文件权限或残留 journal。",
        }

def _list_mistake_records(req: MistakeListRequest, mistake_book) -> list[MistakeRecord]:
    records = mistake_book.list_all(
        subject=req.subject or None,
        chapter=req.chapter or None,
        tag=req.tag or None,
        limit=req.limit,
    )
    if req.search_kw.strip():
        kw = req.search_kw.strip().lower()
        records = [
            record
            for record in records
            if kw in record.question_text.lower()
            or kw in record.ocr_text.lower()
            or kw in record.explanation.lower()
            or any(kw in tag.lower() for tag in record.tags)
        ]
    return records


@router.post("/list")
def list_mistakes(req: MistakeListRequest, book_name: str = "default"):
    records = _list_mistake_records(req, _mb(book_name))
    return {"success": True, "data": [_record_to_out(record) for record in records]}


@router.post("/overview")
def get_mistake_overview(req: MistakeListRequest, book_name: str = "default"):
    mistake_book = _mb(book_name)
    records = _list_mistake_records(req, mistake_book)
    errors = {}
    try:
        due = mistake_book.get_due(subject=req.subject or None)
    except Exception as exc:
        print(f"[MistakeOverview] due queue unavailable: {exc}", flush=True)
        due = []
        errors["due_records"] = "到期复习队列暂不可用"
    return {
        "success": True,
        "data": {
            "records": [_record_to_out(record) for record in records],
            "due_records": [_record_to_out(record) for record in due],
            "errors": errors,
        },
    }


@router.get("/due")
def get_due_mistakes(subject: str = "", book_name: str = "default"):
    records = _mb(book_name).get_due(subject=subject or None)
    return {"success": True, "data": [_record_to_out(r) for r in records]}


@router.post("/recognize-image")
def recognize_mistake_image(file: UploadFile = File(...)):
    image_path: Path | None = None
    try:
        image_path = _image_store.save_upload(file)
        visual_ir = _ocr_image_with_kimi(image_path)
        if not visual_ir.problem_text and not visual_ir.visual_summary:
            _image_store.delete(image_path)
            return {
                "success": False,
                "message": "识图模型未返回有效 OCR 文本，请手动输入题干后保存。",
                "ocr_text": "",
            }
        return {
            "success": True,
            "message": "识图模型已提取题干和图形语义，请校对不确定项后再保存或解答。",
            "image_path": str(image_path),
            "ocr_text": visual_ir.problem_text,
            "visual_ir": visual_ir.to_dict(),
            "ocr_provider": "kimi-vision-bridge-v1",
            "optimized": image_path.name.endswith("_ocr.jpg"),
        }
    except Exception as e:
        _image_store.delete(image_path)
        return {"success": False, "message": f"OCR 识别失败: {e}"}

@router.post("/solve-image")
def solve_mistake_image(
    file: UploadFile = File(...),
    user_answer: str = Form(""),
    subject: str = Form(""),
    tags: str = Form(""),
    question: str = Form(""),
    import_to_mistakes: bool = Form(False),
    book_name: str = Form("default"),
    conversation_id: str = Form(""),
    turn_id: str = Form(""),
):
    image_path: Path | None = None
    try:
        image_path = _image_store.save_upload(file)
        visual_ir = _ocr_image_with_kimi(image_path, user_question=question, subject=subject)
        if not visual_ir.problem_text and not visual_ir.visual_summary:
            _image_store.delete(image_path)
            return {
                "success": False,
                "message": "识图模型未返回有效 OCR 文本，请手动补充题干后再解答。",
                "ocr_text": "",
            }
        missing_inputs = blocking_required_inputs(visual_ir.required_inputs)
        if missing_inputs:
            task = _create_visual_learning_task(
                visual_ir=visual_ir,
                image_path=image_path,
                question=question,
                user_answer=user_answer,
                subject=subject,
                tags=tags,
                book_name=book_name,
                import_to_mistakes=import_to_mistakes,
                conversation_id=conversation_id,
                turn_id=turn_id,
            )
            return {
                "success": True,
                "message": "精确解答需要补充材料。你可以补充后继续，或暂时只看方法。",
                "image_path": str(image_path),
                "ocr_text": visual_ir.problem_text,
                "visual_ir": visual_ir.to_dict(),
                "learning_task": task.to_dict(public=True),
            }
        explanation = _solve_visual_ir(
            visual_ir, user_question=question, user_answer=user_answer,
            subject=subject, tags=tags,
        )
        explanation, answer_verification = _verify_visual_answer(
            explanation, question=question, visual_ir=visual_ir,
        )
        draft = MistakeRecord(
            question_text=visual_ir.problem_text or visual_ir.visual_summary,
            user_answer=user_answer, subject=normalize_subject_value(subject, fallback=book_name),
            tags=_tags_from_text(tags), image_path=str(image_path),
            ocr_text=visual_ir.problem_text, visual_ir=visual_ir.to_dict(), explanation=explanation,
            source="问答图片上传",
        )
        # The answer is user-facing latency-critical. Link against the local KG
        # only; an extra LLM concept-extraction call must not delay delivery.
        linked_concepts = _link_mistake_concepts(
            draft, explanation=explanation, book_name=book_name,
            allow_llm_fallback=False,
        )
        if linked_concepts:
            try:
                from knowledge.concept_memory import ConceptMemory

                ConceptMemory(book_name).log_exposure(
                    linked_concepts, visual_ir.problem_text or question, "image_qa",
                    source="chat_image", subject=draft.subject,
                )
            except Exception as exc:
                print(f"[ConceptMemory] image QA exposure failed: {exc}", flush=True)
        mistake_id = ""
        if import_to_mistakes:
            committed_path, _ = _image_store.commit_pending(str(image_path))
            image_path = Path(committed_path)
            draft.image_path = committed_path
            draft.linked_concepts = linked_concepts
            mistake_id = _mb(book_name).add(draft)
            _log_learning_event("mistake_added", book_name=book_name, record=draft, payload={"origin": "chat_image"})
        return {
            "success": True,
            "message": "识图模型已提取题干与图形关系并完成讲解，请校对视觉不确定项。",
            "image_path": str(image_path),
            "ocr_text": visual_ir.problem_text,
            "visual_ir": visual_ir.to_dict(),
            "ocr_provider": "kimi-vision-bridge-v1",
            "optimized": image_path.name.endswith("_ocr.jpg"),
            "explanation": explanation,
            "linked_concepts": linked_concepts,
            "mistake_id": mistake_id,
            "answer_verification": answer_verification,
        }
    except Exception as e:
        _image_store.delete(image_path)
        return {"success": False, "message": f"讲解失败: {e}"}


def _sse_event(stage: str, *, activity: dict | None = None, **payload) -> str:
    event = {"stage": stage, **payload}
    if activity:
        event["activity"] = activity
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _create_visual_learning_task(
    *,
    visual_ir: VisualProblemIR,
    image_path: Path,
    question: str,
    user_answer: str,
    subject: str,
    tags: str,
    book_name: str,
    import_to_mistakes: bool,
    conversation_id: str = "",
    turn_id: str = "",
):
    task = get_learning_task_store().create(
        task_type="visual_qa",
        goal=question or visual_ir.problem_text or "完整讲解图片题",
        conversation_id=conversation_id,
        turn_id=turn_id,
        answer_mode="visual_grounded",
        required_inputs=visual_ir.required_inputs,
        required_outputs=derive_required_outputs(
            question or visual_ir.problem_text,
            intent="application",
            answer_mode="visual_grounded",
        ),
        artifacts={
            "image_path": str(image_path),
            "visual_ir": visual_ir.to_dict(),
            "supplemental_visual_irs": [],
            "question": question,
            "user_answer": user_answer,
            "subject": subject,
            "tags": tags,
            "book_name": book_name,
            "import_to_mistakes": bool(import_to_mistakes),
            "completed_derivation": "",
        },
        status="waiting_for_input",
    )
    return task


def _verify_visual_answer(
    answer: str,
    *,
    question: str,
    visual_ir: VisualProblemIR,
    supplemental_visual_irs: list[VisualProblemIR] | None = None,
    required_outputs: list[dict] | None = None,
    answer_policy: str = "exact",
) -> tuple[str, dict]:
    evidence = [visual_ir.to_dict(), *[item.to_dict() for item in (supplemental_visual_irs or [])]]
    result = verify_answer(
        answer,
        required_outputs=required_outputs or derive_required_outputs(
            question or visual_ir.problem_text, intent="application", answer_mode="visual_grounded",
        ),
        evidence_items=evidence,
        answer_policy=answer_policy,
    )
    notice = verification_notice(result)
    final = answer.rstrip() + (f"\n\n{notice}" if notice and notice not in answer else "")
    return final, result


def _stream_solution_events(
    visual_ir: VisualProblemIR,
    *,
    user_question: str,
    user_answer: str,
    subject: str,
    tags: str,
    reason_label: str,
    reason_detail: str,
    supplemental_visual_irs: list[VisualProblemIR] | None = None,
    answer_policy: str = "exact",
):
    """Yield observable reasoning/generation events and return the final answer."""
    step_started = time.perf_counter()
    yield _sse_event("activity", activity={
        "id": "reason", "kind": "reasoning", "label": reason_label,
        "status": "active", "detail": reason_detail,
    })
    chunks: list[str] = []
    first_visible_chunk = True
    for chunk in _iter_visual_solution_chunks(
        visual_ir,
        user_question=user_question,
        user_answer=user_answer,
        subject=subject,
        tags=tags,
        supplemental_visual_irs=supplemental_visual_irs,
        answer_policy=answer_policy,
    ):
        if first_visible_chunk:
            first_visible_chunk = False
            yield _sse_event("activity", activity={
                "id": "reason", "kind": "reasoning", "label": reason_label,
                "status": "completed", "detail": "已形成可展示的解题路径",
                "duration_ms": round((time.perf_counter() - step_started) * 1000, 2),
            })
        chunks.append(chunk)
        yield _sse_event("generate", chunk=chunk, done=False, activity={
            "id": "generate", "kind": "generation", "label": "生成答案",
            "status": "active", "detail": "正在逐步输出正式讲解",
        })

    if first_visible_chunk:
        yield _sse_event("activity", activity={
            "id": "reason", "kind": "reasoning", "label": reason_label,
            "status": "completed", "detail": "推理已结束，未产生可展示正文",
            "duration_ms": round((time.perf_counter() - step_started) * 1000, 2),
        })
    raw_explanation = "".join(chunks).strip()
    explanation = sanitize_latex(raw_explanation)
    if explanation != raw_explanation:
        yield _sse_event("generate", chunk=explanation, replace=True, done=False, activity={
            "id": "generate", "kind": "generation", "label": "生成答案",
            "status": "active", "detail": "正在规范公式与答案格式",
        })
    yield _sse_event("generate", chunk="", done=True, activity={
        "id": "generate", "kind": "generation", "label": "生成答案",
        "status": "completed", "detail": "正式讲解已生成",
    })
    return explanation


@router.post("/solve-image-stream")
def solve_mistake_image_stream(
    file: UploadFile = File(...),
    user_answer: str = Form(""),
    subject: str = Form(""),
    tags: str = Form(""),
    question: str = Form(""),
    import_to_mistakes: bool = Form(False),
    book_name: str = Form("default"),
    conversation_id: str = Form(""),
    turn_id: str = Form(""),
):
    """Observable image solution path. Each event reflects completed real work."""
    def events():
        image_path: Path | None = None
        started = time.perf_counter()
        try:
            step_started = time.perf_counter()
            image_path = _image_store.save_upload(file)
            yield _sse_event("activity", activity={
                "id": "attachment", "kind": "tool", "label": "读取题目图片",
                "status": "completed", "detail": "图片已安全接收并完成尺寸优化",
                "duration_ms": round((time.perf_counter() - step_started) * 1000, 2),
            })

            yield _sse_event("activity", activity={
                "id": "vision", "kind": "tool", "label": "识图模型解析图片",
                "status": "active", "detail": "正在提取题干、公式、图形实体与连接关系",
            })
            step_started = time.perf_counter()
            visual_ir = _ocr_image_with_kimi(image_path, user_question=question, subject=subject)
            if not visual_ir.problem_text and not visual_ir.visual_summary:
                raise RuntimeError("识图模型未返回有效题目内容")
            entity_count = len(visual_ir.entities)
            relation_count = len(visual_ir.relations)
            uncertainty_count = len(visual_ir.uncertainties)
            yield _sse_event("activity", activity={
                "id": "vision", "kind": "tool", "label": "识图模型解析图片",
                "status": "completed",
                "detail": f"识别为 {visual_ir.visual_type}；{entity_count} 个实体、{relation_count} 条关系、{uncertainty_count} 处不确定项",
                "duration_ms": round((time.perf_counter() - step_started) * 1000, 2),
                "meta": {"visual_type": visual_ir.visual_type, "uncertainties": visual_ir.uncertainties[:5]},
            })

            missing_inputs = blocking_required_inputs(visual_ir.required_inputs)
            if missing_inputs:
                task = _create_visual_learning_task(
                    visual_ir=visual_ir,
                    image_path=image_path,
                    question=question,
                    user_answer=user_answer,
                    subject=subject,
                    tags=tags,
                    book_name=book_name,
                    import_to_mistakes=import_to_mistakes,
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                )
                yield _sse_event("waiting_for_input", done=True, result={
                    "success": True,
                    "question_text": visual_ir.problem_text,
                    "visual_ir": visual_ir.to_dict(),
                    "image_path": str(image_path),
                    "learning_task": task.to_dict(public=True),
                }, activity={
                    "id": "required-inputs",
                    "kind": "system",
                    "label": "等待补充材料",
                    "status": "completed",
                    "detail": f"有 {len(missing_inputs)} 项缺失材料会影响最终结论，已暂停精确解答",
                }, total_ms=round((time.perf_counter() - started) * 1000, 2))
                return

            explanation = yield from _stream_solution_events(
                visual_ir,
                user_question=question,
                user_answer=user_answer,
                subject=subject,
                tags=tags,
                reason_label="综合题干与视觉关系",
                reason_detail="正在依据结构化视觉证据组织可验证的解题步骤",
            )
            verified_explanation, answer_verification = _verify_visual_answer(
                explanation, question=question, visual_ir=visual_ir,
            )
            if verified_explanation != explanation:
                explanation = verified_explanation
                yield _sse_event("generate", chunk=explanation, replace=True, done=False, activity={
                    "id": "verify", "kind": "evidence", "label": "核对答案完整性",
                    "status": "completed", "detail": "已标记无法确定性验证的结果",
                })
                yield _sse_event("generate", chunk="", done=True)

            draft = MistakeRecord(
                question_text=visual_ir.problem_text or visual_ir.visual_summary,
                user_answer=user_answer, subject=normalize_subject_value(subject, fallback=book_name),
                tags=_tags_from_text(tags), image_path=str(image_path),
                ocr_text=visual_ir.problem_text, visual_ir=visual_ir.to_dict(), explanation=explanation,
                source="问答图片上传",
            )
            linked_concepts = _link_mistake_concepts(
                draft, explanation=explanation, book_name=book_name, allow_llm_fallback=False,
            )
            if linked_concepts:
                try:
                    from knowledge.concept_memory import ConceptMemory
                    ConceptMemory(book_name).log_exposure(
                        linked_concepts, visual_ir.problem_text or question, "image_qa",
                        source="chat_image", subject=draft.subject,
                    )
                except Exception as exc:
                    print(f"[ConceptMemory] image QA exposure failed: {exc}", flush=True)

            mistake_id = ""
            if import_to_mistakes:
                committed_path, _ = _image_store.commit_pending(str(image_path))
                image_path = Path(committed_path)
                draft.image_path = committed_path
                draft.linked_concepts = linked_concepts
                mistake_id = _mb(book_name).add(draft)
                _log_learning_event("mistake_added", book_name=book_name, record=draft, payload={"origin": "chat_image"})
            yield _sse_event("done", done=True, result={
                "success": True, "explanation": explanation, "linked_concepts": linked_concepts,
                "question_text": visual_ir.problem_text, "visual_ir": visual_ir.to_dict(),
                "image_path": str(image_path), "mistake_id": mistake_id,
                "answer_verification": answer_verification,
            }, activity={
                "id": "memory", "kind": "memory", "label": "关联学习记录",
                "status": "completed" if linked_concepts or mistake_id else "skipped",
                "detail": (
                    f"已关联 {len(linked_concepts)} 个概念" + ("并导入错题本" if mistake_id else "")
                    if linked_concepts or mistake_id else "未发现可靠概念，未写入错题本"
                ),
            }, total_ms=round((time.perf_counter() - started) * 1000, 2))
        except GeneratorExit:
            raise
        except Exception as exc:
            _image_store.delete(image_path)
            yield _sse_event("error", done=True, message=str(exc), activity={
                "id": "error", "kind": "system", "label": "处理失败",
                "status": "failed", "detail": str(exc),
            })

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/visual-tasks/{task_id}/resume-stream")
def resume_visual_learning_task(
    task_id: str,
    action: str = Form(...),
    file: UploadFile | None = File(None),
):
    """Resume one paused visual task without re-reading its original image."""
    def events():
        store = get_learning_task_store()
        task = store.get(task_id)
        supplemental_path: Path | None = None
        if not task or task.task_type != "visual_qa":
            yield _sse_event("error", done=True, message="未找到可恢复的图片学习任务")
            return
        if task.status == "completed":
            yield _sse_event("done", done=True, result={
                "success": True,
                "explanation": str((task.artifacts or {}).get("completed_derivation") or ""),
                "learning_task": task.to_dict(public=True),
            })
            return
        if task.status != "waiting_for_input":
            yield _sse_event("error", done=True, message=f"当前任务状态不能恢复：{task.status}")
            return

        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"provide_input", "method_only"}:
            yield _sse_event("error", done=True, message="无效的恢复方式")
            return
        if normalized_action == "provide_input" and file is None:
            yield _sse_event("error", done=True, message="请先选择要补充的图片或附表")
            return

        artifacts = dict(task.artifacts or {})
        original_ir = VisualProblemIR.from_dict(dict(artifacts.get("visual_ir") or {}))
        supplemental_irs = [
            VisualProblemIR.from_dict(item)
            for item in (artifacts.get("supplemental_visual_irs") or [])
            if isinstance(item, dict)
        ]
        try:
            if normalized_action == "provide_input":
                supplemental_path = _image_store.save_upload(file)
                yield _sse_event("activity", activity={
                    "id": "supplement", "kind": "tool", "label": "解析补充材料",
                    "status": "active", "detail": "只读取本次新增材料，原题与已有视觉表示保持不变",
                })
                supplement = _ocr_image_with_kimi(
                    supplemental_path,
                    user_question=f"这是题目所需的补充材料：{', '.join(str(item.get('name') or '') for item in task.required_inputs)}",
                    subject=str(artifacts.get("subject") or ""),
                )
                supplemental_irs.append(supplement)
                artifacts["supplemental_visual_irs"] = [item.to_dict() for item in supplemental_irs]
                artifacts["supplemental_image_paths"] = [
                    *(artifacts.get("supplemental_image_paths") or []), str(supplemental_path),
                ]
                mark_required_inputs(task, "provided")
                answer_policy = "exact"
                detail = "补充材料已合并，继续原任务"
            else:
                mark_required_inputs(task, "waived")
                answer_policy = "method_only"
                detail = "已按用户选择降级为只讲方法"

            task.artifacts = artifacts
            store.checkpoint(task, "inputs_resolved", status="running", detail=detail)
            yield _sse_event("activity", activity={
                "id": "required-inputs", "kind": "system", "label": "恢复原任务",
                "status": "completed", "detail": detail,
            })
            explanation = yield from _stream_solution_events(
                original_ir,
                user_question=str(artifacts.get("question") or ""),
                user_answer=str(artifacts.get("user_answer") or ""),
                subject=str(artifacts.get("subject") or ""),
                tags=str(artifacts.get("tags") or ""),
                supplemental_visual_irs=supplemental_irs,
                answer_policy=answer_policy,
                reason_label="继续原题推导",
                reason_detail="正在结合原题、已完成解析与新增材料继续解答",
            )

            raw_explanation = explanation
            explanation, answer_verification = _verify_visual_answer(
                explanation,
                question=str(artifacts.get("question") or ""),
                visual_ir=original_ir,
                supplemental_visual_irs=supplemental_irs,
                required_outputs=task.required_outputs,
                answer_policy=answer_policy,
            )
            if normalized_action == "method_only" and "未验证估算" not in explanation and "未作为精确答案" not in explanation:
                explanation = explanation.rstrip() + "\n\n> 本次未补充必要材料；涉及的数值结论均未作为精确答案提交。"
            if explanation != raw_explanation:
                yield _sse_event("generate", chunk=explanation, replace=True, done=False)
                yield _sse_event("generate", chunk="", done=True)

            task.artifacts["completed_derivation"] = explanation
            task.verification = {
                **answer_verification,
                "input_gate": "passed" if normalized_action == "provide_input" else "degraded_method_only",
            }
            completion_status = "completed" if answer_verification.get("passed") else "degraded"
            store.checkpoint(task, "answer_generated", status=completion_status, detail="原任务已恢复并完成验收")

            book_name = str(artifacts.get("book_name") or "default")
            draft = MistakeRecord(
                question_text=original_ir.problem_text or original_ir.visual_summary,
                user_answer=str(artifacts.get("user_answer") or ""),
                subject=normalize_subject_value(str(artifacts.get("subject") or ""), fallback=book_name),
                tags=_tags_from_text(str(artifacts.get("tags") or "")),
                image_path=str(artifacts.get("image_path") or ""),
                ocr_text=original_ir.problem_text,
                visual_ir=original_ir.to_dict(),
                explanation=explanation,
                source="问答图片上传",
            )
            linked_concepts = _link_mistake_concepts(
                draft, explanation=explanation, book_name=book_name, allow_llm_fallback=False,
            )
            mistake_id = ""
            if bool(artifacts.get("import_to_mistakes")):
                committed_path, _ = _image_store.commit_pending(str(artifacts.get("image_path") or ""))
                draft.image_path = committed_path
                draft.linked_concepts = linked_concepts
                mistake_id = _mb(book_name).add(draft)
                _log_learning_event("mistake_added", book_name=book_name, record=draft, payload={"origin": "chat_image_resumed"})

            yield _sse_event("done", done=True, result={
                "success": True,
                "explanation": explanation,
                "linked_concepts": linked_concepts,
                "question_text": original_ir.problem_text,
                "visual_ir": original_ir.to_dict(),
                "mistake_id": mistake_id,
                "learning_task": task.to_dict(public=True),
                "answer_verification": answer_verification,
            })
        except GeneratorExit:
            raise
        except Exception as exc:
            store.checkpoint(task, "resume_failed", status="waiting_for_input", detail=str(exc))
            yield _sse_event("error", done=True, message=str(exc), activity={
                "id": "resume", "kind": "system", "label": "恢复失败",
                "status": "failed", "detail": "原任务和已有材料已保留，可以重试",
            })

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/solve-cached")
def solve_cached_mistake(req: MistakeChatRequest):
    """Explain a stored mistake from its cached Visual IR without re-uploading."""
    book_name = req.book_name or "default"
    record = _mb(book_name).get(req.id)
    if not record:
        return {"success": False, "message": "错题不存在"}
    try:
        visual_ir = (
            VisualProblemIR.from_dict(record.visual_ir)
            if record.visual_ir
            else VisualProblemIR(problem_text=record.question_text or record.ocr_text, visual_type="text_only")
        )
        explanation = _solve_visual_ir(
            visual_ir, user_question=req.question, user_answer=req.user_answer or record.user_answer,
            subject=record.subject, tags=", ".join(record.tags),
        )
        concepts = record.linked_concepts or _link_mistake_concepts(
            record, explanation=explanation, book_name=book_name,
            allow_llm_fallback=False,
        )
        if concepts and not record.linked_concepts:
            record.linked_concepts = concepts
            _mb(book_name).update(record)
        return {
            "success": True, "explanation": explanation, "linked_concepts": concepts,
            "question_text": record.question_text, "mistake_id": record.id,
            "visual_ir": visual_ir.to_dict(),
        }
    except Exception as exc:
        return {"success": False, "message": f"讲解失败: {exc}"}


@router.post("/solve-cached-stream")
def solve_cached_mistake_stream(req: MistakeChatRequest):
    def events():
        book_name = req.book_name or "default"
        record = _mb(book_name).get(req.id)
        if not record:
            yield _sse_event("error", done=True, message="错题不存在", activity={
                "id": "cache", "kind": "tool", "label": "读取历史错题", "status": "failed", "detail": "错题不存在",
            })
            return
        try:
            visual_ir = VisualProblemIR.from_dict(record.visual_ir) if record.visual_ir else VisualProblemIR(
                problem_text=record.question_text or record.ocr_text, visual_type="text_only",
            )
            yield _sse_event("activity", activity={
                "id": "cache", "kind": "tool", "label": "读取历史错题", "status": "completed",
                "detail": "已复用缓存的题干与视觉表示" if record.visual_ir else "旧记录无视觉缓存，使用题干文本降级",
            })
            explanation = yield from _stream_solution_events(
                visual_ir,
                user_question=req.question,
                user_answer=req.user_answer or record.user_answer,
                subject=record.subject,
                tags=", ".join(record.tags),
                reason_label="重新组织解题思路",
                reason_detail="正在结合历史题目、用户追问和已有概念重新讲解",
            )
            concepts = record.linked_concepts or _link_mistake_concepts(
                record, explanation=explanation, book_name=book_name, allow_llm_fallback=False,
            )
            if concepts and not record.linked_concepts:
                record.linked_concepts = concepts
                _mb(book_name).update(record)
            yield _sse_event("done", done=True, result={
                "success": True, "explanation": explanation, "linked_concepts": concepts,
                "question_text": record.question_text, "mistake_id": record.id, "visual_ir": visual_ir.to_dict(),
            }, activity={
                "id": "memory", "kind": "memory", "label": "读取概念记录",
                "status": "completed" if concepts else "skipped", "detail": f"已关联 {len(concepts)} 个概念" if concepts else "没有可靠概念标签",
            })
        except Exception as exc:
            yield _sse_event("error", done=True, message=str(exc), activity={
                "id": "error", "kind": "system", "label": "处理失败", "status": "failed", "detail": str(exc),
            })
    return StreamingResponse(events(), media_type="text/event-stream")

@router.post("/solve-text")
def solve_mistake_text(req: MistakeAddRequest):
    try:
        if req.visual_ir:
            explanation = _solve_visual_ir(
                VisualProblemIR.from_dict(req.visual_ir),
                user_answer=req.user_answer.strip(), subject=req.subject.strip(), tags=req.tags.strip(),
            )
        else:
            explanation = _solve_ocr_text(
                req.question_text.strip(), user_answer=req.user_answer.strip(),
                subject=req.subject.strip(), tags=req.tags.strip(),
            )
        return {"success": True, "explanation": explanation}
    except Exception as e:
        return {"success": False, "message": f"讲解失败: {e}"}

@router.get("/stats")
def get_stats(subject: str = "", book_name: str = "default") -> MistakeStatsOut:
    stats = _mb(book_name).get_stats(subject=subject or None)
    return MistakeStatsOut(
        total=stats["total"],
        due_today=stats["due_today"],
        by_type=stats.get("by_type", {}),
        by_tag=stats.get("by_tag", {}),
        by_difficulty=stats.get("by_difficulty", {}),
    )


@router.get("/weak-points")
def get_weak_points(subject: str = "", book_name: str = "default", top_n: int = 8):
    weak = _mb(book_name).get_weak_points(subject=subject or None, top_n=top_n)
    return {"success": True, "data": [WeakPointOut(name=w["name"], type=w["type"], count=w["count"]) for w in weak]}



@router.get("/{mistake_id}/image")
def get_mistake_image(mistake_id: str, book_name: str = "default"):
    record = _mb(book_name).get(mistake_id)
    if not record or not record.image_path:
        raise HTTPException(status_code=404, detail="image not found")
    image_path = Path(record.image_path).resolve()
    image_root = (Path(IMAGES_PATH) / "mistakes").resolve()
    try:
        image_path.relative_to(image_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="image path forbidden")
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="image file not found")
    return FileResponse(str(image_path))

@router.get("/{mistake_id}")
def get_mistake_detail(mistake_id: str, book_name: str = "default"):
    record = _mb(book_name).get(mistake_id)
    if not record:
        return {"success": False, "message": "错题不存在"}
    return {"success": True, "data": _record_to_out(record)}

@router.delete("/{mistake_id}")
def delete_mistake(mistake_id: str, book_name: str = "default"):
    mistake_book = _mb(book_name)
    record = mistake_book.get(mistake_id)
    mistake_book.delete(mistake_id)
    if record:
        _image_store.delete(record.image_path)
    return {"success": True, "message": f"已删除 {mistake_id}"}

@router.post("/review")
def review_mistake(req: MistakeReviewRequest, book_name: str = "default"):
    try:
        updated = _mb(book_name).review(req.id, req.quality)
        _log_learning_event("mistake_reviewed", book_name=book_name, record=updated, payload={"quality": req.quality, "next_review": updated.sm2.get("next_review") if updated.sm2 else None})
        next_review = updated.sm2.get("next_review") if updated.sm2 else None
        interval = updated.sm2.get("interval") if updated.sm2 else None
        return {
            "success": True,
            "message": f"已记录复习，{interval or 1} 天后再看",
            "data": _record_to_out(updated),
            "next_review": next_review,
            "interval": interval,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

def _record_mistake_concepts(record: MistakeRecord, explanation: str, rag_context: str, book_name: str) -> list[dict]:
    return _persist_mistake_concepts(record, explanation=explanation or rag_context, book_name=book_name)


@router.post("/explain")
def explain_mistake(req: MistakeExplainRequest, book_name: str = "default"):
    from config import get_llm
    from graph.safe_retrieval import get_safe_vector_store

    mb = _mb(book_name)
    llm = get_llm()
    rag_context = {"text": ""}
    rag_book = (req.book_name or book_name or "").strip()

    def rag_provider(record: MistakeRecord):
        if not rag_book:
            return ""
        try:
            vs, vector_error = get_safe_vector_store()
            if vector_error:
                return ""
            if vs and record.tags:
                ch_docs = vs.search_all(record.tags[0], k=3, book_name=rag_book)
                texts = []
                for chapter, docs in ch_docs.items():
                    texts.append("章节：" + chapter)
                    for doc in docs:
                        texts.append(doc.page_content[:400])
                rag_context["text"] = "\n".join(texts)
                return rag_context["text"]
        except Exception:
            pass
        return ""

    try:
        result = mb.explain(req.id, lambda prompt: strip_thinking(llm.invoke(prompt).content), context_provider=rag_provider)
        sanitized = sanitize_latex(result)
        record = mb.get(req.id)
        if record:
            record.explanation = sanitized
            _record_mistake_concepts(record, sanitized, rag_context["text"], req.book_name or book_name)
            mb.update(record)
            _log_learning_event("mistake_explained", book_name=req.book_name or book_name, record=record, payload={"has_rag_context": bool(rag_context["text"])})
        return {"success": True, "explanation": sanitized, "data": _record_to_out(record) if record else None}
    except Exception as e:
        return {"success": False, "message": f"讲解失败: {e}"}
