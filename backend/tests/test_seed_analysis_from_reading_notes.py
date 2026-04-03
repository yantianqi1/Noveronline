"""Tests for SeedAnalysisAggregator.aggregate_from_reading_notes()."""

import pytest

from app.services.reading_notes_manager import ReadingNotesManager
from app.services.seed_analysis_aggregator import SeedAnalysisAggregator


def _populated_manager() -> ReadingNotesManager:
    """Create a ReadingNotesManager with test data."""
    manager = ReadingNotesManager()

    # Add 沈夜 across 4 segments with personality_traits, speech_style
    manager.merge_character_updates(
        [
            {
                "name": "沈夜",
                "identity": "修真宗门弟子",
                "status": "alive",
                "personality_traits": ["冷静", "果断"],
                "speech_style": "简洁凌厉",
                "aliases": ["夜少"],
                "goals": ["晋阶元婴"],
                "key_actions": ["斩杀妖兽"],
                "quote_examples": ["吾道不孤。"],
            }
        ],
        segment_id="seg_1",
    )
    manager.merge_character_updates(
        [{"name": "沈夜", "personality_traits": ["深沉"], "key_actions": ["破阵"]}],
        segment_id="seg_2",
    )
    manager.merge_character_updates(
        [{"name": "沈夜", "key_actions": ["收徒"]}],
        segment_id="seg_3",
    )
    manager.merge_character_updates(
        [{"name": "沈夜", "status": "injured", "key_actions": ["疗伤"]}],
        segment_id="seg_4",
    )

    # Add 秦昭 in 1 segment (dead)
    manager.merge_character_updates(
        [
            {
                "name": "秦昭",
                "identity": "反派宗主",
                "status": "dead",
                "personality_traits": ["阴险"],
                "speech_style": "阴冷",
            }
        ],
        segment_id="seg_2",
    )

    # Add 玄霄宗 organization
    manager.merge_organization(
        "玄霄宗",
        {
            "type": "修真门派",
            "status": "active",
            "purpose": "修炼与传承",
        },
        segment_id="seg_1",
    )
    manager.merge_organization("玄霄宗", {}, segment_id="seg_3")

    # Add 2 relationship changes
    manager.merge_relationship_changes(
        [
            {
                "source": "沈夜",
                "target": "秦昭",
                "relation": "对立",
                "previous_state": "",
                "trigger": "夺宝之争",
                "evidence": "沈夜与秦昭因夺宝而结仇",
            }
        ],
        segment_id="seg_2",
    )
    manager.merge_relationship_changes(
        [
            {
                "source": "沈夜",
                "target": "秦昭",
                "relation": "仇敌",
                "previous_state": "对立",
                "trigger": "生死决战",
                "evidence": "两人展开生死之战",
            }
        ],
        segment_id="seg_4",
    )

    # Add 2 segment summaries
    manager.add_segment_summary("seg_1", "沈夜初入玄霄宗，展现天赋。")
    manager.add_segment_summary("seg_2", "秦昭率人袭击，沈夜奋力抵抗。")

    return manager


def test_aggregate_from_reading_notes():
    manager = _populated_manager()
    agg = SeedAnalysisAggregator()
    result = agg.aggregate_from_reading_notes(
        manager,
        analysis_goal="测试角色分析",
        project_name="test_project",
    )

    chars = result["characters"]
    assert len(chars) >= 2

    # 沈夜 should be first (4 segments → protagonist)
    shen_ye = chars[0]
    assert shen_ye["name"] == "沈夜"
    assert shen_ye["mention_count"] == 4
    assert shen_ye["importance_tier"] == "protagonist"
    assert len(shen_ye["personality_traits"]) >= 2
    assert shen_ye["speech_style"] == "简洁凌厉"

    orgs = result["organizations"]
    assert len(orgs) >= 1
    assert orgs[0]["name"] == "玄霄宗"
    assert orgs[0]["mention_count"] == 2

    relations = result["relations"]
    assert len(relations) >= 1
    rel = relations[0]
    assert rel["source"] == "沈夜"
    assert rel["target"] == "秦昭"
    assert rel["weight"] == 2
    assert "evolution_chain" in rel
    assert len(rel["evolution_chain"]) == 2

    beats = result["chapter_beats"]
    assert len(beats) >= 1
    assert beats[0]["beat_id"] == "beat_1"
    assert "summary" in beats[0]


def test_backward_compatible_fields():
    manager = _populated_manager()
    agg = SeedAnalysisAggregator()
    result = agg.aggregate_from_reading_notes(
        manager,
        analysis_goal="兼容性测试",
        project_name="compat_project",
    )

    # Top-level required fields
    for field in ("characters", "organizations", "relations", "chapter_beats",
                  "analysis_summary", "source_stats"):
        assert field in result, f"Missing top-level field: {field}"

    assert result["project_name"] == "compat_project"
    assert result["analysis_goal"] == "兼容性测试"

    # source_stats keys
    for key in ("block_count", "character_count", "organization_count", "relation_count"):
        assert key in result["source_stats"], f"Missing source_stats key: {key}"

    # Each character has required fields
    for char in result["characters"]:
        for field in ("name", "mention_count", "importance_tier"):
            assert field in char, f"Character missing field: {field}"


def test_beats_from_summaries_max_20():
    """_beats_from_summaries should cap at 20 beats."""
    manager = ReadingNotesManager()
    for i in range(25):
        manager.add_segment_summary(f"seg_{i}", f"summary {i}")

    agg = SeedAnalysisAggregator()
    result = agg.aggregate_from_reading_notes(manager, "test", "proj")
    assert len(result["chapter_beats"]) == 20


def test_old_aggregate_still_works():
    """The original aggregate() method must remain unaffected."""
    agg = SeedAnalysisAggregator()
    story_memory: dict = {
        "entity_registry": {
            "Alice": {
                "name": "Alice",
                "entity_type": "character",
                "mention_blocks": ["b1", "b2", "b3", "b4", "b5"],
                "summary": "hero",
                "evidence": ["e1"],
            }
        },
        "relationship_ledger": [],
        "block_count": 5,
        "event_timeline": [],
        "open_threads": [],
    }
    block_analyses = [{"plot_summary": "开场"}]
    result = agg.aggregate(story_memory, block_analyses, "goal", "proj")
    assert result["characters"][0]["name"] == "Alice"
    assert result["characters"][0]["importance_tier"] == "protagonist"
    assert result["chapter_beats"][0]["summary"] == "开场"
