from dataclasses import replace
from types import SimpleNamespace
from llm.configuration import resolve_model_role
from llm import tool_capability


def test_receipt_bound_to_exact_connection_and_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(tool_capability, '_path', lambda: tmp_path / 'capabilities.json')
    resolved = resolve_model_role('reasoning', {'LLM_REASONING_API_KEY': 'test-secret'})
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[
        SimpleNamespace(function=SimpleNamespace(name='texa_capability_probe', arguments='{"value":"texa-probe"}'))]))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    monkeypatch.setattr('llm.factory.build_openai_client', lambda *args, **kwargs: client)
    assert not tool_capability.has_verified_tool_capability(resolved)
    assert tool_capability.verify_tool_capability(resolved)
    assert tool_capability.has_verified_tool_capability(resolved)
    assert 'test-secret' not in (tmp_path / 'capabilities.json').read_text()
    for changed in (replace(resolved, api_key='changed'), replace(resolved, model='changed'),
                    replace(resolved, endpoint='https://other.invalid/v1'), replace(resolved, options={'changed': True})):
        assert not tool_capability.has_verified_tool_capability(changed)
    monkeypatch.setattr(tool_capability.time, 'time', lambda: 999999999999)
    assert not tool_capability.has_verified_tool_capability(resolved)


def test_malformed_probe_cannot_grant_capability(tmp_path, monkeypatch):
    monkeypatch.setattr(tool_capability, '_path', lambda: tmp_path / 'capabilities.json')
    resolved = resolve_model_role('reasoning', {'LLM_REASONING_API_KEY': 'test-secret'})
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[]))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    monkeypatch.setattr('llm.factory.build_openai_client', lambda *args, **kwargs: client)
    assert not tool_capability.verify_tool_capability(resolved)
    assert not tool_capability.has_verified_tool_capability(resolved)
