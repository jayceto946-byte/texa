"""Explicit, backed-up Focus v3 migration. Never invoked implicitly by an API read."""
from contextlib import closing
from pathlib import Path
import sqlite3
import time


class FocusMigrationRequired(RuntimeError):
    pass


def migrate_focus(path: Path):
    path=Path(path)
    if not path.is_file():
        raise FocusMigrationRequired('数据库不存在，未执行迁移')
    with closing(sqlite3.connect(path, isolation_level=None)) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version == 3:
            return None
        if version not in (1, 2):
            raise FocusMigrationRequired('不支持的专注记录版本')
        backup = path.with_name(f'{path.stem}-before-focus-v3-{time.time_ns()}.db')
        with closing(sqlite3.connect(backup)) as target:
            conn.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('专注迁移备份校验失败')
        conn.execute('BEGIN IMMEDIATE')
        try:
            if version == 1:
                conn.execute("CREATE TABLE focus_tasks (id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id), title TEXT NOT NULL, content TEXT NOT NULL, duration_seconds INTEGER NOT NULL, elapsed_seconds REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending', revision INTEGER NOT NULL DEFAULT 1)")
                conn.execute("CREATE TABLE focus_state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, task_id TEXT, status TEXT NOT NULL, started_at REAL, elapsed_seconds REAL NOT NULL)")
                conn.execute("INSERT INTO focus_state VALUES (1,0,NULL,'idle',NULL,0)")
                conn.execute("CREATE TABLE focus_receipts (operation_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, response_json TEXT NOT NULL)")
            for definition in ('position INTEGER NOT NULL DEFAULT 0', "criterion_ids TEXT NOT NULL DEFAULT '[]'", 'completed_at REAL', 'deleted_at REAL', 'legacy_elapsed_ms INTEGER NOT NULL DEFAULT 0'):
                conn.execute(f'ALTER TABLE focus_tasks ADD COLUMN {definition}')
            # Only committed legacy time is known. Never fill an offline tail from wall time.
            conn.execute('UPDATE focus_tasks SET position=rowid, legacy_elapsed_ms=CAST(elapsed_seconds*1000 AS INTEGER)')
            conn.execute("UPDATE focus_tasks SET legacy_elapsed_ms=MAX(legacy_elapsed_ms, CAST((SELECT elapsed_seconds FROM focus_state WHERE id=1)*1000 AS INTEGER)) WHERE id=(SELECT task_id FROM focus_state WHERE id=1)")
            conn.execute("UPDATE focus_tasks SET status='pending' WHERE status='in_progress'")
            conn.execute('ALTER TABLE focus_state ADD COLUMN session_id TEXT')
            conn.execute("ALTER TABLE focus_state ADD COLUMN reason TEXT NOT NULL DEFAULT ''")
            conn.execute('ALTER TABLE focus_state ADD COLUMN checkpoint_at REAL')
            conn.execute("UPDATE focus_state SET status='idle',started_at=NULL,reason=CASE WHEN status='running' THEN 'legacy_interrupted' ELSE '' END,revision=revision+1")
            conn.execute("CREATE TABLE focus_sessions (id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES focus_tasks(id), mode TEXT NOT NULL CHECK(mode IN ('countdown','stopwatch')), target_seconds INTEGER, status TEXT NOT NULL CHECK(status IN ('running','paused','ended')), started_at REAL NOT NULL, ended_at REAL, end_reason TEXT NOT NULL DEFAULT '', active_ms INTEGER NOT NULL DEFAULT 0 CHECK(active_ms>=0), revision INTEGER NOT NULL DEFAULT 1)")
            conn.execute("CREATE UNIQUE INDEX focus_single_open_session ON focus_sessions ((1)) WHERE status!='ended'")
            conn.execute("CREATE TABLE focus_segments (session_id TEXT NOT NULL REFERENCES focus_sessions(id), sequence INTEGER NOT NULL, started_at REAL NOT NULL, ended_at REAL, active_ms INTEGER NOT NULL DEFAULT 0 CHECK(active_ms>=0), end_reason TEXT NOT NULL DEFAULT '', PRIMARY KEY(session_id,sequence))")
            conn.execute('CREATE INDEX focus_task_queue ON focus_tasks(goal_id,deleted_at,position,id)')
            conn.execute('CREATE INDEX focus_task_history ON focus_sessions(task_id,started_at,id)')
            conn.execute('PRAGMA user_version=3')
            if conn.execute('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('专注迁移关系校验失败')
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        return backup
