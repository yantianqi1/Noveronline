"""
世界线分支构建与推进服务
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..models.worldline import VariableInjection, WorldEvent, WorldlineBranch, WorldlineSession
from .influence_propagation import InfluencePropagationModel
from .worldline_branch_support import (
    build_branch_states,
    build_relation_states,
    record_state_change,
    resolve_evolution_depth,
)
from .worldline_agent_registry import WorldlineAgentRegistry
from .worldline_single_world import MAIN_WORLD_BRANCH_ID, MAIN_WORLD_TITLE

MAX_VARIABLES_PER_STEP = 3
MAX_ACTIONS_PER_STEP = 2


class WorldlineBranchService:
    def __init__(
        self,
        agent_registry: Optional[WorldlineAgentRegistry] = None,
        influence_model: Optional[InfluencePropagationModel] = None,
    ):
        self.agent_registry = agent_registry or WorldlineAgentRegistry()
        self.influence_model = influence_model or InfluencePropagationModel()

    def build_branches(
        self,
        branch_count: int,
        source: Dict[str, Any],
        focus_question: str,
        world_variables: List[VariableInjection],
    ) -> List[WorldlineBranch]:
        hypotheses = (source.get("config") or {}).get("branch_hypotheses", [])
        branch = self._build_branch(0, hypotheses, source, focus_question, world_variables)
        return [branch]

    def advance_branch(
        self,
        branch: WorldlineBranch,
        session: WorldlineSession,
        evolution_intensity: str = "medium",
        custom_depth: Optional[int] = None,
    ) -> Dict[str, Any]:
        next_step = branch.current_step + 1
        depth = resolve_evolution_depth(branch, evolution_intensity, custom_depth)
        consumed_variables = branch.pending_variables[:MAX_VARIABLES_PER_STEP]
        consumed_actions = branch.pending_actions[:MAX_ACTIONS_PER_STEP]
        branch.pending_variables = branch.pending_variables[MAX_VARIABLES_PER_STEP:]
        branch.pending_actions = branch.pending_actions[MAX_ACTIONS_PER_STEP:]
        branch.evolution_intensity = evolution_intensity
        branch.evolution_depth = depth

        drivers = self._drivers(branch, consumed_actions)
        state_changes = self._apply_state_changes(
            branch,
            next_step,
            drivers,
            consumed_variables,
            consumed_actions,
            depth,
        )
        relation_changes = self._relation_changes(branch, drivers, consumed_variables, consumed_actions)
        branch.timeline.append(
            WorldEvent(
                event_id=f"evt_{uuid.uuid4().hex[:10]}",
                step=next_step,
                title=f"{branch.title} · 第{next_step}步演化",
                summary=self._summary(session.focus_question, consumed_variables, consumed_actions),
                event_type="evolution",
                driving_entities=drivers,
                variable_effects=[item.to_dict() for item in consumed_variables],
                action_effects=[item.to_dict() for item in consumed_actions],
                relation_changes=relation_changes,
                state_changes=state_changes,
            )
        )
        branch.current_step = next_step
        branch.updated_at = datetime.now().isoformat()
        return {
            "consumed_variables": consumed_variables,
            "consumed_actions": consumed_actions,
            "state_changes": state_changes,
            "relation_changes": relation_changes,
        }

    def normalize_variables(self, variables: List[Any]) -> List[VariableInjection]:
        result: List[VariableInjection] = []
        for idx, item in enumerate(variables):
            if isinstance(item, str):
                text = item.strip()
                if not text:
                    continue
                result.append(self._variable(name=text[:40], description=text))
                continue
            name = str(item.get("name", "")).strip() or f"变量{idx + 1}"
            result.append(
                self._variable(
                    name=name,
                    description=str(item.get("description", "")).strip() or "未提供描述",
                    impact_axis=str(item.get("impact_axis", "")).strip(),
                )
            )
        return result

    def default_core_change(self, idx: int, variables: List[VariableInjection]) -> str:
        if not variables:
            return "关键角色的决策窗口提前触发，导致关系网络重新排序"
        return f"{variables[idx % len(variables)].name} 在关键节点被放大，引发因果链重排"

    def _build_branch(
        self,
        idx: int,
        hypotheses: List[Dict[str, Any]],
        source: Dict[str, Any],
        focus_question: str,
        world_variables: List[VariableInjection],
    ) -> WorldlineBranch:
        hypothesis = hypotheses[idx] if idx < len(hypotheses) else {}
        key_agents = list(hypothesis.get("key_agents", [])) or list(source.get("actors", {}).keys())[:3]
        branch = WorldlineBranch(
            branch_id=MAIN_WORLD_BRANCH_ID,
            title=MAIN_WORLD_TITLE,
            core_change=hypothesis.get("core_change") or self.default_core_change(idx, world_variables),
            narrative_value=hypothesis.get("narrative_value") or f"检验问题：{focus_question}",
            key_agents=key_agents,
            expected_conflicts=list(hypothesis.get("expected_conflicts", [])),
            actor_states=build_branch_states(
                source.get("actors", {}),
                MAIN_WORLD_BRANCH_ID,
                source.get("session_scope", "project"),
                source.get("graph_id", ""),
            ),
            organization_states=build_branch_states(
                source.get("organizations", {}),
                MAIN_WORLD_BRANCH_ID,
                source.get("session_scope", "project"),
                source.get("graph_id", ""),
            ),
            relationship_states=[],
            evolution_intensity="medium",
            evolution_depth=3,
        )
        branch.relationship_states = build_relation_states(self.agent_registry, branch, source.get("relationships", []))
        branch.timeline.append(self._seed_event(branch, key_agents, world_variables))
        branch.pending_variables.extend(world_variables)
        return branch

    def _seed_event(
        self,
        branch: WorldlineBranch,
        key_agents: List[str],
        world_variables: List[VariableInjection],
    ) -> WorldEvent:
        return WorldEvent(
            event_id=f"evt_{uuid.uuid4().hex[:10]}",
            step=0,
            title=f"{branch.title} 初始化",
            summary=f"以“{branch.core_change}”为核心偏移创建分支，准备进入推演。",
            event_type="seed",
            driving_entities=key_agents[:5],
            variable_effects=[item.to_dict() for item in world_variables],
            relation_changes=[],
            state_changes=[],
        )

    def _drivers(self, branch: WorldlineBranch, consumed_actions: List[Any]) -> List[str]:
        if consumed_actions:
            action_drivers = [item.actor for item in consumed_actions if item.actor]
            if action_drivers:
                return action_drivers
        return list(branch.actor_states.keys())[:2] or branch.key_agents[:2]

    def _apply_state_changes(
        self,
        branch: WorldlineBranch,
        next_step: int,
        drivers: List[str],
        consumed_variables: List[Any],
        consumed_actions: List[Any],
        evolution_depth: int,
    ) -> List[Dict[str, Any]]:
        changes: Dict[str, Dict[str, Any]] = {}
        reason = "manual_action" if consumed_actions else "variable_shift" if consumed_variables else "inertia"
        for action in consumed_actions:
            record_state_change(changes, self.agent_registry, branch, next_step, action.actor, reason, action.action, 1.0, 0)
            for affected in self.influence_model.propagate(
                actor_name=action.actor,
                action_weight=1.0,
                actor_states=branch.actor_states,
                organization_states=branch.organization_states,
                relationship_states=branch.relationship_states,
                max_depth=evolution_depth,
            ):
                record_state_change(
                    changes,
                    self.agent_registry,
                    branch,
                    next_step,
                    affected["entity"],
                    reason,
                    action.action,
                    affected["influence"],
                    affected["hops"],
                )
        if changes:
            return list(changes.values())
        for name in drivers[:3]:
            latest_action = next((item.action for item in consumed_actions if item.actor == name and item.action), "")
            record_state_change(changes, self.agent_registry, branch, next_step, name, reason, latest_action, 1.0, 0)
        return list(changes.values())

    def _relation_changes(
        self,
        branch: WorldlineBranch,
        drivers: List[str],
        consumed_variables: List[Any],
        consumed_actions: List[Any],
    ) -> List[Dict[str, Any]]:
        relation_action_changes = []
        for action in consumed_actions:
            relation = self.agent_registry.find_relation_state(branch.relationship_states, action.actor)
            if not relation:
                continue
            relation["change"] = "relationship_shift"
            relation["note"] = f"关系 agent 执行动作：{action.action}"
            relation_action_changes.append(dict(relation))
        if relation_action_changes:
            return relation_action_changes
        if len(drivers) < 2:
            return []
        relation = {
            "source": drivers[0],
            "target": drivers[1],
            "change": "tension_up" if (consumed_actions or consumed_variables) else "stable",
            "note": "变量或动作改变了互动强度",
        }
        branch.relationship_states.append(dict(relation))
        return [relation]

    def _summary(
        self,
        focus_question: str,
        consumed_variables: List[Any],
        consumed_actions: List[Any],
    ) -> str:
        parts = []
        if consumed_variables:
            parts.append("变量触发 " + "；".join(f"{item.name}:{item.description}" for item in consumed_variables))
        if consumed_actions:
            parts.append("主动行动 " + "；".join(f"{item.actor}执行“{item.action}”" for item in consumed_actions))
        if not parts:
            parts.append("系统按既有动机与关系惯性推进情节")
        parts.append(f"本轮围绕“{focus_question}”持续收敛。")
        return "；".join(parts)

    def _variable(self, name: str, description: str, impact_axis: str = "") -> VariableInjection:
        return VariableInjection(
            variable_id=f"var_{uuid.uuid4().hex[:10]}",
            name=name,
            description=description,
            impact_axis=impact_axis,
            source="seed",
        )
