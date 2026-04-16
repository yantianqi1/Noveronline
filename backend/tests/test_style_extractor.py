"""Phase 4: style extractor unit tests (LLM mocked)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.services.assets.style_extractor.aggregator import (
    aggregate_chunk_results,
    render_style_content,
)
from app.services.assets.style_extractor.chunker import chunk_novel
from app.services.assets.style_extractor.runner import StyleExtractor


@pytest.fixture()
def isolated(monkeypatch, tmp_path):
    upload_root = tmp_path / "uploads"
    (upload_root / "system").mkdir(parents=True)
    from app.config import Config
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))


def test_chunker_basic():
    text = "段落一。" * 20 + "\n\n" + "段落二。" * 50 + "\n\n" + "段落三。" * 30
    chunks = chunk_novel(text, target_chars=120, max_chunks=10)
    assert 1 <= len(chunks) <= 10
    assert "".join(chunks).count("段落一") > 0


def test_aggregator_picks_top_modes():
    chunk_results = [
        {
            "narrative_pov": "第一人称限知",
            "tense": "过去时",
            "sentence_features": ["短句", "排比"],
            "rhetoric": ["白描"],
            "tone": "冷峻克制",
            "example_snippets": ["他没说话。"],
        },
        {
            "narrative_pov": "第一人称限知",
            "tense": "过去时",
            "sentence_features": ["短句"],
            "rhetoric": ["白描", "象征"],
            "tone": "冷峻克制",
            "example_snippets": ["雨没有停。"],
        },
        {
            "narrative_pov": "第三人称紧贴",
            "tense": "现在时",
            "sentence_features": ["长句"],
            "rhetoric": ["比喻"],
            "tone": "抒情",
            "example_snippets": ["他没说话。"],  # dup
        },
    ]
    agg = aggregate_chunk_results(chunk_results)
    assert "第一人称限知" in agg["narrative_pov"]
    assert agg["tense"].startswith("过去时")
    assert "短句" in agg["sentence_features"]
    assert "白描" in agg["rhetoric"]
    assert agg["chunk_count"] == 3
    # snippets deduped
    assert agg["example_snippets"].count("他没说话。") == 1

    rendered = render_style_content(agg)
    assert "写作风格指南" in rendered
    assert "第一人称" in rendered
    assert "他没说话。" in rendered


def test_extract_sync_with_mock_llm(isolated):
    fake_payload = {
        "narrative_pov": "第一人称限知",
        "tense": "过去时",
        "sentence_features": ["短句", "白描"],
        "rhetoric": ["象征"],
        "pacing": "舒缓",
        "vocabulary": "冷峻克制",
        "dialogue_style": "极简",
        "tone": "冷峻",
        "distinctive_devices": ["大量留白"],
        "example_snippets": ["雨没有停。"],
    }
    fake_client = MagicMock()
    fake_client.chat_json.return_value = fake_payload
    fake_router = MagicMock()
    fake_router.build_client.return_value = fake_client

    extractor = StyleExtractor(llm_router=fake_router, max_workers=2)
    text = ("段落示例。" * 80 + "\n\n") * 6  # ensure multiple chunks
    result = asyncio.run(extractor.extract_sync(
        text,
        title="测试风格",
        category="测试",
        tags=["t1"],
        target_chunk_chars=200,
        max_chunks=8,
    ))
    assert result["asset"]["title"] == "测试风格"
    assert result["asset"]["asset_type"] == "writing_style"
    assert result["successful_chunks"] >= 1
    assert "写作风格指南" in result["asset"]["content"]
    assert "雨没有停。" in result["asset"]["content"]
    assert fake_router.build_client.called
    assert fake_client.chat_json.call_count >= 1
