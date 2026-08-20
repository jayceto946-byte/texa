import os

from llm.configuration import model_settings_env_values, model_settings_payload, resolve_model_role


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


def test_settings_payload_never_contains_api_key(monkeypatch):
    monkeypatch.setenv("LLM_REASONING_API_KEY", "top-secret")
    payload = model_settings_payload(os.environ)

    assert payload["credentials"]["reasoning"]["configured"] is True
    assert "top-secret" not in str(payload)


def test_custom_openai_compatible_role_accepts_model_and_endpoint():
    payload = model_settings_payload({})
    payload["roles"]["reasoning"].update({"provider": "openai_compatible", "model": "private-reasoner"})
    payload["endpoints"]["reasoning"]["base_url"] = "http://127.0.0.1:8001/v1"
    payload["credentials"]["reasoning"]["api_key"] = "local-token"

    values = model_settings_env_values(payload)

    assert values["LLM_REASONING_PROVIDER"] == "openai_compatible"
    assert values["LLM_REASONING_MODEL"] == "private-reasoner"
    assert values["LLM_REASONING_BASE_URL"] == "http://127.0.0.1:8001/v1"
    assert values["LLM_REASONING_API_KEY"] == "local-token"


def test_role_capability_is_validated():
    payload = model_settings_payload({})
    payload["roles"]["vision"]["provider"] = "deepseek"

    try:
        model_settings_env_values(payload)
    except ValueError as exc:
        assert "不支持vision角色" in str(exc)
    else:
        raise AssertionError("vision role accepted a text-only provider")
