"""Graph entity type defaults for native FastAPI routes."""

from typing import Optional

DEFAULT_GRAPH_ENTITY_TYPES = ["Character", "Organization", "Faction"]


def graph_entity_types(entity_types: Optional[list[str]], graph_id: Optional[str]) -> Optional[list[str]]:
    if entity_types:
        return entity_types
    if graph_id:
        return list(DEFAULT_GRAPH_ENTITY_TYPES)
    return None
