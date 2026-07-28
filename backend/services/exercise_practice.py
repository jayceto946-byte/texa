"""Application service for exercise practice-session workflows."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from memory.exercise_bank import ExerciseBank, ExerciseRecord, PracticeSession
from memory.mistake_book import MistakeBook, MistakeRecord


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


@dataclass
class PracticeAnswerService:
    """Coordinate idempotent practice answers and optional mistake creation."""

    bank: ExerciseBank
    mistake_book_provider: MistakeBookProvider
    book_name: str
    mistake_factory: MistakeFactory
    log_event: EventLogger

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
        if add_to_mistake and not mistake_id:
            stable_key = f"{self.book_name}\0{session_id}\0{record.id}"
            stable_mistake_id = (
                "ps_" + hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:16]
            )
            try:
                mistake_id = self.mistake_book_provider().add_if_absent(
                    self.mistake_factory(
                        record,
                        user_answer=user_answer,
                        mistake_id=stable_mistake_id,
                    )
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

        if answer_created:
            self.log_event(
                "exercise_practiced",
                record,
                {
                    "quality": quality,
                    "status": record.status,
                    "session_id": session_id,
                },
            )
        return PracticeAnswerResult(
            session=session,
            record=record,
            mistake_id=mistake_id,
            mistake_error=mistake_error,
        )
