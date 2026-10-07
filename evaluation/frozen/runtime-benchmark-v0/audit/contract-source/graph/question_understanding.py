"""Provider-independent, bounded interpretation contract; never an answer or tool plan."""
from __future__ import annotations

from typing import Any

VERSION = "question-understanding-v1"
INTENTS = frozenset({"qa", "definition", "factual_recall", "formula", "property",
                     "calculation", "derivation", "comparison", "application",
                     "teach", "summarize", "quiz", "plan", "cross_chapter"})
DIMENSIONS = {
    "definition": "定义", "classification": "分类", "comparison": "比较",
    "features": "特点", "examples": "举例", "scenarios": "应用场景",
    "principle": "原理", "formula": "公式", "derivation": "推导",
    "calculation": "计算", "exercises": "习题",
}
UNRESOLVED = frozenset({"unresolved_reference", "incomplete_ordinal_resolution"})


def validate_interpretation(payload: dict, request: dict) -> dict:
    """Copy only literal current spans or one Runtime-owned reference ID."""
    keys = {"action", "intent", "dimensions", "entity_spans", "reference_id"}
    if not isinstance(payload, dict) or set(payload) != keys:
        raise ValueError("invalid_schema")
    action, intent = payload["action"], payload["intent"]
    if action not in {"continue", "clarify"} or intent not in INTENTS:
        raise ValueError("invalid_enum")
    dimensions, spans = payload["dimensions"], payload["entity_spans"]
    if not isinstance(dimensions, list) or len(dimensions) > 4 or any(
        not isinstance(item, str) or item not in DIMENSIONS for item in dimensions
    ) or len(set(dimensions)) != len(dimensions):
        raise ValueError("invalid_dimensions")
    if not isinstance(spans, list) or len(spans) > 3:
        raise ValueError("invalid_spans")
    question = request["question"]
    entities = []
    previous_end = -1
    for span in spans:
        if not isinstance(span, dict) or set(span) != {"start", "end"}:
            raise ValueError("invalid_span")
        start, end = span["start"], span["end"]
        if type(start) is not int or type(end) is not int or not (
            0 <= start < end <= len(question) and 2 <= end - start <= 80 and start >= previous_end
        ):
            raise ValueError("invalid_span")
        value = question[start:end]
        if value != value.strip() or any(char in value for char in "\n，,。！？?!；;"):
            raise ValueError("invalid_span")
        entities.append(value)
        previous_end = end
    reference_id = payload["reference_id"]
    if not isinstance(reference_id, str):
        raise ValueError("invalid_reference")
    refs = {item["id"]: item["value"] for item in request["candidate_references"]}
    unresolved = request["rule"]["method"] in UNRESOLVED or request["rule"].get("reference_fallback") is True
    if reference_id and (reference_id not in refs or not unresolved or entities):
        raise ValueError("invalid_reference")
    if action == "clarify" and (not unresolved or entities or reference_id):
        raise ValueError("invalid_clarification")
    if action == "continue" and unresolved and not (entities or reference_id):
        raise ValueError("missing_reference")
    if request["rule"].get("intent_locked"):
        intent = request["rule"]["intent"]
    return {"version": VERSION, "accepted": True, "action": action, "intent": intent,
            "dimensions": dimensions, "entities": entities,
            "reference": refs.get(reference_id, ""), "reference_id": reference_id}


def interpretation_hint(pack: Any) -> dict:
    """Only the validated, versioned internal pack is consumed downstream."""
    if not isinstance(pack, dict) or pack.get("version") != VERSION or pack.get("accepted") is not True or pack.get("action") != "continue":
        return {}
    intent, dimensions = pack.get("intent"), pack.get("dimensions")
    if not isinstance(intent, str) or intent not in INTENTS or not isinstance(dimensions, list) or len(dimensions) > 4:
        return {}
    if any(not isinstance(item, str) or item not in DIMENSIONS for item in dimensions):
        return {}
    return {"intent": intent, "dimensions": list(dimensions)}


def retrieval_dimensions(pack: Any) -> str:
    return " ".join(DIMENSIONS[item] for item in interpretation_hint(pack).get("dimensions", []))


def interpretation_entities(pack: Any, question: str) -> list[str]:
    if not interpretation_hint(pack):
        return []
    entities = pack.get("entities", [])
    if not isinstance(entities, list) or len(entities) > 3:
        return []
    return [item for item in entities if isinstance(item, str) and 2 <= len(item) <= 80 and item in question]
