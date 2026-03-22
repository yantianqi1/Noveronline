"""Seed 阶段 LLM 返回结构规范化。"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from ..utils.llm_json import normalize_json_object
from .seed_llm_normalizer_utils import (
    analysis_entity_map,
    build_entity_record,
    entity_names,
    first_chapter_id,
    infer_character_state,
    infer_relationship_change,
    list_items,
    mentioned_names,
    normalize_name_list,
    normalize_string_list,
    read_int,
    read_summary,
    read_text,
)


def normalize_local_block_payload(
    payload: Any,
    analysis: Dict[str, Any],
    owned_chapter_ids: Sequence[str],
) -> Dict[str, Any]:
    value = normalize_json_object(payload, "块内局部事实提取")
    chapter_id = first_chapter_id(owned_chapter_ids)
    entities = normalize_local_entities(value.get("local_entities"), analysis)
    events = normalize_local_events(value.get("local_events"), chapter_id, entities)
    return {
        "local_events": events,
        "local_entities": entities,
        "local_relationship_changes": normalize_relationship_changes(
            value.get("local_relationship_changes"),
            entities,
        ),
        "local_threads": normalize_threads(value.get("local_threads"), chapter_id),
        "unresolved_refs": normalize_unresolved_refs(value.get("unresolved_refs")),
        "local_summary": read_summary(value.get("local_summary"), events),
        "evidence_spans": normalize_evidence_spans(value.get("evidence_spans"), chapter_id),
        "world_rules": normalize_string_list(value.get("world_rules")),
    }


def normalize_contextual_block_payload(payload: Any, packet: Dict[str, Any]) -> Dict[str, Any]:
    value = normalize_json_object(payload, "前情快照剧情分析")
    return {
        "plot_summary": read_text(value.get("plot_summary")) or packet.get("local_summary", ""),
        "character_state_updates": normalize_character_updates(value.get("character_state_updates"), packet),
        "relationship_updates": normalize_relationship_updates(value.get("relationship_updates"), packet),
        "thread_updates": normalize_thread_updates(value.get("thread_updates")),
        "block_end_state": normalize_block_end_state(value.get("block_end_state"), packet, value.get("plot_summary")),
    }


def normalize_local_entities(items: Any, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    entity_map = analysis_entity_map(analysis)
    normalized = []
    seen = set()
    for item in list_items(items):
        record = item if isinstance(item, dict) else entity_map.get(str(item).strip(), build_entity_record(str(item).strip()))
        name = read_text(record.get("name"))
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(
            {
                "name": name,
                "entity_type": read_text(record.get("entity_type")) or build_entity_record(name)["entity_type"],
                "aliases": normalize_string_list(record.get("aliases")),
                "summary": read_text(record.get("summary")),
                "importance_tier": read_text(record.get("importance_tier")) or "supporting",
                "organization_type": read_text(record.get("organization_type")) or "organization",
                "evidence": normalize_string_list(record.get("evidence"))[:3],
            }
        )
    return normalized


def normalize_local_events(items: Any, chapter_id: str, entities: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    characters = entity_names(entities, "character")
    organizations = entity_names(entities, "organization")
    for index, item in enumerate(list_items(items), start=1):
        summary = read_text(item.get("summary")) if isinstance(item, dict) else read_text(item)
        if not summary:
            continue
        normalized.append(
            {
                "event_id": read_text(item.get("event_id")) if isinstance(item, dict) else f"{chapter_id}_event_{index:02d}",
                "chapter_id": read_text(item.get("chapter_id")) if isinstance(item, dict) else chapter_id,
                "summary": summary,
                "characters": normalize_name_list(item.get("characters"), characters, summary) if isinstance(item, dict) else mentioned_names(summary, characters),
                "organizations": normalize_name_list(item.get("organizations"), organizations, summary) if isinstance(item, dict) else mentioned_names(summary, organizations),
                "evidence": normalize_string_list(item.get("evidence"))[:2] if isinstance(item, dict) else [summary],
            }
        )
    return normalized


def normalize_relationship_changes(items: Any, entities: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    names = [item.get("name", "") for item in entities]
    normalized = []
    for item in list_items(items):
        if isinstance(item, dict):
            normalized.append(
                {
                    "source": read_text(item.get("source")),
                    "target": read_text(item.get("target")),
                    "change": read_text(item.get("change") or item.get("relation_type")) or "co_occurrence",
                    "weight": read_int(item.get("weight"), 1),
                    "evidence": normalize_string_list(item.get("evidence"))[:3],
                }
            )
            continue
        text = read_text(item)
        matched = mentioned_names(text, names)
        normalized.append(
            {
                "source": matched[0] if len(matched) > 0 else "",
                "target": matched[1] if len(matched) > 1 else "",
                "change": infer_relationship_change(text),
                "weight": 1,
                "evidence": [text] if text else [],
            }
        )
    return normalized


def normalize_threads(items: Any, chapter_id: str) -> List[Dict[str, Any]]:
    normalized = []
    for item in list_items(items):
        if isinstance(item, dict):
            summary = read_text(item.get("summary")) or read_text(item.get("thread_key"))
            key = read_text(item.get("thread_key")) or summary[:40]
            status = read_text(item.get("status")) or "open"
        else:
            summary = read_text(item)
            key = summary[:40]
            status = "open"
        if not key:
            continue
        normalized.append({"thread_key": key, "status": status, "summary": summary, "chapter_id": chapter_id})
    return normalized


def normalize_unresolved_refs(items: Any) -> List[Dict[str, Any]]:
    normalized = []
    for item in list_items(items):
        if isinstance(item, dict):
            normalized.append(
                {
                    "alias": read_text(item.get("alias")),
                    "candidate_names": normalize_string_list(item.get("candidate_names")),
                    "reason": read_text(item.get("reason")) or "存在未解析指代",
                }
            )
            continue
        text = read_text(item)
        normalized.append({"alias": "", "candidate_names": [], "reason": text or "存在未解析指代"})
    return normalized


def normalize_evidence_spans(items: Any, chapter_id: str) -> List[Dict[str, Any]]:
    normalized = []
    for item in list_items(items):
        if isinstance(item, dict):
            snippet = read_text(item.get("snippet") or item.get("evidence"))
            span_chapter_id = read_text(item.get("chapter_id")) or chapter_id
        else:
            snippet = read_text(item)
            span_chapter_id = chapter_id
        if not snippet:
            continue
        normalized.append({"chapter_id": span_chapter_id, "snippet": snippet})
    return normalized


def normalize_character_updates(items: Any, packet: Dict[str, Any]) -> List[Dict[str, Any]]:
    character_names = entity_names(packet.get("local_entities", []), "character")
    normalized = []
    for item in list_items(items):
        if isinstance(item, dict):
            normalized.append(
                {
                    "name": read_text(item.get("name")),
                    "state": read_text(item.get("state")) or infer_character_state(" ".join(normalize_string_list(item.get("evidence")))),
                    "evidence": normalize_string_list(item.get("evidence"))[:2],
                }
            )
            continue
        text = read_text(item)
        for name in mentioned_names(text, character_names):
            normalized.append({"name": name, "state": infer_character_state(text), "evidence": [text]})
    return normalized


def normalize_relationship_updates(items: Any, packet: Dict[str, Any]) -> List[Dict[str, Any]]:
    names = [item.get("name", "") for item in packet.get("local_entities", [])]
    normalized = []
    for item in list_items(items):
        if isinstance(item, dict):
            normalized.append(
                {
                    "source": read_text(item.get("source")),
                    "target": read_text(item.get("target")),
                    "state": read_text(item.get("state") or item.get("change")) or "co_occurrence",
                    "evidence": normalize_string_list(item.get("evidence"))[:2],
                }
            )
            continue
        text = read_text(item)
        matched = mentioned_names(text, names)
        normalized.append(
            {
                "source": matched[0] if len(matched) > 0 else "",
                "target": matched[1] if len(matched) > 1 else "",
                "state": infer_relationship_change(text),
                "evidence": [text] if text else [],
            }
        )
    return normalized


def normalize_thread_updates(items: Any) -> List[Dict[str, Any]]:
    return [{"thread_key": item["thread_key"], "status": item["status"], "summary": item["summary"]} for item in normalize_threads(items, "")]


def normalize_block_end_state(value: Any, packet: Dict[str, Any], plot_summary: Any) -> Dict[str, Any]:
    characters = entity_names(packet.get("local_entities", []), "character")
    organizations = entity_names(packet.get("local_entities", []), "organization")
    if isinstance(value, dict):
        return {
            "focus_characters": normalize_name_list(value.get("focus_characters"), characters, read_text(plot_summary)),
            "focus_organizations": normalize_name_list(value.get("focus_organizations"), organizations, read_text(plot_summary)),
            "open_threads": normalize_string_list(value.get("open_threads"))[:6],
            "summary": read_text(value.get("summary")) or read_text(plot_summary) or packet.get("local_summary", ""),
        }
    summary = read_text(value) or read_text(plot_summary) or packet.get("local_summary", "")
    return {
        "focus_characters": mentioned_names(summary, characters) or characters[:6],
        "focus_organizations": mentioned_names(summary, organizations) or organizations[:4],
        "open_threads": [item.get("thread_key", "") for item in packet.get("local_threads", []) if item.get("thread_key")][:6],
        "summary": summary,
    }
