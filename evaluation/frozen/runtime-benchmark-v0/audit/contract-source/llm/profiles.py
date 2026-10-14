"""Local non-secret model profiles; credentials remain in .env."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Mapping

from config import DATA_DIR
from llm.configuration import credential_env_name, model_settings_env_values, model_settings_payload, resolve_model_role
from llm.registry import get_provider


PROFILE_PATH = Path(os.getenv("LLM_PROFILE_PATH", str(Path(DATA_DIR) / "model_profiles.json")))


def _safe_profile_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-")[:48]
    return cleaned or f"profile-{uuid.uuid4().hex[:10]}"


def load_profiles() -> list[dict]:
    if not PROFILE_PATH.exists():
        return []
    try:
        payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _write_profiles(profiles: list[dict]) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = PROFILE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(PROFILE_PATH)


def _public_profile(profile: Mapping[str, object]) -> dict:
    return {
        "id": str(profile.get("id", "")),
        "name": str(profile.get("name", "")),
        "roles": profile.get("roles", {}),
        "endpoints": profile.get("endpoints", {}),
        "multimodal_mode": profile.get("multimodal_mode", "split"),
    }


def profiles_payload(env: Mapping[str, str] | None = None) -> dict:
    source = env if env is not None else os.environ
    settings = model_settings_payload(source)
    profiles = [_public_profile(item) for item in load_profiles()]
    if not profiles:
        profiles = [_public_profile({
            "id": "default",
            "name": "默认方案",
            "roles": settings["roles"],
            "endpoints": settings["endpoints"],
            "multimodal_mode": settings["multimodal_mode"],
        })]
    active_id = str(source.get("LLM_ACTIVE_PROFILE_ID", "") or profiles[0]["id"])
    active = next((item for item in profiles if item["id"] == active_id), None)
    if active:
        active_roles = active.get("roles") if isinstance(active.get("roles"), Mapping) else {}
        for role_id in ("reasoning", "vision"):
            active_role = active_roles.get(role_id) if isinstance(active_roles.get(role_id), Mapping) else {}
            display_name = str(active_role.get("display_name", "") or "").strip()
            if display_name and isinstance(settings.get("roles", {}).get(role_id), dict):
                settings["roles"][role_id]["display_name"] = display_name
    settings.update({
        "profiles": profiles,
        "active_profile_id": active_id,
        "editing_profile_id": active_id,
        "profile_name": active["name"] if active else "默认方案",
        "credential_status": _credential_status(profiles, settings, source),
    })
    return settings


def _credential_status(profiles: list[dict], settings: dict, env: Mapping[str, str]) -> dict[str, bool]:
    ids = {item["id"] for item in settings["providers"]}
    for profile in profiles:
        for role in (profile.get("roles") or {}).values():
            if isinstance(role, Mapping) and role.get("credential_id"):
                ids.add(str(role["credential_id"]))
    result = {}
    for item in ids:
        configured = bool(str(env.get(credential_env_name(item), "") or "").strip())
        for role_id, role in settings.get("roles", {}).items():
            if isinstance(role, Mapping) and role.get("provider") == item:
                configured = configured or bool(str(env.get(f"LLM_{str(role_id).upper()}_API_KEY", "") or "").strip())
        try:
            provider = get_provider(item)
            configured = configured or any(bool(str(env.get(key, "") or "").strip()) for key in provider.legacy_api_key_env)
        except ValueError:
            pass
        result[item] = configured
    return result


def save_profile(payload: Mapping[str, object]) -> tuple[dict, dict[str, str]]:
    profile_id = _safe_profile_id(str(payload.get("id", "") or ""))
    name = str(payload.get("name", "") or "").strip()[:40]
    if not name:
        raise ValueError("方案名称不能为空")

    settings_payload = {
        "roles": payload.get("roles", {}),
        "credentials": payload.get("credentials", {}),
        "endpoints": payload.get("endpoints", {}),
        "multimodal_mode": payload.get("multimodal_mode", "split"),
    }
    roles = settings_payload["roles"] if isinstance(settings_payload["roles"], Mapping) else {}
    normalized_roles = {}
    for role_id, role_value in roles.items():
        if not isinstance(role_value, Mapping):
            continue
        normalized_role = dict(role_value)
        display_name = str(normalized_role.get("display_name", "") or "").strip()[:80]
        if display_name:
            normalized_role["display_name"] = display_name
        else:
            normalized_role.pop("display_name", None)
        normalized_roles[str(role_id)] = normalized_role
    settings_payload["roles"] = normalized_roles
    env_values = model_settings_env_values(settings_payload)
    roles = settings_payload["roles"] if isinstance(settings_payload["roles"], Mapping) else {}
    credentials = settings_payload["credentials"] if isinstance(settings_payload["credentials"], Mapping) else {}
    for role_id in ("reasoning", "vision"):
        role = roles.get(role_id) if isinstance(roles.get(role_id), Mapping) else {}
        credential = credentials.get(role_id) if isinstance(credentials.get(role_id), Mapping) else {}
        if str(credential.get("api_key", "") or "").strip():
            continue
        current = resolve_model_role(role_id)
        if current.provider.provider_id != str(role.get("provider", "") or "") or not current.api_key:
            continue
        credential_id = str(role.get("credential_id", "") or current.provider.provider_id)
        env_values.setdefault(credential_env_name(credential_id), current.api_key)
    stored = _public_profile({"id": profile_id, "name": name, **settings_payload})
    profiles = load_profiles()
    profiles = [stored if item.get("id") == profile_id else item for item in profiles]
    if not any(item.get("id") == profile_id for item in profiles):
        profiles.append(stored)
    _write_profiles(profiles)
    return stored, env_values


def activate_profile(profile_id: str) -> dict[str, str]:
    profile = next((item for item in load_profiles() if item.get("id") == profile_id), None)
    if profile is None:
        raise ValueError("模型方案不存在")
    values = model_settings_env_values({**profile, "credentials": {}})
    values["LLM_ACTIVE_PROFILE_ID"] = profile_id
    return values


def delete_profile(profile_id: str) -> None:
    profiles = load_profiles()
    if not any(item.get("id") == profile_id for item in profiles):
        raise ValueError("模型方案不存在")
    _write_profiles([item for item in profiles if item.get("id") != profile_id])
