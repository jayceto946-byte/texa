"""Resolve role-oriented model settings with legacy environment fallback."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

from llm.factory import (
    ensure_runtime_support,
    validate_model_runtime_contract,
    validate_provider_runtime_contract,
)
from llm.registry import get_model, get_provider, list_models, list_providers
from llm.types import ModelRole, ResolvedModelRole, required_capability_for_role


ROLE_ENV_PREFIX = {
    ModelRole.REASONING: "LLM_REASONING",
    ModelRole.VISION: "LLM_VISION",
}


def credential_env_name(credential_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9]+", "_", credential_id.strip()).strip("_").upper()
    if not safe_id:
        raise ValueError("credential_id 不能为空")
    return f"LLM_CREDENTIAL_{safe_id}_API_KEY"


def _first(env: Mapping[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = str(env.get(name, "") or "").strip()
        if value:
            return value
    return ""


def _legacy_provider(role: ModelRole, env: Mapping[str, str]) -> str:
    if role is ModelRole.REASONING:
        return _first(env, ("LLM_PROVIDER", "LLM_BACKEND")) or "qwen"
    return _first(env, ("VISION_PROVIDER",)) or "qwen"


def resolve_model_role(
    role: ModelRole | str,
    env: Mapping[str, str] | None = None,
) -> ResolvedModelRole:
    role = role if isinstance(role, ModelRole) else ModelRole(role)
    source = env if env is not None else os.environ
    prefix = ROLE_ENV_PREFIX[role]
    provider_id = _first(source, (f"{prefix}_PROVIDER",)) or _legacy_provider(role, source)
    provider = get_provider(provider_id)
    if not provider.supports(role):
        raise ValueError(f"Provider {provider.provider_id!r} does not support the {role.value} role")

    model = _first(source, (f"{prefix}_MODEL",))
    if not model:
        model = _first(source, tuple(provider.legacy_model_env.get(role, ())))
    if not model:
        model = str(provider.default_models.get(role, "") or "")
    if not model:
        raise ValueError(f"No model configured for the {role.value} role")

    endpoint = _first(source, (f"{prefix}_BASE_URL",))
    if not endpoint:
        endpoint = _first(source, provider.legacy_endpoint_env)
    if not endpoint:
        endpoint = provider.default_endpoint

    explicit_credential_id = _first(source, (f"{prefix}_CREDENTIAL_ID",))
    credential_id = explicit_credential_id or provider.provider_id
    credential_sources = (credential_env_name(credential_id),) if explicit_credential_id else (credential_env_name(credential_id), f"{prefix}_API_KEY")
    api_key = _first(source, credential_sources)
    if not api_key:
        api_key = _first(source, provider.legacy_api_key_env)

    model_spec = get_model(provider.provider_id, model)
    required_capability = required_capability_for_role(role)
    if model_spec and required_capability not in model_spec.capabilities:
        raise ValueError(f"Model {model!r} does not support the {role.value} role")
    options = dict(model_spec.options) if model_spec else dict(provider.role_options.get(role, {}))
    resolved = ResolvedModelRole(
        role=role,
        provider=provider,
        model=model,
        api_key=api_key,
        endpoint=endpoint,
        options=options,
    )
    ensure_runtime_support(resolved, required_capability)
    return resolved


def model_settings_payload(env: Mapping[str, str] | None = None) -> dict:
    source = env if env is not None else os.environ
    providers = list_providers()
    models = list_models()
    for provider in providers:
        validate_provider_runtime_contract(provider)
    for model in models:
        validate_model_runtime_contract(model, get_provider(model.provider_id))
    roles = {}
    credentials = {}
    endpoints = {}
    for role in ModelRole:
        resolved = resolve_model_role(role, source)
        role_id = role.value
        required = required_capability_for_role(role)
        roles[role_id] = {
            "provider": resolved.provider.provider_id,
            "model": resolved.model,
            "credential_id": _first(source, (f"{ROLE_ENV_PREFIX[role]}_CREDENTIAL_ID",)) or resolved.provider.provider_id,
            "endpoint_id": role_id,
            "required_capabilities": [required.value],
        }
        credentials[role_id] = {
            "configured": resolved.credential_configured,
            "required": resolved.provider.requires_api_key,
            "value": "",
        }
        endpoints[role_id] = {
            "base_url": resolved.endpoint,
            "is_default": resolved.endpoint.rstrip("/") == resolved.provider.default_endpoint.rstrip("/"),
        }

    mode = str(source.get("LLM_MULTIMODAL_MODE", "split") or "split").strip().lower()
    return {
        "providers": [{
            "id": item.provider_id,
            "label": item.label,
            "capabilities": sorted(value.value for value in item.capabilities),
            "default_endpoint": item.default_endpoint,
            "default_models": {key.value: value for key, value in item.default_models.items()},
            "requires_api_key": item.requires_api_key,
        } for item in providers],
        "models": [{
            "provider": item.provider_id,
            "id": item.model_id,
            "label": item.label,
            "capabilities": sorted(value.value for value in item.capabilities),
        } for item in models],
        "roles": roles,
        "credentials": credentials,
        "endpoints": endpoints,
        "multimodal_mode": mode,
    }


def model_settings_env_values(payload: Mapping[str, object]) -> dict[str, str]:
    roles = payload.get("roles") if isinstance(payload.get("roles"), Mapping) else {}
    credentials = payload.get("credentials") if isinstance(payload.get("credentials"), Mapping) else {}
    endpoints = payload.get("endpoints") if isinstance(payload.get("endpoints"), Mapping) else {}
    mode = str(payload.get("multimodal_mode", "split") or "split").strip().lower()
    if mode not in {"split", "native"}:
        raise ValueError("multimodal_mode 必须是 split 或 native")
    if mode == "native":
        native_values = []
        for role in ModelRole:
            role_id = role.value
            role_data = roles.get(role_id) if isinstance(roles.get(role_id), Mapping) else {}
            endpoint_data = endpoints.get(role_id) if isinstance(endpoints.get(role_id), Mapping) else {}
            provider_id = str(role_data.get("provider", "") or "").strip().lower()
            provider = get_provider(provider_id)
            native_values.append((
                provider.provider_id,
                str(role_data.get("model", "") or "").strip(),
                str(role_data.get("credential_id", "") or provider.provider_id).strip(),
                (str(endpoint_data.get("base_url", "") or "").strip() or provider.default_endpoint).rstrip("/"),
            ))
        if native_values[0] != native_values[1]:
            raise ValueError("native 模式要求 reasoning 与 vision 显式使用同一 Provider、模型、凭据和 Base URL；配置未保存")
        draft_keys = []
        for role in ModelRole:
            credential_data = credentials.get(role.value) if isinstance(credentials.get(role.value), Mapping) else {}
            draft_keys.append(str(credential_data.get("api_key", "") or "").strip())
        if all(draft_keys) and draft_keys[0] != draft_keys[1]:
            raise ValueError("native 模式的 reasoning 与 vision API Key 不一致；配置未保存")
    values: dict[str, str] = {}

    for role in ModelRole:
        role_id = role.value
        prefix = ROLE_ENV_PREFIX[role]
        role_data = roles.get(role_id) if isinstance(roles.get(role_id), Mapping) else {}
        provider_id = str(role_data.get("provider", "") or "").strip().lower()
        provider = get_provider(provider_id)
        validate_provider_runtime_contract(provider)
        if not provider.supports(role):
            raise ValueError(f"{provider.label} 不支持{role_id}角色")
        model = str(role_data.get("model", "") or "").strip()
        if not model:
            raise ValueError(f"{role_id} 模型名不能为空")
        model_spec = get_model(provider.provider_id, model)
        required = required_capability_for_role(role)
        if model_spec:
            validate_model_runtime_contract(model_spec, provider)
        if model_spec and required not in model_spec.capabilities:
            raise ValueError(f"{model} 不支持{role_id}角色")
        values[f"{prefix}_PROVIDER"] = provider.provider_id
        values[f"{prefix}_MODEL"] = model

        credential_data = credentials.get(role_id) if isinstance(credentials.get(role_id), Mapping) else {}
        credential_id = str(role_data.get("credential_id", "") or provider.provider_id).strip()
        values[f"{prefix}_CREDENTIAL_ID"] = credential_id

        endpoint_data = endpoints.get(role_id) if isinstance(endpoints.get(role_id), Mapping) else {}
        endpoint = str(endpoint_data.get("base_url", "") or "").strip()
        endpoint = endpoint or provider.default_endpoint
        if not endpoint:
            raise ValueError(f"{role_id} 自定义 Provider 必须配置 Base URL")
        if not endpoint.startswith(("http://", "https://")):
            raise ValueError(f"{role_id} Base URL 必须以 http:// 或 https:// 开头")
        values[f"{prefix}_BASE_URL"] = endpoint.rstrip("/")

        api_key = str(credential_data.get("api_key", "") or "").strip()
        if api_key:
            values[credential_env_name(credential_id)] = api_key

    values["LLM_MULTIMODAL_MODE"] = mode
    return values
