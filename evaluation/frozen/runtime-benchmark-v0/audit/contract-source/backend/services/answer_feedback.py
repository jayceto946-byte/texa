"""Local answer-quality feedback bound to persisted assistant messages."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from config import PROGRESS_PATH


ANSWER_FEEDBACK_DB_PATH = Path(PROGRESS_PATH) / "answer_feedback.db"
ANSWER_FEEDBACK_SCHEMA_VERSION = 1
ALLOWED_REASONS = {
    "wrong_object",
    "forgot_context",
    "stale_evidence",
    "insufficient_evidence",
    "irrelevant_or_repetitive",
}


def _connect() -> sqlite3.Connection:
    ANSWER_FEEDBACK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ANSWER_FEEDBACK_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS answer_feedback ("
        "feedback_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
        "message_id TEXT NOT NULL, turn_id TEXT NOT NULL DEFAULT '', "
        "request_id TEXT NOT NULL DEFAULT '', rating TEXT NOT NULL, "
        "reasons_json TEXT NOT NULL DEFAULT '[]', note TEXT NOT NULL DEFAULT '', "
        "subject TEXT NOT NULL DEFAULT '', book_name TEXT NOT NULL DEFAULT '', "
        "versions_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL, UNIQUE(conversation_id, message_id))"
    )
    conn.execute("PRAGMA user_version = 1")
    return conn


def _validate(rating: str, reasons: list[str] | None, note: str) -> tuple[str, list[str], str]:
    normalized_rating = str(rating or "").strip().lower()
    if normalized_rating not in {"helpful", "unhelpful"}:
        raise ValueError("rating must be helpful or unhelpful")
    normalized_reasons = list(dict.fromkeys(
        str(value or "").strip() for value in (reasons or []) if str(value or "").strip()
    ))
    unknown = [value for value in normalized_reasons if value not in ALLOWED_REASONS]
    if unknown:
        raise ValueError(f"unsupported feedback reasons: {unknown}")
    if normalized_rating == "helpful":
        normalized_reasons = []
    return normalized_rating, normalized_reasons[:5], str(note or "").strip()[:1000]


def record_answer_feedback(
    *,
    conversation_id: str,
    message_id: str,
    rating: str,
    reasons: list[str] | None = None,
    note: str = "",
) -> dict[str, Any]:
    from backend.conversation_memory import get_message, update_message_answer_feedback

    message = get_message(conversation_id, message_id)
    if not message or message.get("role") != "assistant":
        raise ValueError("assistant message not found")
    rating, reasons, note = _validate(rating, reasons, note)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    feedback_id = f"feedback_{uuid.uuid4().hex}"
    versions = message.get("context_versions") if isinstance(message.get("context_versions"), dict) else {}
    with _connect() as conn:
        existing = conn.execute(
            "SELECT feedback_id, created_at FROM answer_feedback "
            "WHERE conversation_id = ? AND message_id = ?",
            (conversation_id, message_id),
        ).fetchone()
        if existing:
            feedback_id = str(existing["feedback_id"])
            created_at = str(existing["created_at"])
        else:
            created_at = now
        conn.execute(
            "INSERT INTO answer_feedback "
            "(feedback_id, conversation_id, message_id, turn_id, request_id, rating, "
            "reasons_json, note, subject, book_name, versions_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(conversation_id, message_id) DO UPDATE SET "
            "rating=excluded.rating, reasons_json=excluded.reasons_json, note=excluded.note, "
            "versions_json=excluded.versions_json, updated_at=excluded.updated_at",
            (
                feedback_id, conversation_id, message_id,
                str(message.get("turn_id") or "")[:100],
                str(message.get("request_id") or "")[:100], rating,
                json.dumps(reasons, ensure_ascii=False), note,
                str(message.get("subject") or "")[:100],
                str(message.get("book_name") or "")[:200],
                json.dumps(versions, ensure_ascii=False), created_at, now,
            ),
        )
    result = {
        "feedback_id": feedback_id,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "turn_id": str(message.get("turn_id") or ""),
        "request_id": str(message.get("request_id") or ""),
        "rating": rating,
        "reasons": reasons,
        "note": note,
        "versions": versions,
        "created_at": created_at,
        "updated_at": now,
    }
    result["projection_updated"] = update_message_answer_feedback(
        conversation_id, message_id, result,
    )
    return result


def list_answer_feedback(*, rating: str = "", limit: int = 500) -> list[dict[str, Any]]:
    if not ANSWER_FEEDBACK_DB_PATH.exists():
        return []
    params: list[Any] = []
    where = ""
    if rating:
        where = " WHERE rating = ?"
        params.append(rating)
    params.append(max(1, min(int(limit), 5000)))
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM answer_feedback" + where + " ORDER BY updated_at DESC LIMIT ?",
            params,
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["reasons"] = json.loads(item.pop("reasons_json") or "[]")
        item["versions"] = json.loads(item.pop("versions_json") or "{}")
        result.append(item)
    return result


def resolver_method_feedback_stats(*, limit: int = 500) -> dict[str, Any]:
    """Aggregate feedback proxies by resolver method; this is not calibrated accuracy."""
    from backend.rag_trace import get_trace_resolver_methods

    feedback = list_answer_feedback(limit=limit)
    methods = get_trace_resolver_methods([
        str(item.get("request_id") or "") for item in feedback
    ])
    buckets: dict[str, dict[str, Any]] = {}
    resolver_reasons = {"wrong_object", "forgot_context", "stale_evidence"}
    for item in feedback:
        request_id = str(item.get("request_id") or "")
        method = methods.get(request_id, "unknown")
        bucket = buckets.setdefault(method, {
            "method": method,
            "feedback_count": 0,
            "helpful_count": 0,
            "unhelpful_count": 0,
            "resolver_negative_count": 0,
        })
        bucket["feedback_count"] += 1
        rating = str(item.get("rating") or "")
        if rating == "helpful":
            bucket["helpful_count"] += 1
        elif rating == "unhelpful":
            bucket["unhelpful_count"] += 1
        reasons = set(item.get("reasons") or [])
        if reasons & resolver_reasons:
            bucket["resolver_negative_count"] += 1

    rows = []
    for bucket in buckets.values():
        count = int(bucket["feedback_count"])
        bucket["helpful_rate"] = bucket["helpful_count"] / count if count else 0.0
        bucket["resolver_negative_rate"] = (
            bucket["resolver_negative_count"] / count if count else 0.0
        )
        bucket["routing_decision_ready"] = count >= 30
        rows.append(bucket)
    rows.sort(key=lambda item: (-item["feedback_count"], item["method"]))
    return {
        "metric_kind": "user_feedback_proxy_not_calibrated_accuracy",
        "minimum_samples_for_routing_decision": 30,
        "matched_feedback_count": sum(
            item["feedback_count"] for item in rows if item["method"] != "unknown"
        ),
        "unmatched_feedback_count": next((
            item["feedback_count"] for item in rows if item["method"] == "unknown"
        ), 0),
        "methods": rows,
    }


def resolver_method_quality_report(*, limit: int = 500) -> dict[str, Any]:
    from backend.rag_trace import resolver_method_runtime_stats

    return {
        "runtime": resolver_method_runtime_stats(limit=limit),
        "feedback": resolver_method_feedback_stats(limit=limit),
        "decision_rule": (
            "Do not enable semantic routing from rule_strength. Require at least 30 "
            "feedback samples for the resolver method, then review resolver-negative "
            "examples before changing clarify/semantic routing."
        ),
    }
