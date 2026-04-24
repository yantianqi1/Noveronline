"""异步小说种子提取任务服务（四阶段管线）。"""

import asyncio
from typing import Any, Dict, List, Optional

from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskManager
from ..utils.file_parser import FileParser
from ..utils.retry_policy import RetryPolicy
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


def _build_sequential_reader() -> SequentialReader:
    """Instantiate ``SequentialReader`` with retry policy sourced from settings."""
    from ..config import Settings

    settings = Settings()
    policy = RetryPolicy(
        max_attempts=max(1, int(settings.SEED_SEGMENT_RETRY_MAX_ATTEMPTS)),
        base_delay_seconds=float(settings.SEED_SEGMENT_RETRY_INITIAL_DELAY_SECONDS),
        max_delay_seconds=float(settings.SEED_SEGMENT_RETRY_MAX_DELAY_SECONDS),
    )
    return SequentialReader(
        llm_router=LlmRouter(),
        retry_policy=policy,
        cooldown_streak=int(settings.SEED_STAGE_COOLDOWN_STREAK),
        cooldown_seconds=float(settings.SEED_STAGE_COOLDOWN_SECONDS),
        sweep_enabled=bool(settings.SEED_SWEEP_ENABLED),
    )


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
        self.sequential_reader = sequential_reader or _build_sequential_reader()
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

    async def create_retry_task(
        self,
        project_id: str,
        additional_context: str = "",
    ) -> str:
        """创建 '重读失败段落' 手动重试任务,返回 task_id。"""
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        task_id = await self.task_manager.create_task(
            task_type="seed_retry_segments",
            metadata={"project_id": project_id, "project_name": project.name},
        )
        project.seed_task_id = task_id
        project.error = None
        ProjectManager.save_project(project)
        asyncio.create_task(
            self._run_retry_worker(task_id, project_id, additional_context)
        )
        return task_id

    async def create_relink_task(self, project_id: str) -> str:
        """创建"重新打通数据"任务：再跑一次档案同步 / 图谱构建 / FTS 重建。"""
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        task_id = await self.task_manager.create_task(
            task_type="global_data_relink",
            metadata={"project_id": project_id, "project_name": project.name},
        )
        project.seed_task_id = task_id
        project.error = None
        ProjectManager.save_project(project)
        asyncio.create_task(self._run_relink_worker(task_id, project_id))
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

    async def _run_retry_worker(
        self,
        task_id: str,
        project_id: str,
        additional_context: str,
    ) -> None:
        runner = SeedExtractRunner(self, task_id, use_llm=True, project_id=project_id)
        try:
            await runner.progress.async_initialize()
            self.task_manager._ensure_loop()
            await asyncio.to_thread(
                runner.retry_failed_segments,
                project_id,
                "",
                "",
                additional_context,
            )
        except TaskCancelledException:
            pass
        except Exception as exc:
            message = format_upstream_service_error(exc)
            runner.progress.fail(message)
            # 重试任务失败不改 project.status,避免把已完成项目推回 FAILED;
            # 仅清除 seed_task_id 让后续请求可以再次触发。
            project = ProjectManager.get_project(project_id)
            if project:
                if project.seed_task_id == task_id:
                    project.seed_task_id = None
                project.error = message
                ProjectManager.save_project(project)

    async def _run_relink_worker(self, task_id: str, project_id: str) -> None:
        """Background worker for ``create_relink_task``。

        相较 seed 主流程：无需 runner，直接把 ``GlobalDataLinker.link_project``
        包装为三 Stage 进度事件；失败走 ``_fail_project`` + 清 ``seed_task_id``。
        """
        from .global_data_linker import GlobalDataLinker
        from .seed_task_progress import SeedTaskProgressTracker

        tracker = SeedTaskProgressTracker(
            self.task_manager, task_id, use_llm=True, project_id=project_id,
        )
        await tracker.async_initialize()
        self.task_manager._ensure_loop()

        def _sync_link() -> Dict[str, Any]:
            summary = GlobalDataLinker().link_project(
                project_id, progress=tracker, use_llm=True,
            )
            return summary

        try:
            summary = await asyncio.to_thread(_sync_link)
            tracker.complete("数据打通完成。", {"project_id": project_id, **summary})
            project = ProjectManager.get_project(project_id)
            if project and project.seed_task_id == task_id:
                project.seed_task_id = None
                ProjectManager.save_project(project)
        except TaskCancelledException:
            pass
        except Exception as exc:
            message = format_upstream_service_error(exc)
            tracker.fail(message)
            project = ProjectManager.get_project(project_id)
            if project:
                if project.seed_task_id == task_id:
                    project.seed_task_id = None
                project.status = ProjectStatus.FAILED
                project.error = message
                ProjectManager.save_project(project)

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
