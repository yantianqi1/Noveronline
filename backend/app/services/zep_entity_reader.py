"""
本地图谱实体读取与过滤服务。

保留原有接口语义，供档案、平行世界和世界线链路继续复用。
"""

from typing import Dict, Any, List, Optional

from ..utils.logger import get_logger
from ..database import get_engine
from ..repositories.graph_repo import GraphRepository
from .local_story_graph_support import project_id_from_graph_id
from .zep_entity_reader_processing import build_entity_context, build_node_map, filter_entities
from .zep_entity_reader_types import EntityNode, FilteredEntities

logger = get_logger("mirofish.local_graph_reader")


class LocalGraphReader:
    def __init__(self, storage: Optional[GraphRepository] = None):
        self.storage = storage or GraphRepository(get_engine())

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        logger.info(f"读取本地图谱 {graph_id} 的所有节点...")
        project_id = project_id_from_graph_id(graph_id)
        return self.storage.load_all_nodes(project_id)

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        logger.info(f"读取本地图谱 {graph_id} 的所有边...")
        project_id = project_id_from_graph_id(graph_id)
        return self.storage.load_all_edges(project_id)

    def get_node_edges(self, node_uuid: str, graph_id: Optional[str] = None) -> List[Dict[str, Any]]:
        resolved_graph_id = graph_id or self._graph_id_from_node_uuid(node_uuid)
        project_id = project_id_from_graph_id(resolved_graph_id)
        return self.storage.load_node_edges(project_id, node_uuid)

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ) -> FilteredEntities:
        all_nodes = self.get_all_nodes(graph_id)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        return filter_entities(all_nodes, all_edges, defined_entity_types, enrich_with_edges)

    def get_entity_with_context(self, graph_id: str, entity_uuid: str) -> Optional[EntityNode]:
        project_id = project_id_from_graph_id(graph_id)
        node = self.storage.load_node(project_id, entity_uuid)
        if not node:
            return None
        edges = self.get_node_edges(entity_uuid, graph_id=graph_id)
        node_map = build_node_map(self.get_all_nodes(graph_id))
        raw_node = _LocalNode(node)
        return build_entity_context(raw_node, edges, node_map)

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True,
    ) -> List[EntityNode]:
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges,
        )
        return result.entities

    def _graph_id_from_node_uuid(self, node_uuid: str) -> str:
        parts = str(node_uuid or "").split("::")
        if len(parts) < 3:
            raise ValueError(f"无法从节点ID解析 graph_id: {node_uuid}")
        return f"local_graph_{project_id_from_graph_id(parts[1])}"


class _LocalNode:
    def __init__(self, payload: Dict[str, Any]):
        self.uuid_ = payload.get("uuid", "")
        self.uuid = self.uuid_
        self.name = payload.get("name", "")
        self.labels = payload.get("labels", [])
        self.summary = payload.get("summary", "")
        self.attributes = payload.get("attributes", {})


ZepEntityReader = LocalGraphReader
