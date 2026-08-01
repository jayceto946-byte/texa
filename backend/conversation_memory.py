"""Lightweight chat conversation persistence and follow-up rewriting."""
from __future__ import annotations

import json
import re
import time
import threading
import uuid
from pathlib import Path

from config import PROGRESS_PATH
from utils.json_io import atomic_write_json
from utils.subject_catalog import normalize_subject_value, subject_matches

CONV_DIR = Path(PROGRESS_PATH) / "conversations"
_CONVERSATION_LOCKS = tuple(threading.RLock() for _ in range(64))


def _conversation_lock(conversation_id: str) -> threading.RLock:
    return _CONVERSATION_LOCKS[hash(conversation_id) % len(_CONVERSATION_LOCKS)]


def ensure_conversation_id(conversation_id: str = "") -> str:
    if conversation_id and re.match(r"^[\w\-.]{1,80}$", conversation_id):
        return conversation_id
    return f"conv_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


def _path(conversation_id: str) -> Path:
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    return CONV_DIR / f"{conversation_id}.json"


def _read_payload(conversation_id: str) -> dict:
    path = _path(conversation_id)
    if not path.exists():
        return {"id": conversation_id, "messages": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"id": conversation_id, "messages": []}
    except Exception:
        return {"id": conversation_id, "messages": []}


def load_history(conversation_id: str) -> list[dict]:
    return get_conversation(conversation_id).get("messages", [])


def resolve_conversation_id_for_scope(
    conversation_id: str,
    subject: str = "",
    book_name: str = "",
) -> str:
    """Keep one persisted conversation bound to one exact retrieval scope."""
    conversation_id = ensure_conversation_id(conversation_id)
    payload = _read_payload(conversation_id)
    messages = payload.get("messages", []) if isinstance(payload, dict) else []
    if not messages:
        return conversation_id

    stored_subject = normalize_subject_value(
        str(payload.get("subject") or _last_meta(messages, "subject"))
    )
    requested_subject = normalize_subject_value(subject)
    stored_book = str(payload.get("book_name") or _last_meta(messages, "book_name")).strip()
    requested_book = str(book_name or "").strip()
    if stored_subject == requested_subject and stored_book == requested_book:
        return conversation_id
    return ensure_conversation_id()


def ensure_turn_id(turn_id: str = "") -> str:
    if turn_id and re.match(r"^[\w\-.]{1,80}$", turn_id):
        return turn_id
    return f"turn_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


def ensure_message_id(message_id: str = "") -> str:
    if message_id and re.match(r"^[\w\-.]{1,80}$", message_id):
        return message_id
    return f"msg_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


def append_message(
    conversation_id: str,
    role: str,
    content: str,
    book_name: str = "",
    subject: str = "",
    *,
    turn_id: str = "",
    message_id: str = "",
) -> dict:
    subject = normalize_subject_value(subject)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _conversation_lock(conversation_id):
        payload = _read_payload(conversation_id)
        history = payload.get("messages", []) if isinstance(payload, dict) else []
        item = {
            "id": ensure_message_id(message_id),
            "turn_id": ensure_turn_id(turn_id),
            "role": role,
            "content": content,
            "book_name": book_name,
            "subject": subject,
            "created_at": now,
        }
        history.append(item)
        payload = {
            "id": conversation_id,
            "messages": history[-40:],
            "subject": subject or payload.get("subject", ""),
            "book_name": book_name or payload.get("book_name", ""),
            "created_at": payload.get("created_at") or now,
            "updated_at": now,
        }
        atomic_write_json(_path(conversation_id), payload)
        return item


def reclassify_conversation(conversation_id: str, subject: str, book_name: str = "") -> dict:
    """Relabel one conversation without touching learning events or RAG traces."""
    conversation_id = ensure_conversation_id(conversation_id)
    subject = normalize_subject_value(subject)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _conversation_lock(conversation_id):
        payload = _read_payload(conversation_id)
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        if not messages:
            raise ValueError("conversation not found or empty")
        previous = {
            "subject": str(payload.get("subject") or _last_meta(messages, "subject")),
            "book_name": str(payload.get("book_name") or _last_meta(messages, "book_name")),
        }
        relabeled = [
            {**item, "subject": subject, "book_name": book_name}
            for item in messages
            if isinstance(item, dict)
        ]
        history = list(payload.get("scope_history") or [])
        history.append({
            "mode": "reclassify",
            "from": previous,
            "to": {"subject": subject, "book_name": book_name},
            "created_at": now,
        })
        payload.update({
            "id": conversation_id,
            "messages": relabeled,
            "subject": subject,
            "book_name": book_name,
            "updated_at": now,
            "scope_history": history[-20:],
        })
        atomic_write_json(_path(conversation_id), payload)
    return get_conversation(conversation_id)


def split_turn_to_conversation(
    conversation_id: str,
    turn_id: str,
    subject: str,
    book_name: str = "",
) -> tuple[dict, dict]:
    """Move one identified turn into a new conversation under a corrected scope."""
    conversation_id = ensure_conversation_id(conversation_id)
    turn_id = ensure_turn_id(turn_id)
    subject = normalize_subject_value(subject)
    target_id = ensure_conversation_id()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    locks = sorted({_conversation_lock(conversation_id), _conversation_lock(target_id)}, key=id)
    for lock in locks:
        lock.acquire()
    target_written = False
    try:
        source = _read_payload(conversation_id)
        messages = source.get("messages", []) if isinstance(source, dict) else []
        moved = [item for item in messages if isinstance(item, dict) and item.get("turn_id") == turn_id]
        if not moved:
            raise ValueError("turn not found")
        remaining = [item for item in messages if item not in moved]
        moved = [{**item, "subject": subject, "book_name": book_name} for item in moved]
        target = {
            "id": target_id,
            "messages": moved,
            "subject": subject,
            "book_name": book_name,
            "created_at": moved[0].get("created_at") or now,
            "updated_at": now,
            "split_from": {"conversation_id": conversation_id, "turn_id": turn_id},
        }
        atomic_write_json(_path(target_id), target)
        target_written = True

        source["messages"] = remaining
        source["subject"] = _last_meta(remaining, "subject") or source.get("subject", "")
        source["book_name"] = _last_meta(remaining, "book_name") or source.get("book_name", "")
        source["updated_at"] = now
        split_history = list(source.get("scope_history") or [])
        split_history.append({
            "mode": "split_turn",
            "turn_id": turn_id,
            "target_conversation_id": target_id,
            "to": {"subject": subject, "book_name": book_name},
            "created_at": now,
        })
        source["scope_history"] = split_history[-20:]
        atomic_write_json(_path(conversation_id), source)
    except Exception:
        if target_written:
            _path(target_id).unlink(missing_ok=True)
        raise
    finally:
        for lock in reversed(locks):
            lock.release()
    return get_conversation(conversation_id), get_conversation(target_id)


def get_conversation(conversation_id: str) -> dict:
    payload = _read_payload(ensure_conversation_id(conversation_id))
    all_messages = payload.get("messages", []) if isinstance(payload, dict) else []
    subject = normalize_subject_value(payload.get("subject", "") or _last_meta(all_messages, "subject"))
    book_name = str(payload.get("book_name", "") or _last_meta(all_messages, "book_name")).strip()
    messages = _messages_for_scope(all_messages, subject, book_name)
    return {
        "id": payload.get("id") or conversation_id,
        "subject": subject,
        "book_name": book_name,
        "messages": messages,
        "created_at": payload.get("created_at") or _first_meta(messages, "created_at"),
        "updated_at": payload.get("updated_at") or _last_meta(messages, "created_at"),
        "title": _conversation_title(messages),
    }


def list_conversations(subject: str = "", book_name: str = "", limit: int = 80) -> list[dict]:
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    for path in CONV_DIR.glob("*.json"):
        conversation_id = path.stem
        item = get_conversation(conversation_id)
        if subject and not subject_matches(item.get("subject", ""), subject):
            continue
        if book_name and item.get("book_name") != book_name:
            continue
        if not item.get("messages"):
            continue
        items.append({
            "id": item["id"],
            "title": item["title"],
            "subject": item.get("subject", ""),
            "book_name": item.get("book_name", ""),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
            "message_count": len(item.get("messages", [])),
        })
    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return items[: max(1, min(limit, 200))]


def _conversation_title(messages: list[dict]) -> str:
    for item in messages:
        if item.get("role") == "user":
            content = re.sub(r"\s+", " ", str(item.get("content", "")).strip())
            return content[:36] or "新会话"
    return "新会话"


def _last_meta(messages: list[dict], key: str) -> str:
    for item in reversed(messages):
        value = str(item.get(key, "")).strip()
        if value:
            return value
    return ""


def _first_meta(messages: list[dict], key: str) -> str:
    for item in messages:
        value = str(item.get(key, "")).strip()
        if value:
            return value
    return ""


def _messages_for_scope(messages: list[dict], subject: str, book_name: str) -> list[dict]:
    """Hide turns written under another scope by legacy clients reusing one id."""
    scoped = [item for item in messages if isinstance(item, dict) and (item.get("subject") or item.get("book_name"))]
    if not scoped:
        return [item for item in messages if isinstance(item, dict)]
    return [
        item
        for item in scoped
        if normalize_subject_value(str(item.get("subject") or "")) == subject
        and str(item.get("book_name") or "").strip() == book_name
    ]


def rewrite_followup(question: str, history: list[dict], book_name: str = "", subject: str = "") -> str:
    """Turn an explicit anaphoric follow-up into a compact retrieval query."""
    question = question.strip()
    if not history or not _looks_like_followup(question):
        return question
    previous_user = next(
        (_strip_internal_references(str(item.get("content", ""))) for item in reversed(history) if item.get("role") == "user" and str(item.get("content", "")).strip()),
        "",
    )
    if not previous_user:
        return question
    scope = " / ".join(value for value in (subject.strip(), book_name.strip()) if value)
    prefix = f"[{scope}] " if scope else ""
    return f"{prefix}{previous_user[:500]}；{question}"


def _looks_like_followup(question: str) -> bool:
    compact = re.sub(r"\s+", "", question)
    markers = [
        "\u8fd9\u4e2a", "\u90a3\u4e2a", "\u4e0a\u9762", "\u521a\u624d", "\u524d\u9762", "\u7ee7\u7eed",
        "\u8fd9\u91cc", "\u5b83", "\u5176", "\u8fd9\u4e00\u6b65", "\u518d\u89e3\u91ca", "\u5c55\u5f00", "\u8ffd\u95ee",
    ]
    return any(marker in compact for marker in markers)


def _strip_internal_references(text: str) -> str:
    text = re.sub(r"\s*/\s*[a-f0-9]{12,64}(?=\s*\])", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()
