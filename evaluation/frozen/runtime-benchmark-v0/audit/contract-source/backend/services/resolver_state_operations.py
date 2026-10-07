"""Validated state-operation derivation, separate from reference resolution."""
from __future__ import annotations

from typing import Any, Callable

from backend.services.resolver_speech_act import (
    apply_topic_transition,
    classify_speech_act,
)


def derive_state_operations(
    question: str,
    before: Any,
    after: Any,
    observation: dict[str, Any],
    *,
    should_clarify: bool,
    topic_correction: Callable[[str, Any], dict[str, Any] | None],
    constraint_replacement: Callable[[str, Any], dict[str, str] | None],
    topic_return_resolution: Callable[[str, Any], dict[str, str] | None],
) -> tuple[str, list[dict[str, Any]]]:
    if should_clarify:
        return "clarification", [{"operation": "clarify"}]

    operations: list[dict[str, Any]] = []
    method = str(observation.get("method") or "")
    correction = topic_correction(question, before)
    replacement = constraint_replacement(question, before)
    topic_return = topic_return_resolution(question, before)
    speech_act = classify_speech_act(
        method=method,
        has_replacement=bool(replacement),
        has_correction=bool(correction),
        has_topic_return=bool(topic_return),
        is_followup=bool(observation.get("is_followup")),
    )

    if replacement:
        operations.append({
            "operation": "replace_constraint",
            "old_value": replacement["old"],
            "new_value": replacement["new"],
        })
    elif correction:
        operations.append({
            "operation": "correct_entity",
            "old_value": getattr(before, "topic", ""),
            "new_value": correction["topic"],
        })
        if correction.get("keep_intent"):
            operations.append({
                "operation": "keep_previous_intent",
                "value": getattr(before, "intent", ""),
            })
    elif topic_return:
        operations.append({
            "operation": "return_to_topic",
            "value": topic_return["target"],
        })
    elif method == "deterministic_assistant_artifact":
        operations.append({
            "operation": "select_artifact",
            "value": observation.get("referenced_entity") or "",
        })
    elif method in {"deterministic_continuation", "deterministic_rephrase"}:
        operations.append({
            "operation": "keep_previous_intent",
            "value": getattr(before, "intent", ""),
        })

    before_topic = str(getattr(before, "topic", "") or "")
    after_topic = str(getattr(after, "topic", "") or "")
    if before_topic != after_topic and after_topic and not any(
        item["operation"] in {"correct_entity", "return_to_topic"} for item in operations
    ):
        operations.append({
            "operation": "set_topic",
            "old_value": before_topic,
            "new_value": after_topic,
        })
        speech_act = apply_topic_transition(speech_act, before, after)

    before_constraints = list(getattr(before, "constraints", []) or [])
    after_constraints = list(getattr(after, "constraints", []) or [])
    if before_constraints != after_constraints and not any(
        item["operation"] == "replace_constraint" for item in operations
    ):
        for value in after_constraints:
            if value not in before_constraints:
                operations.append({"operation": "add_constraint", "value": value})
    return speech_act, operations
