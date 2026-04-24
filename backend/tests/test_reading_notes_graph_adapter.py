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
    assert chapter_continuity["chapter_count"] == 0  # no chapter_segments provided


def test_local_block_facts_with_smart_segments():
    smart_segments = {
        "segments": [
            {"segment_id": "seg_001", "chapters": ["第一章"]},
            {"segment_id": "seg_002", "chapters": ["第二章"]},
            {"segment_id": "seg_003", "chapters": ["第三章"]},
        ]
    }
    _, local_block_facts, _, _ = adapt_reading_notes_for_graph(
        _sample_reading_notes(), _sample_seed_analysis(), smart_segments=smart_segments
    )
    assert local_block_facts["block_count"] == 3
    assert len(local_block_facts["packets"]) == 3
    # seg_001 should contain 林动 (segments_seen includes seg_001)
    seg1_packet = next(p for p in local_block_facts["packets"] if p["block_id"] == "seg_001")
    entity_names = [e["name"] for e in seg1_packet["local_entities"]]
    assert "林动" in entity_names
    # seg_002 should contain both 林动 and 小貂
    seg2_packet = next(p for p in local_block_facts["packets"] if p["block_id"] == "seg_002")
    entity_names_2 = [e["name"] for e in seg2_packet["local_entities"]]
    assert "林动" in entity_names_2
    assert "小貂" in entity_names_2


def test_handles_notes_wrapped_format():
    """reading_notes.json from ReadingNotesManager.save() wraps data under 'notes' key."""
    inner = _sample_reading_notes()
    wrapped = {
        "arc_interval": 5,
        "volume_arc_threshold": 10,
        "all_segment_summaries": [],
        "_arc_cursor": 0,
        "notes": inner,
    }
    story_memory, local_block_facts, _, _ = adapt_reading_notes_for_graph(
        wrapped, _sample_seed_analysis()
    )
    registry = story_memory["entity_registry"]
    assert "林动" in registry
    assert registry["林动"]["entity_type"] == "character"
    assert len(story_memory["relationship_ledger"]) >= 1
    assert len(story_memory["world_rules"]) >= 1
    assert local_block_facts["block_count"] >= 1


def test_location_state_changes_produce_location_entities():
    """When sequential_reader never populates core_facts.key_locations but
    does emit notes.location_state_changes, the adapter must still surface
    locations as graph entities."""
    notes = _sample_reading_notes()
    notes["location_state_changes"] = [
        {
            "location": "青阳镇",
            "change": "战后化为废墟，林家残部暂时安置于此。",
            "segment_id": "seg_002",
        },
    ]
    story_memory, _, _, _ = adapt_reading_notes_for_graph(
        notes, _sample_seed_analysis()
    )
    registry = story_memory["entity_registry"]
    assert "青阳镇" in registry
    location_entry = registry["青阳镇"]
    assert location_entry["entity_type"] == "location"
    assert "废墟" in location_entry["summary"]
    assert "seg_002" in location_entry["mention_blocks"]


def test_location_merges_multiple_state_changes():
    """Repeated location updates across segments merge into a single
    entity, with evidence and mention_blocks accumulating."""
    notes = _sample_reading_notes()
    notes["location_state_changes"] = [
        {"location": "青阳镇", "change": "繁华市集", "segment_id": "seg_001"},
        {"location": "青阳镇", "change": "遭遇夜袭", "segment_id": "seg_002"},
        {"location": "青阳镇", "change": "残余势力重建", "segment_id": "seg_003"},
    ]
    story_memory, _, _, _ = adapt_reading_notes_for_graph(
        notes, _sample_seed_analysis()
    )
    registry = story_memory["entity_registry"]
    entry = registry["青阳镇"]
    assert entry["entity_type"] == "location"
    # first change wins as summary
    assert entry["summary"] == "繁华市集"
    # mention_blocks aggregates unique segment_ids
    assert set(entry["mention_blocks"]) == {"seg_001", "seg_002", "seg_003"}
    # evidence contains every non-empty change text
    assert "繁华市集" in entry["evidence"]
    assert "遭遇夜袭" in entry["evidence"]
    assert "残余势力重建" in entry["evidence"]


def test_core_facts_key_locations_still_honored_when_present():
    """If the pipeline ever does populate key_locations, its richer entries
    should take precedence over location_state_changes augmentation."""
    notes = _sample_reading_notes()
    notes["core_facts"]["key_locations"] = {
        "青阳镇": {
            "description": "元素边陲小镇，林家世代居住之地。",
            "segments_seen": ["seg_001"],
        }
    }
    notes["location_state_changes"] = [
        {"location": "青阳镇", "change": "遭遇夜袭", "segment_id": "seg_002"},
    ]
    story_memory, _, _, _ = adapt_reading_notes_for_graph(
        notes, _sample_seed_analysis()
    )
    entry = story_memory["entity_registry"]["青阳镇"]
    # initial description from key_locations is preserved as summary
    assert entry["summary"].startswith("元素边陲")
    # state changes still contribute segment_ids
    assert "seg_002" in entry["mention_blocks"]
