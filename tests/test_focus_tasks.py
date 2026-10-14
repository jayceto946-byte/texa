import json
import sqlite3
import pytest
from concurrent.futures import ThreadPoolExecutor
from backend.services.goals.store import GoalStore, GoalConflict
from backend.services.goals.focus import FocusStore

@pytest.fixture
def setup(tmp_path):
    path=tmp_path/'goals.db'
    goal=GoalStore(path).create(learner_id='local_default',title='学习偏导',objective='理解定义',scope={},success_criteria=[])
    clock=[1000.0]
    focus=FocusStore(path,clock=lambda:clock[0])
    return path,goal,focus,clock

def submit(focus,operation,**kwargs):
    return focus.command(dict(operation=operation,operation_id=kwargs.pop('operation_id',operation+str(focus.snapshot()['revision'])),expected_revision=kwargs.pop('expected_revision',focus.snapshot()['revision']),**kwargs))

def task(focus,goal,title='定义'):
    return submit(focus,'create',goal_id=goal['id'],title=title,content='阅读定义',duration_seconds=60)['tasks'][-1]

def test_migration_preserves_goals_and_has_restorable_backup(setup):
    path,goal,focus,_=setup
    assert GoalStore(path).get(goal['id'])['title']==goal['title']
    assert sqlite3.connect(path).execute('PRAGMA user_version').fetchone()[0]==2
    backup=next(path.parent.glob('goals-before-focus-v2-*.db'))
    with sqlite3.connect(backup) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA user_version').fetchone()[0]==1
        assert conn.execute('SELECT id FROM goals').fetchone()[0]==goal['id']
    # Repeat opening must not create repeated backups.
    FocusStore(path)
    assert len(list(path.parent.glob('goals-before-focus-v2-*.db')))==1

def test_clock_pause_restart_expiry_never_completes_goal(setup):
    path,goal,focus,clock=setup;t=task(focus,goal)
    submit(focus,'start',task_id=t['id']);clock[0]+=20
    assert focus.snapshot()['remaining_seconds']==40
    submit(focus,'pause');clock[0]+=300
    reopened=FocusStore(path,clock=lambda:clock[0]);assert reopened.snapshot()['remaining_seconds']==40
    submit(reopened,'start');clock[0]+=50
    assert reopened.snapshot()['status']=='expired'
    assert reopened.snapshot()['current_task']['status']!='completed'
    assert GoalStore(path).get(goal['id'])['status']==goal['status']
    submit(reopened,'complete')
    assert reopened.snapshot()['current_task']['status']=='completed'
    assert GoalStore(path).get(goal['id'])['revision']==goal['revision']

def test_lost_response_receipt_and_payload_collision(setup):
    _,goal,focus,_=setup;t=task(focus,goal)
    payload=dict(operation='start',task_id=t['id'],operation_id='same',expected_revision=focus.snapshot()['revision'])
    first=focus.command(payload);assert focus.command(payload)==first
    assert focus.receipt('same')==first
    with pytest.raises(GoalConflict):focus.command({**payload,'operation':'pause'})

def test_two_devices_only_one_revision_wins(setup):
    _,goal,focus,_=setup;a=task(focus,goal);b=task(focus,goal,'例题');revision=focus.snapshot()['revision']
    def start(t):
        try:return focus.command(dict(operation='start',task_id=t['id'],expected_revision=revision,operation_id=t['id']))
        except GoalConflict:return None
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(start,[a,b]))
    assert sum(value is not None for value in results)==1
    assert focus.snapshot()['status']=='running'

def test_switch_keeps_prior_elapsed(setup):
    _,goal,focus,clock=setup;a=task(focus,goal);b=task(focus,goal,'例题')
    submit(focus,'start',task_id=a['id']);clock[0]+=15
    submit(focus,'switch',task_id=b['id']);clock[0]+=5
    submit(focus,'switch',task_id=a['id'])
    assert focus.snapshot()['remaining_seconds']==45

def test_invalid_commands_do_not_commit_revision(setup):
    _,goal,focus,_=setup
    with pytest.raises(ValueError):task(focus,{'id':'missing'})
    assert focus.snapshot()['revision']==0
    with pytest.raises(ValueError):submit(focus,'create',goal_id=goal['id'],title='x',duration_seconds=0)
    assert focus.snapshot()['tasks']==[]

def test_legacy_goal_projection_rejects_missing_contract(monkeypatch):
    from backend.services.goals import execution
    goal={'status':'active','objective':'学习','scope':{},'success_criteria':[]}
    monkeypatch.setattr(execution,'public_task',lambda *_:{'resumable':True})
    invalid=execution.project_goal_runtime(None,{'run':{'checkpoint':{}}},goal)
    assert not invalid['resumable'] and '已有结果保留' in invalid['resume_block_reason']
    valid=execution.project_goal_runtime(None,{'run':{'checkpoint':{'goal_contract':execution.goal_contract(goal)}}},goal)
    assert valid['resumable']


def test_focus_http_validation_receipts_and_cas(setup):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.focus import router, store
    _,goal,focus,_=setup
    app=FastAPI();app.include_router(router,prefix='/api');app.dependency_overrides[store]=lambda:focus
    client=TestClient(app)
    payload=dict(operation='create',operation_id='http-create',expected_revision=0,goal_id=goal['id'],title='定义',duration_seconds=60)
    first=client.post('/api/focus/commands',json=payload)
    assert first.status_code==200
    assert client.post('/api/focus/commands',json=payload).json()==first.json()
    assert client.get('/api/focus/operations/http-create').json()['data']==first.json()['data']
    assert client.post('/api/focus/commands',json={**payload,'operation_id':'stale'}).status_code==409
    assert client.post('/api/focus/commands',json={**payload,'unexpected':'secret'}).status_code==422
    assert client.post('/api/focus/commands',json={**payload,'duration_seconds':0}).status_code==422
