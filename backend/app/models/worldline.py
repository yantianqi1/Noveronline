"""
世界线演化数据模型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now().isoformat()


@dataclass
class VariableInjection:
    variable_id: str
    name: str
    description: str
    impact_axis: str = ""
    created_at: str = field(default_factory=_now_iso)
    source: str = "user"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variable_id": self.variable_id,
            "name": self.name,
            "description": self.description,
            "impact_axis": self.impact_axis,
            "created_at": self.created_at,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VariableInjection":
        return cls(
            variable_id=data.get("variable_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            impact_axis=data.get("impact_axis", ""),
            created_at=data.get("created_at", _now_iso()),
            source=data.get("source", "user"),
        )


@dataclass
class AgentAction:
    action_id: str
    agent_id: str
    actor: str
    action: str
    intent: str = ""
    target: str = ""
    created_at: str = field(default_factory=_now_iso)
    source: str = "user"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "agent_id": self.agent_id,
            "actor": self.actor,
            "action": self.action,
            "intent": self.intent,
            "target": self.target,
            "created_at": self.created_at,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentAction":
        return cls(
            action_id=data.get("action_id", ""),
            agent_id=data.get("agent_id", ""),
            actor=data.get("actor", ""),
            action=data.get("action", ""),
            intent=data.get("intent", ""),
            target=data.get("target", ""),
            created_at=data.get("created_at", _now_iso()),
            source=data.get("source", "user"),
        )


@dataclass
class WorldEvent:
    event_id: str
    step: int
    title: str
    summary: str
    event_type: str = "evolution"
    driving_entities: List[str] = field(default_factory=list)
    variable_effects: List[Dict[str, Any]] = field(default_factory=list)
    relation_changes: List[Dict[str, Any]] = field(default_factory=list)
    state_changes: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "step": self.step,
            "title": self.title,
            "summary": self.summary,
            "event_type": self.event_type,
            "driving_entities": self.driving_entities,
            "variable_effects": self.variable_effects,
            "relation_changes": self.relation_changes,
            "state_changes": self.state_changes,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldEvent":
        return cls(
            event_id=data.get("event_id", ""),
            step=data.get("step", 0),
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            event_type=data.get("event_type", "evolution"),
            driving_entities=list(data.get("driving_entities", [])),
            variable_effects=list(data.get("variable_effects", [])),
            relation_changes=list(data.get("relation_changes", [])),
            state_changes=list(data.get("state_changes", [])),
            created_at=data.get("created_at", _now_iso()),
        )


@dataclass
class WorldlineBranch:
    branch_id: str
    title: str
    core_change: str
    narrative_value: str = ""
    current_step: int = 0
    status: str = "running"
    key_agents: List[str] = field(default_factory=list)
    expected_conflicts: List[str] = field(default_factory=list)
    evolution_intensity: str = "medium"
    evolution_depth: int = 3
    actor_states: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    organization_states: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    relationship_states: List[Dict[str, Any]] = field(default_factory=list)
    timeline: List[WorldEvent] = field(default_factory=list)
    pending_variables: List[VariableInjection] = field(default_factory=list)
    pending_actions: List[AgentAction] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "title": self.title,
            "core_change": self.core_change,
            "narrative_value": self.narrative_value,
            "current_step": self.current_step,
            "status": self.status,
            "key_agents": self.key_agents,
            "expected_conflicts": self.expected_conflicts,
            "evolution_intensity": self.evolution_intensity,
            "evolution_depth": self.evolution_depth,
            "actor_states": self.actor_states,
            "organization_states": self.organization_states,
            "relationship_states": self.relationship_states,
            "timeline": [event.to_dict() for event in self.timeline],
            "pending_variables": [item.to_dict() for item in self.pending_variables],
            "pending_actions": [item.to_dict() for item in self.pending_actions],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldlineBranch":
        return cls(
            branch_id=data.get("branch_id", ""),
            title=data.get("title", ""),
            core_change=data.get("core_change", ""),
            narrative_value=data.get("narrative_value", ""),
            current_step=data.get("current_step", 0),
            status=data.get("status", "running"),
            key_agents=list(data.get("key_agents", [])),
            expected_conflicts=list(data.get("expected_conflicts", [])),
            evolution_intensity=data.get("evolution_intensity", "medium"),
            evolution_depth=data.get("evolution_depth", 3),
            actor_states=dict(data.get("actor_states", {})),
            organization_states=dict(data.get("organization_states", {})),
            relationship_states=list(data.get("relationship_states", [])),
            timeline=[WorldEvent.from_dict(item) for item in data.get("timeline", [])],
            pending_variables=[VariableInjection.from_dict(item) for item in data.get("pending_variables", [])],
            pending_actions=[AgentAction.from_dict(item) for item in data.get("pending_actions", [])],
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )


@dataclass
class WorldlineSession:
    session_id: str
    project_id: Optional[str]
    graph_id: str
    simulation_goal: str
    focus_question: str
    branch_count: int
    session_scope: str = "project"
    status: str = "running"
    branches: List[WorldlineBranch] = field(default_factory=list)
    world_variables: List[VariableInjection] = field(default_factory=list)
    timeline_focus: List[str] = field(default_factory=list)
    agent_behavior_axes: List[str] = field(default_factory=list)
    source_summary: Dict[str, Any] = field(default_factory=dict)
    source_archive_ids: List[str] = field(default_factory=list)
    source_project_ids: List[str] = field(default_factory=list)
    source_archive_count: int = 0
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_goal": self.simulation_goal,
            "focus_question": self.focus_question,
            "branch_count": self.branch_count,
            "session_scope": self.session_scope,
            "status": self.status,
            "branches": [branch.to_dict() for branch in self.branches],
            "world_variables": [item.to_dict() for item in self.world_variables],
            "timeline_focus": self.timeline_focus,
            "agent_behavior_axes": self.agent_behavior_axes,
            "source_summary": self.source_summary,
            "source_archive_ids": self.source_archive_ids,
            "source_project_ids": self.source_project_ids,
            "source_archive_count": self.source_archive_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldlineSession":
        return cls(
            session_id=data.get("session_id", ""),
            project_id=data.get("project_id"),
            graph_id=data.get("graph_id", ""),
            simulation_goal=data.get("simulation_goal", ""),
            focus_question=data.get("focus_question", ""),
            branch_count=data.get("branch_count", 0),
            session_scope=data.get("session_scope", "project"),
            status=data.get("status", "running"),
            branches=[WorldlineBranch.from_dict(item) for item in data.get("branches", [])],
            world_variables=[VariableInjection.from_dict(item) for item in data.get("world_variables", [])],
            timeline_focus=list(data.get("timeline_focus", [])),
            agent_behavior_axes=list(data.get("agent_behavior_axes", [])),
            source_summary=dict(data.get("source_summary", {})),
            source_archive_ids=list(data.get("source_archive_ids", [])),
            source_project_ids=list(data.get("source_project_ids", [])),
            source_archive_count=data.get("source_archive_count", 0),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )
