"""图谱实体类型默认值。"""

from typing import List, Optional


DEFAULT_GRAPH_ENTITY_TYPES = ["Character", "Organization", "Faction"]


def graph_entity_types(entity_types: Optional[List[str]], graph_id: Optional[str]) -> Optional[List[str]]:
    if entity_types:
        return entity_types
    if graph_id:
        return list(DEFAULT_GRAPH_ENTITY_TYPES)
    return None
