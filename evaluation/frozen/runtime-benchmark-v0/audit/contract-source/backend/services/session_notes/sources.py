"""Frozen source adapters. Source labels express traceability, never truth."""
import copy
import re

from memory.session_notes import fingerprint, new_id, NoteError, encode
from utils.thinking_filter import strip_thinking

EVIDENCE_FIELDS = {"book_id", "book_name", "chunk_id", "index_version", "canonical_hash", "source_block_ids", "section_path", "chapter", "section_title", "page_start", "page_end", "page_idx", "bbox", "source_kind", "text", "snippet", "excerpt", "support_text", "provenance_schema", "corpus_version", "content_fingerprint"}


def safe_text(text):
    value = strip_thinking(str(text or ""))
    value = re.sub(r"(?i)\b(?:sk-[A-Za-z0-9_-]{10,}|Bearer\s+[A-Za-z0-9_.-]{10,})", "[凭证已隐藏]", value)
    value = re.sub(r"(?i)((?:api[_-]?key|secret|password)\s*[=:]\s*)[^\s,;\"']+", r"\1[已隐藏]", value)
    return re.sub(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)[^\s\"<>]+", "[本地路径已隐藏]", value)


def public_message(raw):
    result = {k: copy.deepcopy(raw[k]) for k in ("id", "turn_id", "role", "created_at", "seq", "subject", "book_name", "answer_mode", "delivery_status", "evidence_support_status") if k in raw}
    result["content"] = safe_text(raw.get("content"))
    task = raw.get("learning_task") or {}
    result["learning_task"] = {"id": task.get("id"), "status": task.get("status", "unknown"), "verification": {k: v for k, v in (task.get("verification") or {}).items() if k in {"status", "reasons", "warnings", "checks"}}, "required_inputs": [{k: v for k, v in i.items() if k in {"id", "kind", "label", "status", "reason"}} for i in task.get("required_inputs", []) if isinstance(i, dict)]}
    result["citation_provenance"] = {k: v for k, v in (raw.get("citation_provenance") or {}).items() if k in {"status", "alignment", "mode", "aligned_source_ids", "warnings", "reason"}}
    return sanitize_metadata(result)


def sanitize_metadata(value):
    if isinstance(value, dict):
        return {k: sanitize_metadata(v) for k, v in value.items() if not re.search(r"(?i)(api.?key|secret|password|endpoint|file.?path|source_file)", k)}
    if isinstance(value, list):
        return [sanitize_metadata(v) for v in value]
    if isinstance(value, str):
        return safe_text(value)
    return value


def materialize(capture, chapter_resolver):
    snapshot = {k: copy.deepcopy(v) for k, v in capture.items() if k != "messages"}
    snapshot.update(id=new_id("snapshot"), sources=[], evidence=[], warnings=[])
    chapters = {}
    for raw in capture["messages"]:
        message = public_message(raw)
        sid = new_id("source")
        message.update(source_ref_id=sid, original_conversation_id=capture["conversation_id"], content_hash=fingerprint(raw), included=bool(message["content"].strip()))
        if raw.get("role") not in {"user", "assistant"}:
            message.update(included=False, exclusion_reason="non_learning_role")
        if not message["content"].strip():
            message.update(included=False, exclusion_reason="empty_or_placeholder")
        if raw.get("delivery_status") in {"error", "waiting"}:
            message.update(included=False, exclusion_reason="failed_or_placeholder")
        snapshot["sources"].append(message)
        reasons = []
        if str(raw.get("content", "")).startswith("📎") or any(isinstance(e, dict) and e.get("figure_id") for e in raw.get("sources", [])):
            reasons.append("image_input_not_owned")
        if raw.get("role") == "assistant" and raw.get("delivery_status", "complete") != "complete":
            reasons.append("incomplete_answer")
        if raw.get("evidence_support_status") in {"degraded", "unverified", "unsupported", "insufficient"} or message["learning_task"]["status"] in {"degraded", "unverified", "waiting_for_input"}:
            reasons.append("source_unverified")
        if any(i.get("status", "missing") == "missing" for i in message["learning_task"]["required_inputs"]):
            reasons.append("missing_required_input")
        for n, raw_e in enumerate(raw.get("sources") or []):
            if not isinstance(raw_e, dict):
                continue
            evidence = {k: copy.deepcopy(v) for k, v in raw_e.items() if k in EVIDENCE_FIELDS}
            evidence.update(evidence_ref_id=new_id("evidence"), source_ref_id=sid, original_e_id=raw_e.get("id") or f"E{n+1}")
            evidence["source_locations"] = [{k: v for k, v in loc.items() if k in {"block_id", "page_start", "page_end", "page", "bbox", "section_path"}} for loc in raw_e.get("source_locations", []) if isinstance(loc, dict)]
            for field in ("text", "snippet", "excerpt", "support_text"):
                if field in evidence:
                    evidence[field] = safe_text(evidence[field])
            evidence["snippet_status"] = "saved" if any(evidence.get(k) for k in ("text", "snippet", "excerpt", "support_text")) else "unknown"
            evidence = sanitize_metadata(evidence)
            snapshot["evidence"].append(evidence)
            if evidence["snippet_status"] == "unknown":
                reasons.append("historical_evidence_text_unknown")
            if not message["citation_provenance"] or message["citation_provenance"].get("status") not in {"aligned", "model_aligned"}:
                reasons.append("textbook_alignment_unknown")
            try:
                ref = chapter_resolver.resolve(evidence)
                chapters[ref["chapter_ref_id"]] = ref
            except Exception:
                reasons.append("chapter_unavailable")
        if reasons:
            snapshot["warnings"].append({"source_ref_id": sid, "reasons": sorted(set(reasons))})
    snapshot["chapter_refs"] = list(chapters.values())
    if len(encode(snapshot).encode("utf-8")) > 8 * 1024 * 1024:
        raise NoteError("needs_range_selection", "物化来源超过 8 MiB，请缩小完整轮次范围")
    return sanitize_metadata(snapshot)


def source_detail(snapshot, source_ref_id, resolver):
    source = next((s for s in snapshot["sources"] if s["source_ref_id"] == source_ref_id), None)
    if source is None:
        raise NoteError("invalid_source_ref", "来源不属于当前笔记", 404)
    try:
        live = resolver(source["original_conversation_id"], source["id"])
        target = live.get("target")
        if target:
            # seq is frozen position, not part of the persisted payload.
            comparable = {k: v for k, v in target.items() if k in {"id", "turn_id", "role", "content", "created_at", "subject", "book_name", "sources", "answer_mode", "delivery_status", "evidence_support_status", "learning_task", "citation_provenance"}}
            comparable["seq"] = source["seq"]
            if live["status"] != "moved" and fingerprint(comparable) != source["content_hash"]:
                live["status"] = "changed"
        locator = {"conversation_id": live["conversation_id"], "message_id": source["id"]} if target else None
        status = live["status"]
    except Exception:
        locator, status = None, "unavailable"
    return {"source": source, "evidence": [e for e in snapshot["evidence"] if e["source_ref_id"] == source_ref_id], "live_locator": locator, "status": status}
