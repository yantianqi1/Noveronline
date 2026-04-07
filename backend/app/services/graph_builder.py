"""本地图谱构建服务。"""

import threading
from typing import Any, Callable, Dict, Optional

from ..models.project import ProjectManager
from ..models.task import TaskManager
from .graph_builder_types import GraphInfo
from .graph_builder_worker import run_graph_build
from .local_story_graph_builder import LocalStoryGraphBuilder
from .local_story_graph_storage import LocalStoryGraphStorage


class GraphBuilderService:
    def __init__(
        self,
        builder: Optional[LocalStoryGraphBuilder] = None,
        storage: Optional[LocalStoryGraphStorage] = None,
    ):
        self.builder = builder or LocalStoryGraphBuilder()
        self.storage = storage or LocalStoryGraphStorage()
        self.task_manager = TaskManager()

    def build_graph_async(
        self,
        project_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "Novel Story Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> str:
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "project_id": project_id,
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            },
        )
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, project_id, text, ontology, graph_name, chunk_size, chunk_overlap),
            daemon=True,
        )
        thread.start()
        return task_id

    def _build_graph_worker(
        self,
        task_id: str,
        project_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        run_graph_build(self, task_id, project_id, text, ontology, graph_name, chunk_size, chunk_overlap)

    def build_graph(
        self,
        project_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        local_block_facts = self._optional_json(project_id, "local_block_facts.json")
        block_analyses = self._optional_json(project_id, "block_analyses.json")
        story_memory = self._optional_json(project_id, "story_memory.json")
        chapter_continuity = self._optional_json(project_id, "chapter_continuity.json")

        if not all([local_block_facts, block_analyses, story_memory, chapter_continuity]):
            from .reading_notes_graph_adapter import adapt_reading_notes_for_graph

            reading_notes = self._required_json(project_id, "reading_notes.json")
            seed_analysis = self._required_json(project_id, "seed_analysis.json")
            smart_segments = self._optional_json(project_id, "smart_segments.json")
            chapter_segs = self._optional_json(project_id, "chapter_segments.json")
            story_memory, local_block_facts, block_analyses, chapter_continuity = (
                adapt_reading_notes_for_graph(reading_notes, seed_analysis, smart_segments, chapter_segs)
            )

        return self.builder.build_for_project(
            project_id=project_id,
            graph_name=graph_name,
            ontology=ontology,
            extracted_text=text,
            local_block_facts=local_block_facts,
            block_analyses=block_analyses,
            story_memory=story_memory,
            chapter_continuity=chapter_continuity,
            progress_callback=progress_callback,
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        return self.storage.load_snapshot(graph_id)

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        payload = self.storage.load_snapshot(graph_id)
        entity_types = sorted({
            label
            for node in payload.get("nodes", [])
            for label in node.get("labels", [])
            if label not in {"Entity", "Node"}
        })
        return GraphInfo(
            graph_id=payload["graph_id"],
            node_count=payload.get("node_count", len(payload.get("nodes", []))),
            edge_count=payload.get("edge_count", len(payload.get("edges", []))),
            entity_types=entity_types,
        )

    def _required_json(self, project_id: str, filename: str) -> Dict[str, Any]:
        payload = ProjectManager.load_project_json(project_id, filename)
        if payload is None:
            raise ValueError(f"项目缺少构建本地图谱所需工件: {filename}")
        return payload

    def _optional_json(self, project_id: str, filename: str) -> Optional[Dict[str, Any]]:
        return ProjectManager.load_project_json(project_id, filename)
