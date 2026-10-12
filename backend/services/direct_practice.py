"""Receipt-backed direct practice; optional writes reconcile through stable keys."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from backend.services.exercise_practice import EventLogger, MistakeBookProvider, MistakeFactory
from memory.exercise_bank import ExerciseBank, ExerciseRecord
from memory.mistake_lifecycle import MistakeLifecycleStore


@dataclass(frozen=True)
class DirectPracticeResult:
    record: ExerciseRecord
    receipt: dict


@dataclass
class DirectPracticeService:
    bank: ExerciseBank
    book_name: str
    mistake_book_provider: MistakeBookProvider
    mistake_factory: MistakeFactory
    log_event: EventLogger

    def answer(self, exercise_id: str, operation_id: str, *, user_answer: str = "",
               quality: int = 0, note: str = "", add_to_mistake: bool = False) -> DirectPracticeResult:
        operation_id = operation_id.strip()
        if not operation_id:
            raise ValueError("缺少本次作答身份，请更新客户端后提交；练习尚未写入")
        payload = dict(user_answer=user_answer.strip(), quality=quality, note=note.strip(),
                       add_to_mistake=add_to_mistake)
        record, receipt = self.bank.store.record_direct_answer(exercise_id, operation_id, payload)
        if receipt["completion_status"] == "complete":
            return DirectPracticeResult(record, receipt)
        source_record = ExerciseRecord.from_dict(receipt["source_snapshot"])
        # Both retries and status recovery use the originally committed request.
        key = f"practice-direct:{self.book_name}:{exercise_id}:{operation_id}"
        event_key = hashlib.sha256(key.encode()).hexdigest()
        mistake_id = candidate_id = ""
        try:
            if add_to_mistake:
                mb = self.mistake_book_provider()
                stable_id = "ps_" + hashlib.sha256(f"{self.book_name}\0{record.id}".encode()).hexdigest()[:16]
                mistake_id = mb.add_if_absent(self.mistake_factory(
                    source_record, user_answer=payload["user_answer"], mistake_id=stable_id))
                lifecycle = MistakeLifecycleStore(mb.store)
                lifecycle.link_source(f"exercise:{self.book_name}:{record.id}", mistake_id)
                lifecycle.append_occurrence_once(mistake_id, key, answer=payload["user_answer"],
                    source_ref={"type": "exercise_practice", "exercise_id": record.id, "operation_id": operation_id})
                self.log_event("exercise_to_mistake", source_record, {
                    "mistake_id": mistake_id, "trigger": "practice", "operation_id": operation_id,
                    "event_id": "evt_direct_link_" + event_key})
            elif quality < 3:
                lifecycle = MistakeLifecycleStore(self.mistake_book_provider().store)
                candidate = lifecycle.create_candidate(key, {
                    "question_text": source_record.question_text, "user_answer": payload["user_answer"],
                    "correct_answer": source_record.answer, "subject": source_record.subject, "chapter": source_record.chapter,
                    "source": source_record.source, "tags": source_record.tags, "image_path": source_record.image_path,
                    "ocr_text": source_record.ocr_text, "content_complete": True, "failure_confirmed": True,
                    "stable_source_key": f"exercise:{self.book_name}:{record.id}",
                    "source_ref": {"type": "exercise_practice", "exercise_id": record.id, "operation_id": operation_id},
                })
                candidate_id = candidate["id"]
            self.log_event("exercise_practiced", source_record, {
                "quality": quality, "status": "mastered" if quality >= 4 else "practicing" if quality >= 3 else "needs_review",
                "add_to_mistake": add_to_mistake, "operation_id": operation_id,
                "event_id": "evt_direct_practice_" + event_key})
            record, receipt = self.bank.store.complete_direct_answer(exercise_id, operation_id,
                mistake_id=mistake_id, candidate_id=candidate_id)
        except Exception:
            # Never claim rollback: secondary writes may already be durable.
            # Another concurrent retry might have completed; reread authority.
            record, receipt = self.bank.store.direct_receipt(exercise_id, operation_id)
        return DirectPracticeResult(record, receipt)
