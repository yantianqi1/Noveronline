import httpx
import openai
import pytest

from app.services.local_block_fact_extractor import LocalBlockFactExtractor
from app.utils.llm_client import LLMClient


HTML_504_PAGE = """<!DOCTYPE html>
<html>
  <head><title>opcl.cloud | 504: Gateway time-out</title></head>
  <body>
    <div>api.opcl.cloud</div>
  </body>
</html>"""


def test_local_block_fact_extractor_summarizes_html_gateway_errors(monkeypatch):
    monkeypatch.setattr("app.services.seed_llm_retry.time.sleep", lambda _: None)

    class AlwaysFailingClient:
        def chat_json_value(self, messages, temperature=0.1, max_tokens=4096):
            raise RuntimeError(HTML_504_PAGE)

    extractor = LocalBlockFactExtractor(llm_client=AlwaysFailingClient())

    payload = extractor.extract_blocks(
        blocks=[
            {
                "block_id": "block_0001",
                "owned_chapter_ids": ["chapter_0001"],
                "context_chapter_ids": [],
                "owned_chapter_range": {"start_order": 1, "end_order": 1},
                "order": 1,
            }
        ],
        chapters=[
            {
                "chapter_id": "chapter_0001",
                "title": "第1章",
                "content": "沈夜继续追查镜湖旧案。",
            }
        ],
        use_llm=True,
        skeleton={"global_characters": [], "global_organizations": [], "chapter_sketches": []},
        anchors={"anchors": []},
    )

    packet = payload["packets"][0]
    assert packet["generation_mode"] == "rule_fallback"
    assert "HTTP 504" in packet["fallback_reason"]
    assert "api.opcl.cloud" in packet["fallback_reason"]
    assert "<!DOCTYPE html>" not in packet["fallback_reason"]


def test_llm_client_summarizes_final_transient_html_gateway_error(monkeypatch):
    monkeypatch.setattr("app.utils.llm_client.time.sleep", lambda _: None)

    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    response = httpx.Response(504, request=request, text=HTML_504_PAGE)

    def create_fn(**kwargs):
        raise openai.InternalServerError(
            "gateway timeout",
            response=response,
            body=response.text,
        )

    client = LLMClient(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="gpt-test",
    )
    completions = type("CompletionsProxy", (), {})()
    completions.create = create_fn
    chat = type("ChatProxy", (), {})()
    chat.completions = completions
    client.client = type("FakeOpenAI", (), {"chat": chat})()

    with pytest.raises(RuntimeError) as exc_info:
        client.chat(messages=[{"role": "user", "content": "hello"}])

    message = str(exc_info.value)
    assert "HTTP 504" in message
    assert "Gateway time-out" in message
    assert "api.opcl.cloud" in message
    assert "<html>" not in message.lower()
