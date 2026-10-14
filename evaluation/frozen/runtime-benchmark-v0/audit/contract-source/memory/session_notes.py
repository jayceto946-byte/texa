"""Independent, versioned learning documents. No model or application imports."""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from utils.sqlite_migrations import apply_sqlite_migrations

SCHEMA_VERSION = 1


class NoteError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422, *, reason: str = "", path: str = ""):
        self.reason, self.path = reason, path
        super().__init__(message)
        self.code, self.status = code, status


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value) -> str:
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def _migrate(conn):
    statements = [
        "CREATE TABLE session_notes(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL, subject TEXT NOT NULL, search_text TEXT NOT NULL, summary_json TEXT NOT NULL, document_json TEXT NOT NULL)",
        "CREATE INDEX notes_page ON session_notes(status, updated_at DESC, id DESC)",
        "CREATE TABLE note_revisions(note_id TEXT NOT NULL, revision INTEGER NOT NULL, saved_at TEXT NOT NULL, change_kind TEXT NOT NULL, document_json TEXT NOT NULL, PRIMARY KEY(note_id,revision))",
        "CREATE TABLE note_drafts(id TEXT PRIMARY KEY, status TEXT NOT NULL, revision INTEGER NOT NULL, updated_at TEXT NOT NULL, conversation_id TEXT NOT NULL, active_key TEXT UNIQUE, document_json TEXT NOT NULL)",
        "CREATE INDEX drafts_page ON note_drafts(updated_at DESC,id DESC)",
        "CREATE TABLE note_source_snapshots(id TEXT PRIMARY KEY, document_json TEXT NOT NULL)",
        "CREATE TABLE note_relations(note_id TEXT NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL, PRIMARY KEY(note_id,kind,ref))",
        "CREATE INDEX relations_lookup ON note_relations(kind,ref,note_id)",
        "CREATE TABLE note_operations(id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, receipt_json TEXT NOT NULL)",
    ]
    for statement in statements:
        conn.execute(statement)


class SessionNoteStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as conn:
            apply_sqlite_migrations(conn, component="session_notes", current_version=1, migrations={1: _migrate})

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            installed = conn.execute("PRAGMA user_version").fetchone()[0]
            if installed > SCHEMA_VERSION:
                raise NoteError("storage_unavailable", "笔记数据库版本高于当前程序，请升级后打开", 503)
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _get(self, conn, table: str, identity: str):
        row = conn.execute(f"SELECT document_json FROM {table} WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise NoteError("not_found", "笔记或草稿不存在", 404)
        return json.loads(row[0])

    def get(self, table: str, identity: str):
        if table not in {"session_notes", "note_drafts", "note_source_snapshots"}:
            raise ValueError("unknown note table")
        with self.transaction() as conn:
            return self._get(conn, table, identity)

    def receipt(self, conn, operation_id: str, request):
        if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 100:
            raise NoteError("invalid_document", "operation_id 长度必须为 1–100")
        row = conn.execute("SELECT * FROM note_operations WHERE id=?", (operation_id,)).fetchone()
        if row is None:
            return None
        if row["request_hash"] != fingerprint(request):
            raise NoteError("operation_conflict", "同一操作编号不能提交不同内容", 409)
        return json.loads(row["receipt_json"])

    def record(self, conn, operation_id: str, request, receipt):
        conn.execute("INSERT INTO note_operations VALUES(?,?,?)", (operation_id, fingerprint(request), encode(receipt)))

    def put_draft(self, conn, draft, *, active_key=None):
        conn.execute(
            "INSERT INTO note_drafts VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,revision=excluded.revision,updated_at=excluded.updated_at,active_key=excluded.active_key,document_json=excluded.document_json",
            (draft["id"], draft["status"], draft["draft_revision"], draft["updated_at"], draft["conversation_id"], active_key, encode(draft)),
        )

    def register_generation(self, operation_id, request, snapshot, draft, active_key):
        with self.transaction() as conn:
            receipt = self.receipt(conn, operation_id, request)
            if receipt:
                return receipt
            row = conn.execute("SELECT document_json FROM note_drafts WHERE active_key=?", (active_key,)).fetchone()
            if row:
                old = json.loads(row[0])
                receipt = {"draft_id": old["id"], "job_id": old["job_id"], "snapshot_id": old["source_snapshot_ids"][0]}
            else:
                conn.execute("INSERT OR IGNORE INTO note_source_snapshots VALUES(?,?)", (snapshot["id"], encode(snapshot)))
                self.put_draft(conn, draft, active_key=active_key)
                receipt = {"draft_id": draft["id"], "job_id": draft["job_id"], "snapshot_id": snapshot["id"]}
            self.record(conn, operation_id, request, receipt)
            return receipt

    def candidate(self, draft_id, document):
        with self.transaction() as conn:
            draft = self._get(conn, "note_drafts", draft_id)
            if draft["status"] != "preparing" or draft.get("candidate_hash"):
                raise NoteError("revision_conflict", "生成申请已经结束", 409)
            draft.update(candidate=document, candidate_hash=fingerprint(document), updated_at=now())
            key = conn.execute("SELECT active_key FROM note_drafts WHERE id=?", (draft_id,)).fetchone()[0]
            self.put_draft(conn, draft, active_key=key)
            return draft["candidate_hash"]

    def publish_candidate(self, draft_id, completed_job):
        with self.transaction() as conn:
            draft = self._get(conn, "note_drafts", draft_id)
            if draft["status"] != "preparing":
                return draft
            result = completed_job.get("result") or {}
            if completed_job.get("status") != "completed" or completed_job.get("id") != draft["job_id"] or result.get("draft_id") != draft_id or result.get("candidate_hash") != draft.get("candidate_hash") or not draft.get("candidate") or fingerprint(draft["candidate"]) != draft["candidate_hash"]:
                raise NoteError("invalid_document", "生成完成回执与候选不匹配")
            draft.update(content=draft.pop("candidate"), status="editable", updated_at=now())
            draft["draft_revision"] += 1
            self.put_draft(conn, draft)
            return draft

    def release_generation(self, draft_id):
        with self.transaction() as conn:
            conn.execute("UPDATE note_drafts SET active_key=NULL WHERE id=?", (draft_id,))

    def list(self, *, drafts=False, cursor="", limit=30, **filters):
        limit = max(1, min(int(limit), 100))
        table = "note_drafts" if drafts else "session_notes"
        clauses, params = [], []
        if cursor:
            try:
                stamp, identity = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if not isinstance(stamp, str) or not isinstance(identity, str):
                    raise ValueError()
            except Exception:
                raise NoteError("invalid_selection", "分页游标无效", 400) from None
            clauses.append("(updated_at,id)<(?,?)")
            params.extend([stamp, identity])
        for key in ("status", "conversation_id", "subject", "book_id", "chapter_ref_id"):
            value = filters.get(key)
            if not value:
                continue
            if key in {"status", "subject"} and not (drafts and key == "subject") or (drafts and key == "conversation_id"):
                clauses.append(f"{key}=?")
                params.append(value)
            elif not drafts:
                clauses.append("id IN (SELECT note_id FROM note_relations WHERE kind=? AND ref=?)")
                params.extend([key, value])
        if drafts and not filters.get("status"):
            clauses.append("status NOT IN ('discarded','published')")
        if filters.get("q") and not drafts:
            clauses.append("instr(search_text,?)>0")
            params.append(str(filters["q"]).lower())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        column = "document_json" if drafts else "summary_json"
        selection = "json_remove(document_json,'$.content','$.candidate','$.candidate_hash') AS document_json, json_extract(document_json,'$.content.title') AS draft_title" if drafts else "summary_json"
        with self.transaction() as conn:
            rows = conn.execute(f"SELECT id,updated_at,{selection} FROM {table}{where} ORDER BY updated_at DESC,id DESC LIMIT ?", (*params, limit + 1)).fetchall()
        selected = rows[:limit]
        items = [json.loads(row[column]) for row in selected]
        if drafts:
            items = [d | {"title": row["draft_title"] or "整理中的笔记"} for d, row in zip(items, selected)]
        next_cursor = base64.urlsafe_b64encode(encode([selected[-1]["updated_at"], selected[-1]["id"]]).encode()).decode() if len(rows) > limit else None
        return {"items": items, "next_cursor": next_cursor}

    def put_note(self, conn, note, change_kind):
        summary = {k: v for k, v in note.items() if k not in {"blocks", "generation", "source_snapshot_ids"}}
        search_text = " ".join([note["title"], note.get("abstract", ""), *note.get("tags", [])]).lower()
        conn.execute("INSERT INTO session_notes VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,status=excluded.status,updated_at=excluded.updated_at,subject=excluded.subject,search_text=excluded.search_text,summary_json=excluded.summary_json,document_json=excluded.document_json", (note["id"], note["revision"], note["status"], note["updated_at"], note.get("subject", ""), search_text, encode(summary), encode(note)))
        conn.execute("INSERT INTO note_revisions VALUES(?,?,?,?,?)", (note["id"], note["revision"], note["saved_at"], change_kind, encode(note)))
        conn.execute("DELETE FROM note_relations WHERE note_id=?", (note["id"],))
        relations = [("conversation_id", o["conversation_id"]) for o in note["origins"]]
        relations += [("book_id", c["book_id"]) for c in note.get("chapter_refs", []) if c.get("book_id")]
        relations += [("chapter_ref_id", c["chapter_ref_id"]) for c in note.get("chapter_refs", [])]
        for sid in note["source_snapshot_ids"]:
            snapshot = self._get(conn, "note_source_snapshots", sid)
            relations += [("book_id", c["book_id"]) for c in snapshot.get("chapter_refs", []) if c.get("book_id")]
            relations += [("book_id", e["book_id"]) for e in snapshot.get("evidence", []) if e.get("book_id")]
        conn.executemany("INSERT OR IGNORE INTO note_relations VALUES(?,?,?)", [(note["id"], kind, ref) for kind, ref in relations])

    def filter_options(self, status="active"):
        """Version anchors across the collection, independent of the current list page."""
        with self.transaction() as conn:
            rows = conn.execute("SELECT DISTINCT value FROM session_notes, json_each(summary_json,'$.chapter_refs') WHERE session_notes.status=?", (status,)).fetchall()
            books = conn.execute("SELECT DISTINCT ref FROM note_relations JOIN session_notes ON session_notes.id=note_relations.note_id WHERE kind='book_id' AND status=?", (status,)).fetchall()
        chapters = {c["chapter_ref_id"]: c for c in (json.loads(row[0]) for row in rows)}
        names = {c["book_id"]: c.get("book_name_snapshot") or c["book_id"] for c in chapters.values() if c.get("book_id")}
        return {"chapter_refs": list(chapters.values()), "books": [{"book_id": row[0], "name": names.get(row[0], row[0])} for row in books]}

    def revisions(self, note_id, revision=None, before=None, limit=30):
        limit = max(1, min(limit, 100))
        with self.transaction() as conn:
            self._get(conn, "session_notes", note_id)
            if revision is not None:
                row = conn.execute("SELECT document_json FROM note_revisions WHERE note_id=? AND revision=?", (note_id, revision)).fetchone()
                if row is None:
                    raise NoteError("not_found", "版本不存在", 404)
                return json.loads(row[0])
            rows = conn.execute("SELECT revision,saved_at,change_kind FROM note_revisions WHERE note_id=? AND revision<? ORDER BY revision DESC LIMIT ?", (note_id, before or 2**63 - 1, max(1, min(limit, 100)) + 1)).fetchall()
            return {"items": [dict(row) for row in rows[:limit]], "next_cursor": rows[limit-1]["revision"] if len(rows) > limit else None}


def validate_notes_database(path: str | Path) -> None:
    """Read-only restore validation; old archives without this component are valid."""
    path = Path(path)
    if not path.exists():
        return
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok" or conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise ValueError("unsupported or damaged session_notes database")
        snapshots = {row[0] for row in conn.execute("SELECT id FROM note_source_snapshots")}
        for table in ("session_notes", "note_drafts", "note_revisions"):
            for (payload,) in conn.execute(f"SELECT document_json FROM {table}"):
                document = json.loads(payload)
                if document.get("schema_version") != 1 or not document.get("source_snapshot_ids") or any(ref not in snapshots for ref in document["source_snapshot_ids"]):
                    raise ValueError("session_notes source references are incomplete")
        # Missing jobs are reconciled as interrupted after startup; they are not corrupt Notes.
        for table in ("note_operations", "note_relations"):
            conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
