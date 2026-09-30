"""Application service for exercise practice-session workflows."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from memory.exercise_bank import ExerciseBank, ExerciseRecord, PracticeSession
from memory.mistake_book import MistakeBook, MistakeRecord
from memory.mistake_lifecycle import MistakeLifecycleStore


class MistakeFactory(Protocol):
    def __call__(
        self,
        record: ExerciseRecord,
        *,
        user_answer: str = "",
        mistake_id: str = "",
    ) -> MistakeRecord: ...


class EventLogger(Protocol):
    def __call__(
        self,
        event_type: str,
        record: ExerciseRecord,
        payload: dict,
    ) -> None: ...


class MistakeBookProvider(Protocol):
    def __call__(self) -> MistakeBook: ...


@dataclass(frozen=True)
class PracticeAnswerResult:
    session: PracticeSession
    record: ExerciseRecord
    mistake_id: str = ""
    mistake_error: str = ""
    candidate_id: str = ""


@dataclass
class PracticeAnswerService:
    """Coordinate idempotent practice answers and optional mistake creation."""

    bank: ExerciseBank
    mistake_book_provider: MistakeBookProvider
    book_name: str
    mistake_factory: MistakeFactory
    log_event: EventLogger
    reconcile_events: bool = False

    def answer_session(
        self,
        session_id: str,
        *,
        exercise_id: str,
        user_answer: str = "",
        quality: int = 0,
        note: str = "",
        add_to_mistake: bool = False,
    ) -> PracticeAnswerResult:
        session, record, answer_created = self.bank.record_session_answer_with_status(
            session_id,
            exercise_id=exercise_id,
            user_answer=user_answer,
            quality=quality,
            note=note,
        )

        mistake_id = str(session.results.get(record.id, {}).get("mistake_id") or "")
        mistake_error = ""
        candidate_id = ""
        if add_to_mistake and not mistake_id:
            stable_key = f"{self.book_name}\0{record.id}"
            stable_mistake_id = (
                "ps_" + hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:16]
            )
            try:
                mistake_book = self.mistake_book_provider()
                mistake_id = mistake_book.add_if_absent(
                    self.mistake_factory(
                        record,
                        user_answer=user_answer,
                        mistake_id=stable_mistake_id,
                    )
                )
                lifecycle = MistakeLifecycleStore(mistake_book.store)
                lifecycle.link_source(f"exercise:{self.book_name}:{record.id}", mistake_id)
                lifecycle.append_occurrence_once(
                    mistake_id, f"practice:{self.book_name}:{session_id}:{record.id}",
                    answer=user_answer,
                    source_ref={"type": "exercise_attempt", "exercise_id": record.id, "session_id": session_id},
                )
                session = self.bank.attach_practice_session_mistake(
                    session_id,
                    record.id,
                    mistake_id,
                )
            except Exception as exc:
                mistake_error = str(exc)
            else:
                self.log_event(
                    "exercise_to_mistake",
                    record,
                    {
                        "mistake_id": mistake_id,
                        "trigger": "practice_session",
                        "session_id": session_id,
                    },
                )
        elif quality < 3 and not mistake_id:
            try:
                lifecycle = MistakeLifecycleStore(self.mistake_book_provider().store)
                candidate = lifecycle.create_candidate(
                    f"practice:{self.book_name}:{session_id}:{record.id}",
                    {
                        "question_text": record.question_text, "user_answer": user_answer,
                        "correct_answer": record.answer, "subject": record.subject,
                        "chapter": record.chapter, "source": record.source,
                        "tags": record.tags, "image_path": record.image_path,
                        "ocr_text": record.ocr_text, "content_complete": True,
                        "failure_confirmed": True,
                        "stable_source_key": f"exercise:{self.book_name}:{record.id}",
                        "source_ref": {"type": "exercise_attempt", "exercise_id": record.id, "session_id": session_id},
                    },
                )
                candidate_id = candidate["id"]
            except Exception as exc:
                mistake_error = str(exc)

        if answer_created or self.reconcile_events:
            stored = session.results[record.id]
            self.log_event(
                "exercise_practiced",
                record,
                {
                    "quality": stored["quality"],
                    "status": record.status,
                    "session_id": session_id,
                    "event_id": "evt_practice_" + hashlib.sha256(f"{self.book_name}\0{session_id}\0{record.id}".encode()).hexdigest(),
                },
            )
        return PracticeAnswerResult(
            session=session,
            record=record,
            mistake_id=mistake_id,
            mistake_error=mistake_error,
            candidate_id=candidate_id,
        )
