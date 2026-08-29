"""反馈节点 — 更新记忆 + 掌握度 + 优化策略"""
import re
import threading
from memory.study_memory import StudyMemory
from memory.spaced_repetition import SpacedRepetition


def _state_answer_mode(state: dict) -> str:
    mode = str(state.get("answer_mode") or "").strip()
    if mode:
        return mode
    if state.get("use_textbook_context") is not False and state.get("book_name"):
        return "textbook_grounded"
    return "subject_general" if state.get("subject") else "global_general"


def _feedback_node_impl(state: dict) -> dict:
    """Collect feedback and update learning state."""
    book_name = state.get("book_name", "default")
    target_chapters = state.get("target_chapters", [])
    feedback = state.get("user_feedback") or {}

    memory = StudyMemory(book_name)
    sr = SpacedRepetition(book_name)

    mastery_update = {}
    verification = state.get("answer_verification") or {}
    answer_verified = verification.get("status") == "passed"

    # A generated answer is only exposure. Chapter completion is recorded only
    # after the task's deterministic postconditions pass.
    if answer_verified:
        for ch in target_chapters:
            memory.mark_chapter_studied(ch)
            mastery_update[ch] = memory.get_chapter_progress(ch)

    # 处理反馈评分
    rating = feedback.get("rating", 0)
    if rating and target_chapters:
        ch = target_chapters[0]
        kp = feedback.get("knowledge_point", f"{ch}_auto")
        card_id = f"{ch}::{kp}"
        sr.add_knowledge_point(card_id, ch, kp)
        quality = _rating_to_quality(rating)
        sr.review(card_id, quality)

    linked_concepts = _record_concept_memory(state)

    return {
        "mastery_update": mastery_update,
        "learning_update_status": "verified_task" if answer_verified else "exposure_only",
        "user_feedback": None,
        "linked_concepts": linked_concepts,
    }


def feedback_node(state: dict) -> dict:
    """Finalize response semantics, then record learning side effects off-path."""
    linked_concepts = link_concepts_for_response(state)

    def record() -> None:
        try:
            _feedback_node_impl(dict(state))
        except Exception as exc:
            print(f"[feedback] record failed: {exc}", flush=True)

    threading.Thread(target=record, name="chat-feedback", daemon=True).start()
    return {
        "mastery_update": {},
        "learning_update_status": "exposure_only",
        "user_feedback": None,
        "linked_concepts": linked_concepts,
    }

def _kg_for_state(state: dict):
    """返回本地预构建 KG（用于字典扫描）；非本地返回 None。"""
    try:
        from knowledge.knowledge_graph import get_kg
        kg = get_kg(str(state.get("book_name") or "default"))
        return kg if getattr(kg, "_is_local", False) else None
    except Exception:
        return None


# 教材名/书目容器的常见后缀："传感器长书" -> "传感器"
_BOOK_CONTAINER_SUFFIXES = (
    "\u957f\u4e66", "\u77ed\u4e66", "\u6559\u6750", "\u8bb2\u4e49", "\u8bfe\u672c",
    "\u4e0a\u518c", "\u4e0b\u518c", "\u7b2c\u4e00\u7248", "\u7b2c2\u7248", "\u7b2c\u4e8c\u7248",
)


def _strip_book_container_suffix(name: str) -> str:
    """"传感器长书"->"传感器"（书目名容器）。"""
    for suffix in _BOOK_CONTAINER_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix) + 1:
            return name[: -len(suffix)]
    return name


def _normalize_chapter_container(title: str) -> str:
    """把章节标题归一化为可能出现的容器词（如"第1章 绪论"->"绪论"）。"""
    value = re.sub(r"^\u7b2c[\u4e00-\u4e5d\u5341\u767e\u5343\d]+\u7ae0\s*", "", str(title or "")).strip()
    value = re.sub(r"^\u7b2c[\u4e00-\u4e5d\u5341\u767e\u5343\d]+\u8282\s*", "", value).strip()
    return value


def _container_names_for_state(state: dict) -> set[str]:
    """当前 book / subject / 章节层级的 container 名称集合（归一化后）。"""
    from knowledge.query_concepts import normalize_full
    names: set[str] = set()
    for raw in (str(state.get("book_name") or ""), str(state.get("subject") or "")):
        raw = raw.strip()
        if raw:
            names.add(normalize_full(raw))
            stripped = _strip_book_container_suffix(raw)
            if stripped and stripped != raw:
                names.add(normalize_full(stripped))
    for title in state.get("target_chapters") or []:
        chapter_container = _normalize_chapter_container(title)
        if chapter_container and len(chapter_container) >= 2:
            names.add(normalize_full(chapter_container))
    return names


def _targeted_repair(
    question: str,
    auto_missing,
    validate_missing,
    kg,
    *,
    allow_llm_repair: bool = True,
    container_names: set[str] | None = None,
) -> list[dict]:
    """Coverage Gate 发现的缺失候选 -> 受限补回。

    - 字典已确认（query_dictionary）缺失：直接补回，不调用 LLM；
      但与当前 book/subject/chapter container 同名的候选默认不补回
      （容器只因词面出现，不是被询问的核心概念；"什么是传感器？"这类
      显式询问仍由 kg_matched 路径覆盖，不受影响）。
    - 启发式（query_parallel）缺失：一次受限逐项验证（constrained classification），
      仅在 allow_llm_repair 且本地 KG 激活时执行，避免 UI 回答路径被 LLM 拖慢。
    """
    from knowledge.query_concepts import normalize_full
    repaired: list[dict] = []
    for cand in auto_missing or []:
        name = cand.canonical_name or cand.name
        if container_names and name and normalize_full(name) in container_names:
            continue
        repaired.append({
            "name": name,
            "concept_id": cand.concept_id or "",
            "type": "concept",
            "confidence": 1.0,
            "source": "query_dictionary",
            "evidence": cand.name,
            "aliases": list(cand.aliases or []),
        })
    if allow_llm_repair and validate_missing and kg is not None and getattr(kg, "_is_local", False):
        try:
            from config import get_llm
            from knowledge.query_concepts import validate_missing_candidates
            repaired.extend(validate_missing_candidates(question, validate_missing, get_llm()))
        except Exception as exc:
            print(f"[ConceptMemory] repair validation failed: {exc}", flush=True)
    return repaired


def _resolve_final_concepts(state: dict, *, allow_llm_repair: bool = True) -> list[dict]:
    """Query-first Candidate Extraction -> 现有 KG linking -> 合并 -> Coverage Gate -> targeted repair。

    数据流：
      query_candidates（确定性并列切分 + KG 字典/别名扫描，不依赖 answer）
      raw（现有 ConceptLinker 从 question/answer/chunks/matched 抽取）
      strict（confidence>=0.85 且出现在问题原文）
      coverage_gate(strict) -> auto_missing / validate_missing
      repair -> final（append_concepts 按 canonical identity 去重）

    allow_llm_repair=False 时跳过 LLM 验证（UI 概念标签的同步快速路径），
    完整（含 LLM repair）只在后台学习记忆路径执行。
    """
    import time as _time
    _started = _time.perf_counter()
    question = str(state.get("user_input", ""))
    if _state_answer_mode(state) == "subject_mismatch" or (
        _state_answer_mode(state) == "textbook_grounded"
        and str((state.get("evidence_support") or {}).get("status") or "") in {"insufficient", "unavailable"}
    ):
        return []
    if not state.get("use_textbook_context", True):
        # General QA has no selected textbook evidence/KG. Keep the synchronous
        # path local; the background memory path may add constrained LLM extraction.
        return _strict_concepts(_link_concepts_locally(state), question)
    try:
        from knowledge.query_concepts import (
            append_concepts,
            coverage_gate,
            debug_log_concepts,
            extract_query_candidates,
        )
        kg = _kg_for_state(state)
        query_candidates = extract_query_candidates(question, kg)
        raw = _link_concepts_locally(state)
        strict = _strict_concepts(raw, question)
        auto_missing, validate_missing = coverage_gate(query_candidates, strict)
        container_names = _container_names_for_state(state)
        repaired = _targeted_repair(
            question,
            auto_missing,
            validate_missing,
            kg,
            allow_llm_repair=allow_llm_repair,
            container_names=container_names,
        )
        final = append_concepts(strict, repaired)
        debug_log_concepts(question, query_candidates, final, auto_missing, validate_missing, repaired)
        _elapsed_ms = round((_time.perf_counter() - _started) * 1000, 1)
        if allow_llm_repair:
            print(
                f"[ConceptMemory] full pipeline {_elapsed_ms}ms (llm_repair={len(validate_missing) > 0})",
                flush=True,
            )
        else:
            print(
                f"[ConceptMemory] fast pipeline {_elapsed_ms}ms (llm_repair deferred={len(validate_missing) > 0})",
                flush=True,
            )
        return final
    except Exception as exc:
        print(f"[ConceptMemory] concept pipeline failed: {exc}", flush=True)
        try:
            return _strict_concepts(_link_concepts_locally(state), question)
        except Exception:
            return []


def link_concepts_for_response(state: dict) -> list[dict]:
    """Resolve UI concept links locally (query-first + coverage + repair).

    UI 概念标签走快速路径（确定性 + 字典，不调用 LLM repair），保证回答路径不被 LLM 拖慢；
    完整（含 LLM repair）解析由后台学习记忆路径执行，能力不丢失。
    """
    try:
        return _resolve_final_concepts(state, allow_llm_repair=False)
    except Exception as exc:
        print(f"[ConceptMemory] response linking failed: {exc}", flush=True)
        return []


_GENERIC_ALIAS_TERMS = {
    "\u65b9\u6cd5", "\u6b65\u9aa4", "\u8fed\u4ee3", "\u8fed\u4ee3\u6b65\u9aa4", "\u7a0b\u5e8f\u6846\u56fe", "\u539f\u7406", "\u8fc7\u7a0b", "\u7b97\u6cd5", "\u7ea6\u675f", "\u4f18\u5316", "\u4f18\u5316\u65b9\u6cd5", "\u6700\u4f18\u5316\u65b9\u6cd5", "\u95ee\u9898", "\u6761\u4ef6",
    "method", "step", "steps", "algorithm",
}


def _strict_concepts(concepts: list[dict], question: str = "") -> list[dict]:
    strict = []
    question_text = (question or "").lower()
    for concept in concepts:
        try:
            if float(concept.get("confidence", 0) or 0) < 0.85:
                continue
        except (TypeError, ValueError):
            continue

        name = str(concept.get("name", "")).strip()
        aliases = [str(a).strip() for a in concept.get("aliases", []) if str(a).strip()]
        direct_terms = [name, *[a for a in aliases if a not in _GENERIC_ALIAS_TERMS]]
        if question_text and not any(term and term.lower() in question_text for term in direct_terms):
            continue
        strict.append(concept)
    return strict


def _record_concept_memory(state: dict) -> list[dict]:
    """Link final QA output to KG concepts and persist shared concept memory."""
    try:
        from knowledge.concept_memory import ConceptMemory, has_explicit_weak_signal
        from memory.learning_events import LearningEvent, concept_names, get_learning_event_store

        answer_mode = _state_answer_mode(state)
        if answer_mode == "subject_mismatch" or (
            answer_mode == "textbook_grounded"
            and str((state.get("evidence_support") or {}).get("status") or "") in {"insufficient", "unavailable"}
        ):
            return []
        book_name = str(state.get("book_name") or "").strip()
        memory_book = "default" if answer_mode == "global_general" else (book_name or "default")
        intent = state.get("intent", "qa")
        subject = "" if answer_mode == "global_general" else state.get("subject", "")
        conversation_id = state.get("conversation_id", "")
        question = state.get("user_input", "")
        answer = state.get("final_output", "")
        raw_concepts = _link_concepts_locally(state)
        explicit_weak = has_explicit_weak_signal(question)

        memory = ConceptMemory(memory_book)
        # 主线程（stream 路径）已用快速路径计算 UI 概念标签（无 LLM repair）；
        # 这里是后台学习记忆路径，执行完整解析以保留 LLM repair 能力。
        # 同步路径（graph.invoke）此前未计算过，同样在此完整解析。
        concepts = _resolve_final_concepts(state)
        if answer_mode in {"subject_general", "global_general"} and not concepts:
            try:
                extracted = memory.extract_concepts(
                    question,
                    answer,
                    subject=subject,
                    answer_mode=answer_mode,
                )
            except TypeError:  # compatibility for older extensions/test doubles
                extracted = memory.extract_concepts(question, answer)
            for item in extracted:
                if isinstance(item, dict):
                    item.setdefault("source", "general_qa_llm")
                    item.setdefault("aliases", [])
            raw_concepts = [*raw_concepts, *extracted]
            concepts = _strict_concepts(raw_concepts, question)
        if concepts:
            memory.log_exposure(
                concepts,
                question,
                intent,
                source={
                    "textbook_grounded": "qa_textbook",
                    "subject_general": "qa_subject_general",
                    "global_general": "qa_global_general",
                }.get(answer_mode, "qa"),
                weak=explicit_weak,
                subject=subject,
                conversation_id=conversation_id,
                weak_reason="explicit_confusion" if explicit_weak else "",
            )

        strict_names = {
            str(item.get("name", "")).strip().lower()
            for item in concepts
            if item and item.get("name")
        }
        candidates = [
            item for item in raw_concepts
            if item and str(item.get("name", "")).strip().lower() not in strict_names
        ]
        if candidates:
            memory.log_candidates(
                candidates,
                question,
                intent,
                source="qa_general_candidate" if answer_mode in {"subject_general", "global_general"} else "qa_linker_candidate",
                subject=subject,
                conversation_id=conversation_id,
                answer=answer,
            )

        store = get_learning_event_store()
        try:
            from backend.services.learning_state import resolve_book_identity
            learning_book_id = resolve_book_identity(memory_book)["book_id"]
        except Exception:
            learning_book_id = ""
        store.append(LearningEvent(
            event_type="chat_qa",
            book_id=learning_book_id,
            book_name=memory_book,
            subject=subject,
            conversation_id=conversation_id,
            source_type="conversation",
            source_id=conversation_id,
            concept_names=concept_names(concepts),
            payload={
                "intent": intent,
                "question": question,
                "answer_preview": answer[:500],
                "target_chapters": state.get("target_chapters", []),
                "retrieval_status": state.get("retrieval_status", ""),
                "answer_mode": answer_mode,
                "scope_reason": state.get("scope_reason", ""),
                "candidate_count": len(candidates or []),
            },
        ))
        for item in concepts:
            store.append(LearningEvent(
                event_type="concept_exposure",
                book_id=learning_book_id,
                book_name=memory_book,
                subject=subject,
                conversation_id=conversation_id,
                source_type="conversation",
                source_id=conversation_id,
                concept_names=concept_names([item]),
                payload={
                    "intent": intent,
                    "question": question,
                    "confidence": item.get("confidence", 0),
                    "link_source": item.get("source", ""),
                    "weak": explicit_weak,
                },
            ))
        if candidates:
            store.append(LearningEvent(
                event_type="concept_candidates",
                book_id=learning_book_id,
                book_name=memory_book,
                subject=subject,
                conversation_id=conversation_id,
                source_type="conversation",
                source_id=conversation_id,
                concept_names=concept_names(candidates),
                payload={
                    "intent": intent,
                    "question": question,
                    "candidate_count": len(candidates),
                },
            ))

        return concepts
    except Exception as e:
        print(f"[ConceptMemory] QA record failed: {e}", flush=True)
        return []


def _link_concepts_locally(state: dict) -> list[dict]:
    """Use the local KG linker first; generic QA may use a background LLM fallback."""
    from knowledge.concept_linker import ConceptLinker

    chapter_contents = state.get("chapter_contents", {}) or {}
    chunks: list[str] = []
    for docs in chapter_contents.values():
        chunks.extend(docs[:2])

    answer_mode = _state_answer_mode(state)
    linker_book = "default" if answer_mode in {"subject_general", "global_general", "subject_mismatch"} else state.get("book_name", "default")
    return ConceptLinker(linker_book).link(
        question=state.get("user_input", ""),
        answer=state.get("final_output", ""),
        chunks=chunks,
        matched_concepts=state.get("matched_concepts", []),
        intent=state.get("intent", "qa"),
        limit=8,
    )


def _rating_to_quality(rating) -> int:
    if isinstance(rating, (int, float)):
        r = float(rating)
        if r >= 5:
            return 5
        elif r >= 4:
            return 4
        elif r >= 3:
            return 3
        elif r >= 2:
            return 2
        elif r >= 1:
            return 1
    return 3
