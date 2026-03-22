"""Seed 阶段 LLM 规范化公共工具。"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .novel_seed_analyzer import ORG_SUFFIX_TO_TYPE


DEAD_HINTS = ("身死", "战死", "死去", "陨落", "丧命")
INJURED_HINTS = ("受伤", "重伤", "负伤", "流血")
MISSING_HINTS = ("失踪", "下落不明", "消失")
ALLY_HINTS = ("联手", "合作", "协作", "帮助", "救下", "同行")
CONFLICT_HINTS = ("敌视", "追杀", "对峙", "威胁", "冲突", "逼近")


def first_chapter_id(chapter_ids: Sequence[str]) -> str:
    return chapter_ids[0] if chapter_ids else ""


def analysis_entity_map(analysis: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for item in analysis.get("characters", []):
        mapping[item.get("name", "")] = {
            "name": item.get("name", ""),
            "entity_type": "character",
            "aliases": [],
            "summary": item.get("profile_summary", ""),
            "importance_tier": item.get("importance_tier", "supporting"),
            "evidence": item.get("evidence", [])[:3],
        }
    for item in analysis.get("organizations", []):
        mapping[item.get("name", "")] = {
            "name": item.get("name", ""),
            "entity_type": "organization",
            "aliases": [],
            "summary": item.get("summary", ""),
            "importance_tier": item.get("importance_tier", "major"),
            "organization_type": item.get("organization_type", "organization"),
            "evidence": item.get("evidence", [])[:3],
        }
    return mapping


def build_entity_record(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "entity_type": infer_entity_type(name),
        "aliases": [],
        "summary": "",
        "importance_tier": "supporting",
        "evidence": [],
    }


def infer_entity_type(name: str) -> str:
    return "organization" if any(name.endswith(suffix) for suffix in ORG_SUFFIX_TO_TYPE) else "character"


def entity_names(entities: Sequence[Dict[str, Any]], entity_type: str) -> List[str]:
    return [item.get("name", "") for item in entities if item.get("entity_type") == entity_type and item.get("name")]


def mentioned_names(text: str, candidates: Sequence[str]) -> List[str]:
    return [item for item in candidates if item and item in text]


def normalize_name_list(value: Any, candidates: Sequence[str], fallback_text: str) -> List[str]:
    names = normalize_string_list(value)
    return names or mentioned_names(fallback_text, candidates)


def infer_character_state(text: str) -> str:
    if any(hint in text for hint in DEAD_HINTS):
        return "dead"
    if any(hint in text for hint in INJURED_HINTS):
        return "injured"
    if any(hint in text for hint in MISSING_HINTS):
        return "missing"
    return "active"


def infer_relationship_change(text: str) -> str:
    if any(hint in text for hint in ALLY_HINTS):
        return "ally"
    if any(hint in text for hint in CONFLICT_HINTS):
        return "conflict"
    return "co_occurrence"


def normalize_string_list(value: Any) -> List[str]:
    result = []
    for item in list_items(value):
        text = read_text(item)
        if text:
            result.append(text)
    return result


def list_items(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def read_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def read_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def read_summary(value: Any, events: Sequence[Dict[str, Any]]) -> str:
    summary = read_text(value)
    if summary:
        return summary
    joined = "；".join(item.get("summary", "") for item in events[:2] if item.get("summary"))
    return joined or "当前块未提炼出明确主线。"
