"""Recovery of explicit effects on committed answers, within one desktop backend.

The outcome JSON is the durable queue. Domain stores own permanent idempotency
receipts; completing a queue item never substitutes for those receipts.
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
import time

from config import PROGRESS_PATH

logger = logging.getLogger(__name__)
EFFECT_SCHEMA = "execution-effect/v1"
_EFFECT_LOCKS = tuple(threading.Lock() for _ in range(64))


class _EffectStopped(Exception):
    pass


def chat_effects(state: dict, task) -> list[dict]:
    proposal = state.get("feedback_proposal")
    if not proposal or task.status not in {"completed", "degraded"}:
        return []
    return [{"kind": "chat_feedback", "payload": proposal}]


def visual_effect(record, *, book_name: str, import_to_mistakes: bool) -> dict:
    return {"kind": "visual_feedback", "payload": {
        "book_name": book_name, "import_to_mistakes": import_to_mistakes,
        "record": record.to_dict(),
    }}


def bind_effects(current, task, event: dict, proposals: list[dict]) -> list[dict]:
    """Called under commit_outcome's lock, using persisted consent and identity."""
    if task.status not in {"completed", "degraded"} or event["type"] != "final":
        raise ValueError("effects require a committed delivered answer")
    if event["payload"].get("task_status") != task.status:
        raise ValueError("effect outcome status does not match the task")
    if len(proposals) != 1:
        raise ValueError("only one existing feedback effect is allowed per answer")
    proposal = proposals[0]
    if set(proposal) != {"kind", "payload"}:
        raise ValueError("invalid effect proposal")
    kind, payload = proposal["kind"], copy.deepcopy(proposal["payload"])
    if kind == "chat_feedback" and current.task_type == "qa":
        from graph.feedback_node import feedback_proposal
        if set(payload) - set(feedback_proposal(payload)):
            raise ValueError("unsupported chat feedback fields")
        # Authority comes from the request/task, never model-generated fields.
        payload["book_name"] = current.artifacts.get("book_name") or "default"
        payload["subject"] = current.artifacts.get("subject") or ""
        payload["conversation_id"] = current.conversation_id
        payload["answer_verification"] = copy.deepcopy(task.verification)
        payload["final_output"] = task.artifacts.get("final_output") or ""
    elif kind == "visual_feedback" and current.task_type == "visual_qa":
        if set(payload) != {"book_name", "import_to_mistakes", "record"}:
            raise ValueError("unsupported visual feedback fields")
        if payload["import_to_mistakes"] is not bool(current.artifacts.get("import_to_mistakes")):
            raise ValueError("mistake import requires the saved request selection")
        payload["book_name"] = current.artifacts.get("book_name") or "default"
        from memory.mistake_book import MistakeRecord
        if set(payload["record"]) - set(MistakeRecord.__dataclass_fields__):
            raise ValueError("unsupported mistake fields")
        payload["record"]["explanation"] = task.artifacts.get("completed_derivation") or ""
    else:
        raise ValueError("unsupported task effect")
    if len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 1_000_000:
        raise ValueError("feedback payload exceeds the durable queue budget")
    operation_id = "effect_" + hashlib.sha256(f"{task.id}/{event['run_id']}/0".encode()).hexdigest()
    return [{"schema": EFFECT_SCHEMA, "id": operation_id, "run_id": event["run_id"],
             "kind": kind, "payload": payload, "prepared": None, "receipt": None,
             "attempts": 0, "retry_at": 0, "error": ""}]


def _prepare(effect: dict) -> dict:
    if effect["kind"] == "chat_feedback":
        from graph.feedback_node import _record_concept_memory
        return _record_concept_memory(effect["payload"], prepare_only=True)
    if effect["kind"] == "visual_feedback":
        # Visual concepts already use the local response linker; freeze that result.
        from backend.services.learning_state import resolve_book_identity
        record = copy.deepcopy(effect["payload"]["record"])
        record["book_id"] = resolve_book_identity(effect["payload"]["book_name"])["book_id"]
        return record
    raise ValueError("unsupported effect kind")


def _apply(effect: dict, *, stop: threading.Event | None = None) -> dict:
    def before_write():
        if stop and stop.is_set():
            raise _EffectStopped()

    payload, operation_id = effect["payload"], effect["id"]
    if effect["kind"] == "chat_feedback":
        from graph.feedback_node import _record_concept_memory, _rating_to_quality
        from memory.study_memory import StudyMemory
        from memory.spaced_repetition import SpacedRepetition
        book_name = payload.get("book_name") or "default"
        chapters = list(dict.fromkeys(payload.get("target_chapters") or []))
        if (payload.get("answer_verification") or {}).get("status") == "passed" and chapters:
            memory = StudyMemory(book_name)
            for ordinal, chapter in enumerate(chapters):
                before_write()
                memory.mark_chapter_studied(chapter, operation_id=f"{operation_id}:chapter:{ordinal}")
        feedback = payload.get("user_feedback") or {}
        if feedback.get("rating") and chapters:
            chapter = chapters[0]
            kp = feedback.get("knowledge_point") or f"{chapter}_auto"
            card_id = f"{chapter}::{kp}"
            sr = SpacedRepetition(book_name)
            before_write()
            sr.add_knowledge_point(card_id, chapter, kp)
            before_write()
            sr.review(card_id, _rating_to_quality(feedback["rating"]), operation_id=operation_id + ":review")
        concepts = _record_concept_memory(payload, prepared=effect["prepared"], operation_id=operation_id,
                                          before_write=before_write)
        return {"concept_count": len(concepts)}
    if effect["kind"] == "visual_feedback":
        from knowledge.concept_memory import ConceptMemory
        from memory.mistake_book import MistakeRecord, get_mistake_book
        from memory.learning_events import LearningEvent, concept_names, get_learning_event_store
        record = MistakeRecord.from_dict(effect["prepared"])
        book_name = payload["book_name"]
        result = {"mistake_id": "", "concept_count": len(record.linked_concepts)}
        if payload["import_to_mistakes"]:
            record.id = operation_id + "_mistake"
            book = get_mistake_book(book_name, str(PROGRESS_PATH))
            if book.get(record.id) is None:
                before_write()
                book.add_if_absent(record)
            result["mistake_id"] = record.id
            result["image_path"] = record.image_path
            before_write()
            get_learning_event_store().append(LearningEvent(
                id=operation_id + ":mistake_added", event_type="mistake_added",
                book_name=book_name, book_id=record.book_id, chapter_id=record.chapter or "",
                subject=record.subject, source_type="mistake", source_id=record.id,
                concept_names=concept_names(record.linked_concepts), payload={"origin": "chat_image"},
            ))
        if record.linked_concepts:
            before_write()
            ConceptMemory(book_name).log_exposure(
                record.linked_concepts, record.question_text, "image_qa", source="chat_image",
                subject=record.subject, operation_id=operation_id + ":exposure",
            )
        return result
    raise ValueError("unsupported effect kind")


def recover_task_effects(store, task_id: str, *, run_id: str = "", stop: threading.Event | None = None) -> None:
    """One bounded attempt. Model work never holds the LearningTask lock."""
    key = str(store._path(task_id).resolve()).casefold()
    lock = _EFFECT_LOCKS[int(hashlib.sha256(key.encode()).hexdigest(), 16) % len(_EFFECT_LOCKS)]
    if not lock.acquire(blocking=False):
        return
    try:
        for effect in store.outcome_effects(task_id, run_id):
            if stop and stop.is_set():
                return
            if effect.get("schema") != EFFECT_SCHEMA or effect.get("receipt") is not None:
                continue
            if effect.get("retry_at", 0) > time.time():
                continue
            owned_run = effect["run_id"]
            try:
                if effect.get("prepared") is None:
                    prepared = _prepare(effect)
                    if stop and stop.is_set():
                        return
                    effect = store.update_outcome_effect(task_id, owned_run, effect["id"], prepared=prepared)
                if stop and stop.is_set():
                    return
                receipt = _apply(effect, **({"stop": stop} if stop is not None else {}))
                if stop and stop.is_set():
                    return
                store.update_outcome_effect(task_id, owned_run, effect["id"], receipt=receipt, error="", retry_at=0)
            except _EffectStopped:
                return
            except Exception as exc:
                attempts = min(int(effect.get("attempts", 0)) + 1, 1000)
                # Persist a stable safe error, not provider messages or credentials.
                store.update_outcome_effect(
                    task_id, owned_run, effect["id"], attempts=attempts,
                    retry_at=time.time() + min(300, 5 * 2 ** min(attempts - 1, 6)),
                    error="领域记录待恢复：" + type(exc).__name__,
                )
                logger.warning("effect pending recovery: %s (%s)", effect["id"], type(exc).__name__)
    finally:
        lock.release()


def visual_effect_result(store, task_id: str, run_id: str) -> dict:
    effects = store.outcome_effects(task_id, run_id)
    result = {"mistake_id": "", "effects_status": "completed"}
    for effect in effects:
        if effect["kind"] == "visual_feedback":
            if effect.get("receipt") is None:
                result.update(effects_status="pending", effects_message="答案已保存，学习记录待恢复")
            else:
                result.update(effect["receipt"])
    return result


class ExecutionEffectsWorker:
    """One lifecycle-owned thread, disk queue, and bounded retry interval."""
    def __init__(self, store, *, interval: float = 5):
        self.store = store
        self.interval = max(.05, min(60, interval))
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="execution-effects", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self, timeout: float = 2) -> bool:
        self.stop_event.set()
        self.thread.join(max(0, min(5, timeout)))
        return not self.thread.is_alive()

    def run_once(self):
        for path in self.store.root.glob("*.json"):
            if self.stop_event.is_set():
                return
            try:
                recover_task_effects(self.store, path.stem, stop=self.stop_event)
                if not self.stop_event.is_set():
                    self.store.project_effects(path.stem)
            except Exception as exc:
                logger.warning("effect recovery unavailable: %s (%s)", path.stem, type(exc).__name__)

    def _run(self):
        while not self.stop_event.is_set():
            self.run_once()
            self.stop_event.wait(self.interval)
