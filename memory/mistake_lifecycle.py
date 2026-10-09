"""Durable candidate, attempt and review-session facts for one mistake book."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import date, datetime
from typing import Any

from memory.mistake_book import MistakeBookStore, MistakeRecord, SM2Scheduler


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class MistakeLifecycleStore:
    def __init__(self, store: MistakeBookStore):
        self.store = store

    def _receipt(self, conn: sqlite3.Connection, operation_id: str, args: Any) -> dict | None:
        if not operation_id:
            raise ValueError("operation_id is required")
        row = conn.execute("SELECT args_hash,result_json FROM mistake_operations WHERE operation_id=?", (operation_id,)).fetchone()
        if not row:
            return None
        if row[0] != _fingerprint(args):
            raise ValueError("operation arguments changed")
        return json.loads(row[1])

    def _save_receipt(self, conn: sqlite3.Connection, operation_id: str, args: Any, result: dict) -> dict:
        conn.execute("INSERT INTO mistake_operations VALUES (?,?,?)", (operation_id, _fingerprint(args), json.dumps(result, ensure_ascii=False)))
        return result

    def create_candidate(self, source_key: str, snapshot: dict) -> dict:
        if not source_key.strip() or not snapshot.get("question_text") and not snapshot.get("image_path"):
            raise ValueError("candidate requires source and question or image")
        candidate_id = "mc_" + hashlib.sha256(source_key.encode()).hexdigest()[:24]
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data,status,revision,linked_mistake_id FROM mistake_candidates WHERE source_key=?", (source_key,)).fetchone()
            if row:
                return {"id": candidate_id, **json.loads(row[0]), "status": row[1], "revision": row[2], "linked_mistake_id": row[3]}
            created_at = _now()
            stable_key = str(snapshot.get("stable_source_key") or "")
            linked = conn.execute("SELECT mistake_id FROM mistake_sources WHERE source_key=?", (stable_key,)).fetchone() if stable_key else None
            linked_id = linked[0] if linked else ""
            conn.execute("INSERT INTO mistake_candidates VALUES (?,?,?,?,?,?,?)", (candidate_id, source_key, json.dumps(snapshot, ensure_ascii=False), "pending", 1, linked_id, created_at))
            return {"id": candidate_id, **snapshot, "status": "pending", "revision": 1, "linked_mistake_id": linked_id, "created_at": created_at}

    def link_source(self, source_key: str, mistake_id: str) -> None:
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT mistake_id FROM mistake_sources WHERE source_key=?", (source_key,)).fetchone()
            if row and row[0] != mistake_id:
                raise ValueError("source already linked to another mistake")
            conn.execute("INSERT OR IGNORE INTO mistake_sources VALUES (?,?)", (source_key, mistake_id))

    def list_candidates(self, *, limit: int = 30) -> list[dict]:
        with self.store._connect() as conn:
            rows = conn.execute("SELECT id,data,status,revision,linked_mistake_id,created_at FROM mistake_candidates WHERE status='pending' ORDER BY created_at ASC LIMIT ?", (limit,)).fetchall()
        return [{"id": row[0], **json.loads(row[1]), "status": row[2], "revision": row[3], "linked_mistake_id": row[4], "created_at": row[5]} for row in rows]

    def update_candidate(self, candidate_id: str, *, expected_revision: int, changes: dict) -> dict:
        if not changes or set(changes) - {"question_text", "user_answer", "correct_answer", "content_complete", "mistake_type", "tags", "notes", "diagnosis_status"}:
            raise ValueError("unsupported candidate changes")
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data,status,revision,linked_mistake_id,created_at FROM mistake_candidates WHERE id=?", (candidate_id,)).fetchone()
            if not row:
                raise ValueError("candidate not found")
            if row[1] != "pending" or row[2] != expected_revision:
                raise ValueError("candidate revision changed")
            updated = {**json.loads(row[0]), **changes}
            conn.execute("UPDATE mistake_candidates SET data=?,revision=? WHERE id=?", (json.dumps(updated, ensure_ascii=False), expected_revision + 1, candidate_id))
            return {"id": candidate_id, **updated, "status": "pending", "revision": expected_revision + 1, "linked_mistake_id": row[3], "created_at": row[4]}

    def resolve_candidate(self, candidate_id: str, *, accept: bool, expected_revision: int, operation_id: str) -> dict:
        args = [candidate_id, accept, expected_revision]
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = self._receipt(conn, operation_id, args)
            if prior is not None:
                return prior
            row = conn.execute("SELECT source_key,data,status,revision,linked_mistake_id FROM mistake_candidates WHERE id=?", (candidate_id,)).fetchone()
            if not row:
                raise ValueError("candidate not found")
            source_key, raw, status, revision, linked_id = row
            if revision != expected_revision:
                raise ValueError("candidate revision changed")
            if status != "pending":
                raise ValueError("candidate already resolved")
            if not accept:
                conn.execute("UPDATE mistake_candidates SET status='dismissed',revision=revision+1 WHERE id=?", (candidate_id,))
                return self._save_receipt(conn, operation_id, args, {"candidate_id": candidate_id, "status": "dismissed"})
            data = json.loads(raw)
            question = str(data.get("question_text") or "").strip()
            if not question or data.get("content_complete") is False:
                raise ValueError("question needs correction before acceptance")
            source_row = conn.execute("SELECT mistake_id FROM mistake_sources WHERE source_key=?", (source_key,)).fetchone()
            record_id = source_row[0] if source_row else linked_id
            if not record_id and data.get("stable_source_key"):
                stable_row = conn.execute("SELECT mistake_id FROM mistake_sources WHERE source_key=?", (data["stable_source_key"],)).fetchone()
                record_id = stable_row[0] if stable_row else ""
            existing_record = bool(record_id)
            if not record_id:
                record = MistakeRecord(
                    id="m_" + uuid.uuid4().hex[:20], question_text=question,
                    book_id=str(data.get("book_id") or ""), subject=str(data.get("subject") or ""),
                    user_answer=str(data.get("user_answer") or ""), correct_answer=str(data.get("correct_answer") or ""),
                    source=str(data.get("source") or ""), source_ref=dict(data.get("source_ref") or {}),
                    chapter=str(data.get("chapter") or "") or None,
                    tags=list(data.get("tags") or []), mistake_type=list(data.get("mistake_type") or []),
                    notes=str(data.get("notes") or ""), explanation=str(data.get("explanation") or ""),
                    image_path=data.get("image_path"), ocr_text=str(data.get("ocr_text") or ""),
                    attachments=list(data.get("attachments") or []),
                    visual_ir=dict(data.get("visual_ir") or {}),
                    content_status="ready" if data.get("content_complete", True) else "needs_correction",
                    diagnosis_status="confirmed" if data.get("mistake_type") else "missing",
                )
                if record.content_status == "ready":
                    SM2Scheduler(record)
                conn.execute("INSERT INTO mistakes (id,data,created_at,next_review,subject,chapter) VALUES (?,?,?,?,?,?)", (
                    record.id, json.dumps(record.to_dict(), ensure_ascii=False), record.created_at,
                    record.sm2.get("next_review") if record.sm2 else None, record.subject, record.chapter,
                ))
                record_id = record.id
            conn.execute("INSERT OR IGNORE INTO mistake_sources VALUES (?,?)", (source_key, record_id))
            stable_source_key = str(data.get("stable_source_key") or "")
            if stable_source_key:
                conn.execute("INSERT OR IGNORE INTO mistake_sources VALUES (?,?)", (stable_source_key, record_id))
            conn.execute("UPDATE mistake_candidates SET status='accepted',revision=revision+1,linked_mistake_id=? WHERE id=?", (record_id, candidate_id))
            if data.get("failure_confirmed"):
                attempt_key = "occurrence:" + source_key
                attempt_id = "mo_" + hashlib.sha256(attempt_key.encode()).hexdigest()[:24]
                current = MistakeRecord.from_dict(json.loads(conn.execute("SELECT data FROM mistakes WHERE id=?", (record_id,)).fetchone()[0]))
                fact = {"answer": str(data.get("user_answer") or ""), "result": "wrong", "judgement_source": "user_confirmed", "source_ref": data.get("source_ref") or {}, "question_revision": current.content_revision}
                inserted = conn.execute("INSERT OR IGNORE INTO mistake_attempts VALUES (?,?,?,?,?,?)", (attempt_id, record_id, attempt_key, "occurrence", json.dumps(fact, ensure_ascii=False), _now())).rowcount
                if inserted and existing_record:
                    current.manual_mastered = False
                    SM2Scheduler(current).review(1)
                    current.revision += 1
                    conn.execute("UPDATE mistakes SET data=?,next_review=? WHERE id=?", (json.dumps(current.to_dict(), ensure_ascii=False), current.sm2.get("next_review"), record_id))
            return self._save_receipt(conn, operation_id, args, {"candidate_id": candidate_id, "status": "accepted", "mistake_id": record_id})

    @staticmethod
    def _chat_identity(source_ref: dict) -> tuple[str, str] | None:
        if source_ref.get("type") != "chat":
            return None
        conversation = str(source_ref.get("conversation_id") or "").strip()
        message = str(source_ref.get("message_id") or "").strip()
        return (conversation, message) if conversation and message else None

    def _chat_links(self, conn: sqlite3.Connection, refs: list[dict]) -> dict:
        """Read the complete source namespace, including legacy source_ref records.

        Do not derive completeness from a UI list's bounded draft page. Existing
        duplicates are left intact; prefer a formal record, then oldest draft.
        """
        identities = {self._chat_identity(ref) for ref in refs}
        result = {}
        for row in conn.execute("SELECT id,data FROM mistakes ORDER BY created_at,id"):
            data = json.loads(row[1])
            identity = self._chat_identity(data.get("source_ref") or {})
            if identity in identities and identity is not None and identity not in result:
                result[identity] = {"status": "recorded", "mistake_id": row[0], "visibility": data.get("visibility", "active")}
        for row in conn.execute("""SELECT d.id,d.data,c.status,c.linked_mistake_id,m.data
                FROM mistake_drafts d LEFT JOIN mistake_candidates c ON c.source_key='manual:' || d.id
                LEFT JOIN mistakes m ON m.id=c.linked_mistake_id ORDER BY d.updated_at,d.id"""):
            data = json.loads(row[1])
            identity = self._chat_identity(data.get("source_ref") or {})
            if identity not in identities or identity is None or identity in result:
                continue
            if row[2] == "accepted" and row[3] and row[4]:
                result[identity] = {"status": "recorded", "mistake_id": row[3], "visibility": json.loads(row[4]).get("visibility", "active")}
            elif row[2] != "accepted":
                result[identity] = {"status": "draft", "draft_id": row[0]}
        return result

    def lookup_chat_sources(self, refs: list[dict]) -> list[dict]:
        with self.store._connect() as conn:
            links = self._chat_links(conn, refs)
        return [{"message_id": ref["message_id"], **links.get(self._chat_identity(ref), {"status": "unrecorded"})} for ref in refs]

    def get_or_create_chat_draft(self, data: dict, stable_source_key: str, *, prepare=None) -> dict:
        identity = self._chat_identity(data.get("source_ref") or {})
        if identity is None:
            raise ValueError("chat capture requires a persisted conversation and message identity")
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = self._chat_links(conn, [data["source_ref"]]).get(identity)
            if existing:
                return existing
            draft_id, now = "md_" + uuid.uuid4().hex[:24], _now()
            payload = {**data, **(prepare(draft_id) if prepare else {}), "stable_source_key": stable_source_key}
            conn.execute("INSERT INTO mistake_drafts VALUES (?,?,?,?)", (draft_id, json.dumps(payload, ensure_ascii=False), 1, now))
            return {"status": "draft", "draft_id": draft_id}

    def create_draft(self, data: dict) -> dict:
        draft_id = "md_" + uuid.uuid4().hex[:24]
        now = _now()
        with self.store._connect() as conn:
            conn.execute("INSERT INTO mistake_drafts VALUES (?,?,?,?)", (draft_id, json.dumps(data, ensure_ascii=False), 1, now))
        return {"id": draft_id, "revision": 1, "updated_at": now, **data}

    def get_draft(self, draft_id: str) -> dict | None:
        with self.store._connect() as conn:
            row = conn.execute("SELECT data,revision,updated_at FROM mistake_drafts WHERE id=?", (draft_id,)).fetchone()
        return {"id": draft_id, **json.loads(row[0]), "revision": row[1], "updated_at": row[2]} if row else None

    def list_drafts(self, *, limit: int = 20) -> list[dict]:
        with self.store._connect() as conn:
            rows = conn.execute("""SELECT d.id,d.data,d.revision,d.updated_at FROM mistake_drafts d
                WHERE NOT EXISTS (SELECT 1 FROM mistake_candidates c WHERE c.source_key='manual:' || d.id AND c.status='accepted')
                ORDER BY d.updated_at DESC,d.id DESC LIMIT ?""", (limit,)).fetchall()
        return [{"id": row[0], **json.loads(row[1]), "revision": row[2], "updated_at": row[3]} for row in rows]

    def update_draft(self, draft_id: str, data: dict, expected_revision: int) -> dict:
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data,revision FROM mistake_drafts WHERE id=?", (draft_id,)).fetchone()
            if not row:
                raise ValueError("draft not found")
            saved = conn.execute("SELECT linked_mistake_id FROM mistake_candidates WHERE source_key=? AND status='accepted'", ("manual:" + draft_id,)).fetchone()
            if saved:
                raise ValueError("该草稿已保存为正式错题，请打开错题记录编辑")
            if row[1] != expected_revision:
                raise ValueError("draft revision changed")
            updated = {**json.loads(row[0]), **data}
            now = _now()
            conn.execute("UPDATE mistake_drafts SET data=?,revision=?,updated_at=? WHERE id=?", (json.dumps(updated, ensure_ascii=False), expected_revision+1, now, draft_id))
            return {"id": draft_id, **updated, "revision": expected_revision+1, "updated_at": now}

    def list_attempts(self, mistake_id: str, *, limit: int = 30, before: str = "") -> list[dict]:
        query = "SELECT id,kind,data,created_at FROM mistake_attempts WHERE mistake_id=?"
        params: list[Any] = [mistake_id]
        if before:
            query += " AND created_at<?"
            params.append(before)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(limit)
        with self.store._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [{"id": row[0], "kind": row[1], **json.loads(row[2]), "created_at": row[3]} for row in rows]

    def append_occurrence_once(self, mistake_id: str, source_key: str, *, answer: str, source_ref: dict) -> str:
        if not source_key:
            raise ValueError("source key is required")
        attempt_key = "occurrence:" + source_key
        attempt_id = "mo_" + hashlib.sha256(attempt_key.encode()).hexdigest()[:24]
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data FROM mistakes WHERE id=?", (mistake_id,)).fetchone()
            if not row:
                raise ValueError("mistake not found")
            existing = conn.execute("SELECT mistake_id FROM mistake_attempts WHERE source_key=?", (attempt_key,)).fetchone()
            if existing:
                if existing[0] != mistake_id:
                    raise ValueError("source already linked to another mistake")
                return attempt_id
            record = MistakeRecord.from_dict(json.loads(row[0]))
            fact = {"answer": answer, "result": "wrong", "judgement_source": "user_confirmed", "source_ref": source_ref, "question_revision": record.content_revision}
            conn.execute("INSERT INTO mistake_attempts VALUES (?,?,?,?,?,?)", (attempt_id, mistake_id, attempt_key, "occurrence", json.dumps(fact, ensure_ascii=False), _now()))
            record.manual_mastered = False
            SM2Scheduler(record).review(1)
            record.revision += 1
            conn.execute("UPDATE mistakes SET data=?,next_review=? WHERE id=?", (json.dumps(record.to_dict(), ensure_ascii=False), record.sm2.get("next_review"), mistake_id))
            return attempt_id

    def change_record(self, mistake_id: str, *, expected_revision: int, operation_id: str,
                      changes: dict, meaning_changed: bool = False) -> dict:
        allowed = {"question_text", "user_answer", "correct_answer", "mistake_type", "tags", "notes", "subject", "chapter", "source", "content_status", "diagnosis_status", "visibility", "manual_mastered"}
        if not changes or set(changes) - allowed:
            raise ValueError("unsupported mistake changes")
        if "content_status" in changes and changes["content_status"] not in {"ready", "needs_correction", "legacy_unverified"}:
            raise ValueError("unsupported content status")
        if "diagnosis_status" in changes and changes["diagnosis_status"] not in {"missing", "confirmed", "deferred", "suggested"}:
            raise ValueError("unsupported diagnosis status")
        if "visibility" in changes and changes["visibility"] not in {"active", "archived"}:
            raise ValueError("unsupported visibility")
        if "manual_mastered" in changes and type(changes["manual_mastered"]) is not bool:
            raise ValueError("invalid mastery flag")
        for field in ("question_text", "user_answer", "correct_answer", "notes", "subject", "chapter", "source"):
            if field in changes and (not isinstance(changes[field], str) or len(changes[field]) > 30000):
                raise ValueError(f"invalid {field}")
        for field in ("mistake_type", "tags"):
            if field in changes and (not isinstance(changes[field], list) or len(changes[field]) > 30 or any(not isinstance(value, str) or len(value) > 120 for value in changes[field])):
                raise ValueError(f"invalid {field}")
        args = [mistake_id, expected_revision, changes, meaning_changed]
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = self._receipt(conn, operation_id, args)
            if prior is not None:
                return prior
            row = conn.execute("SELECT data FROM mistakes WHERE id=?", (mistake_id,)).fetchone()
            if not row:
                raise ValueError("mistake not found")
            record = MistakeRecord.from_dict(json.loads(row[0]))
            if record.revision != expected_revision:
                raise ValueError("mistake revision changed")
            if meaning_changed:
                conn.execute("INSERT OR IGNORE INTO mistake_revisions VALUES (?,?,?,?)", (mistake_id, record.content_revision, json.dumps(record.to_dict(), ensure_ascii=False), _now()))
                record.content_revision += 1
                record.manual_mastered = False
            for field, value in changes.items():
                setattr(record, field, value)
            if record.content_status == "ready" and not record.question_text.strip():
                raise ValueError("ready mistake requires question text")
            if record.content_status == "ready" and not record.sm2:
                SM2Scheduler(record)
            record.revision += 1
            conn.execute("UPDATE mistakes SET data=?,next_review=?,subject=?,chapter=? WHERE id=?", (
                json.dumps(record.to_dict(), ensure_ascii=False), record.sm2.get("next_review") if record.sm2 else None,
                record.subject, record.chapter, record.id,
            ))
            return self._save_receipt(conn, operation_id, args, {"mistake_id": record.id, "revision": record.revision, "content_revision": record.content_revision})

    def create_review_session(self, mistake_ids: list[str], *, scope: str) -> dict:
        if not mistake_ids or len(mistake_ids) != len(set(mistake_ids)):
            raise ValueError("review items must be nonempty and unique")
        with self.store._connect() as conn:
            rows = [conn.execute("SELECT data FROM mistakes WHERE id=?", (rid,)).fetchone() for rid in mistake_ids]
            if any(row is None for row in rows):
                raise ValueError("review item not found")
            records = [MistakeRecord.from_dict(json.loads(row[0])) for row in rows if row]
            if any(record.visibility != "active" or record.content_status == "needs_correction" for record in records):
                raise ValueError("review item is not eligible")
            session_id = "mrs_" + uuid.uuid4().hex[:24]
            now = _now()
            data = {"scope": scope, "items": mistake_ids, "index": 0, "results": {}, "current_answer": "", "revealed": False, "created_at": now}
            conn.execute("INSERT INTO mistake_review_sessions VALUES (?,?,?,?)", (session_id, json.dumps(data, ensure_ascii=False), 1, now))
        return {"id": session_id, **data, "revision": 1}

    def find_incomplete_review_session(self, *, subject: str = "") -> dict | None:
        from utils.subject_catalog import subject_matches
        with self.store._connect() as conn:
            for row in conn.execute("SELECT id,data,revision,updated_at FROM mistake_review_sessions ORDER BY updated_at DESC,id DESC"):
                data = json.loads(row[1])
                if data.get("index", 0) >= len(data.get("items") or []):
                    continue
                if subject:
                    records = [conn.execute("SELECT data FROM mistakes WHERE id=?", (rid,)).fetchone() for rid in data["items"]]
                    if any(record is None or not subject_matches(str(json.loads(record[0]).get("subject") or ""), subject) for record in records):
                        continue
                return {"id": row[0], **data, "revision": row[2], "updated_at": row[3]}
        return None

    def get_review_session(self, session_id: str) -> dict | None:
        with self.store._connect() as conn:
            row = conn.execute("SELECT data,revision,updated_at FROM mistake_review_sessions WHERE id=?", (session_id,)).fetchone()
        return {"id": session_id, **json.loads(row[0]), "revision": row[1], "updated_at": row[2]} if row else None

    def update_review_draft(self, session_id: str, *, expected_revision: int, answer: str, revealed: bool) -> dict:
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data,revision FROM mistake_review_sessions WHERE id=?", (session_id,)).fetchone()
            if not row or row[1] != expected_revision:
                raise ValueError("review session revision changed")
            data = json.loads(row[0])
            if revealed:
                data["revealed"] = True
            else:
                if data.get("revealed"):
                    raise ValueError("answer is locked after reveal")
                data["current_answer"] = answer
            now = _now()
            conn.execute("UPDATE mistake_review_sessions SET data=?,revision=?,updated_at=? WHERE id=?", (json.dumps(data, ensure_ascii=False), expected_revision+1, now, session_id))
            return {"id": session_id, **data, "revision": expected_revision+1, "updated_at": now}

    def submit_review_result(self, session_id: str, *, expected_revision: int, operation_id: str, result: str, hint_used: bool, judgement_source: str) -> dict:
        if result not in {"wrong", "partial", "prompted_correct", "independent_correct"}:
            raise ValueError("unsupported review result")
        if judgement_source not in {"user_confirmed", "deterministic"}:
            raise ValueError("unsupported judgement source")
        args = [session_id, expected_revision, result, hint_used, judgement_source]
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = self._receipt(conn, operation_id, args)
            if prior is not None:
                return prior
            row = conn.execute("SELECT data,revision FROM mistake_review_sessions WHERE id=?", (session_id,)).fetchone()
            if not row or row[1] != expected_revision:
                raise ValueError("review session revision changed")
            data = json.loads(row[0])
            index = data["index"]
            if index >= len(data["items"]):
                raise ValueError("review session complete")
            if not data.get("revealed"):
                raise ValueError("reveal feedback before recording result")
            mistake_id = data["items"][index]
            record_row = conn.execute("SELECT data FROM mistakes WHERE id=?", (mistake_id,)).fetchone()
            if not record_row:
                raise ValueError("review item not found")
            record = MistakeRecord.from_dict(json.loads(record_row[0]))
            was_due = bool(record.sm2 and record.sm2.get("next_review", "9999-12-31") <= date.today().isoformat())
            quality = {"wrong": 1, "partial": 2, "prompted_correct": 3, "independent_correct": 4}[result]
            if hint_used and result == "independent_correct":
                result = "prompted_correct"
                quality = 3
            if result == "independent_correct" and not data.get("current_answer", "").strip():
                raise ValueError("independent correct result requires a submitted answer")
            # Revealing after a saved answer is allowed; the reveal timestamp is kept.
            fact = {"answer": data.get("current_answer", ""), "result": result, "hint_used": hint_used,
                    "answer_revealed": bool(data.get("revealed")), "judgement_source": judgement_source,
                    "was_due": was_due, "question_revision": record.content_revision, "quality": quality}
            attempt_id = "ma_" + uuid.uuid4().hex[:24]
            source_key = f"review:{session_id}:{index}"
            conn.execute("INSERT INTO mistake_attempts VALUES (?,?,?,?,?,?)", (attempt_id, mistake_id, source_key, "redo", json.dumps(fact, ensure_ascii=False), _now()))
            SM2Scheduler(record).review(quality)
            if result in {"wrong", "partial"}:
                record.manual_mastered = False
            record.revision += 1
            conn.execute("UPDATE mistakes SET data=?,next_review=? WHERE id=?", (json.dumps(record.to_dict(), ensure_ascii=False), record.sm2.get("next_review"), mistake_id))
            data["results"][mistake_id] = attempt_id
            data["index"] = index + 1
            data["current_answer"] = ""
            data["revealed"] = False
            now = _now()
            conn.execute("UPDATE mistake_review_sessions SET data=?,revision=?,updated_at=? WHERE id=?", (json.dumps(data, ensure_ascii=False), expected_revision+1, now, session_id))
            receipt = {"session_id": session_id, "revision": expected_revision+1, "mistake_id": mistake_id, "attempt_id": attempt_id, "next_review": record.sm2.get("next_review"), "index": data["index"]}
            return self._save_receipt(conn, operation_id, args, receipt)
