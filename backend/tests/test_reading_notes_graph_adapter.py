from app.services.reading_notes_graph_adapter import adapt_reading_notes_for_graph


def _sample_reading_notes():
    return {
        "core_facts": {
            "characters": {
                "林动": {
                    "aliases": ["小动"],
                    "status": "active",
                    "identity": "林家少年",
                    "first_seen": "seg_001",
                    "personality_traits": ["坚韧", "聪慧"],
                    "speech_style": "直率",
                    "goals": ["变强"],
                    "key_actions": ["获得石符", "击败对手"],
                    "knowledge_gained": [],
                    "quote_examples": ["我一定会变强"],
                    "segments_seen": ["seg_001", "seg_002", "seg_003"],
                    "status_history": [],
                },
                "小貂": {
                    "aliases": [],
                    "status": "active",
                    "identity": "神秘妖兽",
                    "first_seen": "seg_002",
                    "personality_traits": ["傲娇"],
                    "speech_style": "",
                    "goals": [],
                    "key_actions": ["协助战斗"],
                    "knowledge_gained": [],
                    "quote_examples": [],
                    "segments_seen": ["seg_002"],
                    "status_history": [],
                },
            },
            "organizations": {
                "林家": {
                    "type": "家族",
                    "status": "active",
                    "members_mentioned": ["林动", "林震天"],
                    "purpose": "守护家族荣耀",
                    "first_seen": "seg_001",
                    "segments_seen": ["seg_001", "seg_002"],
                },
            },
            "world_rules": [
                {"fact": "元力修炼分为九重", "evidence": "修炼体系以元力为基础"},
            ],
            "key_locations": {},
        },
        "relationship_graph": [
            {
                "source": "林动",
                "target": "小貂",
                "relation": "ally",
                "previous_state": "",
                "trigger": "结伴同行",
                "evidence": "林动收服小貂后结为伙伴",
                "segment_id": "seg_002",
            },
            {
                "source": "林动",
                "target": "小貂",
                "relation": "ally",
                "previous_state": "ally",
                "trigger": "并肩作战",
                "evidence": "两人联手击败敌人",
                "segment_id": "seg_003",
            },
        ],
        "plot_state": {
            "arc_summaries": [
                {"summary": "林动获得神秘石符开始修炼之路", "segment_range": "seg_001-seg_003"},
            ],
            "volume_summaries": [],
            "recent_segment_summaries": [],
            "open_threads": [
                {"thread": "石符来历之谜", "status": "open"},
            ],
            "narrative_phase": "起步",
        },
    }


def _sample_seed_analysis():
    return {
        "characters": [
            {"name": "林动", "importance_tier": "protagonist", "profile_summary": "主角少年"},
            {"name": "小貂", "importance_tier": "major", "profile_summary": "妖兽伙伴"},
        ],
        "organizations": [
            {"name": "林家", "importance_tier": "major", "summary": "主角家族"},
        ],
        "relations": [
            {"source": "林动", "target": "小貂", "relation_type": "ally", "evidence": ["结伴同行"]},
        ],
    }


def test_entity_registry_characters():
    story_memory, _, _, _ = adapt_reading_notes_for_graph(
        _sample_reading_notes(), _sample_seed_analysis()
    )
    registry = story_memory["entity_registry"]
    assert "林动" in registry
    assert registry["林动"]["entity_type"] == "character"
    assert registry["林动"]["importance_tier"] == "protagonist"
    assert "小动" in registry["林动"]["aliases"]
    assert len(registry["林动"]["mention_blocks"]) == 3


def test_entity_registry_organizations():
    story_memory, _, _, _ = adapt_reading_notes_for_graph(
        _sample_reading_notes(), _sample_seed_analysis()
    )
    registry = story_memory["entity_registry"]
    assert "林家" in registry
    assert registry["林家"]["entity_type"] == "organization"


def test_relationship_ledger():
    story_memory, _, _, _ = adapt_reading_notes_for_graph(
        _sample_reading_notes(), _sample_seed_analysis()
    )
    ledger = story_memory["relationship_ledger"]
    assert len(ledger) >= 1
    pair = next(r for r in ledger if r["source"] == "林动" and r["target"] == "小貂")
    assert len(pair["changes"]) == 2
    assert pair["changes"][0]["change"] == "ally"


def test_world_rules():
    story_memory, _, _, _ = adapt_reading_notes_for_graph(
        _sample_reading_notes(), _sample_seed_analysis()
    )
    assert "元力修炼分为九重" in story_memory["world_rules"]


def test_event_timeline_from_arcs():
    story_memory, _, _, _ = adapt_reading_notes_for_graph(
        _sample_reading_notes(), _sample_seed_analysis()
    )
    assert len(story_memory["event_timeline"]) >= 1
    assert "林动" in story_memory["event_timeline"][0].get("summary", "")


def test_local_block_facts_shape():
    _, local_block_facts, _, _ = adapt_reading_notes_for_graph(
        _sample_reading_notes(), _sample_seed_analysis()
    )
    assert "block_count" in local_block_facts
    assert "packets" in local_block_facts
    assert local_block_facts["block_count"] >= 1


def test_block_analyses_and_continuity_shape():
    _, _, block_analyses, chapter_continuity = adapt_reading_notes_for_graph(
        _sample_reading_notes(), _sample_seed_analysis()
    )
    assert "block_count" in block_analyses
    assert "chapter_count" in chapter_continuity
