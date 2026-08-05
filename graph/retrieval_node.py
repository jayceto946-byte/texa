"""Hybrid retrieval node: KG exact hits, role-aware vector search, rerank, and debug metadata."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from config import PROGRESS_PATH
from ingestion.lexical_index import expand_neighbors, search_book, tokenize
from ingestion.reranker import cross_encoder_scores, reranker_status
from graph.safe_retrieval import get_safe_kg, get_safe_vector_store
from utils.resource_groups import resolve_retrieval_resources

INTENT_ROLE_PRIORITY: dict[str, list[str]] = {
    "factual_recall": ["property", "definition", "reference", "theorem", "formula"],
    "definition": ["definition", "theorem", "property", "example", "derivation"],
    "formula": ["definition", "property", "derivation", "example"],
    "property": ["property", "theorem", "definition", "example"],
    "derivation": ["derivation", "theorem", "proof", "definition"],
    "comparison": ["definition", "property", "example"],
    "application": ["example", "algorithm", "exercise", "derivation"],
    "teach": ["definition", "example", "algorithm", "property", "derivation"],
    "summarize": ["definition", "property", "theorem", "derivation"],
    "quiz": ["example", "exercise", "derivation"],
    "plan": ["definition", "algorithm", "property"],
    "cross_chapter": ["definition", "property", "theorem"],
    "qa": ["definition", "theorem", "property", "example", "derivation"],
}

BOOK_ROLE_RANK = {"core": 0, "reference": 1, "": 2}

ROLE_RANK = {
    "definition": 0,
    "theorem": 1,
    "property": 2,
    "derivation": 3,
    "proof": 4,
    "algorithm": 5,
    "example": 6,
    "exercise": 7,
    "reference": 8,
    "": 9,
}

TOC_SECTION_MARKERS = {
    "(no title)",
    "\u76ee\u5f55",
    "\u672c\u7ae0\u5b66\u4e60\u8981\u70b9",
    "\u4e60\u9898",
    "\u601d\u8003\u9898",
    "\u53c2\u8003\u6587\u732e",
    "\u9644\u5f55",
    "table of contents",
    "toc",
}

_SUPPORT_META_PHRASES = (
    "教材中有没有介绍", "教材里有没有介绍", "教材有没有介绍",
    "教材中是否说明", "教材里是否说明", "教材是否说明",
    "教材中有没有讲", "教材里有没有讲", "教材有没有讲",
    "教材中是否有", "教材里是否有", "教材是否有",
    "根据教材", "按照教材", "请问", "请解释", "请说明",
)
_SUPPORT_FILLER_PHRASES = (
    "基本思想是什么", "是什么意思", "有哪些", "有什么", "是什么",
    "为什么", "怎么样", "怎么", "如何", "是否", "能否", "适合吗",
    "的主要", "主要", "讲一下", "介绍一下", "说明一下",
    "请分析", "请解释", "请说明", "简述", "列出", "给出", "比较", "适合", "吗", "呢",
)
_TOPIC_SUFFIXES = (
    "传感器", "热敏电阻", "电阻", "误差", "定理", "公式", "方法",
    "算法", "效应", "模型", "概念", "原理", "定律", "法",
)


def retrieve_node(state: dict) -> dict:
    target_chapters = state.get("target_chapters", [])
    user_input = state.get("user_input", "")
    book_name = state.get("book_name", "default")
    subject = str(state.get("subject") or "").strip()
    retrieval_resources = resolve_retrieval_resources(book_name, subject)
    primary_resource = next((item for item in retrieval_resources if item.get("is_primary")), retrieval_resources[0])
    primary_book = str(primary_resource.get("book_name") or book_name)
    intent = state.get("intent", "qa")

    if not state.get("use_textbook_context", True):
        return {
            "chapter_contents": {},
            "retrieval_debug_items": [],
            "concept_results": [],
            "history_results": [],
            "knowledge_graph_path": [],
            "knowledge_graph_formulas": [],
            "matched_concepts": [],
            "evidence_support": {"status": "not_applicable", "reason": "textbook_context_disabled"},
            "retrieval_status": "ordinary_qa",
            "retrieval_error": "",
        }

    retrieval_errors: list[str] = []
    if state.get("retrieval_error"):
        retrieval_errors.append(str(state.get("retrieval_error")))

    vs, vector_error = get_safe_vector_store()
    kg, kg_error = get_safe_kg(primary_book)
    if vector_error:
        retrieval_errors.append(f"vector_store: {vector_error}")
    if kg_error:
        retrieval_errors.append(f"knowledge_graph: {kg_error}")

    index_stats = {}
    if primary_book and primary_book != "default" and hasattr(vs, "get_book_index_stats"):
        try:
            index_stats = vs.get_book_index_stats(primary_book)
        except Exception as exc:
            retrieval_errors.append(f"index_health: {exc}")
        if index_stats and not index_stats.get("healthy") and not getattr(kg, "_is_local", False):
            return {
                "chapter_contents": {}, "retrieval_debug_items": [], "evidence_items": [],
                "concept_results": [], "history_results": [], "knowledge_graph_path": [],
                "knowledge_graph_formulas": [], "matched_concepts": [],
                "evidence_support": {"status": "unavailable", "reason": "book_index_empty"},
                "retrieval_status": "unavailable",
                "retrieval_error": "book_index_empty",
                "index_stats": index_stats,
            }

    precise_results, matched_concepts = _kg_precise_retrieval(kg, user_input, intent=intent)
    for item in precise_results:
        item.setdefault("book_name", primary_book)
        item.setdefault("book_role", str(primary_resource.get("role") or ""))
        item.setdefault("rag_priority", float(primary_resource.get("priority") or 1.0))
    vector_results: list[dict] = []
    lexical_results: list[dict] = []
    neighbor_results: list[dict] = []
    for resource in retrieval_resources:
        candidate_book = str(resource.get("book_name") or "")
        is_primary = bool(resource.get("is_primary"))
        candidate_lexical = search_book(candidate_book, user_input, k=20 if is_primary else 12, chapters=(target_chapters or None) if is_primary else None)
        lexical_results.extend(candidate_lexical)
        fallback_chapters = list(dict.fromkeys(
            str(item.get("chapter") or "") for item in candidate_lexical if item.get("chapter")
        ))[:12]
        candidate_vectors = _vector_retrieval(
            vs, user_input, intent=intent, book_name=candidate_book,
            target_chapters=target_chapters if is_primary else [],
            precise_chapters=list({r["chapter"] for r in precise_results if r.get("chapter")}) if is_primary else [],
            fallback_chapters=fallback_chapters,
            k=20 if is_primary else 12, top_n=4 if is_primary else 3,
        )
        vector_results.extend(candidate_vectors)
        candidate_neighbors = expand_neighbors(candidate_book, [item.get("chunk_id", "") for item in candidate_lexical[:3]], window=1)
        default_role = str(resource.get("role") or "")
        default_priority = float(resource.get("priority") or 1.0)
        is_selected_book = bool(resource.get("is_selected"))
        for item in candidate_vectors + candidate_lexical + candidate_neighbors:
            if default_role and not item.get("book_role"):
                item["book_role"] = default_role
            if default_role and item.get("rag_priority") in {None, ""}:
                item["rag_priority"] = default_priority
            item.setdefault("book_name", candidate_book)
            item["is_selected_book"] = is_selected_book
        neighbor_results.extend(candidate_neighbors)
    chapter_contents, retrieval_debug_items = _merge_and_rerank(
        precise_results,
        vector_results + lexical_results + neighbor_results,
        max_chunks_per_chapter=6,
        max_total_chunks=10,
        include_metadata=True,
        query=user_input,
        intent=intent,
    )

    kg_path: list[str] = []
    # Directional KG relations are not reliable enough to influence answers.
    # Keep the state field for backward compatibility, but never populate it
    # from inferred prerequisite/extension edges.
    kg_formulas: list[dict] = []
    try:
        if matched_concepts:
            concept_name = matched_concepts[0]
            detail = kg.get_concept_detail(concept_name)
            if detail:
                kg_formulas = detail.get("related_formulas", [])[:3]
    except Exception as exc:
        retrieval_errors.append(f"knowledge_graph_query: {exc}")

    concept_results = []
    debug_by_text = {item.get("preview", ""): item for item in retrieval_debug_items}
    for ch_name, contents in chapter_contents.items():
        for content in contents[:2]:
            debug = _find_debug_for_content(content, debug_by_text)
            concept_results.append({
                "chapter": ch_name,
                "content": content[:150],
                "chunk_id": debug.get("chunk_id", "") if debug else "",
            })

    history_results = _load_history(primary_book, target_chapters)

    candidate_evidence = [
        {
            "chunk_id": item.get("chunk_id", ""), "chapter": item.get("chapter", ""),
            "section_title": item.get("section_title", ""), "page_idx": item.get("page_idx", -1),
            "text": item.get("text", ""), "score": item.get("score", 0.0),
            "query_coverage": item.get("query_coverage", 0.0),
            "book_name": item.get("book_name", ""),
            "book_role": item.get("book_role", ""),
            "is_selected_book": bool(item.get("is_selected_book")),
            "rag_priority": item.get("rag_priority", 1.0),
            "role": item.get("role", ""),
            "source": item.get("source", ""),
            "is_direct_hit": bool(item.get("is_direct_hit")),
            "fusion_sources": item.get("fusion_sources", []),
        }
        for item in retrieval_debug_items[:10]
        if item.get("text")
        and _supports_query_literals(
            user_input,
            f"{item.get('section_title', '')}\n{item.get('text', '')}",
        )
        and (item.get("is_direct_hit") or float(item.get("query_coverage", 0)) >= 0.2)
    ]
    evidence_support = _assess_evidence_support(
        user_input,
        candidate_evidence,
        matched_concepts=matched_concepts,
    )
    evidence_items = candidate_evidence if evidence_support["status"] in {"supported", "partial"} else []

    return {
        "chapter_contents": chapter_contents,
        "retrieval_debug_items": retrieval_debug_items,
        "concept_results": concept_results,
        "history_results": history_results,
        "knowledge_graph_path": kg_path,
        "knowledge_graph_formulas": kg_formulas,
        "matched_concepts": matched_concepts,
        "evidence_items": evidence_items,
        "evidence_support": evidence_support,
        "index_stats": index_stats,
        "retrieval_status": "degraded" if retrieval_errors else "ok",
        "retrieval_error": "; ".join(dict.fromkeys(retrieval_errors)),
        "evidence_gate_applied": True,
    }
def _supports_query_literals(query: str, text: str) -> bool:
    """Require exact years, identifiers and Latin tokens when the query has them."""
    literals = [token.lower() for token in re.findall(r"[A-Za-z]+\d*|\d{2,}", query or "")]
    lowered = (text or "").lower()
    return all(token in lowered for token in literals)




def _normalized_support_text(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.+一-鿿-]+", "", value or "").lower()


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _extract_query_focus(query: str, matched_concepts: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Separate the known textbook topic from the fact the user actually asks for."""
    cleaned = str(query or "").lower()
    for phrase in _SUPPORT_META_PHRASES:
        cleaned = cleaned.replace(phrase, " ")
    normalized_query = _normalized_support_text(cleaned)

    topics = [
        _normalized_support_text(name)
        for name in (matched_concepts or [])
        if _normalized_support_text(name) in normalized_query
    ]
    suffix_pattern = "|".join(re.escape(value) for value in _TOPIC_SUFFIXES)
    match = re.search(rf"[A-Za-z0-9_.+一-鿿-]{{2,}}?(?:{suffix_pattern})", normalized_query)
    if match:
        topics.append(match.group(0))
    ordered_topics = _dedupe_preserving_order(sorted(topics, key=len, reverse=True))
    topics = [
        topic
        for index, topic in enumerate(ordered_topics)
        if not any(topic in longer for longer in ordered_topics[:index])
    ]

    residual = normalized_query
    for topic in topics:
        residual = residual.replace(topic, " ")
    for phrase in _SUPPORT_FILLER_PHRASES:
        residual = residual.replace(_normalized_support_text(phrase), " ")
    residual = residual.replace("以及", " ").replace("并且", " ").replace("还有", " ")
    residual = residual.replace("和", " ").replace("与", " ")
    focus = [
        value.strip("的是在中里")
        for value in re.findall(r"[A-Za-z0-9_.+-]+|[一-鿿]{2,}", residual)
    ]
    focus = [value for value in focus if len(value) >= 2]
    return topics, _dedupe_preserving_order(focus)


def _focus_coverage(phrase: str, text: str) -> float:
    phrase = _normalized_support_text(phrase)
    text = _normalized_support_text(text)
    if not phrase:
        return 1.0
    if phrase in text:
        return 1.0
    if re.fullmatch(r"[一-鿿]+", phrase) and len(phrase) >= 3:
        bigrams = _dedupe_preserving_order([phrase[index:index + 2] for index in range(len(phrase) - 1)])
        return sum(token in text for token in bigrams) / max(len(bigrams), 1)
    return 0.0


def _assess_evidence_support(
    query: str,
    evidence_items: list[dict],
    *,
    matched_concepts: list[str] | None = None,
) -> dict:
    """Reject topic-only matches when no evidence supports the question focus."""
    topics, focus = _extract_query_focus(query, matched_concepts)
    if not evidence_items:
        return {
            "status": "insufficient",
            "reason": "required_literal_missing_or_no_candidates",
            "topic_terms": topics,
            "focus_terms": focus,
            "matched_focus_terms": [],
            "best_focus_coverage": 0.0,
            "best_query_coverage": 0.0,
        }

    evidence_texts = [
        f"{item.get('section_title', '')}\n{item.get('text', '')}"
        for item in evidence_items
    ]
    focus_coverages = {
        phrase: max((_focus_coverage(phrase, text) for text in evidence_texts), default=0.0)
        for phrase in focus
    }
    matched_focus = [phrase for phrase, coverage in focus_coverages.items() if coverage >= 0.6]
    best_focus_coverage = max(focus_coverages.values(), default=1.0 if not focus else 0.0)
    best_query_coverage = max((float(item.get("query_coverage", 0.0)) for item in evidence_items), default=0.0)
    strong_evidence = any(
        item.get("is_direct_hit")
        or "kg" in set(item.get("fusion_sources") or [])
        or {"dense", "bm25"}.issubset(set(item.get("fusion_sources") or []))
        or float(item.get("query_coverage", 0.0)) >= 0.5
        for item in evidence_items
    )

    if not focus and strong_evidence:
        status, reason = "supported", "topic_supported"
    elif focus and len(matched_focus) == len(focus) and strong_evidence:
        status, reason = "supported", "question_focus_supported"
    elif matched_focus or (strong_evidence and best_query_coverage >= 0.45):
        status, reason = "partial", "question_focus_partially_supported"
    else:
        status, reason = "insufficient", "topic_matched_but_question_focus_missing"

    return {
        "status": status,
        "reason": reason,
        "topic_terms": topics,
        "focus_terms": focus,
        "matched_focus_terms": matched_focus,
        "best_focus_coverage": round(best_focus_coverage, 6),
        "best_query_coverage": round(best_query_coverage, 6),
    }


def _find_debug_for_content(content: str, debug_by_preview: dict[str, dict]) -> dict | None:
    for preview, item in debug_by_preview.items():
        if preview and content.startswith(preview):
            return item
    return None


def _core_query_terms(user_input: str) -> list[str]:
    text = user_input.strip()
    for suffix in (
        "\u662f\u4ec0\u4e48",
        "\u662f\u4ec0\u4e48\u610f\u601d",
        "\u7684\u5b9a\u4e49",
        "\u5b9a\u4e49",
        "\u6709\u4ec0\u4e48\u6027\u8d28",
        "\u57fa\u672c\u601d\u60f3\u662f\u4ec0\u4e48",
        "\u8bb2\u4e00\u4e0b",
        "\u8bf7\u89e3\u91ca",
        "\uff1f",
        "?",
        "\u3002",
    ):
        text = text.replace(suffix, " ")
    parts = re.findall(r"[A-Za-z0-9_.+-]+|[\u4e00-\u9fff]{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def _rank_concept_matches(matches: list[tuple[float, dict]], user_input: str, intent: str = "qa") -> list[tuple[float, dict]]:
    q = user_input.strip().lower()
    terms = _core_query_terms(user_input)
    role_boost = set(INTENT_ROLE_PRIORITY.get(intent, []))

    def score(item: tuple[float, dict]) -> tuple[float, int, int]:
        base, concept = item
        name = str(concept.get("canonical_name") or "")
        aliases = [str(a) for a in concept.get("aliases", [])]
        names = [name] + aliases
        adjusted = float(base)
        if any(q == n.lower() for n in names):
            adjusted += 60
        if any(n and n.lower() in q for n in names):
            adjusted += 35
        if any(term == name for term in terms):
            adjusted += 40
        partial_terms = [term for term in terms if term and term in name and term != name]
        if partial_terms:
            best_partial = max(partial_terms, key=len)
            adjusted -= max(0, len(name) - len(best_partial)) * 1.5
        if role_boost and role_boost.intersection(set(concept.get("roles", []))):
            adjusted += 12
        return adjusted, -len(name), int(concept.get("occurrence_count", 0))

    return sorted(matches, key=score, reverse=True)


def _looks_like_toc_chunk(item: dict) -> bool:
    section = str(item.get("section_title") or "")
    section_lc = section.strip().lower()
    text = str(item.get("text") or "")
    if section_lc in TOC_SECTION_MARKERS:
        return True
    if any(marker in section_lc for marker in ("\u76ee\u5f55", "\u672c\u7ae0\u5b66\u4e60\u8981\u70b9", "\u4e60\u9898", "table of contents")):
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    joined = " ".join(lines[:8])
    chapter_markers = sum(1 for line in lines[:14] if "\u7b2c" in line and ("\u7ae0" in line or "\u8282" in line))
    page_number_markers = len(re.findall(r"\s\d{1,3}(\s|$)", joined))
    return chapter_markers >= 3 and page_number_markers >= 3


def _kg_precise_retrieval(kg, user_input: str, intent: str = "qa") -> tuple[list[dict], list[str]]:
    if not getattr(kg, "_is_local", False):
        return [], []

    matched = _rank_concept_matches(kg.search_concept(user_input, k=8), user_input, intent=intent)[:3]
    if not matched:
        return [], []

    results: list[dict] = []
    matched_names: list[str] = []
    for score, concept in matched:
        if score < 30:
            continue
        name = concept["canonical_name"]
        matched_names.append(name)
        chunks = kg.get_concept_chunks(name, window=1, max_hits=3)
        chunks = sorted(chunks, key=lambda ch: (_looks_like_toc_chunk(ch), not ch.get("is_direct_hit", False), ROLE_RANK.get(ch.get("role", ""), 9)))
        for ch in chunks:
            if _looks_like_toc_chunk(ch) and not ch.get("is_direct_hit", False):
                continue
            results.append({
                "chapter": ch.get("chapter", ""),
                "chunk_id": ch.get("chunk_id", ""),
                "text": ch.get("text", ""),
                "section_title": ch.get("section_title", ""),
                "page_idx": ch.get("page_idx", -1),
                "is_direct_hit": ch.get("is_direct_hit", False),
                "role": ch.get("role", ""),
                "source": "kg_precise",
            })

    return results, matched_names


def _vector_retrieval(vs, user_input: str, *, intent: str = "qa", book_name: str = "", target_chapters: list[str], precise_chapters: list[str], fallback_chapters: list[str] | None = None, k: int = 3, top_n: int = 2) -> list[dict]:
    results: list[dict] = []
    priority_roles = INTENT_ROLE_PRIORITY.get(intent, [])
    search_scope: list[str] = []
    if precise_chapters:
        search_scope = [ch for ch in precise_chapters if ch]
    elif target_chapters:
        search_scope = target_chapters[:2]

    if search_scope:
        for ch in search_scope:
            docs, used_role = _search_chapter_with_role(vs, ch, user_input, k, priority_roles, book_name=book_name)
            for d in docs:
                results.append(_doc_to_item(d, ch, f"vector({used_role})" if used_role else "vector"))
            if used_role == "example":
                try:
                    for d in vs.search_chapter(ch, user_input, k=k * 2, book_name=book_name):
                        results.append(_doc_to_item(d, ch, "vector(example_boost)"))
                except Exception:
                    pass
    else:
        all_results, used_role = _search_all_with_role(vs, user_input, k, top_n, priority_roles, book_name=book_name, fallback_chapters=fallback_chapters)
        for ch_name, docs in all_results.items():
            for d in docs:
                results.append(_doc_to_item(d, ch_name, f"vector({used_role})" if used_role else "vector"))
        if used_role == "example":
            try:
                for ch_name, docs in vs.search_all(user_input, k=k * 2, top_n=top_n, book_name=book_name, fallback_chapters=fallback_chapters).items():
                    for d in docs:
                        results.append(_doc_to_item(d, ch_name, "vector(example_boost)"))
            except Exception:
                pass
    for rank, item in enumerate(results, 1):
        item["retrieval_rank"] = rank
        item["dense_rank"] = rank
    return results


def _doc_to_item(doc, chapter: str, source: str) -> dict:
    meta = getattr(doc, "metadata", {}) or {}
    return {
        "chapter": chapter,
        "chunk_id": meta.get("chunk_id", ""),
        "text": meta.get("raw_content") or getattr(doc, "page_content", ""),
        "parent_id": meta.get("parent_id", ""),
        "prev_chunk_id": meta.get("prev_chunk_id", ""),
        "next_chunk_id": meta.get("next_chunk_id", ""),
        "section_path": meta.get("section_path", ""),
        "section_title": meta.get("section_title", ""),
        "page_idx": meta.get("page_idx", -1),
        "is_direct_hit": False,
        "role": meta.get("role", ""),
        "book_role": meta.get("book_role", ""),
        "rag_priority": float(meta.get("rag_priority") or 1.0),
        "subject": meta.get("subject", ""),
        "source": source,
    }


def _search_chapter_with_role(vs, chapter: str, query: str, k: int, priority_roles: list[str], book_name: str = ""):
    try:
        return vs.search_chapter(chapter, query, k=k, book_name=book_name), None
    except Exception:
        return [], None


def _search_all_with_role(vs, query: str, k: int, top_n: int, priority_roles: list[str], book_name: str = "", fallback_chapters: list[str] | None = None):
    try:
        return vs.search_all(query, k=k, top_n=top_n, book_name=book_name, fallback_chapters=fallback_chapters), None
    except Exception:
        return {}, None


def _merge_and_rerank(
    precise: list[dict],
    vector: list[dict],
    *,
    max_chunks_per_chapter: int = 5,
    max_total_chunks: int = 8,
    include_metadata: bool = False,
    query: str = "",
    intent: str = "qa",
):
    """Fuse KG, dense and BM25 ranks, then apply query-aware local reranking."""
    fused = {}
    source_ranks = {}
    for source_items in (precise, vector):
        for position, original in enumerate(source_items, 1):
            item = dict(original)
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            key = str(item.get("chunk_id") or text[:100].replace(" ", "").replace("\n", ""))
            source = str(item.get("source") or "unknown")
            source_key = "bm25" if source == "bm25" else ("kg" if source.startswith("kg") else "dense")
            rank = int(item.get("retrieval_rank") or position)
            source_ranks[(key, source_key)] = min(rank, source_ranks.get((key, source_key), rank))
            existing = fused.get(key)
            if existing is None or source_key == "bm25":
                # The lexical index stores the complete chunk. Dense hits may use a
                # shorter child representation with the same chunk_id.
                fused[key] = item
            if item.get("is_direct_hit"):
                fused[key]["is_direct_hit"] = True
                fused[key]["source"] = source

    query_tokens = set(tokenize(query))
    role_order = INTENT_ROLE_PRIORITY.get(intent, [])
    ranked = []
    for key, item in fused.items():
        score = 0.0
        sources = []
        for source_key in ("kg", "dense", "bm25"):
            rank = source_ranks.get((key, source_key))
            if rank is not None:
                score += 1.0 / (60.0 + rank)
                sources.append(source_key)
        if item.get("is_direct_hit"):
            score += 0.05
        item_tokens = set(tokenize(f"{item.get('section_title', '')}\n{item.get('text', '')}"))
        coverage = 0.0
        if query_tokens:
            coverage = len(query_tokens & item_tokens) / len(query_tokens)
            score += 0.08 * coverage
        item["query_coverage"] = round(coverage, 6)
        role = str(item.get("role") or "")
        if role in role_order:
            score += 0.012 * (len(role_order) - role_order.index(role)) / max(len(role_order), 1)
        book_role = str(item.get("book_role") or "")
        if book_role == "core":
            score += 0.035
        elif book_role == "reference":
            score -= 0.006
        # Explicit user selection is independent of the core/reference role.
        # Keep selected reference evidence from disappearing behind generic core chunks.
        if item.get("is_selected_book"):
            score += 0.045
            if intent == "factual_recall" and "bm25" in sources:
                score += 0.025
        if item.get("source") == "neighbor":
            score -= 0.004
        if _looks_like_toc_chunk(item):
            score -= 0.2
        item["score"] = round(score, 6)
        item["fusion_sources"] = sources
        ranked.append(item)

    cross_scores = cross_encoder_scores(query, [str(item.get("text") or "") for item in ranked])
    if cross_scores is not None:
        for item, cross_score in zip(ranked, cross_scores):
            item["cross_encoder_score"] = cross_score
            item["score"] = float(item.get("score", 0)) + 0.15 * cross_score
    rerank_meta = reranker_status()

    enumeration_query = intent == "factual_recall" and any(
        marker in query for marker in ("哪些", "优点", "特点", "不足", "缺点", "主要")
    )
    if enumeration_query:
        # List answers are commonly split across consecutive textbook chunks.
        # Preserve the selected book BM25 order so exact list members survive Top-K.
        ranked.sort(key=lambda item: (
            0 if item.get("is_selected_book") and "bm25" in item.get("fusion_sources", []) else 1,
            int(item.get("retrieval_rank") or 999999),
            -float(item.get("score", 0)),
            item.get("page_idx", 999999),
        ))
    else:
        ranked.sort(key=lambda item: (-float(item.get("score", 0)), item.get("page_idx", 999999)))
    chapter_contents: dict[str, list[str]] = {}
    debug_items: list[dict] = []
    total = 0
    for item in ranked:
        chapter = item.get("chapter") or "\u76f8\u5173\u7ae0\u8282"
        chapter_contents.setdefault(chapter, [])
        if len(chapter_contents[chapter]) >= max_chunks_per_chapter:
            continue
        if total >= max_total_chunks:
            break
        text = item.get("text", "")
        chapter_contents[chapter].append(text)
        debug_items.append({
            "rank": total + 1,
            "chapter": chapter,
            "score": item.get("score", 0.0),
            "fusion_sources": item.get("fusion_sources", []),
            "text": text,
            "parent_id": item.get("parent_id", ""),
            "cross_encoder_score": item.get("cross_encoder_score"),
            "query_coverage": item.get("query_coverage", 0.0),
            "reranker_mode": rerank_meta.get("mode"),
            "chunk_id": item.get("chunk_id", ""),
            "source": item.get("source", ""),
            "role": item.get("role", ""),
            "book_name": item.get("book_name", ""),
            "book_role": item.get("book_role", ""),
            "is_selected_book": bool(item.get("is_selected_book")),
            "rag_priority": item.get("rag_priority", 1.0),
            "section_title": item.get("section_title", ""),
            "page_idx": item.get("page_idx", -1),
            "is_direct_hit": bool(item.get("is_direct_hit", False)),
            "is_toc_like": _looks_like_toc_chunk(item),
            "preview": text[:180],
        })
        total += 1

    if include_metadata:
        return chapter_contents, debug_items
    return chapter_contents


def _load_history(book_name: str, chapters: list[str]) -> list[dict]:
    results: list[dict] = []
    progress_dir = Path(PROGRESS_PATH) / book_name
    weakness_file = progress_dir / "weakness.json"
    if weakness_file.exists():
        with open(weakness_file, "r", encoding="utf-8") as f:
            for item in json.load(f)[-10:]:
                results.append({"type": "weakness", "chapter": item})
    quiz_file = progress_dir / "quiz_history.json"
    if quiz_file.exists():
        with open(quiz_file, "r", encoding="utf-8") as f:
            for q in json.load(f)[-10:]:
                results.append({
                    "type": "quiz",
                    "chapter": q.get("chapter", ""),
                    "correct": q.get("correct", False),
                    "question": q.get("question", "")[:80],
                })
    return results
