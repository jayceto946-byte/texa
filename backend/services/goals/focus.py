"""User-controlled focus tasks. Never starts Runtime, models, review or mastery writes."""
from __future__ import annotations
import hashlib
import json
import sqlite3
import time
import uuid
import threading
from contextlib import contextmanager, closing
from pathlib import Path
from backend.services.goals.store import GoalConflict, GoalStore

_migration_lock = threading.Lock()

def _dump(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

class FocusStore:
    def __init__(self, path, *, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        GoalStore(self.path)  # existing schema initialization and forward compatibility check
        with _migration_lock, self._connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 1:
                backup = self.path.with_name(f"{self.path.stem}-before-focus-v2-{time.time_ns()}.db")
                with closing(sqlite3.connect(backup)) as target:
                    conn.backup(target)
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute("CREATE TABLE IF NOT EXISTS focus_tasks (id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id), title TEXT NOT NULL, content TEXT NOT NULL, duration_seconds INTEGER NOT NULL, elapsed_seconds REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending', revision INTEGER NOT NULL DEFAULT 1)")
                    conn.execute("CREATE TABLE IF NOT EXISTS focus_state (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, task_id TEXT, status TEXT NOT NULL, started_at REAL, elapsed_seconds REAL NOT NULL)")
                    conn.execute("INSERT OR IGNORE INTO focus_state VALUES (1,0,NULL,'idle',NULL,0)")
                    conn.execute("CREATE TABLE IF NOT EXISTS focus_receipts (operation_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, response_json TEXT NOT NULL)")
                    conn.execute("PRAGMA user_version=2")
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
            elif version != 2:
                raise ValueError("不支持的专注记录版本")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _write(self):
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def _elapsed(self, state, task):
        elapsed = state["elapsed_seconds"]
        if state["status"] == "running":
            elapsed += max(0, self.clock() - state["started_at"])
        return min(task["duration_seconds"], elapsed)

    def _snapshot(self, conn):
        state = dict(conn.execute("SELECT * FROM focus_state WHERE id=1").fetchone())
        tasks = [dict(row) for row in conn.execute("SELECT t.* FROM focus_tasks t JOIN goals g ON g.id=t.goal_id WHERE g.learner_id='local_default' ORDER BY t.rowid LIMIT 100")]
        task = next((item for item in tasks if item["id"] == state["task_id"]), None)
        elapsed = self._elapsed(state, task) if task else 0
        return {"revision":state["revision"], "tasks":tasks, "current_task":task,
                "status":"expired" if task and state["status"] == "running" and elapsed >= task["duration_seconds"] else state["status"],
                "remaining_seconds":max(0, task["duration_seconds"] - elapsed) if task else 0,
                "server_time":self.clock()}

    def snapshot(self):
        with self._connect() as conn:
            return self._snapshot(conn)

    def receipt(self, operation_id):
        with self._connect() as conn:
            row = conn.execute("SELECT response_json FROM focus_receipts WHERE operation_id=?", (operation_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def command(self, payload):
        operation_id = payload.get("operation_id", "")
        if not isinstance(operation_id,str) or not 1 <= len(operation_id) <= 100:
            raise ValueError("缺少有效操作标识")
        digest = hashlib.sha256(_dump(payload).encode()).hexdigest()
        with self._write() as conn:
            receipt = conn.execute("SELECT * FROM focus_receipts WHERE operation_id=?", (operation_id,)).fetchone()
            if receipt:
                if receipt["payload_hash"] != digest:
                    raise GoalConflict("同一操作标识不能提交不同内容")
                return json.loads(receipt["response_json"])
            state = dict(conn.execute("SELECT * FROM focus_state WHERE id=1").fetchone())
            if payload.get("expected_revision") != state["revision"]:
                raise GoalConflict("专注任务已在另一页面更新，请刷新后操作")
            operation = payload.get("operation")
            if operation == "create":
                goal = conn.execute("SELECT * FROM goals WHERE id=? AND learner_id='local_default'", (payload.get("goal_id"),)).fetchone()
                if not goal or goal["status"] in {"completed", "cancelled"}:
                    raise ValueError("该目标不可添加专注任务")
                count = conn.execute("SELECT COUNT(*) FROM focus_tasks").fetchone()[0]
                if count >= 100:
                    raise ValueError("当前最多保存100个专注任务")
                title, content, duration = payload.get("title", "").strip(), payload.get("content", "").strip(), payload.get("duration_seconds",1500)
                if not 1 <= len(title) <= 200 or len(content) > 2000 or type(duration) is not int or not 60 <= duration <= 7200:
                    raise ValueError("请填写任务内容与1–120分钟时长")
                conn.execute("INSERT INTO focus_tasks(id,goal_id,title,content,duration_seconds) VALUES (?,?,?,?,?)", ("focus_"+uuid.uuid4().hex,goal["id"],title,content,duration))
            else:
                task_id = payload.get("task_id") or state["task_id"]
                target = conn.execute("SELECT t.* FROM focus_tasks t JOIN goals g ON g.id=t.goal_id WHERE t.id=? AND g.learner_id='local_default'",(task_id,)).fetchone()
                if not target:
                    raise ValueError("找不到专注任务")
                current = conn.execute("SELECT * FROM focus_tasks WHERE id=?",(state["task_id"],)).fetchone()
                elapsed = self._elapsed(state,current) if current else 0
                if operation in {"start", "switch"}:
                    if target["status"] == "completed":
                        raise ValueError("已完成任务不能继续计时")
                    if current and state["status"] == "running":
                        conn.execute("UPDATE focus_tasks SET elapsed_seconds=?,revision=revision+1 WHERE id=?",(elapsed,current["id"]))
                    remaining_elapsed = elapsed if current and current["id"] == target["id"] else target["elapsed_seconds"]
                    if remaining_elapsed >= target["duration_seconds"]:
                        raise ValueError("本次计时已到期，请结束或标记完成")
                    conn.execute("UPDATE focus_state SET task_id=?,status='running',started_at=?,elapsed_seconds=? WHERE id=1",(target["id"],self.clock(),remaining_elapsed))
                    conn.execute("UPDATE focus_tasks SET status='in_progress',revision=revision+1 WHERE id=?",(target["id"],))
                elif operation in {"pause", "finish", "complete"}:
                    if state["task_id"] != target["id"]:
                        raise ValueError("请先选择该任务")
                    conn.execute("UPDATE focus_tasks SET elapsed_seconds=?,status=?,revision=revision+1 WHERE id=?",(elapsed,"completed" if operation == "complete" else target["status"],target["id"]))
                    conn.execute("UPDATE focus_state SET status=?,started_at=NULL,elapsed_seconds=? WHERE id=1",("finished" if operation in {"finish","complete"} else "paused",elapsed))
                else:
                    raise ValueError("不支持的专注操作")
            conn.execute("UPDATE focus_state SET revision=revision+1 WHERE id=1")
            response = self._snapshot(conn)
            conn.execute("INSERT INTO focus_receipts VALUES (?,?,?)",(operation_id,digest,_dump(response)))
            return response
