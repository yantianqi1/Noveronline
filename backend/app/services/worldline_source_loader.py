"""
世界线种子源加载器
"""

from typing import Any, Dict, List, Optional

from ..repositories.project_artifact_repo import load_project_artifact
from .archive_library_service import ArchiveLibraryService
from .world_state_store import WorldStateStore


ORG_KEYWORDS = (
    "organization", "org", "faction", "group", "guild", "company", "sect", "school",
    "宗门", "组织", "势力", "门派", "集团", "公司",
)
SEED_AGENT_AXES = ["关系变化", "组织博弈", "信息差", "角色目标"]
DEFAULT_ACTORS = {
    "主角": {
        "agent_kind": "character",
        "status": "active",
        "drive": "回应变量扰动并寻求最优路径",
        "tension": "未知风险正在累积",
        "role": "protagonist",
        "importance_tier": "protagonist",
        "last_event": "seed",
    },
    "关键对手": {
        "agent_kind": "character",
        "status": "active",
        "drive": "维持既有秩序或争夺主导权",
        "tension": "与主角目标存在冲突",
        "role": "major",
        "importance_tier": "major",
        "last_event": "seed",
    },
}


class WorldlineSourceLoader:
    def __init__(self, store: WorldStateStore):
        self.store = store

    def load(
        self,
        project: Optional[Any],
        graph_id: str,
        container_dir: str,
        archives: Optional[List[Dict[str, Any]]] = None,
        entity_types: Optional[List[str]] = None,
        config_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        config = self._load_config(container_dir, config_override)
        seed_analysis = self._load_seed_analysis(project, container_dir)
        resolved_archives = self._load_archives(container_dir, archives)
        entities = self._load_entities(graph_id, entity_types, resolved_archives, seed_analysis)

        actors, organizations = self._build_actor_maps(project.project_id if project else None, resolved_archives, seed_analysis, entities)
        relationships = self._build_relationships(resolved_archives, seed_analysis, actors, organizations)
        if not actors and not organizations:
            actors = {name: dict(state) for name, state in DEFAULT_ACTORS.items()}

        return {
            "actors": actors,
            "organizations": organizations,
            "relationships": relationships,
            "graph_id": graph_id,
            "session_scope": "project" if project else "global",
            "timeline_focus": self._timeline_focus(config, seed_analysis),
            "agent_behavior_axes": self._agent_axes(config, seed_analysis),
            "source_summary": {
                "archives": len(resolved_archives),
                "parallel_world_config": bool(config),
                "graph_entities": len(entities),
                "seed_analysis": bool(seed_analysis),
            },
            "config": config,
        }

    def _load_config(
        self,
        container_dir: str,
        config_override: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if config_override is not None:
            return config_override
        return self.store.load_json_if_exists(container_dir, "parallel_world_config.json") or {}

    def _load_seed_analysis(
        self,
        project: Optional[Any],
        container_dir: str,
    ) -> Dict[str, Any]:
        seed_analysis = self.store.load_json_if_exists(container_dir, "seed_analysis.json")
        if seed_analysis or not project:
            return seed_analysis or {}
        return load_project_artifact(project.project_id, "seed_analysis") or {}

    def _load_archives(
        self,
        container_dir: str,
        archives: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        if archives is not None:
            return archives
        archive_payload = self.store.load_json_if_exists(container_dir, "narrative_archives.json")
        if not archive_payload:
            return []
        if isinstance(archive_payload.get("archives"), list):
            return archive_payload["archives"]
        if isinstance(archive_payload, list):
            return archive_payload
        raise ValueError("narrative_archives.json 结构无效")

    def _load_entities(
        self,
        graph_id: str,
        entity_types: Optional[List[str]],
        resolved_archives: List[Dict[str, Any]],
        seed_analysis: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if not graph_id or not str(graph_id).startswith("local_graph_"):
            return []
        from .zep_entity_reader import ZepEntityReader

        reader = ZepEntityReader()
        filtered = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=False,
        )
        return [entity.to_dict() for entity in filtered.entities[:120]]

    def _build_actor_maps(
        self,
        project_id: Optional[str],
        resolved_archives: List[Dict[str, Any]],
        seed_analysis: Dict[str, Any],
        entities: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        actors = self._actors_from_archives(project_id, resolved_archives)
        organizations = self._organizations_from_archives(project_id, resolved_archives)
        if actors or organizations:
            return actors, organizations
        actors = self._actors_from_entities(entities)
        organizations = self._organizations_from_entities(entities)
        if actors or organizations:
            return actors, organizations
        if not actors:
            actors = self._actors_from_seed(seed_analysis)
        if not organizations:
            organizations = self._organizations_from_seed(seed_analysis)
        return actors, organizations

    def _actors_from_archives(self, project_id: Optional[str], archives: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        return self._states_from_archives(project_id, archives, want_org=False)

    def _organizations_from_archives(self, project_id: Optional[str], archives: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        return self._states_from_archives(project_id, archives, want_org=True)

    def _states_from_archives(
        self,
        project_id: Optional[str],
        archives: List[Dict[str, Any]],
        want_org: bool,
    ) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for item in archives:
            name = item.get("entity_name") or item.get("name")
            if not name:
                continue
            agent_kind = item.get("agent_kind") or "generic"
            if agent_kind == "relationship":
                continue
            entity_type = (item.get("entity_type") or "").lower()
            if self._is_organization(entity_type) != want_org:
                continue
            template_payload = dict(item.get("template_payload") or {})
            result[name] = {
                "agent_kind": agent_kind,
                "status": self._state_status(template_payload),
                "drive": item.get("core_drive") or "维持当前立场",
                "tension": item.get("hidden_tension") or "潜在冲突尚未显性化",
                "role": item.get("entity_role", ""),
                "importance_tier": item.get("importance_tier", "supporting"),
                "entity_uuid": item.get("entity_uuid"),
                "archive_id": item.get("archive_id") or self._archive_id(project_id, item),
                "template_key": item.get("template_key"),
                "template_version": item.get("template_version", "v1"),
                "template_sections": list(item.get("template_sections") or []),
                "template_payload": template_payload,
                "state_source": "narrative_archives",
                "last_event": "seed",
            } | self._detail_state_fields(agent_kind, template_payload)
        return result

    def _actors_from_seed(self, seed_analysis: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for item in seed_analysis.get("characters", []):
            name = item.get("name", "")
            if not name:
                continue
            result[name] = {
                "agent_kind": "character",
                "status": "active",
                "drive": "推动自己在主线中的目标",
                "tension": item.get("profile_summary") or "命运与关系网络正在收紧",
                "role": item.get("identity_hint", "角色"),
                "importance_tier": item.get("importance_tier", "supporting"),
                "entity_uuid": f"seed_character_{name}",
                "state_source": "seed_analysis",
                "last_event": "seed",
            }
        return result

    def _organizations_from_seed(self, seed_analysis: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for item in seed_analysis.get("organizations", []):
            name = item.get("name", "")
            if not name:
                continue
            result[name] = {
                "agent_kind": "organization",
                "status": "active",
                "drive": "维持组织利益与权力秩序",
                "tension": item.get("summary") or "组织内部与外部压力并存",
                "role": item.get("organization_type", "organization"),
                "importance_tier": item.get("importance_tier", "major"),
                "entity_uuid": f"seed_org_{name}",
                "state_source": "seed_analysis",
                "last_event": "seed",
            }
        return result

    def _actors_from_entities(self, entities: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        return self._states_from_entities(entities, want_org=False)

    def _organizations_from_entities(self, entities: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        return self._states_from_entities(entities, want_org=True)

    def _states_from_entities(
        self,
        entities: List[Dict[str, Any]],
        want_org: bool,
    ) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for entity in entities:
            name = entity.get("name", "")
            if not name:
                continue
            entity_type = next(
                (str(item).lower() for item in entity.get("labels", []) if str(item).lower() not in ("entity", "node")),
                "unknown",
            )
            if self._is_organization(entity_type) != want_org:
                continue
            result[name] = {
                "agent_kind": "organization" if want_org else "generic",
                "status": "active",
                "drive": "根据图谱上下文推进目标",
                "tension": "外部变量可能引发关系变化",
                "role": entity_type,
                "importance_tier": "supporting",
                "entity_uuid": entity.get("uuid"),
                "state_source": "graph_entities",
                "last_event": "seed",
            }
        return result

    def _build_relationships(
        self,
        archives: List[Dict[str, Any]],
        seed_analysis: Dict[str, Any],
        actors: Dict[str, Dict[str, Any]],
        organizations: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        archived = self._relationships_from_archives(archives, actors, organizations)
        return archived or self._relationships_from_seed(seed_analysis, actors, organizations)

    def _timeline_focus(self, config: Dict[str, Any], seed_analysis: Dict[str, Any]) -> List[str]:
        if config.get("timeline_focus"):
            return list(config["timeline_focus"])
        return [item.get("title", "") for item in seed_analysis.get("chapter_beats", [])[:4] if item.get("title")]

    def _agent_axes(self, config: Dict[str, Any], seed_analysis: Dict[str, Any]) -> List[str]:
        if config.get("agent_behavior_axes"):
            return list(config["agent_behavior_axes"])
        return list(SEED_AGENT_AXES) if seed_analysis else []

    def _is_organization(self, entity_type: str) -> bool:
        lowered = (entity_type or "").lower()
        return any(keyword in lowered for keyword in ORG_KEYWORDS)

    def _archive_id(self, project_id: Optional[str], item: Dict[str, Any]) -> str:
        entity_uuid = str(item.get("entity_uuid") or "").strip()
        if not project_id or not entity_uuid:
            return ""
        return ArchiveLibraryService.build_archive_id(project_id, entity_uuid)

    def _relationships_from_archives(
        self,
        archives: List[Dict[str, Any]],
        actors: Dict[str, Dict[str, Any]],
        organizations: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        items = []
        for archive in archives:
            if archive.get("agent_kind") != "relationship":
                continue
            relationship_payload = dict((archive.get("template_payload") or {}).get("relationship") or {})
            source = relationship_payload.get("source", "")
            target = relationship_payload.get("target", "")
            if not source or not target:
                continue
            items.append({
                "source": source,
                "target": target,
                "change": relationship_payload.get("change", "co_occurrence"),
                "note": archive.get("relationship_summary") or "从档案中继承的关系",
                "status": self._state_status(archive.get("template_payload") or {}),
                "importance_tier": archive.get("importance_tier", "supporting"),
                "template_key": archive.get("template_key"),
                "template_version": archive.get("template_version", "v1"),
                "template_sections": list(archive.get("template_sections") or []),
                "template_payload": archive.get("template_payload") or {},
                "source_importance_tier": self._state_tier(source, actors, organizations),
                "target_importance_tier": self._state_tier(target, actors, organizations),
                "state_source": "narrative_archives",
            } | self._relationship_state_fields(relationship_payload))
        return items[:120]

    def _relationships_from_seed(
        self,
        seed_analysis: Dict[str, Any],
        actors: Dict[str, Dict[str, Any]],
        organizations: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return [
            {
                "source": item.get("source", ""),
                "target": item.get("target", ""),
                "change": item.get("relation_type", "co_occurrence"),
                "note": "从小说种子中提取的初始关系",
                "source_importance_tier": self._state_tier(item.get("source", ""), actors, organizations),
                "target_importance_tier": self._state_tier(item.get("target", ""), actors, organizations),
                "state_source": "seed_analysis",
            }
            for item in seed_analysis.get("relations", [])[:120]
            if item.get("source") and item.get("target")
        ]

    def _state_tier(
        self,
        name: str,
        actors: Dict[str, Dict[str, Any]],
        organizations: Dict[str, Dict[str, Any]],
    ) -> str:
        state = actors.get(name) or organizations.get(name) or {}
        return str(state.get("importance_tier") or "supporting")

    def _state_status(self, template_payload: Dict[str, Any]) -> str:
        state_payload = dict((template_payload or {}).get("state") or {})
        return str(state_payload.get("status") or "active")

    def _detail_state_fields(self, agent_kind: str, template_payload: Dict[str, Any]) -> Dict[str, Any]:
        identity = dict((template_payload or {}).get("identity") or {})
        behavior = dict((template_payload or {}).get("behavior") or {})
        private = dict((template_payload or {}).get("private") or {})
        state_payload = dict((template_payload or {}).get("state") or {})
        risk_payload = dict((template_payload or {}).get("risk") or {})
        details: Dict[str, Any] = {
            "surface_mask": state_payload.get("surface_mask") or private.get("surface_mask", ""),
            "human_ai_relation_tag": private.get("human_ai_relation_tag", "none"),
            "notable_risks": list(risk_payload.get("notable_risks") or []),
            "can_act_as_agent": bool(state_payload.get("can_act_as_agent", True)),
            "agent_behavior_hint": behavior.get("agent_behavior_hint", ""),
        }
        if agent_kind == "character":
            details.update({
                "identity_hint": identity.get("identity_hint", ""),
                "personality": behavior.get("personality", ""),
                "skills": list(behavior.get("skills") or []),
                "loyalty": behavior.get("loyalty", ""),
                "secrets": list(private.get("secrets") or []),
                "long_term_goal": behavior.get("long_term_goal", ""),
                "short_term_goal": behavior.get("short_term_goal", ""),
            })
        if agent_kind == "organization":
            details.update({
                "organization_type": identity.get("organization_type", ""),
                "resources": list(behavior.get("resources") or []),
                "internal_factions": list(behavior.get("internal_factions") or []),
                "territorial_control": private.get("territorial_control", ""),
                "public_stance": behavior.get("public_stance", ""),
                "strategic_goal": behavior.get("strategic_goal", ""),
                "conflict_targets": list(behavior.get("conflict_targets") or []),
            })
        return details

    def _relationship_state_fields(self, relationship_payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "history": relationship_payload.get("history", ""),
            "power_dynamic": relationship_payload.get("power_dynamic", ""),
            "trust_level": relationship_payload.get("trust_level", ""),
            "conflict_trigger": relationship_payload.get("conflict_trigger", ""),
            "stability_forecast": relationship_payload.get("stability_forecast", ""),
            "last_action": relationship_payload.get("last_action", ""),
        }
