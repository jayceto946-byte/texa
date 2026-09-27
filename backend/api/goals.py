"""Local Goal HTTP adapter; service dependencies open storage on demand."""
from __future__ import annotations

from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.services.goals.service import GoalService
from backend.services.goals.store import DEFAULT_GOAL_DB_PATH, GoalConflict, GoalStore
from memory.learning_events import get_learning_event_store

router = APIRouter(prefix="/goals", tags=["goals"])


def get_goal_service() -> GoalService:
    return GoalService(GoalStore(DEFAULT_GOAL_DB_PATH), get_learning_event_store())


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: str = Field(default="local_default", min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(default="", max_length=2000)
    scope: dict[str, Any] = Field(default_factory=dict)
    success_criteria: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    target_date: str = ""
    timezone_name: str = ""


class GoalCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    operation: Literal["update", "activate", "pause", "measure"]
    changes: dict[str, Any] = Field(default_factory=dict)
    evidence_by_criterion: dict[str, list[str]] = Field(default_factory=dict)
    user_confirms_completion: bool = False


def _invoke(action):
    try:
        return {"success": True, "data": action()}
    except GoalConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, "goal not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("")
def list_goals(learner_id: str = "local_default", limit: int = Query(50, ge=1, le=100),
               before_id: str = "", service: GoalService = Depends(get_goal_service)):
    return _invoke(lambda: service.store.list(learner_id=learner_id, limit=limit, before_id=before_id))


@router.post("")
def create_goal(req: GoalCreate, service: GoalService = Depends(get_goal_service)):
    return _invoke(lambda: service.create(**req.model_dump()))


@router.get("/{goal_id}")
def get_goal(goal_id: str, service: GoalService = Depends(get_goal_service)):
    def read():
        goal = service.store.get(goal_id)
        if goal is None:
            raise KeyError(goal_id)
        return {**goal, "next_action": service.get_next_action(goal_id),
                "run_links": service.store.links(goal_id)}
    return _invoke(read)


@router.get("/{goal_id}/evidence")
def goal_evidence(goal_id: str, service: GoalService = Depends(get_goal_service)):
    return _invoke(lambda: service.evidence_candidates(goal_id))


@router.post("/{goal_id}/commands")
def apply_goal_command(goal_id: str, req: GoalCommand,
                       service: GoalService = Depends(get_goal_service)):
    def apply():
        if req.operation != "update" and req.changes:
            raise ValueError("changes require update operation")
        if req.operation != "measure" and (req.evidence_by_criterion or req.user_confirms_completion):
            raise ValueError("measurement fields require measure operation")
        if service.store.get(goal_id) is None:
            raise KeyError(goal_id)
        if req.operation == "update":
            return service.update(goal_id, expected_revision=req.expected_revision, changes=req.changes)
        if req.operation == "measure":
            return service.measure(goal_id, expected_revision=req.expected_revision,
                evidence_by_criterion=req.evidence_by_criterion,
                user_confirms_completion=req.user_confirms_completion)
        return getattr(service, req.operation)(goal_id, expected_revision=req.expected_revision)
    return _invoke(apply)


class GoalIntake(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    book_name: str = Field(default="", max_length=200)
    subject: str = Field(default="", max_length=200)


@router.post("/intake/summarize")
def summarize_intake(req: GoalIntake):
    from backend.services.goals.execution import summarize_goal
    try:
        return {"success": True, "data": {**summarize_goal(req.text),
            "scope": {"book_name": req.book_name, "subject": req.subject}}}
    except Exception as exc:
        raise HTTPException(503, "目标整理暂不可用，请检查模型配置。原始目标可以直接保存。") from exc


class GoalRunCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    request_key: str = Field(min_length=1, max_length=200)
    task_id: str = ""


@router.post("/{goal_id}/run")
def run_goal(goal_id: str, req: GoalRunCommand, service: GoalService = Depends(get_goal_service)):
    from backend.services.goals.execution import start_goal, resume_goal
    from backend.services.agent_runtime.contracts import RuntimeConflict, RuntimeDenied
    try:
        data = resume_goal(service, goal_id, task_id=req.task_id, expected_revision=req.expected_revision, request_key=req.request_key) if req.task_id else start_goal(service, goal_id, expected_revision=req.expected_revision, request_key=req.request_key)
        return {"success": True, "data": data}
    except (GoalConflict, RuntimeConflict) as exc:
        raise HTTPException(409, str(exc)) from exc
    except (RuntimeDenied, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{goal_id}/runtime")
def goal_runtime(goal_id: str, service: GoalService = Depends(get_goal_service)):
    from backend.services.agent_runtime.locator import runtime_store, public_task
    if not service.store.get(goal_id):
        raise HTTPException(404, "goal not found")
    links = service.store.links(goal_id)
    store = runtime_store()
    snapshot = store.task_snapshot(links[-1]["task_id"]) if store and links else None
    return {"success": True, "data": public_task(store, snapshot) if snapshot else None, "goal": service.store.get(goal_id)}


class GoalScheduleCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    due_at: str = Field(default="", max_length=50)
    interval_hours: Literal[0, 24, 168] = 0


@router.post("/{goal_id}/schedule")
def goal_schedule(goal_id: str, req: GoalScheduleCommand, service: GoalService = Depends(get_goal_service)):
    from backend.services.goals.execution import schedule_goal
    if not req.due_at:
        return _invoke(lambda: service.store.update(goal_id, expected_revision=req.expected_revision, changes={"next_action": None}))
    return _invoke(lambda: schedule_goal(service, goal_id, expected_revision=req.expected_revision,
        due_at=req.due_at, interval_hours=req.interval_hours))
