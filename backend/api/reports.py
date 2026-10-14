"""Weekly learning report API."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter

from config import PROGRESS_PATH
from memory.exercise_bank import get_exercise_bank
from memory.mistake_book import get_mistake_book
from backend.services.learning_reports import conversation_statistics, parse_activity_time
from utils.subject_catalog import subject_matches

router = APIRouter(prefix="/reports", tags=["reports"])


def _parse_dt(value: str) -> datetime | None:
    return parse_activity_time(value)


def _since_days(days: int) -> datetime:
    return datetime.now() - timedelta(days=days)


@router.get("/weekly")
def weekly_report(book_name: str = "default", subject: str = "", days: int = 7):
    days = max(1, min(days, 31))
    start = _since_days(days)
    book = book_name or "default"

    mistakes = get_mistake_book(book, str(PROGRESS_PATH)).list_all(subject=subject or None, limit=10000)
    week_mistakes = [m for m in mistakes if (_parse_dt(m.created_at) or datetime.min) >= start]
    reviewed_mistakes = []
    for m in mistakes:
        for item in m.review_history or []:
            t = _parse_dt(str(item.get("timestamp") or item.get("time") or item.get("date") or ""))
            if t and t >= start:
                reviewed_mistakes.append(m)
                break

    bank = get_exercise_bank(book, str(PROGRESS_PATH))
    exercises = bank.list_all(subject=subject or None, limit=10000)
    week_exercises = [e for e in exercises if (_parse_dt(e.created_at) or datetime.min) >= start]
    practiced = []
    for e in exercises:
        for item in e.practice_history or []:
            t = _parse_dt(str(item.get("timestamp") or item.get("time") or item.get("date") or ""))
            if t and t >= start:
                practiced.append(e)
                break

    conversations, qa_count = _conversation_stats(start, book, subject)
    concept_stats = _concept_stats(start, book, subject)

    weak_counter = Counter()
    for m in week_mistakes:
        for tag in m.tags:
            weak_counter[tag] += 1
        for concept in m.linked_concepts:
            name = str(concept.get("name", "")).strip()
            if name:
                weak_counter[name] += 1

    suggestions = []
    if reviewed_mistakes:
        suggestions.append(f"继续清理到期错题，本周已复习 {len(reviewed_mistakes)} 道。")
    elif mistakes:
        suggestions.append("错题复习记录偏少，优先处理待复习错题。")
    if concept_stats["top_concepts"]:
        suggestions.append(f"围绕 {concept_stats['top_concepts'][0]['name']} 做一次教材例题回看。")
    if week_exercises and not practiced:
        suggestions.append("本周导入了习题但练习记录较少，建议从新题中抽 5-10 道练习。")
    if not suggestions:
        suggestions.append("本周记录较少，先从一次教材问答或错题复盘开始积累数据。")

    return {
        "success": True,
        "data": {
            "book_name": book,
            "subject": subject,
            "range_days": days,
            "start_date": start.date().isoformat(),
            "end_date": datetime.now().date().isoformat(),
            "summary": {
                "qa_count": qa_count,
                "new_mistakes": len(week_mistakes),
                "reviewed_mistakes": len(reviewed_mistakes),
                "new_exercises": len(week_exercises),
                "practiced_exercises": len(practiced),
                "concept_exposures": concept_stats["exposure_count"],
            },
            "top_concepts": concept_stats["top_concepts"],
            "weak_points": [{"name": name, "count": count} for name, count in weak_counter.most_common(8)],
            "recent_questions": conversations[-10:],
            "suggestions": suggestions,
        },
    }


def _conversation_stats(start: datetime, book_name: str, subject: str) -> tuple[list[dict], int]:
    return conversation_statistics(start, book_name, subject)


def _concept_stats(start: datetime, book_name: str, subject: str = "") -> dict:
    path = Path(PROGRESS_PATH) / book_name / "concept_memory.json"
    if not path.exists():
        return {"exposure_count": 0, "top_concepts": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"exposure_count": 0, "top_concepts": []}
    counter = Counter()
    exposure_count = 0
    for item in data.get("exposures", []) or []:
        if subject and not subject_matches(item.get("subject", ""), subject):
            continue
        t = _parse_dt(str(item.get("timestamp", "")))
        if t and t >= start:
            name = str(item.get("concept", "")).strip()
            if name:
                counter[name] += 1
                exposure_count += 1
    return {"exposure_count": exposure_count, "top_concepts": [{"name": name, "count": count} for name, count in counter.most_common(10)]}
