"""Explicit backend ownership. Runtime IDs never fall through to legacy JSON."""
from pathlib import Path
from backend.services.agent_runtime.store import DEFAULT_RUNTIME_DB_PATH, RuntimeStore


def is_runtime_task(task_id: str) -> bool:
    return task_id.startswith("rtask_")


def runtime_store(*, create: bool = False) -> RuntimeStore | None:
    if not create and not Path(DEFAULT_RUNTIME_DB_PATH).exists():
        return None
    return RuntimeStore(DEFAULT_RUNTIME_DB_PATH)


def public_task(store: RuntimeStore, snapshot: dict) -> dict:
    task = dict(snapshot["task"])
    task["artifacts"] = {**task["artifacts"], "storage_backend": "sqlite-runtime",
        "active_run_id": snapshot["run"]["id"],
        "execution_events": store.events(snapshot["run"]["id"], limit=500)}
    types = {"save_mistake": "add_mistake", "create_exercise_set": "create_practice_session",
             "record_result": "record_practice_result", "update_mistake": "update_mistake"}
    approvals = {item["call_id"]: item for item in snapshot.get("approvals", [])}
    task["artifacts"]["pending_actions"] = [{"action_id": call["id"], "type": types[call["tool_id"]],
        "payload": call["args"], "status": "confirmed" if call["status"] == "succeeded" else
        "rejected" if approvals[call["id"]]["status"] == "rejected" else "pending"}
        for call in snapshot["tool_calls"] if call["id"] in approvals and call["tool_id"] in types]
    task["active_run_id"] = snapshot["run"]["id"]
    task["revision"] = snapshot["task_revision"]
    status = task["status"]
    task.update(terminal=status in {"completed", "degraded", "failed", "cancelled"},
                interruptible=status == "running", resumable=status == "interrupted",
                input_action_required=status == "waiting_for_input",
                confirmation_required=status == "waiting_for_confirmation" or any(call["permission"] == "LOCAL_WRITE" and call["status"] == "unknown" for call in snapshot["tool_calls"]))
    return task
