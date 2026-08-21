import os

from backend.api import system
from llm.configuration import model_settings_payload
from llm import profiles
from llm import connectivity


def test_model_settings_are_written_without_echoing_secret(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(system, "ENV_PATH", env_path)
    payload = model_settings_payload({})
    payload["roles"]["reasoning"].update({"provider": "openai", "model": "gpt-custom"})
    payload["endpoints"]["reasoning"]["base_url"] = "https://gateway.example/v1"
    payload["credentials"]["reasoning"]["api_key"] = "sk-private-value"

    result = system.save_model_settings(payload)

    assert result["success"] is True
    assert "sk-private-value" in env_path.read_text(encoding="utf-8")
    assert "sk-private-value" not in str(result)
    assert result["data"]["roles"]["reasoning"]["model"] == "gpt-custom"


def test_blank_key_preserves_existing_env_value(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("LLM_REASONING_API_KEY=existing-secret\n", encoding="utf-8")
    monkeypatch.setattr(system, "ENV_PATH", env_path)
    payload = model_settings_payload({})

    result = system.save_model_settings(payload)

    assert result["success"] is True
    assert "LLM_REASONING_API_KEY=existing-secret" in env_path.read_text(encoding="utf-8")


def test_named_profile_keeps_secret_out_of_profile_file(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    profile_path = tmp_path / "model_profiles.json"
    monkeypatch.setattr(system, "ENV_PATH", env_path)
    monkeypatch.setattr(profiles, "PROFILE_PATH", profile_path)
    payload = model_settings_payload({})
    payload.update({"id": "daily-study", "name": "日常学习"})
    payload["roles"]["reasoning"]["credential_id"] = "deepseek"
    payload["credentials"]["reasoning"]["api_key"] = "profile-secret"

    result = system.save_model_profile({"profile": payload, "activate": True})

    assert result["success"] is True
    assert result["data"]["active_profile_id"] == "daily-study"
    assert "日常学习" in profile_path.read_text(encoding="utf-8")
    assert "profile-secret" not in profile_path.read_text(encoding="utf-8")
    assert "LLM_CREDENTIAL_DEEPSEEK_API_KEY=profile-secret" in env_path.read_text(encoding="utf-8")


def test_profile_can_be_activated_with_one_request(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(profiles, "PROFILE_PATH", tmp_path / "model_profiles.json")
    payload = model_settings_payload({})
    payload.update({"id": "native-vision", "name": "图片直解", "multimodal_mode": "native"})
    system.save_model_profile({"profile": payload, "activate": False})

    result = system.activate_model_profile("native-vision")

    assert result["success"] is True
    assert result["data"]["active_profile_id"] == "native-vision"
    assert result["data"]["multimodal_mode"] == "native"


def test_saving_profile_migrates_existing_role_key_to_credential_slot(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(system, "ENV_PATH", env_path)
    monkeypatch.setattr(profiles, "PROFILE_PATH", tmp_path / "model_profiles.json")
    monkeypatch.setenv("LLM_REASONING_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_REASONING_MODEL", "deepseek-v4-pro")
    monkeypatch.delenv("LLM_REASONING_CREDENTIAL_ID", raising=False)
    monkeypatch.delenv("LLM_CREDENTIAL_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("LLM_REASONING_API_KEY", "existing-role-secret")
    payload = model_settings_payload(os.environ)
    payload.update({"id": "migrated", "name": "迁移方案"})

    result = system.save_model_profile({"profile": payload, "activate": True})

    assert result["success"] is True
    assert "LLM_CREDENTIAL_DEEPSEEK_API_KEY=existing-role-secret" in env_path.read_text(encoding="utf-8")


def test_connection_check_uses_unsaved_custom_model_and_does_not_write_env(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(system, "ENV_PATH", env_path)
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)

    class Client:
        chat = type("Chat", (), {"completions": Completions()})()

    monkeypatch.setattr(connectivity, "build_openai_client", lambda *args, **kwargs: Client())
    payload = model_settings_payload({})
    payload["roles"]["reasoning"].update({
        "provider": "openai_compatible",
        "model": "new-model-from-provider",
        "credential_id": "draft-custom",
    })
    payload["endpoints"]["reasoning"]["base_url"] = "https://gateway.example/v1"
    payload["credentials"]["reasoning"]["api_key"] = "draft-secret"

    result = system.test_model_connection({"role": "reasoning", "settings": payload})

    assert result["success"] is True
    assert result["data"]["model"] == "new-model-from-provider"
    assert calls[0]["model"] == "new-model-from-provider"
    assert not env_path.exists()
    assert "draft-secret" not in str(result)


def test_connection_error_does_not_echo_draft_secret(monkeypatch):
    def fail(_resolved):
        raise RuntimeError("upstream rejected secret-token-value")

    monkeypatch.setitem(connectivity._testers, "openai_compatible", fail)
    payload = model_settings_payload({})
    payload["roles"]["reasoning"].update({"provider": "openai", "model": "gpt-custom"})
    payload["credentials"]["reasoning"]["api_key"] = "secret-token-value"

    result = system.test_model_connection({"role": "reasoning", "settings": payload})

    assert result["success"] is False
    assert "secret-token-value" not in result["message"]
