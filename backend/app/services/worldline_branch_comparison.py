"""
世界线分支对比摘要服务
"""

from typing import Any, Dict, List, Optional


ACTION_PREVIEW_LIMIT = 3
RELATION_PREVIEW_LIMIT = 3
STATE_PREVIEW_LIMIT = 3
VARIABLE_PREVIEW_LIMIT = 3


class WorldlineBranchComparisonService:
    def build(self, session, branch_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        branches = self._select_branches(session.branches, branch_ids or [])
        return {
            "session_id": session.session_id,
            "project_id": session.project_id,
            "graph_id": session.graph_id,
            "comparison_axes": self._comparison_axes(session, branches),
            "branches": [self._branch_card(branch) for branch in branches],
        }

    def _select_branches(self, branches, branch_ids: List[str]):
        if not branch_ids:
            return list(branches)
        mapping = {branch.branch_id: branch for branch in branches}
        missing = [branch_id for branch_id in branch_ids if branch_id not in mapping]
        if missing:
            raise LookupError(f"分支不存在: {', '.join(missing)}")
        return [mapping[branch_id] for branch_id in dict.fromkeys(branch_ids)]

    def _comparison_axes(self, session, branches) -> Dict[str, Any]:
        return {
            "focus_question": session.focus_question,
            "branch_count": len(branches),
            "selected_branch_ids": [branch.branch_id for branch in branches],
            "shared_variables": [item.name for item in session.world_variables],
        }

    def _branch_card(self, branch) -> Dict[str, Any]:
        return {
            "branch_id": branch.branch_id,
            "title": branch.title,
            "core_change": branch.core_change,
            "current_step": branch.current_step,
            "status": branch.status,
            "key_agents": list(branch.key_agents),
            "latest_event": self._latest_event(branch),
            "key_actor_states": self._state_cards(branch, branch.actor_states),
            "key_organization_states": self._state_cards(branch, branch.organization_states),
            "relation_highlights": self._relation_highlights(branch),
            "pending": self._pending_summary(branch),
        }

    def _latest_event(self, branch) -> Optional[Dict[str, Any]]:
        if not branch.timeline:
            return None
        latest = branch.timeline[-1]
        return {
            "event_id": latest.event_id,
            "step": latest.step,
            "title": latest.title,
            "summary": latest.summary,
            "event_type": latest.event_type,
            "driving_entities": list(latest.driving_entities),
        }

    def _state_cards(self, branch, states: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        names = self._prioritized_state_names(branch, states)
        return [self._state_card(name, states[name]) for name in names[:STATE_PREVIEW_LIMIT]]

    def _prioritized_state_names(self, branch, states: Dict[str, Dict[str, Any]]) -> List[str]:
        names: List[str] = []
        latest_event = branch.timeline[-1] if branch.timeline else None
        for name in list(branch.key_agents) + list(latest_event.driving_entities if latest_event else []):
            if name in states and name not in names:
                names.append(name)
        for name in states.keys():
            if name not in names:
                names.append(name)
        return names

    def _state_card(self, name: str, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": name,
            "status": state.get("status", "active"),
            "role": state.get("role") or state.get("entity_role") or "unknown",
            "drive": state.get("drive") or state.get("core_drive") or "围绕当前目标持续行动",
            "tension": state.get("tension") or state.get("hidden_tension") or "局势仍在变化中",
            "last_action": state.get("last_action", ""),
            "last_event": state.get("last_event", ""),
        }

    def _relation_highlights(self, branch) -> List[Dict[str, Any]]:
        latest_event = branch.timeline[-1] if branch.timeline else None
        changes = list(latest_event.relation_changes) if latest_event and latest_event.relation_changes else []
        if not changes:
            changes = list(branch.relationship_states[-RELATION_PREVIEW_LIMIT:])
        return [self._relation_card(item) for item in changes if item.get("source") and item.get("target")]

    def _relation_card(self, relation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "source": relation.get("source", ""),
            "target": relation.get("target", ""),
            "change": relation.get("change", "stable"),
            "note": relation.get("note", ""),
            "status": relation.get("status", "active"),
            "last_action": relation.get("last_action", ""),
        }

    def _pending_summary(self, branch) -> Dict[str, Any]:
        return {
            "variable_count": len(branch.pending_variables),
            "action_count": len(branch.pending_actions),
            "variable_names": [item.name for item in branch.pending_variables[:VARIABLE_PREVIEW_LIMIT]],
            "action_labels": [
                f"{item.actor}:{item.action}" for item in branch.pending_actions[:ACTION_PREVIEW_LIMIT]
            ],
        }
