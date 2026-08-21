"""Provider-neutral connectivity checks for unsaved model settings."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from llm.configuration import model_settings_env_values, resolve_model_role
from llm.factory import build_openai_client
from llm.types import ResolvedModelRole


ConnectionTester = Callable[[ResolvedModelRole], None]
_testers: dict[str, ConnectionTester] = {}


def register_connection_tester(transport: str, tester: ConnectionTester) -> None:
    _testers[transport] = tester


def _test_openai_compatible(resolved: ResolvedModelRole) -> None:
    client = build_openai_client(resolved, timeout=20, max_retries=0)
    extra_body = dict(resolved.options.get("extra_body") or {})
    client.chat.completions.create(
        model=resolved.model,
        messages=[{"role": "user", "content": "Reply with OK."}],
        stream=False,
        extra_body=extra_body or None,
    )


def _test_ollama(resolved: ResolvedModelRole) -> None:
    import httpx

    response = httpx.get(f"{resolved.endpoint.rstrip('/')}/api/tags", timeout=10, trust_env=False)
    response.raise_for_status()
    names = {str(item.get("name", "")) for item in response.json().get("models", [])}
    if resolved.model not in names and f"{resolved.model}:latest" not in names:
        raise ValueError(f"本地服务可访问，但未找到模型 {resolved.model}")


register_connection_tester("openai_compatible", _test_openai_compatible)
register_connection_tester("ollama", _test_ollama)


def test_model_settings_connection(payload: Mapping[str, object], role: str) -> ResolvedModelRole:
    if role not in {"reasoning", "vision"}:
        raise ValueError("role 必须是 reasoning 或 vision")
    values = dict(os.environ)
    values.update(model_settings_env_values(payload))
    resolved = resolve_model_role(role, values)
    if resolved.provider.requires_api_key and not resolved.api_key:
        raise ValueError("请先填写 API Key")
    try:
        tester = _testers[resolved.provider.transport]
    except KeyError as exc:
        raise ValueError(f"{resolved.provider.label} 暂不支持连接测试") from exc
    tester(resolved)
    return resolved
