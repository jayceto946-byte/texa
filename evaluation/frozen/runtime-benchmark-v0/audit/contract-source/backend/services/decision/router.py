"""Conservative System 0 routing with optional shadow semantic ranking."""
from __future__ import annotations

import re
import math
from dataclasses import dataclass, replace

from backend.services.decision.contracts import (
    DecisionContext, DecisionResult, DomainCapability,
    SemanticRouterBackend, SemanticRanking,
)

CATALOG_VERSION = "1"
CAPABILITIES: tuple[DomainCapability, ...] = (
    "textbook.search", "textbook.read", "mistake.search_related", "mistake.manage",
    "learning.inspect", "exercise.inspect", "exercise.create_set",
    "exercise.record_result", "review.manage", "math.verify",
)
_WRITE = frozenset({"mistake.manage", "exercise.create_set", "exercise.record_result", "review.manage"})
_TEXTBOOK = re.compile(r"教材|课本|原文|第.{0,8}章|按.{0,12}(书|页)|textbook", re.I)
_LEARNING = re.compile(r"掌握|薄弱|最近.{0,8}(学习|进度|活动)|复习.{0,4}(状态|队列)|learning state", re.I)
_MISTAKE = re.compile(r"错题|错误记录|mistake", re.I)
_EXERCISE = re.compile(r"练习|习题|题库|exercise", re.I)
_MATH = re.compile(r"计算|求导|积分|解方程|验算|等价|\d\s*[+*/=−-]\s*\d", re.I)
_WRITE_VERB = re.compile(r"添加|保存|创建|更新|修改|记录|开始|加入|删除|移除", re.I)


@dataclass(frozen=True)
class CalibrationProfile:
    backend_id: str
    backend_version: str
    minimum_score: dict[str, float]
    minimum_margin: dict[str, float]
    sample_count: int
    version: str

    def accepts(self, ranking: SemanticRanking) -> str:
        if ranking.backend_id != self.backend_id or ranking.backend_version != self.backend_version:
            return ""
        if self.sample_count < 30 or ranking.abstained or not ranking.candidates:
            return ""
        ordered = sorted(ranking.candidates, key=lambda item: item.rank)
        if any(not math.isfinite(item.raw_score) or item.capability_id not in CAPABILITIES for item in ordered):
            return ""
        if len({item.rank for item in ordered}) != len(ordered) or len({item.capability_id for item in ordered}) != len(ordered):
            return ""
        top = ordered[0]
        if top.capability_id not in self.minimum_score or top.capability_id not in self.minimum_margin:
            return ""
        second = ordered[1].raw_score if len(ordered) > 1 else float("-inf")
        if top.raw_score < self.minimum_score[top.capability_id] or top.raw_score - second < self.minimum_margin[top.capability_id]:
            return ""
        return top.capability_id


class DecisionRouter:
    def __init__(self, *, semantic: SemanticRouterBackend | None = None,
                 calibration: CalibrationProfile | None = None,
                 shadow: bool = True):
        self.semantic = semantic
        self.calibration = calibration
        self.shadow = shadow

    def route(self, context: DecisionContext) -> DecisionResult:
        return replace(self._route(context), shadow_only=self.shadow)

    def _route(self, context: DecisionContext) -> DecisionResult:
        text = context.resolved_query or context.text
        if context.current_task_status in {"waiting_for_input", "waiting_for_confirmation"} or context.required_inputs:
            return DecisionResult("clarify", reason_codes=("input_gate",), rule_match="task_gate")
        if context.resolution_status == "clarify":
            return DecisionResult("clarify", reason_codes=("reference_unclear",), rule_match="resolution")
        if context.answer_mode == "subject_mismatch":
            return DecisionResult("clarify", reason_codes=("subject_mismatch",), rule_match="scope")
        if context.explicit_action:
            return self._explicit(context)
        rule = self._rule(context, text)
        if rule and (self.semantic is None or not self.shadow):
            return rule
        ranking = None
        if self.semantic:
            try:
                ranking = self.semantic.rank(context, CAPABILITIES)
            except Exception:
                ranking = None
        if rule:
            if ranking and self.shadow:
                return DecisionResult(**{**rule.__dict__, "semantic_candidates": ranking.candidates,
                                         "shadow_only": True})
            return rule
        if ranking and not self.shadow and self.calibration:
            selected = self.calibration.accepts(ranking)
            if selected and selected not in _WRITE:
                return DecisionResult("capability", selected_capability=selected,
                    semantic_candidates=ranking.candidates, confidence_kind="uncalibrated",
                    backend_id=ranking.backend_id, backend_version=ranking.backend_version)
        return DecisionResult("unsupported", reason_codes=("no_safe_route",),
                              semantic_candidates=ranking.candidates if ranking else (),
                              shadow_only=self.shadow)

    def _explicit(self, context: DecisionContext) -> DecisionResult:
        actions = {
            "search_textbook": "textbook.search", "inspect_learning": "learning.inspect",
            "search_mistakes": "mistake.search_related", "search_exercises": "exercise.inspect",
            "verify_math": "math.verify",
        }
        capability = actions.get(context.explicit_action)
        if not capability:
            return DecisionResult("unsupported", reason_codes=("unknown_ui_action",), rule_match="explicit")
        if context.answer_mode == "textbook_grounded" and capability != "textbook.search":
            return DecisionResult("unsupported", reason_codes=("scope_conflict",), rule_match="explicit")
        return DecisionResult("capability", selected_capability=capability,
                              rule_match="explicit", reason_codes=("explicit_ui_action",))

    def _rule(self, context: DecisionContext, text: str) -> DecisionResult | None:
        if context.attachments:
            return DecisionResult("unsupported", reason_codes=("attachment_requires_existing_visual_path",), rule_match="attachment")
        matches = matching_capabilities(text, textbook_grounded=context.answer_mode == "textbook_grounded",
                                        understanding=context.question_understanding)
        if matches:
            capability, rule_match = matches[0]
            return DecisionResult("capability", selected_capability=capability, rule_match=rule_match)
        if context.answer_mode in {"global_general", "subject_general"} and not _WRITE_VERB.search(text):
            return DecisionResult("direct_answer", reason_codes=("general_no_tool",), rule_match="general")
        return None


def matching_capabilities(text: str, *, textbook_grounded: bool = False,
                          understanding: dict | None = None) -> tuple[tuple[str, str], ...]:
    """All deterministic matches in Router priority order; no semantic ranking."""
    matches = []
    if _MISTAKE.search(text):
        matches.append(("mistake.manage" if _WRITE_VERB.search(text) else "mistake.search_related", "mistake"))
    if re.search(r"(?:记录|提交|保存).{0,12}(?:作答|练习答案|练习成绩)", text):
        matches.append(("exercise.record_result", "practice_result"))
    if _EXERCISE.search(text):
        matches.append(("exercise.create_set" if _WRITE_VERB.search(text) else "exercise.inspect", "exercise"))
    if _LEARNING.search(text):
        matches.append(("learning.inspect", "learning"))
    if textbook_grounded or _TEXTBOOK.search(text):
        matches.append(("textbook.search", "textbook"))
    if _MATH.search(text):
        matches.append(("math.verify", "math"))
    from graph.question_understanding import interpretation_hint
    hint = interpretation_hint(understanding)
    if hint and (hint["intent"] == "quiz" or "exercises" in hint["dimensions"]):
        # Interpretation can add only a read capability; explicit rule matches
        # retain priority and write intents still require the existing gates.
        if not any(cap.startswith("exercise.") for cap, _ in matches):
            position = next((i for i, (cap, _) in enumerate(matches)
                             if cap in {"textbook.search", "math.verify"}), len(matches))
            matches.insert(position, ("exercise.inspect", "understanding_read_hint"))
    return tuple(matches)
