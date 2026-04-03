"""种子提取流水线执行器（四阶段管线）。"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Tuple

from ..models.project import ProjectManager, ProjectStatus
from .llm_router import LlmRouter
from .reading_notes_manager import ReadingNotesManager
from .seed_task_callbacks import build_ontology_progress_callback
from .seed_task_progress import SeedTaskProgressTracker
from .task_cancelled import TaskCancelledException
from ..utils.task_file_logger import TaskFileLogger


class SeedExtractRunner:
    """执行四阶段种子提取流水线。

    阶段:
      1. extract_text + smart_segmentation
      2. sequential_reading
      3. global_integration + ontology
      4. agent_profiles
    """

    def __init__(self, service: Any, task_id: str, use_llm: bool, project_id: str = ""):
        self.service = service
        self.task_id = task_id
        self.use_llm = use_llm
        self.progress = SeedTaskProgressTracker(
            service.task_manager, task_id, use_llm, project_id=project_id,
        )
        self.task_logger = None
        if project_id:
            project_dir = ProjectManager._get_project_dir(project_id)
            self.task_logger = TaskFileLogger(project_dir, task_id)

    def _check_cancelled(self) -> None:
        if self.service.task_manager.is_cancelled(self.task_id):
            raise TaskCancelledException(self.task_id, "runner")

    def _log(self, stage: str, message: str, level: str = "info") -> None:
        if self.task_logger:
            getattr(self.task_logger, level)(stage, message)

    def run(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
    ) -> None:
        pipeline_start = time.time()
        self._log("pipeline", f"管线启动: project={project_name}, use_llm={self.use_llm}")

        try:
            self._validate_llm_modules()

            # Stage 1: extract_text + smart_segmentation
            t0 = time.time()
            if self.task_logger:
                self.task_logger.stage_start("extract_text", "提取文本与智能分段")
            documents, chapter_segments = self._extract_and_segment(project_id)
            seg_count = chapter_segments.get("smart_segments", {}).get("segment_count", 0)
            if self.task_logger:
                self.task_logger.stage_end("extract_text", time.time() - t0, f"{len(documents)} 份文稿, {seg_count} 个阅读段")

            self._check_cancelled()

            # Stage 2: sequential_reading
            t0 = time.time()
            if self.task_logger:
                self.task_logger.stage_start("sequential_reading", f"共 {seg_count} 个段落")
            manager = self._sequential_reading(project_id, chapter_segments)
            char_count = len(manager.notes["core_facts"]["characters"])
            if self.task_logger:
                self.task_logger.stage_end("sequential_reading", time.time() - t0, f"记录 {char_count} 名角色")

            self._check_cancelled()

            # Stage 3: global_integration + ontology
            t0 = time.time()
            if self.task_logger:
                self.task_logger.stage_start("global_integration", "聚合分析与本体生成")
            seed_analysis, ontology = self._global_integration_and_ontology(
                project_id, project_name, analysis_goal, additional_context,
                documents, manager,
            )
            if self.task_logger:
                self.task_logger.stage_end("global_integration", time.time() - t0, self._seed_counts_text(seed_analysis))

            self._check_cancelled()

            # Stage 4: agent_profiles
            t0 = time.time()
            if self.task_logger:
                self.task_logger.stage_start("agent_profiles", "角色档案生成")
            agent_profiles = self._generate_agent_profiles(project_id, manager)
            if self.task_logger:
                self.task_logger.stage_end("agent_profiles", time.time() - t0, f"{agent_profiles['profile_count']} 个档案")

            # Finalize
            self.service._finalize_project(project_id, analysis_goal, ontology, seed_analysis)
            self.progress.complete(
                "上传完成，项目与种子分析已生成。",
                self._result_payload(project_id, chapter_segments, manager, seed_analysis, agent_profiles),
            )
            if self.task_logger:
                total_s = time.time() - pipeline_start
                self.task_logger.info("pipeline", f"管线完成，总耗时 {total_s:.1f}s")

        except TaskCancelledException as exc:
            self._log("pipeline", f"任务被用户取消 (stage={exc.stage})", "warning")
            self.service._fail_project(project_id, "用户取消了分析任务")
            self.progress.fail("用户取消了分析任务")

        finally:
            if self.task_logger:
                self.task_logger.close()

    # ── Stage 1: extract_text + smart_segmentation ──

    def _extract_and_segment(self, project_id: str) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        # extract_text
        self.progress.enter_stage("extract_text", "正在提取上传文件文本", 3, "读取并清洗上传的原始文稿")
        step_id = self.progress.begin_step("extract_text", "file_extract", "提取上传文件文本")
        documents, all_text = self.service._extract_documents(project_id)
        self.service._save_text(project_id, documents, all_text)
        self.progress.end_step(step_id)
        self.progress.note("extract_text", "文本提取完成", f"已提取 {len(documents)} 份文稿，共 {len(all_text)} 字")

        # chapter segmentation (existing)
        chapter_segments = self.service.chapter_segmenter.segment_documents(documents)
        ProjectManager.save_project_json(project_id, "chapter_segments.json", chapter_segments)
        self.progress.set_counts(chapter_count=chapter_segments["chapter_count"])

        # smart_segmentation
        self.progress.enter_stage("smart_segmentation", "正在智能分段", 8, "将章节分组为阅读段")
        step_id = self.progress.begin_step("smart_segmentation", "segment", "智能分段")
        segment_result = self.service.smart_segmenter.segment(chapter_segments["chapters"])
        ProjectManager.save_project_json(project_id, "smart_segments.json", segment_result)
        self.progress.end_step(step_id)
        self.progress.set_counts(
            chapter_count=chapter_segments["chapter_count"],
            segment_count=segment_result["segment_count"],
        )
        self.progress.note(
            "smart_segmentation",
            "智能分段完成",
            f"共生成 {segment_result['segment_count']} 个阅读段",
            meta={"kind": "artifact", "artifact": "smart_segments.json"},
        )

        # Attach segments to chapter_segments dict for downstream use
        chapter_segments["smart_segments"] = segment_result
        return documents, chapter_segments

    # ── Stage 2: sequential_reading ──

    def _sequential_reading(self, project_id: str, chapter_segments: Dict[str, Any]) -> ReadingNotesManager:
        segment_result = chapter_segments["smart_segments"]
        segments = segment_result["segments"]
        total_segments = len(segments)

        self.progress.enter_stage("sequential_reading", "正在顺序阅读小说", 10, "逐段深度阅读并记录笔记")

        def reading_progress_callback(event_type: str, data: Dict[str, Any]) -> None:
            seg_idx = data.get("segment_index", 0)
            seg_id = data.get("segment_id", "")
            total = data.get("total_segments", total_segments)
            if total < 1:
                total = 1

            if event_type == "segment_start":
                progress_pct = 10 + int((seg_idx / total) * 65)
                self.progress.block_started(
                    "sequential_reading",
                    f"开始阅读 {seg_id}",
                    f"段落 {seg_idx + 1}/{total}",
                    {"kind": "segment", "block_id": seg_id, "segment_index": seg_idx},
                )
                self.progress.enter_stage(
                    "sequential_reading",
                    f"正在阅读段落 {seg_idx + 1}/{total}",
                    progress_pct,
                )
            elif event_type == "segment_end":
                progress_pct = 10 + int(((seg_idx + 1) / total) * 65)
                self.progress.block_completed(
                    "sequential_reading",
                    f"完成阅读 {seg_id}",
                    f"段落 {seg_idx + 1}/{total}",
                    {"kind": "segment", "block_id": seg_id, "segment_index": seg_idx},
                )

        manager = self.service.sequential_reader.read(
            segments=segments,
            use_llm=self.use_llm,
            progress_callback=reading_progress_callback,
            cancel_check=self._check_cancelled,
        )

        # Save reading notes
        import os
        notes_path = os.path.join(ProjectManager._get_project_dir(project_id), "reading_notes.json")
        manager.save(notes_path)

        # Save segment summaries
        ProjectManager.save_project_json(
            project_id, "segment_summaries.json",
            {"summaries": manager.all_segment_summaries},
        )

        self.progress.note(
            "sequential_reading",
            "顺序阅读完成",
            f"已阅读 {total_segments} 个段落，记录 {len(manager.notes['core_facts']['characters'])} 名角色",
            meta={"kind": "artifact", "artifact": "reading_notes.json"},
        )
        return manager

    # ── Stage 3: global_integration + ontology ──

    def _global_integration_and_ontology(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        documents: List[Dict[str, str]],
        manager: ReadingNotesManager,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        # global_integration: aggregate seed analysis from reading notes
        self.progress.enter_stage("global_integration", "正在聚合种子分析", 78, "从阅读笔记中聚合角色、组织与关系")
        step_id = self.progress.begin_step("global_integration", "aggregate", "聚合种子分析")
        seed_analysis = self.service.seed_analysis_aggregator.aggregate_from_reading_notes(
            manager=manager,
            analysis_goal=analysis_goal,
            project_name=project_name,
        )
        ProjectManager.save_project_json(project_id, "seed_analysis.json", seed_analysis)
        self.progress.end_step(step_id)
        self.progress.note(
            "global_integration",
            "种子分析聚合完成",
            self._seed_counts_text(seed_analysis),
            meta={"kind": "artifact", "artifact": "seed_analysis.json"},
        )

        # ontology
        self.progress.enter_stage("ontology", "正在生成小说本体与故事主轴", 85)
        step_id = self.progress.begin_step("ontology", "ontology", "生成小说本体与故事主轴")
        ontology = self.service.ontology_generator.generate(
            document_texts=[item["text"] for item in documents],
            analysis_goal=analysis_goal,
            additional_context=additional_context or None,
            use_llm=self.use_llm,
            story_memory={"reading_notes_context": manager.assemble_context()},
            progress_callback=build_ontology_progress_callback(self.progress),
        )
        self.progress.end_step(step_id)
        return seed_analysis, ontology

    # ── Stage 4: agent_profiles ──

    def _generate_agent_profiles(self, project_id: str, manager: ReadingNotesManager) -> Dict[str, Any]:
        self.progress.enter_stage("agent_profiles", "正在生成角色代理档案", 92, "为重要角色生成结构化代理档案")

        def profile_progress_callback(event_type: str, data: Dict[str, Any]) -> None:
            if event_type == "profiles_start":
                total = data.get("total", 0)
                self.progress.note(
                    "agent_profiles",
                    f"开始生成 {total} 个角色档案",
                    f"共 {total} 名重要角色",
                )
            elif event_type == "profile_done":
                name = data.get("name", "")
                completed = data.get("completed", 0)
                total = data.get("total", 1)
                progress_pct = 92 + int((completed / max(total, 1)) * 8)
                self.progress.enter_stage(
                    "agent_profiles",
                    f"角色档案 {completed}/{total}",
                    min(progress_pct, 99),
                )
                self.progress.note(
                    "agent_profiles",
                    f"完成角色档案: {name}",
                    f"{completed}/{total}",
                )

        agent_profiles = self.service.character_agent_profile_generator.generate(
            manager=manager,
            use_llm=self.use_llm,
            progress_callback=profile_progress_callback,
            cancel_check=self._check_cancelled,
        )
        ProjectManager.save_project_json(project_id, "agent_profiles.json", agent_profiles)
        self.progress.note(
            "agent_profiles",
            "角色代理档案生成完成",
            f"已生成 {agent_profiles['profile_count']} 个角色档案",
            meta={"kind": "artifact", "artifact": "agent_profiles.json"},
        )
        return agent_profiles

    # ── Result payload ──

    def _result_payload(
        self,
        project_id: str,
        chapter_segments: Dict[str, Any],
        manager: ReadingNotesManager,
        seed_analysis: Dict[str, Any],
        agent_profiles: Dict[str, Any],
    ) -> Dict[str, Any]:
        segment_result = chapter_segments.get("smart_segments", {})
        return {
            "project_id": project_id,
            "project_status": ProjectStatus.ONTOLOGY_GENERATED.value,
            "chapter_count": chapter_segments["chapter_count"],
            "segment_count": segment_result.get("segment_count", 0),
            "seed_analysis": {
                "character_count": len(seed_analysis.get("characters", [])),
                "organization_count": len(seed_analysis.get("organizations", [])),
                "relation_count": len(seed_analysis.get("relations", [])),
            },
            "agent_profile_count": agent_profiles.get("profile_count", 0),
        }

    def _seed_counts_text(self, seed_analysis: Dict[str, Any]) -> str:
        return (
            f"角色 {len(seed_analysis.get('characters', []))} 个，"
            f"组织 {len(seed_analysis.get('organizations', []))} 个，"
            f"关系 {len(seed_analysis.get('relations', []))} 条"
        )

    def _validate_llm_modules(self) -> None:
        if not self.use_llm:
            return
        missing = []
        router = LlmRouter()
        for module_key in (
            "sequential_reading",
            "character_agent_profile",
            "story_ontology",
        ):
            try:
                router.build_client(module_key)
            except ValueError as exc:
                if not self._is_module_binding_error(str(exc)):
                    raise
                missing.append(module_key)
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"以下 LLM 模块未完成绑定或渠道不可用，无法启动分析：{joined}")

    def _is_module_binding_error(self, message: str) -> bool:
        return any(
            text in message
            for text in ("未配置 LLM 渠道和模型", "绑定的渠道已不存在", "绑定的渠道已停用")
        )
