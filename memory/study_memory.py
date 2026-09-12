"""学习进度与记忆管理（含间隔重复集成）"""
import json
from contextlib import ExitStack
from functools import wraps
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from config import PROGRESS_PATH
from utils.json_io import atomic_write_json
from utils.path_safety import safe_book_name, safe_child_path
from utils.state_locks import get_state_lock


_STATE_AREAS = {
    "quiz": ("_quiz_lock", "quiz_file", "_quiz_history", list),
    "progress": ("_progress_lock", "progress_file", "_progress", dict),
    "weakness": ("_weakness_lock", "weakness_file", "_weakness", list),
    "chat": ("_chat_lock", "chat_file", "_chat_history", list),
}


def _with_fresh_memory(*areas: str):
    ordered = tuple(sorted(set(areas)))

    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            with ExitStack() as stack:
                for area in ordered:
                    lock_attr, _, _, _ = _STATE_AREAS[area]
                    stack.enter_context(getattr(self, lock_attr))
                for area in ordered:
                    _, path_attr, data_attr, factory = _STATE_AREAS[area]
                    setattr(self, data_attr, self._load_json(getattr(self, path_attr), factory()))
                return method(self, *args, **kwargs)
        return wrapped
    return decorate
from memory.spaced_repetition import SpacedRepetition


class StudyMemory:
    """管理用户学习进度、薄弱环节、历史记录和间隔重复"""

    def __init__(self, book_name: str = "default"):
        self.book_name = book_name
        self.base_path = safe_child_path(PROGRESS_PATH, safe_book_name(book_name))
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.quiz_file = self.base_path / "quiz_history.json"
        self.progress_file = self.base_path / "progress.json"
        self.weakness_file = self.base_path / "weakness.json"
        self.chat_file = self.base_path / "chat_history.json"

        self._quiz_lock = get_state_lock(self.quiz_file)
        self._progress_lock = get_state_lock(self.progress_file)
        self._weakness_lock = get_state_lock(self.weakness_file)
        self._chat_lock = get_state_lock(self.chat_file)
        self._quiz_history: list[dict] = []
        self._progress: dict = {}
        self._weakness: list[str] = []
        self._chat_history: list[dict] = []

        # 间隔重复
        self.sr = SpacedRepetition(book_name)

    def _load_json(self, path: Path, default):
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return default

    def _save_json(self, path: Path, data):
        # Keep the legacy payload shape for direct readers, but make replacement
        # crash-safe. Component versions live in data/storage_manifest.json.
        atomic_write_json(path, data)

    @_with_fresh_memory("progress")
    def mark_chapter_studied(self, chapter: str, *, operation_id: str = ""):
        previous = self._progress.get(chapter, {})
        operations = dict(previous.get("operations") or {})
        if operation_id and operation_id in operations:
            return
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        if operation_id:
            operations[operation_id] = today
        self._progress[chapter] = {
            **previous,
            "status": "studied",
            "last_review": today,
            "review_count": previous.get("review_count", 0) + 1,
            "operations": operations,
        }
        self._save_json(self.progress_file, self._progress)

    @_with_fresh_memory("progress")
    def get_chapter_progress(self, chapter: str) -> Optional[dict]:
        return self._progress.get(chapter)

    @_with_fresh_memory("progress")
    def get_all_progress(self) -> dict:
        return dict(self._progress)

    @_with_fresh_memory("quiz", "weakness")
    def add_quiz_record(self, chapter: str, question: str, answer: str,
                        correct: bool, user_answer: str = "",
                        knowledge_point: str = "", score: int = 0):
        record = {
            "chapter": chapter,
            "question": question,
            "correct_answer": answer,
            "user_answer": user_answer,
            "correct": correct,
            "score": score,
            "knowledge_point": knowledge_point,
            "timestamp": datetime.now().isoformat(),
        }
        self._quiz_history.append(record)
        self._save_json(self.quiz_file, self._quiz_history)

        if not correct:
            self._weakness.append(chapter)
            self._save_json(self.weakness_file, self._weakness)

        # 集成间隔重复
        if knowledge_point:
            self.sr.auto_review_from_quiz(chapter, knowledge_point, score)
        else:
            self.sr.auto_review_from_quiz(chapter, question[:30], score)

    @_with_fresh_memory("weakness")
    def get_weakness(self) -> list[str]:
        from collections import Counter
        weak_counter = Counter(self._weakness)
        return [ch for ch, _ in weak_counter.most_common()]

    @_with_fresh_memory("chat")
    def add_chat(self, role: str, content: str, chapter: str = ""):
        self._chat_history.append({
            "role": role,
            "content": content,
            "chapter": chapter,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self._chat_history) > 200:
            self._chat_history = self._chat_history[-200:]
        self._save_json(self.chat_file, self._chat_history)

    @_with_fresh_memory("chat")
    def get_chapter_chat(self, chapter: str, limit: int = 20) -> list[dict]:
        chats = [c for c in self._chat_history if c["chapter"] == chapter]
        return chats[-limit:]

    # ===== 间隔重复调度 =====

    def get_due_reviews(self) -> list[dict]:
        return self.sr.get_due_reviews()

    def get_chapter_due_reviews(self, chapter: str) -> list[dict]:
        return self.sr.get_chapter_due(chapter)

    def mark_review_done(self, card_id: str, quality: int):
        self.sr.review(card_id, quality)

    def add_knowledge_point(self, card_id: str, chapter: str, kp: str):
        self.sr.add_knowledge_point(card_id, chapter, kp)

    def get_sr_stats(self) -> dict:
        return self.sr.get_stats()

    def get_weekly_schedule(self) -> dict[str, int]:
        return self.sr.get_weekly_schedule()

    # ===== 统计 =====

    @_with_fresh_memory("progress", "quiz", "weakness")
    def get_stats(self) -> dict:
        total_quiz = len(self._quiz_history)
        correct_count = sum(1 for q in self._quiz_history if q["correct"])
        accuracy = correct_count / total_quiz * 100 if total_quiz > 0 else 0

        sr_stats = self.get_sr_stats()

        return {
            "chapters_studied": len(self._progress),
            "total_quiz": total_quiz,
            "accuracy": round(accuracy, 1),
            "weak_areas": len(self.get_weakness()),
            "streak": self._calculate_study_streak(),
            "sr_total": sr_stats["total"],
            "sr_due_today": sr_stats["due_today"],
            "sr_mastered": sr_stats["mastered"],
        }

    def _calculate_study_streak(self) -> int:
        if not self._progress:
            return 0
        dates = set()
        for info in self._progress.values():
            if "last_review" in info:
                dates.add(info["last_review"].split(" ")[0])

        from datetime import timedelta
        streak = 0
        today = date.today()
        for i in range(365):
            check = (today - timedelta(days=i)).isoformat()
            if check in dates:
                streak += 1
            else:
                break
        return streak
