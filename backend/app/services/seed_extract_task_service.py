"""异步小说种子提取任务服务。"""

import threading
from typing import Any, Dict, List, Optional

from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskManager
from ..utils.file_parser import FileParser
from .analysis_block_builder import AnalysisBlockBuilder
from .anchor_point_builder import AnchorPointBuilder
from .chapter_card_generator import ChapterCardGenerator
from .chapter_continuity_service import ChapterContinuityService
from .chapter_meta_service import ChapterMetaService
from .contextual_block_analyzer import ContextualBlockAnalyzer
from .continuity_consistency_auditor import ContinuityConsistencyAuditor
from .entity_resolution_service import EntityResolutionService
from .local_block_fact_extractor import LocalBlockFactExtractor
from .novel_chapter_segmenter import NovelChapterSegmenter
from .novel_seed_analyzer import NovelSeedAnalyzer
from .seed_extract_runner import SeedExtractRunner
from .seed_analysis_aggregator import SeedAnalysisAggregator
from .skeleton_timeline_builder import SkeletonTimelineBuilder
from .story_memory_builder import StoryMemoryBuilder
from .story_ontology_generator import StoryOntologyGenerator
from .text_processor import TextProcessor
from ..utils.upstream_error_formatter import format_upstream_service_error


class SeedExtractTaskService:
    def __init__(
        self,
        task_manager: Optional[TaskManager] = None,
        chapter_segmenter: Optional[NovelChapterSegmenter] = None,
        block_builder: Optional[AnalysisBlockBuilder] = None,
        local_block_fact_extractor: Optional[LocalBlockFactExtractor] = None,
        story_memory_builder: Optional[StoryMemoryBuilder] = None,
        contextual_block_analyzer: Optional[ContextualBlockAnalyzer] = None,
        consistency_auditor: Optional[ContinuityConsistencyAuditor] = None,
        continuity_service: Optional[ChapterContinuityService] = None,
        chapter_card_generator: Optional[ChapterCardGenerator] = None,
        chapter_meta_service: Optional[ChapterMetaService] = None,
        seed_analysis_aggregator: Optional[SeedAnalysisAggregator] = None,
        ontology_generator: Optional[StoryOntologyGenerator] = None,
        skeleton_timeline_builder: Optional[SkeletonTimelineBuilder] = None,
        anchor_point_builder: Optional[AnchorPointBuilder] = None,
        entity_resolution_service: Optional[EntityResolutionService] = None,
    ):
        analyzer = NovelSeedAnalyzer()
        self.task_manager = task_manager or TaskManager()
        self.chapter_segmenter = chapter_segmenter or NovelChapterSegmenter()
        self.block_builder = block_builder or AnalysisBlockBuilder()
        self.local_block_fact_extractor = local_block_fact_extractor or LocalBlockFactExtractor(analyzer=analyzer)
        self.story_memory_builder = story_memory_builder or StoryMemoryBuilder()
        self.contextual_block_analyzer = contextual_block_analyzer or ContextualBlockAnalyzer()
        self.consistency_auditor = consistency_auditor or ContinuityConsistencyAuditor()
        self.continuity_service = continuity_service or ChapterContinuityService()
        self.chapter_card_generator = chapter_card_generator or ChapterCardGenerator()
        self.chapter_meta_service = chapter_meta_service or ChapterMetaService()
        self.seed_analysis_aggregator = seed_analysis_aggregator or SeedAnalysisAggregator()
        self.ontology_generator = ontology_generator or StoryOntologyGenerator()
        self.skeleton_timeline_builder = skeleton_timeline_builder or SkeletonTimelineBuilder(analyzer)
        self.anchor_point_builder = anchor_point_builder or AnchorPointBuilder()
        self.entity_resolution_service = entity_resolution_service or EntityResolutionService()

    def create_task(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        use_llm: bool,
    ) -> str:
        task_id = self.task_manager.create_task(
            task_type="seed_extract",
            metadata={"project_id": project_id, "project_name": project_name},
        )
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        project.status = ProjectStatus.SEED_PROCESSING
        project.seed_task_id = task_id
        ProjectManager.save_project(project)
        self._start_worker(task_id, project_id, project_name, analysis_goal, additional_context, use_llm)
        return task_id

    def _start_worker(
        self,
        task_id: str,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        use_llm: bool,
    ) -> None:
        thread = threading.Thread(
            target=self._run_worker,
            args=(task_id, project_id, project_name, analysis_goal, additional_context, use_llm),
            daemon=True,
        )
        thread.start()

    def _run_worker(
        self,
        task_id: str,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        use_llm: bool,
    ) -> None:
        runner = SeedExtractRunner(self, task_id, use_llm, project_id=project_id)
        try:
            runner.run(project_id, project_name, analysis_goal, additional_context)
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
