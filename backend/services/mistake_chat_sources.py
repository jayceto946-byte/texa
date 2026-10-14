"""Stable chat capture identity and reuse over the existing mistake lifecycle."""
from __future__ import annotations

import hashlib
import json
from memory.mistake_lifecycle import MistakeLifecycleStore


class MistakeChatSourceService:
    def __init__(self, lifecycle: MistakeLifecycleStore, *, message_reader=None, image_store=None, task_store=None):
        self.lifecycle = lifecycle
        self.message_reader = message_reader
        self.image_store = image_store
        self.task_store = task_store

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
        from backend.conversation_memory import get_message, load_turn_messages
        from backend.services.learning_task import get_learning_task_store
        from backend.services.visual_session_assets import visual_session_text
        reader = self.message_reader or get_message
        message = reader(conversation_id, message_id)
        if not message or message.get("role") != "user":
            raise ValueError("persisted user message not found")
        actual_turn = str(message.get("turn_id") or "")
        if turn_id and turn_id != actual_turn:
            raise ValueError("message turn does not match")
        ref = self.reference(conversation_id, message_id, actual_turn)
        messages = load_turn_messages(conversation_id, [actual_turn], max_turns=1) if actual_turn else []
        answer = next((m for m in messages if m.get("role") == "assistant" and m.get("delivery_status", "complete") == "complete"), {})
        task_id = str((message.get("learning_task") or answer.get("learning_task") or {}).get("id") or "")
        task = (self.task_store or get_learning_task_store()).get(task_id) if task_id else None
        if task and (task.conversation_id != conversation_id or task.turn_id != actual_turn):
            raise ValueError("visual task source does not match")
        assets = task.artifacts if task and task.task_type == "visual_qa" else {}
        inherited = {"question_text": str(message.get("content") or ""),
                     "correct_answer": str(answer.get("content") or ""),
                     "explanation": str(answer.get("content") or ""),
                     "subject": str(message.get("subject") or data.get("subject") or ""),
                     "source": "学习会话", "content_complete": False}
        if assets:
            inherited.update(question_text=visual_session_text(assets),
                             ocr_text=str((assets.get("visual_ir") or {}).get("problem_text") or ""),
                             visual_ir=assets.get("visual_ir") or {}, user_answer=assets.get("user_answer") or "")
            ref["task_id"] = task.id
        if not inherited["question_text"].strip():
            raise ValueError("persisted question is empty")
        prepare = None
        if assets.get("image_path"):
            def prepare(draft_id):
                import shutil
                from pathlib import Path
                image_store = self.image_store
                if image_store is None:
                    raise ValueError("image storage unavailable")
                root = image_store.image_root.resolve()
                folder = root / "drafts" / draft_id
                attachment = {"id": "att_" + task.id, "filename": "原始题目图片"}
                for field, source_value in (("original_path", assets.get("original_image_path") or assets["image_path"]),
                                            ("work_path", assets["image_path"])):
                    source = Path(source_value).resolve()
                    if not source.is_relative_to(root) or not source.is_file():
                        raise ValueError("source image not found")
                    folder.mkdir(parents=True, exist_ok=True)
                    target = folder / (field + source.suffix)
                    shutil.copyfile(source, target)
                    attachment[field] = str(target)
                return {"attachments": [attachment]}
        # The actual per-book database filename is the storage scope. Its root
        # may move during backup/restore, so an absolute path is not an identity.
        namespace = [self.lifecycle.store.db_path.name, conversation_id, message_id]
        key = "chat:" + hashlib.sha256(json.dumps(namespace, ensure_ascii=False).encode()).hexdigest()
        return self.lifecycle.get_or_create_chat_draft({**data, **inherited, "source_ref": ref}, key, prepare=prepare)
