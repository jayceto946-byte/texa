"""User-controlled study tasks and monotonic focus sessions; no models or mastery writes."""
from __future__ import annotations
from contextlib import contextmanager, closing
from pathlib import Path
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from backend.services.goals.store import GoalConflict
from backend.services.goals.service import GOAL_CONTROL_LOCK
from backend.services.goals.focus_migration import FocusMigrationRequired, migrate_focus


_runtime_id=uuid.uuid4().hex


def _dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


class FocusStore:
    def __init__(self, path, *, clock=time.monotonic, wall_clock=time.time, allow_migration=False, max_gap_seconds=90):
        self.path = Path(path)
        self.clock, self.wall_clock = clock, wall_clock
        self.max_gap_seconds = max_gap_seconds
        self.lock = threading.RLock()
        self.anchor = None
        self.sequence = 0
        # A missing/older DB is a deployment decision, not a side effect of GET /focus.
        if not self.path.exists():
            raise FocusMigrationRequired('专注记录尚未初始化，请先完成显式数据库迁移')
        with closing(sqlite3.connect(f'file:{self.path}?mode=ro', uri=True)) as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version != 3:
            if not allow_migration:
                raise FocusMigrationRequired('专注记录需要显式升级；旧记录已保留，请先备份并批准迁移')
            migrate_focus(self.path)
        self.recover_unfinished()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA synchronous=FULL')
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write(self):
        with self.lock, self._connect() as conn:
            anchor = self.anchor
            conn.execute('BEGIN IMMEDIATE')
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                self.anchor = anchor
                raise

    def _state(self, conn):
        return dict(conn.execute('SELECT * FROM focus_state WHERE id=1').fetchone())

    def _session(self, conn, state):
        row = conn.execute('SELECT * FROM focus_sessions WHERE id=?', (state['session_id'],)).fetchone()
        return dict(row) if row else None

    def _delta(self, session):
        if not session or session['status'] != 'running' or not self.anchor or self.anchor[0] != session['id']:
            return 0
        return max(0, int((self.clock()-self.anchor[1])*1000))

    def _commit_time(self, conn, state):
        session = self._session(conn, state)
        if not session or session['status'] != 'running':
            return
        delta = self._delta(session)
        if not self.anchor or (self.max_gap_seconds is not None and delta > self.max_gap_seconds*1000):
            self._close_segment(conn, state, 'interrupted', commit=False)
            return
        conn.execute('UPDATE focus_sessions SET active_ms=active_ms+?,revision=revision+1 WHERE id=?', (delta, session['id']))
        conn.execute('UPDATE focus_segments SET active_ms=active_ms+? WHERE session_id=? AND ended_at IS NULL', (delta, session['id']))
        conn.execute('UPDATE focus_state SET checkpoint_at=? WHERE id=1', (self.wall_clock(),))
        self.anchor = (session['id'], self.clock())

    def _close_segment(self, conn, state, reason, *, commit=True):
        if commit:
            self._commit_time(conn, state)
        session = self._session(conn, state)
        if session and session['status'] == 'running':
            # Interrupted tails stop at the last confirmed checkpoint, not at restart time.
            ended = self.wall_clock() if commit else state['checkpoint_at'] or session['started_at']
            conn.execute('UPDATE focus_segments SET ended_at=?,end_reason=? WHERE session_id=? AND ended_at IS NULL', (ended, reason, session['id']))
            conn.execute("UPDATE focus_sessions SET status='paused',end_reason=?,revision=revision+1 WHERE id=?", (reason, session['id']))
            conn.execute("UPDATE focus_state SET status='paused',reason=?,started_at=NULL WHERE id=1", (reason,))
        self.anchor = None

    def _end(self, conn, state, reason):
        self._close_segment(conn, state, reason)
        session = self._session(conn, state)
        if session and session['status'] != 'ended':
            conn.execute("UPDATE focus_sessions SET status='ended',ended_at=?,end_reason=?,revision=revision+1 WHERE id=?", (self.wall_clock(), reason, session['id']))
        conn.execute("UPDATE focus_state SET status='finished',reason=?,started_at=NULL WHERE id=1", (reason,))

    def recover_unfinished(self):
        with self._write() as conn:
            state = self._state(conn)
            session = self._session(conn, state)
            if session and session['status'] == 'running':
                self._close_segment(conn, state, 'interrupted', commit=False)
                conn.execute('UPDATE focus_state SET revision=revision+1 WHERE id=1')

    def checkpoint(self):
        with self._write() as conn:
            state = self._state(conn)
            self._commit_time(conn, state)
            if self._state(conn)['status'] != state['status']:
                conn.execute('UPDATE focus_state SET revision=revision+1 WHERE id=1')

    def _task(self, conn, task_id, *, deleted=False):
        row = conn.execute("SELECT t.*, json_extract(g.snapshot_json,'$.title') AS goal_title, g.status AS goal_status, g.revision AS goal_revision FROM focus_tasks t JOIN goals g ON g.id=t.goal_id WHERE t.id=? AND g.learner_id='local_default'", (task_id,)).fetchone()
        if not row or (row['deleted_at'] is not None and not deleted):
            return None
        task = dict(row)
        task['criterion_ids'] = json.loads(task['criterion_ids'])
        confirmed = conn.execute('SELECT COALESCE(SUM(active_ms),0) FROM focus_sessions WHERE task_id=?', (task_id,)).fetchone()[0]
        task['active_ms'] = confirmed + task['legacy_elapsed_ms']
        task['elapsed_seconds'] = task['active_ms']/1000
        return task

    def _snapshot(self, conn, *, goal_id='', offset=0, limit=100, task_status=''):
        state = self._state(conn)
        task = self._task(conn, state['task_id'])
        session = self._session(conn, state)
        delta = self._delta(session)
        active = (session['active_ms'] if session else 0) + delta
        if session:
            session['confirmed_active_ms'] = session['active_ms']
            session['active_ms'] = active
        if task:
            task['active_ms'] += delta
            task['elapsed_seconds'] = task['active_ms']/1000
        rows = conn.execute("SELECT t.id FROM focus_tasks t JOIN goals g ON g.id=t.goal_id WHERE g.learner_id='local_default' AND t.deleted_at IS NULL AND (?='' OR t.goal_id=?) AND (?='' OR t.status=?) ORDER BY t.position,t.id LIMIT ? OFFSET ?", (goal_id, goal_id, task_status, task_status, limit+1, offset)).fetchall()
        target = session['target_seconds'] if session else (task['duration_seconds'] if task else None)
        stats = [dict(row) for row in conn.execute("SELECT t.goal_id,SUM(t.deleted_at IS NULL) AS task_count,SUM(t.status='completed' AND t.deleted_at IS NULL) AS completed_count,SUM(t.legacy_elapsed_ms+COALESCE((SELECT SUM(s.active_ms) FROM focus_sessions s WHERE s.task_id=t.id),0)) AS active_ms FROM focus_tasks t JOIN goals g ON g.id=t.goal_id WHERE g.learner_id='local_default' GROUP BY t.goal_id")]
        if task and delta:
            for item in stats:
                if item['goal_id'] == task['goal_id']:
                    item['active_ms'] += delta
        self.sequence += 1
        next_row=conn.execute("SELECT id FROM focus_tasks WHERE goal_id=? AND deleted_at IS NULL AND status='pending' AND id!=? ORDER BY position,id LIMIT 1",(task['goal_id'],task['id'])).fetchone() if task else None
        return dict(runtime_id=_runtime_id,next_task=self._task(conn,next_row[0]) if next_row else None,revision=state['revision'],snapshot_sequence=self.sequence,server_time=self.wall_clock(),
                    tasks=[self._task(conn,row['id']) for row in rows[:limit]],next_offset=offset+limit if len(rows)>limit else None,
                    current_task=task,current_session=session,status=state['status'],reason=state['reason'],checkpoint_at=state['checkpoint_at'],
                    active_ms=active,remaining_seconds=max(0,target-active/1000) if target is not None else None,
                    overtime_seconds=max(0,active/1000-target) if target is not None else 0,goal_stats=stats)

    def snapshot(self, *, goal_id='', offset=0, limit=100, task_status='', around_task_id=''):
        if not 1 <= limit <= 100 or offset < 0 or task_status not in ('','pending','completed'):
            raise ValueError('无效任务分页')
        with self._write() as conn:
            state = self._state(conn)
            session = self._session(conn,state)
            if self.max_gap_seconds is not None and self._delta(session) > self.max_gap_seconds*1000:
                self._commit_time(conn,state)
                if self._state(conn)['status'] != state['status']:
                    conn.execute('UPDATE focus_state SET revision=revision+1 WHERE id=1')
            if around_task_id and goal_id:
                target=self._task(conn,around_task_id)
                if target and target['goal_id']==goal_id:
                    rank=conn.execute("SELECT COUNT(*) FROM focus_tasks WHERE goal_id=? AND deleted_at IS NULL AND (?='' OR status=?) AND (position<? OR (position=? AND id<?))",(goal_id,task_status,task_status,target['position'],target['position'],target['id'])).fetchone()[0]
                    offset=(rank//limit)*limit
            return {**self._snapshot(conn,goal_id=goal_id,offset=offset,limit=limit,task_status=task_status),'page_offset':offset}

    def history(self, *, goal_id='', task_id='', offset=0, limit=50, timezone_name='UTC'):
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError('无效历史分页')
        with self._connect() as conn:
            rows = conn.execute("SELECT s.*,t.title,t.goal_id,t.deleted_at FROM focus_sessions s JOIN focus_tasks t ON t.id=s.task_id JOIN goals g ON g.id=t.goal_id WHERE g.learner_id='local_default' AND (?='' OR t.goal_id=?) AND (?='' OR t.id=?) ORDER BY s.rowid DESC LIMIT ? OFFSET ?",(goal_id,goal_id,task_id,task_id,limit+1,offset)).fetchall()
            from backend.services.goals.focus_time import daily_totals
            segments=conn.execute("SELECT seg.started_at,seg.active_ms FROM focus_segments seg JOIN focus_sessions s ON s.id=seg.session_id JOIN focus_tasks t ON t.id=s.task_id JOIN goals g ON g.id=t.goal_id WHERE g.learner_id='local_default' AND (?='' OR t.goal_id=?) AND (?='' OR t.id=?)",(goal_id,goal_id,task_id,task_id)).fetchall()
            return {'sessions':[dict(row) for row in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None,'daily_totals':daily_totals(segments,timezone_name),'timezone':timezone_name}

    def receipt(self, operation_id):
        with self._connect() as conn:
            row = conn.execute('SELECT response_json FROM focus_receipts WHERE operation_id=?', (operation_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def _validate_task(self, conn, goal_id, payload, existing_criteria=()):
        title, content = payload.get('title','').strip(), payload.get('content','').strip()
        duration = payload.get('duration_seconds',1500)
        criteria = payload.get('criterion_ids',[])
        goal = conn.execute("SELECT * FROM goals WHERE id=? AND learner_id='local_default'",(goal_id,)).fetchone()
        if not goal or goal['status'] in ('completed','cancelled'):
            raise ValueError('该目标不可添加或编辑任务')
        if not 1<=len(title)<=200 or len(content)>2000 or type(duration) is not int or not 60<=duration<=7200:
            raise ValueError('请填写有效任务标题与1–120分钟时长')
        valid = {item['id'] for item in json.loads(goal['snapshot_json'])['success_criteria']} | set(existing_criteria)
        if not isinstance(criteria,list) or len(criteria)>12 or any(not isinstance(item,str) or item not in valid for item in criteria):
            raise ValueError('任务条件来源已变化，请重新选择')
        return title,content,duration,_dump(list(dict.fromkeys(criteria)))

    def command(self, payload):
        operation_id = payload.get('operation_id','')
        if not isinstance(operation_id,str) or not 1<=len(operation_id)<=100:
            raise ValueError('缺少有效操作标识')
        digest=hashlib.sha256(_dump(payload).encode()).hexdigest()
        with GOAL_CONTROL_LOCK, self._write() as conn:
            receipt=conn.execute('SELECT * FROM focus_receipts WHERE operation_id=?',(operation_id,)).fetchone()
            if receipt:
                if receipt['payload_hash']!=digest:
                    raise GoalConflict('同一操作标识不能提交不同内容')
                return json.loads(receipt['response_json'])
            state=self._state(conn)
            if payload.get('expected_revision')!=state['revision']:
                raise GoalConflict('任务或专注已更新，请刷新后操作')
            operation=payload.get('operation')
            if operation in ('create','create_batch'):
                items=[payload] if operation=='create' else payload.get('tasks',[])
                if not 1<=len(items)<=20:
                    raise ValueError('一次添加1–20项任务')
                goal_id=payload.get('goal_id','')
                position=conn.execute('SELECT COALESCE(MAX(position),0) FROM focus_tasks WHERE goal_id=?',(goal_id,)).fetchone()[0]
                for index,item in enumerate(items):
                    values=self._validate_task(conn,goal_id,item)
                    conn.execute('INSERT INTO focus_tasks(id,goal_id,title,content,duration_seconds,criterion_ids,position) VALUES (?,?,?,?,?,?,?)',('focus_'+uuid.uuid4().hex,goal_id,*values,position+index+1))
            elif operation=='reorder':
                goal=conn.execute("SELECT status FROM goals WHERE id=? AND learner_id='local_default'",(payload.get('goal_id',''),)).fetchone()
                if not goal or goal['status'] in ('completed','cancelled'):
                    raise ValueError('该目标不可调整任务')
                ids=payload.get('task_ids',[])
                expected={row[0] for row in conn.execute("SELECT id FROM focus_tasks WHERE goal_id=? AND deleted_at IS NULL AND status='pending'",(payload.get('goal_id',''),))}
                if not isinstance(ids,list) or len(ids)!=len(set(ids)) or set(ids)!=expected:
                    raise GoalConflict('任务顺序已变化，请重新读取')
                for position,task_id in enumerate(ids):
                    conn.execute('UPDATE focus_tasks SET position=?,revision=revision+1 WHERE id=?',(position,task_id))
            else:
                target=self._task(conn,payload.get('task_id') or state['task_id'])
                if not target:
                    raise ValueError('找不到任务')
                session=self._session(conn,state)
                open_session=session and session['status']!='ended'
                if operation=='update':
                    values=self._validate_task(conn,target['goal_id'],{**target,**payload},target['criterion_ids'])
                    conn.execute('UPDATE focus_tasks SET title=?,content=?,duration_seconds=?,criterion_ids=?,revision=revision+1 WHERE id=?',(*values,target['id']))
                elif operation in ('complete','reopen','delete'):
                    if operation in ('complete','delete') and open_session and state['task_id']==target['id']:
                        self._end(conn,state,'task_completed' if operation=='complete' else 'task_deleted')
                    conn.execute('UPDATE focus_tasks SET status=?,completed_at=?,deleted_at=?,revision=revision+1 WHERE id=?',('pending' if operation=='reopen' else 'completed' if operation=='complete' else target['status'],self.wall_clock() if operation=='complete' else None,self.wall_clock() if operation=='delete' else None,target['id']))
                    if operation=='delete' and state['task_id']==target['id']:
                        conn.execute("UPDATE focus_state SET task_id=NULL,session_id=NULL,status='idle' WHERE id=1")
                elif operation in ('start','select','switch'):
                    if target['status']=='completed':
                        raise ValueError('请先撤销任务完成，再开始专注')
                    if open_session and (state['task_id']!=target['id'] or operation=='switch'):
                        if operation!='switch':
                            raise GoalConflict('已有未结束专注，请明确结束并切换')
                        self._end(conn,state,'switched')
                        open_session=False
                    if operation=='select' and open_session:
                        pass  # Selecting the current task never discards its live session.
                    elif operation in ('select','switch') and not payload.get('start_after_switch',False):
                        conn.execute("UPDATE focus_state SET task_id=?,session_id=NULL,status='idle',reason='' WHERE id=1",(target['id'],))
                    else:
                        if target['goal_status']!='active':
                            raise GoalConflict('请先明确开始学习或恢复搁置目标')
                        if payload.get('expected_goal_revision')!=target['goal_revision']:
                            raise GoalConflict('目标已变化，请重新读取后开始专注')
                        if open_session:
                            if session['status']=='running':
                                raise GoalConflict('本次专注已经开始')
                            session_id=session['id']
                            conn.execute("UPDATE focus_sessions SET status='running',end_reason='',revision=revision+1 WHERE id=?",(session_id,))
                        else:
                            mode=payload.get('mode','countdown')
                            duration=payload.get('duration_seconds',target['duration_seconds'])
                            if mode not in ('countdown','stopwatch') or type(duration) is not int or not 60<=duration<=7200:
                                raise ValueError('无效专注模式或时长')
                            session_id='focus_session_'+uuid.uuid4().hex
                            conn.execute("INSERT INTO focus_sessions(id,task_id,mode,target_seconds,status,started_at) VALUES (?,?,?,?,'running',?)",(session_id,target['id'],mode,duration if mode=='countdown' else None,self.wall_clock()))
                        number=conn.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM focus_segments WHERE session_id=?',(session_id,)).fetchone()[0]
                        conn.execute('INSERT INTO focus_segments(session_id,sequence,started_at) VALUES (?,?,?)',(session_id,number,self.wall_clock()))
                        conn.execute("UPDATE focus_state SET task_id=?,session_id=?,status='running',started_at=NULL,reason='',checkpoint_at=? WHERE id=1",(target['id'],session_id,self.wall_clock()))
                        self.anchor=(session_id,self.clock())
                elif operation in ('pause','finish','acknowledge'):
                    if not open_session or state['task_id']!=target['id']:
                        raise GoalConflict('没有该任务的未结束专注')
                    if operation=='finish':
                        self._end(conn,state,payload.get('reason') or 'user_ended')
                    elif operation=='pause':
                        self._close_segment(conn,state,payload.get('reason') or 'user_paused',commit=payload.get('reason')!='suspend')
                    else:
                        conn.execute("UPDATE focus_state SET reason='overtime_acknowledged' WHERE id=1")
                else:
                    raise ValueError('不支持的任务或专注操作')
            conn.execute('UPDATE focus_state SET revision=revision+1 WHERE id=1')
            response=self._snapshot(conn)
            conn.execute('INSERT INTO focus_receipts VALUES (?,?,?)',(operation_id,digest,_dump(response)))
            return response

    def settle_goal(self, goal_id, reason='goal_changed'):
        """Focus commit precedes the existing Runtime fence; these are separate commits."""
        with GOAL_CONTROL_LOCK, self._write() as conn:
            state=self._state(conn)
            task=self._task(conn,state['task_id'])
            session=self._session(conn,state)
            if task and task['goal_id']==goal_id and session and session['status']!='ended':
                self._end(conn,state,reason)
                conn.execute('UPDATE focus_state SET revision=revision+1 WHERE id=1')
                return True
            return False


_stores = {}
_stores_lock = threading.RLock()


def get_focus_store(path=None):
    if path is None:
        from backend.services.goals.store import DEFAULT_GOAL_DB_PATH
        path=DEFAULT_GOAL_DB_PATH
    key=str(Path(path).resolve())
    with _stores_lock:
        if key not in _stores:
            fresh=not Path(path).exists()
            if fresh:
                from backend.services.goals.store import GoalStore
                GoalStore(path)
            _stores[key]=FocusStore(path,allow_migration=fresh)
        return _stores[key]


def existing_focus_store(path):
    path=Path(path)
    if not path.exists():
        return None
    with closing(sqlite3.connect(f'file:{path}?mode=ro',uri=True)) as conn:
        if conn.execute('PRAGMA user_version').fetchone()[0]!=3:
            return None
    return get_focus_store(path)


class FocusCheckpointWorker:
    def __init__(self):
        self.stop_event=threading.Event()
        self.thread=threading.Thread(target=self._run,name='focus-checkpoints',daemon=True)

    def start(self):
        self.thread.start()
        return self

    def _run(self):
        import logging
        while not self.stop_event.wait(30):
            with _stores_lock:
                stores=list(_stores.values())
            for store in stores:
                try:
                    store.checkpoint()
                except Exception:
                    logging.getLogger(__name__).exception('Focus checkpoint failed')

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)
        with _stores_lock:
            stores=list(_stores.values())
        for store in stores:
            with store._write() as conn:
                state=store._state(conn)
                if state['status']=='running':
                    store._close_segment(conn,state,'shutdown')
                    conn.execute('UPDATE focus_state SET revision=revision+1 WHERE id=1')
