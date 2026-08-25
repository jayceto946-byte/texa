"""Durable, bounded task state for learning-question workflows.

The conversation log records what was said.  A LearningTask records what still
has to happen before a turn may be treated as complete.  The store is purposely
small and JSON-backed: it is a harness checkpoint, not another source of truth
for books, mistakes, exercises, or learner mastery.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config import PROGRESS_PATH
from utils.json_io import atomic_write_json


LEARNING_TASK_SCHEMA_VERSION = "learning-task/v1"
TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}
RESUMABLE_TASK_STATUSES = {"interrupted"}
_TASK_LOCK = threading.RLock()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _bounded_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _bounded_json(value: Any, *, depth: int = 0) -> Any:
    if depth >= 5:
        return _bounded_text(value, 500)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:12000]
    if isinstance(value, list):
        return [_bounded_json(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, dict):
        return {
            _bounded_text(key, 100): _bounded_json(item, depth=depth + 1)
            for key, item in list(value.items())[:100]
        }
    return _bounded_text(value, 500)


@dataclass
class RequiredInput:
    type: str
    name: str
    reason: str
    affects: list[str] = field(default_factory=list)
    blocking: bool = True
    status: str = "missing"  # missing | provided | waived

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RequiredInput":
        raw_affects = value.get("affects") or []
        if isinstance(raw_affects, str):
            raw_affects = [raw_affects]
        return cls(
            type=_bounded_text(value.get("type") or "other", 80),
            name=_bounded_text(value.get("name") or "补充材料", 200),
            reason=_bounded_text(value.get("reason"), 500),
            affects=[_bounded_text(item, 100) for item in raw_affects[:20] if _bounded_text(item, 100)],
            blocking=bool(value.get("blocking", True)),
            status=_bounded_text(value.get("status") or "missing", 20),
        )


@dataclass
class LearningTask:
    id: str
    task_type: str
    goal: str
    status: str = "running"
    conversation_id: str = ""
    turn_id: str = ""
    answer_mode: str = ""
    required_inputs: list[dict[str, Any]] = field(default_factory=list)
    required_outputs: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    schema_version: str = LEARNING_TASK_SCHEMA_VERSION

    def to_dict(self, *, public: bool = False) -> dict[str, Any]:
        value = asdict(self)
        if public:
            artifacts = value.get("artifacts") or {}
            value["artifacts"] = {
                "visual_ir": artifacts.get("visual_ir") or {},
                "supplement_count": len(artifacts.get("supplemental_visual_irs") or []),
                "completed_derivation": _bounded_text(artifacts.get("completed_derivation"), 4000),
                "pending_actions": list(artifacts.get("pending_actions") or [])[:10],
                "resume_available": self.status in RESUMABLE_TASK_STATUSES,
                "resume_stage": _bounded_text(artifacts.get("resume_stage"), 80),
                "partial_output": _bounded_text(artifacts.get("partial_output"), 4000),
            }
        return value


class LearningTaskStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or PROGRESS_PATH) / "learning_tasks"

    def _path(self, task_id: str) -> Path:
        safe_id = _bounded_text(task_id, 80)
        if not safe_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in safe_id):
            raise ValueError("invalid learning task id")
        return self.root / f"{safe_id}.json"

    def create(
        self,
        *,
        task_type: str,
        goal: str,
        conversation_id: str = "",
        turn_id: str = "",
        answer_mode: str = "",
        required_inputs: list[dict[str, Any]] | None = None,
        required_outputs: list[dict[str, Any]] | None = None,
        artifacts: dict[str, Any] | None = None,
        status: str = "running",
    ) -> LearningTask:
        task = LearningTask(
            id=f"task_{uuid.uuid4().hex}",
            task_type=_bounded_text(task_type, 80),
            goal=_bounded_text(goal, 2000),
            status=_bounded_text(status, 40),
            conversation_id=_bounded_text(conversation_id, 100),
            turn_id=_bounded_text(turn_id, 100),
            answer_mode=_bounded_text(answer_mode, 80),
            required_inputs=[asdict(RequiredInput.from_dict(item)) for item in (required_inputs or [])[:40]],
            required_outputs=[_bounded_json(item) for item in (required_outputs or [])[:40] if isinstance(item, dict)],
            artifacts=_bounded_json(artifacts or {}),
        )
        task.checkpoints.append({"stage": "created", "status": status, "at": task.created_at})
        self.save(task)
        return task

    def get(self, task_id: str) -> LearningTask | None:
        path = self._path(task_id)
        if not path.is_file():
            return None
        import json

        with _TASK_LOCK:
            value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema_version") != LEARNING_TASK_SCHEMA_VERSION:
            return None
        fields = LearningTask.__dataclass_fields__
        return LearningTask(**{key: value[key] for key in fields if key in value})

    def save(self, task: LearningTask) -> LearningTask:
        task.updated_at = _now()
        path = self._path(task.id)
        with _TASK_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(path, task.to_dict())
        return task

    def run_is_active(self, task_id: str, run_id: str) -> bool:
        current = self.get(task_id)
        return bool(
            current
            and current.status == "running"
            and str(current.artifacts.get("active_run_id") or "") == str(run_id or "")
        )

    def save_for_run(self, task: LearningTask, run_id: str) -> LearningTask:
        """Save stream-owned state only while that exact run still owns the task."""
        with _TASK_LOCK:
            current = self.get(task.id)
            if not current or current.status != "running":
                return current or task
            if str(current.artifacts.get("active_run_id") or "") != str(run_id or ""):
                return current
            return self.save(task)

    def checkpoint_for_run(
        self,
        task: LearningTask,
        run_id: str,
        stage: str,
        *,
        status: str | None = None,
        detail: str = "",
    ) -> LearningTask:
        """Checkpoint without allowing a stale stream to overwrite stop/resume state."""
        with _TASK_LOCK:
            current = self.get(task.id)
            if not current or current.status != "running":
                return current or task
            if str(current.artifacts.get("active_run_id") or "") != str(run_id or ""):
                return current
            return self.checkpoint(task, stage, status=status, detail=detail)

    def checkpoint(self, task: LearningTask, stage: str, *, status: str | None = None, detail: str = "") -> LearningTask:
        if status:
            task.status = _bounded_text(status, 40)
        task.checkpoints = [
            *task.checkpoints,
            {"stage": _bounded_text(stage, 80), "status": task.status, "detail": _bounded_text(detail, 500), "at": _now()},
        ][-30:]
        return self.save(task)


def blocking_required_inputs(required_inputs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        item for item in (required_inputs or [])
        if isinstance(item, dict)
        and bool(item.get("blocking"))
        and str(item.get("status") or "missing") == "missing"
    ]


def mark_required_inputs(task: LearningTask, status: str) -> None:
    for item in task.required_inputs:
        if item.get("blocking") and str(item.get("status") or "missing") == "missing":
            item["status"] = status


def interrupt_learning_task(
    store: LearningTaskStore,
    task: LearningTask,
    *,
    stage: str,
    partial_output: str = "",
    expected_run_id: str = "",
) -> LearningTask:
    """Persist the smallest safe checkpoint needed to resume the same turn."""
    with _TASK_LOCK:
        if expected_run_id:
            current = store.get(task.id)
            if current is None:
                return task
            if str(current.artifacts.get("active_run_id") or "") != str(expected_run_id):
                return current
            task = current
        if task.status in TERMINAL_TASK_STATUSES:
            return task
        if task.status == "interrupted":
            if stage:
                task.artifacts["resume_stage"] = _bounded_text(stage, 80)
            if partial_output:
                task.artifacts["partial_output"] = _bounded_text(partial_output, 12000)
            return store.save(task)
        task.artifacts["resume_stage"] = _bounded_text(stage or "unknown", 80)
        task.artifacts["partial_output"] = _bounded_text(partial_output, 12000)
        return store.checkpoint(task, "interrupted", status="interrupted", detail=stage)


def resume_learning_task(
    store: LearningTaskStore,
    task: LearningTask,
    *,
    run_id: str = "",
) -> LearningTask:
    """Move an interrupted task back to running without discarding its artifacts."""
    if task.status not in RESUMABLE_TASK_STATUSES:
        raise ValueError(f"learning task is not resumable: {task.status}")
    if run_id:
        task.artifacts["active_run_id"] = _bounded_text(run_id, 80)
    return store.checkpoint(
        task,
        "resumed",
        status="running",
        detail=str(task.artifacts.get("resume_stage") or "unknown"),
    )


_DEFAULT_STORE: LearningTaskStore | None = None


def get_learning_task_store() -> LearningTaskStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = LearningTaskStore()
    return _DEFAULT_STORE
