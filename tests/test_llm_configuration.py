import os

from llm.configuration import model_settings_env_values, model_settings_payload, resolve_model_role
from llm.registry import get_model, list_models
from llm.types import Capability


def test_unconfigured_default_is_qwen37_plus_for_both_roles():
    payload = model_settings_payload({})
    resolved = resolve_model_role("reasoning", {})

    assert resolved.provider.provider_id == "qwen"
    assert resolved.model == "qwen3.7-plus"
    assert resolved.options["extra_body"]["enable_thinking"] is True
    assert payload["multimodal_mode"] == "split"
    assert payload["roles"]["reasoning"]["model"] == "qwen3.7-plus"
    assert payload["roles"]["vision"]["model"] == "qwen3.7-plus"


def test_legacy_environment_preserves_deepseek_default():
    resolved = resolve_model_role("reasoning", {
        "LLM_BACKEND": "deepseek",
        "DEEPSEEK_API_KEY": "legacy-secret",
        "DEEPSEEK_MODEL_NAME": "deepseek-v4-pro",
    })

    assert resolved.provider.provider_id == "deepseek"
    assert resolved.model == "deepseek-v4-pro"
    assert resolved.api_key == "legacy-secret"
    assert resolved.options["extra_body"]["reasoning_effort"] == "high"


def test_custom_model_does_not_inherit_model_specific_reasoning_parameters():
    resolved = resolve_model_role("reasoning", {
        "LLM_REASONING_PROVIDER": "deepseek",
        "LLM_REASONING_MODEL": "deepseek-chat",
    })

    assert resolved.options == {}


def test_explicit_credential_slot_does_not_reuse_legacy_role_key():
    resolved = resolve_model_role("reasoning", {
        "LLM_REASONING_PROVIDER": "qwen",
        "LLM_REASONING_MODEL": "qwen-plus",
        "LLM_REASONING_CREDENTIAL_ID": "qwen",
        "LLM_REASONING_API_KEY": "old-deepseek-key",
    })

    assert resolved.api_key == ""


def test_settings_payload_never_contains_api_key(monkeypatch):
    monkeypatch.setenv("LLM_REASONING_API_KEY", "top-secret")
    payload = model_settings_payload(os.environ)

    assert payload["credentials"]["reasoning"]["configured"] is True
    assert "top-secret" not in str(payload)


def test_custom_openai_compatible_role_accepts_model_and_endpoint():
    payload = model_settings_payload({})
    payload["roles"]["reasoning"].update({"provider": "openai_compatible", "model": "private-reasoner", "credential_id": "local-gateway"})
    payload["endpoints"]["reasoning"]["base_url"] = "http://127.0.0.1:8001/v1"
    payload["credentials"]["reasoning"]["api_key"] = "local-token"

    values = model_settings_env_values(payload)

    assert values["LLM_REASONING_PROVIDER"] == "openai_compatible"
    assert values["LLM_REASONING_MODEL"] == "private-reasoner"
    assert values["LLM_REASONING_BASE_URL"] == "http://127.0.0.1:8001/v1"
    assert values["LLM_CREDENTIAL_LOCAL_GATEWAY_API_KEY"] == "local-token"


def test_role_capability_is_validated():
    payload = model_settings_payload({})
    payload["roles"]["vision"]["provider"] = "deepseek"

    try:
        model_settings_env_values(payload)
    except ValueError as exc:
        assert "不支持vision角色" in str(exc)
    else:
        raise AssertionError("vision role accepted a text-only provider")


def test_catalog_includes_current_provider_models_and_keeps_compatibility_aliases():
    ids = {(item.provider_id, item.model_id) for item in list_models()}

    assert ("deepseek", "deepseek-v4-pro") in ids
    assert ("qwen", "qwen3.8-max") in ids
    assert ("gemini", "gemini-3.7-flash") in ids
    assert ("openai", "gpt-5.6-terra") in ids
    assert ("openai", "gpt-4o-mini") in ids


def test_qwen37_plus_is_available_to_integrated_text_and_vision_mode():
    model = get_model("qwen", "qwen3.7-plus")

    assert model is not None
    assert Capability.TEXT in model.capabilities
    assert Capability.VISION in model.capabilities

    payload = model_settings_payload({})
    payload["multimodal_mode"] = "native"
    payload["roles"]["vision"].update({
        "provider": "qwen",
        "model": "qwen3.7-plus",
        "credential_id": "qwen",
    })
    payload["endpoints"]["vision"]["base_url"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    values = model_settings_env_values(payload)

    assert values["LLM_REASONING_MODEL"] == "qwen3.7-plus"
    assert values["LLM_VISION_MODEL"] == "qwen3.7-plus"
    assert values["LLM_MULTIMODAL_MODE"] == "native"
