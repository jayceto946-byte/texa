import pytest

from backend.services.resolver_speech_act import classify_speech_act
from backend.services.semantic_resolver import (
    run_semantic_resolver,
    should_attempt_semantic_resolution,
    validate_semantic_operations,
)
from backend.services.session_context import SessionContextState, build_resolution_trace


def _state():
    return SessionContextState(
        topic="压阻效应",
        entities=["压阻效应", "压电效应"],
        topic_stack=["压电效应", "压阻效应"],
    )


def test_speech_act_layer_is_independently_classified():
    assert classify_speech_act(method="identity") == "ask"
    assert classify_speech_act(method="identity", has_correction=True) == "correction"
    assert classify_speech_act(method="deterministic_rephrase") == "continue"
    assert classify_speech_act(method="identity", should_clarify=True) == "clarification"


def test_semantic_resolver_only_runs_for_enabled_low_confidence_reference():
    unresolved = {"method": "unresolved_reference", "confidence": 0.0}
    assert should_attempt_semantic_resolution(unresolved, enabled=False) is False
    assert should_attempt_semantic_resolution(unresolved, enabled=True) is True
    assert should_attempt_semantic_resolution(
        {"method": "deterministic_anaphora", "confidence": 0.94}, enabled=True,
    ) is False


def test_semantic_resolver_accepts_only_bounded_candidate_or_clarify():
    state = _state()
    resolved = validate_semantic_operations({
        "state_operations": [{"operation": "resolve_reference", "value": "压电效应"}],
    }, state)
    assert resolved.operation == {"operation": "resolve_reference", "value": "压电效应"}

    with pytest.raises(ValueError, match="outside bounded candidates"):
        validate_semantic_operations({
            "state_operations": [{"operation": "resolve_reference", "value": "模型新增对象"}],
        }, state)
    with pytest.raises(ValueError, match="not allowed"):
        validate_semantic_operations({
            "state_operations": [{"operation": "set_topic", "value": "压电效应"}],
        }, state)


def test_semantic_resolver_filters_thinking_and_never_returns_freeform_query():
    result = run_semantic_resolver(
        "那个呢？", _state(),
        model_runner=lambda _prompt: (
            '<think>private</think>{"state_operations":['
            '{"operation":"resolve_reference","value":"压电效应"}]}'
        ),
    )
    assert result.operation["value"] == "压电效应"


def test_resolution_trace_uses_semantic_reference_without_direct_state_write():
    history = [{"role": "user", "content": "什么是压阻效应？", "turn_id": "t1"}]
    trace = build_resolution_trace(
        "第九个是什么意思？", history,
        initial_state={
            "topic": "压阻效应", "entities": ["压阻效应"],
            "topic_stack": ["压阻效应"],
        },
        semantic_enabled=True,
        semantic_model_runner=lambda _prompt: (
            '{"state_operations":[{"operation":"resolve_reference","value":"压阻效应"}]}'
        ),
    )
    assert trace["method"] == "semantic_reference"
    assert trace["speech_act"] == "followup"
    assert trace["state_operations"][0] == {
        "operation": "resolve_reference", "value": "压阻效应",
    }
    assert trace["referenced_turn_ids"] == ["t1"]
    assert trace["semantic_resolver"] == {"attempted": True, "error": ""}


def test_invalid_semantic_output_falls_back_to_clarification():
    trace = build_resolution_trace(
        "第九个是什么意思？", [],
        initial_state={"topic": "压阻效应", "entities": ["压阻效应"]},
        semantic_enabled=True,
        semantic_model_runner=lambda _prompt: (
            '{"state_operations":[{"operation":"set_topic","value":"任意对象"}]}'
        ),
    )
    assert trace["resolution_action"] == "clarify"
    assert trace["semantic_resolver"]["attempted"] is True
    assert "not allowed" in trace["semantic_resolver"]["error"]
