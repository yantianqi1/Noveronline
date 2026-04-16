"""异步小说种子提取任务服务（四阶段管线）。"""

import asyncio
from typing import Any, Dict, List, Optional

from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskManager
from ..utils.file_parser import FileParser
from .character_agent_profile_generator import CharacterAgentProfileGenerator
from .llm_router import LlmRouter
from .novel_chapter_segmenter import NovelChapterSegmenter
from .seed_analysis_aggregator import SeedAnalysisAggregator
from .seed_extract_runner import SeedExtractRunner
from .sequential_reader import SequentialReader
from .smart_novel_segmenter import SmartNovelSegmenter
from .story_ontology_generator import StoryOntologyGenerator
from .text_processor import TextProcessor
from .task_cancelled import TaskCancelledException
from ..utils.upstream_error_formatter import format_upstream_service_error


class SeedExtractTaskService:
    def __init__(
        self,
        task_manager: Optional[TaskManager] = None,
        chapter_segmenter: Optional[NovelChapterSegmenter] = None,
        smart_segmenter: Optional[SmartNovelSegmenter] = None,
        sequential_reader: Optional[SequentialReader] = None,
        seed_analysis_aggregator: Optional[SeedAnalysisAggregator] = None,
        ontology_generator: Optional[StoryOntologyGenerator] = None,
        character_agent_profile_generator: Optional[CharacterAgentProfileGenerator] = None,
    ):
        self.task_manager = task_manager or TaskManager()
        self.chapter_segmenter = chapter_segmenter or NovelChapterSegmenter()
        self.smart_segmenter = smart_segmenter or SmartNovelSegmenter()
        self.sequential_reader = sequential_reader or SequentialReader(llm_router=LlmRouter())
        self.seed_analysis_aggregator = seed_analysis_aggregator or SeedAnalysisAggregator()
        self.ontology_generator = ontology_generator or StoryOntologyGenerator()
        self.character_agent_profile_generator = character_agent_profile_generator or CharacterAgentProfileGenerator()

    async def create_task(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        use_llm: bool,
        segment_token_limit: int = 50000,
    ) -> str:
        task_id = await self.task_manager.create_task(
            task_type="seed_extract",
            metadata={"project_id": project_id, "project_name": project_name},
        )
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        project.status = ProjectStatus.SEED_PROCESSING
        project.seed_task_id = task_id
        ProjectManager.save_project(project)
        asyncio.create_task(
            self._run_worker(task_id, project_id, project_name, analysis_goal, additional_context, use_llm, segment_token_limit)
        )
        return task_id

    async def _run_worker(
        self,
        task_id: str,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        use_llm: bool,
        segment_token_limit: int = 50000,
    ) -> None:
        self.smart_segmenter = SmartNovelSegmenter(target_token_limit=segment_token_limit)
        runner = SeedExtractRunner(self, task_id, use_llm, project_id=project_id)
        try:
            # Initialize progress detail from async context (safe on event loop).
            await runner.progress.async_initialize()
            # Cache the event loop so sync_bridge works from threads.
            self.task_manager._ensure_loop()
            # run() is still sync-heavy (LLM calls, file I/O) — delegate to thread
            await asyncio.to_thread(
                runner.run, project_id, project_name, analysis_goal, additional_context,
            )
        except TaskCancelledException:
            pass  # Already handled inside runner.run()
        except Exception as exc:
            message = format_upstream_service_error(exc)
            self._fail_project(project_id, message)
            runner.progress.fail(message)

    def _extract_documents(self, project_id: str) -> tuple[List[Dict[str, str]], str]:
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        source_names = {
            item.get("saved_filename"): item.get("filename", item.get("saved_filename", "上传文件"))
            for item in project.files
        }
        payloads = []
        all_text_parts = []
        for path in ProjectManager.get_project_files(project_id):
            text = TextProcessor.preprocess_text(FileParser.extract_text(path))
            saved_name = path.rsplit("/", 1)[-1]
            filename = source_names.get(saved_name, saved_name)
            payloads.append({"source_name": filename, "text": text})
            all_text_parts.append(f"\n\n=== {filename} ===\n{text}")
        if not payloads:
            raise ValueError("项目没有可处理的上传文件")
        return payloads, "".join(all_text_parts)

    def _save_text(self, project_id: str, document_payloads: List[Dict[str, str]], all_text: str) -> None:
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project_id, all_text)
        ProjectManager.save_project(project)

    def _finalize_project(
        self,
        project_id: str,
        analysis_goal: str,
        ontology: Dict[str, Any],
        seed_analysis: Dict[str, Any],
    ) -> None:
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        project.analysis_goal = analysis_goal
        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", []),
        }
        project.analysis_summary = ontology.get("analysis_summary") or seed_analysis.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        project.seed_task_id = None
        project.error = None
        ProjectManager.save_project(project)

    def _fail_project(self, project_id: str, error_message: str) -> None:
        project = ProjectManager.get_project(project_id)
        if not project:
            return
        project.status = ProjectStatus.FAILED
        project.seed_task_id = None
        project.error = error_message
        ProjectManager.save_project(project)
