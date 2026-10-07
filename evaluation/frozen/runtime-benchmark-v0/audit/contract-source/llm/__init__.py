"""Texa model-provider abstraction.

Application code selects a model role. Provider SDK details, credentials and
endpoints are resolved behind this package.
"""

from llm.configuration import model_settings_payload, resolve_model_role
from llm.registry import get_provider, list_models, list_providers, register_model, register_provider
from llm.types import Capability, ModelRole, ModelSpec, ProviderSpec, ResolvedModelRole

__all__ = [
    "Capability",
    "ModelRole",
    "ModelSpec",
    "ProviderSpec",
    "ResolvedModelRole",
    "get_provider",
    "list_providers",
    "list_models",
    "register_model",
    "model_settings_payload",
    "register_provider",
    "resolve_model_role",
]
