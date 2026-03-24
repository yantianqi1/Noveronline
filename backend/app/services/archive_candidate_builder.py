"""档案候选构建器。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .agent_template_registry import AgentTemplateRegistry
from .zep_entity_reader_types import EntityNode


CHARACTER_KEYWORDS = ("character", "人物", "角色", "human", "person")
ORGANIZATION_KEYWORDS = (
    "organization", "org", "faction", "group", "guild", "company", "sect", "school",
    "宗门", "组织", "势力", "门派", "集团", "公司",
)


def relation_candidate_id(source_id: str, target_id: str) -> str:
    left, right = sorted([str(source_id or ""), str(target_id or "")])
    return f"relation::{left}::{right}"


def relation_display_name(source: str, target: str) -> str:
    return f"{source} × {target}"


class ArchiveCandidateBuilder:
    """统一构建图谱/种子分析下的档案候选。"""

    def __init__(self, template_registry: Optional[AgentTemplateRegistry] = None):
        self.template_registry = template_registry or AgentTemplateRegistry()

    def build_from_seed_analysis(self, seed_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        entity_tiers: Dict[str, str] = {}
        entity_ids: Dict[str, str] = {}

        for item in seed_analysis.get("characters", []):
            candidate = self._seed_candidate(item, "Character", "character", item.get("profile_summary", ""))
            candidates.append(candidate)
            entity_tiers[candidate["display_name"]] = candidate["recommended_importance_tier"]
            entity_ids[candidate["display_name"]] = candidate["entity_uuid"]

        for item in seed_analysis.get("organizations", []):
            candidate = self._seed_candidate(item, "Organization", "organization", item.get("summary", ""))
            candidates.append(candidate)
            entity_tiers[candidate["display_name"]] = candidate["recommended_importance_tier"]
            entity_ids[candidate["display_name"]] = candidate["entity_uuid"]

        for item in seed_analysis.get("relations", [])[:120]:
            source = str(item.get("source") or "").strip()
            target = str(item.get("target") or "").strip()
            if not source or not target:
                continue
            recommended = self.template_registry.max_tier([
                entity_tiers.get(source, "supporting"),
                entity_tiers.get(target, "supporting"),
            ])
            candidates.append(
                self._relation_candidate(
                    source=source,
                    target=target,
                    source_uuid=entity_ids.get(source, source),
                    target_uuid=entity_ids.get(target, target),
                    relation_type=item.get("relation_type", "co_occurrence"),
                    summary=(item.get("evidence") or [""])[0] or f"{source} 与 {target} 存在初始关系",
                    recommended_tier=recommended,
                    source_kind="seed_analysis",
                )
            )
        return candidates

    def build_from_entities(self, entities: Iterable[EntityNode]) -> List[Dict[str, Any]]:
        entity_list = list(entities)
        name_by_uuid = {item.uuid: item.name for item in entity_list}
        tier_by_uuid: Dict[str, str] = {}
        candidates: List[Dict[str, Any]] = []

        for entity in entity_list:
            candidate = self._entity_candidate(entity)
            candidates.append(candidate)
            tier_by_uuid[entity.uuid] = candidate["recommended_importance_tier"]

        seen_relation_ids = set()
        for entity in entity_list:
            for edge in entity.related_edges:
                other_uuid = edge.get("target_node_uuid") or edge.get("source_node_uuid")
                if not other_uuid or other_uuid not in name_by_uuid:
                    continue
                candidate_id = relation_candidate_id(entity.uuid, other_uuid)
                if candidate_id in seen_relation_ids:
                    continue
                seen_relation_ids.add(candidate_id)
                source_uuid, target_uuid = sorted([entity.uuid, other_uuid])
                source = name_by_uuid[source_uuid]
                target = name_by_uuid[target_uuid]
                recommended = self.template_registry.max_tier([
                    tier_by_uuid.get(source_uuid, "supporting"),
                    tier_by_uuid.get(target_uuid, "supporting"),
                ])
                candidates.append(
                    self._relation_candidate(
                        source=source,
                        target=target,
                        source_uuid=source_uuid,
                        target_uuid=target_uuid,
                        relation_type=edge.get("edge_name", "related_to"),
                        summary=edge.get("fact") or f"{source} 与 {target} 之间存在关系",
                        recommended_tier=recommended,
                        source_kind="graph_edges",
                    )
                )
        return candidates

    def _seed_candidate(self, item: Dict[str, Any], entity_type: str, agent_kind: str, summary: str) -> Dict[str, Any]:
        name = str(item.get("name") or "").strip()
        entity_uuid = f"seed_{agent_kind}_{name}"
        return self._candidate_payload(
            entity_uuid=entity_uuid,
            display_name=name,
            entity_type=entity_type,
            agent_kind=agent_kind,
            recommended_tier=item.get("importance_tier", "supporting"),
            summary=summary or f"{name} 可生成为 {agent_kind} 档案",
            source_payload=dict(item),
            source_kind="seed_analysis",
        )

    def _entity_candidate(self, entity: EntityNode) -> Dict[str, Any]:
        entity_type = entity.get_entity_type() or "Unknown"
        agent_kind = self._infer_agent_kind(entity_type)
        recommended = entity.attributes.get("importance_tier", "supporting")
        return self._candidate_payload(
            entity_uuid=entity.uuid,
            display_name=entity.name,
            entity_type=entity_type,
            agent_kind=agent_kind,
            recommended_tier=recommended,
            summary=entity.summary or f"{entity.name} 可生成为 {agent_kind} 档案",
            source_payload=entity.to_dict(),
            source_kind="graph_entities",
        )

    def _relation_candidate(
        self,
        source: str,
        target: str,
        source_uuid: str,
        target_uuid: str,
        relation_type: str,
        summary: str,
        recommended_tier: str,
        source_kind: str,
    ) -> Dict[str, Any]:
        entity_uuid = relation_candidate_id(source_uuid, target_uuid)
        return self._candidate_payload(
            entity_uuid=entity_uuid,
            display_name=relation_display_name(source, target),
            entity_type="Relationship",
            agent_kind="relationship",
            recommended_tier=recommended_tier,
            summary=summary,
            source_payload={
                "source": source,
                "target": target,
                "source_uuid": source_uuid,
                "target_uuid": target_uuid,
                "relation_type": relation_type,
            },
            source_kind=source_kind,
        )

    def _candidate_payload(
        self,
        entity_uuid: str,
        display_name: str,
        entity_type: str,
        agent_kind: str,
        recommended_tier: str,
        summary: str,
        source_payload: Dict[str, Any],
        source_kind: str,
    ) -> Dict[str, Any]:
        template = self.template_registry.describe(agent_kind, recommended_tier)
        return {
            "candidate_id": entity_uuid,
            "entity_uuid": entity_uuid,
            "display_name": display_name,
            "entity_type": entity_type,
            "agent_kind": template["agent_kind"],
            "recommended_importance_tier": template["importance_tier"],
            "selected_importance_tier": template["importance_tier"],
            "template_key": template["template_key"],
            "template_version": template["template_version"],
            "template_sections": template["template_sections"],
            "summary": summary or display_name,
            "source_payload": source_payload,
            "source_kind": source_kind,
        }

    def _infer_agent_kind(self, entity_type: str) -> str:
        lowered = str(entity_type or "").lower()
        if any(keyword in lowered for keyword in ORGANIZATION_KEYWORDS):
            return "organization"
        if any(keyword in lowered for keyword in CHARACTER_KEYWORDS):
            return "character"
        return "generic"
