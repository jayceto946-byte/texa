"""Pure helpers for knowledge-graph learning summaries."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable


def parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def days_since(value: str, *, now: datetime | None = None) -> int | None:
    parsed = parse_datetime(value)
    if not parsed:
        return None
    reference = now or datetime.now()
    if parsed.tzinfo is None and reference.tzinfo is not None:
        parsed = parsed.replace(tzinfo=reference.tzinfo)
    elif parsed.tzinfo is not None and reference.tzinfo is None:
        reference = reference.replace(tzinfo=parsed.tzinfo)
    return max(0, (reference - parsed).days)


def mistake_summary(record: Any) -> dict:
    sm2 = getattr(record, "sm2", {}) or {}
    return {
        "id": record.id,
        "question_text": record.question_text,
        "source": record.source,
        "subject": record.subject,
        "chapter": record.chapter,
        "tags": record.tags,
        "mistake_type": record.mistake_type,
        "next_review": sm2.get("next_review"),
        "interval": sm2.get("interval"),
        "review_history": record.review_history,
        "linked_concepts": record.linked_concepts,
    }


def _normalize_question(value: str) -> str:
    return " ".join(str(value or "").split())


def _legacy_concept_match(concept_name: str, text: str) -> bool:
    """Match legacy unstructured records without reintroducing one-char noise."""
    concept = _normalize_question(concept_name).casefold()
    haystack = _normalize_question(text).casefold()
    return len(concept) >= 2 and concept in haystack


def _legacy_question_match(question: str, texts: Iterable[str]) -> bool:
    normalized_question = _normalize_question(question).casefold()
    if len(normalized_question) < 2:
        return False
    for text in texts:
        normalized_text = _normalize_question(text).casefold()
        if not normalized_text:
            continue
        shorter, longer = sorted(
            (normalized_question, normalized_text),
            key=len,
        )
        if (
            shorter in longer
            and len(shorter) >= 4
            and len(shorter) / len(longer) >= 0.75
        ):
            return True
    return False


def _build_mistake_indexes(
    records: list[Any],
) -> tuple[
    dict[str, list[dict]],
    dict[str, str],
    list[tuple[dict, tuple[str, str, str]]],
]:
    by_concept: dict[str, list[dict]] = defaultdict(list)
    question_ids: dict[str, str] = {}
    legacy_records: list[tuple[dict, tuple[str, str, str]]] = []

    for record in records:
        summary = mistake_summary(record)
        linked_names = {
            str(concept.get("name", "")).strip()
            for concept in getattr(record, "linked_concepts", []) or []
            if str(concept.get("name", "")).strip()
        }
        explicit_names = linked_names | {
            str(tag).strip()
            for tag in getattr(record, "tags", []) or []
            if str(tag).strip()
        }
        for concept_name in explicit_names:
            by_concept[concept_name].append(summary)

        for text in (
            getattr(record, "question_text", ""),
            getattr(record, "ocr_text", ""),
        ):
            normalized = _normalize_question(text)
            if normalized:
                question_ids.setdefault(normalized, record.id)
        legacy_records.append((
            summary,
            (
                str(getattr(record, "question_text", "") or ""),
                str(getattr(record, "ocr_text", "") or ""),
                str(getattr(record, "explanation", "") or ""),
            ),
        ))

    return dict(by_concept), question_ids, legacy_records


def build_concept_review_plan(
    concepts: dict,
    strict_exposures: list[dict],
    concept_counts,
    mistake_weak_points: list[dict],
    mistake_records: Iterable[Any],
    *,
    limit: int = 8,
    weak_names: set[str] | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Build deterministic review cards from already-loaded domain data."""
    reference = now or datetime.now()
    records = list(mistake_records)
    weak_names = weak_names if weak_names is not None else {
        name for name, info in concepts.items() if info.get("weak_flag")
    }
    mistake_counts = {
        item.get("name", ""): int(item.get("count", 0) or 0)
        for item in mistake_weak_points
    }
    candidate_names = (
        set(weak_names)
        | {name for name, _ in concept_counts.most_common(12)}
        | {name for name, count in mistake_counts.items() if count > 0}
    )

    (
        mistakes_by_concept,
        mistake_ids_by_question,
        legacy_mistake_records,
    ) = _build_mistake_indexes(records)
    review_items = []
    for name in candidate_names:
        if not name:
            continue
        info = concepts.get(name, {})
        if str(info.get("last_reviewed_at", ""))[:10] == reference.date().isoformat():
            continue
        exposure_count = int(info.get("exposure_count", 0) or concept_counts.get(name, 0) or 0)
        days_since_seen = days_since(info.get("last_exposed_at", ""), now=reference)
        days_since_review = days_since(info.get("last_reviewed_at", ""), now=reference)
        related_mistakes = mistakes_by_concept.get(name, [])
        if not related_mistakes:
            related_mistakes = [
                summary
                for summary, texts in legacy_mistake_records
                if any(_legacy_concept_match(name, text) for text in texts)
            ]
        related_mistakes = related_mistakes[:50]

        recent_questions = []
        seen_questions = set()
        for exposure in reversed(strict_exposures):
            if exposure.get("concept") != name:
                continue
            question = (exposure.get("question") or "").strip()
            if not question or question in seen_questions:
                continue
            seen_questions.add(question)
            normalized_question = _normalize_question(question)
            mistake_id = mistake_ids_by_question.get(normalized_question, "")
            if not mistake_id:
                mistake_id = next(
                    (
                        summary["id"]
                        for summary, texts in legacy_mistake_records
                        if _legacy_question_match(question, texts)
                    ),
                    "",
                )
            recent_questions.append({
                "question": question,
                "source": (
                    "mistake"
                    if exposure.get("source") == "mistake" or exposure.get("intent") == "mistake"
                    else "qa"
                ),
                "timestamp": exposure.get("timestamp", ""),
                "weak": bool(exposure.get("weak")),
                "mistake_id": mistake_id,
            })
            if len(recent_questions) >= 3:
                break

        textbook_snippets = [
            {"type": "chapter", "text": chapter, "chapter": chapter}
            for chapter in [
                str(chapter)
                for chapter in info.get("source_chapters", [])
                if str(chapter).strip()
            ][:4]
        ]

        reasons = []
        priority = 0
        if name in weak_names:
            reasons.append("已标记为薄弱概念")
            priority += 45
        if related_mistakes:
            reasons.append(f"关联 {len(related_mistakes)} 道错题")
            priority += 30 + len(related_mistakes) * 4
        elif mistake_counts.get(name, 0):
            reasons.append(f"错题统计出现 {mistake_counts[name]} 次")
            priority += 25
        if days_since_seen is not None and days_since_seen >= 7:
            reasons.append(f"{days_since_seen} 天未接触")
            priority += min(30, days_since_seen)
        if exposure_count >= 2:
            reasons.append(f"累计接触 {exposure_count} 次")
            priority += min(15, exposure_count * 2)
        if days_since_review is None:
            reasons.append("还没有明确复习记录")
            priority += 8
        elif days_since_review >= 7:
            reasons.append(f"上次复习已过 {days_since_review} 天")
            priority += min(20, days_since_review)
        if recent_questions:
            priority += 4
        if not reasons:
            continue

        review_items.append({
            "name": name,
            "priority": priority,
            "reasons": reasons[:4],
            "days_since_seen": days_since_seen,
            "days_since_review": days_since_review,
            "exposure_count": exposure_count,
            "mastery_level": info.get("mastery_level", 0),
            "weak": name in weak_names,
            "recent_questions": recent_questions,
            "related_mistakes": related_mistakes,
            "textbook_snippets": textbook_snippets[:3],
        })

    review_items.sort(
        key=lambda item: (-item["priority"], -item["exposure_count"], item["name"])
    )
    return review_items[:limit]
