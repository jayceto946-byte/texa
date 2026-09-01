"""Transport factories for configured model roles."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable

from llm.types import Capability, ModelSpec, ProviderSpec, ResolvedModelRole


_cache: dict[tuple, object] = {}
_cache_lock = threading.RLock()
_chat_transports: dict[str, Callable[..., object]] = {}
_vision_transports: dict[str, Callable[..., object]] = {}
_transport_capabilities: dict[str, frozenset[Capability]] = {}


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


def _register_transport_capabilities(name: str, capabilities: frozenset[Capability]) -> None:
    current = _transport_capabilities.get(name, frozenset())
    _transport_capabilities[name] = current | capabilities


def register_chat_transport(
    name: str,
    factory: Callable[..., object],
    *,
    capabilities: frozenset[Capability],
) -> None:
    _chat_transports[name] = factory
    _register_transport_capabilities(name, capabilities)


def register_vision_transport(name: str, factory: Callable[..., object]) -> None:
    _vision_transports[name] = factory
    _register_transport_capabilities(name, frozenset({Capability.VISION}))


def transport_capabilities(name: str) -> frozenset[Capability]:
    try:
        return _transport_capabilities[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported LLM transport {name!r}") from exc


def validate_provider_runtime_contract(provider: ProviderSpec) -> None:
    """Reject catalog claims which have no executable transport implementation."""
    unsupported = provider.capabilities - transport_capabilities(provider.transport)
    if unsupported:
        names = ", ".join(sorted(item.value for item in unsupported))
        raise ValueError(
            f"Provider {provider.provider_id!r} declares capabilities without runtime transport support: {names}"
        )


def validate_model_runtime_contract(model: ModelSpec, provider: ProviderSpec) -> None:
    unsupported_by_provider = model.capabilities - provider.capabilities
    if unsupported_by_provider:
        names = ", ".join(sorted(item.value for item in unsupported_by_provider))
        raise ValueError(
            f"Model {model.model_id!r} declares capabilities absent from provider {provider.provider_id!r}: {names}"
        )
    unsupported_by_transport = model.capabilities - transport_capabilities(provider.transport)
    if unsupported_by_transport:
        names = ", ".join(sorted(item.value for item in unsupported_by_transport))
        raise ValueError(
            f"Model {model.model_id!r} declares capabilities without runtime transport support: {names}"
        )


def ensure_runtime_support(resolved: ResolvedModelRole, capability: Capability) -> None:
    """Fail before a request if provider, model, or transport cannot satisfy it."""
    if capability not in resolved.provider.capabilities:
        raise ValueError(
            f"Provider {resolved.provider.provider_id!r} does not support capability {capability.value!r}"
        )
    from llm.registry import get_model

    model_spec = get_model(resolved.provider.provider_id, resolved.model)
    if model_spec is not None and capability not in model_spec.capabilities:
        raise ValueError(f"Model {resolved.model!r} does not support capability {capability.value!r}")
    if capability not in transport_capabilities(resolved.provider.transport):
        raise ValueError(
            f"Transport {resolved.provider.transport!r} cannot execute capability {capability.value!r}"
        )


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
    *,
    include_response_headers: bool,
    stream_usage: bool,
    request_timeout: float,
    max_retries: int,
):
    from langchain_openai import ChatOpenAI

    endpoint = resolved.endpoint.rstrip("/")
    if not endpoint.endswith("/v1"):
        endpoint = f"{endpoint}/v1"
    key = (
        "ollama", resolved.role.value, resolved.model, float(temperature), endpoint,
        bool(include_response_headers), bool(stream_usage), float(request_timeout), int(max_retries),
    )

    def create():
        kwargs = dict(
            model=resolved.model,
            temperature=temperature,
            api_key="ollama",
            base_url=endpoint,
            streaming=True,
            timeout=request_timeout,
            max_retries=max_retries,
            include_response_headers=include_response_headers,
            stream_usage=stream_usage,
        )
        if "http_socket_options" in getattr(ChatOpenAI, "model_fields", {}):
            kwargs["http_socket_options"] = ()
        return ChatOpenAI(**kwargs)

    return _cached(key, create)


register_chat_transport(
    "openai_compatible",
    _openai_compatible_chat,
    capabilities=frozenset({
        Capability.TEXT,
        Capability.REASONING,
        Capability.STREAMING,
        Capability.SYSTEM_PROMPT,
        Capability.TOKEN_USAGE,
        Capability.LOCAL,
    }),
)
register_chat_transport(
    "ollama",
    _ollama_chat,
    capabilities=frozenset({
        Capability.TEXT,
        Capability.REASONING,
        Capability.STREAMING,
        Capability.SYSTEM_PROMPT,
        Capability.LOCAL,
    }),
)


def build_chat_model(
    resolved: ResolvedModelRole,
    temperature: float,
    *,
    include_response_headers: bool = False,
    stream_usage: bool = False,
    request_timeout: float = 120,
    max_retries: int = 2,
):
    ensure_runtime_support(resolved, Capability.REASONING)
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
        raise ValueError(
            f"Transport {resolved.provider.transport!r} does not expose an OpenAI-compatible client"
        )
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


def _openai_compatible_vision_completion(
    resolved: ResolvedModelRole,
    *,
    messages: list[dict],
    max_tokens: int,
    timeout: float,
    stream: bool,
    client=None,
):
    request_client = client or build_openai_client(resolved, timeout=timeout, max_retries=0)
    extra_body = dict(resolved.options.get("extra_body") or {})
    return request_client.chat.completions.create(
        model=resolved.model,
        messages=messages,
        max_tokens=max_tokens,
        extra_body=extra_body or None,
        timeout=timeout,
        stream=stream,
    )


register_vision_transport("openai_compatible", _openai_compatible_vision_completion)


def create_vision_completion(
    resolved: ResolvedModelRole,
    *,
    messages: list[dict],
    max_tokens: int,
    timeout: float,
    stream: bool = False,
    client=None,
):
    """Execute the image request path shared by production vision and probes."""
    ensure_runtime_support(resolved, Capability.VISION)
    try:
        factory = _vision_transports[resolved.provider.transport]
    except KeyError as exc:
        raise ValueError(
            f"Transport {resolved.provider.transport!r} has no image request implementation"
        ) from exc
    return factory(
        resolved,
        messages=messages,
        max_tokens=max_tokens,
        timeout=timeout,
        stream=stream,
        client=client,
    )


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
