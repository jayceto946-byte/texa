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
        "execution_events": snapshot["execution_events"]}
    types = {"save_mistake": "add_mistake", "create_exercise_set": "create_practice_session",
             "record_result": "record_practice_result", "update_mistake": "update_mistake"}
    approvals = {item["call_id"]: item for item in snapshot.get("approvals", [])}
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    actions = []
    for call in snapshot["tool_calls"]:
        approval = approvals.get(call["id"])
        if not approval or call["tool_id"] not in types:
            continue
        if call["status"] == "succeeded":
            status = "executed"
        elif call["status"] == "unknown":
            status = "unknown"
        elif approval["status"] == "rejected":
            status = "rejected"
        elif approval["status"] == "pending" and approval["expires_at"] <= now:
            status = "expired"
        elif approval["status"] in {"pending", "confirmed"} and call["status"] == "awaiting_approval" and task["status"] in {"waiting_for_confirmation", "interrupted"}:
            status = "pending"
        elif call["status"] == "running":
            status = "executing"
        else:
            status = "failed"
        allowed = ["confirm", "reject"] if status == "pending" else ["reject"] if status == "expired" else []
        actions.append({"action_id": call["id"], "type": types[call["tool_id"]], "payload": call["args"],
                        "status": status, "allowed_actions": allowed})
    task["artifacts"]["pending_actions"] = actions
    task["active_run_id"] = snapshot["run"]["id"]
    task["revision"] = snapshot["task_revision"]
    status = task["status"]
    task.update(terminal=status in {"completed", "degraded", "failed", "cancelled"},
                interruptible=status == "running", resumable=status == "interrupted" and not any(item["status"] == "unknown" for item in actions),
                input_action_required=status == "waiting_for_input",
                confirmation_required=any(item["status"] == "pending" for item in actions))
    return task
