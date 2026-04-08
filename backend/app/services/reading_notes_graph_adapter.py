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
    # reading_notes.json serializes ReadingNotesManager state:
    # the actual notes live under a "notes" key when saved via manager.save()
    notes = reading_notes.get("notes", reading_notes)
    core = notes.get("core_facts", {})
    tier_lookup = _build_tier_lookup(seed_analysis)

    entity_registry = _build_entity_registry(core, tier_lookup)
    alias_map = _build_alias_map(core.get("characters", {}))
    relationship_ledger = _build_relationship_ledger(
        notes.get("relationship_graph", []),
        notes.get("co_occurrence", []),
    )
    event_timeline = _build_event_timeline(
        notes.get("plot_state", {}),
        notes.get("key_events", []),
        entity_registry,
        alias_map,
    )
    world_rules = _build_world_rules(core.get("world_rules", []))

    story_memory = {
        "block_count": len(smart_segments.get("segments", [])) if smart_segments else 1,
        "entity_registry": entity_registry,
        "alias_map": _build_alias_map(core.get("characters", {})),
        "relationship_ledger": relationship_ledger,
        "event_timeline": event_timeline,
        "open_threads": [
            {"thread_id": f"thread_{i}", "description": t.get("thread", "")}
            for i, t in enumerate(notes.get("plot_state", {}).get("open_threads", []))
        ],
        "world_rules": world_rules,
        "block_summaries": [],
        "alias_map_full": alias_map,
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
    co_occurrence: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Build merged relationship ledger from explicit relationship_graph
    and lightweight co_occurrence pairs.

    Explicit relations win over CO_APPEARS for the same (source, target) pair.
    """
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

    # Augment with CO_APPEARS edges from co_occurrence — undirected,
    # only added when no explicit relation exists for either direction.
    for entry in co_occurrence or []:
        a = entry.get("a", "")
        b = entry.get("b", "")
        if not a or not b or a == b:
            continue
        key_ab = f"{a}|{b}"
        key_ba = f"{b}|{a}"
        if key_ab in pairs or key_ba in pairs:
            # Strengthen existing pair with an extra evidence trace
            target_key = key_ab if key_ab in pairs else key_ba
            pairs[target_key]["changes"].append({
                "change": "co_appears",
                "chapter_id": "",
                "block_id": entry.get("segment_id", ""),
                "evidence": [entry.get("scene", "")] if entry.get("scene") else [],
            })
            continue
        pairs[key_ab] = {
            "source": a,
            "target": b,
            "changes": [{
                "change": "co_appears",
                "chapter_id": "",
                "block_id": entry.get("segment_id", ""),
                "evidence": [entry.get("scene", "")] if entry.get("scene") else [],
            }],
        }
    return list(pairs.values())


def _build_event_timeline(
    plot_state: Dict[str, Any],
    key_events: List[Dict[str, Any]],
    entity_registry: Dict[str, Any],
    alias_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Construct event nodes for the graph.

    Source priority:
    1. ``key_events`` (per-event LLM extraction) — produces fine-grained
       PlotEvent nodes with title/description/participants.
    2. ``plot_state.arc_summaries`` — produces coarse arc-level event nodes
       (kept for backwards compatibility / context).
    3. ``plot_state.open_threads`` — produces thread placeholder events.

    Participants are resolved structurally (no naive substring matching as
    primary signal); substring matching is only used as a supplementary
    recall step with alias expansion.
    """
    events: List[Dict[str, Any]] = []
    entity_names = list(entity_registry.keys())
    alias_map = alias_map or {}

    def _resolve_name(name: str) -> str:
        """Resolve a name to its canonical form via alias map."""
        if not name:
            return ""
        if name in entity_registry:
            return name
        if name in alias_map:
            return alias_map[name]
        return name

    def _substring_recall(text: str, exclude: set) -> List[str]:
        """Supplementary substring matching with alias expansion."""
        if not text:
            return []
        found: List[str] = []
        for n in entity_names:
            if n in exclude or n not in text:
                continue
            found.append(n)
        for alias, canonical in alias_map.items():
            if canonical in exclude or canonical in found:
                continue
            if alias and alias in text:
                found.append(canonical)
        return found

    # 1) Fine-grained key_events (preferred)
    for ev in key_events or []:
        if not isinstance(ev, dict):
            continue
        title = (ev.get("title") or "").strip()
        description = (ev.get("description") or "").strip()
        if not title and not description:
            continue
        structured = [_resolve_name(p) for p in (ev.get("participants") or []) if isinstance(p, str) and p.strip()]
        structured = [p for p in structured if p]
        seen = set(structured)
        recalled = _substring_recall(description or title, seen)
        characters = structured + recalled
        events.append({
            "summary": description or title,
            "title": title or description[:30],
            "event_id": ev.get("event_id") or f"key_event_{len(events)}",
            "arc_id": ev.get("arc_id", ""),
            "chapter_id": ev.get("chapter_hint", ""),
            "block_id": "",
            "characters": characters,
            "organizations": [],
            "evidence": [description] if description else ([title] if title else []),
            "consequence": ev.get("consequence", ""),
            "kind": "key_event",
        })

    # 2) Arc-level events (coarse) — derive participants from structured fields
    for i, arc in enumerate(plot_state.get("arc_summaries", [])):
        if not isinstance(arc, dict):
            arc = {"summary": str(arc)}
        summary = arc.get("summary", "")
        # Structured: character_arcs[*].name + relationship_shifts[*].{source,target}
        structured: List[str] = []
        for ca in arc.get("character_arcs", []) or []:
            n = _resolve_name(ca.get("name", "") if isinstance(ca, dict) else "")
            if n and n not in structured:
                structured.append(n)
        for rs in arc.get("relationship_shifts", []) or []:
            if not isinstance(rs, dict):
                continue
            for k in ("source", "target"):
                n = _resolve_name(rs.get(k, ""))
                if n and n not in structured:
                    structured.append(n)
        seen = set(structured)
        recalled = _substring_recall(summary, seen)
        characters = structured + recalled
        events.append({
            "summary": summary,
            "title": (arc.get("arc_id") or f"arc_{i}"),
            "event_id": arc.get("arc_id") or f"arc_{i}",
            "chapter_id": "",
            "block_id": "",
            "characters": characters,
            "organizations": [],
            "evidence": [summary] if summary else [],
            "kind": "arc",
        })

    # 3) Thread placeholders
    for i, thread in enumerate(plot_state.get("open_threads", [])):
        desc = thread.get("thread", "") if isinstance(thread, dict) else str(thread)
        if not desc:
            continue
        recalled = _substring_recall(desc, set())
        events.append({
            "summary": desc,
            "title": desc[:30],
            "event_id": f"thread_{i}",
            "chapter_id": "",
            "block_id": "",
            "characters": recalled,
            "organizations": [],
            "evidence": [desc],
            "kind": "thread",
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
