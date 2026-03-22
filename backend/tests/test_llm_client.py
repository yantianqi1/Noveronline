import pytest

from app.utils.llm_client import LLMClient


class DummyOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class StubbedResponseLLMClient(LLMClient):
    def __init__(self, response: str):
        self.response = response

    def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
        return self.response


def test_llm_client_sets_explicit_request_timeout(monkeypatch):
    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return DummyOpenAI(**kwargs)

    monkeypatch.setattr("app.utils.llm_client.OpenAI", fake_openai)

    LLMClient(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="gpt-test",
    )

    assert captured["api_key"] == "test-key"
    assert captured["base_url"] == "https://example.com/v1"
    assert captured["timeout"] == 120.0


def test_chat_json_value_accepts_top_level_list_payload():
    client = StubbedResponseLLMClient('[{"local_events": []}]')

    payload = client.chat_json_value(messages=[])

    assert isinstance(payload, list)
    assert payload[0]["local_events"] == []


def test_chat_json_unwraps_single_object_list():
    client = StubbedResponseLLMClient('[{"plot_summary": "镜湖线正式启动"}]')

    payload = client.chat_json(messages=[])

    assert payload == {"plot_summary": "镜湖线正式启动"}


def test_chat_json_rejects_multi_item_list():
    client = StubbedResponseLLMClient('[{"name": "A"}, {"name": "B"}]')

    with pytest.raises(ValueError, match="LLM响应必须返回单个 JSON 对象.*2 个元素的 list"):
        client.chat_json(messages=[])


def test_chat_json_rejects_empty_list():
    client = StubbedResponseLLMClient("[]")

    with pytest.raises(ValueError, match="LLM响应必须返回 JSON 对象，实际收到空 list"):
        client.chat_json(messages=[])


def test_chat_json_rejects_scalar_value():
    client = StubbedResponseLLMClient('"just-text"')

    with pytest.raises(ValueError, match="LLM响应必须返回 JSON 对象，实际收到 str"):
        client.chat_json(messages=[])
