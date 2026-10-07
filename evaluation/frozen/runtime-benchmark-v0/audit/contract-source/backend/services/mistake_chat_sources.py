"""Stable chat capture identity and reuse over the existing mistake lifecycle."""
from __future__ import annotations

import hashlib
import json
from memory.mistake_lifecycle import MistakeLifecycleStore


class MistakeChatSourceService:
    def __init__(self, lifecycle: MistakeLifecycleStore):
        self.lifecycle = lifecycle

    @staticmethod
    def reference(conversation_id: str, message_id: str, turn_id: str = "") -> dict:
        if not conversation_id.strip() or not message_id.strip():
            raise ValueError("persisted conversation_id and message_id are required")
        return {"type": "chat", "conversation_id": conversation_id, "message_id": message_id, "turn_id": turn_id}

    def lookup(self, conversation_id: str, message_ids: list[str], turn_ids: list[str] | None = None) -> list[dict]:
        refs = [self.reference(conversation_id, mid) for mid in message_ids]
        resolved = []
        if turn_ids:
            from backend.conversation_memory import load_turn_messages
            # The context loader deliberately caps reads at four turns. A UI
            # page may contain many fresh questions whose IDs are not yet in
            # the client projection; resolve every requested turn explicitly.
            messages = []
            requested = list(dict.fromkeys(turn_ids))
            for start in range(0, len(requested), 4):
                messages.extend(load_turn_messages(conversation_id, requested[start:start + 4], max_turns=4))
            user_by_turn = {str(m.get("turn_id") or ""): m for m in messages if m.get("role") == "user"}
            for turn_id in turn_ids:
                message = user_by_turn.get(turn_id)
                if message and message.get("id"):
                    refs.append(self.reference(conversation_id, str(message["id"]), turn_id))
                    resolved.append((turn_id, str(message["id"])))
                else:
                    resolved.append((turn_id, ""))
        states = self.lifecycle.lookup_chat_sources(refs)
        by_id = {state["message_id"]: state for state in states}
        return [*states[:len(message_ids)], *[{"turn_id": tid, **by_id[mid]} if mid else {"turn_id": tid, "message_id": "", "status": "pending"} for tid, mid in resolved]]

    def capture(self, conversation_id: str, message_id: str, turn_id: str, data: dict) -> dict:
        ref = self.reference(conversation_id, message_id, turn_id)
        # The actual per-book database filename is the storage scope. Its root
        # may move during backup/restore, so an absolute path is not an identity.
        namespace = [self.lifecycle.store.db_path.name, conversation_id, message_id]
        key = "chat:" + hashlib.sha256(json.dumps(namespace, ensure_ascii=False).encode()).hexdigest()
        return self.lifecycle.get_or_create_chat_draft({**data, "source_ref": ref}, key)
