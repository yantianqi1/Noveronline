"""Tests for SequentialReader + sequential_reader_prompts."""
from __future__ import annotations

import pytest

from app.services.sequential_reader import SequentialReader, MODULE_KEY
from app.services.smart_novel_segmenter import SmartNovelSegmenter


# ---------------------------------------------------------------------------
# Fake LLM helpers
# ---------------------------------------------------------------------------

CANNED_SEGMENT_RESULT = {
    "segment_summary": "沈夜在第一段登场，展示了其冷静的性格。",
    "character_updates": [
        {
            "name": "沈夜",
            "aliases": [],
            "status": "alive",
            "identity": "主角",
            "personality_traits": ["冷静", "果断"],
            "speech_style": "简洁直接",
            "goals": ["查明真相"],
            "key_actions": ["独自调查"],
            "knowledge_gained": ["发现线索"],
            "quote_examples": ["「我不需要帮助。」"],
            "first_seen": "seg_001",
        }
    ],
    "relationship_changes": [],
    "plot_threads": [
        {"thread": "失踪案", "status": "open", "detail": "案件尚未解决"}
    ],
    "world_building": [
        {"fact": "这个城市有暗部组织", "evidence": "沈夜提到了影卫"}
    ],
    "consistency_notes": [],
    "narrative_phase": "铺垫",
}

CANNED_ARC_RESULT = {
    "arc_summary": "第一弧线：沈夜展开调查，逐渐揭开失踪案背后的秘密。"
}

CANNED_VOLUME_RESULT = {
    "volume_summary": "第一卷：沈夜从孤身调查者成长为势力核心，世界格局初现。"
}


class FakeSequentialReadingClient:
    """Returns canned JSON based on detected prompt type."""

    def chat_json_value(self, messages, temperature=0.3, max_tokens=8192):
        # Detect prompt type from system message content
        system_content = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
                break

        if "弧线摘要" in system_content and "卷摘要" not in system_content:
            return dict(CANNED_ARC_RESULT)
        if "卷摘要" in system_content:
            return dict(CANNED_VOLUME_RESULT)
        # Default: segment reading
        return dict(CANNED_SEGMENT_RESULT)


class FakeRouterForReading:
    def build_client(self, module_key):
        assert module_key == MODULE_KEY, (
            f"Expected module_key={MODULE_KEY!r}, got {module_key!r}"
        )
        return FakeSequentialReadingClient()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_segment(index: int, character: str = "沈夜") -> dict:
    """Build a minimal segment dict."""
    seg_id = f"seg_{index:03d}"
    return {
        "segment_id": seg_id,
        "chapters": [
            {
                "chapter_id": f"ch_{index:03d}",
                "order": index,
                "title": f"第{index}章",
                "content": f"{character}出现在这一章节中，发生了重要事件。",
                "word_count": 20,
            }
        ],
        "chapter_range": str(index),
        "estimated_tokens": 30,
    }


# ---------------------------------------------------------------------------
# Test 1: basic reading produces notes
# ---------------------------------------------------------------------------

def test_sequential_read_produces_reading_notes():
    """3 segments → 'shen ye' in characters, 3 summaries recorded."""
    segments = [_make_segment(i) for i in range(1, 4)]
    reader = SequentialReader(llm_router=FakeRouterForReading(), arc_interval=5)
    notes_mgr = reader.read(segments, use_llm=True)

    # Characters should contain 沈夜
    characters = notes_mgr.notes["core_facts"]["characters"]
    assert "沈夜" in characters, f"Expected '沈夜' in characters; got {list(characters.keys())}"

    # All 3 segment summaries should be recorded
    assert len(notes_mgr.all_segment_summaries) == 3, (
        f"Expected 3 summaries, got {len(notes_mgr.all_segment_summaries)}"
    )


# ---------------------------------------------------------------------------
# Test 2: progress callback receives correct events
# ---------------------------------------------------------------------------

def test_sequential_read_progress_callback():
    """2 segments → 2 'segment_start' + 2 'segment_end' events."""
    segments = [_make_segment(i) for i in range(1, 3)]
    reader = SequentialReader(llm_router=FakeRouterForReading(), arc_interval=5)

    events = []

    def callback(event_type, data):
        events.append({"type": event_type, **data})

    reader.read(segments, use_llm=True, progress_callback=callback)

    start_events = [e for e in events if e["type"] == "segment_start"]
    end_events = [e for e in events if e["type"] == "segment_end"]

    assert len(start_events) == 2, f"Expected 2 start events, got {len(start_events)}"
    assert len(end_events) == 2, f"Expected 2 end events, got {len(end_events)}"

    # Verify total_segments is reported correctly
    for e in events:
        assert e["total_segments"] == 2


# ---------------------------------------------------------------------------
# Test 3: offline mode
# ---------------------------------------------------------------------------

def test_sequential_read_offline_mode():
    """use_llm=False → at least 2 summaries produced without LLM calls."""
    segments = [_make_segment(i) for i in range(1, 4)]
    # No llm_router — would crash if LLM were called
    reader = SequentialReader(llm_router=None, arc_interval=5)
    notes_mgr = reader.read(segments, use_llm=False)

    assert len(notes_mgr.all_segment_summaries) >= 2, (
        f"Expected >=2 summaries in offline mode, got {len(notes_mgr.all_segment_summaries)}"
    )

    # Offline summaries should contain [离线] marker
    first_summary = notes_mgr.all_segment_summaries[0]["summary"]
    assert "[离线]" in first_summary, (
        f"Expected '[离线]' in offline summary, got: {first_summary!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: arc summary triggered at arc_interval
# ---------------------------------------------------------------------------

def test_arc_summary_triggered():
    """arc_interval=2, 4 segments → 2 arc summaries generated."""
    segments = [_make_segment(i) for i in range(1, 5)]
    reader = SequentialReader(llm_router=FakeRouterForReading(), arc_interval=2)
    notes_mgr = reader.read(segments, use_llm=True)

    arc_summaries = notes_mgr.notes["plot_state"]["arc_summaries"]
    assert len(arc_summaries) == 2, (
        f"Expected 2 arc summaries, got {len(arc_summaries)}: {arc_summaries}"
    )

    # Each arc summary should contain the canned text
    for arc in arc_summaries:
        assert arc["summary"] == CANNED_ARC_RESULT["arc_summary"]


# ---------------------------------------------------------------------------
# Test 5: end-to-end with SmartNovelSegmenter
# ---------------------------------------------------------------------------

def test_end_to_end_with_segmenter():
    """SmartNovelSegmenter → SequentialReader → '沈夜' in notes."""
    novel_text = """第一章 初遇
沈夜走进了废弃的仓库，四周一片寂静。他嗅到了危险的气息，停下了脚步。
经过片刻的观察，他发现了地上的一行血迹。

第二章 线索
沈夜沿着血迹追踪，来到了一扇铁门前。他推开铁门，看见了一个意想不到的人。
那个人正是他三年前以为已经死去的搭档。

第三章 真相
「你没死？」沈夜的声音难得地颤抖了一下。
搭档苦笑着摇了摇头：「我一直在等你来找我。」
"""

    segmenter = SmartNovelSegmenter(target_token_limit=50000)
    result = segmenter.segment_raw_text(novel_text)
    segments = result["segments"]

    assert len(segments) >= 1, "Segmenter produced no segments"

    reader = SequentialReader(llm_router=FakeRouterForReading(), arc_interval=5)
    notes_mgr = reader.read(segments, use_llm=True)

    characters = notes_mgr.notes["core_facts"]["characters"]
    assert "沈夜" in characters, (
        f"Expected '沈夜' in characters after end-to-end read; got {list(characters.keys())}"
    )
