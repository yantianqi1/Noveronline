"""
项目模型定义
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ProjectStatus(str, Enum):
    CREATED = "created"
    SEED_PROCESSING = "seed_processing"
    ONTOLOGY_GENERATED = "ontology_generated"
    GRAPH_BUILDING = "graph_building"
    GRAPH_COMPLETED = "graph_completed"
    FAILED = "failed"


@dataclass
class Project:
    project_id: str
    name: str
    status: ProjectStatus
    created_at: str
    updated_at: str
    files: List[Dict[str, str]] = field(default_factory=list)
    total_text_length: int = 0
    ontology: Optional[Dict[str, Any]] = None
    analysis_summary: Optional[str] = None
    graph_id: Optional[str] = None
    graph_build_task_id: Optional[str] = None
    seed_task_id: Optional[str] = None
    analysis_goal: Optional[str] = None
    chunk_size: int = 500
    chunk_overlap: int = 50
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "status": self.status.value if isinstance(self.status, ProjectStatus) else self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "files": self.files,
            "total_text_length": self.total_text_length,
            "ontology": self.ontology,
            "analysis_summary": self.analysis_summary,
            "graph_id": self.graph_id,
            "graph_build_task_id": self.graph_build_task_id,
            "seed_task_id": self.seed_task_id,
            "analysis_goal": self.analysis_goal,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        status = data.get("status", "created")
        if isinstance(status, str):
            status = ProjectStatus(status)
        return cls(
            project_id=data["project_id"],
            name=data.get("name", "Unnamed Project"),
            status=status,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            files=data.get("files", []),
            total_text_length=data.get("total_text_length", 0),
            ontology=data.get("ontology"),
            analysis_summary=data.get("analysis_summary"),
            graph_id=data.get("graph_id"),
            graph_build_task_id=data.get("graph_build_task_id"),
            seed_task_id=data.get("seed_task_id"),
            analysis_goal=data.get("analysis_goal"),
            chunk_size=data.get("chunk_size", 500),
            chunk_overlap=data.get("chunk_overlap", 50),
            error=data.get("error"),
        )
