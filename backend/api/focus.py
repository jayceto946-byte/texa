"""Focus HTTP adapter. Commands and timing belong to the domain service."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from backend.services.goals.focus import FocusStore, get_focus_store
from backend.services.goals.focus_migration import FocusMigrationRequired
from backend.services.goals.store import GoalConflict

router = APIRouter(prefix='/focus', tags=['focus'])


def store():
    try:
        return get_focus_store()
    except FocusMigrationRequired as exc:
        raise HTTPException(503, str(exc)) from exc


class TaskInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1,max_length=200)
    content: str = Field(default='',max_length=2000)
    duration_seconds: int = Field(default=1500,ge=60,le=7200,strict=True)
    criterion_ids: list[str] = Field(default_factory=list,max_length=12)


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation: Literal['create','create_batch','update','reorder','select','start','switch','pause','finish','complete','reopen','delete','acknowledge']
    operation_id: str = Field(min_length=1,max_length=100)
    expected_revision: int = Field(ge=0)
    expected_goal_revision: int | None = Field(default=None,ge=1)
    goal_id: str = ''
    task_id: str = ''
    title: str = Field(default='',max_length=200)
    content: str = Field(default='',max_length=2000)
    duration_seconds: int = Field(default=1500,ge=60,le=7200,strict=True)
    mode: Literal['countdown','stopwatch'] = 'countdown'
    criterion_ids: list[str] = Field(default_factory=list,max_length=12)
    task_ids: list[str] = Field(default_factory=list,max_length=5000)
    tasks: list[TaskInput] = Field(default_factory=list,max_length=20)
    start_after_switch: bool = False
    reason: Literal['','user_paused','user_ended','suspend','shutdown'] = ''


@router.get('')
def current(goal_id: str = '',offset: int = Query(0,ge=0),limit: int = Query(100,ge=1,le=100),task_status: Literal['','pending','completed']='',around_task_id: str='',service: FocusStore = Depends(store)):
    return {'success':True,'data':service.snapshot(goal_id=goal_id,offset=offset,limit=limit,task_status=task_status,around_task_id=around_task_id)}


@router.get('/history')
def history(goal_id: str='',task_id: str='',offset: int=Query(0,ge=0),limit: int=Query(50,ge=1,le=100),timezone_name: str=Query('UTC',max_length=100),service: FocusStore=Depends(store)):
    try:
        return {'success':True,'data':service.history(goal_id=goal_id,task_id=task_id,offset=offset,limit=limit,timezone_name=timezone_name)}
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc


@router.get('/operations/{operation_id}')
def receipt(operation_id: str,service: FocusStore=Depends(store)):
    return {'success':True,'data':service.receipt(operation_id)}


@router.post('/commands')
def command(request: Command,service: FocusStore=Depends(store)):
    try:
        return {'success':True,'data':service.command(request.model_dump(exclude_unset=True))}
    except GoalConflict as exc:
        raise HTTPException(409,str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400,str(exc)) from exc
