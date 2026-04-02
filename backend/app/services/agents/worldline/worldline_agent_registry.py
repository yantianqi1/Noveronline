"""
世界线 agent 名册服务
"""

from collections import Counter
import hashlib
from typing import Any, Dict, List, Optional

from ..registry import AgentSchemaRegistry
from ..registry import AgentTemplateRegistry
from ...genre_plugin import resolve_genre_plugin

CHARACTER_KIND = "character"
ORGANIZATION_KIND = "organization"
RELATIONSHIP_KIND = "relationship"

KIND_ROLE_TEXT = {
    CHARACTER_KIND: "角色",
    ORGANIZATION_KIND: "组织",
    RELATIONSHIP_KIND: "关系推动者",
}


def relation_display_name(source: str, target: str) -> str:
    return f"{source} × {target}"


def relation_agent_id(source_agent_id: str, target_agent_id: str) -> str:
    return f"relation::{source_agent_id}::{target_agent_id}"


def _stable_hash(*parts: str) -> str:
    joined = "::".join(parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def relation_change_text(change: str) -> str:
    mapping = {
        "stable": "稳定",
        "tension_up": "张力上升",
        "relationship_shift": "关系转变",
    }
    return mapping.get(change, "变化中")


class WorldlineAgentRegistry:
    def __init__(
        self,
        schema_registry: Optional[AgentSchemaRegistry] = None,
        template_registry: Optional[AgentTemplateRegistry] = None,
        genre: str = "default",
    ):
        self.schema_registry = schema_registry or AgentSchemaRegistry()
        self.template_registry = template_registry or AgentTemplateRegistry()
        resolve_genre_plugin(genre).customize_agent_schema(self.schema_registry)

    def list_agents(self, branch) -> List[Dict[str, Any]]:
        agents = []
        agents.extend(self._state_agents(branch.actor_states, CHARACTER_KIND))
        agents.extend(self._state_agents(branch.organization_states, ORGANIZATION_KIND))
        agents.extend(self._relation_agents(branch.relationship_states))
        return agents

    def count_by_kind(self, agents: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = Counter(item["agent_kind"] for item in agents)
        return {
            CHARACTER_KIND: counts.get(CHARACTER_KIND, 0),
            ORGANIZATION_KIND: counts.get(ORGANIZATION_KIND, 0),
            RELATIONSHIP_KIND: counts.get(RELATIONSHIP_KIND, 0),
        }

    def resolve_agent(self, branch, agent_ref: str) -> Optional[Dict[str, Any]]:
        text = (agent_ref or "").strip()
        if not text:
            return None
        for agent in self.list_agents(branch):
            if text in {agent["agent_id"], agent["display_name"], agent["source_ref"]}:
                return agent
        return None

    def find_relation_state(self, relationship_states: List[Dict[str, Any]], agent_name: str) -> Optional[Dict[str, Any]]:
        for item in reversed(relationship_states):
            if relation_display_name(item.get("source", ""), item.get("target", "")) == agent_name:
                return item
        return None

    def relation_endpoint_agent_id(self, branch, name: str) -> str:
        for candidate in self._state_agents(branch.actor_states, CHARACTER_KIND) + self._state_agents(
            branch.organization_states,
            ORGANIZATION_KIND,
        ):
            if candidate["display_name"] == name:
                return candidate["agent_id"]
        return f"entity_fallback_{_stable_hash(name)}"

    def relation_agent_id_from_names(self, branch, source: str, target: str) -> str:
        return relation_agent_id(
            self.relation_endpoint_agent_id(branch, source),
            self.relation_endpoint_agent_id(branch, target),
        )

    def _state_agents(self, states: Dict[str, Dict[str, Any]], agent_kind: str) -> List[Dict[str, Any]]:
        agents = []
        for name, state in states.items():
            resolved_kind = state.get("agent_kind") or agent_kind
            template = self._template_for_state(resolved_kind, state)
            schema = self.schema_registry.get_schema(resolved_kind)
            agents.append({
                "agent_id": self._state_agent_id(name, state, resolved_kind),
                "agent_kind": resolved_kind,
                "display_name": name,
                "source_ref": name,
                "role": state.get("role") or state.get("entity_role") or KIND_ROLE_TEXT.get(resolved_kind, "对象"),
                "drive": state.get("drive") or state.get("core_drive") or "围绕当前目标持续行动",
                "tension": state.get("tension") or state.get("hidden_tension") or "局势仍在变化中",
                "status": state.get("status", "active"),
                "summary": self._state_summary(name, state),
                "schema": schema,
                "validation_errors": self.schema_registry.validate_state(resolved_kind, state),
                "can_chat": True,
                "can_act": True,
                "state_source": state.get("state_source", "session_bootstrap"),
                "source_archive_id": state.get("archive_id"),
                "source_entity_uuid": state.get("entity_uuid"),
                "importance_tier": template["importance_tier"],
                "template_key": template["template_key"],
                "template_version": template["template_version"],
                "template_sections": template["template_sections"],
                "state": state,
            })
        return agents

    def _relation_agents(self, relationship_states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: Dict[str, Dict[str, Any]] = {}
        for item in relationship_states:
            source = item.get("source", "")
            target = item.get("target", "")
            if not source or not target:
                continue
            source_agent_id = item.get("source_agent_id") or f"entity_fallback_{_stable_hash(source)}"
            target_agent_id = item.get("target_agent_id") or f"entity_fallback_{_stable_hash(target)}"
            agent_id = relation_agent_id(source_agent_id, target_agent_id)
            display_name = relation_display_name(source, target)
            change = item.get("change", "stable")
            importance_tier = self._relation_tier(item)
            template = self.template_registry.describe(RELATIONSHIP_KIND, importance_tier)
            relationship_payload = dict((item.get("template_payload") or {}).get("relationship") or {})
            state = {
                "role": KIND_ROLE_TEXT[RELATIONSHIP_KIND],
                "drive": f"推动或稳住“{source}”与“{target}”之间的关系走势",
                "tension": item.get("note") or "双方关系仍可能继续偏移",
                "status": item.get("status", "active"),
                "change": change,
                "source": source,
                "target": target,
                "source_agent_id": source_agent_id,
                "target_agent_id": target_agent_id,
                "importance_tier": template["importance_tier"],
                "template_key": item.get("template_key") or template["template_key"],
                "template_version": item.get("template_version") or template["template_version"],
                "template_sections": list(item.get("template_sections") or template["template_sections"]),
                "template_payload": item.get("template_payload") or {
                    "identity": {"entity_name": display_name, "role": KIND_ROLE_TEXT[RELATIONSHIP_KIND]},
                    "relationship": {
                        "source": source,
                        "target": target,
                        "change": change,
                        "summary": f"{source} 与 {target} 当前关系变化：{relation_change_text(change)}",
                    },
                    "state": {"status": item.get("status", "active")},
                },
                "state_source": item.get("state_source", "session_bootstrap"),
                "history": item.get("history") or relationship_payload.get("history", ""),
                "power_dynamic": item.get("power_dynamic") or relationship_payload.get("power_dynamic", ""),
                "trust_level": item.get("trust_level") or relationship_payload.get("trust_level", ""),
                "conflict_trigger": item.get("conflict_trigger") or relationship_payload.get("conflict_trigger", ""),
                "stability_forecast": item.get("stability_forecast") or relationship_payload.get("stability_forecast", ""),
                "last_action": item.get("last_action") or relationship_payload.get("last_action", ""),
            }
            deduped[agent_id] = {
                "agent_id": agent_id,
                "agent_kind": RELATIONSHIP_KIND,
                "display_name": display_name,
                "source_ref": f"{source}->{target}",
                "role": KIND_ROLE_TEXT[RELATIONSHIP_KIND],
                "drive": f"推动或稳住“{source}”与“{target}”之间的关系走势",
                "tension": item.get("note") or "双方关系仍可能继续偏移",
                "status": item.get("status", "active"),
                "summary": f"{source} 与 {target} 当前关系变化：{relation_change_text(change)}",
                "schema": self.schema_registry.get_schema(RELATIONSHIP_KIND),
                "validation_errors": self.schema_registry.validate_state(RELATIONSHIP_KIND, state),
                "can_chat": True,
                "can_act": True,
                "state_source": item.get("state_source", "session_bootstrap"),
                "importance_tier": template["importance_tier"],
                "template_key": state["template_key"],
                "template_version": state["template_version"],
                "template_sections": state["template_sections"],
                "state": state,
            }
        return list(deduped.values())

    def _state_summary(self, name: str, state: Dict[str, Any]) -> str:
        drive = state.get("drive") or state.get("core_drive") or "目标未明"
        tension = state.get("tension") or state.get("hidden_tension") or "局势未明"
        return f"{name} 当前围绕“{drive}”行动，核心张力是“{tension}”。"

    def _state_agent_id(self, name: str, state: Dict[str, Any], agent_kind: str) -> str:
        archive_id = str(state.get("archive_id") or "").strip()
        if archive_id:
            return archive_id
        entity_uuid = str(state.get("entity_uuid") or "").strip()
        if entity_uuid:
            return entity_uuid
        graph_id = str(state.get("graph_id") or "")
        branch_id = str(state.get("branch_id") or "")
        session_scope = str(state.get("session_scope") or "")
        return f"{agent_kind}_{_stable_hash(session_scope, graph_id, branch_id, name)}"

    def _template_for_state(self, agent_kind: str, state: Dict[str, Any]) -> Dict[str, Any]:
        importance_tier = state.get("importance_tier", "supporting")
        if state.get("template_key") and state.get("template_sections"):
            return {
                "importance_tier": self.template_registry.normalize_tier(importance_tier),
                "template_key": state.get("template_key"),
                "template_version": state.get("template_version", "v1"),
                "template_sections": list(state.get("template_sections") or []),
            }
        return self.template_registry.describe(agent_kind, importance_tier)

    def _relation_tier(self, item: Dict[str, Any]) -> str:
        direct = str(item.get("importance_tier") or "").strip()
        if direct:
            return direct
        tiers = [item.get("source_importance_tier", ""), item.get("target_importance_tier", "")]
        return self.template_registry.max_tier(tiers)
