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
from backend.services.goals.service import GOAL_CONTROL_LOCK

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


def _read_legacy_payload(conversation_id: str) -> dict:
    """Read a legacy JSON conversation only at the one-shot import boundary."""
    path = _path(conversation_id)
    if not path.exists():
        return {"id": conversation_id, "messages": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"legacy conversation JSON is invalid: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"legacy conversation JSON must contain an object: {path}")
    return data


def _event_db_path() -> Path:
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    return CONV_DIR / "_conversation_events.db"


def conversation_exists(conversation_id: str) -> bool:
    """Return whether the authoritative SQLite projection contains the conversation."""
    conversation_id = ensure_conversation_id(conversation_id)
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        row = conn.execute(
            "SELECT 1 FROM conversation_messages WHERE conversation_id = ? LIMIT 1",
            (conversation_id,),
        ).fetchone()
    return row is not None


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
    conn.execute(
        "CREATE TABLE IF NOT EXISTS conversation_ledgers ("
        "conversation_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, "
        "state_json TEXT NOT NULL, active_evidence_json TEXT NOT NULL, "
        "last_message_id TEXT NOT NULL DEFAULT '', last_seq INTEGER NOT NULL DEFAULT 0, "
        "updated_at TEXT NOT NULL)"
    )
    return conn


def latest_message_marker(conversation_id: str) -> tuple[int, str]:
    conversation_id = ensure_conversation_id(conversation_id)
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        row = conn.execute(
            "SELECT (SELECT COALESCE(MAX(event_id), 0) FROM conversation_events e "
            "WHERE e.conversation_id = conversation_messages.conversation_id) AS seq, message_id FROM conversation_messages "
            "WHERE conversation_id = ? ORDER BY conversation_messages.seq DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
    return (int(row["seq"]), str(row["message_id"] or "")) if row else (0, "")


def resolution_is_current(conversation_id: str, base_revision: int, message_id: str) -> bool:
    with _connect_events() as conn:
        rows = conn.execute(
            "SELECT event_type, message_id FROM conversation_events WHERE conversation_id = ? AND event_id > ?",
            (conversation_id, base_revision),
        ).fetchall()
    return len(rows) == 1 and rows[0]["event_type"] == "message_added" and rows[0]["message_id"] == message_id


def load_session_ledger_projection(conversation_id: str) -> dict | None:
    conversation_id = ensure_conversation_id(conversation_id)
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        row = conn.execute(
            "SELECT schema_version, state_json, active_evidence_json, "
            "last_message_id, last_seq, updated_at FROM conversation_ledgers "
            "WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
    if row is None:
        return None
    try:
        state = json.loads(str(row["state_json"]))
        active_evidence = json.loads(str(row["active_evidence_json"]))
    except (TypeError, json.JSONDecodeError):
        logger.exception("invalid SQLite session ledger projection: %s", conversation_id)
        return None
    if not isinstance(state, dict) or not isinstance(active_evidence, dict):
        logger.error("invalid SQLite session ledger shape: %s", conversation_id)
        return None
    return {
        "schema_version": int(row["schema_version"]),
        "conversation_id": conversation_id,
        "state": state,
        "active_evidence": active_evidence,
        "last_message_id": str(row["last_message_id"] or ""),
        "last_seq": int(row["last_seq"] or 0),
        "updated_at": str(row["updated_at"] or ""),
    }


def save_session_ledger_projection(conversation_id: str, value: dict) -> bool:
    conversation_id = ensure_conversation_id(conversation_id)
    with _connect_events() as conn:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_event_projection(conn, conversation_id)
        latest = conn.execute(
            "SELECT (SELECT COALESCE(MAX(event_id), 0) FROM conversation_events e "
            "WHERE e.conversation_id = conversation_messages.conversation_id) AS seq, message_id FROM conversation_messages "
            "WHERE conversation_id = ? ORDER BY conversation_messages.seq DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        if latest is None:
            return False
        if "last_seq" in value and int(value["last_seq"]) != int(latest["seq"]):
            return False
        if value.get("last_message_id") and value["last_message_id"] != latest["message_id"]:
            return False
        conn.execute(
            "INSERT INTO conversation_ledgers "
            "(conversation_id, schema_version, state_json, active_evidence_json, "
            "last_message_id, last_seq, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(conversation_id) DO UPDATE SET "
            "schema_version = excluded.schema_version, state_json = excluded.state_json, "
            "active_evidence_json = excluded.active_evidence_json, "
            "last_message_id = excluded.last_message_id, last_seq = excluded.last_seq, "
            "updated_at = excluded.updated_at",
            (
                conversation_id,
                int(value.get("schema_version") or 1),
                json.dumps(value.get("state") or {}, ensure_ascii=False),
                json.dumps(value.get("active_evidence") or {}, ensure_ascii=False),
                str(value.get("last_message_id") or latest["message_id"] or ""),
                int(latest["seq"]),
                time.strftime("%Y-%m-%dT%H:%M:%S"),
            ),
        )
    return True


def delete_session_ledger_projection(conversation_id: str) -> None:
    conversation_id = ensure_conversation_id(conversation_id)
    with _connect_events() as conn:
        conn.execute(
            "DELETE FROM conversation_ledgers WHERE conversation_id = ?",
            (conversation_id,),
        )


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
) -> None:
    imported = conn.execute(
        "SELECT 1 FROM conversation_imports WHERE conversation_id = ?", (conversation_id,),
    ).fetchone()
    if imported:
        return
    payload = _read_legacy_payload(conversation_id)
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


def _authoritative_scope(conn: sqlite3.Connection, conversation_id: str) -> tuple[str, str]:
    row = conn.execute(
        "SELECT subject, book_name FROM conversation_messages "
        "WHERE conversation_id = ? AND (subject != '' OR book_name != '') "
        "ORDER BY seq DESC LIMIT 1",
        (conversation_id,),
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT subject, book_name FROM conversation_messages "
            "WHERE conversation_id = ? ORDER BY seq DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
    if row is None:
        return "", ""
    return normalize_subject_value(str(row["subject"] or "")), str(row["book_name"] or "").strip()


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
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        subject, book_name = _authoritative_scope(conn, conversation_id)
        return _message_page_from_projection(
            conn, conversation_id, subject=subject, book_name=book_name,
            limit=limit, before_seq=before_seq,
        )


def load_full_history(conversation_id: str, *, limit: int = 5000) -> list[dict]:
    conversation_id = ensure_conversation_id(conversation_id)
    safe_limit = max(1, min(int(limit), 5000))
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        subject, book_name = _authoritative_scope(conn, conversation_id)
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
    placeholders = ",".join("?" for _ in requested)
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
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
    from backend.services.conversation_management import assert_conversation_writable
    with GOAL_CONTROL_LOCK:
        assert_conversation_writable(conversation_id)
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        exists = conn.execute(
            "SELECT 1 FROM conversation_messages WHERE conversation_id = ? LIMIT 1",
            (conversation_id,),
        ).fetchone()
        if not exists:
            return conversation_id
        stored_subject, stored_book = _authoritative_scope(conn, conversation_id)
    requested_subject = normalize_subject_value(subject)
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
    request_id: str = "",
    context_versions: dict | None = None,
    learning_task: dict | None = None,
    citation_provenance: dict | None = None,
) -> dict:
    subject = normalize_subject_value(subject)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with GOAL_CONTROL_LOCK, _conversation_lock(conversation_id):
        if role == "user":
            from backend.services.conversation_management import assert_conversation_writable
            assert_conversation_writable(conversation_id)
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
        if request_id:
            item["request_id"] = str(request_id)[:80]
        if isinstance(context_versions, dict) and context_versions:
            item["context_versions"] = {
                str(key)[:60]: value
                for key, value in context_versions.items()
                if isinstance(value, (str, int, float, bool))
            }
        if isinstance(learning_task, dict) and learning_task:
            item["learning_task"] = learning_task
        if isinstance(citation_provenance, dict) and citation_provenance:
            item["citation_provenance"] = {
                str(key)[:60]: value
                for key, value in citation_provenance.items()
                if isinstance(value, (str, int, float, bool, list))
            }
        with _connect_events() as conn:
            _ensure_event_projection(conn, conversation_id)
            existing_row = conn.execute(
                "SELECT message_id, payload_json FROM conversation_messages "
                "WHERE conversation_id = ? AND turn_id = ? AND role = ? ORDER BY seq LIMIT 1",
                (conversation_id, item["turn_id"], role),
            ).fetchone()
            if existing_row:
                existing = json.loads(str(existing_row["payload_json"]))
                can_complete_partial = (
                    role == "assistant"
                    and str(existing.get("delivery_status") or "complete") in {"partial", "error", "waiting"}
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
            projection = _conversation_snapshot(conn, conversation_id)
        _write_json_projection(_path(conversation_id), projection)
        return item


def _update_projected_message(
    conversation_id: str,
    message_id: str,
    *,
    updates: dict,
    event_type: str,
) -> bool:
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        row = conn.execute(
            "SELECT payload_json FROM conversation_messages "
            "WHERE conversation_id = ? AND message_id = ?",
            (conversation_id, message_id),
        ).fetchone()
        if not row:
            return False
        item = json.loads(str(row["payload_json"]))
        if all(item.get(key) == value for key, value in updates.items()):
            return True
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
        projection = _conversation_snapshot(conn, conversation_id)
    _write_json_projection(_path(conversation_id), projection)
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


def update_learning_task_projection(
    conversation_id: str,
    task_id: str,
    learning_task: dict,
    *,
    message_id: str = "",
) -> bool:
    """Refresh the latest assistant snapshot after an out-of-band task action."""
    if not conversation_id or not task_id or not isinstance(learning_task, dict):
        return False
    if message_id:
        with _conversation_lock(conversation_id):
            message = get_message(conversation_id, message_id)
            if not message or (message.get("learning_task") or {}).get("id") != task_id:
                return False
            return _update_projected_message(conversation_id, message_id, updates={"learning_task": learning_task},
                                             event_type="message_learning_task_updated")
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        row = conn.execute(
            "SELECT message_id FROM conversation_messages WHERE conversation_id=? AND role='assistant' "
            "AND json_extract(payload_json, '$.learning_task.id')=? ORDER BY seq DESC LIMIT 1",
            (conversation_id, task_id),
        ).fetchone()
    if row:
        with _conversation_lock(conversation_id):
            return _update_projected_message(conversation_id, str(row[0]),
                updates={"learning_task": learning_task}, event_type="message_learning_task_updated")
    return False


def get_message(conversation_id: str, message_id: str) -> dict | None:
    """Read one projected message without scanning the full conversation."""
    if not conversation_id or not message_id:
        return None
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        row = conn.execute(
            "SELECT payload_json FROM conversation_messages "
            "WHERE conversation_id = ? AND message_id = ?",
            (conversation_id, message_id),
        ).fetchone()
    if not row:
        return None
    try:
        item = json.loads(str(row["payload_json"]))
    except (TypeError, json.JSONDecodeError):
        return None
    return item if isinstance(item, dict) else None


def update_message_answer_feedback(
    conversation_id: str,
    message_id: str,
    feedback: dict,
) -> bool:
    """Persist a bounded feedback snapshot for conversation history reloads."""
    if not message_id or not isinstance(feedback, dict):
        return False
    snapshot = {
        "rating": str(feedback.get("rating") or "")[:20],
        "reasons": [str(value)[:60] for value in (feedback.get("reasons") or [])[:5]],
        "updated_at": str(feedback.get("updated_at") or "")[:40],
    }
    with _conversation_lock(conversation_id):
        return _update_projected_message(
            conversation_id,
            message_id,
            updates={"answer_feedback": snapshot},
            event_type="message_answer_feedback_updated",
        )


def _conversation_snapshot(
    conn: sqlite3.Connection,
    conversation_id: str,
    *,
    limit: int = RECENT_MESSAGE_LIMIT,
    before_seq: int | None = None,
) -> dict:
    subject, book_name = _authoritative_scope(conn, conversation_id)
    page = _message_page_from_projection(
        conn,
        conversation_id,
        subject=subject,
        book_name=book_name,
        limit=limit,
        before_seq=before_seq,
    )
    scope_sql, scope_params = _projection_scope_clause(
        conn, conversation_id, subject, book_name,
    )
    metadata = conn.execute(
        "SELECT MIN(NULLIF(created_at, '')) AS created_at, "
        "MAX(NULLIF(created_at, '')) AS updated_at "
        "FROM conversation_messages WHERE conversation_id = ?" + scope_sql,
        (conversation_id, *scope_params),
    ).fetchone()
    first_user = conn.execute(
        "SELECT payload_json FROM conversation_messages "
        "WHERE conversation_id = ? AND role = 'user'" + scope_sql + " ORDER BY seq LIMIT 1",
        (conversation_id, *scope_params),
    ).fetchone()
    title_messages = [json.loads(str(first_user["payload_json"]))] if first_user else page["messages"]
    return {
        "id": conversation_id,
        "subject": subject,
        "book_name": book_name,
        "messages": page["messages"],
        "created_at": str((metadata or {})["created_at"] or "") if metadata else "",
        "updated_at": str((metadata or {})["updated_at"] or "") if metadata else "",
        "title": _conversation_title(title_messages),
        "message_count": page["total"],
        "page": {
            "has_more": page["has_more"],
            "next_before_seq": page["next_before_seq"],
            "limit": page["limit"],
            "total": page["total"],
        },
    }
def reclassify_conversation(conversation_id: str, subject: str, book_name: str = "") -> dict:
    """Relabel one conversation without touching learning events or RAG traces."""
    conversation_id = ensure_conversation_id(conversation_id)
    subject = normalize_subject_value(subject)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _conversation_lock(conversation_id):
        with _connect_events() as conn:
            _ensure_event_projection(conn, conversation_id)
            rows = conn.execute(
                "SELECT message_id, payload_json FROM conversation_messages "
                "WHERE conversation_id = ? ORDER BY seq",
                (conversation_id,),
            ).fetchall()
            messages = [json.loads(str(row["payload_json"])) for row in rows]
            if not messages:
                raise ValueError("conversation not found or empty")
            previous_subject, previous_book = _authoritative_scope(conn, conversation_id)
            previous = {"subject": previous_subject, "book_name": previous_book}
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
            projection = _conversation_snapshot(conn, conversation_id)
        _write_json_projection(_path(conversation_id), projection)
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
        with _connect_events() as conn:
            _ensure_event_projection(conn, conversation_id)
            _ensure_event_projection(conn, target_id)
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
            source_projection = _conversation_snapshot(conn, conversation_id)
            target_projection = _conversation_snapshot(conn, target_id)
        target_written = _write_json_projection(_path(target_id), target_projection)
        _write_json_projection(_path(conversation_id), source_projection)
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
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        return _conversation_snapshot(
            conn, conversation_id, limit=limit, before_seq=before_seq,
        )


def conversation_catalog(subject: str = "", book_name: str = "", book_names: list[str] | None = None) -> list[dict]:
    """Complete summary catalog, without loading every conversation's message window."""
    CONV_DIR.mkdir(parents=True, exist_ok=True)
    with _connect_events() as conn:
        for path in CONV_DIR.glob("*.json"):
            _ensure_event_projection(conn, path.stem)
        items = []
        for row in conn.execute("SELECT conversation_id,MIN(created_at),MAX(created_at),COUNT(*) FROM conversation_messages GROUP BY conversation_id"):
            cid = row[0]
            stored_subject, stored_book = _authoritative_scope(conn, cid)
            if subject and not subject_matches(stored_subject, subject):
                continue
            if book_name and stored_book != book_name:
                continue
            if book_names and stored_book not in book_names:
                continue
            scope_sql, scope_params = _projection_scope_clause(conn, cid, stored_subject, stored_book)
            values = (cid, *scope_params)
            metadata = conn.execute("SELECT MIN(created_at),MAX(created_at),COUNT(*) FROM conversation_messages WHERE conversation_id=?" + scope_sql, values).fetchone()
            first = conn.execute("SELECT payload_json FROM conversation_messages WHERE conversation_id=? AND role='user'" + scope_sql + " ORDER BY seq LIMIT 1", values).fetchone()
            items.append({"id": cid, "title": _conversation_title([json.loads(first[0])] if first else []),
                          "subject": stored_subject, "book_name": stored_book,
                          "created_at": metadata[0] or "", "updated_at": metadata[1] or "", "message_count": metadata[2]})
    return items


def list_conversations(subject: str = "", book_name: str = "", limit: int = 80) -> list[dict]:
    from backend.services.conversation_management import ConversationManagementService
    return ConversationManagementService().page(subject=subject, book_name=book_name, limit=limit)["items"]


def _conversation_title(messages: list[dict]) -> str:
    for item in messages:
        if item.get("role") == "user":
            content = re.sub(r"\s+", " ", str(item.get("content", "")).strip())
            return content[:36] or "新会话"
    return "新会话"


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


def capture_note_selection(conversation_id: str, *, turn_ids: list[str] | None = None,
                           through_seq: int | None = None, max_bytes: int = 8 * 1024 * 1024) -> dict:
    """Materialize a bounded selection in ONE SQLite snapshot, never the JSON window.

    Initial legacy import is committed before the read transaction. All pages,
    scope and watermark below see the same database version.
    """
    from memory.session_notes import NoteError, fingerprint, now
    if not isinstance(conversation_id, str) or not re.fullmatch(r"[\w.-]{1,80}", conversation_id) or conversation_id in {".", ".."}:
        raise NoteError("invalid_selection", "会话编号无效", 400)
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        conn.commit()
        conn.execute("BEGIN")
        last = conn.execute("SELECT MAX(seq) FROM conversation_messages WHERE conversation_id=?", (conversation_id,)).fetchone()[0]
        if last is None:
            raise NoteError("not_found", "会话不存在或没有消息", 404)
        cutoff = int(last) if through_seq is None else through_seq
        if type(cutoff) is not int or cutoff < 1 or cutoff > last:
            raise NoteError("invalid_selection", "截止范围无效", 400)
        # A cutoff may only end a complete turn, never half a question/answer.
        if conn.execute("SELECT 1 FROM conversation_messages a JOIN conversation_messages b ON a.conversation_id=b.conversation_id AND a.turn_id=b.turn_id WHERE a.conversation_id=? AND a.seq<=? AND b.seq>? LIMIT 1", (conversation_id, cutoff, cutoff)).fetchone():
            raise NoteError("invalid_selection", "必须选择完整轮次", 400)
        subject, book_name = _authoritative_scope(conn, conversation_id)
        scope_sql, _ = _projection_scope_clause(conn, conversation_id, subject, book_name)
        watermark = conn.execute("SELECT COALESCE(MAX(event_id),0) FROM conversation_events WHERE conversation_id=?", (conversation_id,)).fetchone()[0]
        requested = set(turn_ids) if turn_ids is not None else None
        if requested is not None and (not requested or len(requested) != len(turn_ids) or any(not isinstance(t, str) for t in requested)):
            raise NoteError("invalid_selection", "轮次选择为空或重复", 400)
        messages, excluded, found, selected_turns = [], [], set(), []
        after, size = 0, 0
        while True:
            rows = conn.execute("SELECT * FROM conversation_messages WHERE conversation_id=? AND seq>? AND seq<=? ORDER BY seq LIMIT 200", (conversation_id, after, cutoff)).fetchall()
            if not rows:
                break
            for row in rows:
                after = row["seq"]
                if requested is not None and row["turn_id"] not in requested:
                    continue
                if row["turn_id"] not in found:
                    selected_turns.append(row["turn_id"])
                found.add(row["turn_id"])
                item = json.loads(row["payload_json"])
                if scope_sql and (normalize_subject_value(row["subject"]) != subject or row["book_name"] != book_name):
                    excluded.append({"message_id": row["message_id"], "turn_id": row["turn_id"], "reason": "outside_current_scope"})
                else:
                    # Only answer-relevant persisted fields; diagnostic metadata is not source content.
                    fields = ("id", "turn_id", "role", "content", "created_at", "subject", "book_name", "sources", "answer_mode", "delivery_status", "evidence_support_status", "learning_task", "citation_provenance")
                    item = {key: item[key] for key in fields if key in item}
                    item["seq"] = row["seq"]
                    size += len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
                    messages.append(item)
                if size + len(json.dumps(excluded).encode()) > max_bytes:
                    raise NoteError("needs_range_selection", "来源超过 8 MiB，请选择较小的完整轮次范围")
        if requested is not None and requested != found:
            raise NoteError("invalid_selection", "选区包含不存在的轮次", 400)
        if not messages:
            raise NoteError("no_learning_content", "当前范围没有可整理的消息")
        return {"conversation_id": conversation_id, "title_snapshot": _conversation_title(messages),
                "subject": subject, "book_name": book_name, "captured_at": now(), "watermark": watermark,
                # Retain excluded turns too: replaying this selection must produce
                # the same exclusion manifest and preflight fingerprint.
                "selection": {"conversation_id": conversation_id, "turn_ids": selected_turns, "through_seq": cutoff},
                "messages": messages, "excluded": excluded,
                "input_hash": fingerprint({"messages": messages, "excluded": excluded, "subject": subject, "book_name": book_name})}


def resolve_message_context(conversation_id: str, message_id: str, *, radius: int = 10) -> dict:
    """Resolve only recorded turn moves, with a bounded chain and exact message ID."""
    from memory.session_notes import NoteError
    if not re.fullmatch(r"[\w.-]{1,80}", conversation_id) or conversation_id in {".", ".."} or not re.fullmatch(r"[\w.-]{1,100}", message_id):
        raise NoteError("invalid_selection", "消息定位无效", 400)
    original, visited = conversation_id, set()
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        conn.commit()
        conn.execute("BEGIN")
        for _ in range(8):
            if conversation_id in visited:
                break
            visited.add(conversation_id)
            row = conn.execute("SELECT * FROM conversation_messages WHERE conversation_id=? AND message_id=?", (conversation_id, message_id)).fetchone()
            if row:
                r = max(1, min(radius, 30))
                rows = conn.execute("SELECT seq,payload_json FROM conversation_messages WHERE conversation_id=? AND seq BETWEEN ? AND ? ORDER BY seq", (conversation_id, row["seq"]-r, row["seq"]+r)).fetchall()
                low, high = rows[0]["seq"], rows[-1]["seq"]
                total = conn.execute("SELECT COUNT(*) FROM conversation_messages WHERE conversation_id=?", (conversation_id,)).fetchone()[0]
                return {"conversation_id": conversation_id, "status": "moved" if conversation_id != original else "current", "target": json.loads(row["payload_json"]), "messages": [json.loads(x["payload_json"]) for x in rows], "subject": row["subject"], "book_name": row["book_name"], "page": {"total": total, "has_more": bool(conn.execute("SELECT 1 FROM conversation_messages WHERE conversation_id=? AND seq<? LIMIT 1", (conversation_id, low)).fetchone()), "next_before_seq": low, "next_after_seq": high}}
            moves = conn.execute("SELECT payload_json FROM conversation_events WHERE conversation_id=? AND event_type='turn_split_out' ORDER BY event_id DESC", (conversation_id,)).fetchall()
            target = next((p.get("target_conversation_id") for p in (json.loads(x[0]) for x in moves) if message_id in p.get("message_ids", [])), None)
            if not target:
                break
            conversation_id = target
    return {"conversation_id": original, "status": "unavailable", "target": None, "messages": []}


def load_message_page_after(conversation_id: str, after_seq: int, *, limit: int = 40) -> dict:
    """Forward pagination for an exact historical message window."""
    from memory.session_notes import NoteError
    if not re.fullmatch(r"[\w.-]{1,80}", conversation_id) or conversation_id in {".", ".."}:
        raise NoteError("invalid_selection", "会话编号无效", 400)
    size = max(1, min(limit, 200))
    with _connect_events() as conn:
        rows = conn.execute("SELECT seq,payload_json FROM conversation_messages WHERE conversation_id=? AND seq>? ORDER BY seq LIMIT ?", (conversation_id, after_seq, size+1)).fetchall()
        selected = rows[:size]
        return {"messages": [json.loads(row["payload_json"]) for row in selected], "has_more": len(rows)>size, "next_after_seq": selected[-1]["seq"] if selected else None}


def list_note_turns(conversation_id: str, *, before_seq: int | None = None, limit: int = 40) -> dict:
    """A paged range picker which remains available even when a full note is over budget."""
    from memory.session_notes import NoteError
    if not re.fullmatch(r"[\w.-]{1,80}", conversation_id) or conversation_id in {".", ".."}:
        raise NoteError("invalid_selection", "会话编号无效", 400)
    size = max(1, min(limit, 100))
    with _connect_events() as conn:
        _ensure_event_projection(conn, conversation_id)
        conn.commit()
        conn.execute("BEGIN")
        subject, book = _authoritative_scope(conn, conversation_id)
        scope_sql, scope_params = _projection_scope_clause(conn, conversation_id, subject, book)
        rows = conn.execute(
            "SELECT turn_id, MIN(seq) first_seq, MAX(seq) last_seq, COUNT(*) message_count, "
            "MAX(CASE WHEN role='user' THEN substr(json_extract(payload_json,'$.content'),1,100) ELSE '' END) label "
            "FROM conversation_messages WHERE conversation_id=?" + scope_sql +
            " GROUP BY turn_id HAVING MAX(seq)<? ORDER BY MAX(seq) DESC LIMIT ?",
            (conversation_id, *scope_params, before_seq or 2**63-1, size+1),
        ).fetchall()
        return {"items": [dict(row) for row in rows[:size]], "next_cursor": rows[size-1]["last_seq"] if len(rows)>size else None}
