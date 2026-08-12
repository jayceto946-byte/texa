"""Append-only learning event log.

This store is a shared timeline for chat, concept exposure, mistakes, and
exercise activity. Existing feature stores remain the source of truth; events
make cross-feature summaries easier without migrating old data immediately.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import PROGRESS_PATH
from utils.path_safety import safe_book_name, safe_child_path
from utils.sqlite_recovery import prepare_sqlite_retry_files
from utils.sqlite_migrations import apply_sqlite_migrations
from utils.subject_catalog import normalize_subject_value, subject_matches


@dataclass
class LearningEvent:
    event_type: str
    learner_id: str = "local_default"
    book_id: str = ""
    book_name: str = ""
    chapter_id: str = ""
    unit_id: str = ""
    subject: str = ""
    conversation_id: str = ""
    source_type: str = ""
    source_id: str = ""
    concept_names: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:16]}")

    def to_dict(self) -> dict:
        return asdict(self)


class LearningEventStore:
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

    def _init_db(self) -> None:
        try:
            self._init_db_once()
        except sqlite3.OperationalError as exc:
            if not _is_sqlite_storage_error(exc):
                raise
            self._force_delete_journal = True
            self._prepare_retry_db_files()
            self._init_db_once()

    def _init_db_once(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_events (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    learner_id TEXT NOT NULL DEFAULT 'local_default',
                    book_id TEXT NOT NULL DEFAULT '',
                    book_name TEXT,
                    chapter_id TEXT NOT NULL DEFAULT '',
                    unit_id TEXT NOT NULL DEFAULT '',
                    subject TEXT,
                    conversation_id TEXT,
                    source_type TEXT,
                    source_id TEXT,
                    concept_names TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_learning_events_type_time ON learning_events(event_type, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_learning_events_book_time ON learning_events(book_name, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_learning_events_subject_time ON learning_events(subject, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_learning_events_source ON learning_events(source_type, source_id)")
            apply_sqlite_migrations(
                conn,
                component="learning_events",
                current_version=2,
                migrations={2: _migrate_learning_events_v2},
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_learning_events_learner_book_time "
                "ON learning_events(learner_id, book_id, timestamp)"
            )
            conn.commit()

    def _prepare_retry_db_files(self) -> None:
        result = prepare_sqlite_retry_files(self.db_path)
        if result["preserved"]:
            print(
                f"[sqlite] preserved non-empty recovery files for {self.db_path}: "
                f"{', '.join(result['preserved'])}",
                flush=True,
            )

    def append(self, event: LearningEvent) -> str:
        event.learner_id = _clean_identifier(event.learner_id, "local_default")
        event.book_id = _clean_identifier(event.book_id)
        event.subject = normalize_subject_value(event.subject)
        event.book_name = safe_book_name(event.book_name) if event.book_name else ""
        event.chapter_id = _clean_identifier(event.chapter_id)
        event.unit_id = _clean_identifier(event.unit_id)
        event.concept_names = _dedupe_names(event.concept_names)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO learning_events
                (id, event_type, timestamp, learner_id, book_id, book_name, chapter_id, unit_id,
                 subject, conversation_id, source_type, source_id, concept_names, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.event_type,
                    event.timestamp,
                    event.learner_id,
                    event.book_id,
                    event.book_name,
                    event.chapter_id,
                    event.unit_id,
                    event.subject,
                    event.conversation_id,
                    event.source_type,
                    event.source_id,
                    json.dumps(event.concept_names, ensure_ascii=False),
                    json.dumps(event.payload, ensure_ascii=False),
                ),
            )
            conn.commit()
        return event.id

    def list_recent(
        self,
        *,
        event_type: str = "",
        book_name: str = "",
        subject: str = "",
        learner_id: str = "",
        book_id: str = "",
        limit: int = 100,
    ) -> list[LearningEvent]:
        sql = _event_select_sql() + " WHERE 1=1"
        params: list[Any] = []
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        if book_name:
            sql += " AND book_name = ?"
            params.append(safe_book_name(book_name))
        if learner_id:
            sql += " AND learner_id = ?"
            params.append(_clean_identifier(learner_id, "local_default"))
        if book_id:
            sql += " AND book_id = ?"
            params.append(_clean_identifier(book_id))
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(max(limit if not subject else limit * 10, 1))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        events = [_row_to_event(row) for row in rows]
        if subject:
            events = [event for event in events if subject_matches(event.subject, subject)]
        return events[:limit]

    def list_for_state(
        self,
        *,
        learner_id: str,
        book_id: str = "",
        book_name: str = "",
    ) -> list[LearningEvent]:
        """Read the complete ordered event stream for one rebuildable state."""
        learner = _clean_identifier(learner_id, "local_default")
        normalized_book = safe_book_name(book_name) if book_name else ""
        sql = _event_select_sql() + " WHERE (learner_id = ? OR learner_id = '')"
        params: list[Any] = [learner]
        if book_id and normalized_book:
            sql += " AND (book_id = ? OR (book_id = '' AND book_name = ?))"
            params.extend([_clean_identifier(book_id), normalized_book])
        elif book_id:
            sql += " AND book_id = ?"
            params.append(_clean_identifier(book_id))
        elif normalized_book:
            sql += " AND book_name = ?"
            params.append(normalized_book)
        sql += " ORDER BY timestamp ASC, rowid ASC"
        with self._connect() as conn:
            return [_row_to_event(row) for row in conn.execute(sql, params).fetchall()]


def _row_to_event(row) -> LearningEvent:
    concept_names = json.loads(row[12] or "[]")
    payload = json.loads(row[13] or "{}")
    return LearningEvent(
        id=row[0],
        event_type=row[1],
        timestamp=row[2],
        learner_id=row[3] or "local_default",
        book_id=row[4] or "",
        book_name=row[5] or "",
        chapter_id=row[6] or "",
        unit_id=row[7] or "",
        subject=row[8] or "",
        conversation_id=row[9] or "",
        source_type=row[10] or "",
        source_id=row[11] or "",
        concept_names=concept_names if isinstance(concept_names, list) else [],
        payload=payload if isinstance(payload, dict) else {},
    )


def _event_select_sql() -> str:
    return (
        "SELECT id, event_type, timestamp, learner_id, book_id, book_name, chapter_id, unit_id, "
        "subject, conversation_id, source_type, source_id, concept_names, payload FROM learning_events"
    )


def _clean_identifier(value: str, default: str = "") -> str:
    clean = " ".join(str(value or "").strip().split())[:160]
    return clean or default


def _migrate_learning_events_v2(conn: sqlite3.Connection) -> None:
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(learning_events)")}
    additions = {
        "learner_id": "TEXT NOT NULL DEFAULT 'local_default'",
        "book_id": "TEXT NOT NULL DEFAULT ''",
        "chapter_id": "TEXT NOT NULL DEFAULT ''",
        "unit_id": "TEXT NOT NULL DEFAULT ''",
    }
    for name, declaration in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE learning_events ADD COLUMN {name} {declaration}")


def _dedupe_names(names: list[str]) -> list[str]:
    result: list[str] = []
    for name in names or []:
        value = str(name or "").strip()
        if value and value not in result:
            result.append(value)
        if len(result) >= 20:
            break
    return result


def concept_names(concepts: list[dict]) -> list[str]:
    return _dedupe_names([str(item.get("name", "")) for item in concepts or [] if isinstance(item, dict)])


def _is_sqlite_storage_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return (
        "disk i/o" in message
        or "readonly" in message
        or "unable to open database file" in message
    )


def get_learning_event_store(data_dir: str | Path = PROGRESS_PATH) -> LearningEventStore:
    return LearningEventStore(safe_child_path(data_dir, "learning_events.db"))


def log_learning_event(event_type: str, **kwargs) -> str:
    return get_learning_event_store().append(LearningEvent(event_type=event_type, **kwargs))
