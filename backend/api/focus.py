"""Focus HTTP adapter. Authentication is inherited from the local API boundary."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from backend.services.goals.focus import FocusStore
from backend.services.goals.store import DEFAULT_GOAL_DB_PATH, GoalConflict
router = APIRouter(prefix="/focus", tags=["focus"])
def store():
    return FocusStore(DEFAULT_GOAL_DB_PATH)
class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["create","start","switch","pause","finish","complete"]
    operation_id: str = Field(min_length=1,max_length=100)
    expected_revision: int = Field(ge=0)
    goal_id: str = ""
    task_id: str = ""
    title: str = Field(default="",max_length=200)
    content: str = Field(default="",max_length=2000)
    duration_seconds: int = Field(default=1500,ge=60,le=7200)
@router.get("")
def current(service: FocusStore = Depends(store)):
    return {"success":True,"data":service.snapshot()}
@router.get("/operations/{operation_id}")
def receipt(operation_id: str, service: FocusStore = Depends(store)):
    return {"success":True,"data":service.receipt(operation_id)}
@router.post("/commands")
def command(request: Command, service: FocusStore = Depends(store)):
    try:
        return {"success":True,"data":service.command(request.model_dump())}
    except GoalConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
