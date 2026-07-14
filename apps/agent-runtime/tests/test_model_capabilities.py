from mirofish_agents.llm.model_capabilities import (
    effective_supports_json,
    infer_model_capabilities,
    normalize_model_id,
)


def test_normalize_strips_proxy_tags() -> None:
    assert normalize_model_id("[free]deepseek-v4-flash") == "deepseek-v4-flash"
    assert normalize_model_id("  DeepSeek-Chat ") == "deepseek-chat"


def test_chat_models_default_to_json_capable() -> None:
    for model_id in (
        "deepseek-v4-flash",
        "deepseek-chat",
        "[free]deepseek-v4-pro",
        "gpt-5.5",
        "claude-sonnet-4-6",
        "gemini-2.5-pro",
        "qwen-plus",
        "custom-proxy-chat",
    ):
        caps = infer_model_capabilities(model_id)
        assert caps.supports_json is True, model_id
        assert caps.supports_tools is True, model_id


def test_non_chat_and_reasoners_stay_false() -> None:
    for model_id in (
        "deepseek-reasoner",
        "deepseek-r1",
        "qwq-32b",
        "text-embedding-3-large",
        "gpt-image-2",
    ):
        caps = infer_model_capabilities(model_id)
        assert caps.supports_json is False, model_id


def test_effective_or_with_stored_flag() -> None:
    assert effective_supports_json(model_id="deepseek-v4-flash", stored=False) is True
    assert effective_supports_json(model_id="deepseek-reasoner", stored=False) is False
    assert effective_supports_json(model_id="deepseek-reasoner", stored=True) is True
