"""Controlled tools over textbook, KG, mistakes, and review data."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from config import PROGRESS_PATH
from graph.safe_retrieval import get_safe_kg, get_safe_vector_store
from ingestion.chunk_roles import classify_chunk_role, normalize_role
from knowledge.concept_memory import ConceptMemory
from memory.exercise_bank import ExerciseRecord, get_exercise_bank
from memory.learning_events import get_learning_event_store
from memory.mistake_book import MistakeRecord, get_mistake_book
from utils.subject_catalog import subject_matches

from backend.tools.registry import ToolContext, ToolRegistry, ToolResult, ToolSpec


def _as_int(value: Any, default: int, low: int = 1, high: int = 50) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def _record_summary(record: MistakeRecord) -> dict:
    sm2 = record.sm2 or {}
    return {
        "id": record.id,
        "question_text": record.question_text,
        "subject": record.subject,
        "chapter": record.chapter,
        "source": record.source,
        "tags": record.tags,
        "mistake_type": record.mistake_type,
        "difficulty": record.difficulty,
        "next_review": sm2.get("next_review"),
        "interval": sm2.get("interval"),
        "linked_concepts": record.linked_concepts,
    }


def _exercise_summary(record: ExerciseRecord) -> dict:
    return {
        "id": record.id,
        "question_text": record.question_text[:600],
        "source": record.source,
        "subject": record.subject,
        "chapter": record.chapter,
        "tags": record.tags[:12],
        "question_type": record.question_type,
        "difficulty": record.difficulty,
        "linked_concepts": record.linked_concepts[:12],
        "status": record.status,
        "practice_count": record.practice_count,
        "last_practiced": record.last_practiced,
        "answer_available": bool(record.answer.strip()),
        "explanation_available": bool(record.explanation.strip()),
    }


def _parse_datetime(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _exercise_query_terms(query: str) -> list[str]:
    normalized = "".join(str(query or "").casefold().split())
    if not normalized:
        return []
    generic_phrases = (
        "请给我", "给我", "帮我", "按照", "根据", "最近的", "最近", "教材里的",
        "找几道", "找一道", "找", "练几道", "做几道", "做一道", "安排", "开始",
        "从简单到困难", "由易到难", "相关练习题", "相关习题", "相关题目", "相关",
        "练习题", "习题", "题目", "题库", "薄弱知识点", "薄弱点", "知识点",
        "练习一下", "开始练习", "练习", "practice", "exercise", "session",
    )
    core = normalized
    for phrase in generic_phrases:
        core = core.replace(phrase, "")
    core = "".join(character for character in core if character.isalnum() or character in "_.+-")
    if core.endswith("题"):
        core = core[:-1]
    terms = [core] if len(core) >= 2 else []
    if len(normalized) >= 2 and normalized != core:
        terms.append(normalized)
    return list(dict.fromkeys(terms))


def search_textbook(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult(False, message="query is required")
    book_name = str(args.get("book_name") or context.book_name or "").strip()
    chapter = str(args.get("chapter") or "").strip()
    limit = _as_int(args.get("limit"), 5, high=12)

    vs, error = get_safe_vector_store()
    if error:
        return ToolResult(False, data=[], message=f"vector store unavailable: {error}")

    snippets: list[dict] = []
    if chapter:
        docs = vs.search_chapter(chapter, query, k=limit, book_name=book_name)
        for doc in docs:
            snippets.append({
                "chapter": chapter,
                "chunk_id": doc.metadata.get("chunk_id", ""),
                "role": doc.metadata.get("role", ""),
                "page": doc.metadata.get("page_idx", doc.metadata.get("page", "")),
                "text": doc.page_content[:1200],
            })
    else:
        results = vs.search_all(query, k=min(3, limit), top_n=limit, book_name=book_name)
        for ch_name, docs in results.items():
            for doc in docs:
                snippets.append({
                    "chapter": ch_name,
                    "chunk_id": doc.metadata.get("chunk_id", ""),
                    "role": doc.metadata.get("role", ""),
                    "page": doc.metadata.get("page_idx", doc.metadata.get("page", "")),
                    "text": doc.page_content[:1200],
                })
                if len(snippets) >= limit:
                    break
            if len(snippets) >= limit:
                break

    return ToolResult(True, data={"book_name": book_name, "snippets": snippets})


def find_textbook_examples(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    """Find example-role textbook chunks without treating generated exercises as sources."""
    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult(False, message="query is required")
    book_name = str(args.get("book_name") or context.book_name or "").strip()
    chapter = str(args.get("chapter") or "").strip()
    limit = _as_int(args.get("limit"), 5, high=10)

    vs, error = get_safe_vector_store()
    if error:
        return ToolResult(False, data=[], message=f"vector store unavailable: {error}")

    def search(*, role_filter: bool) -> list[tuple[str, Any]]:
        filter_value = {"role": "example"} if role_filter else None
        if chapter:
            docs = vs.search_chapter(
                chapter,
                query,
                k=max(8, limit * 3),
                filter=filter_value,
                book_name=book_name,
            )
            return [(chapter, doc) for doc in docs]
        results = vs.search_all(
            query,
            k=max(4, limit),
            top_n=min(6, max(2, limit)),
            filter=filter_value,
            book_name=book_name,
        )
        return [
            (chapter_name, doc)
            for chapter_name, docs in results.items()
            for doc in docs
        ]

    candidates = search(role_filter=True)
    if len(candidates) < limit:
        candidates.extend(search(role_filter=False))

    examples: list[dict] = []
    seen: set[str] = set()
    for chapter_name, doc in candidates:
        metadata = getattr(doc, "metadata", {}) or {}
        text = str(
            metadata.get("raw_content")
            or getattr(doc, "page_content", "")
            or ""
        ).strip()
        role = normalize_role(metadata.get("role") or metadata.get("semantic_role"))
        if role != "example" and classify_chunk_role(text) != "example":
            continue
        chunk_id = str(metadata.get("chunk_id") or "")
        dedupe_key = chunk_id or " ".join(text.split())[:300]
        if not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        examples.append({
            "chapter": chapter_name,
            "chunk_id": chunk_id,
            "section_title": metadata.get("section_title", ""),
            "section_path": metadata.get("section_path", []),
            "page": metadata.get("page_idx", metadata.get("page", "")),
            "role": "example",
            "text": text[:1200],
        })
        if len(examples) >= limit:
            break

    return ToolResult(True, data={
        "book_name": book_name,
        "query": query,
        "examples": examples,
    })


def search_concepts(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult(False, message="query is required")
    book_name = str(args.get("book_name") or context.book_name or "").strip()
    limit = _as_int(args.get("limit"), 5, high=15)

    kg, error = get_safe_kg(book_name)
    if error:
        return ToolResult(False, data=[], message=f"knowledge graph unavailable: {error}")

    matches = []
    for score, concept in kg.search_concept(query, k=limit):
        name = concept.get("canonical_name") or concept.get("name") or ""
        detail = kg.get_concept_detail(name) if name else None
        matches.append({
            "name": name,
            "score": score,
            "aliases": concept.get("aliases", []),
            "definition": (detail or {}).get("definition", concept.get("definition", "")),
            "related_formulas": (detail or {}).get("related_formulas", [])[:5],
            "path": kg.find_path(name) if name else [],
        })
    return ToolResult(True, data={"book_name": book_name, "concepts": matches})


def get_due_mistakes(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    book_name = str(args.get("book_name") or context.book_name or "default").strip()
    subject = str(args.get("subject") or context.subject or "").strip()
    limit = _as_int(args.get("limit"), 10, high=50)
    mb = get_mistake_book(book_name, str(PROGRESS_PATH))
    records = mb.get_due(subject=subject or None)[:limit]
    return ToolResult(True, data={"book_name": book_name, "subject": subject, "mistakes": [_record_summary(r) for r in records]})


def get_mistake_stats(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    book_name = str(args.get("book_name") or context.book_name or "default").strip()
    subject = str(args.get("subject") or context.subject or "").strip()
    mb = get_mistake_book(book_name, str(PROGRESS_PATH))
    return ToolResult(True, data={
        "book_name": book_name,
        "subject": subject,
        "stats": mb.get_stats(subject=subject or None),
        "weak_points": mb.get_weak_points(subject=subject or None, top_n=_as_int(args.get("limit"), 8, high=30)),
    })


def get_weak_concepts(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    """Merge explicit ConceptMemory weakness with concept-linked mistake evidence."""
    book_name = str(args.get("book_name") or context.book_name or "default").strip()
    subject = str(args.get("subject") or context.subject or "").strip()
    limit = _as_int(args.get("limit"), 8, high=30)
    merged: dict[str, dict] = {}
    errors: dict[str, str] = {}

    try:
        concept_weak_points = ConceptMemory(book_name).get_weak_points()
    except Exception as exc:
        concept_weak_points = []
        errors["concept_memory"] = str(exc)
    for item in concept_weak_points:
        name = str(item.get("name") or "").strip()
        subjects = [str(value) for value in item.get("subjects", []) if str(value).strip()]
        if not name or (subject and subjects and not any(subject_matches(value, subject) for value in subjects)):
            continue
        merged[name] = {
            "name": name,
            "explicit_weak": True,
            "weak_reason": str(item.get("weak_reason") or ""),
            "exposure_count": int(item.get("exposure_count", 0) or 0),
            "mastery_level": int(item.get("mastery_level", 0) or 0),
            "last_exposed_at": str(item.get("last_exposed_at") or ""),
            "last_reviewed_at": str(item.get("last_reviewed_at") or ""),
            "source_chapters": list(item.get("source_chapters") or [])[:8],
            "mistake_count": 0,
            "mistake_ids": [],
            "reasons": ["concept_memory_weak"],
        }

    try:
        mistake_book = get_mistake_book(book_name, str(PROGRESS_PATH))
        records = mistake_book.list_all(subject=subject or None, limit=5000)
    except Exception as exc:
        records = []
        errors["mistakes"] = str(exc)
    for record in records:
        names = {
            str(item.get("name") or "").strip()
            for item in record.linked_concepts or []
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        }
        names.update(str(tag).strip() for tag in record.tags or [] if str(tag).strip())
        for name in names:
            target = merged.setdefault(name, {
                "name": name,
                "explicit_weak": False,
                "weak_reason": "",
                "exposure_count": 0,
                "mastery_level": 0,
                "last_exposed_at": "",
                "last_reviewed_at": "",
                "source_chapters": [],
                "mistake_count": 0,
                "mistake_ids": [],
                "reasons": [],
            })
            target["mistake_count"] += 1
            if record.id not in target["mistake_ids"] and len(target["mistake_ids"]) < 8:
                target["mistake_ids"].append(record.id)
            if record.chapter and record.chapter not in target["source_chapters"]:
                target["source_chapters"].append(record.chapter)
            if "linked_mistakes" not in target["reasons"]:
                target["reasons"].append("linked_mistakes")

    concepts = list(merged.values())
    for item in concepts:
        item["priority"] = (
            (100 if item["explicit_weak"] else 0)
            + min(80, int(item["mistake_count"]) * 12)
            + min(20, int(item["exposure_count"]))
            - min(20, int(item["mastery_level"]) * 4)
        )
    concepts.sort(key=lambda item: (-item["priority"], -item["mistake_count"], item["name"]))
    return ToolResult(True, data={
        "book_name": book_name,
        "subject": subject,
        "weak_concepts": concepts[:limit],
        "errors": errors,
    })


def search_exercises(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    """Search exercise assets without leaking solutions into the planning step."""
    query = str(args.get("query") or "").strip()
    book_name = str(args.get("book_name") or context.book_name or "default").strip()
    subject = str(args.get("subject") or context.subject or "").strip()
    chapter = str(args.get("chapter") or "").strip()
    tag = str(args.get("tag") or "").strip()
    status = str(args.get("status") or "").strip()
    limit = _as_int(args.get("limit"), 8, high=30)

    bank = get_exercise_bank(book_name, str(PROGRESS_PATH))
    records = bank.list_all(
        subject=subject or None,
        chapter=chapter or None,
        tag=tag or None,
        status=status,
        limit=2000,
    )
    query_terms = _exercise_query_terms(query)
    status_rank = {"needs_review": 0, "practicing": 1, "new": 2, "mastered": 3}
    ranked: list[tuple[int, ExerciseRecord]] = []
    for record in records:
        concepts = [
            str(item.get("name") or "")
            for item in record.linked_concepts or []
            if isinstance(item, dict)
        ]
        fields = {
            "question": record.question_text,
            "chapter": record.chapter or "",
            "tags": " ".join(record.tags or []),
            "concepts": " ".join(concepts),
            "source": record.source,
        }
        normalized_fields = {
            key: "".join(value.casefold().split())
            for key, value in fields.items()
        }
        score = 0
        if query_terms:
            if any(term in normalized_fields["concepts"] for term in query_terms):
                score += 8
            if any(term in normalized_fields["tags"] for term in query_terms):
                score += 7
            if any(term in normalized_fields["chapter"] for term in query_terms):
                score += 5
            if any(term in normalized_fields["question"] for term in query_terms):
                score += 4
            if any(term in normalized_fields["source"] for term in query_terms):
                score += 1
            if score == 0:
                continue
        ranked.append((score, record))

    ranked.sort(key=lambda item: (
        -item[0],
        status_rank.get(item[1].status, 2),
        item[1].practice_count,
        item[1].created_at,
    ))
    return ToolResult(True, data={
        "book_name": book_name,
        "query": query,
        "filters": {
            "subject": subject,
            "chapter": chapter,
            "tag": tag,
            "status": status,
        },
        "exercises": [_exercise_summary(record) for _, record in ranked[:limit]],
        "solution_fields_omitted": True,
    })


def get_recent_progress(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    """Summarize the append-only learning event timeline for a bounded period."""
    book_name = str(args.get("book_name") or context.book_name or "default").strip()
    subject = str(args.get("subject") or context.subject or "").strip()
    days = _as_int(args.get("days"), 7, high=31)
    limit = _as_int(args.get("limit"), 12, high=50)
    cutoff = datetime.now() - timedelta(days=days)
    events = get_learning_event_store().list_recent(
        book_name=book_name,
        subject=subject,
        limit=max(200, limit * 10),
    )
    recent = [event for event in events if (_parse_datetime(event.timestamp) or datetime.min) >= cutoff]
    event_counts = Counter(event.event_type for event in recent)
    concept_counts = Counter(
        concept
        for event in recent
        for concept in (event.concept_names or [])
        if str(concept).strip()
    )
    recent_items = []
    for event in recent[:limit]:
        payload = event.payload if isinstance(event.payload, dict) else {}
        recent_items.append({
            "id": event.id,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "source_type": event.source_type,
            "source_id": event.source_id,
            "concept_names": (event.concept_names or [])[:12],
            "question": str(payload.get("question") or "")[:240],
            "quality": payload.get("quality"),
            "status": payload.get("status"),
        })
    return ToolResult(True, data={
        "book_name": book_name,
        "subject": subject,
        "range_days": days,
        "summary": {
            "total_events": len(recent),
            "qa_count": event_counts.get("chat_qa", 0),
            "mistakes_added": event_counts.get("mistake_added", 0),
            "mistakes_reviewed": event_counts.get("mistake_reviewed", 0),
            "exercises_added": event_counts.get("exercise_added", 0),
            "exercises_practiced": event_counts.get("exercise_practiced", 0),
            "event_counts": dict(event_counts),
        },
        "top_concepts": [
            {"name": name, "count": count}
            for name, count in concept_counts.most_common(10)
        ],
        "recent_events": recent_items,
    })


def build_review_plan(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    book_name = str(args.get("book_name") or context.book_name or "default").strip()
    subject = str(args.get("subject") or context.subject or "").strip()
    limit = _as_int(args.get("limit"), 8, high=20)

    mb = get_mistake_book(book_name, str(PROGRESS_PATH))
    stats = mb.get_stats(subject=subject or None)
    due = mb.get_due(subject=subject or None)
    weak_points = mb.get_weak_points(subject=subject or None, top_n=limit)

    concept_queue = []
    concept_stats = {}
    try:
        from knowledge.concept_memory import ConceptMemory

        cm = ConceptMemory(book_name)
        concept_queue = cm.get_review_queue(limit=limit)
        concept_stats = cm.get_stats()
    except Exception as exc:
        concept_stats = {"error": str(exc)}

    mistake_items = [
        {
            "type": "mistake",
            "priority": 100 - index,
            "reason": "due_review",
            "item": _record_summary(record),
        }
        for index, record in enumerate(due[:limit])
    ]
    concept_items = [
        {
            "type": "concept",
            "priority": 70 - index,
            "reason": item.get("reason", "review_queue"),
            "item": item,
        }
        for index, item in enumerate(concept_queue[:limit])
    ]
    weak_items = [
        {
            "type": "weak_point",
            "priority": 50 - index,
            "reason": "mistake_statistics",
            "item": item,
        }
        for index, item in enumerate(weak_points[:limit])
    ]

    plan = sorted(mistake_items + concept_items + weak_items, key=lambda x: x["priority"], reverse=True)[:limit]
    return ToolResult(True, data={
        "book_name": book_name,
        "subject": subject,
        "summary": {
            "due_mistakes": len(due),
            "total_mistakes": stats.get("total", 0),
            "weak_points": len(weak_points),
            "concept_stats": concept_stats,
        },
        "plan": plan,
    })


def link_concepts(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    text = str(args.get("text") or args.get("query") or "").strip()
    if not text:
        return ToolResult(False, message="text is required")
    return search_concepts(context, {"query": text, "limit": args.get("limit", 5), "book_name": args.get("book_name")})


def propose_add_mistake(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    question_text = str(args.get("question_text") or args.get("question") or "").strip()
    if not question_text:
        return ToolResult(False, message="question_text is required")
    payload = {
        "question_text": question_text,
        "user_answer": str(args.get("user_answer") or ""),
        "correct_answer": str(args.get("correct_answer") or ""),
        "source": str(args.get("source") or "agent_proposal"),
        "subject": str(args.get("subject") or context.subject or ""),
        "chapter": str(args.get("chapter") or ""),
        "tags": str(args.get("tags") or ""),
        "mistake_type": args.get("mistake_type") if isinstance(args.get("mistake_type"), list) else [],
        "difficulty": _as_int(args.get("difficulty"), 3, high=5),
        "explanation": str(args.get("explanation") or ""),
    }
    return ToolResult(
        True,
        data={"preview": payload},
        message="pending user confirmation",
        pending_action={"type": "add_mistake", "payload": payload},
    )


def propose_concept_review(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    name = str(args.get("name") or args.get("concept") or "").strip()
    if not name:
        return ToolResult(False, message="name is required")
    payload = {
        "name": name,
        "quality": _as_int(args.get("quality"), 4, low=0, high=5),
        "note": str(args.get("note") or "agent_proposal"),
        "book_name": str(args.get("book_name") or context.book_name or ""),
    }
    return ToolResult(
        True,
        data={"preview": payload},
        message="pending user confirmation",
        pending_action={"type": "mark_concept_reviewed", "payload": payload},
    )


def propose_practice_session(context: ToolContext, args: dict[str, Any]) -> ToolResult:
    """Preview a stable set of exercise ids; do not create a session yet."""
    book_name = str(args.get("book_name") or context.book_name or "default").strip()
    subject = str(args.get("subject") or context.subject or "").strip()
    chapter = str(args.get("chapter") or "").strip()
    tag = str(args.get("tag") or "").strip()
    status = str(args.get("status") or "").strip()
    query = str(args.get("query") or "").strip()
    limit = _as_int(args.get("limit"), 5, high=30)
    shuffle = _as_bool(args.get("shuffle"), False)
    result = search_exercises(context, {
        "query": query,
        "book_name": book_name,
        "subject": subject,
        "chapter": chapter,
        "tag": tag,
        "status": status,
        "limit": limit,
    })
    exercises = (result.data or {}).get("exercises", []) if result.success else []
    if not result.success:
        return result
    if not exercises:
        return ToolResult(
            False,
            data={"preview": {"exercise_count": 0, "exercises": []}},
            message="no exercises matched the requested practice scope",
        )
    payload = {
        "book_name": book_name,
        "subject": subject,
        "chapter": chapter,
        "tag": tag,
        "status": status,
        "query": query,
        "limit": limit,
        "shuffle": shuffle,
        "exercise_ids": [item["id"] for item in exercises],
    }
    return ToolResult(
        True,
        data={
            "preview": {
                "exercise_count": len(exercises),
                "exercises": exercises,
                "solution_fields_omitted": True,
            },
        },
        message="pending user confirmation",
        pending_action={"type": "create_practice_session", "payload": payload},
    )


def summarize_learning_evidence(tool_outputs: list[dict]) -> dict:
    calls = Counter(item.get("tool") for item in tool_outputs)
    pending = [item.get("result", {}).get("pending_action") for item in tool_outputs if item.get("result", {}).get("pending_action")]
    return {
        "tool_counts": dict(calls),
        "pending_actions": pending,
        "has_textbook_evidence": any(item.get("tool") == "search_textbook" and item.get("result", {}).get("data", {}).get("snippets") for item in tool_outputs),
        "has_review_evidence": any(item.get("tool") in {"get_due_mistakes", "build_review_plan", "get_mistake_stats"} for item in tool_outputs),
    }


def register_learning_tools(registry: ToolRegistry):
    registry.register(ToolSpec(
        name="search_textbook",
        description="Search textbook chunks from the local vector store.",
        parameters={"query": "str", "book_name": "str?", "chapter": "str?", "limit": "int?"},
        read_only=True,
        handler=search_textbook,
    ))
    registry.register(ToolSpec(
        name="search_concepts",
        description="Search local knowledge graph concepts and related formulas.",
        parameters={"query": "str", "book_name": "str?", "limit": "int?"},
        read_only=True,
        handler=search_concepts,
    ))
    registry.register(ToolSpec(
        name="find_textbook_examples",
        description="Find source-grounded textbook example chunks for a concept or method.",
        parameters={"query": "str", "book_name": "str?", "chapter": "str?", "limit": "int?"},
        read_only=True,
        handler=find_textbook_examples,
    ))
    registry.register(ToolSpec(
        name="link_concepts",
        description="Link free text to likely knowledge graph concepts.",
        parameters={"text": "str", "book_name": "str?", "limit": "int?"},
        read_only=True,
        handler=link_concepts,
    ))
    registry.register(ToolSpec(
        name="get_due_mistakes",
        description="Read due mistake reviews from the SM-2 queue.",
        parameters={"book_name": "str?", "subject": "str?", "limit": "int?"},
        read_only=True,
        handler=get_due_mistakes,
    ))
    registry.register(ToolSpec(
        name="get_mistake_stats",
        description="Read mistake statistics and weak points.",
        parameters={"book_name": "str?", "subject": "str?", "limit": "int?"},
        read_only=True,
        handler=get_mistake_stats,
    ))
    registry.register(ToolSpec(
        name="get_weak_concepts",
        description="Read weak concepts merged from ConceptMemory and linked mistake evidence.",
        parameters={"book_name": "str?", "subject": "str?", "limit": "int?"},
        read_only=True,
        handler=get_weak_concepts,
    ))
    registry.register(ToolSpec(
        name="search_exercises",
        description="Search the local exercise bank without exposing answers or explanations.",
        parameters={"query": "str?", "book_name": "str?", "subject": "str?", "chapter": "str?", "tag": "str?", "status": "str?", "limit": "int?"},
        read_only=True,
        handler=search_exercises,
    ))
    registry.register(ToolSpec(
        name="get_recent_progress",
        description="Summarize recent chat, mistake, exercise, and concept activity from the learning event log.",
        parameters={"book_name": "str?", "subject": "str?", "days": "int?", "limit": "int?"},
        read_only=True,
        handler=get_recent_progress,
    ))
    registry.register(ToolSpec(
        name="build_review_plan",
        description="Build a read-only review plan from due mistakes, weak points, and concept memory.",
        parameters={"book_name": "str?", "subject": "str?", "limit": "int?"},
        read_only=True,
        handler=build_review_plan,
    ))
    registry.register(ToolSpec(
        name="propose_add_mistake",
        description="Prepare an add-mistake action for user confirmation; does not write data.",
        parameters={"question_text": "str", "user_answer": "str?", "correct_answer": "str?", "subject": "str?", "chapter": "str?"},
        read_only=True,
        handler=propose_add_mistake,
    ))
    registry.register(ToolSpec(
        name="propose_concept_review",
        description="Prepare a concept-review action for user confirmation; does not write data.",
        parameters={"name": "str", "quality": "int?", "note": "str?"},
        read_only=True,
        handler=propose_concept_review,
    ))
    registry.register(ToolSpec(
        name="propose_practice_session",
        description="Prepare a bounded practice session for user confirmation; does not create it.",
        parameters={"query": "str?", "book_name": "str?", "subject": "str?", "chapter": "str?", "tag": "str?", "status": "str?", "limit": "int?", "shuffle": "bool?"},
        read_only=True,
        handler=propose_practice_session,
    ))
