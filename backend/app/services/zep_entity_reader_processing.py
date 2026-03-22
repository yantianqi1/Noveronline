"""本地图谱实体筛选与上下文构造逻辑。"""

from typing import Dict, Any, List, Optional, Set, Tuple

from ..utils.logger import get_logger
from .zep_entity_reader_types import EntityNode, FilteredEntities

logger = get_logger("mirofish.local_graph_reader.processing")


def build_node_map(all_nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {node["uuid"]: node for node in all_nodes}


def collect_related_edges(
    node_uuid: str,
    all_edges: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    related_edges: List[Dict[str, Any]] = []
    related_node_uuids: Set[str] = set()

    for edge in all_edges:
        if edge["source_node_uuid"] == node_uuid:
            related_edges.append({
                "direction": "outgoing",
                "edge_name": edge["name"],
                "fact": edge["fact"],
                "target_node_uuid": edge["target_node_uuid"],
            })
            related_node_uuids.add(edge["target_node_uuid"])
        elif edge["target_node_uuid"] == node_uuid:
            related_edges.append({
                "direction": "incoming",
                "edge_name": edge["name"],
                "fact": edge["fact"],
                "source_node_uuid": edge["source_node_uuid"],
            })
            related_node_uuids.add(edge["source_node_uuid"])

    return related_edges, related_node_uuids


def build_related_nodes(
    related_node_uuids: Set[str], node_map: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    related_nodes = []
    for related_uuid in related_node_uuids:
        related_node = node_map.get(related_uuid)
        if not related_node:
            continue
        related_nodes.append({
            "uuid": related_node["uuid"],
            "name": related_node["name"],
            "labels": related_node["labels"],
            "summary": related_node.get("summary", ""),
        })
    return related_nodes


def determine_entity_type(
    labels: List[str],
    defined_entity_types: Optional[List[str]],
) -> Optional[str]:
    custom_labels = [label for label in labels if label not in ["Entity", "Node"]]
    if not custom_labels:
        return None
    if defined_entity_types:
        matching = [label for label in custom_labels if label in defined_entity_types]
        return matching[0] if matching else None
    return custom_labels[0]


def filter_entities(
    all_nodes: List[Dict[str, Any]],
    all_edges: List[Dict[str, Any]],
    defined_entity_types: Optional[List[str]],
    enrich_with_edges: bool,
) -> FilteredEntities:
    total_count = len(all_nodes)
    node_map = build_node_map(all_nodes)
    filtered_entities: List[EntityNode] = []
    entity_types_found: Set[str] = set()

    for node in all_nodes:
        entity_type = determine_entity_type(node.get("labels", []), defined_entity_types)
        if not entity_type:
            continue

        entity_types_found.add(entity_type)
        entity = EntityNode(
            uuid=node["uuid"],
            name=node["name"],
            labels=node["labels"],
            summary=node["summary"],
            attributes=node["attributes"],
        )

        if enrich_with_edges:
            related_edges, related_node_uuids = collect_related_edges(node["uuid"], all_edges)
            entity.related_edges = related_edges
            entity.related_nodes = build_related_nodes(related_node_uuids, node_map)

        filtered_entities.append(entity)

    logger.info(
        "筛选完成",
        extra={
            "total_nodes": total_count,
            "filtered_count": len(filtered_entities),
            "entity_types": list(entity_types_found),
        },
    )

    return FilteredEntities(
        entities=filtered_entities,
        entity_types=entity_types_found,
        total_count=total_count,
        filtered_count=len(filtered_entities),
    )


def build_entity_context(
    node: Any,
    edges: List[Dict[str, Any]],
    node_map: Dict[str, Dict[str, Any]],
) -> EntityNode:
    related_edges, related_node_uuids = collect_related_edges(node.uuid_ or node.uuid, edges)
    related_nodes = build_related_nodes(related_node_uuids, node_map)
    return EntityNode(
        uuid=getattr(node, "uuid_", None) or getattr(node, "uuid", ""),
        name=getattr(node, "name", ""),
        labels=getattr(node, "labels", []) or [],
        summary=getattr(node, "summary", "") or "",
        attributes=getattr(node, "attributes", {}) or {},
        related_edges=related_edges,
        related_nodes=related_nodes,
    )
