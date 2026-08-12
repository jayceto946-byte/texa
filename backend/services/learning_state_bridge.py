"""Controlled bridge from learning speech acts to cross-session state."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.services.learning_state import (
    DEFAULT_LEARNER_ID,
    LearningStateService,
    resolve_chapter_identity,
)


@dataclass(frozen=True)
class LearningBridgeResult:
    action: str = "none"
    resolved_query: str = ""
    learning_context: dict[str, Any] = field(default_factory=dict)
    clarification_message: str = ""
    state_operations: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


def classify_learning_speech_act(question: str) -> str:
    compact = re.sub(r"\s+", "", str(question or "")).strip("。？?!！")
    if re.fullmatch(r"(?:继续|接着)(?:上次|之前|昨天)?(?:的)?(?:学习|课程|进度)", compact):
        return "resume_learning"
    if re.search(r"(?:开始|从头开始)(?:学习|学)(?:这本书|本章|这一章|第.+章)", compact):
        return "start_learning"
    if re.search(r"(?:今天)?(?:先学到这里|暂停学习|先暂停|先停一下)", compact):
        return "pause_learning"
    if re.search(r"(?:我要|我想|目标是).{0,30}(?:学完|学会|掌握).{0,30}(?:章|节|教材|课程)", compact):
        return "set_learning_goal"
    if re.search(r"(?:复习|回顾).{0,20}(?:薄弱|不会|错题|上次)", compact):
        return "review_request"
    if re.search(r"(?:我|这个|这部分).{0,12}(?:还是|仍然|一直)?(?:不会|不懂|没懂|容易混淆|总是混淆)", compact):
        return "self_report_weakness"
    return ""


def bridge_learning_request(
    question: str,
    speech_act: str,
    *,
    book_name: str,
    subject: str,
    conversation_id: str,
    current_topic: str = "",
    learner_id: str = DEFAULT_LEARNER_ID,
    service: LearningStateService | None = None,
) -> LearningBridgeResult:
    if not speech_act:
        return LearningBridgeResult()
    state_service = service or LearningStateService()
    try:
        if speech_act in {"resume_learning", "review_request"}:
            candidates = (
                state_service.list_reviewable(
                    learner_id=learner_id, book_name=book_name, subject=subject,
                )
                if speech_act == "review_request"
                else state_service.list_resumable(
                    learner_id=learner_id, book_name=book_name, subject=subject,
                )
            )
            if not candidates:
                return LearningBridgeResult(
                    action="clarify",
                    clarification_message=(
                        "当前没有可继续的学习目标。请先选择教材和章节，并告诉我你想从哪里开始。"
                    ),
                    state_operations=[{"operation": "clarify_learning_target"}],
                )
            if len(candidates) > 1:
                choices = "、".join(
                    str(item.get("book_name") or "未命名教材") for item in candidates[:5]
                )
                return LearningBridgeResult(
                    action="clarify",
                    clarification_message=f"找到多个可继续的学习目标：{choices}。请指定要继续哪一本教材。",
                    state_operations=[{"operation": "clarify_learning_target"}],
                )
            state = candidates[0]
            progress = state.get("guided_progress") or {}
            if speech_act == "resume_learning":
                state = state_service.apply_operation(
                    {
                        "operation": "resume_learning",
                        "chapter_id": str(progress.get("chapter_id") or ""),
                        "chapter_name": str(progress.get("chapter_name") or ""),
                        "unit_id": str(progress.get("current_unit_id") or ""),
                        "unit_name": str(progress.get("current_unit_name") or ""),
                    },
                    learner_id=learner_id,
                    book_name=str(state.get("book_name") or book_name),
                    subject=subject,
                    conversation_id=conversation_id,
                )
            pack = state_service.learning_context_pack(state)
            progress = pack.get("current_progress") or {}
            next_action = pack.get("next_action") or {}
            target = str(
                next_action.get("target_name")
                or progress.get("current_unit_name")
                or progress.get("chapter_name")
                or ""
            )
            rewritten = (
                f"复习{target}" if speech_act == "review_request" and target
                else (f"继续学习{target}" if target else "继续当前学习目标")
            )
            return LearningBridgeResult(
                action="resume",
                resolved_query=rewritten,
                learning_context=pack,
                state_operations=[{
                    "operation": "resume_learning",
                    "book_name": str(state.get("book_name") or ""),
                    "target_id": str((pack.get("next_action") or {}).get("target_id") or ""),
                }],
            )
        if speech_act == "pause_learning":
            candidates = state_service.list_resumable(
                learner_id=learner_id, book_name=book_name, subject=subject,
            )
            if len(candidates) != 1:
                return LearningBridgeResult(
                    action="clarify",
                    clarification_message="请先指定要暂停的教材或学习目标。",
                    state_operations=[{"operation": "clarify_learning_target"}],
                )
            state = state_service.apply_operation(
                {"operation": "pause_learning"}, learner_id=learner_id,
                book_name=str(candidates[0].get("book_name") or book_name), subject=subject,
                conversation_id=conversation_id,
            )
            return LearningBridgeResult(
                action="handled",
                learning_context=state_service.learning_context_pack(state),
                clarification_message="已保存当前学习位置。下次可以直接说“继续上次的学习”。",
                state_operations=[{"operation": "pause_learning"}],
            )
        if speech_act in {"start_learning", "set_learning_goal"}:
            if not book_name:
                return LearningBridgeResult(
                    action="clarify",
                    clarification_message="请先选择教材，并说明要开始学习的章节。",
                    state_operations=[{"operation": "clarify_learning_target"}],
                )
            chapter_reference = _chapter_reference(question)
            if not chapter_reference:
                return LearningBridgeResult(
                    action="clarify",
                    clarification_message="请说明要开始学习哪一章。",
                    state_operations=[{"operation": "clarify_learning_target"}],
                )
            chapter = resolve_chapter_identity(
                book_name, chapter_reference, progress_root=state_service.progress_root,
            )
            operation_name = "start_learning" if speech_act == "start_learning" else "create_goal"
            state = state_service.apply_operation(
                {
                    "operation": operation_name,
                    "target_type": "chapter",
                    "target_id": chapter["chapter_id"],
                    "target_name": chapter["chapter_name"],
                    "chapter_id": chapter["chapter_id"],
                    "chapter_name": chapter["chapter_name"],
                },
                learner_id=learner_id, book_name=book_name, subject=subject,
                conversation_id=conversation_id,
            )
            return LearningBridgeResult(
                action="recorded",
                resolved_query=f"开始学习{chapter['chapter_name']}",
                learning_context=state_service.learning_context_pack(state),
                state_operations=[{
                    "operation": operation_name,
                    "chapter_id": chapter["chapter_id"],
                    "chapter_name": chapter["chapter_name"],
                }],
            )
        if speech_act == "self_report_weakness" and current_topic and book_name:
            state = state_service.apply_operation(
                {"operation": "record_weakness", "concept_names": [current_topic], "reason": "explicit_user_statement"},
                learner_id=learner_id, book_name=book_name, subject=subject,
                conversation_id=conversation_id,
            )
            return LearningBridgeResult(
                action="recorded",
                learning_context=state_service.learning_context_pack(state),
                state_operations=[{"operation": "record_weakness", "concept_names": [current_topic]}],
            )
        return LearningBridgeResult(
            action="candidate",
            state_operations=[{"operation": speech_act}],
        )
    except Exception as exc:
        return LearningBridgeResult(error=f"{type(exc).__name__}: {str(exc)[:300]}")


def _chapter_reference(question: str) -> str:
    match = re.search(r"(第[一二三四五六七八九十百\d]+章(?:[^，。？！]{0,30})?)", str(question or ""))
    return " ".join(match.group(1).strip().split()) if match else ""
