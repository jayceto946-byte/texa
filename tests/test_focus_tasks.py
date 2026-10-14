import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from backend.services.goals.store import GoalStore, GoalConflict
from backend.services.goals.focus import FocusStore
from backend.services.goals.focus_migration import FocusMigrationRequired


@pytest.fixture
def setup(tmp_path):
    path=tmp_path/'goals.db'
    store=GoalStore(path)
    goal=store.create(learner_id='local_default',title='学习偏导',objective='理解定义',scope={},success_criteria=[{'id':'c1','description':'理解定义'}])
    goal=store.update(goal['id'],expected_revision=1,changes={'status':'active'})
    clock=[1000.0]; wall=[1700000000.0]
    focus=FocusStore(path,clock=lambda:clock[0],wall_clock=lambda:wall[0],allow_migration=True,max_gap_seconds=None)
    return path,goal,focus,clock,wall


def submit(focus,operation,**kwargs):
    return focus.command(dict(operation=operation,operation_id=kwargs.pop('operation_id',operation+str(focus.snapshot()['revision'])),expected_revision=kwargs.pop('expected_revision',focus.snapshot()['revision']),**kwargs))


def task(focus,goal,title='定义'):
    return submit(focus,'create',goal_id=goal['id'],title=title,content='阅读定义',duration_seconds=1500)['tasks'][-1]


def start(focus,t,**kwargs):
    return submit(focus,'start',task_id=t['id'],expected_goal_revision=t['goal_revision'],**kwargs)


def test_migration_explicit_backup_and_forward_guard(setup,tmp_path):
    path,goal,focus,_,_=setup
    assert GoalStore(path).get(goal['id'])==goal
    assert sqlite3.connect(path).execute('PRAGMA user_version').fetchone()[0]==3
    backup=next(path.parent.glob('goals-before-focus-v3-*.db'))
    with sqlite3.connect(backup) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA user_version').fetchone()[0]==1
        assert conn.execute('SELECT id FROM goals').fetchone()[0]==goal['id']
    FocusStore(path)
    assert len(list(path.parent.glob('*before-focus-v3-*.db')))==1
    old=tmp_path/'old.db';GoalStore(old)
    with pytest.raises(FocusMigrationRequired):FocusStore(old)
    assert sqlite3.connect(old).execute('PRAGMA user_version').fetchone()[0]==1
    with sqlite3.connect(old) as conn:conn.execute('PRAGMA user_version=4')
    with pytest.raises(RuntimeError):GoalStore(old)


def test_pause_resume_20_plus_10_not_300_and_wall_clock_jump(setup):
    path,goal,focus,clock,wall=setup;t=task(focus,goal)
    start(focus,t);clock[0]+=20;wall[0]+=3600
    submit(focus,'pause');clock[0]+=300;wall[0]-=7200
    assert focus.snapshot()['active_ms']==20000
    start(focus,t);clock[0]+=10
    submit(focus,'finish')
    assert focus.snapshot()['active_ms']==30000
    assert focus.snapshot()['current_task']['status']=='pending'
    assert GoalStore(path).get(goal['id'])==goal
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM focus_segments').fetchone()[0]==2
        assert conn.execute('SELECT SUM(active_ms) FROM focus_segments').fetchone()[0]==30000


def test_two_sessions_25_plus_18_equals_43_and_overtime_27(setup):
    _,goal,focus,clock,_=setup;t=task(focus,goal)
    start(focus,t);clock[0]+=1500;submit(focus,'finish')
    first=focus.snapshot()['current_session']['id']
    start(focus,t);assert focus.snapshot()['remaining_seconds']==1500
    clock[0]+=1080;submit(focus,'finish')
    assert focus.snapshot()['current_task']['active_ms']==43*60*1000
    history=focus.history()['sessions'];assert len(history)==2
    assert history[0]['id']!=first
    start(focus,t);clock[0]+=1620
    snapshot=focus.snapshot()
    assert snapshot['status']=='running' and snapshot['remaining_seconds']==0 and snapshot['overtime_seconds']==120
    submit(focus,'acknowledge');submit(focus,'complete')
    assert focus.history()['sessions'][0]['active_ms']==27*60*1000
    assert focus.snapshot()['current_task']['status']=='completed'
    submit(focus,'reopen')
    assert focus.snapshot()['current_task']['status']=='pending'
    assert focus.snapshot()['current_session']['status']=='ended'


def test_stopwatch_without_timer_complete_noncurrent_and_switch_explicit(setup):
    _,goal,focus,clock,_=setup;a=task(focus,goal);b=task(focus,goal,'例题')
    start(focus,a,mode='stopwatch');clock[0]+=10
    assert focus.snapshot()['remaining_seconds'] is None
    submit(focus,'complete',task_id=b['id'])
    assert focus.snapshot()['current_session']['status']=='running'
    assert focus.snapshot()['current_task']['id']==a['id']
    submit(focus,'reopen',task_id=b['id'])
    with pytest.raises(GoalConflict):submit(focus,'select',task_id=b['id'])
    submit(focus,'select',task_id=a['id'])
    assert focus.snapshot()['current_session'] is not None
    submit(focus,'switch',task_id=b['id'])
    assert focus.snapshot()['status']=='idle' and focus.snapshot()['current_session'] is None
    assert focus.history()['sessions'][0]['active_ms']==10000
    submit(focus,'complete',task_id=b['id'])
    assert focus.snapshot()['current_task']['active_ms']==0


def test_receipt_replay_stale_time_and_payload_collision(setup):
    _,goal,focus,clock,_=setup;t=task(focus,goal)
    payload=dict(operation='start',task_id=t['id'],expected_goal_revision=t['goal_revision'],operation_id='same',expected_revision=focus.snapshot()['revision'])
    first=focus.command(payload);clock[0]+=20
    assert focus.command(payload)==first
    assert focus.receipt('same')==first
    assert focus.snapshot()['active_ms']==20000
    with pytest.raises(GoalConflict):focus.command({**payload,'operation':'pause'})
    submit(focus,'complete');rev=focus.snapshot()['revision']
    assert focus.command(payload)==first
    assert focus.snapshot()['revision']==rev
    assert len(focus.history()['sessions'])==1


def test_two_devices_only_one_revision_wins_and_goal_admission(setup):
    path,goal,focus,_,_=setup;a=task(focus,goal);b=task(focus,goal,'例题');revision=focus.snapshot()['revision']
    def begin(t):
        try:return focus.command(dict(operation='start',task_id=t['id'],expected_goal_revision=t['goal_revision'],expected_revision=revision,operation_id=t['id']))
        except GoalConflict:return None
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(begin,[a,b]))
    assert sum(value is not None for value in results)==1
    submit(focus,'finish')
    GoalStore(path).update(goal['id'],expected_revision=goal['revision'],changes={'status':'paused'})
    with pytest.raises(GoalConflict):start(focus,a)
    GoalStore(path).update(goal['id'],expected_revision=goal['revision']+1,changes={'status':'active'})
    with pytest.raises(GoalConflict):start(focus,a) # stale goal revision


def test_recovery_discards_uncommitted_tail_and_gap_pauses(setup):
    path,goal,focus,clock,wall=setup;t=task(focus,goal)
    start(focus,t);clock[0]+=20;focus.checkpoint();clock[0]+=30000;wall[0]+=30000
    reopened=FocusStore(path,clock=lambda:clock[0],wall_clock=lambda:wall[0])
    assert reopened.snapshot()['status']=='paused'
    assert reopened.snapshot()['active_ms']==20000
    assert reopened.snapshot()['reason']=='interrupted'
    start(reopened,t);clock[0]+=100
    reopened.snapshot()
    assert reopened.snapshot()['status']=='paused' and reopened.snapshot()['active_ms']==20000


def test_pagination_current_independent_batch_reorder_and_rollback(setup):
    _,goal,focus,_,_=setup
    for page in range(6):
        submit(focus,'create_batch',goal_id=goal['id'],tasks=[{'title':f'任务{page*20+i}'} for i in range(20)])
    assert len(focus.snapshot()['tasks'])==100
    last=focus.snapshot(offset=100)['tasks'][-1];start(focus,last)
    assert focus.snapshot(limit=1)['current_task']['id']==last['id']
    other=focus.snapshot()['tasks'][0]
    submit(focus,'complete',task_id=other['id'])
    assert focus.snapshot(task_status='completed',limit=1)['current_task']['id']==last['id']
    rev=focus.snapshot()['revision']
    with pytest.raises(ValueError):submit(focus,'create_batch',goal_id=goal['id'],tasks=[{'title':'有效'},{'title':''}])
    assert focus.snapshot()['revision']==rev
    pending=focus.snapshot(task_status='pending',limit=100)['tasks']+focus.snapshot(task_status='pending',offset=100)['tasks']
    ids=[item['id'] for item in pending]
    submit(focus,'reorder',goal_id=goal['id'],task_ids=ids[::-1])
    assert focus.snapshot()['tasks'][0]['id']==last['id']


def test_task_sources_and_deleted_history_are_retained(setup):
    path,goal,focus,clock,_=setup
    submit(focus,'create',goal_id=goal['id'],title='阅读定义',criterion_ids=['c1'])
    t=focus.snapshot()['tasks'][0];start(focus,t);clock[0]+=20
    submit(focus,'delete',task_id=t['id'])
    assert focus.snapshot()['current_task'] is None
    assert focus.snapshot()['tasks']==[]
    assert focus.history()['sessions'][0]['active_ms']==20000
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT criterion_ids FROM focus_tasks').fetchone()[0]=='["c1"]'


def test_focus_http_validation_receipts_and_cas(setup):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.focus import router,store
    _,goal,focus,_,_=setup
    app=FastAPI();app.include_router(router,prefix='/api');app.dependency_overrides[store]=lambda:focus
    client=TestClient(app)
    task(focus,goal,'已有任务')
    payload=dict(operation='create',operation_id='http-create',expected_revision=focus.snapshot()['revision'],goal_id=goal['id'],title='定义',duration_seconds=60)
    first=client.post('/api/focus/commands',json=payload);assert first.status_code==200
    assert client.post('/api/focus/commands',json=payload).json()==first.json()
    assert client.get('/api/focus/operations/http-create').json()['data']==first.json()['data']
    assert client.post('/api/focus/commands',json={**payload,'operation_id':'stale'}).status_code==409
    assert client.post('/api/focus/commands',json={**payload,'unexpected':'secret'}).status_code==422
    assert client.post('/api/focus/commands',json={**payload,'duration_seconds':60.5}).status_code==422
    assert client.get('/api/focus?limit=1').json()['data']['next_offset'] is not None
    assert client.get('/api/focus/history').status_code==200


def test_v2_migration_preserves_ids_revisions_links_receipts_and_committed_legacy(tmp_path):
    from contextlib import closing
    from backend.services.goals.focus_migration import migrate_focus
    path=tmp_path/'legacy.db';goals=GoalStore(path)
    goal=goals.create(learner_id='local_default',title='旧目标',objective='保留',success_criteria=[])
    # Original v2 schema, with WAL and an uncheckpointed WAL row in the live connection.
    with closing(sqlite3.connect(path,isolation_level=None)) as conn:
        conn.execute('PRAGMA journal_mode=WAL');conn.execute('PRAGMA wal_autocheckpoint=0')
        conn.execute("CREATE TABLE focus_tasks (id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id), title TEXT NOT NULL, content TEXT NOT NULL, duration_seconds INTEGER NOT NULL, elapsed_seconds REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending', revision INTEGER NOT NULL DEFAULT 1)")
        conn.execute("CREATE TABLE focus_state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, task_id TEXT, status TEXT NOT NULL, started_at REAL, elapsed_seconds REAL NOT NULL)")
        conn.execute("CREATE TABLE focus_receipts (operation_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, response_json TEXT NOT NULL)")
        conn.execute("INSERT INTO focus_tasks VALUES ('old-task',?,'定义','原文',1500,20.5,'in_progress',7)",(goal['id'],))
        conn.execute("INSERT INTO focus_state VALUES (1,8,'old-task','running',1000,20.5)")
        conn.execute("INSERT INTO focus_receipts VALUES ('old-op','old-hash','{}')")
        conn.execute("INSERT INTO goal_run_links VALUES (?,'task-old','run-old','now')",(goal['id'],))
        conn.execute('PRAGMA user_version=2')
        before={name:conn.execute(f'SELECT * FROM {name}').fetchall() for name in ['goals','goal_revisions','goal_run_links','focus_receipts']}
        backup=migrate_focus(path)
        assert {name:conn.execute(f'SELECT * FROM {name}').fetchall() for name in before}==before
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('SELECT id,elapsed_seconds,legacy_elapsed_ms,status,revision FROM focus_tasks').fetchone()==('old-task',20.5,20500,'pending',7)
        assert conn.execute('SELECT task_id,status,reason FROM focus_state').fetchone()==('old-task','idle','legacy_interrupted')
        assert conn.execute('SELECT COUNT(*) FROM focus_sessions').fetchone()[0]==0
        with closing(sqlite3.connect(backup)) as restored:
            assert restored.execute('PRAGMA user_version').fetchone()[0]==2
            assert restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert restored.execute('SELECT elapsed_seconds FROM focus_tasks').fetchone()[0]==20.5
            assert {name:restored.execute(f'SELECT * FROM {name}').fetchall() for name in before}==before


def test_goal_pause_settles_focus_before_runtime_and_condition_edits_keep_sources(setup,monkeypatch):
    from backend.services.goals.service import GoalService
    from backend.services.goals import focus as module
    path,goal,focus,clock,_=setup
    monkeypatch.setattr(module,'existing_focus_store',lambda _:focus)
    service=GoalService(GoalStore(path));monkeypatch.setattr(service,'_interrupt_runs',lambda _:None)
    submit(focus,'create',goal_id=goal['id'],title='定义',criterion_ids=['c1']);t=focus.snapshot()['tasks'][0]
    start(focus,t);clock[0]+=15
    paused=service.pause(goal['id'],expected_revision=goal['revision'])
    assert paused['status']=='paused' and focus.snapshot()['current_session']['status']=='ended'
    assert focus.snapshot()['active_ms']==15000
    service.update(goal['id'],expected_revision=paused['revision'],changes={'success_criteria':[]})
    assert focus.snapshot()['current_task']['criterion_ids']==['c1']
    submit(focus,'update',task_id=t['id'],title='阅读旧条件对应定义')
    assert focus.snapshot()['current_task']['criterion_ids']==['c1']


def test_suspend_does_not_add_unknown_resume_interval(setup):
    _,goal,focus,clock,_=setup;t=task(focus,goal)
    start(focus,t);clock[0]+=20;focus.checkpoint();clock[0]+=300
    submit(focus,'pause',reason='suspend')
    assert focus.snapshot()['active_ms']==20000
    assert focus.snapshot()['reason']=='suspend'


def test_midnight_allocation_splits_activity_and_excludes_pauses():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from backend.services.goals.focus_time import daily_totals
    start=datetime(2026,10,14,23,59,50,tzinfo=ZoneInfo('Asia/Shanghai')).timestamp()
    totals=daily_totals([{'started_at':start,'active_ms':20000},{'started_at':start+300,'active_ms':10000}],'Asia/Shanghai')
    assert totals==[{'date':'2026-10-15','active_ms':20000},{'date':'2026-10-14','active_ms':10000}]
    with pytest.raises(ValueError):daily_totals([], 'Invalid/Timezone')


def test_goal_partial_failure_and_invalid_edit_never_claim_cross_store_atomicity(setup,monkeypatch):
    from backend.services.goals.service import GoalService
    from backend.services.goals import focus as module
    path,goal,focus,clock,_=setup;t=task(focus,goal);start(focus,t);clock[0]+=10
    monkeypatch.setattr(module,'existing_focus_store',lambda _:focus)
    service=GoalService(GoalStore(path))
    with pytest.raises(ValueError):service.update(goal['id'],expected_revision=goal['revision'],changes={'objective':'新内容','success_criteria':[{}]})
    assert focus.snapshot()['status']=='running'
    def fail(_):raise RuntimeError('fence failure')
    monkeypatch.setattr(service,'_interrupt_runs',fail)
    with pytest.raises(GoalConflict,match='专注已结束，目标尚未搁置'):
        service.pause(goal['id'],expected_revision=goal['revision'])
    assert focus.snapshot()['status']=='finished'
    assert GoalStore(path).get(goal['id'])['status']=='active'


def test_legacy_goal_projection_rejects_missing_contract(monkeypatch):
    from backend.services.goals import execution
    goal={'status':'active','objective':'学习','scope':{},'success_criteria':[]}
    monkeypatch.setattr(execution,'public_task',lambda *_:{'resumable':True})
    invalid=execution.project_goal_runtime(None,{'run':{'checkpoint':{}}},goal)
    assert not invalid['resumable'] and '已有结果保留' in invalid['resume_block_reason']
    valid=execution.project_goal_runtime(None,{'run':{'checkpoint':{'goal_contract':execution.goal_contract(goal)}}},goal)
    assert valid['resumable']


def test_brand_new_focus_bootstrap_and_existing_legacy_remains_explicit(tmp_path):
    from backend.services.goals.focus import get_focus_store
    fresh=tmp_path/'fresh.db'
    assert get_focus_store(fresh).snapshot()['tasks']==[]
    assert sqlite3.connect(fresh).execute('PRAGMA user_version').fetchone()[0]==3
    legacy=tmp_path/'existing.db';GoalStore(legacy)
    with pytest.raises(FocusMigrationRequired):get_focus_store(legacy)
    assert sqlite3.connect(legacy).execute('PRAGMA user_version').fetchone()[0]==1


def test_management_locator_returns_task_page_without_switching_current(setup):
    _,goal,focus,_,_=setup
    for page in range(6):submit(focus,'create_batch',goal_id=goal['id'],tasks=[{'title':f'行动{page*20+i}'} for i in range(20)])
    last=focus.snapshot(offset=100)['tasks'][-1]
    selected=focus.snapshot()['tasks'][0]
    submit(focus,'select',task_id=selected['id'])
    located=focus.snapshot(goal_id=goal['id'],around_task_id=last['id'])
    assert located['page_offset']==100
    assert last['id'] in [item['id'] for item in located['tasks']]
    assert located['current_task']['id']==selected['id']
    assert located['current_session'] is None
