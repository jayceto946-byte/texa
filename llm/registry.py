"""Provider registry. Adding a provider does not change application code."""

from __future__ import annotations

from llm.types import Capability, ModelRole, ModelSpec, ProviderSpec


_PROVIDERS: dict[str, ProviderSpec] = {}
_MODELS: dict[tuple[str, str], ModelSpec] = {}


def register_provider(spec: ProviderSpec) -> ProviderSpec:
    key = spec.provider_id.strip().lower()
    if not key:
        raise ValueError("provider_id must not be empty")
    _PROVIDERS[key] = spec
    return spec


def get_provider(provider_id: str) -> ProviderSpec:
    key = (provider_id or "").strip().lower()
    try:
        return _PROVIDERS[key]
    except KeyError as exc:
        choices = ", ".join(sorted(_PROVIDERS))
        raise ValueError(f"Unknown LLM provider {provider_id!r}; available: {choices}") from exc


def list_providers(role: ModelRole | None = None) -> list[ProviderSpec]:
    values = list(_PROVIDERS.values())
    if role is not None:
        values = [item for item in values if item.supports(role)]
    return values


def register_model(spec: ModelSpec) -> ModelSpec:
    get_provider(spec.provider_id)
    _MODELS[(spec.provider_id.lower(), spec.model_id)] = spec
    return spec


def get_model(provider_id: str, model_id: str) -> ModelSpec | None:
    return _MODELS.get((provider_id.strip().lower(), model_id))


def list_models(provider_id: str | None = None) -> list[ModelSpec]:
    values = list(_MODELS.values())
    if provider_id:
        values = [item for item in values if item.provider_id == provider_id]
    return values


def _register_builtins() -> None:
    common = frozenset({
        Capability.TEXT, Capability.STREAMING,
        Capability.SYSTEM_PROMPT, Capability.TOKEN_USAGE,
    })
    register_provider(ProviderSpec(
        provider_id="deepseek", label="DeepSeek", transport="openai_compatible",
        capabilities=common | {Capability.REASONING},
        default_endpoint="https://api.deepseek.com/v1",
        default_models={ModelRole.REASONING: "deepseek-v4-pro"},
        legacy_api_key_env=("DEEPSEEK_API_KEY", "OPENAI_API_KEY"),
        legacy_endpoint_env=("DEEPSEEK_API_BASE",),
        legacy_model_env={ModelRole.REASONING: ("DEEPSEEK_MODEL_NAME", "LLM_MODEL_NAME")},
    ))
    register_provider(ProviderSpec(
        provider_id="moonshot", label="Moonshot / Kimi", transport="openai_compatible",
        capabilities=common | {Capability.VISION, Capability.REASONING},
        default_endpoint="https://api.moonshot.cn/v1",
        default_models={ModelRole.REASONING: "kimi-k2.6", ModelRole.VISION: "kimi-k2.5"},
        legacy_api_key_env=("MOONSHOT_API_KEY", "OPENAI_API_KEY"),
        legacy_endpoint_env=("MOONSHOT_API_BASE",),
        legacy_model_env={
            ModelRole.REASONING: ("LLM_MODEL_NAME",),
            ModelRole.VISION: ("KIMI_VISION_MODEL",),
        },
    ))
    register_provider(ProviderSpec(
        provider_id="qwen", label="Qwen / 通义千问", transport="openai_compatible",
        capabilities=common | {Capability.VISION, Capability.REASONING},
        default_endpoint="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_models={ModelRole.REASONING: "qwen-plus", ModelRole.VISION: "qwen-vl-plus"},
        legacy_api_key_env=("DASHSCOPE_API_KEY",),
        legacy_endpoint_env=("DASHSCOPE_API_BASE",),
    ))
    register_provider(ProviderSpec(
        provider_id="gemini", label="Google Gemini", transport="openai_compatible",
        capabilities=common | {Capability.VISION, Capability.REASONING},
        default_endpoint="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_models={ModelRole.REASONING: "gemini-2.5-pro", ModelRole.VISION: "gemini-2.5-pro"},
        legacy_api_key_env=("GEMINI_API_KEY",),
        legacy_endpoint_env=("GEMINI_API_BASE",),
    ))
    register_provider(ProviderSpec(
        provider_id="openai", label="OpenAI", transport="openai_compatible",
        capabilities=common | {Capability.VISION, Capability.REASONING},
        default_endpoint="https://api.openai.com/v1",
        default_models={ModelRole.REASONING: "gpt-4o-mini", ModelRole.VISION: "gpt-4o-mini"},
        legacy_api_key_env=("OPENAI_API_KEY",),
        legacy_endpoint_env=("OPENAI_API_BASE",),
        legacy_model_env={ModelRole.REASONING: ("LLM_MODEL_NAME",)},
    ))
    register_provider(ProviderSpec(
        provider_id="ollama", label="Ollama（本地）", transport="ollama",
        capabilities=common | {Capability.VISION, Capability.LOCAL},
        default_endpoint="http://localhost:11434",
        default_models={ModelRole.REASONING: "qwen2.5:7b", ModelRole.VISION: "qwen2.5vl:7b"},
        requires_api_key=False,
        legacy_endpoint_env=("OLLAMA_BASE_URL",),
        legacy_model_env={ModelRole.REASONING: ("LLM_MODEL_NAME",)},
    ))
    register_provider(ProviderSpec(
        provider_id="openai_compatible", label="自定义 OpenAI-compatible", transport="openai_compatible",
        capabilities=common | {Capability.VISION, Capability.REASONING, Capability.LOCAL},
        default_endpoint="",
        default_models={ModelRole.REASONING: "", ModelRole.VISION: ""},
        requires_api_key=False,
    ))

    for spec in (
        ModelSpec("deepseek", "deepseek-v4-pro", "DeepSeek V4 Pro", common | {Capability.REASONING}, {
            "extra_body": {"reasoning_effort": "high", "thinking": {"type": "enabled"}},
        }),
        ModelSpec("deepseek", "deepseek-v4-flash", "DeepSeek V4 Flash", common | {Capability.REASONING}),
        ModelSpec("moonshot", "kimi-k2.6", "Kimi K2.6", common | {Capability.REASONING, Capability.VISION}),
        ModelSpec("moonshot", "kimi-k2.5", "Kimi K2.5", common | {Capability.REASONING, Capability.VISION}, {
            "extra_body": {"thinking": {"type": "disabled"}},
        }),
        ModelSpec("qwen", "qwen3.8-max", "Qwen 3.8 Max", common | {Capability.REASONING}),
        ModelSpec("qwen", "qwen3.7-plus", "Qwen 3.7 Plus", common | {Capability.REASONING}),
        ModelSpec("qwen", "qwen3.5-plus", "Qwen 3.5 Plus", common | {Capability.REASONING}),
        ModelSpec("qwen", "qwen3.5-flash", "Qwen 3.5 Flash", common | {Capability.REASONING}),
        ModelSpec("qwen", "qwen-plus", "Qwen Plus（兼容别名）", common | {Capability.REASONING}),
        ModelSpec("qwen", "qwen3-vl-plus", "Qwen 3 VL Plus", common | {Capability.REASONING, Capability.VISION}),
        ModelSpec("qwen", "qwen-vl-plus", "Qwen VL Plus（兼容别名）", common | {Capability.REASONING, Capability.VISION}),
        ModelSpec("gemini", "gemini-3.7-flash", "Gemini 3.7 Flash", common | {Capability.REASONING, Capability.VISION}),
        ModelSpec("gemini", "gemini-3.6-flash", "Gemini 3.6 Flash", common | {Capability.REASONING, Capability.VISION}),
        ModelSpec("gemini", "gemini-2.5-pro", "Gemini 2.5 Pro（兼容）", common | {Capability.REASONING, Capability.VISION}),
        ModelSpec("openai", "gpt-5.6-sol", "GPT-5.6 Sol", common | {Capability.REASONING, Capability.VISION}),
        ModelSpec("openai", "gpt-5.6-terra", "GPT-5.6 Terra", common | {Capability.REASONING, Capability.VISION}),
        ModelSpec("openai", "gpt-5.6-luna", "GPT-5.6 Luna", common | {Capability.REASONING, Capability.VISION}),
        ModelSpec("openai", "gpt-5.4-mini", "GPT-5.4 mini", common | {Capability.REASONING, Capability.VISION}),
        ModelSpec("openai", "gpt-4o-mini", "GPT-4o mini（兼容）", common | {Capability.REASONING, Capability.VISION}),
        ModelSpec("ollama", "qwen2.5:7b", "Qwen 2.5 7B（本地）", common | {Capability.LOCAL}),
        ModelSpec("ollama", "qwen2.5vl:7b", "Qwen 2.5 VL 7B（本地）", common | {Capability.REASONING, Capability.VISION, Capability.LOCAL}),
    ):
        register_model(spec)


_register_builtins()
