"""本地图谱领域模型。"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class EvidenceRef:
    chapter_id: str
    block_id: str
    snippet: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class GraphNode:
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    evidence_refs: List[EvidenceRef] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["evidence_refs"] = [item.to_dict() for item in self.evidence_refs]
        return payload


@dataclass(frozen=True)
class GraphEdge:
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    attributes: Dict[str, Any]
    weight: int
    evidence_refs: List[EvidenceRef] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["evidence_refs"] = [item.to_dict() for item in self.evidence_refs]
        return payload


@dataclass(frozen=True)
class GraphSnapshot:
    graph_id: str
    project_id: str
    graph_name: str
    built_at: str
    build_version: str
    ontology: Dict[str, Any]
    nodes: List[GraphNode]
    edges: List[GraphEdge]

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "project_id": self.project_id,
            "graph_name": self.graph_name,
            "built_at": self.built_at,
            "build_version": self.build_version,
            "ontology": self.ontology,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "nodes": [item.to_dict() for item in self.nodes],
            "edges": [item.to_dict() for item in self.edges],
        }
