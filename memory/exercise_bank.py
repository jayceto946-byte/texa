"""Exercise bank storage.

The exercise bank is a general question asset layer. Mistakes can be copied into
this structure through origin_type/origin_id without changing the mistake book.
"""
from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from utils.path_safety import safe_book_name, safe_child_path
from utils.book_registry import BookRegistry
from utils.sqlite_recovery import prepare_sqlite_retry_files
from utils.sqlite_migrations import apply_sqlite_migrations
from utils.subject_catalog import subject_matches
from typing import Any, Optional


@dataclass
class ExerciseRecord:
    question_text: str
    book_id: str = ""
    answer: str = ""
    explanation: str = ""
    source: str = ""
    subject: str = ""
    chapter: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    question_type: str = ""
    difficulty: int = 3
    image_path: Optional[str] = None
    ocr_text: str = ""
    linked_concepts: list[dict] = field(default_factory=list)
    origin_type: str = "manual"
    origin_id: str = ""
    status: str = "new"
    notes: str = ""
    last_practiced: Optional[str] = None
    practice_count: int = 0
    practice_history: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExerciseRecord":
        data = dict(data)
        if data.get("chapter") == "":
            data["chapter"] = None
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def question_fingerprint(question_text: str) -> str:
    normalized = "".join(str(question_text or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


@dataclass
class PracticeSession:
    exercise_ids: list[str]
    filters: dict = field(default_factory=dict)
    shuffle: bool = False
    seed: int = 0
    current_index: int = 0
    status: str = "active"
    results: dict[str, dict] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PracticeSession":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def summary(self) -> dict:
        qualities = [int(item.get("quality", 0)) for item in self.results.values()]
        return {
            "total": len(self.exercise_ids),
            "answered": len(self.results),
            "remaining": max(0, len(self.exercise_ids) - len(self.results)),
            "mastered": sum(1 for quality in qualities if quality >= 4),
            "struggling": sum(1 for quality in qualities if quality < 3),
            "average_quality": round(sum(qualities) / len(qualities), 2) if qualities else 0.0,
        }


class ExerciseBankStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._force_delete_journal = False
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.execute("PRAGMA busy_timeout = 15000")
        if self._force_delete_journal:
            conn.execute("PRAGMA journal_mode = DELETE")
        else:
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError as exc:
                if not _is_sqlite_storage_error(exc):
                    raise
                self._force_delete_journal = True
                conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _init_db(self):
        try:
            self._init_db_once()
        except sqlite3.OperationalError as exc:
            if not _is_sqlite_storage_error(exc):
                raise
            self._force_delete_journal = True
            self._prepare_retry_db_files()
            self._init_db_once()

    def _init_db_once(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exercises (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    subject TEXT,
                    chapter TEXT,
                    source TEXT,
                    origin_type TEXT,
                    origin_id TEXT,
                    status TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_subject ON exercises(subject)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_chapter ON exercises(chapter)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_origin ON exercises(origin_type, origin_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_status ON exercises(status)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exercise_import_batches (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exercise_practice_sessions (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ex_session_status ON exercise_practice_sessions(status, updated_at)")
            apply_sqlite_migrations(conn, component="exercise_bank", current_version=1)
            conn.commit()

    def _prepare_retry_db_files(self) -> None:
        result = prepare_sqlite_retry_files(self.db_path)
        if result["preserved"]:
            print(
                f"[sqlite] preserved non-empty recovery files for {self.db_path}: "
                f"{', '.join(result['preserved'])}",
                flush=True,
            )

    def add(self, record: ExerciseRecord) -> str:
        record.updated_at = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO exercises (id, data, created_at, updated_at, subject, chapter, source, origin_type, origin_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    json.dumps(record.to_dict(), ensure_ascii=False),
                    record.created_at,
                    record.updated_at,
                    record.subject,
                    record.chapter,
                    record.source,
                    record.origin_type,
                    record.origin_id,
                    record.status,
                ),
            )
            conn.commit()
        return record.id

    def find_duplicate(self, question_text: str) -> Optional[str]:
        fingerprint = question_fingerprint(question_text)
        if not fingerprint:
            return None
        for record in self.list_all(limit=100000):
            if question_fingerprint(record.question_text) == fingerprint:
                return record.id
        return None

    def add_batch(
        self,
        records: list[ExerciseRecord],
        *,
        source_label: str = "",
        allow_duplicates: bool = False,
    ) -> dict:
        existing = {
            question_fingerprint(record.question_text): record.id
            for record in self.list_all(limit=100000)
            if question_fingerprint(record.question_text)
        }
        accepted: list[ExerciseRecord] = []
        skipped: list[dict] = []
        seen = dict(existing)
        for record in records:
            fingerprint = question_fingerprint(record.question_text)
            duplicate_of = seen.get(fingerprint) if fingerprint else None
            if duplicate_of and not allow_duplicates:
                skipped.append({"origin_id": record.origin_id, "duplicate_of": duplicate_of})
                continue
            accepted.append(record)
            if fingerprint:
                seen[fingerprint] = record.id

        batch_id = str(uuid.uuid4())[:12]
        created_at = datetime.now().isoformat()
        batch = {
            "id": batch_id,
            "source_label": source_label.strip(),
            "exercise_ids": [record.id for record in accepted],
            "skipped": skipped,
            "created_at": created_at,
            "status": "active",
        }
        with self._connect() as conn:
            for record in accepted:
                record.updated_at = created_at
                conn.execute(
                    """
                    INSERT INTO exercises (id, data, created_at, updated_at, subject, chapter, source, origin_type, origin_id, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        json.dumps(record.to_dict(), ensure_ascii=False),
                        record.created_at,
                        record.updated_at,
                        record.subject,
                        record.chapter,
                        record.source,
                        record.origin_type,
                        record.origin_id,
                        record.status,
                    ),
                )
            conn.execute(
                "INSERT INTO exercise_import_batches (id, data, created_at, status) VALUES (?, ?, ?, ?)",
                (batch_id, json.dumps(batch, ensure_ascii=False), created_at, "active"),
            )
            conn.commit()
        return batch

    def rollback_import_batch(self, batch_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT data, status FROM exercise_import_batches WHERE id = ?", (batch_id,)).fetchone()
            if not row:
                return None
            batch = json.loads(row[0])
            if row[1] == "rolled_back":
                return batch
            exercise_ids = [str(item) for item in batch.get("exercise_ids", []) if str(item)]
            if exercise_ids:
                placeholders = ",".join("?" for _ in exercise_ids)
                conn.execute(f"DELETE FROM exercises WHERE id IN ({placeholders})", exercise_ids)
            batch["status"] = "rolled_back"
            batch["rolled_back_at"] = datetime.now().isoformat()
            conn.execute(
                "UPDATE exercise_import_batches SET data = ?, status = ? WHERE id = ?",
                (json.dumps(batch, ensure_ascii=False), "rolled_back", batch_id),
            )
            conn.commit()
        return batch

    def list_import_batches(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT data FROM exercise_import_batches ORDER BY created_at DESC LIMIT ?",
                (max(1, min(100, int(limit))),),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get(self, rid: str) -> Optional[ExerciseRecord]:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM exercises WHERE id = ?", (rid,)).fetchone()
        return ExerciseRecord.from_dict(json.loads(row[0])) if row else None

    def find_by_origin(self, origin_type: str, origin_id: str) -> Optional[ExerciseRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM exercises WHERE origin_type = ? AND origin_id = ? LIMIT 1",
                (origin_type, origin_id),
            ).fetchone()
        return ExerciseRecord.from_dict(json.loads(row[0])) if row else None

    def update(self, record: ExerciseRecord):
        record.updated_at = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE exercises
                SET data = ?, updated_at = ?, subject = ?, chapter = ?, source = ?, origin_type = ?, origin_id = ?, status = ?
                WHERE id = ?
                """,
                (
                    json.dumps(record.to_dict(), ensure_ascii=False),
                    record.updated_at,
                    record.subject,
                    record.chapter,
                    record.source,
                    record.origin_type,
                    record.origin_id,
                    record.status,
                    record.id,
                ),
            )
            conn.commit()

    def delete(self, rid: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM exercises WHERE id = ?", (rid,))
            conn.commit()

    def list_all(
        self,
        subject: Optional[str] = None,
        chapter: Optional[str] = None,
        tag: Optional[str] = None,
        search_kw: str = "",
        status: str = "",
        limit: int = 100,
    ) -> list[ExerciseRecord]:
        sql = "SELECT data FROM exercises WHERE 1=1"
        params: list[Any] = []
        if chapter:
            sql += " AND chapter = ?"
            params.append(chapter)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit if not subject and not tag and not search_kw.strip() else max(limit * 10, 1000))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        records = [ExerciseRecord.from_dict(json.loads(row[0])) for row in rows]
        if subject:
            records = [r for r in records if subject_matches(r.subject, subject)]
        if tag:
            records = [r for r in records if tag in r.tags]
        if search_kw.strip():
            kw = search_kw.strip().lower()
            records = [
                r for r in records
                if kw in r.question_text.lower()
                or kw in r.answer.lower()
                or kw in r.explanation.lower()
                or kw in r.source.lower()
                or any(kw in tag.lower() for tag in r.tags)
            ]
        return records[:limit]

    def stats(self, subject: Optional[str] = None) -> dict:
        records = self.list_all(subject=subject, limit=10000)
        by_type: dict[str, int] = {}
        by_tag: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for record in records:
            if record.question_type:
                by_type[record.question_type] = by_type.get(record.question_type, 0) + 1
            by_status[record.status] = by_status.get(record.status, 0) + 1
            for tag in record.tags:
                by_tag[tag] = by_tag.get(tag, 0) + 1
        return {"total": len(records), "by_type": by_type, "by_tag": by_tag, "by_status": by_status}


    def save_session(self, session: PracticeSession) -> PracticeSession:
        session.updated_at = datetime.now().isoformat()
        payload = json.dumps(session.to_dict(), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO exercise_practice_sessions (id, data, updated_at, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at, status = excluded.status
                """,
                (session.id, payload, session.updated_at, session.status),
            )
            conn.commit()
        return session

    def create_session_once(self, session: PracticeSession) -> PracticeSession:
        """Replace the active session and insert this operation in one transaction."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data FROM exercise_practice_sessions WHERE id = ?", (session.id,)).fetchone()
            if row:
                return PracticeSession.from_dict(json.loads(row[0]))
            rows = conn.execute("SELECT data FROM exercise_practice_sessions WHERE status IN ('active', 'paused')").fetchall()
            now = datetime.now().isoformat()
            for row in rows:
                previous = PracticeSession.from_dict(json.loads(row[0]))
                previous.status = "replaced"
                previous.completed_at = now
                previous.updated_at = now
                conn.execute("UPDATE exercise_practice_sessions SET data = ?, status = ?, updated_at = ? WHERE id = ?",
                             (json.dumps(previous.to_dict(), ensure_ascii=False), previous.status, now, previous.id))
            session.updated_at = now
            conn.execute("INSERT INTO exercise_practice_sessions (id, data, updated_at, status) VALUES (?, ?, ?, ?)",
                         (session.id, json.dumps(session.to_dict(), ensure_ascii=False), now, session.status))
        return session

    def get_session(self, session_id: str) -> Optional[PracticeSession]:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM exercise_practice_sessions WHERE id = ?", (session_id,)).fetchone()
        return PracticeSession.from_dict(json.loads(row[0])) if row else None

    def get_active_session(self) -> Optional[PracticeSession]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM exercise_practice_sessions WHERE status IN ('active', 'paused') ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return PracticeSession.from_dict(json.loads(row[0])) if row else None


    def record_session_answer(
        self,
        session_id: str,
        *,
        exercise_id: str,
        user_answer: str = "",
        quality: int = 0,
        note: str = "",
    ) -> tuple[PracticeSession, ExerciseRecord, bool]:
        """Atomically persist exercise practice and session progress.

        Replaying an answer for an exercise already present in the session is
        idempotent: the stored session and exercise are returned unchanged.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session_row = conn.execute(
                "SELECT data FROM exercise_practice_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not session_row:
                raise ValueError("\u672a\u627e\u5230\u7ec3\u4e60\u4f1a\u8bdd")
            session = PracticeSession.from_dict(json.loads(session_row[0]))

            exercise_row = conn.execute(
                "SELECT data FROM exercises WHERE id = ?", (exercise_id,)
            ).fetchone()
            if not exercise_row:
                raise ValueError("\u672a\u627e\u5230\u5f53\u524d\u4e60\u9898")
            record = ExerciseRecord.from_dict(json.loads(exercise_row[0]))

            if exercise_id in session.results:
                return session, record, False
            if session.status != "active":
                raise ValueError("\u7ec3\u4e60\u4f1a\u8bdd\u5f53\u524d\u4e0d\u53ef\u4f5c\u7b54")
            if session.current_index < 0 or session.current_index >= len(session.exercise_ids):
                raise ValueError("\u7ec3\u4e60\u4f1a\u8bdd\u8fdb\u5ea6\u5f02\u5e38")
            if session.exercise_ids[session.current_index] != exercise_id:
                raise ValueError("\u63d0\u4ea4\u9898\u76ee\u4e0e\u5f53\u524d\u7ec3\u4e60\u8fdb\u5ea6\u4e0d\u4e00\u81f4")

            normalized_quality = max(0, min(5, int(quality)))
            practiced_at = datetime.now().isoformat()
            record.last_practiced = practiced_at
            record.practice_count += 1
            record.practice_history.append({
                "date": practiced_at,
                "quality": normalized_quality,
                "user_answer": user_answer.strip(),
                "note": note.strip(),
            })
            if normalized_quality >= 4:
                record.status = "mastered"
            elif normalized_quality >= 3:
                record.status = "practicing"
            else:
                record.status = "needs_review"
            record.updated_at = practiced_at
            conn.execute(
                """
                UPDATE exercises
                SET data = ?, updated_at = ?, subject = ?, chapter = ?, source = ?, origin_type = ?, origin_id = ?, status = ?
                WHERE id = ?
                """,
                (
                    json.dumps(record.to_dict(), ensure_ascii=False),
                    record.updated_at,
                    record.subject,
                    record.chapter,
                    record.source,
                    record.origin_type,
                    record.origin_id,
                    record.status,
                    record.id,
                ),
            )

            session.results[exercise_id] = {
                "exercise_id": exercise_id,
                "user_answer": user_answer.strip(),
                "quality": normalized_quality,
                "note": note.strip(),
                "mistake_id": "",
                "answered_at": practiced_at,
            }
            session.current_index += 1
            if session.current_index >= len(session.exercise_ids):
                session.status = "completed"
                session.completed_at = practiced_at
            session.updated_at = practiced_at
            conn.execute(
                "UPDATE exercise_practice_sessions SET data = ?, updated_at = ?, status = ? WHERE id = ?",
                (json.dumps(session.to_dict(), ensure_ascii=False), session.updated_at, session.status, session.id),
            )
            return session, record, True

    def attach_session_mistake(
        self, session_id: str, exercise_id: str, mistake_id: str
    ) -> PracticeSession:
        """Attach a mistake id to the latest session state without overwriting progress."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT data FROM exercise_practice_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not row:
                raise ValueError("\u672a\u627e\u5230\u7ec3\u4e60\u4f1a\u8bdd")
            session = PracticeSession.from_dict(json.loads(row[0]))
            result = session.results.get(exercise_id)
            if not result:
                raise ValueError("\u7ec3\u4e60\u4f1a\u8bdd\u4e2d\u6ca1\u6709\u8be5\u9898\u7684\u4f5c\u7b54\u8bb0\u5f55")
            current = str(result.get("mistake_id") or "")
            if current and current != mistake_id:
                raise ValueError("\u8be5\u4f5c\u7b54\u5df2\u7ed1\u5b9a\u5176\u4ed6\u9519\u9898\u8bb0\u5f55")
            result["mistake_id"] = mistake_id
            session.updated_at = datetime.now().isoformat()
            conn.execute(
                "UPDATE exercise_practice_sessions SET data = ?, updated_at = ?, status = ? WHERE id = ?",
                (json.dumps(session.to_dict(), ensure_ascii=False), session.updated_at, session.status, session.id),
            )
            return session

class ExerciseBank:
    def __init__(self, db_path: str | Path, book_id: str = ""):
        self.store = ExerciseBankStore(db_path)
        self.book_id = book_id

    def add(self, record: ExerciseRecord) -> str:
        if self.book_id and not record.book_id:
            record.book_id = self.book_id
        return self.store.add(record)

    def find_duplicate(self, question_text: str) -> Optional[str]:
        return self.store.find_duplicate(question_text)

    def add_batch(
        self,
        records: list[ExerciseRecord],
        *,
        source_label: str = "",
        allow_duplicates: bool = False,
    ) -> dict:
        if self.book_id:
            for record in records:
                if not record.book_id:
                    record.book_id = self.book_id
        return self.store.add_batch(records, source_label=source_label, allow_duplicates=allow_duplicates)

    def rollback_import_batch(self, batch_id: str) -> Optional[dict]:
        return self.store.rollback_import_batch(batch_id)

    def list_import_batches(self, limit: int = 20) -> list[dict]:
        return self.store.list_import_batches(limit=limit)

    def get(self, rid: str) -> Optional[ExerciseRecord]:
        return self.store.get(rid)

    def find_by_origin(self, origin_type: str, origin_id: str) -> Optional[ExerciseRecord]:
        return self.store.find_by_origin(origin_type, origin_id)

    def update(self, record: ExerciseRecord):
        self.store.update(record)

    def record_practice(self, rid: str, user_answer: str = "", quality: int = 0, add_note: str = "") -> Optional[ExerciseRecord]:
        record = self.get(rid)
        if not record:
            return None
        quality = max(0, min(5, int(quality)))
        practiced_at = datetime.now().isoformat()
        record.last_practiced = practiced_at
        record.practice_count += 1
        record.practice_history.append(
            {
                "date": practiced_at,
                "quality": quality,
                "user_answer": user_answer.strip(),
                "note": add_note.strip(),
            }
        )
        if quality >= 4:
            record.status = "mastered"
        elif quality >= 3:
            record.status = "practicing"
        else:
            record.status = "needs_review"
        self.update(record)
        return record

    def create_practice_session(
        self,
        *,
        subject: str = "",
        chapter: str = "",
        tag: str = "",
        status: str = "",
        limit: int = 20,
        shuffle: bool = False,
    ) -> PracticeSession:
        previous = self.store.get_active_session()
        if previous:
            previous.status = "replaced"
            previous.completed_at = datetime.now().isoformat()
            self.store.save_session(previous)
        records = self.list_all(
            subject=subject or None,
            chapter=chapter or None,
            tag=tag or None,
            status=status,
            limit=10000,
        )
        rank = {"needs_review": 0, "practicing": 1, "new": 2, "mastered": 3}
        records.sort(key=lambda record: (rank.get(record.status, 2), record.practice_count, record.created_at))
        seed = random.SystemRandom().randint(1, 2**31 - 1)
        selected = records[:max(1, min(200, int(limit)))]
        if shuffle:
            random.Random(seed).shuffle(selected)
        if not selected:
            raise ValueError("当前筛选范围内没有可练习习题")
        session = PracticeSession(
            exercise_ids=[record.id for record in selected],
            filters={"subject": subject, "chapter": chapter, "tag": tag, "status": status},
            shuffle=shuffle,
            seed=seed,
        )
        return self.store.save_session(session)

    def get_practice_session(self, session_id: str) -> Optional[PracticeSession]:
        return self.store.get_session(session_id)

    def get_active_practice_session(self) -> Optional[PracticeSession]:
        return self.store.get_active_session()

    def save_practice_session(self, session: PracticeSession) -> PracticeSession:
        return self.store.save_session(session)

    def create_practice_session_once(self, session: PracticeSession) -> PracticeSession:
        return self.store.create_session_once(session)

    def current_session_record(self, session: PracticeSession) -> Optional[ExerciseRecord]:
        if session.current_index < 0 or session.current_index >= len(session.exercise_ids):
            return None
        return self.get(session.exercise_ids[session.current_index])

    def record_session_answer(
        self,
        session_id: str,
        *,
        exercise_id: str,
        user_answer: str = "",
        quality: int = 0,
        note: str = "",
        mistake_id: str = "",
    ) -> tuple[PracticeSession, ExerciseRecord]:
        session, record, _created = self.store.record_session_answer(
            session_id,
            exercise_id=exercise_id,
            user_answer=user_answer,
            quality=quality,
            note=note,
        )
        if mistake_id:
            session = self.store.attach_session_mistake(session_id, exercise_id, mistake_id)
        return session, record

    def record_session_answer_with_status(
        self,
        session_id: str,
        *,
        exercise_id: str,
        user_answer: str = "",
        quality: int = 0,
        note: str = "",
    ) -> tuple[PracticeSession, ExerciseRecord, bool]:
        return self.store.record_session_answer(
            session_id,
            exercise_id=exercise_id,
            user_answer=user_answer,
            quality=quality,
            note=note,
        )

    def attach_practice_session_mistake(
        self, session_id: str, exercise_id: str, mistake_id: str
    ) -> PracticeSession:
        return self.store.attach_session_mistake(session_id, exercise_id, mistake_id)

    def set_practice_session_status(self, session_id: str, status: str) -> PracticeSession:
        session = self.store.get_session(session_id)
        if not session:
            raise ValueError("未找到练习会话")
        if status not in {"active", "paused", "abandoned"}:
            raise ValueError("不支持的练习会话状态")
        if session.status == "completed":
            raise ValueError("已完成的练习会话不能修改状态")
        session.status = status
        if status == "abandoned":
            session.completed_at = datetime.now().isoformat()
        return self.store.save_session(session)

    def delete(self, rid: str):
        self.store.delete(rid)

    def list_all(self, **filters) -> list[ExerciseRecord]:
        return self.store.list_all(**filters)

    def stats(self, subject: Optional[str] = None) -> dict:
        return self.store.stats(subject=subject)


def _is_sqlite_storage_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return (
        "disk i/o" in message
        or "readonly" in message
        or "unable to open database file" in message
    )


def get_exercise_bank(book_name: str = "default", data_dir: str = "./data/progress") -> ExerciseBank:
    identity = BookRegistry(data_dir).resolve(book_name, include_archived=True)
    book_id = str(identity.get("book_id") or "") if identity else ""
    return ExerciseBank(safe_child_path(data_dir, f"exercise_bank_{safe_book_name(book_name)}.db"), book_id=book_id)
