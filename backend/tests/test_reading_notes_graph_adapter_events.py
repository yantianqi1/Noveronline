"""Tests for the upgraded story graph adapter:
- key_events become fine-grained PlotEvent nodes
- co_occurrence augments the relationship ledger
- arc-level events resolve participants from structured fields, not substring
"""
from app.services.reading_notes_graph_adapter import (
    _build_event_timeline,
    _build_relationship_ledger,
    adapt_reading_notes_for_graph,
)


def _registry():
    return {
        "林动": {"entity_type": "character", "summary": "主角", "aliases": []},
        "应欢欢": {"entity_type": "character", "summary": "女配", "aliases": []},
        "林炎": {"entity_type": "character", "summary": "兄长", "aliases": ["大哥"]},
    }


def test_key_events_produce_fine_grained_event_nodes():
    plot_state = {"arc_summaries": [], "open_threads": []}
    key_events = [
        {
            "event_id": "arc_001_ev_01",
            "title": "符纹塔斗法",
            "description": "应欢欢与林炎在符纹塔切磋，最终林炎落败。",
            "participants": ["应欢欢", "林炎"],
            "consequence": "应欢欢晋级",
        }
    ]
    events = _build_event_timeline(plot_state, key_events, _registry(), {})
    key = [e for e in events if e["kind"] == "key_event"]
    assert len(key) == 1
    assert key[0]["title"] == "符纹塔斗法"
    assert key[0]["summary"].startswith("应欢欢")
    assert "应欢欢" in key[0]["characters"]
    assert "林炎" in key[0]["characters"]
    assert "林动" not in key[0]["characters"]  # protagonist not present
    assert key[0]["consequence"] == "应欢欢晋级"


def test_arc_event_participants_use_structured_fields_not_only_substring():
    """Arc summary mentions only the protagonist; structured character_arcs
    must still surface supporting characters as participants."""
    plot_state = {
        "arc_summaries": [
            {
                "arc_id": "arc_001",
                "summary": "林动经历了一场惊心动魄的修炼。",
                "character_arcs": [
                    {"name": "应欢欢", "change": "默默支持"},
                    {"name": "林炎", "change": "幕后保护"},
                ],
                "relationship_shifts": [],
            }
        ],
        "open_threads": [],
    }
    events = _build_event_timeline(plot_state, [], _registry(), {})
    arc = [e for e in events if e["kind"] == "arc"][0]
    # Both supporting characters present despite never being named in summary
    assert "应欢欢" in arc["characters"]
    assert "林炎" in arc["characters"]


def test_co_occurrence_adds_co_appears_edges():
    rel_graph = [
        {"source": "林动", "target": "应欢欢", "relation": "ally", "evidence": "并肩作战"},
    ]
    co = [
        {"a": "应欢欢", "b": "林炎", "scene": "饭桌闲聊", "interaction_type": "对话"},
        {"a": "林动", "b": "应欢欢", "scene": "再次同行", "interaction_type": "共处"},
    ]
    ledger = _build_relationship_ledger(rel_graph, co)
    pairs = {(e["source"], e["target"]) for e in ledger}
    assert ("林动", "应欢欢") in pairs
    # New supporting↔supporting edge created from co_occurrence alone
    assert ("应欢欢", "林炎") in pairs
    # The protagonist's existing pair still exists; co_appears strengthens it
    main = next(e for e in ledger if (e["source"], e["target"]) == ("林动", "应欢欢"))
    assert any(c["change"] == "co_appears" for c in main["changes"])


def test_alias_expansion_in_substring_recall():
    plot_state = {
        "arc_summaries": [
            {
                "arc_id": "arc_001",
                "summary": "大哥默默守护着家人。",
                "character_arcs": [],
                "relationship_shifts": [],
            }
        ],
        "open_threads": [],
    }
    alias_map = {"大哥": "林炎"}
    events = _build_event_timeline(plot_state, [], _registry(), alias_map)
    arc = [e for e in events if e["kind"] == "arc"][0]
    assert "林炎" in arc["characters"]
