"""Conversation navigation metadata; message events and learning assets stay intact."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from backend.services.goals.service import GOAL_CONTROL_LOCK

SCHEMA_VERSION = 1
BLOCKING_STATUSES = {'running', 'waiting_for_input', 'waiting_for_confirmation', 'interrupted'}


class ConversationManagementError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409, **details):
        super().__init__(message)
        self.code, self.status, self.details = code, status, details


def _now():
    return datetime.now(timezone.utc).isoformat()


def _dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _valid_id(value: str):
    if not re.fullmatch(r'[\w.\-]{1,80}', value or ''):
        raise ConversationManagementError('invalid_conversation', '会话标识无效', 422)


def _default():
    return {'state': 'active', 'pinned': False, 'revision': 0, 'updated_at': '', 'previous_state': None}


def ensure_management_schema(conn: sqlite3.Connection):
    """Version only this extension; legacy event DB has no global schema version."""
    conn.execute('CREATE TABLE IF NOT EXISTS conversation_management_schema (component TEXT PRIMARY KEY,version INTEGER NOT NULL)')
    row = conn.execute("SELECT version FROM conversation_management_schema WHERE component='navigation'").fetchone()
    if row and row[0] != SCHEMA_VERSION:
        raise ConversationManagementError('storage_unavailable', '会话管理存储版本高于当前程序，请升级后打开。', 503)
    conn.execute("CREATE TABLE IF NOT EXISTS conversation_management (conversation_id TEXT PRIMARY KEY,pinned INTEGER NOT NULL DEFAULT 0 CHECK(pinned IN (0,1)),state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','archived','trashed')),revision INTEGER NOT NULL CHECK(revision>=0),updated_at TEXT NOT NULL,previous_state TEXT CHECK(previous_state IN ('active','archived')))")
    conn.execute('CREATE TABLE IF NOT EXISTS conversation_management_operations (operation_id TEXT PRIMARY KEY,args_hash TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL)')
    conn.execute("INSERT OR IGNORE INTO conversation_management_schema VALUES ('navigation',?)", (SCHEMA_VERSION,))


def _metadata(conn, conversation_id):
    row = conn.execute('SELECT state,pinned,revision,updated_at,previous_state FROM conversation_management WHERE conversation_id=?', (conversation_id,)).fetchone()
    return dict(zip(('state', 'pinned', 'revision', 'updated_at', 'previous_state'), row)) | {'pinned': bool(row[1])} if row else _default()


def assert_conversation_writable(conversation_id: str, *, progress_root: Path | None = None):
    """Called inside the shared Runtime/legacy admission fence. No optional IO creation."""
    if not conversation_id:
        return
    _valid_id(conversation_id)
    if progress_root is None:
        from backend.conversation_memory import CONV_DIR
        path = CONV_DIR / '_conversation_events.db'
    else:
        path = Path(progress_root) / 'conversations' / '_conversation_events.db'
    if not path.exists():
        return
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='conversation_management'").fetchone():
            return
        version = conn.execute("SELECT version FROM conversation_management_schema WHERE component='navigation'").fetchone()
        if not version or version[0] != SCHEMA_VERSION:
            raise ConversationManagementError('storage_unavailable', '会话管理存储版本无法核对，请升级后打开。', 503)
        state = _metadata(conn, conversation_id)['state']
    if state == 'trashed':
        raise ConversationManagementError('conversation_trashed', '会话已在回收站，请明确恢复后再继续提问。')


def validate_management_database(path: Path | str):
    """Restore gate accepts legacy archives; rejects future or malformed metadata."""
    path = Path(path)
    if not path.exists():
        return
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'conversation_management' not in tables:
            return
        required = {'conversation_management_schema', 'conversation_management_operations'}
        if not required.issubset(tables):
            raise ValueError('conversation management storage is incomplete')
        version = conn.execute("SELECT version FROM conversation_management_schema WHERE component='navigation'").fetchone()
        if not version or version[0] != SCHEMA_VERSION:
            raise ValueError('unsupported conversation management storage version')
        if conn.execute("SELECT 1 FROM conversation_management WHERE state NOT IN ('active','archived','trashed') OR pinned NOT IN (0,1) OR revision<0 OR (previous_state IS NOT NULL AND previous_state NOT IN ('active','archived')) LIMIT 1").fetchone():
            raise ValueError('damaged conversation management metadata')


class ConversationManagementService:
    def __init__(self, *, progress_root: Path | str | None = None):
        from backend import conversation_memory as memory
        self.memory = memory
        self.progress_root = Path(progress_root) if progress_root is not None else memory.CONV_DIR.parent
        self.db_path = self.progress_root / 'conversations' / '_conversation_events.db'

    def _connect(self):
        # The default authority creates the established message tables first.
        if self.db_path == self.memory.CONV_DIR / '_conversation_events.db':
            conn = self.memory._connect_events()
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout=10000')
        try:
            conn.execute('BEGIN IMMEDIATE')
            ensure_management_schema(conn)
            conn.commit()
            return conn
        except BaseException:
            conn.rollback()
            conn.close()
            raise

    def get(self, conversation_id):
        _valid_id(conversation_id)
        with closing(self._connect()) as conn:
            return _metadata(conn, conversation_id)

    def blocking_tasks(self, conversation_id: str):
        with GOAL_CONTROL_LOCK:
            try:
                return self._blocking_tasks(conversation_id)
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
                raise ConversationManagementError('task_state_unavailable', '未完成任务状态暂时无法核对，请稍后重试。', 503) from None

    def _blocking_tasks(self, conversation_id: str):
        """Read real task authorities, never old message snapshots or capped lists."""
        from backend.services.learning_task import LearningTaskStore
        tasks = []
        legacy = LearningTaskStore(self.progress_root)
        for path in legacy.root.glob('*.json'):
            value = json.loads(path.read_text(encoding='utf-8'))
            if value.get('conversation_id') == conversation_id and value.get('status') in BLOCKING_STATUSES:
                tasks.append({'id': value['id'], 'status': value['status'], 'run_id': value.get('artifacts', {}).get('active_run_id', ''), 'revision': None, 'can_cancel': value['status'] != 'running', 'backend': 'legacy'})
        runtime_path = self.progress_root / 'agent_runtime.db'
        if runtime_path.exists():
            with closing(sqlite3.connect(runtime_path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)) as conn:
                for row in conn.execute('SELECT id,status,revision,snapshot_json FROM runtime_tasks'):
                    snapshot = json.loads(row[3])
                    if snapshot.get('conversation_id') != conversation_id:
                        continue
                    uncertain = conn.execute("SELECT 1 FROM tool_calls WHERE task_id=? AND permission='LOCAL_WRITE' AND status='unknown' LIMIT 1", (row[0],)).fetchone()
                    if row[1] not in BLOCKING_STATUSES and not uncertain:
                        continue
                    latest = conn.execute('SELECT id FROM agent_runs WHERE task_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (row[0],)).fetchone()
                    tasks.append({'id': row[0], 'status': row[1], 'run_id': latest[0] if latest else '', 'revision': row[2], 'can_cancel': row[1] != 'running' and not bool(uncertain), 'backend': 'runtime', 'unknown_write': bool(uncertain)})
        return tasks

    @staticmethod
    def _receipt(conn, operation_id, args):
        old = conn.execute('SELECT args_hash,result_json FROM conversation_management_operations WHERE operation_id=?', (operation_id,)).fetchone()
        if not old:
            return None
        if old[0] != hashlib.sha256(_dump(args).encode()).hexdigest():
            raise ConversationManagementError('operation_conflict', '操作标识已用于不同请求。')
        return json.loads(old[1])

    @staticmethod
    def _save_receipt(conn, operation_id, args, result):
        conn.execute('INSERT INTO conversation_management_operations VALUES (?,?,?,?)', (operation_id, hashlib.sha256(_dump(args).encode()).hexdigest(), _dump(result), _now()))

    def change(self, conversation_id, *, action, operation_id, expected_revision):
        _valid_id(conversation_id)
        if action not in {'pin', 'unpin', 'archive', 'restore', 'trash'}:
            raise ConversationManagementError('invalid_action', '不支持的会话管理操作。', 422)
        if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 120 or not isinstance(expected_revision, int) or expected_revision < 0:
            raise ConversationManagementError('invalid_operation', '管理请求缺少有效的操作标识或版本。', 422)
        args = ['management', conversation_id, action, expected_revision]
        with GOAL_CONTROL_LOCK, closing(self._connect()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                old = self._receipt(conn, operation_id, args)
                if old is not None:
                    conn.rollback(); return old
                if self.db_path == self.memory.CONV_DIR / '_conversation_events.db':
                    self.memory._ensure_event_projection(conn, conversation_id)
                if not conn.execute('SELECT 1 FROM conversation_messages WHERE conversation_id=? LIMIT 1', (conversation_id,)).fetchone():
                    raise ConversationManagementError('conversation_not_found', '尚未保存的空会话无需管理。', 404)
                current = _metadata(conn, conversation_id)
                if current['revision'] != expected_revision:
                    raise ConversationManagementError('revision_conflict', '会话状态已变化，请重新读取。', management=current)
                if action in {'archive', 'trash'}:
                    tasks = self.blocking_tasks(conversation_id)
                    if tasks:
                        raise ConversationManagementError('conversation_busy', '会话有未完成任务，请先停止并明确结束，或继续完成任务。', tasks=tasks)
                result = {**current, 'revision': current['revision'] + 1, 'updated_at': _now()}
                if action in {'pin', 'unpin'}:
                    if current['state'] == 'trashed':
                        raise ConversationManagementError('conversation_trashed', '请先恢复回收站会话。')
                    result['pinned'] = action == 'pin'
                elif action == 'archive':
                    if current['state'] == 'trashed':
                        raise ConversationManagementError('conversation_trashed', '请先恢复回收站会话。')
                    result['state'] = 'archived'
                elif action == 'trash':
                    if current['state'] != 'trashed':
                        result.update(state='trashed', previous_state=current['state'])
                else:
                    restored_state = (current['previous_state'] or 'active') if current['state'] == 'trashed' else 'active'
                    result.update(state=restored_state, previous_state=None)
                conn.execute('INSERT INTO conversation_management VALUES (?,?,?,?,?,?) ON CONFLICT(conversation_id) DO UPDATE SET pinned=excluded.pinned,state=excluded.state,revision=excluded.revision,updated_at=excluded.updated_at,previous_state=excluded.previous_state', (conversation_id, int(result['pinned']), result['state'], result['revision'], result['updated_at'], result['previous_state']))
                self._save_receipt(conn, operation_id, args, result)
                conn.commit(); return result
            except BaseException:
                conn.rollback(); raise

    def page(self, *, view='active', subject='', book_name='', book_names=None, limit=40, cursor=''):
        if view not in {'active', 'archived', 'trashed'}:
            raise ConversationManagementError('invalid_view', '会话视图无效。', 422)
        limit = max(1, min(int(limit), 200))
        # Catalog is complete and contains summaries only; no full history enters UI.
        with GOAL_CONTROL_LOCK:
            catalog = self.memory.conversation_catalog(subject=subject, book_name=book_name, book_names=book_names)
            with closing(self._connect()) as conn:
                rows = [{**row, 'management': _metadata(conn, row['id'])} for row in catalog]
        rows = [row for row in rows if row['management']['state'] == view]
        def order(row):
            return (int(row['management']['pinned']), row.get('updated_at') or '', row['id'])
        rows.sort(key=order, reverse=True)
        scope = [view, subject, book_name, sorted(set(book_names or []))]
        generation = hashlib.sha256(_dump([(row["id"], order(row), row["message_count"], row["management"]["revision"]) for row in rows]).encode()).hexdigest()
        if cursor:
            try:
                value = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                if value['scope'] != scope or value.get('generation') != generation or len(value['after']) != 3:
                    raise ValueError('changed scope')
                after = tuple(value['after'])
                rows = [row for row in rows if order(row) < after]
            except (ValueError, TypeError, KeyError, UnicodeError):
                raise ConversationManagementError('invalid_cursor', '分页游标已失效，请从第一页重新读取。', 422) from None
        items = rows[:limit]
        more = len(rows) > limit
        next_cursor = base64.urlsafe_b64encode(_dump({'scope': scope, 'generation': generation, 'after': order(items[-1])}).encode()).decode() if more else None
        return {'items': items, 'next_cursor': next_cursor, 'has_more': more}

    def cancel_task(self, task_id, *, operation_id, expected_run_id, expected_revision=None):
        from backend.services.learning_task import LearningTaskStore
        from backend.services.agent_runtime.store import RuntimeStore
        _valid_id(task_id)
        if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 120 or not expected_run_id:
            raise ConversationManagementError('invalid_operation', '结束任务需要操作标识和运行标识。', 422)
        if task_id.startswith('rtask_') and (not isinstance(expected_revision, int) or expected_revision < 0):
            raise ConversationManagementError('invalid_operation', 'Runtime 结束任务需要当前版本。', 422)
        args = ['cancel_task', task_id, expected_run_id, expected_revision]
        with GOAL_CONTROL_LOCK, closing(self._connect()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                old = self._receipt(conn, operation_id, args)
                if old is not None:
                    conn.rollback(); return old
                if task_id.startswith('rtask_'):
                    path = self.progress_root / 'agent_runtime.db'
                    if not path.exists():
                        raise ConversationManagementError('task_not_found', '任务不存在。', 404)
                    result = RuntimeStore(path).cancel_task(task_id, expected_revision=expected_revision, expected_run_id=expected_run_id, operation_id=operation_id)
                else:
                    store = LearningTaskStore(self.progress_root)
                    task = store.get(task_id)
                    if not task:
                        raise ConversationManagementError('task_not_found', '任务不存在。', 404)
                    if task.task_type not in {'qa', 'visual_qa', 'figure_qa'} or not task.conversation_id:
                        raise ConversationManagementError('task_conflict', '此入口只能结束会话学习任务。')
                    if task.artifacts.get('active_run_id', '') != expected_run_id:
                        raise ConversationManagementError('task_conflict', '任务运行已变化，请重新读取。')
                    if task.status == 'running':
                        raise ConversationManagementError('task_running', '请先停止运行，再结束任务。')
                    if task.status not in {'interrupted', 'waiting_for_input', 'waiting_for_confirmation', 'cancelled'}:
                        raise ConversationManagementError('task_conflict', '当前任务不需要结束。')
                    from backend.services.pending_actions import PendingActionStore
                    actions = PendingActionStore(self.progress_root)
                    settled = {}
                    for path in actions.root.glob('*.json'):
                        action = actions.get(path.stem)
                        if (action.get('context') or {}).get('learning_task_id') != task_id or action.get('status') not in {'pending', 'failed'}:
                            continue
                        try:
                            receipt = actions.domain_receipt(path.stem)
                            if receipt is not None:
                                # A crash may have committed a domain write before its JSON receipt.
                                actions.confirm(path.stem)
                                settled[path.stem] = 'executed'
                            else:
                                actions.reject(path.stem)
                                settled[path.stem] = 'rejected'
                        except (OSError, ValueError, KeyError, sqlite3.Error):
                            raise ConversationManagementError('unknown_write', '既有写入结果尚未核对，不能结束任务。') from None
                    for action in task.artifacts.get('pending_actions', []):
                        aid = action.get('action_id')
                        if aid in settled:
                            action.update(status=settled[aid], allowed_actions=[])
                        elif action.get('status') in {'pending', 'expired'}:
                            action.update(status='rejected', allowed_actions=[])
                    if task.status != 'cancelled':
                        task = store.checkpoint(task, 'user_cancelled', status='cancelled', detail='用户明确结束未完成任务；已有内容保留')
                    result = task.to_dict(public=True)
                self._save_receipt(conn, operation_id, args, result)
                conn.commit(); return result
            except BaseException:
                conn.rollback(); raise
