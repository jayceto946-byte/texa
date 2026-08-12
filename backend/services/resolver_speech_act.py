"""Pure speech-act classification for the structured session resolver."""
from __future__ import annotations

from typing import Any

from backend.services.learning_state_bridge import classify_learning_speech_act


def classify_speech_act(
    *,
    method: str,
    has_replacement: bool = False,
    has_correction: bool = False,
    has_topic_return: bool = False,
    is_followup: bool = False,
    should_clarify: bool = False,
) -> str:
    if should_clarify:
        return "clarification"
    if has_replacement or has_correction:
        return "correction"
    if has_topic_return:
        return "return"
    if method in {"deterministic_continuation", "deterministic_rephrase"}:
        return "continue"
    if is_followup:
        return "followup"
    return "ask"


def apply_topic_transition(speech_act: str, before: Any, after: Any) -> str:
    """Turn a fresh ask into an explicit topic switch after state comparison."""
    before_topic = str(getattr(before, "topic", "") or "")
    after_topic = str(getattr(after, "topic", "") or "")
    if speech_act == "ask" and before_topic and after_topic and before_topic != after_topic:
        return "switch_topic"
    return speech_act


def apply_learning_speech_act(question: str, speech_act: str) -> str:
    """Learning commands override conversational ask/follow-up labels only."""
    learning_act = classify_learning_speech_act(question)
    return learning_act or speech_act
