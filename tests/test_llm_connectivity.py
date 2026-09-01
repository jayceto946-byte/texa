from copy import deepcopy
from types import SimpleNamespace

import pytest

from llm import connectivity
from llm.configuration import model_settings_payload


def _response(content: str = "OK"):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content),
    )])


def test_text_connectivity_executes_minimal_completion(monkeypatch):
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return _response()

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    monkeypatch.setattr(connectivity, "build_openai_client", lambda *args, **kwargs: client)
    payload = model_settings_payload({})
    payload["credentials"]["reasoning"]["api_key"] = "test-key"

    resolved = connectivity.test_model_settings_connection(payload, "reasoning")

    assert resolved.model == "qwen3.7-plus"
    assert calls[0]["messages"] == [{"role": "user", "content": "Reply with OK."}]
    assert calls[0]["stream"] is False


def test_text_connectivity_failure_names_actual_text_request(monkeypatch):
    def fail(_resolved):
        raise TimeoutError("upstream timeout")

    monkeypatch.setitem(connectivity._testers, "openai_compatible", fail)
    payload = model_settings_payload({})
    payload["credentials"]["reasoning"]["api_key"] = "test-key"

    with pytest.raises(RuntimeError, match="文本实际请求失败：upstream timeout"):
        connectivity.test_model_settings_connection(payload, "reasoning")


def test_ollama_text_connectivity_invokes_runtime_model(monkeypatch):
    invocations = []

    class Runtime:
        def invoke(self, prompt):
            invocations.append(prompt)
            return SimpleNamespace(content="OK")

    monkeypatch.setattr(connectivity, "build_chat_model", lambda *args, **kwargs: Runtime())
    payload = model_settings_payload({})
    payload["roles"]["reasoning"].update({"provider": "ollama", "model": "qwen2.5:7b"})
    payload["endpoints"]["reasoning"]["base_url"] = "http://localhost:11434"

    resolved = connectivity.test_model_settings_connection(payload, "reasoning")

    assert resolved.provider.provider_id == "ollama"
    assert invocations == ["Reply with OK."]


def test_vision_connectivity_uses_shared_image_completion_without_mutating_profile(monkeypatch):
    calls = []

    def complete(resolved, **kwargs):
        calls.append((resolved, kwargs))
        return _response("white")

    monkeypatch.setattr(connectivity, "create_vision_completion", complete)
    payload = model_settings_payload({})
    payload["credentials"]["vision"]["api_key"] = "test-key"
    before = deepcopy(payload)

    resolved = connectivity.test_model_settings_connection(payload, "vision")

    assert payload == before
    assert resolved.model == payload["roles"]["vision"]["model"]
    content = calls[0][1]["messages"][0]["content"]
    image = next(item for item in content if item["type"] == "image_url")
    assert image["image_url"]["url"].startswith("data:image/png;base64,")
    assert calls[0][1]["stream"] is False


def test_vision_connectivity_failure_names_actual_image_request(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("model rejected image input")

    monkeypatch.setattr(connectivity, "create_vision_completion", fail)
    payload = model_settings_payload({})
    payload["credentials"]["vision"]["api_key"] = "test-key"

    with pytest.raises(RuntimeError, match="图片实际请求失败：model rejected image input"):
        connectivity.test_model_settings_connection(payload, "vision")
