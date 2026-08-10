"""Small, bounded request traces for diagnosing local RAG latency and ranking."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

from config import PROGRESS_PATH
from utils.sqlite_migrations import apply_sqlite_migrations

TRACE_DB_PATH = Path(PROGRESS_PATH) / "rag_traces.db"
MAX_TRACE_ROWS = 500
TRACE_SCHEMA_VERSION = 2


def _migrate_v2(conn: sqlite3.Connection) -> None:
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(rag_traces)")}
    if "context_json" not in columns:
        conn.execute("ALTER TABLE rag_traces ADD COLUMN context_json TEXT NOT NULL DEFAULT '{}'")


def _connect() -> sqlite3.Connection:
    TRACE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(TRACE_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS rag_traces (request_id TEXT PRIMARY KEY, created_at REAL NOT NULL, conversation_id TEXT, book_name TEXT, question TEXT, intent TEXT, fast_path INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, ttft_ms REAL, total_ms REAL, timings_json TEXT NOT NULL, evidence_json TEXT NOT NULL, error TEXT, context_json TEXT NOT NULL DEFAULT '{}')")
    apply_sqlite_migrations(
        conn,
        component="rag_trace",
        current_version=TRACE_SCHEMA_VERSION,
        migrations={2: _migrate_v2},
    )
    return conn


def new_request_id() -> str:
    return uuid.uuid4().hex


def _bounded_string_list(values, *, limit: int = 20, item_chars: int = 160) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()[:item_chars]
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _bounded_state(value: dict | None) -> dict:
    state = value if isinstance(value, dict) else {}
    frame = state.get("frame") if isinstance(state.get("frame"), dict) else {}
    return {
        "topic": str(state.get("topic") or "")[:200],
        "entities": _bounded_string_list(state.get("entities"), limit=12),
        "frame": {
            "kind": str(frame.get("kind") or "")[:40],
            "entities": _bounded_string_list(frame.get("entities"), limit=6),
            "goal": str(frame.get("goal") or "")[:200],
        } if frame else {},
        "constraints": _bounded_string_list(state.get("constraints"), limit=12),
        "intent": str(state.get("intent") or "")[:40],
        "last_resolved_query": str(state.get("last_resolved_query") or "")[:1000],
        "topic_stack": _bounded_string_list(state.get("topic_stack"), limit=20),
        "entity_record_count": len(state.get("entity_records") or []),
        "entity_group_count": len(state.get("entity_groups") or []),
        "assistant_artifact_count": len(state.get("assistant_artifacts") or []),
    }


def _sanitize_context_trace(value: dict | None) -> dict:
    """Persist diagnostics only: no prompt bodies, answers, or model thinking."""
    context = value if isinstance(value, dict) else {}
    resolution = context.get("resolution") if isinstance(context.get("resolution"), dict) else {}
    conversation = context.get("conversation_context") if isinstance(context.get("conversation_context"), dict) else {}
    retrieval = context.get("retrieval") if isinstance(context.get("retrieval"), dict) else {}
    budget = context.get("context_budget") if isinstance(context.get("context_budget"), dict) else {}
    numeric_budget = {
        str(key)[:80]: value
        for key, value in budget.items()
        if isinstance(value, (int, float, bool))
    }
    if budget.get("budget_unit"):
        numeric_budget["budget_unit"] = str(budget["budget_unit"])[:40]
    if budget.get("assembly_mode"):
        numeric_budget["assembly_mode"] = str(budget["assembly_mode"])[:80]
    return {
        "version": 2,
        "resolution": {
            "raw_query": str(resolution.get("raw_query") or "")[:1000],
            "resolved_query": str(resolution.get("resolved_query") or "")[:1000],
            "resolution_action": str(resolution.get("resolution_action") or "continue")[:40],
            "speech_act": str(resolution.get("speech_act") or "")[:40],
            "state_operations": [{
                "operation": str(item.get("operation") or "")[:60],
                **({"value": str(item.get("value") or "")[:200]} if "value" in item else {}),
                **({"old_value": str(item.get("old_value") or "")[:200]} if "old_value" in item else {}),
                **({"new_value": str(item.get("new_value") or "")[:200]} if "new_value" in item else {}),
            } for item in (resolution.get("state_operations") or [])[:12] if isinstance(item, dict)],
            "is_followup": bool(resolution.get("is_followup")),
            "resolution_changed": bool(resolution.get("resolution_changed")),
            "method": str(resolution.get("method") or "")[:80],
            "confidence": float(resolution.get("confidence") or 0.0),
            "confidence_kind": str(resolution.get("confidence_kind") or "")[:40],
            "referenced_entity": str(resolution.get("referenced_entity") or "")[:200],
            "referenced_entities": _bounded_string_list(resolution.get("referenced_entities"), limit=12),
            "referenced_turn_ids": _bounded_string_list(resolution.get("referenced_turn_ids"), limit=12, item_chars=100),
            "state_before": _bounded_state(resolution.get("state_before")),
            "state_after": _bounded_state(resolution.get("state_after")),
        },
        "conversation_context": {
            "budget": int(conversation.get("budget") or 0),
            "char_count": int(conversation.get("char_count") or 0),
            "state_chars": int(conversation.get("state_chars") or 0),
            "recent_turns_chars": int(conversation.get("recent_turns_chars") or 0),
            "current_topic": str(conversation.get("current_topic") or "")[:200],
            "question_dimension": str(conversation.get("question_dimension") or "")[:40],
            "speech_act": str(conversation.get("speech_act") or "")[:40],
            "constraints": _bounded_string_list(conversation.get("constraints"), limit=12),
            "turn_ids": _bounded_string_list(conversation.get("turn_ids"), limit=2, item_chars=100),
            "artifact_targets": _bounded_string_list(conversation.get("artifact_targets"), limit=4),
            "summary_used": bool(conversation.get("summary_used")),
            "evidence_action": str(conversation.get("evidence_action") or "")[:40],
            "reused_evidence_refs": _bounded_string_list(conversation.get("reused_evidence_refs"), limit=12, item_chars=20),
            "new_evidence_refs": _bounded_string_list(conversation.get("new_evidence_refs"), limit=12, item_chars=20),
            "dropped_turn_count": int(conversation.get("dropped_turn_count") or 0),
        },
        "retrieval": {
            "action": str(retrieval.get("action") or "")[:40],
            "query": str(retrieval.get("query") or "")[:1000],
            "reused_evidence_ids": _bounded_string_list(retrieval.get("reused_evidence_ids")),
            "new_evidence_ids": _bounded_string_list(retrieval.get("new_evidence_ids")),
            "dropped_evidence_ids": _bounded_string_list(retrieval.get("dropped_evidence_ids")),
            "support_status": str(retrieval.get("support_status") or "")[:40],
            "status": str(retrieval.get("status") or "")[:40],
            "error": str(retrieval.get("error") or "")[:500],
        },
        "context_budget": numeric_budget,
    }


def save_trace(trace: dict) -> None:
    evidence = [{
        "chunk_id": str(item.get("chunk_id") or ""),
        "chapter": str(item.get("chapter") or ""),
        "section_title": str(item.get("section_title") or ""),
        "source": str(item.get("source") or ""),
        "score": item.get("final_score", item.get("score")),
    } for item in (trace.get("evidence") or [])[:20]]
    context = _sanitize_context_trace(trace.get("context"))
    with _connect() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO rag_traces
            (request_id, created_at, conversation_id, book_name, question, intent,
             fast_path, status, ttft_ms, total_ms, timings_json, evidence_json,
             error, context_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trace["request_id"], trace.get("created_at", time.time()), trace.get("conversation_id", ""),
            trace.get("book_name", ""), str(trace.get("question") or "")[:1000], trace.get("intent", ""),
            int(bool(trace.get("fast_path"))), trace.get("status", "done"), trace.get("ttft_ms"),
            trace.get("total_ms"), json.dumps(trace.get("timings") or {}, ensure_ascii=False),
            json.dumps(evidence, ensure_ascii=False), str(trace.get("error") or "")[:2000],
            json.dumps(context, ensure_ascii=False),
        ))
        conn.execute("DELETE FROM rag_traces WHERE request_id IN (SELECT request_id FROM rag_traces ORDER BY created_at DESC LIMIT -1 OFFSET ?)", (MAX_TRACE_ROWS,))


def list_traces(limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit), 200))
    if not TRACE_DB_PATH.exists():
        return []
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM rag_traces ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["fast_path"] = bool(item["fast_path"])
        item["timings"] = json.loads(item.pop("timings_json") or "{}")
        item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
        item["context"] = json.loads(item.pop("context_json") or "{}")
        result.append(item)
    return result
