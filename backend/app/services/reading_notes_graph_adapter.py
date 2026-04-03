"""将 reading_notes + seed_analysis 转换为 LocalStoryGraphBuilder 所需的输入格式。"""

from typing import Any, Dict, List, Optional, Tuple


def adapt_reading_notes_for_graph(
    reading_notes: Dict[str, Any],
    seed_analysis: Dict[str, Any],
    smart_segments: Optional[Dict[str, Any]] = None,
    chapter_segments: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Convert reading_notes + seed_analysis into the 4 artifacts for graph building.

    Returns (story_memory, local_block_facts, block_analyses, chapter_continuity).
    """
    core = reading_notes.get("core_facts", {})
    tier_lookup = _build_tier_lookup(seed_analysis)

    entity_registry = _build_entity_registry(core, tier_lookup)
    relationship_ledger = _build_relationship_ledger(reading_notes.get("relationship_graph", []))
    event_timeline = _build_event_timeline(reading_notes.get("plot_state", {}), entity_registry)
    world_rules = _build_world_rules(core.get("world_rules", []))

    story_memory = {
        "block_count": len(smart_segments.get("segments", [])) if smart_segments else 1,
        "entity_registry": entity_registry,
        "alias_map": _build_alias_map(core.get("characters", {})),
        "relationship_ledger": relationship_ledger,
        "event_timeline": event_timeline,
        "open_threads": [
            {"thread_id": f"thread_{i}", "description": t.get("thread", "")}
            for i, t in enumerate(reading_notes.get("plot_state", {}).get("open_threads", []))
        ],
        "world_rules": world_rules,
        "block_summaries": [],
    }

    local_block_facts = _build_local_block_facts(core, smart_segments)
    block_analyses = {"block_count": local_block_facts["block_count"]}
    chapter_count = len(chapter_segments.get("chapters", [])) if chapter_segments else 0
    chapter_continuity = {"chapter_count": chapter_count}

    return story_memory, local_block_facts, block_analyses, chapter_continuity


def _build_tier_lookup(seed_analysis: Dict[str, Any]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for char in seed_analysis.get("characters", []):
        name = char.get("name", "").strip()
        if name:
            lookup[name] = char.get("importance_tier", "supporting")
    for org in seed_analysis.get("organizations", []):
        name = org.get("name", "").strip()
        if name:
            lookup[name] = org.get("importance_tier", "supporting")
    return lookup


def _build_entity_registry(
    core: Dict[str, Any], tier_lookup: Dict[str, str]
) -> Dict[str, Dict[str, Any]]:
    registry: Dict[str, Dict[str, Any]] = {}

    for name, data in core.get("characters", {}).items():
        evidence = list(data.get("key_actions", []))[:3] + list(data.get("quote_examples", []))[:2]
        registry[name] = {
            "entity_type": "character",
            "summary": data.get("identity", "") or name,
            "importance_tier": tier_lookup.get(name, "supporting"),
            "aliases": list(data.get("aliases", [])),
            "mention_blocks": list(data.get("segments_seen", [])),
            "evidence": evidence or [name],
        }

    for name, data in core.get("organizations", {}).items():
        registry[name] = {
            "entity_type": "organization",
            "summary": data.get("purpose", "") or name,
            "importance_tier": tier_lookup.get(name, "supporting"),
            "organization_type": data.get("type", "organization"),
            "aliases": [],
            "mention_blocks": list(data.get("segments_seen", [])),
            "evidence": [data.get("purpose", "")] if data.get("purpose") else [name],
        }

    for name, data in core.get("key_locations", {}).items():
        registry[name] = {
            "entity_type": "location",
            "summary": data.get("description", "") or name,
            "importance_tier": "supporting",
            "aliases": [],
            "mention_blocks": list(data.get("segments_seen", [])) if isinstance(data, dict) else [],
            "evidence": [name],
        }

    return registry


def _build_relationship_ledger(
    relationship_graph: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    pairs: Dict[str, Dict[str, Any]] = {}
    for entry in relationship_graph:
        source = entry.get("source", "")
        target = entry.get("target", "")
        if not source or not target:
            continue
        key = f"{source}|{target}"
        if key not in pairs:
            pairs[key] = {"source": source, "target": target, "changes": []}
        pairs[key]["changes"].append({
            "change": entry.get("relation", "co_occurrence"),
            "chapter_id": "",
            "block_id": entry.get("segment_id", ""),
            "evidence": [entry["evidence"]] if entry.get("evidence") else [],
        })
    return list(pairs.values())


def _build_event_timeline(
    plot_state: Dict[str, Any], entity_registry: Dict[str, Any]
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    entity_names = list(entity_registry.keys())
    for i, arc in enumerate(plot_state.get("arc_summaries", [])):
        summary = arc.get("summary", "") if isinstance(arc, dict) else str(arc)
        mentioned = [n for n in entity_names if n in summary]
        events.append({
            "summary": summary,
            "event_id": f"arc_{i}",
            "chapter_id": "",
            "block_id": "",
            "characters": mentioned,
            "organizations": [],
            "evidence": [summary] if summary else [],
        })
    for i, thread in enumerate(plot_state.get("open_threads", [])):
        desc = thread.get("thread", "") if isinstance(thread, dict) else str(thread)
        if not desc:
            continue
        mentioned = [n for n in entity_names if n in desc]
        events.append({
            "summary": desc,
            "event_id": f"thread_{i}",
            "chapter_id": "",
            "block_id": "",
            "characters": mentioned,
            "organizations": [],
            "evidence": [desc],
        })
    return events


def _build_world_rules(world_rules: List) -> List[str]:
    rules: List[str] = []
    for item in world_rules:
        if isinstance(item, dict):
            fact = item.get("fact", "")
            if fact:
                rules.append(fact)
        elif isinstance(item, str) and item:
            rules.append(item)
    return rules


def _build_alias_map(characters: Dict[str, Any]) -> Dict[str, str]:
    alias_map: Dict[str, str] = {}
    for name, data in characters.items():
        for alias in data.get("aliases", []):
            if alias and alias != name:
                alias_map[alias] = name
    return alias_map


def _build_local_block_facts(
    core: Dict[str, Any],
    smart_segments: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    characters = core.get("characters", {})

    if smart_segments and smart_segments.get("segments"):
        segments = smart_segments["segments"]
        packets = []
        for seg in segments:
            seg_id = seg.get("segment_id", "")
            owned = seg.get("chapters", [])
            if isinstance(owned, list) and owned and isinstance(owned[0], dict):
                owned = [c.get("title", c.get("chapter_id", "")) for c in owned]
            local_entities = []
            for name, data in characters.items():
                if seg_id in data.get("segments_seen", []):
                    evidence = list(data.get("key_actions", []))[:2]
                    local_entities.append({"name": name, "evidence": evidence})
            packets.append({
                "block_id": seg_id,
                "owned_chapters": owned if isinstance(owned, list) else [str(owned)],
                "local_entities": local_entities,
            })
        return {"block_count": len(packets), "packets": packets}

    # Fallback: single synthetic packet with all characters
    all_entities = [
        {"name": name, "evidence": list(data.get("key_actions", []))[:2]}
        for name, data in characters.items()
    ]
    return {
        "block_count": 1,
        "packets": [{"block_id": "full", "owned_chapters": [], "local_entities": all_entities}],
    }
