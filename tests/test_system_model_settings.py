from backend.api import system
from llm.configuration import model_settings_payload


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
