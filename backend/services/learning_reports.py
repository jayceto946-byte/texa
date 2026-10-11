"""Bounded aggregation of recorded study activity for learning reports."""
from __future__ import annotations

from datetime import datetime

from utils.subject_catalog import subject_matches


def parse_activity_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def conversation_statistics(start: datetime, book_name: str, subject: str) -> tuple[list[dict], int]:
    """Count authoritative messages, retaining only ten display snippets.

    The catalog imports legacy projections through the existing storage adapter;
    forward cursor pages include SQLite-only sessions and all recorded history.
    """
    from backend.conversation_memory import conversation_catalog, load_message_page_after

    questions: list[dict] = []
    count = 0
    for conversation in conversation_catalog():
        cursor = 0
        while True:
            page = load_message_page_after(conversation["id"], cursor, limit=200)
            for message in page["messages"]:
                if message.get("role") != "user":
                    continue
                timestamp = parse_activity_time(str(message.get("created_at", "")))
                if timestamp is None or timestamp < start:
                    continue
                if book_name not in {"", "default"} and message.get("book_name") != book_name:
                    continue
                if subject and not subject_matches(message.get("subject", ""), subject):
                    continue
                count += 1
                questions.append({"time": timestamp.isoformat(timespec="minutes"), "question": str(message.get("content", ""))[:160]})
                questions.sort(key=lambda item: item["time"])
                questions = questions[-10:]
            if not page["has_more"]:
                break
            cursor = page["next_after_seq"]
    return questions, count
