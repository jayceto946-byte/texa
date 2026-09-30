"""SQLite authority for new P0 tasks and their complete V1 milestone stream."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from config import PROGRESS_PATH
from backend.services.agent_runtime.contracts import RunCommand, RuntimeConflict
from backend.services.execution_events import ExecutionEventEmitter, EXECUTION_EVENT_V2_SCHEMA, validate_execution_event
from utils.sqlite_migrations import apply_sqlite_migrations

SCHEMA_VERSION = 3
DEFAULT_RUNTIME_DB_PATH = Path(PROGRESS_PATH) / "agent_runtime.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _schema(conn: sqlite3.Connection) -> None:
    statements = """
    CREATE TABLE runtime_tasks (
      id TEXT PRIMARY KEY, snapshot_json TEXT NOT NULL, status TEXT NOT NULL,
      active_run_id TEXT, revision INTEGER NOT NULL, budget_calls INTEGER NOT NULL,
      consumed_calls INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE agent_runs (
      id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES runtime_tasks(id),
      resume_of_run_id TEXT, root_run_id TEXT NOT NULL,
      request_key TEXT NOT NULL UNIQUE, request_id TEXT NOT NULL,
      conversation_id TEXT NOT NULL, turn_id TEXT NOT NULL,
      status TEXT NOT NULL, owner_token TEXT NOT NULL,
      revision INTEGER NOT NULL, seq_high_water INTEGER NOT NULL DEFAULT 0,
      checkpoint_json TEXT NOT NULL, output_json TEXT, error_code TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, ended_at TEXT
    );
    CREATE UNIQUE INDEX one_active_run_per_task ON agent_runs(task_id)
      WHERE status IN ('created','running');
    CREATE TABLE tool_calls (
      id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES runtime_tasks(id),
      requested_run_id TEXT NOT NULL REFERENCES agent_runs(id),
      executed_run_id TEXT, step_index INTEGER NOT NULL,
      tool_id TEXT NOT NULL, tool_version TEXT NOT NULL, schema_hash TEXT NOT NULL,
      args_json TEXT NOT NULL, args_hash TEXT NOT NULL,
      operation_key TEXT NOT NULL, status TEXT NOT NULL, attempt_count INTEGER NOT NULL,
      result_json TEXT, receipt_json TEXT, error_code TEXT, created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL, UNIQUE(task_id, operation_key)
    );
    CREATE TABLE execution_events (
      run_id TEXT NOT NULL REFERENCES agent_runs(id), seq INTEGER NOT NULL,
      task_id TEXT NOT NULL REFERENCES runtime_tasks(id), event_json TEXT NOT NULL,
      created_at TEXT NOT NULL, PRIMARY KEY(run_id,seq)
    );
    """
    for statement in statements.split(";"):
        if statement.strip():
            conn.execute(statement)


def _migrate_v2(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE tool_calls ADD COLUMN permission TEXT NOT NULL DEFAULT 'READ'")
    conn.execute("ALTER TABLE runtime_tasks ADD COLUMN budget_model_calls INTEGER NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE runtime_tasks ADD COLUMN consumed_model_calls INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE TABLE runtime_approvals (id TEXT PRIMARY KEY, call_id TEXT NOT NULL UNIQUE REFERENCES tool_calls(id), args_hash TEXT NOT NULL, scope_json TEXT NOT NULL, status TEXT NOT NULL, actor_id TEXT, expires_at TEXT NOT NULL, revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE runtime_outbox (id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES runtime_tasks(id), run_id TEXT NOT NULL REFERENCES agent_runs(id), kind TEXT NOT NULL, payload_json TEXT NOT NULL, status TEXT NOT NULL, receipt_json TEXT, attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")


def _migrate_v3(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE agent_runs ADD COLUMN trigger_kind TEXT NOT NULL DEFAULT 'user'")
    conn.execute("ALTER TABLE agent_runs ADD COLUMN trigger_id TEXT NOT NULL DEFAULT ''")


class RuntimeStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._audit_local = threading.local()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            installed = conn.execute("PRAGMA user_version").fetchone()[0]
            if installed > SCHEMA_VERSION:
                raise RuntimeError("agent_runtime database schema is newer than supported")
            if installed == 0:
                if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='runtime_tasks'").fetchone():
                    raise RuntimeError("unversioned or partially migrated agent_runtime database")
                conn.execute("BEGIN IMMEDIATE")
                try:
                    _schema(conn)
                    apply_sqlite_migrations(conn, component="agent_runtime", current_version=1)
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
            if installed < 2:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    apply_sqlite_migrations(conn, component="agent_runtime",
                                            current_version=2,
                                            migrations={2: _migrate_v2})
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
            if installed < SCHEMA_VERSION:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    apply_sqlite_migrations(conn, component="agent_runtime",
                                            current_version=SCHEMA_VERSION,
                                            migrations={3: _migrate_v3})
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        from backend.services.goals.service import GOAL_CONTROL_LOCK
        GOAL_CONTROL_LOCK.acquire()
        try:
            conn = self._connect()
        except BaseException:
            GOAL_CONTROL_LOCK.release()
            raise
        pending_audit: list[dict[str, Any]] = []
        self._audit_local.events = pending_audit
        committed = False
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
            committed = True
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
            del self._audit_local.events
            GOAL_CONTROL_LOCK.release()
            if committed:
                from backend.services.runtime_events import observe_execution_event
                for event in pending_audit:
                    try:
                        observe_execution_event(event)
                    except Exception:
                        logging.getLogger(__name__).exception("RuntimeEvent projection failed after commit")

    def _event(self, conn: sqlite3.Connection, run: sqlite3.Row, *, lifecycle: str,
               event_type: str = "state_transition", status: str = "running",
               payload: dict[str, Any] | None = None) -> dict[str, Any]:
        def persist(event: dict[str, Any]) -> None:
            validate_execution_event(event, require_persisted_identity=True)
            conn.execute("INSERT INTO execution_events VALUES (?,?,?,?,?)",
                         (run["id"], event["seq"], run["task_id"], _dump(event), _now()))
            conn.execute("UPDATE agent_runs SET seq_high_water=? WHERE id=?",
                         (event["seq"], run["id"]))
        emitter = ExecutionEventEmitter(
            request_id=run["request_id"], task_id=run["task_id"], run_id=run["id"],
            conversation_id=run["conversation_id"], turn_id=run["turn_id"],
            start_seq=run["seq_high_water"], persist=persist,
            audit=False,
            schema=EXECUTION_EVENT_V2_SCHEMA if run["trigger_kind"] in {"schedule", "goal"} else "texa.execution/v1",
            origin={"kind": run["trigger_kind"], "id": run["trigger_id"]} if run["trigger_kind"] in {"schedule", "goal"} else None,
        )
        event = emitter.emit(event_type, phase=lifecycle.split(".")[0], status=status,
                            summary=lifecycle, kind="tool" if lifecycle.startswith("tool.") else "system",
                            payload={"lifecycle": lifecycle, **(payload or {})})
        self._audit_local.events.append(event)
        return event

    def create(self, command: RunCommand) -> dict[str, Any]:
        if not all((command.request_key, command.request_id, command.task_id,
                    command.owner_token)):
            raise ValueError("persisted run identity must be nonempty")
        if command.trigger_kind in {"schedule", "goal"}:
            if not command.trigger_id or command.conversation_id or command.turn_id:
                raise ValueError("scheduled trigger requires an id and no invented conversation")
        elif not command.conversation_id or not command.turn_id:
            raise ValueError("conversation-bound run requires conversation and turn")
        if command.budget_calls < 0 or command.budget_calls > 6 or command.budget_model_calls < 0 or command.budget_model_calls > 8:
            raise ValueError("runtime budget exceeds bounded limit")
        if len(command.goal) > 4000 or len(command.required_outputs) > 20 or len(_dump(command.required_outputs)) > 16000:
            raise ValueError("task contract exceeds P0 size budget")
        with self._write() as conn:
            old = conn.execute("SELECT * FROM agent_runs WHERE request_key=?", (command.request_key,)).fetchone()
            if old:
                if old["task_id"] != command.task_id or old["request_id"] != command.request_id:
                    raise RuntimeConflict("request key belongs to another command")
                snapshot = self._snapshot(conn, old["id"])
                if (snapshot["task"]["goal"] != command.goal or snapshot["task"]["required_outputs"] != command.required_outputs or
                    snapshot["budget_calls"] != command.budget_calls or snapshot["budget_model_calls"] != command.budget_model_calls or
                    (old["conversation_id"], old["turn_id"], old["trigger_kind"], old["trigger_id"]) !=
                    (command.conversation_id, command.turn_id, command.trigger_kind, command.trigger_id)):
                    raise RuntimeConflict("request key reused with a changed command")
                return snapshot
            existing = conn.execute("SELECT id FROM runtime_tasks WHERE id=?", (command.task_id,)).fetchone()
            if existing:
                raise RuntimeConflict("task already exists; use resume")
            now = _now()
            run_id = f"arun_{uuid.uuid4().hex}"
            task = {"schema_version": "learning-task/v1", "id": command.task_id,
                    "task_type": "agent_runtime", "goal": command.goal, "status": "running",
                    "conversation_id": command.conversation_id, "turn_id": command.turn_id,
                    "required_inputs": [], "required_outputs": command.required_outputs,
                    "artifacts": {"active_run_id": run_id}, "checkpoints": [],
                    "verification": {}, "created_at": now, "updated_at": now}
            conn.execute("INSERT INTO runtime_tasks (id,snapshot_json,status,active_run_id,revision,budget_calls,consumed_calls,created_at,updated_at,budget_model_calls) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (command.task_id, _dump(task), "running", run_id, 1,
                          command.budget_calls, 0, now, now, command.budget_model_calls))
            checkpoint = {"steps": []}
            if command.trigger_kind in {"goal", "schedule"} and command.task_id.startswith("rtask_"):
                from backend.services.goals.store import GoalStore
                from backend.services.goals.service import goal_contract
                goal = GoalStore(self.db_path.parent / "goals.db").get(command.trigger_id)
                if not goal or goal["status"] != "active":
                    raise RuntimeConflict("goal is not active")
                checkpoint["goal_contract"] = goal_contract(goal)
            conn.execute("INSERT INTO agent_runs (id,task_id,resume_of_run_id,root_run_id,request_key,request_id,conversation_id,turn_id,status,owner_token,revision,seq_high_water,checkpoint_json,output_json,error_code,created_at,updated_at,ended_at,trigger_kind,trigger_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (run_id, command.task_id, None, run_id, command.request_key,
                          command.request_id, command.conversation_id, command.turn_id,
                          "running", command.owner_token, 1, 0, _dump(checkpoint),
                          None, None, now, now, None, command.trigger_kind, command.trigger_id))
            run = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
            self._event(conn, run, lifecycle="run.created", status="started",
                        payload={"task_status": "running"})
            return self._snapshot(conn, run_id)

    def _owned(self, conn: sqlite3.Connection, run_id: str, owner: str, *, check_goal: bool = True) -> sqlite3.Row:
        run = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
        if not run or run["status"] != "running" or run["owner_token"] != owner:
            raise RuntimeConflict("run is no longer owned or active")
        task = conn.execute("SELECT * FROM runtime_tasks WHERE id=?", (run["task_id"],)).fetchone()
        if task["active_run_id"] != run_id:
            raise RuntimeConflict("run is fenced by another active run")
        if check_goal:
            self._validate_goal_run(run)
        return run

    def _validate_goal_run(self, run):
        checkpoint = json.loads(run["checkpoint_json"])
        if run["trigger_kind"] not in {"goal", "schedule"} or not run["task_id"].startswith("rtask_"):
            return
        from backend.services.goals.store import GoalStore
        from backend.services.goals.service import goal_contract
        goal = GoalStore(self.db_path.parent / "goals.db").get(run["trigger_id"])
        if not goal or goal["status"] != "active" or checkpoint.get("goal_contract", checkpoint.get("answer_state", {}).get("_goal_contract")) != goal_contract(goal):
            raise RuntimeConflict("goal is inactive or its execution contract changed")

    def _snapshot(self, conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
        run = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
        if not run:
            raise KeyError(run_id)
        task = conn.execute("SELECT * FROM runtime_tasks WHERE id=?", (run["task_id"],)).fetchone()
        calls = conn.execute("SELECT * FROM tool_calls WHERE task_id=? ORDER BY created_at,rowid", (run["task_id"],)).fetchall()
        return {"task": json.loads(task["snapshot_json"]), "task_revision": task["revision"],
                "execution_events": [json.loads(row[0]) for row in conn.execute("SELECT event_json FROM execution_events WHERE run_id=? ORDER BY seq LIMIT 500", (run_id,))],
                "approvals": [dict(row) for row in conn.execute("SELECT a.* FROM runtime_approvals a JOIN tool_calls c ON c.id=a.call_id WHERE c.task_id=?", (run["task_id"],))],
                "budget_calls": task["budget_calls"], "consumed_calls": task["consumed_calls"],
                "budget_model_calls": task["budget_model_calls"], "consumed_model_calls": task["consumed_model_calls"],
                "run": {**dict(run), "checkpoint": json.loads(run["checkpoint_json"]),
                        "output": json.loads(run["output_json"]) if run["output_json"] else None},
                "tool_calls": [{**dict(c), "args": json.loads(c["args_json"]),
                                "result": json.loads(c["result_json"]) if c["result_json"] else None}
                               for c in calls]}

    def snapshot(self, run_id: str) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            conn.execute("BEGIN")
            return self._snapshot(conn, run_id)

    def task_snapshot(self, task_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            conn.execute("BEGIN")
            row = conn.execute("SELECT id FROM agent_runs WHERE task_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1", (task_id,)).fetchone()
            return self._snapshot(conn, row[0]) if row else None

    def goal_tasks(self, goal_id: str):
        with closing(self._connect()) as conn:
            return [row[0] for row in conn.execute("SELECT DISTINCT task_id FROM agent_runs WHERE trigger_kind IN ('goal','schedule') AND trigger_id=?", (goal_id,))]

    def configure_chat(self, run_id: str, owner: str, *, state: dict, candidates: tuple[dict, ...],
                       request_question: str, book_name: str, subject: str, delivery: str = "chat") -> dict:
        config = {"answer_state": state, "candidates": candidates, "delivery": delivery}
        if len(_dump(config)) > 64000:
            raise ValueError("chat context exceeds checkpoint budget")
        with self._write() as conn:
            run = self._owned(conn, run_id, owner)
            checkpoint = json.loads(run["checkpoint_json"])
            checkpoint.update(config)
            task = conn.execute("SELECT snapshot_json FROM runtime_tasks WHERE id=?", (run["task_id"],)).fetchone()
            snapshot = json.loads(task[0])
            snapshot["task_type"] = "qa"
            snapshot["answer_mode"] = state.get("answer_mode", "")
            snapshot["artifacts"].update({"request_question": request_question, "book_name": book_name, "subject": subject,
                "context_versions": state.get("context_versions") or {}})
            conn.execute("UPDATE agent_runs SET checkpoint_json=? WHERE id=?", (_dump(checkpoint), run_id))
            conn.execute("UPDATE runtime_tasks SET snapshot_json=? WHERE id=?", (_dump(snapshot), run["task_id"]))
            return self._snapshot(conn, run_id)

    def stream_snapshot(self, run_id: str, *, after_seq: int = 0):
        with closing(self._connect()) as conn:
            conn.execute("BEGIN")
            snapshot = self._snapshot(conn, run_id)
            events = [json.loads(row[0]) for row in conn.execute(
                "SELECT event_json FROM execution_events WHERE run_id=? AND seq>? ORDER BY seq LIMIT 100",
                (run_id, after_seq))]
            return snapshot, events

    def events(self, run_id: str, *, after_seq: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        if after_seq < 0 or limit < 1 or limit > 500:
            raise ValueError("event page limit out of range")
        with closing(self._connect()) as conn:
            return [json.loads(row[0]) for row in conn.execute(
                "SELECT event_json FROM execution_events WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",
                (run_id, after_seq, limit))]

    def mark_resume_launched(self, run_id: str, owner: str):
        with self._write() as conn:
            run = self._owned(conn, run_id, owner)
            checkpoint = json.loads(run["checkpoint_json"])
            checkpoint["resume_launched"] = True
            conn.execute("UPDATE agent_runs SET checkpoint_json=? WHERE id=?", (_dump(checkpoint), run_id))

    def start_model_step(self, run_id: str, owner: str) -> dict[str, Any]:
        with self._write() as conn:
            run = self._owned(conn, run_id, owner)
            task = conn.execute("SELECT * FROM runtime_tasks WHERE id=?", (run["task_id"],)).fetchone()
            if task["consumed_model_calls"] >= task["budget_model_calls"]:
                raise RuntimeConflict("task model budget exhausted")
            conn.execute("UPDATE runtime_tasks SET consumed_model_calls=consumed_model_calls+1,revision=revision+1,updated_at=? WHERE id=?",
                         (_now(), run["task_id"]))
            self._event(conn, run, lifecycle="model.started", status="started")
            return self._snapshot(conn, run_id)

    def complete_model_step(self, run_id: str, owner: str, *, action_kind: str,
                            transcript: list[dict]) -> dict[str, Any]:
        if len(transcript) > 24 or len(_dump(transcript)) > 64000:
            raise ValueError("model transcript exceeds bounded checkpoint")
        with self._write() as conn:
            run = self._owned(conn, run_id, owner)
            checkpoint = json.loads(run["checkpoint_json"])
            checkpoint["transcript"] = transcript
            checkpoint["last_action_kind"] = action_kind
            conn.execute("UPDATE agent_runs SET checkpoint_json=?,revision=revision+1,updated_at=? WHERE id=?",
                         (_dump(checkpoint), _now(), run_id))
            self._event(conn, run, lifecycle="model.completed", status="completed")
            return self._snapshot(conn, run_id)

    def request_tool(self, run_id: str, owner: str, *, tool_id: str,
                     version: str, schema_hash: str, args: dict[str, Any],
                     args_hash: str, operation_key: str,
                     permission: str = "READ") -> dict[str, Any]:
        if not operation_key or len(operation_key) > 160 or len(_dump(args)) > 16000:
            raise ValueError("tool request exceeds P0 size budget")
        if permission not in {"READ", "LOCAL_WRITE"}:
            raise ValueError("unsupported runtime permission")
        with self._write() as conn:
            run = self._owned(conn, run_id, owner)
            task = conn.execute("SELECT * FROM runtime_tasks WHERE id=?", (run["task_id"],)).fetchone()
            prior = conn.execute("SELECT * FROM tool_calls WHERE task_id=? AND operation_key=?",
                                 (run["task_id"], operation_key)).fetchone()
            if prior:
                if prior["args_hash"] != args_hash or prior["tool_id"] != tool_id:
                    raise RuntimeConflict("operation key reused with different arguments")
                return self._snapshot(conn, run_id)
            if task["consumed_calls"] >= task["budget_calls"]:
                raise RuntimeConflict("task tool budget exhausted")
            call_id = f"call_{uuid.uuid4().hex}"
            now = _now()
            conn.execute("INSERT INTO tool_calls (id,task_id,requested_run_id,executed_run_id,step_index,tool_id,tool_version,schema_hash,args_json,args_hash,operation_key,status,attempt_count,result_json,receipt_json,error_code,created_at,updated_at,permission) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (call_id, run["task_id"], run_id, None, task["consumed_calls"] + 1,
                          tool_id, version, schema_hash, _dump(args), args_hash,
                          operation_key, "requested", 0, None, None, None, now, now, permission))
            conn.execute("UPDATE runtime_tasks SET consumed_calls=consumed_calls+1,revision=revision+1,updated_at=? WHERE id=? AND revision=?",
                         (now, run["task_id"], task["revision"]))
            checkpoint = json.loads(run["checkpoint_json"])
            checkpoint["pending_call_id"] = call_id
            conn.execute("UPDATE agent_runs SET checkpoint_json=?,revision=revision+1,updated_at=? WHERE id=?",
                         (_dump(checkpoint), now, run_id))
            self._event(conn, run, lifecycle="tool.requested", payload={"tool_call_id": call_id,
                        "tool_id": tool_id, "tool_version": version})
            return self._snapshot(conn, run_id)

    def start_tool(self, run_id: str, owner: str, call_id: str) -> dict[str, Any]:
        with self._write() as conn:
            run = self._owned(conn, run_id, owner)
            call = conn.execute("SELECT * FROM tool_calls WHERE id=? AND requested_run_id=?",
                                (call_id, run_id)).fetchone()
            if not call or call["status"] != "requested":
                raise RuntimeConflict("tool call is not ready")
            if call["permission"] != "READ":
                raise RuntimeConflict("write call requires a separate confirmed action")
            conn.execute("UPDATE tool_calls SET status='running',executed_run_id=?,attempt_count=attempt_count+1,updated_at=? WHERE id=?",
                         (run_id, _now(), call_id))
            self._event(conn, run, lifecycle="tool.started", status="started",
                        payload={"tool_call_id": call_id})
            return self._snapshot(conn, run_id)

    def finish_tool(self, run_id: str, owner: str, call_id: str,
                    result: dict[str, Any], *, error_code: str = "") -> dict[str, Any]:
        if len(_dump(result)) > 128000:
            raise ValueError("tool result exceeds P0 size budget")
        with self._write() as conn:
            run = self._owned(conn, run_id, owner)
            call = conn.execute("SELECT * FROM tool_calls WHERE id=? AND executed_run_id=?",
                                (call_id, run_id)).fetchone()
            if not call or call["status"] != "running":
                raise RuntimeConflict("tool call is not running")
            now = _now()
            status = ("unknown" if error_code and call["permission"] == "LOCAL_WRITE"
                      else "failed" if error_code else "succeeded")
            receipt = result.get("domain_receipt") if isinstance(result, dict) else None
            conn.execute("UPDATE tool_calls SET status=?,result_json=?,receipt_json=?,error_code=?,updated_at=? WHERE id=?",
                         (status, _dump(result), _dump(receipt) if receipt is not None else None,
                          error_code or None, now, call_id))
            checkpoint = json.loads(run["checkpoint_json"])
            checkpoint.pop("pending_call_id", None)
            checkpoint["steps"].append({"call_id": call_id, "status": status})
            transcript = list(checkpoint.get("transcript") or [])
            transcript.append({"role": "tool", "tool_id": call["tool_id"],
                               "status": status, "data": str(result.get("data") or "")[:3000]})
            checkpoint["transcript"] = transcript[-24:]
            conn.execute("UPDATE agent_runs SET checkpoint_json=?,revision=revision+1,updated_at=? WHERE id=?",
                         (_dump(checkpoint), now, run_id))
            self._event(conn, run, lifecycle="tool.failed" if error_code else "tool.completed",
                        event_type="tool_result", status="failed" if error_code else "completed",
                        payload={"tool_call_id": call_id, "tool_id": call["tool_id"],
                                 "tool_status": status})
            return self._snapshot(conn, run_id)

    def await_approval(self, run_id: str, owner: str, call_id: str, *,
                       scope: dict[str, Any], expires_at: str) -> dict[str, Any]:
        if len(_dump(scope)) > 8000:
            raise ValueError("approval scope exceeds size budget")
        with self._write() as conn:
            run = self._owned(conn, run_id, owner)
            call = conn.execute("SELECT * FROM tool_calls WHERE id=? AND requested_run_id=?",
                                (call_id, run_id)).fetchone()
            if not call or call["permission"] != "LOCAL_WRITE" or call["status"] != "requested":
                raise RuntimeConflict("write call is not ready for approval")
            task = conn.execute("SELECT * FROM runtime_tasks WHERE id=?", (run["task_id"],)).fetchone()
            now = _now()
            conn.execute("INSERT INTO runtime_approvals VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (f"approval_{call_id}", call_id, call["args_hash"], _dump(scope),
                          "pending", None, expires_at, 1, now, now))
            conn.execute("UPDATE tool_calls SET status='awaiting_approval',updated_at=? WHERE id=?", (now, call_id))
            self._event(conn, run, lifecycle="tool.awaiting_approval",
                        payload={"tool_call_id": call_id})
            run = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
            snapshot = json.loads(task["snapshot_json"])
            snapshot["status"] = "waiting_for_confirmation"
            snapshot["artifacts"]["active_run_id"] = ""
            snapshot["updated_at"] = now
            conn.execute("UPDATE runtime_tasks SET snapshot_json=?,status='waiting_for_confirmation',active_run_id=NULL,revision=revision+1,updated_at=? WHERE id=?",
                         (_dump(snapshot), now, run["task_id"]))
            conn.execute("UPDATE agent_runs SET status='paused',revision=revision+1,ended_at=?,updated_at=? WHERE id=?",
                         (now, now, run_id))
            self._event(conn, run, lifecycle="run.paused", payload={
                "task_status_before": "running", "task_status_after": "waiting_for_confirmation",
                "pause_reason": "approval", "tool_call_id": call_id})
            return self._snapshot(conn, run_id)

    def confirm_approval(self, call_id: str, *, actor_id: str, args_hash: str,
                         scope: dict[str, Any]) -> dict[str, Any]:
        if not actor_id:
            raise ValueError("confirming actor is required")
        with self._write() as conn:
            row = conn.execute("SELECT * FROM runtime_approvals WHERE call_id=?", (call_id,)).fetchone()
            if not row:
                raise KeyError(call_id)
            call = conn.execute("SELECT requested_run_id FROM tool_calls WHERE id=?", (call_id,)).fetchone()
            run = conn.execute("SELECT * FROM agent_runs WHERE id=?", (call[0],)).fetchone()
            self._validate_goal_run(run)
            if row["args_hash"] != args_hash or row["scope_json"] != _dump(scope):
                raise RuntimeConflict("approval arguments or scope changed")
            if row["status"] == "confirmed":
                return dict(row)
            if row["status"] != "pending" or row["expires_at"] <= _now():
                raise RuntimeConflict("approval is rejected or expired")
            conn.execute("UPDATE runtime_approvals SET status='confirmed',actor_id=?,revision=revision+1,updated_at=? WHERE call_id=?",
                         (actor_id, _now(), call_id))
            return dict(conn.execute("SELECT * FROM runtime_approvals WHERE call_id=?", (call_id,)).fetchone())

    def reject_approval(self, call_id: str, *, actor_id: str,
                        interrupt_task: bool = False) -> dict[str, Any]:
        if not actor_id.strip():
            raise ValueError("rejecting actor is required")
        with self._write() as conn:
            row = conn.execute("SELECT * FROM runtime_approvals WHERE call_id=?", (call_id,)).fetchone()
            if not row:
                raise KeyError(call_id)
            if row["status"] in {"pending", "confirmed"}:
                call = conn.execute("SELECT * FROM tool_calls WHERE id=?", (call_id,)).fetchone()
                task = conn.execute("SELECT * FROM runtime_tasks WHERE id=?", (call["task_id"],)).fetchone()
                if call["status"] != "awaiting_approval" or call["executed_run_id"] or call["attempt_count"]:
                    raise RuntimeConflict("admitted approval cannot be rejected")
                if task["status"] not in {"waiting_for_confirmation", "running", "interrupted"}:
                    raise RuntimeConflict("approval task has already advanced")
                if task["status"] == "running" and not interrupt_task:
                    raise RuntimeConflict("running task must be stopped before cancellation")
                stopped_status = "interrupted" if interrupt_task else "cancelled"
                conn.execute("UPDATE runtime_approvals SET status='rejected',actor_id=?,revision=revision+1,updated_at=? WHERE call_id=?",
                             (actor_id, _now(), call_id))
                conn.execute("UPDATE tool_calls SET status='denied',updated_at=? WHERE id=?",
                             (_now(), call_id))
                snapshot = json.loads(task["snapshot_json"])
                snapshot["status"] = stopped_status
                snapshot["artifacts"]["active_run_id"] = ""
                snapshot["updated_at"] = _now()
                conn.execute("UPDATE runtime_tasks SET snapshot_json=?,status=?,active_run_id=NULL,revision=revision+1,updated_at=? WHERE id=?",
                             (_dump(snapshot), stopped_status, _now(), call["task_id"]))
                run = conn.execute("SELECT * FROM agent_runs WHERE id=?", (task["active_run_id"] or call["requested_run_id"],)).fetchone()
                conn.execute("UPDATE agent_runs SET status=?,revision=revision+1,ended_at=?,updated_at=? WHERE id=?", ("paused" if interrupt_task else "cancelled", _now(), _now(), run["id"]))
                # A paused run's event stream is closed. The approval/task rows
                # carry cancellation facts; only an active run gets a stop event.
                if run["status"] == "running":
                    self._event(conn, run, lifecycle="approval.rejected", status="cancelled",
                        payload={"task_status_before": task["status"], "task_status_after": stopped_status})
            return dict(conn.execute("SELECT * FROM runtime_approvals WHERE call_id=?", (call_id,)).fetchone())

    def start_approved_tool(self, run_id: str, owner: str, call_id: str) -> dict[str, Any]:
        with self._write() as conn:
            run = self._owned(conn, run_id, owner)
            call = conn.execute("SELECT * FROM tool_calls WHERE id=? AND task_id=?",
                                (call_id, run["task_id"])).fetchone()
            approval = conn.execute("SELECT * FROM runtime_approvals WHERE call_id=?", (call_id,)).fetchone()
            if not call or not approval or approval["status"] != "confirmed" or call["status"] != "awaiting_approval":
                raise RuntimeConflict("write call lacks a valid confirmed approval")
            conn.execute("UPDATE tool_calls SET status='running',executed_run_id=?,attempt_count=attempt_count+1,updated_at=? WHERE id=?",
                         (run_id, _now(), call_id))
            self._event(conn, run, lifecycle="tool.started", status="started",
                        payload={"tool_call_id": call_id})
            return self._snapshot(conn, run_id)

    def reconcile_approved_tool(self, task_id: str, call_id: str,
                                receipt: dict[str, Any], *, args_hash: str,
                                scope: dict[str, Any]) -> dict[str, Any]:
        """Record an admitted domain fact without resuming or admitting work."""
        if not receipt:
            raise ValueError("domain receipt is required for reconciliation")
        with self._write() as conn:
            call = conn.execute("SELECT * FROM tool_calls WHERE id=? AND task_id=?",
                                (call_id, task_id)).fetchone()
            approval = conn.execute("SELECT * FROM runtime_approvals WHERE call_id=?", (call_id,)).fetchone()
            if not call or call["status"] not in {"unknown", "succeeded"} or call["permission"] != "LOCAL_WRITE" or not approval or approval["status"] != "confirmed" or not call["executed_run_id"] or not call["attempt_count"]:
                raise RuntimeConflict("write call is not reconcilable")
            if call["args_hash"] != args_hash or approval["args_hash"] != args_hash or approval["scope_json"] != _dump(scope):
                raise RuntimeConflict("receipt arguments or scope changed")
            latest = conn.execute("SELECT id FROM agent_runs WHERE task_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1", (task_id,)).fetchone()
            if call["status"] == "succeeded":
                if json.loads(call["receipt_json"]) != receipt:
                    raise RuntimeConflict("domain receipt changed")
                return self._snapshot(conn, latest[0])
            run_id = call["executed_run_id"]
            run = conn.execute("SELECT * FROM agent_runs WHERE id=? AND task_id=?", (run_id, task_id)).fetchone()
            if not run or run["status"] == "running":
                raise RuntimeConflict("write execution has not been fenced")
            result = {"success": True, "domain_receipt": receipt, "reconciled": True}
            conn.execute("UPDATE tool_calls SET status='succeeded',result_json=?,receipt_json=?,error_code=NULL,updated_at=? WHERE id=?",
                         (_dump(result), _dump(receipt), _now(), call_id))
            checkpoint = json.loads(run["checkpoint_json"])
            checkpoint.setdefault("steps", []).append({"call_id": call_id, "status": "succeeded", "reconciled": True})
            conn.execute("UPDATE agent_runs SET checkpoint_json=?,revision=revision+1,updated_at=? WHERE id=?",
                         (_dump(checkpoint), _now(), run_id))
            # Receipt accounting updates the durable call, not the closed run's
            # lifecycle stream or final output. Its execution owner stays fenced.
            return self._snapshot(conn, latest[0])

    def close(self, run_id: str, owner: str, *, outcome: str,
              answer: str = "", error_code: str = "",
              verification: dict[str, Any] | None = None, sources: list[dict] | None = None) -> dict[str, Any]:
        if len(answer) > 64000:
            raise ValueError("answer exceeds P0 size budget")
        mapping = {"completed": ("completed", "final", "completed", "run.completed"),
                   "degraded": ("degraded", "final", "completed", "run.completed"),
                   "failed": ("failed", "error", "failed", "run.failed"),
                   "paused": ("interrupted", "state_transition", "running", "run.paused"),
                   "approval": ("waiting_for_confirmation", "state_transition", "running", "run.paused")}
        if outcome not in mapping:
            raise ValueError("invalid P0 outcome")
        task_status, event_type, event_status, lifecycle = mapping[outcome]
        with self._write() as conn:
            run = self._owned(conn, run_id, owner, check_goal=outcome != "paused")
            task = conn.execute("SELECT * FROM runtime_tasks WHERE id=?", (run["task_id"],)).fetchone()
            now = _now()
            snapshot = json.loads(task["snapshot_json"])
            if outcome in {"completed", "degraded"} and snapshot["required_outputs"] and not verification:
                raise RuntimeConflict("required outputs must be verified before publishing")
            if outcome == "completed" and verification and verification.get("status") != "passed":
                raise RuntimeConflict("unverified answer cannot be marked completed")
            snapshot["status"] = task_status
            snapshot["updated_at"] = now
            snapshot["artifacts"]["active_run_id"] = ""
            if outcome == "paused":
                conn.execute("UPDATE tool_calls SET status=CASE WHEN permission='LOCAL_WRITE' THEN 'unknown' ELSE 'failed' END,error_code='interrupted',updated_at=? WHERE executed_run_id=? AND status='running'", (now, run_id))
            if verification:
                snapshot["verification"] = verification
            if outcome in {"completed", "degraded"}:
                snapshot["artifacts"]["final_answer"] = answer
                snapshot["artifacts"]["final_output"] = answer
                if sources:
                    if len(sources) > 20 or len(_dump(sources)) > 64000:
                        raise ValueError("source projection exceeds budget")
                    snapshot["artifacts"]["evidence_sources"] = sources
            conn.execute("UPDATE runtime_tasks SET snapshot_json=?,status=?,active_run_id=NULL,revision=revision+1,updated_at=? WHERE id=? AND revision=?",
                         (_dump(snapshot), task_status, now, run["task_id"], task["revision"]))
            conn.execute("UPDATE agent_runs SET status=?,output_json=?,error_code=?,revision=revision+1,updated_at=?,ended_at=? WHERE id=?",
                         ("completed" if outcome == "degraded" else "paused" if outcome == "approval" else outcome,
                          _dump({"answer": answer, "verification": verification}) if outcome in {"completed", "degraded"} else None,
                          error_code or None, now, now, run_id))
            payload = {"task_status_before": "running", "task_status_after": task_status} if outcome in {"paused", "approval"} else {"task_status": task_status}
            if outcome in {"paused", "approval"}:
                payload["pause_reason"] = error_code or ("approval" if outcome == "approval" else "interrupted")
            if outcome in {"completed", "degraded"} and json.loads(run["checkpoint_json"]).get("delivery") == "chat":
                # Reserve a transport-only output sequence before the durable final.
                # Answer text lives in the outcome, not a persisted delta payload.
                conn.execute("UPDATE agent_runs SET seq_high_water=seq_high_water+1 WHERE id=?", (run_id,))
                run = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
            if error_code:
                payload["error_code"] = error_code
            self._event(conn, run, lifecycle=lifecycle, event_type=event_type,
                        status=event_status, payload=payload)
            if outcome in {"completed", "degraded"} and run["conversation_id"]:
                conn.execute("INSERT OR IGNORE INTO runtime_outbox (id,task_id,run_id,kind,payload_json,status,created_at,updated_at) VALUES (?,?,?,?,?,'pending',?,?)",
                    (f"message_{run['task_id']}", run["task_id"], run_id, "assistant_message",
                     _dump({"conversation_id": run["conversation_id"], "turn_id": run["turn_id"],
                            "request_id": run["request_id"], "answer": answer,
                            "delivery_status": "complete" if outcome == "completed" else "degraded",
                            "message_id": f"msg_{run['task_id']}"}), now, now))
                checkpoint = json.loads(run["checkpoint_json"])
                if checkpoint.get("delivery") == "chat":
                    state = checkpoint["answer_state"]
                    conn.execute("INSERT OR IGNORE INTO runtime_outbox (id,task_id,run_id,kind,payload_json,status,created_at,updated_at) VALUES (?,?,?,?,?,'pending',?,?)",
                        (f"learning_{run['task_id']}", run["task_id"], run_id, "chat_learning_event",
                         _dump({"book_name": state.get("book_name", ""), "subject": state.get("subject", ""),
                                "conversation_id": run["conversation_id"], "request_id": run["request_id"]}), now, now))
            return self._snapshot(conn, run_id)

    def pending_outbox(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM runtime_outbox WHERE status='pending' ORDER BY attempts,updated_at,id LIMIT ?",
                                (min(max(limit, 1), 100),)).fetchall()
            return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def fail_outbox(self, outbox_id: str, error: Exception) -> None:
        logging.getLogger(__name__).error("Outbox %s projection failed: %s", outbox_id, type(error).__name__)
        with self._write() as conn:
            conn.execute("UPDATE runtime_outbox SET attempts=attempts+1,receipt_json=?,updated_at=? WHERE id=? AND status='pending'",
                         (_dump({"error_code": type(error).__name__}), _now(), outbox_id))

    def complete_outbox(self, outbox_id: str, receipt: dict[str, Any]) -> None:
        with self._write() as conn:
            row = conn.execute("SELECT * FROM runtime_outbox WHERE id=?", (outbox_id,)).fetchone()
            if not row:
                raise KeyError(outbox_id)
            if row["status"] == "completed":
                return
            conn.execute("UPDATE runtime_outbox SET status='completed',receipt_json=?,attempts=attempts+1,updated_at=? WHERE id=? AND status='pending'",
                         (_dump(receipt), _now(), outbox_id))

    def resume(self, task_id: str, *, expected_revision: int, request_key: str,
               request_id: str, owner_token: str, turn_id: str) -> dict[str, Any]:
        if not all(isinstance(value, str) and value.strip() for value in
                   (task_id, request_key, request_id, owner_token)):
            raise ValueError("resume requires stable task, request and owner identities")
        with self._write() as conn:
            old = conn.execute("SELECT * FROM agent_runs WHERE request_key=?", (request_key,)).fetchone()
            if old:
                if (old["task_id"], old["request_id"], old["turn_id"], old["owner_token"]) != (task_id, request_id, turn_id, owner_token):
                    raise RuntimeConflict("resume request identity changed")
                self._validate_goal_run(old)
                return self._snapshot(conn, old["id"])
            task = conn.execute("SELECT * FROM runtime_tasks WHERE id=?", (task_id,)).fetchone()
            if not task or task["revision"] != expected_revision or task["status"] not in {"interrupted", "waiting_for_confirmation"}:
                raise RuntimeConflict("task cannot resume at this revision")
            if task["status"] == "waiting_for_confirmation" and not conn.execute(
                "SELECT 1 FROM runtime_approvals a JOIN tool_calls c ON a.call_id=c.id WHERE c.task_id=? AND a.status='confirmed' LIMIT 1",
                (task_id,)).fetchone():
                raise RuntimeConflict("approval has not been confirmed")
            prior = conn.execute("SELECT * FROM agent_runs WHERE task_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1", (task_id,)).fetchone()
            self._validate_goal_run(prior)
            if prior["trigger_kind"] in {"schedule", "goal"} and turn_id:
                raise ValueError("scheduled resume cannot invent a conversation turn")
            if prior["trigger_kind"] not in {"schedule", "goal"} and not turn_id.strip():
                raise ValueError("conversation resume requires a turn identity")
            now = _now()
            checkpoint = json.loads(prior["checkpoint_json"])
            checkpoint.pop("resume_launched", None)
            run_id = f"arun_{uuid.uuid4().hex}"
            snapshot = json.loads(task["snapshot_json"])
            snapshot["status"] = "running"
            snapshot["turn_id"] = turn_id
            snapshot["artifacts"]["active_run_id"] = run_id
            snapshot["updated_at"] = now
            conn.execute("UPDATE runtime_tasks SET snapshot_json=?,status='running',active_run_id=?,revision=revision+1,updated_at=? WHERE id=? AND revision=?",
                         (_dump(snapshot), run_id, now, task_id, expected_revision))
            conn.execute("INSERT INTO agent_runs (id,task_id,resume_of_run_id,root_run_id,request_key,request_id,conversation_id,turn_id,status,owner_token,revision,seq_high_water,checkpoint_json,output_json,error_code,created_at,updated_at,ended_at,trigger_kind,trigger_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (run_id, task_id, prior["id"], prior["root_run_id"], request_key,
                          request_id, prior["conversation_id"], turn_id, "running",
                          owner_token, 1, 0, _dump(checkpoint), None, None,
                          now, now, None, prior["trigger_kind"], prior["trigger_id"]))
            run = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
            self._event(conn, run, lifecycle="run.resumed", status="started",
                        payload={"task_status": "running", "resume_of_run_id": prior["id"]})
            return self._snapshot(conn, run_id)

    def recover_unfinished(self) -> int:
        with self._write() as conn:
            run_ids = [row[0] for row in conn.execute("SELECT id FROM agent_runs WHERE status IN ('created','running')")]
            for run_id in run_ids:
                run = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
                self.close_for_recovery(conn, run)
            return len(run_ids)

    def close_for_recovery(self, conn: sqlite3.Connection, run: sqlite3.Row) -> None:
        task = conn.execute("SELECT * FROM runtime_tasks WHERE id=?", (run["task_id"],)).fetchone()
        snapshot = json.loads(task["snapshot_json"])
        snapshot["status"] = "interrupted"
        snapshot["artifacts"]["active_run_id"] = ""
        conn.execute("UPDATE runtime_tasks SET snapshot_json=?,status='interrupted',active_run_id=NULL,revision=revision+1,updated_at=? WHERE id=?",
                     (_dump(snapshot), _now(), run["task_id"]))
        conn.execute("UPDATE agent_runs SET status='paused',error_code='recovery_required',revision=revision+1,ended_at=?,updated_at=? WHERE id=?",
                     (_now(), _now(), run["id"]))
        conn.execute("UPDATE tool_calls SET status=CASE WHEN permission='LOCAL_WRITE' THEN 'unknown' ELSE 'failed' END,error_code='process_restarted',updated_at=? WHERE executed_run_id=? AND status='running'",
                     (_now(), run["id"]))
        self._event(conn, run, lifecycle="run.paused", payload={
            "task_status_before": "running", "task_status_after": "interrupted",
            "pause_reason": "recovery_required"})
