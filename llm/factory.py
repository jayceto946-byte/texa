"""Transport factories for configured model roles."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable

from llm.types import ResolvedModelRole


_cache: dict[tuple, object] = {}
_cache_lock = threading.RLock()
_chat_transports: dict[str, Callable[..., object]] = {}


def _cached(key: tuple, factory: Callable[[], object]):
    with _cache_lock:
        instance = _cache.get(key)
        if instance is None:
            instance = factory()
            _cache[key] = instance
        return instance


def clear_model_cache() -> None:
    with _cache_lock:
        _cache.clear()


def register_chat_transport(name: str, factory: Callable[..., object]) -> None:
    _chat_transports[name] = factory


def _openai_compatible_chat(
    resolved: ResolvedModelRole,
    temperature: float,
    *,
    include_response_headers: bool,
    stream_usage: bool,
    request_timeout: float,
    max_retries: int,
):
    from langchain_openai import ChatOpenAI

    extra_body = dict(resolved.options.get("extra_body") or {})
    normalized_extra = json.dumps(extra_body, ensure_ascii=False, sort_keys=True)
    key = (
        "chat", resolved.provider.provider_id, resolved.role.value, resolved.model,
        float(temperature), resolved.api_key, resolved.endpoint, normalized_extra,
        bool(include_response_headers), bool(stream_usage), float(request_timeout), int(max_retries),
    )

    def create():
        kwargs = dict(
            model=resolved.model,
            temperature=temperature,
            api_key=resolved.api_key or "not-required",
            base_url=resolved.endpoint,
            streaming=True,
            timeout=request_timeout,
            max_retries=max_retries,
            include_response_headers=include_response_headers,
            stream_usage=stream_usage,
        )
        if "http_socket_options" in getattr(ChatOpenAI, "model_fields", {}):
            kwargs["http_socket_options"] = ()
        if extra_body:
            kwargs["extra_body"] = extra_body
        return ChatOpenAI(**kwargs)

    return _cached(key, create)


def _ollama_chat(
    resolved: ResolvedModelRole,
    temperature: float,
    **_kwargs,
):
    from langchain_community.chat_models import ChatOllama
    key = ("ollama", resolved.role.value, resolved.model, float(temperature), resolved.endpoint)
    return _cached(key, lambda: ChatOllama(
        model=resolved.model,
        temperature=temperature,
        base_url=resolved.endpoint,
    ))


register_chat_transport("openai_compatible", _openai_compatible_chat)
register_chat_transport("ollama", _ollama_chat)


def build_chat_model(
    resolved: ResolvedModelRole,
    temperature: float,
    *,
    include_response_headers: bool = False,
    stream_usage: bool = False,
    request_timeout: float = 120,
    max_retries: int = 2,
):
    try:
        factory = _chat_transports[resolved.provider.transport]
    except KeyError as exc:
        raise ValueError(f"Unsupported LLM transport {resolved.provider.transport!r}") from exc
    return factory(
        resolved,
        temperature,
        include_response_headers=include_response_headers,
        stream_usage=stream_usage,
        request_timeout=request_timeout,
        max_retries=max_retries,
    )


def build_openai_client(resolved: ResolvedModelRole, *, timeout: float = 120, max_retries: int = 0):
    if resolved.provider.transport != "openai_compatible":
        return None
    import httpx
    from openai import OpenAI
    key = (
        "openai-client", resolved.provider.provider_id, resolved.role.value,
        resolved.api_key, resolved.endpoint, float(timeout), int(max_retries),
    )
    return _cached(key, lambda: OpenAI(
        api_key=resolved.api_key or "not-required",
        base_url=resolved.endpoint,
        http_client=httpx.Client(trust_env=False, timeout=timeout),
        max_retries=max_retries,
    ))


# Backward-compatible low-level helper retained for tests and external scripts.
def get_chat_model(
    model: str,
    temperature: float,
    api_key: str,
    base_url: str,
    extra_body: dict | None = None,
    *,
    include_response_headers: bool = False,
    stream_usage: bool = False,
    request_timeout: float = 120,
    max_retries: int = 2,
):
    from llm.registry import ProviderSpec
    from llm.types import Capability, ModelRole
    resolved = ResolvedModelRole(
        role=ModelRole.REASONING,
        provider=ProviderSpec(
            provider_id="legacy", label="Legacy", transport="openai_compatible",
            capabilities=frozenset({Capability.TEXT}), default_endpoint=base_url,
            default_models={ModelRole.REASONING: model},
        ),
        model=model, api_key=api_key, endpoint=base_url,
        options={"extra_body": extra_body or {}},
    )
    return _openai_compatible_chat(
        resolved, temperature,
        include_response_headers=include_response_headers,
        stream_usage=stream_usage,
        request_timeout=request_timeout,
        max_retries=max_retries,
    )
