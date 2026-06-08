"""DB-first read models for seed analysis compatible payloads."""

from __future__ import annotations

import json
from typing import Any

from ..database import get_engine
from ..repositories.entity_repo import EntityRepository
from ..repositories.project_artifact_repo import load_project_artifact
from ..repositories.relationship_repo import RelationshipRepository


CHARACTER_TYPES = {"character", "person", "human", "角色", "人物"}
ORGANIZATION_TYPES = {
    "organization",
    "org",
    "faction",
    "group",
    "guild",
    "sect",
    "school",
    "组织",
    "势力",
    "宗门",
    "门派",
}
IMPORTANCE_TIER_ORDER = {"protagonist": 0, "major": 1, "supporting": 2, "minor": 3}


def load_seed_analysis_for_project(project_id: str) -> dict[str, Any] | None:
    structured = build_seed_analysis_from_structured_tables(project_id)
    artifact = load_project_artifact(project_id, "seed_analysis")
    if structured:
        return merge_seed_analysis_payloads(structured, artifact)
    return artifact if isinstance(artifact, dict) and artifact else None


def load_agent_profiles_for_project(project_id: str) -> dict[str, Any]:
    return build_agent_profiles_from_structured_tables(project_id)


def build_agent_profiles_from_structured_tables(project_id: str) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for row in EntityRepository(get_engine()).list_entities(project_id):
        profile = entity_profile(row)
        if not profile:
            continue
        name = str((profile.get("basic_info") or {}).get("name") or row.get("name") or "").strip()
        if name:
            profiles[name] = profile
    return profiles


def build_seed_analysis_from_structured_tables(
    project_id: str,
) -> dict[str, Any] | None:
    engine = get_engine()
    entity_rows = EntityRepository(engine).list_entities(project_id)
    relationship_rows = RelationshipRepository(engine).list_relationships(project_id)
    entity_by_id = {
        str(row.get("entity_id") or ""): row
        for row in entity_rows
        if row.get("entity_id")
    }
    characters = [
        entity_row_to_seed_character(row)
        for row in entity_rows
        if is_character_entity(row)
    ]
    organizations = [
        entity_row_to_seed_organization(row)
        for row in entity_rows
        if is_organization_entity(row)
    ]
    relations = [
        relationship_row_to_seed_relation(row, entity_by_id)
        for row in relationship_rows
    ]
    characters.sort(key=seed_entity_sort_key)
    organizations.sort(key=seed_entity_sort_key)
    if not characters and not organizations and not relations:
        return None
    return {
        "characters": characters,
        "organizations": organizations,
        "relations": relations,
        "character_count": len(characters),
        "organization_count": len(organizations),
        "relation_count": len(relations),
    }


def merge_seed_analysis_payloads(
    structured: dict[str, Any],
    artifact: Any,
) -> dict[str, Any]:
    merged = dict(artifact) if isinstance(artifact, dict) else {}
    for key in ("characters", "organizations", "relations"):
        structured_items = structured.get(key)
        if structured_items:
            merged[key] = structured_items
        elif key not in merged:
            merged[key] = []
    merged["character_count"] = len(merged.get("characters") or [])
    merged["organization_count"] = len(merged.get("organizations") or [])
    merged["relation_count"] = len(merged.get("relations") or [])
    return merged


def is_character_entity(row: dict[str, Any]) -> bool:
    return str(row.get("entity_type") or "").lower() in CHARACTER_TYPES


def is_organization_entity(row: dict[str, Any]) -> bool:
    return str(row.get("entity_type") or "").lower() in ORGANIZATION_TYPES


def seed_entity_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    tier = str(row.get("importance_tier") or "").lower()
    return (IMPORTANCE_TIER_ORDER.get(tier, 99), str(row.get("name") or ""))


def entity_profile(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("profile_json")
    if raw in (None, "", "{}", "'{}'"):
        return {}
    parsed = json.loads(str(raw))
    return parsed if isinstance(parsed, dict) else {}


def entity_row_to_seed_character(row: dict[str, Any]) -> dict[str, Any]:
    profile = entity_profile(row)
    identity_hint = (
        profile.get("identity_hint")
        or (profile.get("basic_info") or {}).get("identity")
        or ""
    )
    return {
        "entity_id": row.get("entity_id", ""),
        "name": row.get("name", ""),
        "importance_tier": row.get("importance_tier") or profile.get("importance_tier") or "minor",
        "identity_hint": identity_hint,
        "profile_summary": row.get("summary") or profile.get("profile_summary") or profile.get("summary") or "",
        "core_drive": row.get("core_drive") or profile.get("core_drive") or "",
        "current_objective": row.get("current_objective") or profile.get("current_objective") or "",
    }


def entity_row_to_seed_organization(row: dict[str, Any]) -> dict[str, Any]:
    profile = entity_profile(row)
    return {
        "entity_id": row.get("entity_id", ""),
        "name": row.get("name", ""),
        "importance_tier": row.get("importance_tier") or profile.get("importance_tier") or "major",
        "organization_type": profile.get("organization_type") or row.get("entity_type") or "organization",
        "summary": row.get("summary") or profile.get("summary") or "",
    }


def relationship_row_to_seed_relation(
    row: dict[str, Any],
    entity_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_id = str(row.get("source_id") or "")
    target_id = str(row.get("target_id") or "")
    source = entity_by_id.get(source_id, {})
    target = entity_by_id.get(target_id, {})
    description = row.get("description") or ""
    history = row.get("history")
    evolution_chain = json.loads(history) if history else []
    if not isinstance(evolution_chain, list):
        evolution_chain = []
    evidence = [description] if description else []
    return {
        "relation_id": row.get("relation_id", ""),
        "source": source.get("name") or source_id,
        "target": target.get("name") or target_id,
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": row.get("relation_type") or "related",
        "description": description,
        "evidence": evidence,
        "evolution_chain": evolution_chain,
    }
