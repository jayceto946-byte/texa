"""Provider-independent model configuration types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class Capability(str, Enum):
    TEXT = "text"
    VISION = "vision"
    REASONING = "reasoning"
    STREAMING = "streaming"
    SYSTEM_PROMPT = "system_prompt"
    TOKEN_USAGE = "token_usage"
    LOCAL = "local"


class ModelRole(str, Enum):
    REASONING = "reasoning"
    VISION = "vision"


def required_capability_for_role(role: ModelRole) -> Capability:
    """Return the application capability required by a configured model role."""
    return Capability.REASONING if role is ModelRole.REASONING else Capability.VISION


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    label: str
    transport: str
    capabilities: frozenset[Capability]
    default_endpoint: str
    default_models: Mapping[ModelRole, str]
    requires_api_key: bool = True
    legacy_api_key_env: tuple[str, ...] = ()
    legacy_endpoint_env: tuple[str, ...] = ()
    legacy_model_env: Mapping[ModelRole, tuple[str, ...]] = field(default_factory=dict)
    role_options: Mapping[ModelRole, Mapping[str, object]] = field(default_factory=dict)

    def supports(self, role: ModelRole) -> bool:
        return required_capability_for_role(role) in self.capabilities


@dataclass(frozen=True)
class ModelSpec:
    provider_id: str
    model_id: str
    label: str
    capabilities: frozenset[Capability]
    options: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedModelRole:
    role: ModelRole
    provider: ProviderSpec
    model: str
    api_key: str
    endpoint: str
    options: Mapping[str, object] = field(default_factory=dict)

    @property
    def credential_configured(self) -> bool:
        return not self.provider.requires_api_key or bool(self.api_key)
