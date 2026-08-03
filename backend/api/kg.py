"""Knowledge Graph API — 知识图谱


包装 knowledge/knowledge_graph.py 和 knowledge/kg_visualizer.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from backend.schemas import KGGraphOut, KGRefreshOut
from config import PROGRESS_PATH
from backend.job_manager import get_job_manager
from backend.services.dependency_cache import DependencyTTLCache
from backend.services.kg_learning_summary import (
    build_concept_review_plan,
    days_since,
    mistake_summary,
    parse_datetime,
)
from knowledge.kg_enhancement import estimate_enhancement
from backend.services.kg_enhancement_jobs import KG_ENHANCEMENT_JOB_TYPE, start_kg_enhancement_job
_learning_summary_cache = DependencyTTLCache(ttl_seconds=5.0)
from utils.path_safety import safe_book_name, safe_child_path

router = APIRouter(prefix="/kg", tags=["knowledge-graph"])


class KGEnhancementRequest(BaseModel):
    book_name: str
    allow_external_llm: bool = False


@router.get("/enhance/estimate")
def get_enhancement_estimate(book_name: str = ""):
    if not book_name:
        return {"success": False, "message": "Please select a textbook"}
    try:
        return {"success": True, "data": estimate_enhancement(book_name)}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


@router.post("/enhance")
def start_enhancement(req: KGEnhancementRequest):
    if not req.allow_external_llm:
        return {"success": False, "message": "Explicit consent is required before sending selected textbook excerpts to the configured external LLM"}
    try:
        job, created = start_kg_enhancement_job(
            req.book_name, allow_external_llm=req.allow_external_llm,
        )
    except (PermissionError, ValueError) as exc:
        return {"success": False, "message": str(exc)}
    return {
        "success": True,
        "message": "\u6559\u6750\u6982\u5ff5\u7d22\u5f15\u63d0\u53d6\u5df2\u542f\u52a8" if created else "\u8be5\u6559\u6750\u5df2\u6709\u6982\u5ff5\u63d0\u53d6\u4efb\u52a1\u6b63\u5728\u8fd0\u884c",
        "job_id": job["id"],
        "data": job,
    }


@router.get("/enhance/jobs/{job_id}")
def get_enhancement_job(job_id: str):
    job = get_job_manager().get_job(job_id, job_type=KG_ENHANCEMENT_JOB_TYPE)
    if not job:
        return {"success": False, "message": "Knowledge enhancement job not found"}
    return {"success": True, "data": job}

def _kg_html_path(book_name: str) -> Path:
    return safe_child_path(PROGRESS_PATH, safe_book_name(book_name), "kg_graph.html")


@router.get("/graph")
def get_kg_graph(book_name: str = ""):
    """获取知识图谱 HTML

    如果已有缓存，直接返回 HTML 内容；
    如果没有，返回提示信息，前端引导用户点击刷新。
    """
    if not book_name:
        return KGGraphOut(book_name="", exists=False, html_content="", concept_count=0)

    html_path = _kg_html_path(book_name)
    if html_path.exists():
        try:
            html = html_path.read_text(encoding="utf-8")
            # 从 knowledge_graph.py 获取概念数
            from knowledge.knowledge_graph import get_kg
            kg = get_kg(book_name)
            graph = kg.graph()
            count = len(graph) if graph else 0
            return KGGraphOut(
                book_name=book_name,
                exists=True,
                html_content=html,
                concept_count=count,
            )
        except Exception as e:
            return KGGraphOut(
                book_name=book_name,
                exists=False,
                html_content=f"",
                concept_count=0,
            )

    return KGGraphOut(
        book_name=book_name,
        exists=False,
        html_content="",
        concept_count=0,
    )


@router.post("/refresh")
def refresh_kg(book_name: str = ""):
    """重新生成知识图谱"""
    if not book_name:
        return KGRefreshOut(success=False, message="请先选择教材", html_content="", concept_count=0)

    html_path = _kg_html_path(book_name)
    if html_path.exists():
        html_path.unlink()

    try:
        from knowledge.knowledge_graph import get_kg
        from knowledge.kg_visualizer import KGVisualizer

        kg = get_kg(book_name)
        graph = kg.graph()
        if not graph:
            return KGRefreshOut(
                success=False,
                message="知识图谱为空",
                html_content="<p>知识图谱为空</p>",
                concept_count=0,
            )

        viz = KGVisualizer(book_name)
        definitions, _ = viz.enrich_definitions(graph, vector_store=None)
        html = viz.generate_html(graph, definitions, kg_instance=kg)
        viz.save_html(html)
        count = len(graph)

        return KGRefreshOut(
            success=True,
            message=f"已刷新 ({count} 概念)",
            html_content=html,
            concept_count=count,
        )
    except Exception as e:
        return KGRefreshOut(
            success=False,
            message=f"生成失败: {e}",
            html_content="",
            concept_count=0,
        )



@router.get("/concept-wiki")
def get_concept_wiki(name: str, book_name: str = ""):
    """Return a compact concept wiki card for inline chat interactions."""
    if not book_name:
        return {"success": False, "message": "请先选择教材", "data": None}
    try:
        from knowledge.knowledge_graph import get_kg

        kg = get_kg(book_name)
        wiki = kg.get_concept_wiki(name)
        if not wiki:
            return {"success": False, "message": "未找到概念", "data": None}
        return {"success": True, "data": wiki}
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}




def _parse_dt(value: str):
    return parse_datetime(value)


def _days_since(value: str) -> int | None:
    return days_since(value)


def _build_concept_review_plan(book_name: str, concepts: dict, strict_exposures: list[dict], concept_counts, mistake_weak_points: list[dict], subject: str = "", limit: int = 8, weak_names: set[str] | None = None) -> list[dict]:
    """Load mistake records and delegate review-card calculation to a pure service."""
    from config import PROGRESS_PATH
    from memory.mistake_book import get_mistake_book

    try:
        mb = get_mistake_book(book_name, str(PROGRESS_PATH))
        mistake_records = mb.list_all(subject=subject or None, limit=1000)
    except Exception:
        mistake_records = []
    return build_concept_review_plan(
        concepts,
        strict_exposures,
        concept_counts,
        mistake_weak_points,
        mistake_records,
        limit=limit,
        weak_names=weak_names,
    )


def _mistake_summary(record) -> dict:
    return mistake_summary(record)

def _compute_learning_summary(book_name: str = "", subject: str = "", limit: int = 30):
    """Return strict concept memory activity plus mistake weak-point context."""
    memory_book = book_name or "default"
    try:
        from collections import Counter, defaultdict
        from knowledge.concept_memory import ConceptMemory
        from memory.learning_events import get_learning_event_store
        from memory.mistake_book import get_mistake_book
        from utils.subject_catalog import subject_matches

        generic_alias_terms = {
            "\u65b9\u6cd5", "\u6b65\u9aa4", "\u8fed\u4ee3", "\u8fed\u4ee3\u6b65\u9aa4", "\u7a0b\u5e8f\u6846\u56fe", "\u539f\u7406", "\u8fc7\u7a0b", "\u7b97\u6cd5", "\u7ea6\u675f", "\u4f18\u5316", "\u4f18\u5316\u65b9\u6cd5", "\u6700\u4f18\u5316\u65b9\u6cd5", "\u95ee\u9898", "\u6761\u4ef6",
            "method", "step", "steps", "algorithm",
        }

        def is_strict(e: dict, concepts: dict) -> bool:
            try:
                if float(e.get("confidence", 0)) < 0.85:
                    return False
            except (TypeError, ValueError):
                return False
            name = str(e.get("concept", "")).strip()
            question = str(e.get("question", "")).lower()
            if not name or not question:
                return False
            link_source = str(e.get("link_source", ""))
            if (e.get("source") == "mistake" or e.get("intent") == "mistake") and link_source.startswith("mistake_"):
                return True
            info = concepts.get(name, {})
            aliases = [str(a).strip() for a in info.get("aliases", []) if str(a).strip()]
            direct_terms = [name, *[a for a in aliases if a not in generic_alias_terms]]
            return any(term and term.lower() in question for term in direct_terms)

        cm = ConceptMemory(memory_book)
        data = cm._data
        raw_exposures = list(data.get("exposures", []))
        concepts = data.get("concepts", {})
        strict_exposures = [
            e for e in raw_exposures
            if is_strict(e, concepts) and subject_matches(str(e.get("subject", "")), subject)
        ]
        recent_exposures = strict_exposures[-limit:]
        strict_names = {e.get("concept", "") for e in strict_exposures if e.get("concept")}

        concept_counts = Counter(e.get("concept", "") for e in strict_exposures if e.get("concept"))
        source_counts = Counter(e.get("source", "qa") for e in strict_exposures)
        daily = defaultdict(lambda: {"qa": 0, "mistake": 0, "total": 0})
        for e in strict_exposures:
            day = (e.get("timestamp", "") or "")[:10] or "unknown"
            source = "mistake" if e.get("source") == "mistake" or e.get("intent") == "mistake" else "qa"
            daily[day][source] += 1
            daily[day]["total"] += 1

        question_map = {}
        question_order = []
        for e in strict_exposures:
            question = (e.get("question") or "").strip()
            if not question:
                continue
            source = "mistake" if e.get("source") == "mistake" or e.get("intent") == "mistake" else "qa"
            key = (source, question)
            if key not in question_map:
                question_map[key] = {
                    "question": question,
                    "intent": e.get("intent", "qa"),
                    "source": source,
                    "weak": bool(e.get("weak")),
                    "timestamp": e.get("timestamp", ""),
                    "concepts": [],
                }
                question_order.append(key)
            item = question_map[key]
            item["timestamp"] = max(item.get("timestamp", ""), e.get("timestamp", ""))
            item["weak"] = item["weak"] or bool(e.get("weak"))
            concept = e.get("concept")
            if concept and all(c.get("name") != concept for c in item["concepts"]):
                item["concepts"].append({
                    "name": concept,
                    "confidence": e.get("confidence", 0),
                    "weak": bool(e.get("weak")),
                    "source": source,
                    "evidence": e.get("evidence", ""),
                })

        recent_questions = [question_map[k] for k in question_order]
        recent_questions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        qa_events = get_learning_event_store().list_recent(
            event_type="chat_qa",
            subject=subject,
            limit=max(limit * 10, 200),
        )
        if memory_book == "default":
            qa_events = [event for event in qa_events if event.book_name in {"", "default"}]
        else:
            qa_events = [event for event in qa_events if event.book_name == memory_book]
        known_questions = {(item.get("question") or "").strip() for item in recent_questions}
        for event in qa_events:
            question = str(event.payload.get("question") or "").strip()
            if not question or question in known_questions:
                continue
            known_questions.add(question)
            recent_questions.append({
                "question": question,
                "intent": event.payload.get("intent", "qa"),
                "source": "qa",
                "weak": False,
                "timestamp": event.timestamp,
                "concepts": [
                    {"name": name, "confidence": 1.0, "weak": False, "source": "qa_event", "evidence": question}
                    for name in event.concept_names
                ],
            })
        recent_questions.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        recent_questions = recent_questions[:limit]

        effective_weak_names = {item["name"] for item in cm.get_weak_points()}
        weak = []
        for name, info in concepts.items():
            if name in strict_names and name in effective_weak_names:
                weak.append({"name": name, **info})
        weak.sort(key=lambda x: x.get("last_weak_at", x.get("last_exposed_at", "")), reverse=True)

        review_queue = [item for item in cm.get_review_queue(limit=30) if item.get("name") in strict_names][:12]

        try:
            mb = get_mistake_book(memory_book, str(PROGRESS_PATH))
            all_mistakes = mb.list_all(limit=10000)
            subjects = sorted(
                {r.subject for r in all_mistakes if r.subject}
                | {str(e.get("subject", "")) for e in strict_exposures if e.get("subject")}
                | {event.subject for event in qa_events if event.subject}
            )
            subject_mistakes = [r for r in all_mistakes if not subject or r.subject == subject]
            mistake_stats = mb.get_stats(subject=subject or None)
            mistake_weak_points = mb.get_weak_points(subject=subject or None, top_n=10)
            due_mistakes = mb.get_due(subject=subject or None)
        except Exception:
            subjects = []
            subject_mistakes = []
            due_mistakes = []
            mistake_stats = {"total": 0, "due_today": 0, "by_type": {}, "by_tag": {}, "by_difficulty": {}}
            mistake_weak_points = []

        for item in recent_questions:
            question = item.get("question", "")
            if not question:
                continue
            for record in subject_mistakes:
                if question in "\\n".join([record.question_text, record.ocr_text, record.explanation]):
                    item["mistake_id"] = record.id
                    item["source"] = "mistake"
                    break
        if subject:
            recent_questions = [
                item for item in recent_questions
                if item.get("source") != "mistake" or item.get("mistake_id")
            ]

        def exposure_source(e: dict) -> str:
            return "mistake" if e.get("source") == "mistake" or e.get("intent") == "mistake" else "qa"

        def exposure_book(e: dict) -> str:
            if memory_book == "default":
                return str(e.get("subject") or "通用问答")
            return memory_book

        daily_detail_map = defaultdict(lambda: {"qa": 0, "mistake": 0, "total": 0, "books": defaultdict(lambda: {"qa": 0, "mistake": 0, "total": 0, "concepts": Counter()})})
        for e in strict_exposures:
            day = (e.get("timestamp", "") or "")[:10] or "unknown"
            if day == "unknown":
                continue
            source = exposure_source(e)
            item_book = exposure_book(e)
            concept = str(e.get("concept") or "").strip()
            daily_item = daily_detail_map[day]
            daily_item[source] += 1
            daily_item["total"] += 1
            book_item = daily_item["books"][item_book]
            book_item[source] += 1
            book_item["total"] += 1
            if concept:
                book_item["concepts"][concept] += 1

        strict_question_days = {
            ((e.get("timestamp", "") or "")[:10], (e.get("question") or "").strip())
            for e in strict_exposures
        }
        for event in qa_events:
            day = (event.timestamp or "")[:10]
            question = str(event.payload.get("question") or "").strip()
            if not day or not question or (day, question) in strict_question_days:
                continue
            daily[day]["qa"] += 1
            daily[day]["total"] += 1
            label = event.subject or "通用问答"
            daily_item = daily_detail_map[day]
            daily_item["qa"] += 1
            daily_item["total"] += 1
            book_item = daily_item["books"][label]
            book_item["qa"] += 1
            book_item["total"] += 1
            for concept in event.concept_names:
                if concept:
                    book_item["concepts"][concept] += 1

        daily_details = []
        for day, item in sorted(daily_detail_map.items(), reverse=True)[:120]:
            subjects_detail = []
            for book_label, detail in sorted(item["books"].items(), key=lambda kv: kv[1]["total"], reverse=True):
                subjects_detail.append({
                    "subject": book_label,
                    "book_name": book_label,
                    "qa": detail["qa"],
                    "mistake": detail["mistake"],
                    "total": detail["total"],
                    "concepts": [
                        {"name": name, "count": count}
                        for name, count in detail["concepts"].most_common(8)
                    ],
                })
            daily_details.append({
                "date": day,
                "qa": item["qa"],
                "mistake": item["mistake"],
                "total": item["total"],
                "subjects": subjects_detail,
            })
        concept_review_plan = _build_concept_review_plan(
            memory_book,
            concepts,
            strict_exposures,
            concept_counts,
            mistake_weak_points,
            subject=subject,
            limit=8,
            weak_names=effective_weak_names,
        )
        return {
            "success": True,
            "data": {
                "stats": {
                    "total_concepts": len(strict_names),
                    "total_exposures": len(strict_exposures),
                    "weak_count": len(weak),
                    "forgotten_count": len([item for item in cm.get_forgotten(days_threshold=7, limit=100) if item.get("name") in strict_names]),
                    "frequent_top3": [
                        {"name": name, "exposure_count": count}
                        for name, count in concept_counts.most_common(3)
                    ],
                },
                "recent_exposures": recent_exposures,
                "recent_questions": recent_questions,
                "top_concepts": [
                    {"name": name, "count": count, **concepts.get(name, {})}
                    for name, count in concept_counts.most_common(12)
                ],
                "weak_concepts": weak[:12],
                "review_queue": review_queue,
                "concept_review_plan": concept_review_plan,
                "daily": [
                    {"date": day, **counts}
                    for day, counts in sorted(daily.items(), reverse=True)[:14]
                ],
                "daily_details": daily_details,
                "source_counts": dict(source_counts),
                "subjects": subjects,
                "selected_subject": subject,
                "review_rules": {
                    "strict_concepts": "去重后的概念数。仅统计置信度不低于 0.85，且概念名或有效别名直接出现在问题中的接触；错题中明确关联的概念也计入。",
                    "high_confidence_exposures": "符合严格条件的接触事件总数。同一概念每次符合条件的问答或错题各计 1 次，因此可能大于严格概念数。",
                    "weak_concepts": "严格概念中，来自错题、用户明确表示不会/不懂/不熟、复习质量评为 0–2，或被手动标记的概念。仅询问定义、公式或区别不会自动标为薄弱。",
                    "mistake_due": "错题复习采用 SM-2：next_review 小于等于今天即进入待复习。评分 0-2 会重置间隔，3-5 会按掌握度拉长间隔。",
                    "concept_due": "概念复习按优先级推荐：薄弱标记、关联错题、7 天以上未接触或未复习、累计接触次数较高的概念会优先出现。",
                    "concept_reviewed": "点击已复习会记录本次复习并从今天的队列移除。默认质量为 4，会提高掌握度但保留薄弱标记；质量 5 才表示已掌握并解除薄弱。"
                },
                "due_mistakes": [_mistake_summary(r) for r in due_mistakes[:50]],
                "mistake_stats": mistake_stats,
                "mistake_weak_points": mistake_weak_points,
            },
        }
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}


def _learning_summary_dependencies(memory_book: str) -> list[Path]:
    safe = safe_book_name(memory_book)
    progress_root = Path(PROGRESS_PATH)
    mistake_db = safe_child_path(progress_root, f"mistake_book_{safe}.db")
    event_db = safe_child_path(progress_root, "learning_events.db")
    return [
        safe_child_path(progress_root, safe, "concept_memory.json"),
        mistake_db,
        Path(f"{mistake_db}-wal"),
        event_db,
        Path(f"{event_db}-wal"),
    ]


@router.get("/learning-summary")
def get_learning_summary(book_name: str = "", subject: str = "", limit: int = 30):
    memory_book = book_name or "default"
    return _learning_summary_cache.get_or_compute(
        (memory_book, subject, int(limit)),
        _learning_summary_dependencies(memory_book),
        lambda: _compute_learning_summary(book_name, subject, limit),
        should_cache=lambda result: bool(result.get("success")),
    )

@router.post("/concept-review")
def mark_concept_review(payload: dict, book_name: str = ""):
    """Record that the user reviewed a concept from the Learning page."""
    memory_book = book_name or "default"
    name = str(payload.get("name", "")).strip()
    if not name:
        return {"success": False, "message": "缺少概念名", "data": None}
    quality = int(payload.get("quality", 4) or 4)
    note = str(payload.get("note", ""))
    try:
        from knowledge.concept_memory import ConceptMemory
        updated = ConceptMemory(memory_book).mark_reviewed(name, quality=quality, note=note)
        _learning_summary_cache.clear()
        return {"success": True, "message": "已记录概念复习", "data": updated}
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}

@router.get("/open-browser")
def open_kg_browser(book_name: str = ""):
    """在浏览器中打开图谱（仅本地有效）"""
    if not book_name:
        return {"success": False, "message": "请先选择教材"}
    html_path = _kg_html_path(book_name)
    if not html_path.exists():
        return {"success": False, "message": "知识图谱未生成，请先刷新"}
    import webbrowser
    webbrowser.open(html_path.as_uri())
    return {"success": True, "message": f"已在浏览器打开: {html_path.name}"}
