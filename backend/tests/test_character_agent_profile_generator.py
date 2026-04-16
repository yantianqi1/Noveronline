"""Tests for CharacterAgentProfileGenerator."""

import asyncio

import pytest
from app.services.reading_notes_manager import ReadingNotesManager
from app.services.character_agent_profile_generator import (
    CharacterAgentProfileGenerator,
    MODULE_KEY,
    DEFAULT_IMPORTANCE_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Fake LLM helpers
# ---------------------------------------------------------------------------

FAKE_PROFILE = {
    "basic_info": {
        "name": "沈夜",
        "aliases": ["黑衣人"],
        "identity": "主角，暗夜刺客",
        "status": "存活",
    },
    "personality": {
        "core_traits": ["冷静", "果决"],
        "values": "不惜一切完成任务",
        "fears": "失去同伴",
        "decision_pattern": "优先评估风险再行动",
    },
    "speech": {
        "style": "简短有力",
        "verbal_habits": ["少废话"],
        "tone_range": "冷淡至严肃",
        "example_quotes": ["'我不解释。'"],
    },
    "relationships": [
        {
            "target": "林若",
            "current_state": "合作",
            "evolution": "从对立到信任",
            "attitude": "警惕但依赖",
        }
    ],
    "capabilities": {
        "skills": ["近身格斗", "隐身潜行"],
        "limitations": ["不善言辞"],
        "resources": "暗夜组织支持",
    },
    "knowledge_boundary": {
        "knows": ["任务目标"],
        "does_not_know": ["幕后主使真实身份"],
        "believes_wrongly": ["林若是敌方卧底"],
    },
    "motivation": {
        "ultimate_goal": "终结暗夜组织",
        "current_objective": "找到内鬼",
        "internal_conflict": "忠诚与复仇之间的撕裂",
    },
}


class FakeProfileClient:
    def chat_json_value(self, messages, temperature=0.3, max_tokens=4096):
        return FAKE_PROFILE


class FakeProfileRouter:
    def build_client(self, module_key):
        assert module_key == MODULE_KEY, f"Expected {MODULE_KEY!r}, got {module_key!r}"
        return FakeProfileClient()


# ---------------------------------------------------------------------------
# Test fixture: ReadingNotesManager with two characters
# ---------------------------------------------------------------------------

def _make_manager() -> ReadingNotesManager:
    """Build a ReadingNotesManager with:
    - 沈夜  → appears in 3 segments (above threshold=2)
    - 路人甲 → appears in 1 segment  (below threshold=2)
    """
    mgr = ReadingNotesManager()

    # 沈夜 — 3 segment appearances
    for i in range(1, 4):
        mgr.merge_character_updates(
            [
                {
                    "name": "沈夜",
                    "aliases": ["黑衣人"],
                    "status": "存活",
                    "identity": "暗夜刺客",
                    "first_seen": "seg_001",
                    "personality_traits": ["冷静", "果决"],
                    "speech_style": "简短",
                    "goals": ["终结暗夜组织"],
                    "key_actions": [f"行动{i}"],
                    "knowledge_gained": ["任务目标"],
                    "quote_examples": ["'我不解释。'"],
                }
            ],
            segment_id=f"seg_{i:03d}",
        )

    # 路人甲 — 1 segment appearance
    mgr.merge_character_updates(
        [
            {
                "name": "路人甲",
                "aliases": [],
                "status": "存活",
                "identity": "路过的行人",
                "first_seen": "seg_001",
                "personality_traits": ["普通"],
                "speech_style": "日常",
                "goals": [],
                "key_actions": ["走过街道"],
                "knowledge_gained": [],
                "quote_examples": [],
            }
        ],
        segment_id="seg_001",
    )

    # Add arc summary for story context
    mgr.add_segment_summary("seg_001", "沈夜初次亮相，遭遇追杀。")
    mgr.add_segment_summary("seg_002", "沈夜与林若相遇，展开合作。")

    return mgr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_generate_profiles():
    """Character appearing in >=3 segments is profiled; character with 1 is not."""
    mgr = _make_manager()
    gen = CharacterAgentProfileGenerator(
        llm_router=FakeProfileRouter(),
        importance_threshold=DEFAULT_IMPORTANCE_THRESHOLD,
    )
    result = asyncio.run(gen.generate(mgr, use_llm=True))

    assert "profiles" in result
    assert "profile_count" in result

    profiles = result["profiles"]
    assert "沈夜" in profiles, "沈夜 should be profiled (3 segments ≥ threshold 2)"
    assert "路人甲" not in profiles, "路人甲 should NOT be profiled (1 segment < threshold 2)"
    assert result["profile_count"] == 1


def test_generate_profiles_offline():
    """With use_llm=False, profiles are built directly from reading notes."""
    mgr = _make_manager()
    gen = CharacterAgentProfileGenerator(
        llm_router=FakeProfileRouter(),
        importance_threshold=DEFAULT_IMPORTANCE_THRESHOLD,
    )
    result = asyncio.run(gen.generate(mgr, use_llm=False))

    profiles = result["profiles"]
    assert "沈夜" in profiles
    assert "路人甲" not in profiles

    profile = profiles["沈夜"]
    # Must have all required top-level keys
    for key in ("basic_info", "personality", "speech", "relationships", "capabilities",
                "knowledge_boundary", "motivation"):
        assert key in profile, f"Missing key {key!r} in offline profile"

    basic = profile["basic_info"]
    assert basic["name"] == "沈夜"
    assert basic["status"] == "存活"


def test_progress_callback():
    """Callback receives profiles_start and profile_done events."""
    mgr = _make_manager()
    gen = CharacterAgentProfileGenerator(
        llm_router=FakeProfileRouter(),
        importance_threshold=DEFAULT_IMPORTANCE_THRESHOLD,
    )

    events = []

    def callback(event_name: str, payload: dict):
        events.append((event_name, payload))

    asyncio.run(gen.generate(mgr, use_llm=True, progress_callback=callback))

    event_names = [e[0] for e in events]
    assert "profiles_start" in event_names, "profiles_start event must be emitted"
    assert "profile_done" in event_names, "profile_done event must be emitted"

    # profiles_start has total count
    start_event = next(e for e in events if e[0] == "profiles_start")
    assert start_event[1]["total"] == 1  # only 沈夜

    # profile_done events have name, completed, total
    done_events = [e for e in events if e[0] == "profile_done"]
    assert len(done_events) == 1
    done = done_events[0][1]
    assert done["name"] == "沈夜"
    assert done["completed"] == 1
    assert done["total"] == 1
