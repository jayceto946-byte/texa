"""Application use cases. Model/IO dependencies are resolved on demand."""
import copy
import re
import json

from memory.session_notes import SessionNoteStore, NoteError, new_id, now, fingerprint
from .sources import materialize, source_detail, safe_text
from .validation import validate_document, FIELDS
from .generation import plan_batches, budget_config, POLICY, PROMPT


class SessionNoteService:
    def __init__(self, store, *, capture=None, live_resolver=None, chapters=None, jobs_provider=None):
        self.store = store
        if capture is None or live_resolver is None:
            from backend.conversation_memory import capture_note_selection, resolve_message_context
            capture = capture or capture_note_selection
            live_resolver = live_resolver or resolve_message_context
        self.capture, self.live_resolver, self._chapters = capture, live_resolver, chapters
        self.jobs_provider = jobs_provider

    @property
    def chapters(self):
        if self._chapters is None:
            from backend.services.chapter_references import ChapterReferenceResolver
            self._chapters = ChapterReferenceResolver()
        return self._chapters

    def jobs(self):
        if self.jobs_provider:
            return self.jobs_provider()
        from backend.job_manager import get_job_manager
        return get_job_manager()

    def audit(self, phase, identity, status, refs=()):
        try:
            from backend.services.runtime_events import emit_best_effort, safe_reference
            emit_best_effort("state_transition", session_id=f"origin:ui_action:{safe_reference(identity)}", payload={"phase": phase, "status": status, "content_refs": list(refs)[:4]})
        except Exception:
            # Optional diagnostics cannot turn a committed asset into a failed save.
            pass

    def preflight(self, selection, structure_hint="auto", completed_only=False):
        if structure_hint not in {"auto", "concept", "derivation", "problem", "comparison", "review"}:
            raise NoteError("invalid_selection", "整理侧重无效", 400)
        captured = self.capture(selection["conversation_id"], turn_ids=selection.get("turn_ids"), through_seq=selection.get("through_seq"))
        groups = {}
        for m in captured["messages"]:
            groups.setdefault(m["turn_id"], []).append(m)
        pending = [tid for tid, msgs in groups.items() if not any(m["role"] == "assistant" for m in msgs) or any((m.get("learning_task") or {}).get("status") in {"running", "retrieving", "generating", "interrupting"} for m in msgs)]
        if pending:
            if not completed_only:
                raise NoteError("invalid_selection", "范围内有尚未完成的回答，请等待结束或只选择之前已完成的轮次", 400)
            complete = [tid for tid in groups if tid not in pending]
            if not complete:
                raise NoteError("no_learning_content", "尚无可整理的已完成轮次")
            captured = self.capture(selection["conversation_id"], turn_ids=complete, through_seq=captured["selection"]["through_seq"])
        texts = [m.get("content", "").strip() for m in captured["messages"]]
        if all(not t or re.fullmatch(r"(?:你好|谢谢|好的|再见|hi|hello|thanks)[！!。.\s]*", t, re.I) for t in texts):
            raise NoteError("no_learning_content", "当前会话只有寒暄，没有学习内容")
        snap = materialize(captured, self.chapters)
        inputs = self._generation_inputs(snap)
        batches, cfg = plan_batches(inputs, budget_config())
        version = fingerprint({"selection": captured["selection"], "hash": captured["input_hash"], "hint": structure_hint, "budget": cfg})
        return {"selection": captured["selection"], "fingerprint": version, "captured_at": captured["captured_at"], "turn_count": len(groups)-len(pending) if completed_only else len(groups), "message_count": len(captured["messages"]), "warnings": snap["warnings"], "excluded": snap["excluded"], "batches": len(batches), "budget": cfg, "turns": [{"turn_id": tid, "label": next((safe_text(m.get("content", ""))[:100] for m in msgs if m["role"] == "user"), tid)} for tid,msgs in groups.items()], "existing_notes": self.store.list(conversation_id=selection["conversation_id"]), "existing_drafts": self.list_drafts(conversation_id=selection["conversation_id"])}, snap

    @staticmethod
    def _generation_inputs(snapshot):
        # Match generation's actual payload size, including evidence and verification.
        return [{"source_ref_id": f"S{n+1}", "turn_id": s["turn_id"], "role": s["role"], "content": s["content"], "delivery_status": s.get("delivery_status"), "learning_task": s.get("learning_task"), "evidence_support_status": s.get("evidence_support_status"), "evidence": [{**e, "source_ref_id": f"S{n+1}", "evidence_ref_id": "T00000"} for e in snapshot["evidence"] if e["source_ref_id"] == s["source_ref_id"]]} for n,s in enumerate(snapshot["sources"]) if s["included"]]

    def request_generation(self, request):
        op = request["operation_id"]
        with self.store.transaction() as conn:
            previous = self.store.receipt(conn, op, {"kind": "generation", **request})
        if previous:
            return previous
        retry = request.get("retry_of_draft_id")
        if retry:
            parent = self.store.get("note_drafts", retry)
            job = self.jobs().get_job(parent.get("job_id", ""))
            if not job or job["status"] not in {"failed", "cancelled", "interrupted", "completed"}:
                raise NoteError("revision_conflict", "请先等待上次生成结束", 409)
            snapshot = self.store.get("note_source_snapshots", parent["source_snapshot_ids"][0])
            hint = parent["structure_hint"]
        else:
            try:
                preflight, snapshot = self.preflight(request["selection"], request.get("structure_hint", "auto"))
            except NoteError as exc:
                if request.get("preflight_fingerprint") and exc.code in {"not_found", "invalid_selection", "no_learning_content"}:
                    raise NoteError("source_changed", "预检选区已不可用，请重新选择来源", 409) from None
                raise
            if request.get("preflight_fingerprint") != preflight["fingerprint"]:
                raise NoteError("source_changed", "选区正文或来源已变化，请重新预检", 409)
            hint = request.get("structure_hint", "auto")
        stamp = now()
        draft = {"id": new_id("draft"), "schema_version": 1, "kind": "generation", "status": "preparing", "draft_revision": 1,
                 "conversation_id": snapshot["conversation_id"], "source_snapshot_ids": [snapshot["id"]], "structure_hint": hint,
                 "base_note_id": None, "base_note_revision": None, "job_id": new_id("notejob"), "parent_draft_id": retry,
                 "created_at": stamp, "updated_at": stamp, "content": None}
        # Resolve identity without constructing a model transport or persisting credentials.
        try:
            from config import get_model_role_config
            role = get_model_role_config()
            model_identity = {"provider_id": role.provider.provider_id, "model_id": role.model, "model_role": role.role.value}
        except Exception:
            model_identity = {"model_role": "reasoning", "model_id": "unavailable"}
        draft["generation"] = {**model_identity, "job_id": draft["job_id"], "prompt_version": PROMPT, "policy_version": POLICY, "generated_at": stamp}
        active_key = fingerprint({"conversation_id": snapshot["conversation_id"], "input_hash": snapshot["input_hash"], "selection": snapshot["selection"], "hint": hint, "model": model_identity, "policy": POLICY})
        receipt = self.store.register_generation(op, {"kind": "generation", **request}, snapshot, draft, active_key)
        self.audit("note_snapshot", op, "preparing", (receipt["draft_id"], receipt["snapshot_id"]))
        return receipt

    def draft(self, draft_id):
        draft = self.store.get("note_drafts", draft_id)
        job = self.jobs().get_job(draft["job_id"]) if draft.get("job_id") else None
        if job and job["status"] == "completed" and draft["status"] == "preparing" and not draft.get("recovery_error"):
            try:
                draft = self.store.publish_candidate(draft_id, job)
            except NoteError:
                with self.store.transaction() as conn:
                    draft = self.store._get(conn, "note_drafts", draft_id)
                    if draft["status"] == "preparing":
                        draft["recovery_error"] = "candidate_receipt_mismatch"
                        self.store.put_draft(conn, draft)
        public = {k:v for k,v in draft.items() if k not in {"candidate", "candidate_hash"}}
        snapshot = self.store.get("note_source_snapshots", draft["source_snapshot_ids"][0])
        public.update(job=job, sources=[{k:v for k,v in s.items() if k not in {"content", "learning_task"}} for s in snapshot["sources"]], warnings=snapshot["warnings"], chapter_options=snapshot.get("chapter_refs", []))
        return public

    def list_drafts(self, **filters):
        page = self.store.list(drafts=True, **filters)
        for summary in page["items"]:
            job = self.jobs().get_job(summary["job_id"]) if summary.get("job_id") else None
            summary["job"] = job
        return page

    def create_draft(self, *, kind, note_id=None, base_revision=None, snapshot_id=None):
        stamp = now()
        if kind == "edit":
            note = self.store.get("session_notes", note_id)
            if note["revision"] != base_revision or note["status"] != "active":
                raise NoteError("revision_conflict", "笔记版本已变化或已归档", 409)
            snapshot = self.store.get("note_source_snapshots", note["source_snapshot_ids"][0])
            content = {k: copy.deepcopy(note[k]) for k in FIELDS}
            content["quality"] = copy.deepcopy(note["quality"])
            base_id, base = note_id, base_revision
        elif kind == "manual":
            snapshot = self.store.get("note_source_snapshots", snapshot_id)
            # Only snapshots owned by an existing terminal generation request.
            with self.store.transaction() as conn:
                rows = conn.execute("SELECT document_json FROM note_drafts WHERE conversation_id=?", (snapshot["conversation_id"],)).fetchall()
            owners = [d for d in (json.loads(row[0]) for row in rows) if snapshot_id in d["source_snapshot_ids"] and d.get("job_id")]
            if not any(d.get("recovery_error") or (self.jobs().get_job(d["job_id"]) or {}).get("status") in {"failed", "interrupted", "cancelled"} for d in owners):
                raise NoteError("invalid_selection", "手动整理需要已失败、中断或取消的生成来源", 400)
            initial = {"title": snapshot["title_snapshot"][:200] or "学习笔记", "abstract": "", "subject": snapshot["subject"], "tags": [], "chapter_refs": snapshot.get("chapter_refs", []), "blocks": [{"block_id": new_id("noteblock"), "type": "paragraph", "data": {"markdown": "请根据保存的会话来源整理学习内容。"}}]}
            document, quality = validate_document(initial, snapshot)
            content = {**document, "quality": quality}
            base_id, base = None, None
        else:
            raise NoteError("invalid_document", "草稿类型无效")
        draft = {"id": new_id("draft"), "schema_version": 1, "kind": kind, "status": "editable", "draft_revision": 1, "conversation_id": snapshot["conversation_id"], "source_snapshot_ids": [snapshot["id"]], "content": content, "base_note_id": base_id, "base_note_revision": base, "job_id": None, "created_at": stamp, "updated_at": stamp}
        with self.store.transaction() as conn:
            self.store.put_draft(conn, draft)
        return self.draft(draft["id"])

    def patch_draft(self, draft_id, expected_revision, content):
        with self.store.transaction() as conn:
            draft = self.store._get(conn, "note_drafts", draft_id)
            if draft["status"] != "editable" or draft["draft_revision"] != expected_revision:
                raise NoteError("revision_conflict", "草稿已变化，请保留当前修改并重新载入", 409)
            snapshot = self.store._get(conn, "note_source_snapshots", draft["source_snapshot_ids"][0])
            known = {c["chapter_ref_id"] for c in snapshot.get("chapter_refs", []) + draft["content"].get("chapter_refs", [])}
            if isinstance(content, dict) and isinstance(content.get("chapter_refs"), list):
                if any(not isinstance(c, dict) or not isinstance(c.get("chapter_ref_id"), str) or (c.get("book_id") is not None and not isinstance(c["book_id"], str)) for c in content["chapter_refs"]):
                    raise NoteError("invalid_document", "章节引用字段无效")
                added = [c for c in content["chapter_refs"] if isinstance(c, dict) and c.get("chapter_ref_id") not in known]
                if added:
                    snapshot = {**snapshot, "chapter_refs": snapshot.get("chapter_refs", []) + self.chapters.validate_classification(added)}
            document, quality = validate_document(content, snapshot, previous=draft["content"])
            # Coverage belongs to the generated candidate; preserve it as historical review metadata.
            if draft["content"].get("quality", {}).get("coverage"):
                quality["generation_coverage"] = draft["content"]["quality"]["coverage"]
            draft.update(content={**document, "quality": quality}, updated_at=now(), draft_revision=draft["draft_revision"]+1)
            self.store.put_draft(conn, draft)
        return self.draft(draft_id)

    def save(self, draft_id, request):
        op_request = {"kind": "save", "draft_id": draft_id, **request}
        with self.store.transaction() as conn:
            receipt = self.store.receipt(conn, request["operation_id"], op_request)
            if receipt:
                return receipt
            draft = self.store._get(conn, "note_drafts", draft_id)
            if draft["status"] != "editable" or draft["draft_revision"] != request["expected_draft_revision"]:
                raise NoteError("revision_conflict", "草稿已变化或已保存", 409)
            snapshot = self.store._get(conn, "note_source_snapshots", draft["source_snapshot_ids"][0])
            document = {k:copy.deepcopy(draft["content"][k]) for k in FIELDS}
            validate_document(document, snapshot, previous=draft["content"])
            quality = draft["content"]["quality"]
            # Explicit Save publishes the current revision. Historical quality and
            # frozen sources remain unchanged; publication is not verification.
            stamp = now()
            if draft.get("base_note_id"):
                old = self.store._get(conn, "session_notes", draft["base_note_id"])
                if old["revision"] != draft["base_note_revision"] or request.get("base_note_revision") != old["revision"] or old["status"] != "active":
                    raise NoteError("revision_conflict", "正式笔记已被修改或归档，请保留草稿", 409)
                note = {**old, **document, "quality": quality, "revision": old["revision"]+1, "updated_at": stamp, "saved_at": stamp}
            else:
                if request.get("base_note_revision") is not None:
                    raise NoteError("revision_conflict", "新笔记不应指定旧版本", 409)
                note = {**document, "id": new_id("note"), "schema_version": 1, "status": "active", "revision": 1, "quality": quality, "source_snapshot_ids": draft["source_snapshot_ids"], "origins": [{"kind": "session", "conversation_id": snapshot["conversation_id"], "title_snapshot": snapshot["title_snapshot"], "source_snapshot_id": snapshot["id"], "selection": snapshot["selection"], "captured_at": snapshot["captured_at"]}], "generation": draft.get("generation"), "created_at": stamp, "updated_at": stamp, "saved_at": stamp}
            self.store.put_note(conn, note, "edit" if draft.get("base_note_id") else "create")
            draft.update(status="published", published_note_id=note["id"], published_revision=note["revision"], updated_at=stamp)
            self.store.put_draft(conn, draft)
            receipt = {"note_id": note["id"], "revision": note["revision"]}
            self.store.record(conn, request["operation_id"], op_request, receipt)
        self.audit("note_save", request["operation_id"], "saved", (receipt["note_id"], draft_id))
        return receipt

    def status(self, note_id, request):
        if request["status"] not in {"active", "archived"}:
            raise NoteError("invalid_document", "状态无效")
        op_request = {"kind": "status", "note_id": note_id, **request}
        with self.store.transaction() as conn:
            receipt = self.store.receipt(conn, request["operation_id"], op_request)
            if receipt:
                return receipt
            note = self.store._get(conn, "session_notes", note_id)
            if note["revision"] != request["expected_revision"]:
                raise NoteError("revision_conflict", "笔记版本已变化", 409)
            note.update(status=request["status"], revision=note["revision"]+1, updated_at=now(), saved_at=now())
            self.store.put_note(conn, note, request["status"])
            receipt = {"note_id": note_id, "revision": note["revision"], "status": note["status"]}
            self.store.record(conn, request["operation_id"], op_request, receipt)
        return receipt

    def discard(self, draft_id):
        draft = self.store.get("note_drafts", draft_id)
        if draft["status"] == "published":
            raise NoteError("revision_conflict", "已保存草稿不能用于删除正式笔记", 409)
        if draft.get("job_id"):
            job = self.jobs().get_job(draft["job_id"])
            if job and job["status"] in {"queued", "running", "cancelling"}:
                self.jobs().request_cancel(job["id"])
                raise NoteError("revision_conflict", "正在停止生成，请等待确认后丢弃", 409)
        with self.store.transaction() as conn:
            draft = self.store._get(conn, "note_drafts", draft_id)
            if draft["status"] == "published":
                raise NoteError("revision_conflict", "草稿已保存", 409)
            draft.update(status="discarded", updated_at=now())
            self.store.put_draft(conn, draft)
        return {"draft_id": draft_id, "status": "discarded"}

    def detail(self, note_id, revision=None):
        note = self.store.revisions(note_id, revision) if revision is not None else self.store.get("session_notes", note_id)
        snapshot = self.store.get("note_source_snapshots", note["source_snapshot_ids"][0])
        note["source_summary"] = {"captured_at": snapshot["captured_at"], "message_count": len(snapshot["sources"]), "warnings": snapshot["warnings"]}
        try:
            note["chapter_availability"] = {c["chapter_ref_id"]: self.chapters.availability(c) for c in note["chapter_refs"]}
        except Exception:
            note["chapter_availability"] = {c["chapter_ref_id"]: "unavailable" for c in note["chapter_refs"]}
        return note

    def source(self, identity, source_ref_id, *, draft=False, revision=None):
        doc = self.store.get("note_drafts" if draft else "session_notes", identity) if revision is None else self.store.revisions(identity, revision)
        for sid in doc["source_snapshot_ids"]:
            snapshot = self.store.get("note_source_snapshots", sid)
            if any(s["source_ref_id"] == source_ref_id for s in snapshot["sources"]):
                return source_detail(snapshot, source_ref_id, self.live_resolver)
        raise NoteError("invalid_source_ref", "来源不属于当前版本", 404)


def get_notes_service():
    from config import PROGRESS_PATH
    from pathlib import Path
    return SessionNoteService(SessionNoteStore(Path(PROGRESS_PATH) / "session_notes.db"))
