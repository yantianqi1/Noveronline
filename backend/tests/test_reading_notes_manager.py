"""Tests for ReadingNotesManager — three-tier reading notes structure."""
import json
import pytest
from app.services.reading_notes_manager import ReadingNotesManager


def test_fresh_notes_have_correct_structure():
    mgr = ReadingNotesManager()
    notes = mgr.notes
    # core_facts
    assert "core_facts" in notes
    cf = notes["core_facts"]
    assert isinstance(cf["characters"], dict)
    assert isinstance(cf["organizations"], dict)
    assert isinstance(cf["world_rules"], list)
    assert isinstance(cf["key_locations"], dict)
    # relationship_graph
    assert isinstance(notes["relationship_graph"], list)
    # plot_state
    ps = notes["plot_state"]
    assert isinstance(ps["arc_summaries"], list)
    assert isinstance(ps["volume_summaries"], list)
    assert isinstance(ps["recent_segment_summaries"], list)
    assert isinstance(ps["open_threads"], list)
    assert ps["narrative_phase"] == ""
    # instance attributes
    assert mgr.all_segment_summaries == []
    assert mgr._arc_cursor == 0


def test_merge_character_update_new():
    mgr = ReadingNotesManager()
    update = {
        "name": "Alice",
        "aliases": ["Ali"],
        "status": "alive",
        "identity": "protagonist",
        "first_seen": "seg_001",
        "personality_traits": ["brave"],
        "speech_style": "formal",
        "goals": ["save the world"],
        "key_actions": ["entered the forest"],
        "knowledge_gained": ["learned the map"],
        "quote_examples": ["'I will go.'"],
    }
    mgr.merge_character_updates([update], segment_id="seg_001")
    chars = mgr.notes["core_facts"]["characters"]
    assert "Alice" in chars
    c = chars["Alice"]
    assert c["aliases"] == ["Ali"]
    assert c["status"] == "alive"
    assert c["identity"] == "protagonist"
    assert c["first_seen"] == "seg_001"
    assert "brave" in c["personality_traits"]
    assert c["speech_style"] == "formal"
    assert "save the world" in c["goals"]
    assert "entered the forest" in c["key_actions"]
    assert "learned the map" in c["knowledge_gained"]
    assert "'I will go.'" in c["quote_examples"]
    assert "seg_001" in c["segments_seen"]
    assert isinstance(c["status_history"], list)


def test_merge_character_update_accumulates():
    mgr = ReadingNotesManager()
    update1 = {
        "name": "Bob",
        "aliases": ["Bobby"],
        "status": "alive",
        "personality_traits": ["cautious"],
        "key_actions": ["opened the door"],
        "quote_examples": ["'Hello.'"],
    }
    update2 = {
        "name": "Bob",
        "aliases": ["B"],
        "status": "alive",
        "personality_traits": ["brave"],
        "key_actions": ["fought the dragon"],
        "quote_examples": ["'Charge!'"],
    }
    mgr.merge_character_updates([update1], segment_id="seg_001")
    mgr.merge_character_updates([update2], segment_id="seg_002")
    c = mgr.notes["core_facts"]["characters"]["Bob"]
    # aliases accumulate
    assert "Bobby" in c["aliases"]
    assert "B" in c["aliases"]
    # traits accumulate
    assert "cautious" in c["personality_traits"]
    assert "brave" in c["personality_traits"]
    # actions accumulate
    assert "opened the door" in c["key_actions"]
    assert "fought the dragon" in c["key_actions"]
    # quotes accumulate
    assert "'Hello.'" in c["quote_examples"]
    assert "'Charge!'" in c["quote_examples"]
    # segments_seen contains both
    assert "seg_001" in c["segments_seen"]
    assert "seg_002" in c["segments_seen"]


def test_merge_relationship_changes():
    mgr = ReadingNotesManager()
    changes = [
        {
            "source": "Alice",
            "target": "Bob",
            "relation": "allies",
            "previous_state": "strangers",
            "trigger": "shared danger",
            "evidence": "They fought side by side.",
        }
    ]
    mgr.merge_relationship_changes(changes, segment_id="seg_003")
    graph = mgr.notes["relationship_graph"]
    assert len(graph) == 1
    entry = graph[0]
    assert entry["source"] == "Alice"
    assert entry["target"] == "Bob"
    assert entry["relation"] == "allies"
    assert entry["segment_id"] == "seg_003"


def test_merge_plot_threads():
    mgr = ReadingNotesManager()
    threads_open = [
        {"thread": "find the artifact", "status": "open", "detail": "Alice is searching"},
        {"thread": "rescue the king", "status": "open", "detail": "Bob volunteered"},
    ]
    mgr.merge_plot_threads(threads_open)
    open_threads = mgr.notes["plot_state"]["open_threads"]
    assert any(t["thread"] == "find the artifact" for t in open_threads)
    assert any(t["thread"] == "rescue the king" for t in open_threads)

    # resolve one
    threads_resolved = [
        {"thread": "rescue the king", "status": "resolved", "detail": "King saved"},
    ]
    mgr.merge_plot_threads(threads_resolved)
    open_threads = mgr.notes["plot_state"]["open_threads"]
    assert not any(t["thread"] == "rescue the king" for t in open_threads)
    assert any(t["thread"] == "find the artifact" for t in open_threads)


def test_add_segment_summary():
    mgr = ReadingNotesManager()
    for i in range(1, 8):
        mgr.add_segment_summary(f"seg_{i:03d}", f"Events {i}.")
    # all seven in all_segment_summaries
    assert len(mgr.all_segment_summaries) == 7
    # rolling window = SEED_RECENT_SUMMARIES_WINDOW (default 5)
    recent = mgr.notes["plot_state"]["recent_segment_summaries"]
    assert len(recent) == 5
    segment_ids = [s["segment_id"] for s in recent]
    # last 5 are kept; first 2 are dropped
    assert segment_ids == [f"seg_{i:03d}" for i in range(3, 8)]


def test_arc_summary_trigger():
    mgr = ReadingNotesManager(arc_interval=3)
    for i in range(1, 7):
        mgr.add_segment_summary(f"seg_{i:03d}", f"Summary {i}.")
    assert mgr.needs_arc_summary()
    pending = mgr.pending_arc_segments()
    assert len(pending) >= 3


def test_add_arc_summary():
    mgr = ReadingNotesManager(arc_interval=3)
    for i in range(1, 4):
        mgr.add_segment_summary(f"seg_{i:03d}", f"Summary {i}.")
    pending = mgr.pending_arc_segments()
    arc_id = "arc_001"
    mgr.add_arc_summary(arc_id, "First arc summary.", pending)
    arcs = mgr.notes["plot_state"]["arc_summaries"]
    assert len(arcs) == 1
    assert arcs[0]["arc_id"] == arc_id
    assert arcs[0]["summary"] == "First arc summary."
    assert arcs[0]["covered_segments"] == pending
    # cursor advances
    assert mgr._arc_cursor == len(pending)
    # no longer needs arc summary
    assert not mgr.needs_arc_summary()


def test_context_assembly_short_novel():
    mgr = ReadingNotesManager()
    mgr.merge_character_updates(
        [{"name": "Elena", "status": "alive", "personality_traits": ["kind"]}],
        segment_id="seg_001",
    )
    mgr.add_segment_summary("seg_001", "Elena arrives at the village.")
    context = mgr.assemble_context()
    assert "Elena" in context
    assert "Elena arrives at the village." in context


def test_save_and_load(tmp_path):
    mgr = ReadingNotesManager()
    mgr.merge_character_updates(
        [{"name": "Zara", "status": "alive", "personality_traits": ["fierce"]}],
        segment_id="seg_001",
    )
    mgr.add_segment_summary("seg_001", "Zara storms the gate.")
    save_path = tmp_path / "reading_notes.json"
    mgr.save(str(save_path))
    loaded = ReadingNotesManager.load(str(save_path))
    assert "Zara" in loaded.notes["core_facts"]["characters"]
    assert len(loaded.all_segment_summaries) == 1
    assert loaded._arc_cursor == mgr._arc_cursor


def test_merge_world_building():
    mgr = ReadingNotesManager()
    facts1 = [
        {"fact": "Magic requires blood.", "evidence": "Mage spilled blood."},
        {"fact": "Dragons are extinct.", "evidence": "Old texts say so."},
    ]
    mgr.merge_world_building(facts1)
    assert len(mgr.notes["core_facts"]["world_rules"]) == 2

    # duplicate fact — should not be added again
    facts2 = [
        {"fact": "Magic requires blood.", "evidence": "Confirmed again."},
        {"fact": "Stars are alive.", "evidence": "They sing."},
    ]
    mgr.merge_world_building(facts2)
    rules = mgr.notes["core_facts"]["world_rules"]
    magic_count = sum(1 for r in rules if r["fact"] == "Magic requires blood.")
    assert magic_count == 1
    assert len(rules) == 3  # Dragons + Magic (deduped) + Stars


def test_merge_organizations():
    mgr = ReadingNotesManager()
    data1 = {
        "type": "guild",
        "status": "active",
        "members_mentioned": ["Alice", "Bob"],
        "purpose": "protect the realm",
        "first_seen": "seg_002",
    }
    mgr.merge_organization("Knights of Order", data1, segment_id="seg_002")
    orgs = mgr.notes["core_facts"]["organizations"]
    assert "Knights of Order" in orgs
    org = orgs["Knights of Order"]
    assert org["type"] == "guild"
    assert "Alice" in org["members_mentioned"]
    assert "seg_002" in org["segments_seen"]

    # update with new member
    data2 = {"members_mentioned": ["Carol"], "status": "active"}
    mgr.merge_organization("Knights of Order", data2, segment_id="seg_005")
    org = orgs["Knights of Order"]
    assert "Carol" in org["members_mentioned"]
    assert "seg_005" in org["segments_seen"]
    # original members preserved
    assert "Alice" in org["members_mentioned"]


def test_merge_character_update_status_history():
    mgr = ReadingNotesManager()
    update1 = {"name": "Marcus", "status": "alive"}
    mgr.merge_character_updates([update1], segment_id="seg_001")

    update2 = {"name": "Marcus", "status": "wounded"}
    mgr.merge_character_updates([update2], segment_id="seg_004")

    update3 = {"name": "Marcus", "status": "dead"}
    mgr.merge_character_updates([update3], segment_id="seg_007")

    c = mgr.notes["core_facts"]["characters"]["Marcus"]
    assert c["status"] == "dead"
    history = c["status_history"]
    # should have at least 2 transitions recorded
    assert len(history) >= 2
    # transitions should be in order
    statuses = [h["status"] for h in history]
    assert "wounded" in statuses
    assert "dead" in statuses
    # segment_ids recorded
    segments = [h["segment_id"] for h in history]
    assert "seg_004" in segments
    assert "seg_007" in segments


# ---------------------------------------------------------------------------
# Canonical entity table (for prompt hints) — added in Phase C
# ---------------------------------------------------------------------------

def test_canonical_entity_table_returns_top_n_by_mentions():
    mgr = ReadingNotesManager()
    # Two characters, one with more mentions
    mgr.merge_character_updates(
        [{"name": "Alice", "aliases": ["Al"], "status": "alive"}], segment_id="seg_001"
    )
    mgr.merge_character_updates(
        [{"name": "Alice", "aliases": []}], segment_id="seg_002"
    )
    mgr.merge_character_updates(
        [{"name": "Alice", "aliases": []}], segment_id="seg_003"
    )
    mgr.merge_character_updates(
        [{"name": "Bob", "aliases": ["Bobby"]}], segment_id="seg_002"
    )
    mgr.merge_organization("Knights", {"type": "guild"}, segment_id="seg_001")
    mgr.merge_organization("Knights", {}, segment_id="seg_002")

    table = mgr.canonical_entity_table()
    # All three should be present (no top_n cap hit)
    assert "Alice" in table
    assert "Bob" in table
    assert "Knights" in table
    # Aliases preserved
    assert table["Alice"] == ["Al"]
    assert table["Bob"] == ["Bobby"]
    # Organizations have no aliases
    assert table["Knights"] == []


def test_canonical_entity_table_excludes_zero_mention_entries():
    mgr = ReadingNotesManager()
    # Insert a character with no segments_seen (artificial edge case)
    mgr.notes["core_facts"]["characters"]["Ghost"] = mgr._empty_character()
    table = mgr.canonical_entity_table()
    assert "Ghost" not in table


def test_canonical_entity_table_respects_top_n_cap():
    mgr = ReadingNotesManager()
    for i in range(40):
        mgr.merge_character_updates(
            [{"name": f"Char{i:02d}"}], segment_id=f"seg_{i:03d}"
        )
    table = mgr.canonical_entity_table(top_n=10)
    assert len(table) == 10


# ---------------------------------------------------------------------------
# Phase D: structured volume summary fields (back-compat + new fields)
# ---------------------------------------------------------------------------

def test_add_volume_summary_back_compat_no_new_fields():
    """Old call sites that don't pass theme/main_arcs/etc should still work."""
    mgr = ReadingNotesManager()
    mgr.add_volume_summary("vol_001", "summary text", ["arc_001", "arc_002"])
    vols = mgr.notes["plot_state"]["volume_summaries"]
    assert len(vols) == 1
    vol = vols[0]
    assert vol["volume_id"] == "vol_001"
    assert vol["summary"] == "summary text"
    assert vol["covered_arcs"] == ["arc_001", "arc_002"]
    # New optional fields should not be present when not passed
    assert "theme" not in vol
    assert "main_arcs" not in vol


def test_add_volume_summary_with_structured_fields():
    mgr = ReadingNotesManager()
    mgr.add_volume_summary(
        "vol_001",
        "summary text",
        ["arc_001"],
        theme="信任与利用",
        main_arcs=[{"character": "林策", "arc": "成长为政治玩家"}],
        faction_changes=[{"faction": "陆党", "change": "失势"}],
        cross_volume_threads=["白泽司主君的真实意图"],
    )
    vol = mgr.notes["plot_state"]["volume_summaries"][0]
    assert vol["theme"] == "信任与利用"
    assert vol["main_arcs"] == [{"character": "林策", "arc": "成长为政治玩家"}]
    assert vol["faction_changes"] == [{"faction": "陆党", "change": "失势"}]
    assert vol["cross_volume_threads"] == ["白泽司主君的真实意图"]


def test_load_old_reading_notes_without_volume_fields():
    """A pre-Phase-D reading_notes.json should load without errors."""
    import json, tempfile, os
    old_state = {
        "arc_interval": 5,
        "volume_arc_threshold": 10,
        "all_segment_summaries": [{"segment_id": "seg_001", "summary": "x"}],
        "_arc_cursor": 0,
        "notes": ReadingNotesManager._empty_notes(),
    }
    # Old volume entry without new fields
    old_state["notes"]["plot_state"]["volume_summaries"].append({
        "volume_id": "vol_001",
        "summary": "old style summary",
        "covered_arcs": ["arc_001"],
    })
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(old_state, f)
        path = f.name
    try:
        mgr = ReadingNotesManager.load(path)
        vol = mgr.notes["plot_state"]["volume_summaries"][0]
        assert vol["summary"] == "old style summary"
        assert "theme" not in vol  # absent, not coerced to None
    finally:
        os.unlink(path)


# ----------------------------------------------------------------------
# Phase E-4 — recent_segment_summaries window honours Settings
# ----------------------------------------------------------------------

def test_recent_summaries_window_respects_settings(monkeypatch):
    """SEED_RECENT_SUMMARIES_WINDOW controls the rolling cap."""
    import app.services.reading_notes_manager as rnm

    monkeypatch.setattr(rnm, "_recent_summaries_window", lambda: 3)
    mgr = ReadingNotesManager()
    for i in range(1, 6):
        mgr.add_segment_summary(f"seg_{i}", f"Events {i}.")
    recent = mgr.notes["plot_state"]["recent_segment_summaries"]
    assert [r["segment_id"] for r in recent] == ["seg_3", "seg_4", "seg_5"]
