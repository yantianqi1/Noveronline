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

    # Verify total_segments is reported correctly on segment-scoped events.
    # Arc/volume events use different fields, so scope the assertion.
    for e in start_events + end_events:
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
# Periodic reading_notes checkpointing
# ---------------------------------------------------------------------------

def test_checkpoint_callback_fires_every_n_segments():
    """6 段 + 每 2 段一次 checkpoint → 3 次 checkpoint，每次 manager
    里的 summary 数逐步增长（1→3→5... 具体取决于段落摘要数量）。"""
    segments = [_make_segment(i) for i in range(1, 7)]
    reader = SequentialReader(llm_router=FakeRouterForReading(), arc_interval=100)

    checkpoints = []

    def capture(manager):
        checkpoints.append(len(manager.all_segment_summaries))

    reader.read(segments, use_llm=True, checkpoint_callback=capture, checkpoint_every=2)

    # 6 段 / cadence 2 = 3 次 checkpoint
    assert len(checkpoints) == 3, f"Expected 3 checkpoints, got {checkpoints}"
    # 每次 checkpoint 时 manager 里的 summary 数是严格递增的
    assert checkpoints == sorted(checkpoints)
    assert checkpoints[0] >= 1
    assert checkpoints[-1] >= checkpoints[0]


def test_checkpoint_callback_failure_does_not_abort_read():
    """checkpoint 回调抛异常（比如外置盘瞬时失败）时，整个顺序阅读
    不应该崩溃——下一段照常继续，下次 checkpoint 也照常尝试。"""
    segments = [_make_segment(i) for i in range(1, 5)]
    reader = SequentialReader(llm_router=FakeRouterForReading(), arc_interval=100)

    calls = {"n": 0}

    def flaky(manager):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("transient disk error")

    notes_mgr = reader.read(
        segments, use_llm=True, checkpoint_callback=flaky, checkpoint_every=2,
    )

    # 4 段 / cadence 2 = 2 次 checkpoint，第一次抛、第二次成功
    assert calls["n"] == 2
    # 全部 4 段依然读完了
    assert len(notes_mgr.all_segment_summaries) == 4


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


# ---------------------------------------------------------------------------
# Phase C: known_entities hint injected into segment prompt
# ---------------------------------------------------------------------------

def test_build_segment_prompt_injects_known_entities_block():
    from app.services.sequential_reader_prompts import build_segment_reading_prompt

    messages = build_segment_reading_prompt(
        context="某些前情",
        segment_text="林策走入院中。",
        known_entities={"林策": ["小林"], "玄霄宗": []},
    )
    user_content = messages[1]["content"]
    assert "【已知实体表】" in user_content
    assert "林策（别名：小林）" in user_content
    # No-alias entry should be present without parenthetical
    assert "- 玄霄宗" in user_content
    # The instruction in the system prompt should also mention canonical name
    system_content = messages[0]["content"]
    assert "canonical 名" in system_content


def test_build_segment_prompt_omits_block_when_no_known_entities():
    from app.services.sequential_reader_prompts import build_segment_reading_prompt

    messages = build_segment_reading_prompt(
        context="",
        segment_text="林策走入院中。",
        known_entities=None,
    )
    user_content = messages[1]["content"]
    assert "【已知实体表】" not in user_content


def test_build_segment_prompt_back_compat_without_known_entities_arg():
    """Ensure existing callers that don't pass known_entities still work."""
    from app.services.sequential_reader_prompts import build_segment_reading_prompt

    messages = build_segment_reading_prompt("ctx", "text")
    assert len(messages) == 2
    assert "【前情上下文】" in messages[1]["content"]
    assert "【本段正文】" in messages[1]["content"]
    assert "【已知实体表】" not in messages[1]["content"]
