import httpx
import openai
import pytest

from app.services.llm_concurrency_service import LlmConcurrencyService
from app.utils.llm_client import LLMClient


class DummyOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _CompletionsProxy:
    def __init__(self, create_fn):
        self.create = create_fn


class _ChatProxy:
    def __init__(self, create_fn):
        self.completions = _CompletionsProxy(create_fn)


class StubbedResponseLLMClient(LLMClient):
    def __init__(self, response: str, finish_reason: str = "stop"):
        self.response = response
        self.finish_reason = finish_reason

    def chat(self, messages, temperature=0.7, max_tokens=4096, response_format=None):
        return self.response

    def _chat_json_call(self, messages, temperature, max_tokens):
        return self.response, self.finish_reason


def _fake_chat_response(content: str):
    return type(
        "FakeResponse",
        (),
        {
            "choices": [
                type(
                    "Choice",
                    (),
                    {
                        "message": type("Message", (), {"content": content})(),
                    },
                )()
            ]
        },
    )()


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


def test_llm_client_chat_releases_concurrency_when_request_fails():
    concurrency_service = LlmConcurrencyService()
    concurrency_service.set_limit("channel_demo", 1)
    client = LLMClient(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="gpt-test",
        channel_key="channel_demo",
        concurrency_service=concurrency_service,
    )
    client.client = type("FakeOpenAI", (), {
        "chat": _ChatProxy(lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))),
    })()

    with pytest.raises(RuntimeError, match="boom"):
        client.chat(messages=[{"role": "user", "content": "hello"}])

    assert concurrency_service.snapshot("channel_demo") == {
        "limit": 1,
        "inflight": 0,
        "waiting": 0,
    }


def test_llm_client_chat_stream_releases_concurrency_on_generator_close():
    concurrency_service = LlmConcurrencyService()
    concurrency_service.set_limit("channel_stream", 1)
    client = LLMClient(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="gpt-test",
        channel_key="channel_stream",
        concurrency_service=concurrency_service,
    )

    def fake_stream():
        yield type("Chunk", (), {
            "choices": [type("Choice", (), {
                "delta": type("Delta", (), {"content": "第一段"})(),
            })()],
        })()
        yield type("Chunk", (), {
            "choices": [type("Choice", (), {
                "delta": type("Delta", (), {"content": "第二段"})(),
            })()],
        })()

    client.client = type("FakeOpenAI", (), {
        "chat": _ChatProxy(lambda **kwargs: fake_stream()),
    })()

    stream = client.chat_stream(messages=[{"role": "user", "content": "hello"}])
    assert next(stream) == "第一段"
    assert concurrency_service.snapshot("channel_stream") == {
        "limit": 1,
        "inflight": 1,
        "waiting": 0,
    }

    stream.close()

    assert concurrency_service.snapshot("channel_stream") == {
        "limit": 1,
        "inflight": 0,
        "waiting": 0,
    }


def test_llm_client_chat_stream_releases_concurrency_after_normal_exhaustion():
    concurrency_service = LlmConcurrencyService()
    concurrency_service.set_limit("channel_stream_finish", 1)
    client = LLMClient(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="gpt-test",
        channel_key="channel_stream_finish",
        concurrency_service=concurrency_service,
    )

    def fake_stream():
        yield type("Chunk", (), {
            "choices": [type("Choice", (), {
                "delta": type("Delta", (), {"content": "完成"})(),
            })()],
        })()

    client.client = type("FakeOpenAI", (), {
        "chat": _ChatProxy(lambda **kwargs: fake_stream()),
    })()

    chunks = list(client.chat_stream(messages=[{"role": "user", "content": "hello"}]))

    assert chunks == ["完成"]
    assert concurrency_service.snapshot("channel_stream_finish") == {
        "limit": 1,
        "inflight": 0,
        "waiting": 0,
    }



def test_llm_client_chat_retries_on_transient_gateway_error(monkeypatch):
    monkeypatch.setattr("app.utils.llm_client.time.sleep", lambda _: None)
    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    response = httpx.Response(
        504,
        request=request,
        text="<html><title>504 Gateway Time-out</title></html>",
    )
    attempts = {"count": 0}

    def create_fn(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise openai.InternalServerError(
                "gateway timeout",
                response=response,
                body=response.text,
            )
        return _fake_chat_response("恢复成功")

    client = LLMClient(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="gpt-test",
    )
    client.client = type("FakeOpenAI", (), {"chat": _ChatProxy(create_fn)})()

    assert client.chat(messages=[{"role": "user", "content": "hello"}]) == "恢复成功"
    assert attempts["count"] == 2


def test_llm_client_chat_does_not_retry_on_bad_request(monkeypatch):
    monkeypatch.setattr("app.utils.llm_client.time.sleep", lambda _: None)
    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    response = httpx.Response(400, request=request, text='{"error":"bad request"}')
    attempts = {"count": 0}

    def create_fn(**kwargs):
        attempts["count"] += 1
        raise openai.APIStatusError(
            "bad request",
            response=response,
            body={"error": "bad request"},
        )

    client = LLMClient(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="gpt-test",
    )
    client.client = type("FakeOpenAI", (), {"chat": _ChatProxy(create_fn)})()

    with pytest.raises(openai.APIStatusError):
        client.chat(messages=[{"role": "user", "content": "hello"}])

    assert attempts["count"] == 1


# ── chat_json_value 降温重试测试 ──


class _MultiAttemptLLMClient(LLMClient):
    """模拟多次调用返回不同结果的 LLM 客户端。"""

    def __init__(self, responses):
        self._responses = list(responses)
        self._attempt = 0
        self._recorded_temps = []
        self.model = "test-model"

    def _chat_json_call(self, messages, temperature, max_tokens):
        self._recorded_temps.append(temperature)
        idx = min(self._attempt, len(self._responses) - 1)
        self._attempt += 1
        content, finish_reason = self._responses[idx]
        return content, finish_reason


def test_chat_json_value_retries_with_temperature_reduction():
    """首次 JSON 无效，第二次成功，温度应降低。"""
    client = _MultiAttemptLLMClient([
        ("这不是JSON", "stop"),
        ('{"ok": true}', "stop"),
    ])
    result = client.chat_json_value(messages=[{"role": "user", "content": "test"}], temperature=0.3)
    assert result == {"ok": True}
    assert client._attempt == 2
    assert client._recorded_temps[0] == 0.3
    assert client._recorded_temps[1] == pytest.approx(0.15)


def test_chat_json_value_passes_truncated_flag():
    """finish_reason='length' 时应传递 truncated=True 到 parse_json_response。"""
    # 截断的 JSON（缺少闭合括号）只在 truncated=True 时才能修复
    client = _MultiAttemptLLMClient([
        ('{"name": "宁毅"', "length"),
    ])
    result = client.chat_json_value(messages=[{"role": "user", "content": "test"}])
    assert result["name"] == "宁毅"


def test_chat_json_value_raises_after_three_failures():
    """3 次全部失败后应抛出 ValueError。"""
    client = _MultiAttemptLLMClient([
        ("bad1", "stop"),
        ("bad2", "stop"),
        ("bad3", "stop"),
    ])
    with pytest.raises(ValueError, match="LLM返回的JSON格式无效"):
        client.chat_json_value(messages=[{"role": "user", "content": "test"}])
    assert client._attempt == 3


def test_chat_json_value_temperature_floor():
    """温度不应降到 0.05 以下。"""
    client = _MultiAttemptLLMClient([
        ("bad", "stop"),
        ("bad", "stop"),
        ('{"ok": true}', "stop"),
    ])
    result = client.chat_json_value(messages=[{"role": "user", "content": "test"}], temperature=0.1)
    assert result == {"ok": True}
    # temp 0.1, 0.1-0.15=max(-.05, .05)=0.05, 0.1-0.30=max(-.2, .05)=0.05
    assert client._recorded_temps[2] == pytest.approx(0.05)
