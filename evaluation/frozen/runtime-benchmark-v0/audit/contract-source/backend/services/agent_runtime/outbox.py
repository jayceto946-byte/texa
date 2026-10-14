"""Idempotent projection of committed Runtime outcomes to conversation storage."""
from __future__ import annotations

from collections.abc import Callable

from backend.services.agent_runtime.store import RuntimeStore


class RuntimeOutboxProjector:
    def __init__(self, store: RuntimeStore, append_message: Callable):
        self.store = store
        self.append_message = append_message

    def drain_once(self, *, limit: int = 50) -> int:
        projected = 0
        for item in self.store.pending_outbox(limit=limit):
            if item["kind"] != "assistant_message":
                continue
            try:
                payload = item["payload"]
                message = self.append_message(
                    payload["conversation_id"], "assistant", payload["answer"],
                    turn_id=payload["turn_id"], message_id=payload["message_id"],
                    request_id=payload["request_id"],
                    delivery_status=payload["delivery_status"],
                )
                self.store.complete_outbox(item["id"], {"message_id": message["id"]})
                projected += 1
            except Exception as exc:
                self.store.fail_outbox(item["id"], exc)
        return projected
