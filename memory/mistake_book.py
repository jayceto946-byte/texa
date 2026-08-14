"""Mistake book storage and review scheduling."""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from utils.path_safety import safe_book_name, safe_child_path
from utils.book_registry import BookRegistry
from utils.sqlite_recovery import prepare_sqlite_retry_files
from utils.sqlite_migrations import apply_sqlite_migrations
from utils.subject_catalog import subject_matches
from typing import Any, Callable, Optional


MISTAKE_TYPES = [
    "概念不清",
    "公式记错",
    "计算错误",
    "思路卡住",
    "粗心/审题错误",
]


@dataclass
class MistakeRecord:
    """A single mistake entry.

    question_text is the user-confirmed/corrected text. ocr_text keeps the raw
    OCR transcription so later edits do not destroy the original evidence.
    """

    question_text: str
    book_id: str = ""
    user_answer: str = ""
    correct_answer: str = ""
    source: str = ""
    subject: str = ""
    chapter: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    mistake_type: list[str] = field(default_factory=list)
    difficulty: int = 3
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    image_path: Optional[str] = None
    notes: str = ""
    ocr_text: str = ""
    visual_ir: dict = field(default_factory=dict)
    explanation: str = ""
    linked_concepts: list[dict] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    sm2: dict = field(default_factory=dict)
    review_history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MistakeRecord":
        data = dict(data)
        if "question" in data and "question_text" not in data:
            data["question_text"] = data.pop("question")
        if data.get("chapter") == "":
            data["chapter"] = None
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class MistakeBookStore:
    """SQLite-backed mistake storage.

    The table keeps searchable columns plus a JSON blob. New record fields are
    backward-compatible because old rows are reconstructed through from_dict().
    """

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
                CREATE TABLE IF NOT EXISTS mistakes (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    next_review TEXT,
                    subject TEXT,
                    chapter TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_subject ON mistakes(subject)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_next_review ON mistakes(next_review)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chapter ON mistakes(chapter)")
            apply_sqlite_migrations(conn, component="mistake_book", current_version=1)
            conn.commit()

    def _prepare_retry_db_files(self) -> None:
        result = prepare_sqlite_retry_files(self.db_path)
        if result["preserved"]:
            print(
                f"[sqlite] preserved non-empty recovery files for {self.db_path}: "
                f"{', '.join(result['preserved'])}",
                flush=True,
            )

    def add(self, record: MistakeRecord) -> str:
        if not record.sm2:
            record.sm2 = {
                "easiness": 2.5,
                "interval": 1,
                "repetitions": 0,
                "next_review": date.today().isoformat(),
                "last_review": None,
            }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO mistakes (id, data, created_at, next_review, subject, chapter) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    json.dumps(record.to_dict(), ensure_ascii=False),
                    record.created_at,
                    record.sm2.get("next_review", date.today().isoformat()),
                    record.subject,
                    record.chapter,
                ),
            )
            conn.commit()
        return record.id

    def add_if_absent(self, record: MistakeRecord) -> str:
        """Insert a deterministic mistake record once and safely replay retries."""
        if not record.sm2:
            record.sm2 = {
                "easiness": 2.5,
                "interval": 1,
                "repetitions": 0,
                "next_review": date.today().isoformat(),
                "last_review": None,
            }
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data FROM mistakes WHERE id = ?", (record.id,)).fetchone()
            if row:
                existing = MistakeRecord.from_dict(json.loads(row[0]))
                if existing.question_text != record.question_text:
                    raise RuntimeError(f"mistake id collision: {record.id}")
                return existing.id
            conn.execute(
                "INSERT INTO mistakes (id, data, created_at, next_review, subject, chapter) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    json.dumps(record.to_dict(), ensure_ascii=False),
                    record.created_at,
                    record.sm2.get("next_review", date.today().isoformat()),
                    record.subject,
                    record.chapter,
                ),
            )
            return record.id

    def get(self, rid: str) -> Optional[MistakeRecord]:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM mistakes WHERE id = ?", (rid,)).fetchone()
        return MistakeRecord.from_dict(json.loads(row[0])) if row else None

    def update(self, record: MistakeRecord):
        with self._connect() as conn:
            conn.execute(
                "UPDATE mistakes SET data = ?, next_review = ?, subject = ?, chapter = ? WHERE id = ?",
                (
                    json.dumps(record.to_dict(), ensure_ascii=False),
                    record.sm2.get("next_review", date.today().isoformat()),
                    record.subject,
                    record.chapter,
                    record.id,
                ),
            )
            conn.commit()

    def delete(self, rid: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM mistakes WHERE id = ?", (rid,))
            conn.commit()

    def list_all(
        self,
        subject: Optional[str] = None,
        chapter: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 100,
    ) -> list[MistakeRecord]:
        sql = "SELECT data FROM mistakes WHERE 1=1"
        params: list[Any] = []
        if chapter:
            sql += " AND chapter = ?"
            params.append(chapter)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit if not subject and not tag else max(limit * 10, 1000))

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        records = [MistakeRecord.from_dict(json.loads(r[0])) for r in rows]
        if subject:
            records = [r for r in records if subject_matches(r.subject, subject)]
        if tag:
            records = [r for r in records if tag in r.tags]
        return records[:limit]

    def get_due(self, subject: Optional[str] = None) -> list[MistakeRecord]:
        today = date.today().isoformat()
        sql = "SELECT data FROM mistakes WHERE next_review <= ?"
        params: list[Any] = [today]
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        records = [MistakeRecord.from_dict(json.loads(r[0])) for r in rows]
        return [r for r in records if subject_matches(r.subject, subject)] if subject else records

    def get_stats(self, subject: Optional[str] = None) -> dict:
        sql = "SELECT data FROM mistakes WHERE 1=1"
        params: list[Any] = []
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        records = [MistakeRecord.from_dict(json.loads(r[0])) for r in rows]
        if subject:
            records = [r for r in records if subject_matches(r.subject, subject)]
        total = len(records)
        if total == 0:
            return {"total": 0, "due_today": 0, "by_type": {}, "by_tag": {}, "by_difficulty": {}}

        due_today = sum(1 for r in records if r.sm2.get("next_review", "9999-12-31") <= date.today().isoformat())
        by_type: dict[str, int] = {}
        by_tag: dict[str, int] = {}
        by_difficulty: dict[int, int] = {}
        for record in records:
            for item in record.mistake_type:
                by_type[item] = by_type.get(item, 0) + 1
            for tag in record.tags:
                by_tag[tag] = by_tag.get(tag, 0) + 1
            for concept in record.linked_concepts:
                name = str(concept.get("name", "")).strip()
                if name:
                    by_tag[name] = by_tag.get(name, 0) + 1
            by_difficulty[record.difficulty] = by_difficulty.get(record.difficulty, 0) + 1

        return {
            "total": total,
            "due_today": due_today,
            "by_type": by_type,
            "by_tag": by_tag,
            "by_difficulty": by_difficulty,
        }


class SM2Scheduler:
    def __init__(self, record: MistakeRecord):
        self.r = record
        if not self.r.sm2:
            self.r.sm2 = {
                "easiness": 2.5,
                "interval": 1,
                "repetitions": 0,
                "next_review": date.today().isoformat(),
                "last_review": None,
            }

    def review(self, quality: int) -> MistakeRecord:
        quality = max(0, min(5, int(quality)))
        state = self.r.sm2
        state["last_review"] = date.today().isoformat()

        if quality >= 3:
            if state["repetitions"] == 0:
                state["interval"] = 1
            elif state["repetitions"] == 1:
                state["interval"] = 6
            else:
                state["interval"] = int(round(state["interval"] * state["easiness"]))
            state["repetitions"] += 1
        else:
            state["repetitions"] = 0
            state["interval"] = 1

        state["easiness"] = max(
            1.3,
            state["easiness"] + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02),
        )
        state["next_review"] = (date.today() + timedelta(days=max(1, state["interval"]))).isoformat()
        self.r.review_history.append(
            {
                "date": state["last_review"],
                "quality": quality,
                "interval": state["interval"],
                "easiness": round(state["easiness"], 4),
                "next_review": state["next_review"],
            }
        )
        return self.r


ContextProvider = Callable[[MistakeRecord], str]


class MistakeBook:
    def __init__(self, db_path: str | Path, book_id: str = ""):
        self.store = MistakeBookStore(db_path)
        self.book_id = book_id

    def add(self, record: MistakeRecord) -> str:
        if self.book_id and not record.book_id:
            record.book_id = self.book_id
        return self.store.add(record)

    def add_if_absent(self, record: MistakeRecord) -> str:
        if self.book_id and not record.book_id:
            record.book_id = self.book_id
        return self.store.add_if_absent(record)

    def get(self, rid: str) -> Optional[MistakeRecord]:
        return self.store.get(rid)

    def update(self, record: MistakeRecord):
        self.store.update(record)

    def delete(self, rid: str):
        self.store.delete(rid)

    def list_all(self, **filters) -> list[MistakeRecord]:
        return self.store.list_all(**filters)

    def get_due(self, subject: Optional[str] = None) -> list[MistakeRecord]:
        return self.store.get_due(subject=subject)

    def review(self, rid: str, quality: int) -> MistakeRecord:
        record = self.store.get(rid)
        if not record:
            raise ValueError(f"Mistake not found: {rid}")
        updated = SM2Scheduler(record).review(quality)
        self.store.update(updated)
        return updated

    def get_stats(self, subject: Optional[str] = None) -> dict:
        return self.store.get_stats(subject=subject)

    def get_weak_points(self, subject: Optional[str] = None, top_n: int = 5) -> list[dict]:
        stats = self.store.get_stats(subject=subject)
        weak = []
        for tag, count in stats.get("by_tag", {}).items():
            weak.append({"type": "知识点", "name": tag, "count": count})
        for mistake_type, count in stats.get("by_type", {}).items():
            weak.append({"type": "错因", "name": mistake_type, "count": count})
        weak.sort(key=lambda x: x["count"], reverse=True)
        return weak[:top_n]

    def explain_prompt(self, record: MistakeRecord, context_provider: Optional[ContextProvider] = None) -> str:
        ctx = context_provider(record) if context_provider else ""
        ctx_block = f"""
## 相关教材内容
{ctx}
""" if ctx.strip() else ""

        return f"""请详细讲解以下错题，分析错因并给出正确解法。

## 题目
{record.question_text}

## 用户答案
{record.user_answer or '（未提供）'}

## 正确答案
{record.correct_answer or '（未提供，请自行推导）'}

## 用户标记错因
{', '.join(record.mistake_type) or '（未标记）'}

## 涉及知识点
{', '.join(record.tags) or '（未标注）'}
{ctx_block}
## 讲题要求
1. 先分析这道题考查的核心知识点。
2. 指出用户答案中的具体问题，尽量对照错因标签。
3. 给出完整正确的解题步骤，公式使用 LaTeX。
4. 总结类似题的通用解题套路和易错点。
5. 直接输出讲题内容，不要寒暄，不要输出 thinking。
"""

    def explain(
        self,
        rid: str,
        llm_invoke: Callable[[str], str],
        context_provider: Optional[ContextProvider] = None,
        persist: bool = True,
    ) -> str:
        record = self.store.get(rid)
        if not record:
            raise ValueError(f"Mistake not found: {rid}")
        result = llm_invoke(self.explain_prompt(record, context_provider))
        if persist:
            record.explanation = result
            self.store.update(record)
        return result


def _is_sqlite_storage_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return (
        "disk i/o" in message
        or "readonly" in message
        or "unable to open database file" in message
    )


def get_mistake_book(book_name: str = "default", data_dir: str = "./data/progress") -> MistakeBook:
    path = safe_child_path(data_dir, f"mistake_book_{safe_book_name(book_name)}.db")
    identity = BookRegistry(data_dir).resolve(book_name, include_archived=True)
    book_id = str(identity.get("book_id") or "") if identity else ""
    return MistakeBook(path, book_id=book_id)
