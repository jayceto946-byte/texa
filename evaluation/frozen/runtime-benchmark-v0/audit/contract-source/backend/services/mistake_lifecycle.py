"""Deterministic mistake status projections from confirmed, durable facts."""
from __future__ import annotations

from datetime import date

from memory.mistake_book import MistakeRecord


def project_mistake(record: MistakeRecord, attempts: list[dict], *, today: date | None = None) -> dict:
    current_date = today or date.today()
    ordered = sorted(attempts, key=lambda item: (item.get("created_at", ""), item.get("id", "")))
    redos = [item for item in ordered if item.get("kind") == "redo"]
    valid = [item for item in redos if item.get("judgement_source") in {"user_confirmed", "deterministic"} and not item.get("hint_used") and item.get("result") in {"wrong", "partial", "independent_correct"} and item.get("question_revision") == record.content_revision]
    last_failure_time = max((item.get("created_at", "") for item in ordered if item.get("result") in {"wrong", "partial"} and item.get("question_revision") == record.content_revision), default="")
    correct_after_failure = [item for item in valid if item.get("created_at", "") > last_failure_time and item.get("result") == "independent_correct" and item.get("answer", "").strip()]
    evidence_mastered = False
    for latest in reversed(correct_after_failure[1:]):
        if not latest.get("was_due"):
            continue
        try:
            latest_day = date.fromisoformat(latest["created_at"][:10])
            evidence_mastered = any((latest_day - date.fromisoformat(first["created_at"][:10])).days >= 6 for first in correct_after_failure if first["created_at"] < latest["created_at"])
        except (KeyError, ValueError):
            evidence_mastered = False
        if evidence_mastered:
            break
    recent = valid[-3:]
    repeat_wrong = (
        len(recent) >= 2
        and sum(item.get("result") in {"wrong", "partial"} for item in recent) >= 2
        and (not valid or valid[-1].get("result") in {"wrong", "partial"}
             or last_failure_time > valid[-1].get("created_at", ""))
    )
    if evidence_mastered or record.manual_mastered:
        mastery = "mastered"
    elif correct_after_failure:
        mastery = "consolidating"
    else:
        mastery = "unresolved"
    due = bool(record.sm2 and record.sm2.get("next_review", "9999-12-31") <= current_date.isoformat())
    eligible = record.visibility == "active" and record.content_status != "needs_correction"
    pending_reason = ""
    if record.content_status == "needs_correction":
        pending_reason = "校对题目关键内容"
    elif record.diagnosis_status == "suggested":
        pending_reason = "确认错因建议"
    return {
        "content_status": record.content_status,
        "diagnosis_status": record.diagnosis_status,
        "mastery_status": mastery,
        "mastery_source": "redo_evidence" if evidence_mastered else "manual" if record.manual_mastered else "none",
        "review_status": "suspended" if not eligible else "due" if due else "scheduled" if record.sm2 else "unscheduled",
        "repeat_wrong": repeat_wrong,
        "pending_reason": pending_reason,
        "visibility": record.visibility,
    }
