"""Lightweight chat conversation persistence and follow-up rewriting."""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import threading
import uuid
from pathlib import Path

from config import PROGRESS_PATH
from utils.json_io import atomic_write_json
from utils.subject_catalog import normalize_subject_value, subject_matches

CONV_DIR = Path(PROGRESS_PATH) / "conversations"
RECENT_MESSAGE_LIMIT = 40
RESOLVER_HISTORY_LIMIT = 48
_CONVERSATION_LOCKS = tuple(threading.RLock() for _ in range(64))
logger = logging.getLogger(__name__)


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


def _event_db_path() -> Path:
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    return CONV_DIR / "_conversation_events.db"


def conversation_exists(conversation_id: str) -> bool:
    """Return whether either the compatibility JSON or durable projection exists."""
    if _path(conversation_id).exists():
        return True
    db_path = CONV_DIR / "_conversation_events.db"
    if not db_path.exists():
        return False
    try:
        with sqlite3.connect(str(db_path), timeout=2) as conn:
            row = conn.execute(
                "SELECT 1 FROM conversation_messages WHERE conversation_id = ? LIMIT 1",
                (conversation_id,),
            ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


def _connect_events() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_event_db_path()), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS conversation_events ("
        "event_id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, "
        "event_type TEXT NOT NULL, message_id TEXT NOT NULL DEFAULT '', "
        "payload_json TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_events_conversation "
        "ON conversation_events(conversation_id, event_id)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS conversation_messages ("
        "conversation_id TEXT NOT NULL, seq INTEGER NOT NULL, message_id TEXT NOT NULL, "
        "turn_id TEXT NOT NULL DEFAULT '', role TEXT NOT NULL, subject TEXT NOT NULL DEFAULT '', "
        "book_name TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT '', "
        "payload_json TEXT NOT NULL, PRIMARY KEY(conversation_id, message_id), "
        "UNIQUE(conversation_id, seq))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_messages_page "
        "ON conversation_messages(conversation_id, seq DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_messages_turn "
        "ON conversation_messages(conversation_id, turn_id, role)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS conversation_imports ("
        "conversation_id TEXT PRIMARY KEY, imported_at TEXT NOT NULL)"
    )
    return conn


def _write_json_projection(path: Path, payload: dict) -> bool:
    """Best-effort compatibility projection; SQLite is the canonical store."""
    try:
        atomic_write_json(path, payload)
        return True
    except OSError:
        logger.exception("conversation JSON projection write failed: %s", path)
        return False


def _append_event(
    conn: sqlite3.Connection,
    conversation_id: str,
    event_type: str,
    payload: dict,
    *,
    message_id: str = "",
    created_at: str = "",
) -> None:
    conn.execute(
        "INSERT INTO conversation_events "
        "(conversation_id, event_type, message_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            conversation_id,
            event_type,
            message_id,
            json.dumps(payload, ensure_ascii=False),
            created_at or time.strftime("%Y-%m-%dT%H:%M:%S"),
        ),
    )


def _insert_projection_message(
    conn: sqlite3.Connection,
    conversation_id: str,
    item: dict,
    *,
    seq: int,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO conversation_messages "
        "(conversation_id, seq, message_id, turn_id, role, subject, book_name, created_at, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            conversation_id,
            seq,
            str(item.get("id") or ""),
            str(item.get("turn_id") or ""),
            str(item.get("role") or "user"),
            normalize_subject_value(str(item.get("subject") or "")),
            str(item.get("book_name") or "").strip(),
            str(item.get("created_at") or ""),
            json.dumps(item, ensure_ascii=False),
        ),
    )


def _ensure_event_projection(
    conn: sqlite3.Connection,
    conversation_id: str,
    payload: dict,
) -> None:
    imported = conn.execute(
        "SELECT 1 FROM conversation_imports WHERE conversation_id = ?", (conversation_id,),
    ).fetchone()
    if imported:
        return
    existing = [item for item in payload.get("messages", []) if isinstance(item, dict)]
    seq = 0
    for raw_item in existing:
        item = dict(raw_item)
        item["id"] = ensure_message_id(str(item.get("id") or ""))
        item["turn_id"] = ensure_turn_id(str(item.get("turn_id") or ""))
        seq += 1
        _insert_projection_message(conn, conversation_id, item, seq=seq)
        _append_event(
            conn, conversation_id, "legacy_message_imported", item,
            message_id=item["id"], created_at=str(item.get("created_at") or ""),
        )
    conn.execute(
        "INSERT OR IGNORE INTO conversation_imports (conversation_id, imported_at) VALUES (?, ?)",
        (conversation_id, time.strftime("%Y-%m-%dT%H:%M:%S")),
    )


def _projection_scope_clause(
    conn: sqlite3.Connection,
    conversation_id: str,
    subject: str,
    book_name: str,
) -> tuple[str, list[str]]:
    scoped_count = int(conn.execute(
        "SELECT COUNT(*) FROM conversation_messages "
        "WHERE conversation_id = ? AND (subject != '' OR book_name != '')",
        (conversation_id,),
    ).fetchone()[0])
    if not scoped_count:
        return "", []
    return " AND subject = ? AND book_name = ?", [normalize_subject_value(subject), book_name.strip()]


def _message_page_from_projection(
    conn: sqlite3.Connection,
    conversation_id: str,
    *,
    subject: str,
    book_name: str,
    limit: int,
    before_seq: int | None = None,
    max_limit: int = 200,
) -> dict:
    safe_limit = max(1, min(int(limit), max_limit))
    scope_sql, scope_params = _projection_scope_clause(
        conn, conversation_id, subject, book_name,
    )
    before_sql = " AND seq < ?" if before_seq is not None else ""
    params: list = [conversation_id, *scope_params]
    if before_seq is not None:
        params.append(int(before_seq))
    rows = conn.execute(
        "SELECT seq, payload_json FROM conversation_messages WHERE conversation_id = ?"
        f"{scope_sql}{before_sql} ORDER BY seq DESC LIMIT ?",
        (*params, safe_limit + 1),
    ).fetchall()
    has_more = len(rows) > safe_limit
    selected = rows[:safe_limit]
    messages = [json.loads(str(row["payload_json"])) for row in reversed(selected)]
    total = int(conn.execute(
        "SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = ?" + scope_sql,
        (conversation_id, *scope_params),
    ).fetchone()[0])
    return {
        "messages": messages,
        "has_more": has_more,
        "next_before_seq": int(selected[-1]["seq"]) if has_more and selected else None,
        "total": total,
        "limit": safe_limit,
    }


def load_message_page(
    conversation_id: str,
    *,
    limit: int = RECENT_MESSAGE_LIMIT,
    before_seq: int | None = None,
) -> dict:
    conversation_id = ensure_conversation_id(conversation_id)
    payload = _read_payload(conversation_id)
    subject = normalize_subject_value(str(payload.get("subject") or ""))
    book_name = str(payload.get("book_name") or "").strip()
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id, payload)
        if not subject and not book_name:
            latest_scope = conn.execute(
                "SELECT subject, book_name FROM conversation_messages "
                "WHERE conversation_id = ? ORDER BY seq DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
            if latest_scope:
                subject = str(latest_scope["subject"] or "")
                book_name = str(latest_scope["book_name"] or "")
        return _message_page_from_projection(
            conn, conversation_id, subject=subject, book_name=book_name,
            limit=limit, before_seq=before_seq,
        )


def load_full_history(conversation_id: str, *, limit: int = 5000) -> list[dict]:
    conversation_id = ensure_conversation_id(conversation_id)
    payload = _read_payload(conversation_id)
    subject = normalize_subject_value(str(payload.get("subject") or ""))
    book_name = str(payload.get("book_name") or "").strip()
    safe_limit = max(1, min(int(limit), 5000))
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id, payload)
        if not subject and not book_name:
            latest_scope = conn.execute(
                "SELECT subject, book_name FROM conversation_messages "
                "WHERE conversation_id = ? ORDER BY seq DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
            if latest_scope:
                subject = str(latest_scope["subject"] or "")
                book_name = str(latest_scope["book_name"] or "")
        return _message_page_from_projection(
            conn, conversation_id, subject=subject, book_name=book_name,
            limit=safe_limit, max_limit=5000,
        )["messages"]


def load_history(conversation_id: str) -> list[dict]:
    return load_message_page(conversation_id, limit=RESOLVER_HISTORY_LIMIT)["messages"]


def load_turn_messages(
    conversation_id: str,
    turn_ids: list[str],
    *,
    max_turns: int = 2,
) -> list[dict]:
    """Load explicitly referenced turns without scanning or prompting with full history."""
    requested = list(dict.fromkeys(
        str(value).strip() for value in turn_ids if str(value).strip()
    ))[:max(0, min(int(max_turns), 4))]
    if not requested:
        return []
    conversation_id = ensure_conversation_id(conversation_id)
    payload = _read_payload(conversation_id)
    placeholders = ",".join("?" for _ in requested)
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id, payload)
        rows = conn.execute(
            "SELECT payload_json FROM conversation_messages "
            f"WHERE conversation_id = ? AND turn_id IN ({placeholders}) ORDER BY seq",
            (conversation_id, *requested),
        ).fetchall()
    return [json.loads(str(row["payload_json"])) for row in rows]


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
    sources: list | None = None,
    linked_concepts: list | None = None,
    answer_mode: str = "",
    scope_reason: str = "",
    suggested_answer_mode: str = "",
    evidence_support_status: str = "",
    delivery_status: str = "complete",
) -> dict:
    subject = normalize_subject_value(subject)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _conversation_lock(conversation_id):
        payload = _read_payload(conversation_id)
        item = {
            "id": ensure_message_id(message_id),
            "turn_id": ensure_turn_id(turn_id),
            "role": role,
            "content": content,
            "book_name": book_name,
            "subject": subject,
            "created_at": now,
        }
        if sources:
            item["sources"] = sources
        if linked_concepts:
            item["linked_concepts"] = linked_concepts
        if answer_mode:
            item["answer_mode"] = answer_mode
        if scope_reason:
            item["scope_reason"] = scope_reason
        if suggested_answer_mode:
            item["suggested_answer_mode"] = suggested_answer_mode
        if evidence_support_status:
            item["evidence_support_status"] = str(evidence_support_status)[:40]
        if delivery_status:
            item["delivery_status"] = str(delivery_status)[:20]
        with _connect_events() as conn:
            _ensure_event_projection(conn, conversation_id, payload)
            existing_row = conn.execute(
                "SELECT message_id, payload_json FROM conversation_messages "
                "WHERE conversation_id = ? AND turn_id = ? AND role = ? ORDER BY seq LIMIT 1",
                (conversation_id, item["turn_id"], role),
            ).fetchone()
            if existing_row:
                existing = json.loads(str(existing_row["payload_json"]))
                can_complete_partial = (
                    role == "assistant"
                    and str(existing.get("delivery_status") or "complete") in {"partial", "error"}
                    and delivery_status == "complete"
                )
                if can_complete_partial:
                    item["id"] = str(existing_row["message_id"])
                    item["created_at"] = str(existing.get("created_at") or now)
                    conn.execute(
                        "UPDATE conversation_messages SET subject = ?, book_name = ?, payload_json = ? "
                        "WHERE conversation_id = ? AND message_id = ?",
                        (
                            subject,
                            book_name,
                            json.dumps(item, ensure_ascii=False),
                            conversation_id,
                            item["id"],
                        ),
                    )
                    _append_event(
                        conn, conversation_id, "partial_message_completed", item,
                        message_id=item["id"], created_at=now,
                    )
                else:
                    item = existing
            else:
                next_seq = int(conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM conversation_messages WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()[0])
                _insert_projection_message(conn, conversation_id, item, seq=next_seq)
                _append_event(
                    conn, conversation_id, "message_added", item,
                    message_id=item["id"], created_at=now,
                )
            page = _message_page_from_projection(
                conn, conversation_id, subject=subject, book_name=book_name,
                limit=RECENT_MESSAGE_LIMIT,
            )
        payload = {
            **payload,
            "id": conversation_id,
            "messages": page["messages"],
            "message_count": page["total"],
            "subject": subject or payload.get("subject", ""),
            "book_name": book_name or payload.get("book_name", ""),
            "created_at": payload.get("created_at") or now,
            "updated_at": now,
        }
        if not payload.get("title") and role == "user":
            payload["title"] = _conversation_title([item])
        _write_json_projection(_path(conversation_id), payload)
        return item


def _update_projected_message(
    conversation_id: str,
    message_id: str,
    *,
    updates: dict,
    event_type: str,
) -> bool:
    payload = _read_payload(conversation_id)
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id, payload)
        row = conn.execute(
            "SELECT payload_json FROM conversation_messages "
            "WHERE conversation_id = ? AND message_id = ?",
            (conversation_id, message_id),
        ).fetchone()
        if not row:
            return False
        item = json.loads(str(row["payload_json"]))
        item.update(updates)
        conn.execute(
            "UPDATE conversation_messages SET turn_id = ?, role = ?, subject = ?, "
            "book_name = ?, created_at = ?, payload_json = ? "
            "WHERE conversation_id = ? AND message_id = ?",
            (
                str(item.get("turn_id") or ""),
                str(item.get("role") or "user"),
                normalize_subject_value(str(item.get("subject") or "")),
                str(item.get("book_name") or "").strip(),
                str(item.get("created_at") or ""),
                json.dumps(item, ensure_ascii=False),
                conversation_id,
                message_id,
            ),
        )
        _append_event(
            conn, conversation_id, event_type,
            {"message_id": message_id, "updates": updates}, message_id=message_id,
        )
        page = _message_page_from_projection(
            conn, conversation_id,
            subject=str(payload.get("subject") or ""),
            book_name=str(payload.get("book_name") or ""),
            limit=RECENT_MESSAGE_LIMIT,
        )
    payload["messages"] = page["messages"]
    payload["message_count"] = page["total"]
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write_json_projection(_path(conversation_id), payload)
    return True


def update_message_linked_concepts(
    conversation_id: str,
    message_id: str,
    linked_concepts: list | None,
) -> bool:
    """把概念标签快照挂到已持久化的 assistant 消息上（用于历史会话回读）。

    概念在流式回答的 done 阶段才计算完成，主消息已在 generate done 时写入；
    这里只做原位补写，不新增消息，不触发重新抽取。
    """
    if not message_id or not linked_concepts:
        return False
    with _conversation_lock(conversation_id):
        return _update_projected_message(
            conversation_id, message_id,
            updates={"linked_concepts": linked_concepts},
            event_type="message_concepts_updated",
        )


def update_message_evidence_support(
    conversation_id: str,
    message_id: str,
    status: str,
) -> bool:
    """Persist the final evidence-support status once graph completion is observed."""
    status = str(status or "").strip()[:40]
    if not message_id or not status:
        return False
    with _conversation_lock(conversation_id):
        return _update_projected_message(
            conversation_id, message_id,
            updates={"evidence_support_status": status},
            event_type="message_evidence_support_updated",
        )


def reclassify_conversation(conversation_id: str, subject: str, book_name: str = "") -> dict:
    """Relabel one conversation without touching learning events or RAG traces."""
    conversation_id = ensure_conversation_id(conversation_id)
    subject = normalize_subject_value(subject)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _conversation_lock(conversation_id):
        payload = _read_payload(conversation_id)
        with _connect_events() as conn:
            _ensure_event_projection(conn, conversation_id, payload)
            rows = conn.execute(
                "SELECT message_id, payload_json FROM conversation_messages "
                "WHERE conversation_id = ? ORDER BY seq",
                (conversation_id,),
            ).fetchall()
            messages = [json.loads(str(row["payload_json"])) for row in rows]
            if not messages:
                raise ValueError("conversation not found or empty")
            previous = {
                "subject": str(payload.get("subject") or _last_meta(messages, "subject")),
                "book_name": str(payload.get("book_name") or _last_meta(messages, "book_name")),
            }
            for row, item in zip(rows, messages):
                item.update({"subject": subject, "book_name": book_name})
                conn.execute(
                    "UPDATE conversation_messages SET subject = ?, book_name = ?, payload_json = ? "
                    "WHERE conversation_id = ? AND message_id = ?",
                    (subject, book_name, json.dumps(item, ensure_ascii=False), conversation_id, row["message_id"]),
                )
            _append_event(conn, conversation_id, "scope_reclassified", {
                "from": previous, "to": {"subject": subject, "book_name": book_name},
            }, created_at=now)
            page = _message_page_from_projection(
                conn, conversation_id, subject=subject, book_name=book_name,
                limit=RECENT_MESSAGE_LIMIT,
            )
        history = list(payload.get("scope_history") or [])
        history.append({
            "mode": "reclassify",
            "from": previous,
            "to": {"subject": subject, "book_name": book_name},
            "created_at": now,
        })
        payload.update({
            "id": conversation_id,
            "messages": page["messages"],
            "message_count": page["total"],
            "subject": subject,
            "book_name": book_name,
            "updated_at": now,
            "scope_history": history[-20:],
        })
        _write_json_projection(_path(conversation_id), payload)
        try:
            from backend.services.session_ledger import invalidate_session_ledger

            invalidate_session_ledger(conversation_id)
        except Exception:
            logger.exception("session ledger invalidation failed: %s", conversation_id)
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
        target_seed = {"id": target_id, "messages": [], "subject": subject, "book_name": book_name}
        with _connect_events() as conn:
            _ensure_event_projection(conn, conversation_id, source)
            _ensure_event_projection(conn, target_id, target_seed)
            moved_rows = conn.execute(
                "SELECT message_id, payload_json FROM conversation_messages "
                "WHERE conversation_id = ? AND turn_id = ? ORDER BY seq",
                (conversation_id, turn_id),
            ).fetchall()
            if not moved_rows:
                raise ValueError("turn not found")
            moved = []
            next_seq = int(conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM conversation_messages WHERE conversation_id = ?",
                (target_id,),
            ).fetchone()[0])
            for offset, row in enumerate(moved_rows):
                item = json.loads(str(row["payload_json"]))
                item.update({"subject": subject, "book_name": book_name})
                moved.append(item)
                conn.execute(
                    "DELETE FROM conversation_messages WHERE conversation_id = ? AND message_id = ?",
                    (conversation_id, row["message_id"]),
                )
                _insert_projection_message(conn, target_id, item, seq=next_seq + offset)
            _append_event(conn, conversation_id, "turn_split_out", {
                "turn_id": turn_id, "target_conversation_id": target_id,
                "message_ids": [item["id"] for item in moved],
            }, created_at=now)
            _append_event(conn, target_id, "turn_split_in", {
                "turn_id": turn_id, "source_conversation_id": conversation_id,
                "messages": moved,
            }, created_at=now)
            last_source = conn.execute(
                "SELECT subject, book_name FROM conversation_messages "
                "WHERE conversation_id = ? ORDER BY seq DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
            source_subject = str(last_source["subject"] or "") if last_source else str(source.get("subject") or "")
            source_book = str(last_source["book_name"] or "") if last_source else str(source.get("book_name") or "")
            source_page = _message_page_from_projection(
                conn, conversation_id, subject=source_subject, book_name=source_book,
                limit=RECENT_MESSAGE_LIMIT,
            )
            target_page = _message_page_from_projection(
                conn, target_id, subject=subject, book_name=book_name,
                limit=RECENT_MESSAGE_LIMIT,
            )
        target = {
            "id": target_id,
            "messages": target_page["messages"],
            "message_count": target_page["total"],
            "subject": subject,
            "book_name": book_name,
            "created_at": moved[0].get("created_at") or now,
            "updated_at": now,
            "split_from": {"conversation_id": conversation_id, "turn_id": turn_id},
        }
        target_written = _write_json_projection(_path(target_id), target)

        source["messages"] = source_page["messages"]
        source["message_count"] = source_page["total"]
        source["subject"] = source_subject
        source["book_name"] = source_book
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
        _write_json_projection(_path(conversation_id), source)
        try:
            from backend.services.session_ledger import invalidate_session_ledger

            invalidate_session_ledger(conversation_id)
            invalidate_session_ledger(target_id)
        except Exception:
            logger.exception(
                "session ledger invalidation failed after split: %s -> %s",
                conversation_id,
                target_id,
            )
    except Exception:
        if target_written:
            _path(target_id).unlink(missing_ok=True)
        raise
    finally:
        for lock in reversed(locks):
            lock.release()
    return get_conversation(conversation_id), get_conversation(target_id)


def get_conversation(
    conversation_id: str,
    *,
    limit: int = RECENT_MESSAGE_LIMIT,
    before_seq: int | None = None,
) -> dict:
    conversation_id = ensure_conversation_id(conversation_id)
    payload = _read_payload(conversation_id)
    recent = payload.get("messages", []) if isinstance(payload, dict) else []
    subject = normalize_subject_value(payload.get("subject", "") or _last_meta(recent, "subject"))
    book_name = str(payload.get("book_name", "") or _last_meta(recent, "book_name")).strip()
    page = load_message_page(conversation_id, limit=limit, before_seq=before_seq)
    messages = page["messages"]
    subject = normalize_subject_value(payload.get("subject", "") or _last_meta(messages, "subject"))
    book_name = str(payload.get("book_name", "") or _last_meta(messages, "book_name")).strip()
    title = str(payload.get("title") or "").strip()
    if not title:
        with _connect_events() as conn:
            scope_sql, scope_params = _projection_scope_clause(
                conn, conversation_id, subject, book_name,
            )
            first_user = conn.execute(
                "SELECT payload_json FROM conversation_messages "
                "WHERE conversation_id = ? AND role = 'user'" + scope_sql + " ORDER BY seq LIMIT 1",
                (conversation_id, *scope_params),
            ).fetchone()
        title = _conversation_title([
            json.loads(str(first_user["payload_json"]))
        ] if first_user else messages)
    return {
        "id": payload.get("id") or conversation_id,
        "subject": subject,
        "book_name": book_name,
        "messages": messages,
        "created_at": payload.get("created_at") or _first_meta(messages, "created_at"),
        "updated_at": payload.get("updated_at") or _last_meta(messages, "created_at"),
        "title": title,
        "message_count": page["total"],
        "page": {
            "has_more": page["has_more"],
            "next_before_seq": page["next_before_seq"],
            "limit": page["limit"],
            "total": page["total"],
        },
    }


def list_conversations(subject: str = "", book_name: str = "", limit: int = 80) -> list[dict]:
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    conversation_ids = {path.stem for path in CONV_DIR.glob("*.json")}
    db_path = CONV_DIR / "_conversation_events.db"
    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path), timeout=2) as conn:
                conversation_ids.update(
                    str(row[0]) for row in conn.execute(
                        "SELECT DISTINCT conversation_id FROM conversation_messages"
                    )
                )
        except sqlite3.Error:
            pass
    for conversation_id in conversation_ids:
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
            "message_count": int(item.get("message_count") or 0),
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


# ---------------------------------------------------------------------------
# Session 上下文追问解析（Conversation Resolver，结构化状态，毫秒级，无 LLM）
# ---------------------------------------------------------------------------
# 实现位于 services/session_context.py；conversation_memory 只保留兼容入口。

def rewrite_followup(question: str, history: list[dict], book_name: str = "", subject: str = "") -> str:
    """把追问交给结构化 Session Context 解析器。"""
    del book_name, subject  # scope 已由 conversation_id 隔离；参数仅为兼容旧调用。
    from backend.services.session_context import resolve_followup

    return resolve_followup(question, history)


def _strip_internal_references(text: str) -> str:
    text = re.sub(r"\s*/\s*[a-f0-9]{12,64}(?=\s*\])", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()
