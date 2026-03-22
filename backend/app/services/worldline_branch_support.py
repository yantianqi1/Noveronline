"""世界线分支服务辅助函数。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models.worldline import WorldlineBranch


INTENSITY_DEPTH_MAP = {"low": 1, "medium": 3}


def build_branch_states(
    states: Dict[str, Dict[str, Any]],
    branch_id: str,
    session_scope: str,
    graph_id: str,
) -> Dict[str, Dict[str, Any]]:
    return {
        name: {
            **dict(state),
            "branch_id": branch_id,
            "session_scope": session_scope,
            "graph_id": graph_id,
            "last_event": state.get("last_event", "seed"),
        }
        for name, state in states.items()
    }


def build_relation_states(agent_registry, branch: WorldlineBranch, relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = []
    for relation in relationships:
        source = relation.get("source", "")
        target = relation.get("target", "")
        if not source or not target:
            continue
        items.append(
            {
                **dict(relation),
                "source_agent_id": agent_registry.relation_endpoint_agent_id(branch, source),
                "target_agent_id": agent_registry.relation_endpoint_agent_id(branch, target),
                "state_source": relation.get("state_source", "session_bootstrap"),
                "status": relation.get("status", "active"),
                "last_event": relation.get("last_event", "seed"),
            }
        )
    return items


def resolve_evolution_depth(
    branch: WorldlineBranch,
    evolution_intensity: str,
    custom_depth: Optional[int],
) -> int:
    if custom_depth is not None:
        if custom_depth < 1:
            raise ValueError("custom_depth 必须大于 0")
        return custom_depth
    if evolution_intensity == "high":
        return max(1, len(branch.actor_states) + len(branch.organization_states))
    if evolution_intensity not in {"low", "medium", "high"}:
        raise ValueError("evolution_intensity 必须是 low、medium 或 high")
    return INTENSITY_DEPTH_MAP.get(evolution_intensity, 3)


def record_state_change(
    changes: Dict[str, Dict[str, Any]],
    agent_registry,
    branch: WorldlineBranch,
    next_step: int,
    entity_name: str,
    reason: str,
    latest_action: str,
    influence: float,
    hops: int,
) -> None:
    state = branch.actor_states.get(entity_name) or branch.organization_states.get(entity_name)
    if not state:
        state = agent_registry.find_relation_state(branch.relationship_states, entity_name)
    if not state:
        return
    state["last_event"] = f"step_{next_step}"
    if latest_action and (hops == 0 or "last_action" not in state):
        state["last_action"] = latest_action
    state["status"] = "engaged" if hops <= 1 else "adjusting"
    rounded_influence = round(influence, 3)
    recorded = changes.get(entity_name)
    if recorded and recorded["influence"] >= rounded_influence:
        return
    changes[entity_name] = {
        "entity": entity_name,
        "status": state["status"],
        "reason": reason,
        "influence": rounded_influence,
        "hops": hops,
    }
