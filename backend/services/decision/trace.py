"""Local, bounded routing diagnostics; existing historical tables remain readable."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from config import PROGRESS_PATH
from backend.services.decision.contracts import DecisionContext, DecisionResult

DEFAULT_ROUTING_DB_PATH = Path(PROGRESS_PATH) / "routing_traces.db"


class RoutingTraceStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise RuntimeError("routing trace schema is newer than supported")
            if version == 0:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute("CREATE TABLE routing_traces (id TEXT PRIMARY KEY, request_id TEXT NOT NULL, task_id TEXT, created_at TEXT NOT NULL, input_hash TEXT NOT NULL, application_json TEXT NOT NULL, decision_json TEXT NOT NULL)")
                    conn.execute("CREATE TABLE routing_outcomes (id TEXT PRIMARY KEY, trace_id TEXT NOT NULL REFERENCES routing_traces(id), created_at TEXT NOT NULL, outcome_json TEXT NOT NULL)")
                    conn.execute("PRAGMA user_version=1")
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
            if version < 2:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute("CREATE TABLE routing_reviews (id TEXT PRIMARY KEY, trace_id TEXT NOT NULL UNIQUE REFERENCES routing_traces(id), reviewer_id TEXT NOT NULL, expected_capability TEXT NOT NULL, holdout_group TEXT NOT NULL, split TEXT NOT NULL, created_at TEXT NOT NULL)")
                    conn.execute("PRAGMA user_version=2")
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise

    def _connect(self):
        conn = sqlite3.connect(self.db_path, isolation_level=None, timeout=15)
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def record(self, context: DecisionContext, result: DecisionResult, *, task_id: str = "") -> str:
        trace_id = f"route_{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc).isoformat()
        text = context.resolved_query or context.text
        application = {"route": context.route, "answer_mode": context.answer_mode,
                       "subject": context.subject, "book_ids": context.book_ids[:8],
                       "attachment_kinds": context.attachments[:8],
                       "context_version": context.context_version}
        decision = {"mode": result.mode, "selected_capability": result.selected_capability,
                    "action_intent": result.action_intent, "rule_match": result.rule_match,
                    "reason_codes": result.reason_codes, "backend_id": result.backend_id,
                    "backend_version": result.backend_version,
                    "semantic_candidates": [item.__dict__ for item in result.semantic_candidates[:12]],
                    "fallback_used": result.fallback_used, "shadow_only": result.shadow_only}
        with closing(self._connect()) as conn:
            conn.execute("INSERT INTO routing_traces VALUES (?,?,?,?,?,?,?)",
                (trace_id, context.request_id, task_id, now,
                 hashlib.sha256(text.encode()).hexdigest(),
                 json.dumps(application), json.dumps(decision)))
        return trace_id

    def list(self, *, limit: int = 50, before_id: str = "") -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("invalid routing trace page size")
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT id,request_id,task_id,input_hash,application_json,decision_json FROM routing_traces WHERE (?='' OR id<?) ORDER BY id DESC LIMIT ?", (before_id, before_id, limit))
            return [{"id": row[0], "request_id": row[1], "task_id": row[2], "input_hash": row[3],
                     "application": json.loads(row[4]), "decision": json.loads(row[5])} for row in rows]

    def review(self, trace_id: str, *, reviewer_id: str, expected_capability: str, holdout_group: str) -> str:
        from backend.services.decision.router import CAPABILITIES
        if not reviewer_id.strip() or not holdout_group.strip() or expected_capability not in {*CAPABILITIES, "direct_answer", "clarify", "unsupported"}:
            raise ValueError("invalid human routing review")
        if any(len(value) > 200 for value in (reviewer_id, holdout_group)):
            raise ValueError("routing review metadata too long")
        # Stable conversation/time-group split prevents near-duplicate group leakage.
        split = "holdout" if int(hashlib.sha256(holdout_group.encode()).hexdigest()[:8], 16) % 5 == 0 else "calibration"
        review_id = f"review_{uuid.uuid4().hex}"
        with closing(self._connect()) as conn:
            conn.execute("INSERT INTO routing_reviews VALUES (?,?,?,?,?,?,?)",
                (review_id, trace_id, reviewer_id, expected_capability, holdout_group, split, datetime.now(timezone.utc).isoformat()))
        return review_id

    def review_report(self) -> dict:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT r.split,r.expected_capability,t.decision_json FROM routing_reviews r JOIN routing_traces t ON t.id=r.trace_id").fetchall()
        report = {"calibration": {"samples": 0, "matches": 0}, "holdout": {"samples": 0, "matches": 0}}
        for split, expected, encoded in rows:
            decision = json.loads(encoded)
            selected = decision["selected_capability"] or decision["mode"]
            report[split]["samples"] += 1
            report[split]["matches"] += int(selected == expected)
        return {"groups": report, "automatic_takeover_allowed": False,
                "reason": "human review statistics do not enable semantic takeover or prove answer quality"}
