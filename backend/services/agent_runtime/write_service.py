"""Approval-bound Runtime writes through existing domain receipts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from backend.services.agent_runtime.contracts import RuntimeConflict, RuntimeDenied
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.pending_actions import PendingActionStore
from backend.tools.registry import ToolContext, ToolRegistry


class RuntimeWriteService:
    def __init__(self, runtime: RuntimeStore, registry: ToolRegistry,
                 pending: PendingActionStore):
        self.runtime = runtime
        self.registry = registry
        self.pending = pending

    def propose(self, run_id: str, owner: str, *, tool_id: str,
                args: dict, operation_key: str, context: ToolContext) -> dict:
        spec = self.registry.runtime_tool(tool_id)
        meta = spec.runtime_metadata()
        if meta["permission"] != "LOCAL_WRITE" or meta["source"] != "builtin" or tool_id not in {"save_mistake", "create_exercise_set", "record_result", "update_mistake"}:
            raise RuntimeDenied("write tool is unavailable")
        parsed = spec.runtime_input.model_validate(args).model_dump()
        if parsed["book_name"] != context.book_name:
            raise RuntimeDenied("write scope does not match selected book")
        if parsed.get("subject") and parsed["subject"] != context.subject:
            raise RuntimeDenied("write subject does not match selected scope")
        args_hash = hashlib.sha256(json.dumps(parsed, sort_keys=True).encode()).hexdigest()
        requested = self.runtime.request_tool(run_id, owner, tool_id=tool_id,
            version=spec.version, schema_hash=meta["schema_hash"], args=parsed,
            args_hash=args_hash, operation_key=operation_key, permission="LOCAL_WRITE")
        call = next(item for item in requested["tool_calls"] if item["operation_key"] == operation_key)
        if call["status"] != "requested":
            raise RuntimeConflict("write proposal already advanced")
        proposal = spec.handler(context, parsed).pending_action
        if not proposal:
            raise RuntimeDenied("write tool did not return a proposal")
        self.pending.create(proposal, action_id=call["id"], context={
            "book_name": context.book_name, "subject": context.subject,
            "conversation_id": context.conversation_id,
            "learning_task_id": call["task_id"],
        })
        scope = {"book_name": context.book_name, "subject": context.subject}
        expires = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        return self.runtime.await_approval(run_id, owner, call["id"], scope=scope, expires_at=expires)

    def confirm(self, task_id: str, call_id: str, *, actor_id: str,
                args_hash: str, scope: dict, expected_revision: int,
                resume_request_key: str, request_id: str, owner_token: str,
                turn_id: str) -> dict:
        snapshot = self.runtime.task_snapshot(task_id)
        call = next((item for item in snapshot["tool_calls"] if item["id"] == call_id), None) if snapshot else None
        action = self.pending.get(call_id)
        if call is None or action is None or action["payload"] != call["args"]:
            raise RuntimeConflict("approval proposal differs from the frozen task call")
        if call["status"] == "succeeded":
            return snapshot
        spec = self.registry.runtime_tool(call["tool_id"])
        metadata = spec.runtime_metadata()
        if (metadata["schema_hash"], metadata["version"]) != (call["schema_hash"], call["tool_version"]):
            raise RuntimeConflict("approved tool contract changed")
        self.runtime.confirm_approval(call_id, actor_id=actor_id,
                                      args_hash=args_hash, scope=scope)
        resumed = self.runtime.resume(task_id, expected_revision=expected_revision,
            request_key=resume_request_key, request_id=request_id,
            owner_token=owner_token, turn_id=turn_id)
        run_id = resumed["run"]["id"]
        # A repeated confirmation observes the same run and receipt, never a new write.
        call = next(item for item in resumed["tool_calls"] if item["id"] == call_id)
        if call["status"] == "succeeded":
            return resumed
        if call["status"] == "unknown":
            receipt = self.pending.domain_receipt(call_id)
            if receipt is None:
                raise RuntimeConflict("write result is unknown and has no domain receipt")
            return self.runtime.reconcile_approved_tool(run_id, owner_token, call_id, receipt)
        if call["status"] == "awaiting_approval":
            self.runtime.start_approved_tool(run_id, owner_token, call_id)
        try:
            receipt = self.pending.confirm(call_id)["result"]
        except Exception:
            self.runtime.finish_tool(run_id, owner_token, call_id,
                {"success": False, "message": "write outcome requires reconciliation"},
                error_code="write_unknown")
            return self.runtime.close(run_id, owner_token, outcome="paused",
                                      error_code="recovery_required")
        return self.runtime.finish_tool(run_id, owner_token, call_id,
            {"success": True, "domain_receipt": receipt})
