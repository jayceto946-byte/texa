"""Learning State v1 protocol adapter."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.schemas import LearningStateOperationRequest
from backend.services.learning_state import DEFAULT_LEARNER_ID, LearningStateService


router = APIRouter(prefix="/learning-state", tags=["learning-state"])


@router.get("")
def get_learning_state(
    book_name: str = "",
    subject: str = "",
    learner_id: str = DEFAULT_LEARNER_ID,
):
    try:
        service = LearningStateService()
        if book_name:
            data = service.get_state(
                learner_id=learner_id, book_name=book_name, subject=subject,
            )
        else:
            data = {"resumable": service.list_resumable(learner_id=learner_id, subject=subject)}
        return {"success": True, "data": data}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"learning state unavailable: {exc}") from exc


@router.post("/operations")
def apply_learning_state_operation(req: LearningStateOperationRequest):
    operation = req.model_dump(exclude_none=True)
    for key in {"learner_id", "book_name", "subject", "conversation_id", "source_id"}:
        operation.pop(key, None)
    try:
        data = LearningStateService().apply_operation(
            operation,
            learner_id=req.learner_id,
            book_name=req.book_name,
            subject=req.subject,
            conversation_id=req.conversation_id,
            source_id=req.source_id,
        )
        return {"success": True, "data": data}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
