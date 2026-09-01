from types import SimpleNamespace

import pytest

from llm.configuration import model_settings_payload, resolve_model_role
from llm.factory import (
    build_chat_model,
    create_vision_completion,
    validate_model_runtime_contract,
    validate_provider_runtime_contract,
)
from llm.registry import get_model, get_provider, list_models, list_providers
from llm.types import Capability


def _role_env(provider_id: str, model_id: str, role: str) -> dict[str, str]:
    prefix = f"LLM_{role.upper()}"
    provider = get_provider(provider_id)
    return {
        f"{prefix}_PROVIDER": provider_id,
        f"{prefix}_MODEL": model_id,
        f"{prefix}_BASE_URL": provider.default_endpoint or "http://127.0.0.1:8001/v1",
        f"{prefix}_API_KEY": "test-key",
    }


def test_every_catalog_capability_is_backed_by_provider_and_transport_runtime():
    for provider in list_providers():
        validate_provider_runtime_contract(provider)
    for model in list_models():
        validate_model_runtime_contract(model, get_provider(model.provider_id))


def test_every_declared_reasoning_model_can_construct_runtime_client():
    declared = [item for item in list_models() if Capability.REASONING in item.capabilities]

    assert declared
    for model in declared:
        resolved = resolve_model_role(
            "reasoning",
            _role_env(model.provider_id, model.model_id, "reasoning"),
        )
        runtime = build_chat_model(resolved, 0, request_timeout=1, max_retries=0)
        assert callable(getattr(runtime, "invoke", None)), (model.provider_id, model.model_id)


def test_custom_openai_compatible_reasoning_model_constructs_without_catalog_fallback():
    resolved = resolve_model_role("reasoning", {
        "LLM_REASONING_PROVIDER": "openai_compatible",
        "LLM_REASONING_MODEL": "private-model-id",
        "LLM_REASONING_BASE_URL": "http://127.0.0.1:8001/v1",
    })

    runtime = build_chat_model(resolved, 0, request_timeout=1, max_retries=0)

    assert resolved.model == "private-model-id"
    assert getattr(runtime, "model_name", None) == "private-model-id"


def test_every_declared_vision_model_executes_shared_image_request_shape(monkeypatch):
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="white"),
            )])

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    monkeypatch.setattr("llm.factory.build_openai_client", lambda *args, **kwargs: client)
    declared = [item for item in list_models() if Capability.VISION in item.capabilities]

    assert declared
    for model in declared:
        resolved = resolve_model_role(
            "vision",
            _role_env(model.provider_id, model.model_id, "vision"),
        )
        response = create_vision_completion(
            resolved,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe the image."},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                ],
            }],
            max_tokens=32,
            timeout=1,
        )
        assert response.choices[0].message.content == "white"

    assert len(calls) == len(declared)
    for request in calls:
        content = request["messages"][0]["content"]
        assert any(item.get("type") == "image_url" for item in content)
        assert request["stream"] is False


def test_ollama_vision_is_absent_and_rejected_without_fallback():
    provider = get_provider("ollama")

    assert Capability.VISION not in provider.capabilities
    assert "vision" not in {role.value for role in provider.default_models}
    assert get_model("ollama", "qwen2.5vl:7b") is None

    with pytest.raises(ValueError, match="does not support the vision role"):
        resolve_model_role("vision", {
            "LLM_VISION_PROVIDER": "ollama",
            "LLM_VISION_MODEL": "qwen2.5vl:7b",
            "LLM_VISION_BASE_URL": "http://localhost:11434",
        })


def test_invalid_model_capability_fails_instead_of_switching_model_or_provider():
    with pytest.raises(ValueError, match="does not support the vision role"):
        resolve_model_role("vision", {
            "LLM_VISION_PROVIDER": "qwen",
            "LLM_VISION_MODEL": "qwen-plus",
        })


def test_settings_catalog_reports_reasoning_as_the_reasoning_role_requirement():
    payload = model_settings_payload({})

    assert payload["roles"]["reasoning"]["required_capabilities"] == ["reasoning"]
    ollama = next(item for item in payload["providers"] if item["id"] == "ollama")
    assert "vision" not in ollama["capabilities"]
    assert "vision" not in ollama["default_models"]
