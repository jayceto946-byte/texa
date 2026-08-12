"""Reference-resolution observation independent from state mutation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ReferenceResolverHooks:
    match_artifact: Callable[[str, list[dict[str, Any]]], dict[str, Any] | None]
    rephrase_followup: Callable[[str, Any], str]
    topic_correction: Callable[[str, Any], dict[str, Any] | None]
    constraint_replacement: Callable[[str, Any], dict[str, str] | None]
    topic_return: Callable[[str, Any], dict[str, str] | None]
    plural_reference: Callable[[str, Any], dict[str, Any] | None]
    ordinal_target: Callable[[str, Any], tuple[str, str] | None]
    infer_intent: Callable[[str], str]
    is_intent_fragment: Callable[[str, str], bool]
    has_anaphora: Callable[[str], bool]
    referenced_turn_ids: Callable[[list[dict], list[str]], list[str]]


def observe_reference_resolution(
    question: str,
    history: list[dict],
    state: Any,
    resolved: str,
    hooks: ReferenceResolverHooks,
) -> dict[str, Any]:
    """Describe the deterministic rule used; confidence remains rule strength."""
    compact = re.sub(r"\s+", "", question)
    referenced_entities: list[str] = []
    method = "identity"
    confidence = 1.0
    is_followup = False
    artifact = hooks.match_artifact(question, state.assistant_artifacts)
    rephrased = hooks.rephrase_followup(question, state)
    correction = hooks.topic_correction(question, state)
    replacement = hooks.constraint_replacement(question, state)
    topic_return = hooks.topic_return(question, state)
    plural = hooks.plural_reference(question, state)
    ordinal = hooks.ordinal_target(question, state)
    explicit_ordinal = re.search(
        r"第[一二三四五六七八九十\d]+(?:个公式|个|道题|部分|行|步)", question,
    )

    if rephrased:
        method, confidence, is_followup = "deterministic_rephrase", 0.98, True
        referenced_entities = [state.topic] if state.topic else []
    elif artifact:
        target = str(artifact.get("target") or "")
        method, confidence, is_followup = "deterministic_assistant_artifact", 0.97, True
        referenced_entities = [target] if target else []
    elif correction:
        method, confidence = "deterministic_topic_correction", 0.99
        is_followup = bool(correction.get("keep_intent"))
        referenced_entities = [str(correction["topic"])] if is_followup else []
    elif replacement:
        method, confidence, is_followup = "deterministic_constraint_replacement", 0.99, True
        referenced_entities = list(state.frame.get("entities") or [])
    elif topic_return:
        method, confidence, is_followup = "deterministic_topic_return", 0.99, True
        referenced_entities = [str(topic_return["target"])]
    elif re.match(
        r"^这个[\u4e00-\u9fffA-Za-z0-9_]{2,30}?(?:效应|定理|方法|算法|模型|公式|传感器)",
        question,
    ):
        method, confidence, is_followup = "deterministic_explicit_topic", 1.0, False
    elif plural:
        method, confidence, is_followup = "deterministic_plural_reference", 0.98, True
        referenced_entities = list(plural["entities"])
    elif ordinal:
        target = ordinal[0]
        rendered = target in resolved
        method = "deterministic_ordinal" if rendered else "incomplete_ordinal_resolution"
        confidence, is_followup, referenced_entities = (0.98 if rendered else 0.0), True, [target]
    elif explicit_ordinal:
        method, confidence, is_followup = "unresolved_reference", 0.0, True
    elif "前者" in compact or "后者" in compact:
        pair = list(state.frame.get("entities") or [])
        if len(pair) >= 2:
            target = pair[0] if "前者" in compact else pair[1]
            method, confidence, referenced_entities = "deterministic_comparison_reference", 0.98, [target]
        else:
            method, confidence = "unresolved_reference", 0.0
        is_followup = True
    elif state.frame.get("kind") == "comparison" and re.fullmatch(
        r"(?:那|那么)?(?:如果|若|假如)(?:考虑|是|在)?.+?(?:的话|呢)?[。？?!！]*", compact,
    ):
        method, confidence, is_followup = "deterministic_constraint_inheritance", 0.96, True
        referenced_entities = list(state.frame.get("entities") or [])
    else:
        intent = hooks.infer_intent(question)
        previous_pair = re.fullmatch(r"它和前面那个(?P<tail>.+)", compact)
        if previous_pair and len(state.entities) >= 2:
            method, confidence, is_followup = "deterministic_dual_reference", 0.96, True
            referenced_entities = [state.entities[-1], state.entities[-2]]
        elif state.topic and compact.strip("。？?!！") in {
            "继续讲", "继续说", "继续解释", "接着讲", "接着说",
        }:
            method, confidence, is_followup = "deterministic_continuation", 0.97, True
            referenced_entities = [state.topic]
        elif state.topic and hooks.is_intent_fragment(question, intent):
            method, confidence, is_followup = "deterministic_intent_inheritance", 0.96, True
            referenced_entities = [state.topic]
        elif hooks.has_anaphora(question):
            is_followup = True
            if state.topic:
                method, confidence, referenced_entities = "deterministic_anaphora", 0.94, [state.topic]
            else:
                method, confidence = "unresolved_reference", 0.0
        elif resolved != question.strip():
            method, confidence = "deterministic_normalization", 1.0

    artifact_turn_ids = [str(artifact["turn_id"])] if artifact and artifact.get("turn_id") else []
    state_turn_ids: list[str] = []
    for entity in referenced_entities:
        record = next((
            item for item in reversed(state.entity_records) if item.get("name") == entity
        ), None)
        turn_id = str((record or {}).get("last_turn_id") or "")
        if turn_id and turn_id not in state_turn_ids:
            state_turn_ids.append(turn_id)
    return {
        "is_followup": is_followup,
        "resolution_changed": resolved != question.strip(),
        "method": method,
        "confidence": confidence,
        "confidence_kind": "rule_strength",
        "referenced_entity": referenced_entities[0] if referenced_entities else "",
        "referenced_entities": referenced_entities,
        "referenced_turn_ids": artifact_turn_ids or state_turn_ids or hooks.referenced_turn_ids(
            history, referenced_entities,
        ),
    }
