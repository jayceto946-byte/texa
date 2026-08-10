import config


def test_chat_model_instances_are_reused_by_configuration(monkeypatch):
    created = []

    class FakeChatModel:
        model_fields = {}

        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeChatModel)
    config.clear_llm_cache()
    try:
        first = config._get_chat_model(
            "demo-model",
            0.2,
            "demo-key",
            "https://example.invalid/v1",
            {"thinking": {"type": "enabled"}, "reasoning_effort": "high"},
        )
        second = config._get_chat_model(
            "demo-model",
            0.2,
            "demo-key",
            "https://example.invalid/v1",
            {"reasoning_effort": "high", "thinking": {"type": "enabled"}},
        )
        different_temperature = config._get_chat_model(
            "demo-model",
            0.3,
            "demo-key",
            "https://example.invalid/v1",
        )
    finally:
        config.clear_llm_cache()

    assert first is second
    assert different_temperature is not first
    assert len(created) == 2


def test_clear_llm_cache_forces_recreation(monkeypatch):
    created = []

    class FakeChatModel:
        model_fields = {}

        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeChatModel)
    config.clear_llm_cache()
    first = config._get_chat_model("demo", 1, "key", "https://example.invalid/v1")
    config.clear_llm_cache()
    second = config._get_chat_model("demo", 1, "key", "https://example.invalid/v1")
    config.clear_llm_cache()

    assert first is not second
    assert len(created) == 2


def test_chat_model_timeout_and_retry_policy_are_part_of_cached_configuration(monkeypatch):
    created = []

    class FakeChatModel:
        model_fields = {}

        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeChatModel)
    config.clear_llm_cache()
    try:
        bounded = config._get_chat_model(
            "demo",
            0.3,
            "key",
            "https://example.invalid/v1",
            request_timeout=35,
            max_retries=0,
        )
        default = config._get_chat_model("demo", 0.3, "key", "https://example.invalid/v1")
    finally:
        config.clear_llm_cache()

    assert bounded is not default
    assert created[0]["timeout"] == 35
    assert created[0]["max_retries"] == 0
