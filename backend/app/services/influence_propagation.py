"""世界线影响力传导模型。"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Sequence


IMPORTANCE_TIER_WEIGHTS = {
    "protagonist": 1.0,
    "major": 0.7,
    "supporting": 0.4,
    "minor": 0.15,
}
RELATION_PROPAGATION_DECAY = 0.5
MIN_INFLUENCE_THRESHOLD = 0.1


class InfluencePropagationModel:
    """在关系图上按层传播动作影响。"""

    def propagate(
        self,
        actor_name: str,
        action_weight: float,
        actor_states: Dict,
        organization_states: Dict,
        relationship_states: Sequence[Dict],
        max_depth: int = 3,
    ) -> List[Dict]:
        adjacency = self._build_adjacency(relationship_states)
        result = {}
        visited = {}
        queue = deque((seed, 0) for seed in self._seed_entities(actor_name, relationship_states))
        while queue:
            entity, depth = queue.popleft()
            if entity in visited and visited[entity] <= depth:
                continue
            visited[entity] = depth
            influence = self._influence(entity, action_weight, depth, actor_states, organization_states)
            if influence >= MIN_INFLUENCE_THRESHOLD:
                result[entity] = {
                    "entity": entity,
                    "entity_type": self._entity_type(entity, actor_states, organization_states),
                    "influence": round(influence, 3),
                    "hops": depth,
                }
            if depth >= max_depth:
                continue
            for neighbor in adjacency.get(entity, []):
                queue.append((neighbor, depth + 1))
        return sorted(result.values(), key=lambda item: (-item["influence"], item["hops"], item["entity"]))

    def _build_adjacency(self, relationship_states: Sequence[Dict]) -> Dict[str, set[str]]:
        adjacency: Dict[str, set[str]] = {}
        for item in relationship_states:
            source = item.get("source", "")
            target = item.get("target", "")
            if not source or not target:
                continue
            adjacency.setdefault(source, set()).add(target)
            adjacency.setdefault(target, set()).add(source)
        return adjacency

    def _seed_entities(self, actor_name: str, relationship_states: Sequence[Dict]) -> List[str]:
        direct = actor_name.strip()
        if not direct:
            return []
        seeds = [direct]
        for item in relationship_states:
            display_name = f"{item.get('source', '')} × {item.get('target', '')}"
            if display_name != direct:
                continue
            seeds = [item.get("source", ""), item.get("target", "")]
            break
        return [item for item in seeds if item]

    def _influence(
        self,
        entity: str,
        action_weight: float,
        depth: int,
        actor_states: Dict,
        organization_states: Dict,
    ) -> float:
        state = actor_states.get(entity) or organization_states.get(entity) or {}
        tier = state.get("importance_tier", "supporting")
        base_weight = IMPORTANCE_TIER_WEIGHTS.get(tier, IMPORTANCE_TIER_WEIGHTS["supporting"])
        return base_weight * action_weight * (RELATION_PROPAGATION_DECAY ** depth)

    def _entity_type(self, entity: str, actor_states: Dict, organization_states: Dict) -> str:
        if entity in actor_states:
            return "character"
        if entity in organization_states:
            return "organization"
        return "unknown"
