"""Opt-in semantic fallback that can only propose validated state operations."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

from utils.thinking_filter import strip_thinking


SEMANTIC_RESOLVER_POLICY_VERSION = "semantic-resolver-v1"
SEMANTIC_RESOLVER_MAX_CANDIDATES = 24
SEMANTIC_RESOLVER_MAX_INPUT_CHARS = 4000


@dataclass(frozen=True)
class SemanticResolution:
    operation: dict[str, str]
    method: str
    confidence: float


def semantic_resolver_enabled() -> bool:
    return os.getenv("SEMANTIC_RESOLVER_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def should_attempt_semantic_resolution(
    observation: dict[str, Any], *, enabled: bool | None = None,
) -> bool:
    active = semantic_resolver_enabled() if enabled is None else bool(enabled)
    return active and str(observation.get("method") or "") in {
        "unresolved_reference", "incomplete_ordinal_resolution",
    } and float(observation.get("confidence") or 0.0) <= 0.5


def _candidate_values(state: Any) -> list[str]:
    values = [
        str(getattr(state, "topic", "") or ""),
        *(str(value or "") for value in getattr(state, "entities", []) or []),
        *(str(value or "") for value in getattr(state, "topic_stack", []) or []),
    ]
    for artifact in getattr(state, "assistant_artifacts", []) or []:
        if isinstance(artifact, dict):
            values.append(str(artifact.get("target") or ""))
    result: list[str] = []
    for value in reversed(values):
        clean = " ".join(value.strip().split())[:200]
        if clean and clean not in result:
            result.append(clean)
        if len(result) >= SEMANTIC_RESOLVER_MAX_CANDIDATES:
            break
    return result


def _extract_json(text: str) -> dict[str, Any]:
    clean = strip_thinking(str(text or "")).strip()
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.I)
    start, end = clean.find("{"), clean.rfind("}")
    if start < 0 or end < start:
        raise ValueError("semantic resolver did not return a JSON object")
    value = json.loads(clean[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("semantic resolver payload must be an object")
    return value


def validate_semantic_operations(payload: dict[str, Any], state: Any) -> SemanticResolution:
    """Accept exactly one safe operation; arbitrary state mutation is rejected."""
    operations = payload.get("state_operations")
    if not isinstance(operations, list) or len(operations) != 1:
        raise ValueError("semantic resolver must return exactly one state operation")
    raw = operations[0]
    if not isinstance(raw, dict):
        raise ValueError("semantic resolver operation must be an object")
    operation = str(raw.get("operation") or "")
    if operation == "clarify":
        return SemanticResolution(
            operation={"operation": "clarify"},
            method="semantic_clarification",
            confidence=0.0,
        )
    if operation != "resolve_reference":
        raise ValueError("semantic resolver operation is not allowed")
    value = " ".join(str(raw.get("value") or "").strip().split())[:200]
    if value not in _candidate_values(state):
        raise ValueError("semantic resolver reference is outside bounded candidates")
    return SemanticResolution(
        operation={"operation": "resolve_reference", "value": value},
        method="semantic_reference",
        # This is an uncalibrated routing strength, not an accuracy probability.
        confidence=0.7,
    )


def _prompt(question: str, state: Any) -> str:
    candidates = _candidate_values(state)
    payload = {
        "question": str(question or "")[:1000],
        "candidate_references": candidates,
    }
    return (
        "你是对话指代路由器。只判断当前问题引用了哪个候选对象。"
        "不得回答问题，不得生成新对象，不得改写候选。\n"
        "只返回 JSON：若可确定，"
        '{"state_operations":[{"operation":"resolve_reference","value":"候选原文"}]}; '
        "否则返回 "
        '{"state_operations":[{"operation":"clarify"}]}。\n'
        f"输入：{json.dumps(payload, ensure_ascii=False)}"
    )[:SEMANTIC_RESOLVER_MAX_INPUT_CHARS]


def run_semantic_resolver(
    question: str,
    state: Any,
    *,
    model_runner: Callable[[str], str] | None = None,
) -> SemanticResolution:
    if model_runner is None:
        from config import get_llm

        llm = get_llm(temperature=0, request_timeout=20, max_retries=0)
        model_runner = lambda prompt: str(llm.invoke(prompt).content)
    payload = _extract_json(model_runner(_prompt(question, state)))
    return validate_semantic_operations(payload, state)
