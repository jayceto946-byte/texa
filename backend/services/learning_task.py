"""Durable, bounded task state for learning-question workflows.

The conversation log records what was said.  A LearningTask records what still
has to happen before a turn may be treated as complete.  The store is purposely
small and JSON-backed: it is a harness checkpoint, not another source of truth
for books, mistakes, exercises, or learner mastery.
"""
from __future__ import annotations

import threading
import copy
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config import PROGRESS_PATH
from utils.json_io import atomic_write_json


LEARNING_TASK_SCHEMA_VERSION = "learning-task/v1"
LEARNING_TASK_STATE_CONTRACT = {
    "running": {
        "phase": "active",
        "transitions": frozenset({
            "interrupted", "waiting_for_input", "waiting_for_confirmation",
            "completed", "degraded", "failed",
        }),
        "terminal": False,
        "interruptible": True,
        "resumable": False,
        "delivered": False,
        "input_action_required": False,
        "confirmation_required": False,
    },
    "interrupted": {
        "phase": "paused",
        "transitions": frozenset({"running", "cancelled"}),
        "terminal": False,
        "interruptible": False,
        "resumable": True,
        "delivered": False,
        "input_action_required": False,
        "confirmation_required": False,
    },
    "waiting_for_input": {
        "phase": "paused",
        "transitions": frozenset({"running", "cancelled", "failed"}),
        "terminal": False,
        "interruptible": False,
        "resumable": False,
        "delivered": False,
        "input_action_required": True,
        "confirmation_required": False,
    },
    "waiting_for_confirmation": {
        "phase": "paused",
        "transitions": frozenset({"completed", "degraded", "failed", "cancelled"}),
        "terminal": False,
        "interruptible": False,
        "resumable": False,
        "delivered": False,
        "input_action_required": False,
        "confirmation_required": True,
    },
    "completed": {
        "phase": "terminal",
        "transitions": frozenset({"completed"}),
        "terminal": True,
        "interruptible": False,
        "resumable": False,
        "delivered": True,
        "input_action_required": False,
        "confirmation_required": False,
    },
    "degraded": {
        "phase": "terminal",
        "transitions": frozenset({"degraded"}),
        "terminal": True,
        "interruptible": False,
        "resumable": False,
        "delivered": True,
        "input_action_required": False,
        "confirmation_required": False,
    },
    "failed": {
        "phase": "terminal",
        "transitions": frozenset({"failed"}),
        "terminal": True,
        "interruptible": False,
        "resumable": False,
        "delivered": False,
        "input_action_required": False,
        "confirmation_required": False,
    },
    "cancelled": {
        "phase": "terminal",
        "transitions": frozenset({"cancelled"}),
        "terminal": True,
        "interruptible": False,
        "resumable": False,
        "delivered": False,
        "input_action_required": False,
        "confirmation_required": False,
    },
}
LEARNING_TASK_STATUSES = frozenset(LEARNING_TASK_STATE_CONTRACT)
LEARNING_TASK_TRANSITIONS = {
    status: contract["transitions"]
    for status, contract in LEARNING_TASK_STATE_CONTRACT.items()
}
ACTIVE_TASK_STATUSES = frozenset(
    status for status, contract in LEARNING_TASK_STATE_CONTRACT.items()
    if contract["phase"] == "active"
)
PAUSED_TASK_STATUSES = frozenset(
    status for status, contract in LEARNING_TASK_STATE_CONTRACT.items()
    if contract["phase"] == "paused"
)
TERMINAL_TASK_STATUSES = frozenset(
    status for status, contract in LEARNING_TASK_STATE_CONTRACT.items()
    if contract["terminal"]
)
INTERRUPTIBLE_TASK_STATUSES = frozenset(
    status for status, contract in LEARNING_TASK_STATE_CONTRACT.items()
    if contract["interruptible"]
)
RESUMABLE_TASK_STATUSES = frozenset(
    status for status, contract in LEARNING_TASK_STATE_CONTRACT.items()
    if contract["resumable"]
)
DELIVERED_TASK_STATUSES = frozenset(
    status for status, contract in LEARNING_TASK_STATE_CONTRACT.items()
    if contract["delivered"]
)
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


def validate_learning_task_status(status: str) -> str:
    normalized = _bounded_text(status, 40)
    if normalized not in LEARNING_TASK_STATUSES:
        raise ValueError(f"invalid learning task status: {normalized or '<empty>'}")
    return normalized


def validate_learning_task_transition(current_status: str, target_status: str) -> str:
    current = validate_learning_task_status(current_status)
    target = validate_learning_task_status(target_status)
    if target not in LEARNING_TASK_TRANSITIONS[current]:
        raise ValueError(f"invalid learning task transition: {current} -> {target}")
    return target


def is_terminal_task_status(status: str) -> bool:
    contract = LEARNING_TASK_STATE_CONTRACT.get(status)
    return bool(contract and contract["terminal"])


def is_interruptible_task_status(status: str) -> bool:
    contract = LEARNING_TASK_STATE_CONTRACT.get(status)
    return bool(contract and contract["interruptible"])


def is_resumable_task_status(status: str) -> bool:
    contract = LEARNING_TASK_STATE_CONTRACT.get(status)
    return bool(contract and contract["resumable"])


def is_delivered_task_status(status: str) -> bool:
    contract = LEARNING_TASK_STATE_CONTRACT.get(status)
    return bool(contract and contract["delivered"])


def task_requires_input_action(status: str) -> bool:
    contract = LEARNING_TASK_STATE_CONTRACT.get(status)
    return bool(contract and contract["input_action_required"])


def task_requires_confirmation(status: str) -> bool:
    contract = LEARNING_TASK_STATE_CONTRACT.get(status)
    return bool(contract and contract["confirmation_required"])


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
            value.update({
                "active_run_id": str(self.artifacts.get("active_run_id") or ""),
                "terminal": is_terminal_task_status(self.status),
                "interruptible": is_interruptible_task_status(self.status),
                "resumable": is_resumable_task_status(self.status),
                "input_action_required": task_requires_input_action(self.status),
                "confirmation_required": task_requires_confirmation(self.status),
            })
            artifacts = value.get("artifacts") or {}
            value["artifacts"] = {
                "visual_ir": artifacts.get("visual_ir") or {},
                "supplement_count": len(artifacts.get("supplemental_visual_irs") or []),
                "completed_derivation": _bounded_text(artifacts.get("completed_derivation"), 4000),
                "pending_actions": list(artifacts.get("pending_actions") or [])[:10],
                "resume_available": is_resumable_task_status(self.status),
                "resume_stage": _bounded_text(artifacts.get("resume_stage"), 80),
                "partial_output": _bounded_text(artifacts.get("partial_output"), 4000),
                "execution_events": list(artifacts.get("execution_events") or [])[-40:],
                "effects": [
                    {"id": item["id"], "kind": item["kind"],
                     "status": "completed" if item.get("receipt") is not None else "pending",
                     "result": item.get("receipt"), "error": item.get("error", "")}
                    for item in (artifacts.get("execution_outcome") or {}).get("effects", [])
                ],
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
        normalized_status = validate_learning_task_status(status)
        task = LearningTask(
            id=f"task_{uuid.uuid4().hex}",
            task_type=_bounded_text(task_type, 80),
            goal=_bounded_text(goal, 2000),
            status=normalized_status,
            conversation_id=_bounded_text(conversation_id, 100),
            turn_id=_bounded_text(turn_id, 100),
            answer_mode=_bounded_text(answer_mode, 80),
            required_inputs=[asdict(RequiredInput.from_dict(item)) for item in (required_inputs or [])[:40]],
            required_outputs=[_bounded_json(item) for item in (required_outputs or [])[:40] if isinstance(item, dict)],
            artifacts=_bounded_json(artifacts or {}),
        )
        task.checkpoints.append({"stage": "created", "status": normalized_status, "at": task.created_at})
        self._persist(task)
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
        task = LearningTask(**{key: value[key] for key in fields if key in value})
        validate_learning_task_status(task.status)
        return task

    def _persist(self, task: LearningTask) -> LearningTask:
        validate_learning_task_status(task.status)
        with _TASK_LOCK:
            task.updated_at = _now()
            path = self._path(task.id)
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(path, task.to_dict())
        return task

    def save(self, task: LearningTask) -> LearningTask:
        """Persist non-status mutations; status changes must use checkpoint()."""
        with _TASK_LOCK:
            current = self.get(task.id)
            if current is not None and current.status != task.status:
                raise ValueError("learning task status changes must use checkpoint()")
            if current is not None and current.artifacts.get("active_run_id") != task.artifacts.get("active_run_id"):
                raise ValueError("run ownership changes require claim_run or resume")
            if current is not None and current.artifacts.get("execution_outcome"):
                # Terminal projections may still hold an older task snapshot.
                # Only the dedicated outcome methods may change frozen effects/receipts.
                task.artifacts["execution_outcome"] = copy.deepcopy(current.artifacts["execution_outcome"])
            return self._persist(task)

    def claim_run(self, task: LearningTask, run_id: str) -> LearningTask:
        with _TASK_LOCK:
            current = self.get(task.id)
            if not current or current.status != "running" or not run_id:
                raise ValueError("task cannot claim a run")
            if current.artifacts.get("active_run_id") not in (None, "", run_id):
                raise ValueError("task is already owned by another run")
            current.artifacts["active_run_id"] = run_id
            return self._persist(current)

    def prepare_checkpoint_for_run(self, task: LearningTask, run_id: str, stage: str,
                                   *, status: str, detail: str = "") -> LearningTask:
        """Prepare an outcome in memory; commit it together with its terminal event."""
        with _TASK_LOCK:
            current = self.get(task.id)
            if not current or not self.run_is_active(task.id, run_id):
                raise ValueError("stale run cannot prepare an outcome")
            task.status = validate_learning_task_transition(current.status, status)
            task.checkpoints = [*current.checkpoints, {
                "stage": stage, "status": status, "detail": detail[:500], "at": _now(),
            }][-30:]
            task.artifacts["execution_events"] = copy.deepcopy(current.artifacts.get("execution_events") or [])
            return task

    def commit_outcome(self, task: LearningTask, run_id: str, event: dict,
                       *, messages: list[dict] | None = None, effects: list[dict] | None = None) -> LearningTask:
        from backend.services.execution_events import validate_execution_event
        with _TASK_LOCK:
            current = self.get(task.id)
            if current and (current.artifacts.get("execution_outcome") or {}).get("event") == event:
                return current
            if not current or not self.run_is_active(task.id, run_id):
                raise ValueError("stale run cannot commit an outcome")
            if (task.conversation_id, task.turn_id, task.artifacts.get("active_run_id")) != (
                current.conversation_id, current.turn_id, run_id,
            ):
                raise ValueError("outcome task identity does not match its run")
            validate_execution_event(event, expected_task_id=task.id, expected_run_id=run_id,
                                     expected_conversation_id=current.conversation_id,
                                     expected_turn_id=current.turn_id, require_persisted_identity=True)
            boundary_status = event["payload"].get("task_status")
            if event["type"] == "state_transition" and task.status == "waiting_for_input":
                boundary_status = event["payload"].get("task_status_after")
            elif event["type"] not in {"final", "error"}:
                raise ValueError("outcome requires a terminal event or input gate")
            if boundary_status != task.status:
                raise ValueError("outcome requires a matching task boundary")
            if task.status not in {"completed", "degraded", "failed", "waiting_for_input", "waiting_for_confirmation"}:
                raise ValueError("outcome cannot leave the task running")
            validate_learning_task_transition(current.status, task.status)
            events = list(current.artifacts.get("execution_events") or [])
            owned = [e for e in events if e.get("run_id") == run_id]
            if any(e.get("type") in {"final", "error"} for e in owned):
                raise ValueError("run already has a terminal event")
            if event["seq"] <= max((e["seq"] for e in owned), default=0):
                raise ValueError("outcome sequence must increase")
            from backend.services.execution_events import validate_execution_event_sequence
            validate_execution_event_sequence([*owned, event])
            outcome = copy.deepcopy(task)
            outcome.artifacts["execution_events"] = [*events, copy.deepcopy(event)][-40:]
            outcome.artifacts["execution_outcome"] = {
                "event": copy.deepcopy(event), "messages": copy.deepcopy(messages or []),
                "projected": not bool(messages),
            }
            if effects:
                from backend.services.execution_effects import bind_effects
                outcome.artifacts["execution_outcome"]["effects"] = bind_effects(current, task, event, effects)
            return self._persist(outcome)

    def outcome_effects(self, task_id: str, run_id: str = "") -> list[dict]:
        """Only explicit effects on a committed, delivered outcome are eligible."""
        with _TASK_LOCK:
            task = self.get(task_id)
            if not task or task.status not in DELIVERED_TASK_STATUSES:
                return []
            outcome = task.artifacts.get("execution_outcome") or {}
            event = outcome.get("event") or {}
            if (event.get("type") != "final" or event.get("run_id") != task.artifacts.get("active_run_id")
                    or (run_id and run_id != event.get("run_id"))):
                return []
            effects = outcome.get("effects") or []
            if not effects:
                return []
            from backend.services.execution_effects import bind_effects, EFFECT_SCHEMA
            from backend.services.execution_events import validate_execution_event
            validate_execution_event(event, expected_task_id=task.id, expected_run_id=event["run_id"],
                                     expected_conversation_id=task.conversation_id, expected_turn_id=task.turn_id,
                                     require_persisted_identity=True)
            expected = bind_effects(task, task, event, [
                {"kind": item["kind"], "payload": item["payload"]} for item in effects
            ])
            for item, bound in zip(effects, expected):
                if (item.get("schema") != EFFECT_SCHEMA or item.get("id") != bound["id"]
                        or item.get("run_id") != event["run_id"] or item["payload"] != bound["payload"]):
                    raise ValueError("invalid persisted effect authority")
            return copy.deepcopy(effects)

    def update_outcome_effect(self, task_id: str, run_id: str, effect_id: str, **changes) -> dict:
        """Merge only effect state; never overwrite answer or run authority."""
        if set(changes) - {"prepared", "receipt", "attempts", "retry_at", "error"}:
            raise ValueError("invalid effect state update")
        with _TASK_LOCK:
            effects = self.outcome_effects(task_id, run_id)
            if not any(item.get("id") == effect_id for item in effects):
                raise ValueError("effect is not authorized by the committed outcome")
            task = self.get(task_id)
            effect = next(item for item in task.artifacts["execution_outcome"]["effects"] if item["id"] == effect_id)
            if effect.get("receipt") is not None:
                return copy.deepcopy(effect)
            if effect.get("prepared") is not None:
                changes.pop("prepared", None)
            effect.update(copy.deepcopy(changes))
            task.artifacts["execution_outcome"]["effects_projected"] = False
            self._persist(task)
            return copy.deepcopy(effect)

    def project_effects(self, task_id: str) -> None:
        """Refresh the existing assistant message; no new answer or execution event."""
        from backend.conversation_memory import update_learning_task_projection
        with _TASK_LOCK:
            task = self.get(task_id)
            outcome = task.artifacts.get("execution_outcome") if task else None
            if not outcome or not outcome.get("effects") or outcome.get("effects_projected"):
                return
            self.outcome_effects(task_id)  # Validate the persisted authority before projecting it.
            projected = self.project_outcome(task_id)
            task = self.get(task_id)
            for message in projected:
                if message.get("role") == "assistant":
                    if not update_learning_task_projection(task.conversation_id, task.id, task.to_dict(public=True),
                                                           message_id=message["id"]):
                        raise ValueError("effect projection target is unavailable")
            task.artifacts["execution_outcome"]["effects_projected"] = True
            self._persist(task)

    def project_outcome(self, task_id: str, *, run_id: str = "", append=None) -> list[dict]:
        if append is None:
            from backend.conversation_memory import append_message
            append = append_message
        with _TASK_LOCK:
            task = self.get(task_id)
            outcome = task.artifacts.get("execution_outcome") if task else None
            if not outcome:
                return []
            if run_id and outcome["event"]["run_id"] != run_id:
                return []
            results = []
            for message in outcome.get("messages") or []:
                values = copy.deepcopy(message)
                if values.get("role") == "assistant":
                    values["learning_task"] = task.to_dict(public=True)
                results.append(append(task.conversation_id, values.pop("role"), values.pop("text"),
                                      turn_id=task.turn_id, **values))
            if not outcome.get("projected"):
                outcome["projected"] = True
                self._persist(task)
            return results

    def recover_unfinished(self) -> None:
        for path in self.root.glob("*.json"):
            try:
                task = self.get(path.stem)
                if task and task.status == "running":
                    interrupt_learning_task(self, task, stage="process_restarted",
                                            expected_run_id=str(task.artifacts.get("active_run_id") or ""))
                if task and (task.artifacts.get("execution_outcome") or {}).get("projected") is False:
                    self.project_outcome(task.id)
            except Exception:
                logging.getLogger(__name__).exception("task recovery failed: %s", path.stem)

    def run_is_active(self, task_id: str, run_id: str) -> bool:
        normalized_run_id = str(run_id or "")
        if not normalized_run_id:
            return False
        current = self.get(task_id)
        return bool(
            current
            and is_interruptible_task_status(current.status)
            and str(current.artifacts.get("active_run_id") or "") == normalized_run_id
        )

    def save_for_run(self, task: LearningTask, run_id: str) -> LearningTask:
        """Save stream-owned state only while that exact run still owns the task."""
        with _TASK_LOCK:
            current = self.get(task.id)
            if not current or not is_interruptible_task_status(current.status):
                return current or task
            normalized_run_id = str(run_id or "")
            if not normalized_run_id:
                return current
            if str(current.artifacts.get("active_run_id") or "") != normalized_run_id:
                return current
            if task.status != current.status:
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
            if not current or not is_interruptible_task_status(current.status):
                return current or task
            normalized_run_id = str(run_id or "")
            if not normalized_run_id:
                return current
            if str(current.artifacts.get("active_run_id") or "") != normalized_run_id:
                return current
            return self.checkpoint(task, stage, status=status, detail=detail)

    def append_execution_event_for_run(
        self,
        task_id: str,
        run_id: str,
        event: dict[str, Any],
        *,
        limit: int = 40,
    ) -> LearningTask | None:
        """Persist bounded orchestration milestones, never token deltas/heartbeats."""
        from backend.services.execution_events import (
            EXECUTION_EVENT_TERMINAL_TYPES,
            should_persist_execution_event,
            validate_execution_event,
        )

        with _TASK_LOCK:
            current = self.get(task_id)
            if current is None:
                return None
            normalized_run_id = str(run_id or "")
            if not normalized_run_id:
                return current
            if str(current.artifacts.get("active_run_id") or "") != normalized_run_id:
                return current
            persisted_milestone = should_persist_execution_event(event)
            validate_execution_event(
                event,
                expected_task_id=task_id,
                expected_run_id=normalized_run_id,
                expected_conversation_id=current.conversation_id,
                expected_turn_id=current.turn_id,
                require_persisted_identity=persisted_milestone,
            )
            event_type = str(event.get("type") or "")
            event_payload = event.get("payload") or {}
            event_task_status = str(event_payload.get("task_status") or "")
            terminal_matches_current = bool(
                event_type in EXECUTION_EVENT_TERMINAL_TYPES
                and event_task_status
                and event_task_status == current.status
            )
            transition_matches_current = bool(
                event_type == "state_transition"
                and str(event_payload.get("task_status_after") or "") == current.status
            )
            if event_type in EXECUTION_EVENT_TERMINAL_TYPES and not terminal_matches_current:
                return current
            if (
                event_type not in EXECUTION_EVENT_TERMINAL_TYPES
                and not is_interruptible_task_status(current.status)
                and not transition_matches_current
            ):
                return current
            if not persisted_milestone:
                return current
            existing_events = list(current.artifacts.get("execution_events") or [])
            current_run_events = [
                item for item in existing_events
                if isinstance(item, dict)
                and str(item.get("run_id") or "") == normalized_run_id
            ]
            previous_seq = max(
                (int(item.get("seq") or 0) for item in current_run_events),
                default=0,
            )
            if int(event["seq"]) <= previous_seq:
                raise ValueError("execution event seq must increase within a task run")
            if any(item.get("type") in EXECUTION_EVENT_TERMINAL_TYPES for item in current_run_events):
                raise ValueError("execution events cannot follow final or error")
            from backend.services.execution_events import validate_execution_event_sequence
            validate_execution_event_sequence([*current_run_events, event])
            compact = {
                key: event.get(key)
                for key in (
                    "schema", "request_id", "task_id", "run_id", "conversation_id", "turn_id",
                    "seq", "operation_id", "type", "phase", "status", "summary", "label",
                    "kind", "elapsed_ms", "duration_ms", "payload",
                )
                if event.get(key) is not None
            }
            current.artifacts["execution_events"] = [
                *(current.artifacts.get("execution_events") or []), compact,
            ][-max(1, min(int(limit), 80)):]
            return self.save(current)

    def checkpoint(self, task: LearningTask, stage: str, *, status: str | None = None, detail: str = "") -> LearningTask:
        with _TASK_LOCK:
            target_status = (
                validate_learning_task_transition(task.status, status)
                if status is not None
                else validate_learning_task_status(task.status)
            )
            current = self.get(task.id)
            if current is not None and (current.status != task.status or
                    current.artifacts.get("active_run_id") != task.artifacts.get("active_run_id")):
                return current
            if current is not None and current.artifacts.get("execution_outcome"):
                task.artifacts["execution_outcome"] = copy.deepcopy(current.artifacts["execution_outcome"])
            task.status = target_status
            task.checkpoints = [
                *task.checkpoints,
                {"stage": _bounded_text(stage, 80), "status": task.status, "detail": _bounded_text(detail, 500), "at": _now()},
            ][-30:]
            return self._persist(task)


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
        current = store.get(task.id)
        if current is None:
            return task
        if expected_run_id:
            if str(current.artifacts.get("active_run_id") or "") != str(expected_run_id):
                return current
        task = current
        if is_terminal_task_status(task.status):
            return task
        if task.status == "interrupted":
            if stage:
                task.artifacts["resume_stage"] = _bounded_text(stage, 80)
            if partial_output:
                task.artifacts["partial_output"] = _bounded_text(partial_output, 12000)
            return store.save(task)
        if not is_interruptible_task_status(task.status):
            raise ValueError(f"learning task is not interruptible: {task.status}")
        task.artifacts["resume_stage"] = _bounded_text(stage or "unknown", 80)
        task.artifacts["partial_output"] = _bounded_text(partial_output, 12000)
        return store.checkpoint(task, "interrupted", status="interrupted", detail=stage)


def resume_learning_task(
    store: LearningTaskStore,
    task: LearningTask,
    *,
    run_id: str = "",
    turn_id: str = "",
    run_artifacts: dict | None = None,
) -> LearningTask:
    """Move a resumable or input-gated task to a run-owned running state."""
    normalized_run_id = _bounded_text(run_id, 80)
    if not normalized_run_id:
        raise ValueError("run_id is required to resume learning task")
    with _TASK_LOCK:
        current = store.get(task.id)
        if current is None:
            raise ValueError("learning task no longer exists")
        active_run_id = str(current.artifacts.get("active_run_id") or "")
        if current.status == "running":
            if active_run_id == normalized_run_id:
                return current
            raise ValueError("learning task is already running under another run")
        if not (
            is_resumable_task_status(current.status)
            or task_requires_input_action(current.status)
        ):
            raise ValueError(f"learning task is not resumable: {current.status}")
        if (current.artifacts.get("execution_outcome") or {}).get("projected") is False:
            store.project_outcome(current.id)
            current = store.get(current.id)
        current.status = validate_learning_task_transition(current.status, "running")
        current.artifacts["active_run_id"] = normalized_run_id
        current.artifacts.pop("execution_outcome", None)
        if run_artifacts:
            current.artifacts.update(copy.deepcopy(run_artifacts))
        if turn_id:
            current.turn_id = turn_id
            mark_required_inputs(current, "provided")
        current.checkpoints = [*current.checkpoints, {
            "stage": "resumed", "status": "running", "at": _now(),
        }][-30:]
        return store._persist(current)


_DEFAULT_STORE: LearningTaskStore | None = None


def get_learning_task_store() -> LearningTaskStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = LearningTaskStore()
    return _DEFAULT_STORE
