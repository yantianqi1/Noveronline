"""种子提取流水线执行器（四阶段管线）。"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from ..models.project import ProjectManager, ProjectStatus
from ..utils.retry_policy import (
    ExhaustedLLMRetries,
    PermanentLLMError,
    RetryPolicy,
    retry_with_policy,
)
from ..utils.llm_json import normalize_json_object
from .chapter_continuity_service import ChapterContinuityService
from .global_data_linker import GlobalDataLinker
from .llm_router import LlmRouter
from .reading_notes_manager import ReadingNotesManager
from .seed_task_callbacks import build_ontology_progress_callback
from .seed_task_progress import SeedTaskProgressTracker
from .sequential_reader import MODULE_KEY as SEQUENTIAL_READING_MODULE_KEY
from .sequential_reader_prompts import build_segment_reading_prompt
from .step_trace_context import record_artifact
from .task_cancelled import TaskCancelledException
from ..utils.task_file_logger import TaskFileLogger

logger = logging.getLogger(__name__)

LONG_NOVEL_CHAPTER_THRESHOLD = 100
LONG_NOVEL_BLOCK_TARGET_CHAR_COUNT = 680


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
        tm = self.service.task_manager
        if tm.sync_bridge(tm.is_cancelled(self.task_id)):
            raise TaskCancelledException(self.task_id, "runner")

    def _log(self, stage: str, message: str, level: str = "info") -> None:
        if self.task_logger:
            getattr(self.task_logger, level)(stage, message)

    def _record_unified_db_ready(self) -> None:
        self._log("migration", "已切换为统一数据库主真相源")
        self.progress.note(
            "agent_profiles",
            "统一数据库已就绪",
            "后续写作与检索将直接使用主库，不再回填 legacy novel.sqlite3",
            meta={"kind": "migration", "target": "unified_db"},
        )

    def _link_global_data(self, project_id: str) -> None:
        """Stage 5: 档案库同步 / 图谱构建 / FTS 重建。

        在 ``_finalize_project`` 之后、``progress.complete`` 之前调用。
        任一 Stage 抛异常则向上传，由外层 ``_run_worker`` 标记项目为 FAILED。
        ``SEED_AUTO_LINK_GLOBAL_DATA=False`` 时跳过（测试环境用）。
        """
        from ..config import Settings

        settings = Settings()
        if not settings.SEED_AUTO_LINK_GLOBAL_DATA:
            return
        GlobalDataLinker().link_project(
            project_id,
            progress=self.progress,
            use_llm=self.use_llm,
        )

    def _persist_narrative_data(
        self, project_id: str, manager: ReadingNotesManager
    ) -> None:
        """Upsert narrative arcs / volume summaries / segment summaries to DB.

        Stage 2 (sequential reading) and Stage 3 (aggregation) build these in
        ``manager`` but until now only the JSON mirror in ``project_artifacts``
        was produced — the dedicated ``narrative_arcs`` / ``volume_summaries``
        / ``segment_summaries`` tables stayed empty. Writer-agent tools like
        ``get_story_overview`` read those tables directly, so until we populate
        them the agent has no narrative context.

        ``volume_order`` / ``segment_order`` come from enumerate — the order in
        ``manager`` mirrors story time. Individual row failures get logged and
        recorded as progress warnings but never abort the pipeline.
        """
        import json
        from datetime import datetime

        from ..database import get_engine
        from ..repositories.narrative_repo import NarrativeRepository

        repo = NarrativeRepository(get_engine())
        now_iso = datetime.now().isoformat()

        plot_state = manager.notes.get("plot_state", {}) or {}
        arcs_written = 0
        vols_written = 0
        segs_written = 0

        # Narrative arcs: {arc_id, summary, covered_segments, ...}
        for entry in plot_state.get("arc_summaries", []) or []:
            if not isinstance(entry, dict):
                continue
            arc_id = entry.get("arc_id") or ""
            if not arc_id:
                continue
            summary_text = entry.get("summary") or ""
            try:
                repo.upsert_narrative_arc(
                    project_id,
                    {
                        "arc_id": arc_id,
                        "summary": summary_text,
                        "covered_segments_json": json.dumps(
                            entry.get("covered_segments") or [], ensure_ascii=False
                        ),
                        "created_at": now_iso,
                    },
                )
                arcs_written += 1
            except Exception:
                logger.exception("persist narrative_arc failed: %s", arc_id)

        # Volume summaries: volume_order is the insertion order (1-based).
        # `covered_arcs` in manager is a list of arc_ids; richer fields like
        # theme / main_arcs / faction_changes / cross_volume_threads don't
        # have table columns — they stay in the JSON mirror (project_artifacts).
        for idx, entry in enumerate(plot_state.get("volume_summaries", []) or [], start=1):
            if not isinstance(entry, dict):
                continue
            volume_id = entry.get("volume_id") or ""
            if not volume_id:
                continue
            try:
                repo.upsert_volume_summary(
                    project_id,
                    {
                        "volume_id": volume_id,
                        "volume_order": idx,
                        "summary": entry.get("summary") or "",
                        "covered_arcs_json": json.dumps(
                            entry.get("covered_arcs") or [], ensure_ascii=False
                        ),
                        "created_at": now_iso,
                    },
                )
                vols_written += 1
            except Exception:
                logger.exception("persist volume_summary failed: %s", volume_id)

        # Segment summaries: dedup by segment_id since the pipeline may
        # append duplicates during retry; keep only the latest status per id.
        seen_segments: set[str] = set()
        for idx, entry in enumerate(manager.all_segment_summaries or [], start=1):
            if not isinstance(entry, dict):
                continue
            segment_id = entry.get("segment_id") or ""
            if not segment_id or segment_id in seen_segments:
                continue
            seen_segments.add(segment_id)
            try:
                repo.upsert_segment_summary(
                    project_id,
                    {
                        "segment_id": segment_id,
                        "segment_order": idx,
                        "summary": entry.get("summary") or "",
                        "created_at": now_iso,
                    },
                )
                segs_written += 1
            except Exception:
                logger.exception("persist segment_summary failed: %s", segment_id)

        self._log(
            "narrative_persist",
            f"落库：弧线={arcs_written} · 卷册={vols_written} · 段摘要={segs_written}",
        )
        if arcs_written or vols_written or segs_written:
            self.progress.note(
                "agent_profiles",
                "叙事数据落库",
                f"已写入 {arcs_written} 条弧线、{vols_written} 条卷册、{segs_written} 条段摘要到统一数据库。",
                meta={"kind": "persist", "target": "narrative_tables"},
            )

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

            compatibility_artifacts = self._build_story_artifacts(
                project_id,
                chapter_segments,
                use_llm=False,
            )

            self._check_cancelled()

            # Stage 3: global_integration + ontology
            t0 = time.time()
            if self.task_logger:
                self.task_logger.stage_start("global_integration", "聚合分析与本体生成")
            seed_analysis, ontology = self._global_integration_and_ontology(
                project_id, project_name, analysis_goal, additional_context,
                documents, manager, compatibility_artifacts,
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
            self._record_unified_db_ready()

            # Persist narrative (arcs / volumes / segment summaries) produced by
            # Stage 2/3 into the unified DB. Until this step the data lived only
            # in `manager` and the `project_artifacts` JSON mirror — the writer
            # agent's `get_story_overview` / `query_segment_summaries` tools
            # queried empty tables.
            self._persist_narrative_data(project_id, manager)

            # Stage 5: 全局数据打通（档案库 / 图谱 / 全局索引）
            self._link_global_data(project_id)

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
        # 记录产物：文件列表和文本摘要
        for doc in documents:
            name = doc.get("name", "未命名文件")
            text = doc.get("text", "")
            preview = text[:2000] + ("…" if len(text) > 2000 else "")
            record_artifact(f"文稿: {name} ({len(text)} 字)", preview)
        record_artifact("合并全文统计", f"共 {len(documents)} 份文稿，合并后 {len(all_text)} 字", kind="stat")
        self.progress.end_step(step_id)
        self.progress.note("extract_text", "文本提取完成", f"已提取 {len(documents)} 份文稿，共 {len(all_text)} 字")

        # chapter segmentation (existing)
        chapter_segments = self.service.chapter_segmenter.segment_documents(documents)
        ProjectManager.save_project_artifact(project_id, "chapter_segments.json", chapter_segments)
        self.progress.set_counts(chapter_count=chapter_segments["chapter_count"])

        # Generate initial chapter_continuity.json from chapter segments
        # so the writer workbench can list chapters before any finalization
        continuity = ChapterContinuityService().build_from_chapter_cards(chapter_segments["chapters"])
        ProjectManager.save_project_artifact(project_id, "chapter_continuity.json", continuity)

        # smart_segmentation
        self.progress.enter_stage("smart_segmentation", "正在智能分段", 8, "将章节分组为阅读段")
        step_id = self.progress.begin_step("smart_segmentation", "segment", "智能分段")
        segment_result = self.service.smart_segmenter.segment(chapter_segments["chapters"])
        ProjectManager.save_project_artifact(project_id, "smart_segments.json", segment_result)
        # 记录产物：每个段的章节组成
        for seg in segment_result.get("segments", []):
            seg_id = seg.get("segment_id", "")
            chapters = seg.get("chapters", [])
            est_tokens = seg.get("estimated_tokens", 0)
            chapter_range = seg.get("chapter_range", "")
            lines = []
            for ch in chapters:
                title = ch.get("title", "无标题")
                wc = ch.get("word_count", 0)
                lines.append(f"  {ch.get('order', '?')}. {title} ({wc} 字)")
            record_artifact(
                f"段落 {seg_id}（章节 {chapter_range}，{len(chapters)} 章，~{est_tokens} tokens）",
                "\n".join(lines),
            )
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

        # Pre-declare every segment + expected arc summary step so the frontend can
        # render the full "深度阅读" checklist up front (pending) instead of showing
        # a denominator that grows as work happens. 仅在 use_llm 时预报 arc 步骤，
        # 离线模式不生成弧线摘要。
        arc_interval = self.service.sequential_reader.arc_interval
        declared_segment_steps: Dict[str, str] = {}
        declared_arc_steps: Dict[str, str] = {}
        for idx, segment in enumerate(segments):
            seg_id = segment.get("segment_id", f"seg_{idx + 1:03d}")
            declared_segment_steps[seg_id] = self.progress.declare_step(
                "sequential_reading",
                "segment_reading",
                f"阅读段落 {seg_id} ({idx + 1}/{total_segments})",
                group_key="deep_reading",
                group_label="深度阅读",
            )
            if self.use_llm and (idx + 1) % arc_interval == 0:
                arc_index = (idx + 1) // arc_interval
                arc_id = f"arc_{arc_index:03d}"
                declared_arc_steps[arc_id] = self.progress.declare_step(
                    "arc_summary",
                    "arc_summary",
                    f"生成弧线摘要 {arc_id}",
                    group_key="deep_reading",
                    group_label="深度阅读",
                )
        if self.use_llm and total_segments > 0 and total_segments % arc_interval != 0:
            arc_index = (total_segments // arc_interval) + 1
            arc_id = f"arc_{arc_index:03d}"
            declared_arc_steps[arc_id] = self.progress.declare_step(
                "arc_summary",
                "arc_summary",
                f"生成弧线摘要 {arc_id} (收尾)",
                group_key="deep_reading",
                group_label="深度阅读",
            )

        # 跟踪每个 segment / arc / volume 的 step_id，用于在 _end 时关闭
        _active_segment_step: Dict[str, str] = {}
        _active_arc_step: Dict[str, str] = {}
        _active_volume_step: Dict[str, str] = {}

        def reading_progress_callback(event_type: str, data: Dict[str, Any]) -> None:
            seg_idx = data.get("segment_index", 0)
            seg_id = data.get("segment_id", "")
            total = data.get("total_segments", total_segments)
            if total < 1:
                total = 1

            if event_type == "segment_start":
                progress_pct = 10 + int((seg_idx / total) * 65)
                # 开启 step trace 上下文，复用 declare_step 预分配的 step_id
                step_id = self.progress.begin_step(
                    "sequential_reading",
                    "segment_reading",
                    f"阅读段落 {seg_id} ({seg_idx + 1}/{total})",
                    group_key="deep_reading",
                    group_label="深度阅读",
                    step_id=declared_segment_steps.get(seg_id),
                )
                _active_segment_step[seg_id] = step_id
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
                # 关闭 step trace 上下文，写入 trace bundle
                step_id = _active_segment_step.pop(seg_id, "")
                if step_id:
                    self.progress.end_step(step_id)
                self.progress.block_completed(
                    "sequential_reading",
                    f"完成阅读 {seg_id}",
                    f"段落 {seg_idx + 1}/{total}",
                    {"kind": "segment", "block_id": seg_id, "segment_index": seg_idx},
                )
            elif event_type == "arc_start":
                arc_id = data.get("arc_id", "")
                arc_index = data.get("arc_index", 0)
                if not arc_id:
                    return
                step_id = self.progress.begin_step(
                    "arc_summary",
                    "arc_summary",
                    f"生成弧线摘要 {arc_id}",
                    group_key="deep_reading",
                    group_label="深度阅读",
                    step_id=declared_arc_steps.get(arc_id),
                )
                _active_arc_step[arc_id] = step_id
                self.progress.enter_stage(
                    "arc_summary",
                    f"正在生成弧线摘要 {arc_id} (第 {arc_index} 段)",
                    10 + int(((seg_idx + 1) / total) * 65),
                )
            elif event_type == "arc_end":
                arc_id = data.get("arc_id", "")
                step_id = _active_arc_step.pop(arc_id, "")
                if step_id:
                    self.progress.end_step(step_id)
            elif event_type == "volume_start":
                volume_id = data.get("volume_id", "")
                volume_index = data.get("volume_index", 0)
                if not volume_id:
                    return
                # 卷摘要较少发生（需要 10 个弧线），按需即时开一个 step。
                step_id = self.progress.begin_step(
                    "arc_summary",
                    "volume_summary",
                    f"生成卷摘要 {volume_id}",
                    group_key="deep_reading",
                    group_label="深度阅读",
                )
                _active_volume_step[volume_id] = step_id
                self.progress.enter_stage(
                    "arc_summary",
                    f"正在生成卷摘要 {volume_id} (第 {volume_index} 卷)",
                    10 + int(((seg_idx + 1) / total) * 65),
                )
            elif event_type == "volume_end":
                volume_id = data.get("volume_id", "")
                step_id = _active_volume_step.pop(volume_id, "")
                if step_id:
                    self.progress.end_step(step_id)
            elif event_type == "segment_retry":
                attempt = data.get("attempt", 0)
                max_attempts = data.get("max_attempts", 0)
                wait = data.get("wait_seconds", 0)
                error_class = data.get("error_class", "")
                scope = data.get("scope", "segment")
                scope_label = {"arc": "弧线摘要", "volume": "卷摘要"}.get(scope, "段落")
                # 无感更新：不追加新 timeline，只改当前活跃 step 的 detail
                self.progress.update_active_step_detail(
                    f"{scope_label} {seg_id} 正在自动重试 {attempt}/{max(max_attempts - 1, 1)}"
                    f"（{int(wait)}s 后，原因 {error_class}）"
                )
            elif event_type == "stage_cooldown":
                wait = data.get("wait_seconds", 0)
                streak = data.get("failed_streak", 0)
                self.progress.update_active_step_detail(
                    f"连续 {streak} 段落失败，冷却 {int(wait)}s 以缓解上游限流"
                )
            elif event_type == "segment_permanent_failure":
                error_detail = data.get("error_detail", "")
                error_class = data.get("error_class", "")
                scope = data.get("scope", "segment")
                scope_label = {"arc": "弧线摘要", "volume": "卷摘要"}.get(scope, "段落")
                self.progress.emit_warning(
                    "sequential_reading",
                    f"{scope_label} {seg_id} 深度阅读未自动完成",
                    (error_detail or "")[:200],
                    {
                        "kind": "retry_needed_segment",
                        "segment_id": seg_id,
                        "error_class": error_class,
                        "scope": scope,
                    },
                )
            elif event_type == "segment_sweep_recovered":
                # 扫尾阶段恢复的段落仅走 step trace 审计，不扰动主 UI。
                record_artifact(
                    f"扫尾阶段恢复段落 {seg_id}",
                    "通过简化 prompt 重新生成了段落摘要。",
                    kind="retry",
                )

        # 周期 checkpoint：每 5 段把 reading_notes.json 落盘一次，让 断点续传
        # 在任务被杀的情况下也能接着跑。checkpoint 失败不能让整个读阶段崩掉，
        # sequential_reader.read 内部已经 try/except 过，这里只需要提供 saver。
        import os
        notes_path = os.path.join(ProjectManager._get_project_dir(project_id), "reading_notes.json")

        def checkpoint_saver(mgr: ReadingNotesManager) -> None:
            mgr.save(notes_path)

        manager = self.service.sequential_reader.read(
            segments=segments,
            use_llm=self.use_llm,
            progress_callback=reading_progress_callback,
            cancel_check=self._check_cancelled,
            checkpoint_callback=checkpoint_saver if self.use_llm else None,
            checkpoint_every=5,
        )

        # Save reading notes (filesystem + DB mirror for runtime reads)
        manager.save(notes_path)
        ProjectManager.save_project_artifact(project_id, "reading_notes.json", manager.assemble_for_save())

        # Save segment summaries
        ProjectManager.save_project_artifact(
            project_id, "segment_summaries.json",
            {"summaries": manager.all_segment_summaries},
        )

        # 暴露"重读失败段落"出口给前端
        failed_ids = manager.failed_segment_ids()
        self.progress.set_sequential_reading_retry(failed_ids)

        completed_count = total_segments - len(failed_ids)
        char_count = len(manager.notes["core_facts"]["characters"])
        if failed_ids:
            self.progress.note(
                "sequential_reading",
                f"顺序阅读完成（含 {len(failed_ids)} 段待手动重读）",
                f"已阅读 {completed_count}/{total_segments} 个段落，记录 {char_count} 名角色；"
                f"其余 {len(failed_ids)} 段可点击 '一键重读' 补齐。",
                level="warning",
                meta={"kind": "artifact", "artifact": "reading_notes.json"},
            )
        else:
            self.progress.note(
                "sequential_reading",
                "顺序阅读完成",
                f"已阅读 {total_segments} 个段落，记录 {char_count} 名角色",
                meta={"kind": "artifact", "artifact": "reading_notes.json"},
            )
        return manager

    def _build_story_artifacts(
        self,
        project_id: str,
        chapter_segments: Dict[str, Any],
        use_llm: bool,
    ) -> Dict[str, Any]:
        from .analysis_block_builder import AnalysisBlockBuilder
        from .anchor_point_builder import AnchorPointBuilder
        from .chapter_card_generator import ChapterCardGenerator
        from .continuity_consistency_auditor import ContinuityConsistencyAuditor
        from .contextual_block_analyzer import ContextualBlockAnalyzer
        from .local_block_fact_extractor import LocalBlockFactExtractor
        from .novel_seed_analyzer import NovelSeedAnalyzer
        from .sentence_atlas_builder import build_sentence_map
        from .skeleton_timeline_builder import SkeletonTimelineBuilder
        from .story_memory_builder import StoryMemoryBuilder

        chapters = chapter_segments["chapters"]
        sentence_map = build_sentence_map(chapter_segments.get("sentence_atlas", []))
        chapter_map = {chapter["chapter_id"]: chapter for chapter in chapters}
        analysis_blocks = AnalysisBlockBuilder(
            target_owned_char_count=self._analysis_block_target(chapters)
        ).build(chapters)
        ProjectManager.save_project_artifact(project_id, "analysis_blocks.json", analysis_blocks)
        self.progress.set_counts(block_count=analysis_blocks["block_count"])
        self.progress.note("analysis_blocks", "分析块已生成", f"{analysis_blocks['block_count']} 个剧情块")

        skeleton = SkeletonTimelineBuilder(NovelSeedAnalyzer()).build(chapters)
        ProjectManager.save_project_artifact(project_id, "skeleton_timeline.json", skeleton)
        self.progress.note("skeleton_timeline", "骨架时间线已生成", f"{skeleton['chapter_count']} 章")

        if use_llm:
            anchors = AnchorPointBuilder().build(analysis_blocks["blocks"], chapters, skeleton)
        else:
            anchors = self._offline_anchor_points(analysis_blocks["blocks"], skeleton)
        ProjectManager.save_project_artifact(project_id, "anchor_points.json", anchors)
        self.progress.note("anchor_generation", "剧情锚点已生成", f"{anchors['anchor_count']} 个锚点")

        extractor = LocalBlockFactExtractor()
        if use_llm:
            local_facts = self.service.task_manager.sync_bridge(
                extractor.extract_blocks(
                    analysis_blocks["blocks"],
                    chapters,
                    True,
                    skeleton=skeleton,
                    anchors=anchors,
                )
            )
        else:
            packets = [
                extractor._extract_block(
                    block,
                    chapter_map,
                    sentence_map,
                    False,
                    None,
                    skeleton,
                    analysis_blocks["blocks"],
                    anchors,
                    None,
                )
                for block in analysis_blocks["blocks"]
            ]
            local_facts = {"block_count": len(packets), "packets": packets}
        ProjectManager.save_project_artifact(project_id, "local_block_facts.json", local_facts)

        story_payload = StoryMemoryBuilder().build(
            local_facts["packets"], analysis_blocks["blocks"], anchors["anchors"], skeleton,
        )
        story_memory = story_payload["story_memory"]
        ProjectManager.save_project_artifact(project_id, "story_memory.json", story_memory)
        ProjectManager.save_project_artifact(project_id, "story_memory_snapshots.json", {"snapshots": story_payload["snapshots"]})

        analyzer = ContextualBlockAnalyzer()
        if use_llm:
            block_analyses = self.service.task_manager.sync_bridge(
                analyzer.analyze_blocks(
                    analysis_blocks["blocks"],
                    local_facts["packets"],
                    story_payload["snapshots"],
                    chapters,
                    True,
                )
            )
        else:
            packets_by_id = {item["block_id"]: item for item in local_facts["packets"]}
            snapshots_by_id = {item["block_id"]: item for item in story_payload["snapshots"]}
            blocks = [
                analyzer._analyze_block(
                    block,
                    packets_by_id[block["block_id"]],
                    snapshots_by_id[block["block_id"]],
                    chapter_map,
                    sentence_map,
                    False,
                    None,
                )
                for block in analysis_blocks["blocks"]
            ]
            block_analyses = {"block_count": len(blocks), "blocks": blocks}
        ProjectManager.save_project_artifact(project_id, "block_analyses.json", block_analyses)
        consistency = ContinuityConsistencyAuditor().audit(story_memory, block_analyses["blocks"], local_facts["packets"])
        ProjectManager.save_project_artifact(project_id, "consistency_report.json", consistency)

        if use_llm:
            cards = ChapterCardGenerator().generate_cards(chapters, story_memory, block_analyses)
        else:
            cards = self._offline_chapter_cards(chapters, story_memory, block_analyses)
        ProjectManager.save_project_artifact(project_id, "chapter_cards.json", cards)
        self.progress.note("chapter_card_generation", "章节卡已生成", f"{cards['chapter_count']} 张章节卡")
        continuity = ChapterContinuityService().build_from_chapter_cards(cards["chapters"])
        ProjectManager.save_project_artifact(project_id, "chapter_continuity.json", continuity)
        return {"story_memory": story_memory, "block_analyses": block_analyses}

    def _analysis_block_target(self, chapters: List[Dict[str, Any]]) -> int:
        if len(chapters) >= LONG_NOVEL_CHAPTER_THRESHOLD:
            return LONG_NOVEL_BLOCK_TARGET_CHAR_COUNT
        return 5000

    def _offline_anchor_points(self, blocks: List[Dict[str, Any]], skeleton: Dict[str, Any]) -> Dict[str, Any]:
        anchors = []
        sketches = {item["chapter_id"]: item for item in skeleton.get("chapter_sketches", [])}
        for index in range(0, len(blocks), 5):
            group = blocks[index:index + 5]
            anchors.append(self._offline_anchor(index // 5 + 1, group, sketches))
        return {"anchor_count": len(anchors), "anchors": anchors}

    def _offline_anchor(self, index: int, blocks: List[Dict[str, Any]], sketches: Dict[str, Any]) -> Dict[str, Any]:
        chapter_ids = [chapter_id for block in blocks for chapter_id in block.get("owned_chapter_ids", [])]
        characters = sorted({name for chapter_id in chapter_ids for name in sketches.get(chapter_id, {}).get("characters", [])})
        organizations = sorted({name for chapter_id in chapter_ids for name in sketches.get(chapter_id, {}).get("organizations", [])})
        return {
            "anchor_id": f"anchor_{index:04d}",
            "block_range": [block["block_id"] for block in blocks],
            "start_block_order": blocks[0].get("order", 0),
            "end_block_order": blocks[-1].get("order", 0),
            "world_state": {
                "active_characters": [{"name": name, "status": "active"} for name in characters],
                "active_organizations": [{"name": name, "status": "active"} for name in organizations],
                "key_relationships": [],
                "open_plot_threads": [],
                "recent_events_summary": "；".join(sketches.get(chapter_id, {}).get("tail_hook", "") for chapter_id in chapter_ids)[:300],
            },
        }

    def _offline_chapter_cards(self, chapters: List[Dict[str, Any]], story_memory: Dict[str, Any], block_analyses: Dict[str, Any]) -> Dict[str, Any]:
        from .chapter_card_fallback_builder import ChapterCardFallbackBuilder

        builder = ChapterCardFallbackBuilder()
        cards = []
        for chapter in sorted(chapters, key=lambda item: item.get("order", 0)):
            cards.append(builder.build(chapter, story_memory, block_analyses, cards))
        return {"chapter_count": len(cards), "chapters": cards}

    # ── Stage 3: global_integration + ontology ──

    def _global_integration_and_ontology(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        documents: List[Dict[str, str]],
        manager: ReadingNotesManager,
        story_artifacts: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        # global_integration: aggregate seed analysis from reading notes
        self.progress.enter_stage("global_integration", "正在聚合种子分析", 78, "从阅读笔记中聚合角色、组织与关系")
        step_id = self.progress.begin_step("global_integration", "aggregate", "聚合种子分析")
        seed_analysis = self.service.seed_analysis_aggregator.aggregate_from_reading_notes(
            manager=manager,
            analysis_goal=analysis_goal,
            project_name=project_name,
        )
        compatibility_block_count = story_artifacts.get("story_memory", {}).get("block_count")
        if isinstance(compatibility_block_count, int) and compatibility_block_count > 0:
            seed_analysis.setdefault("source_stats", {})["block_count"] = compatibility_block_count
            seed_analysis.setdefault("story_memory", {})["block_count"] = compatibility_block_count
        ProjectManager.save_project_artifact(project_id, "seed_analysis.json", seed_analysis)
        # 记录产物：聚合结果摘要
        chars = seed_analysis.get("characters", [])
        orgs = seed_analysis.get("organizations", [])
        rels = seed_analysis.get("relations", [])
        record_artifact(
            f"角色 ({len(chars)} 个)",
            "\n".join(f"  - {c.get('name', '?')}: {c.get('identity', '')}" for c in chars[:30]),
        )
        if orgs:
            record_artifact(
                f"组织 ({len(orgs)} 个)",
                "\n".join(f"  - {o.get('name', '?')}: {o.get('description', '')}" for o in orgs[:20]),
            )
        if rels:
            record_artifact(
                f"关系 ({len(rels)} 条)",
                "\n".join(
                    f"  - {r.get('source', '?')} → {r.get('target', '?')}: {r.get('relation_type', '')}"
                    for r in rels[:30]
                ),
            )
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
            story_memory=story_artifacts.get("story_memory") or {"reading_notes_context": manager.assemble_context()},
            block_analyses=story_artifacts.get("block_analyses", {}).get("blocks", []),
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

        # 整体包裹在 step 中，使并发 LLM 调用的 trace 被主线程上下文捕获
        step_id = self.progress.begin_step(
            "agent_profiles",
            "profile_batch",
            "批量生成角色Agent档案",
            group_key="agent_build",
            group_label="角色构建",
        )
        agent_profiles = asyncio.run(
            self.service.character_agent_profile_generator.generate(
                manager=manager,
                use_llm=self.use_llm,
                progress_callback=profile_progress_callback,
                cancel_check=self._check_cancelled,
            )
        )
        # 记录产物：生成的角色档案摘要
        import json
        profiles = agent_profiles.get("profiles", {})
        for name, profile in profiles.items():
            preview = json.dumps(profile, ensure_ascii=False, indent=2)
            if len(preview) > 3000:
                preview = preview[:3000] + "\n…（截断）"
            record_artifact(f"角色档案: {name}", preview, kind="json")
        record_artifact(
            "档案生成总结",
            f"共生成 {agent_profiles.get('profile_count', 0)} 个角色Agent档案",
            kind="stat",
        )
        self.progress.end_step(step_id)
        ProjectManager.save_project_artifact(project_id, "agent_profiles.json", agent_profiles)
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

    # ── Manual retry entrypoint ──

    def retry_failed_segments(
        self,
        project_id: str,
        project_name: str = "",
        analysis_goal: str = "",
        additional_context: str = "",
    ) -> None:
        """手动重试入口:重读 reading_notes.json 里所有标记为 retry_needed 的段落
        以及因任务中断而从未被处理过的段落（smart_segments 有但 reading_notes
        中没有对应摘要）。

        如果全部恢复,重跑聚合/本体/角色档案阶段以刷新下游产物;
        否则只保存补齐后的 reading_notes,把仍未完成的清单回写到 progress_detail。
        """
        pipeline_start = time.time()
        self._log("retry_pipeline", f"重读失败段落启动: project={project_id}")

        try:
            self._validate_llm_modules()

            notes_path = os.path.join(
                ProjectManager._get_project_dir(project_id), "reading_notes.json",
            )
            # 断点续传降级：第一遍任务在写出 reading_notes.json 之前就被杀的
            # 场景，用空 manager 把所有段落都当"未处理"重跑，而不是硬报错。
            # smart_segments.json 是下面判断"是否有段落可重跑"的前提，缺它
            # 才算真正无法恢复。
            if os.path.exists(notes_path):
                manager = ReadingNotesManager.load(notes_path)
                fresh_start = False
            else:
                manager = ReadingNotesManager()
                fresh_start = True
                self._log(
                    "retry_pipeline",
                    "reading_notes.json 不存在，按空笔记重跑所有段落。",
                    "warning",
                )

            smart_segments = ProjectManager.load_project_json(
                project_id, "smart_segments.json",
            ) or {}
            segments_by_id = {
                seg.get("segment_id"): seg
                for seg in smart_segments.get("segments", [])
                if seg.get("segment_id")
            }
            if fresh_start and not segments_by_id:
                raise ValueError(
                    "项目尚未生成 smart_segments.json，无法执行重读。"
                    "请点击 重新开始 从头跑一次分段。"
                )

            # 1) Segments marked retry_needed (graceful failure path).
            failed_ids = manager.failed_segment_ids()
            # 2) Segments never attempted (abrupt kill path — no entry at all
            #    in all_segment_summaries). True "breakpoint resume".
            processed_ids = {
                entry.get("segment_id")
                for entry in manager.all_segment_summaries
                if entry.get("segment_id")
            }
            unprocessed_ids = [
                seg_id for seg_id in segments_by_id
                if seg_id not in processed_ids
            ]
            # Combine, ordering strictly by smart_segments.segments position so
            # that `add_segment_summary` for previously-unprocessed segments
            # appends to `all_segment_summaries` in the novel's time order.
            # 否则 `pending_arc_segments()` 的切片就不是按故事时间序，补弧时
            # 会把早段的 segments 塞进后面的弧里，语义错乱。
            need_ids = set(failed_ids) | {sid for sid in unprocessed_ids if sid}
            combined_ids: List[str] = [
                seg_id for seg_id in segments_by_id if seg_id in need_ids
            ]

            if not combined_ids:
                self.progress.set_sequential_reading_retry([])
                self.progress.complete(
                    "没有需要重读的段落。",
                    {"project_id": project_id, "recovered": 0, "remaining": 0},
                )
                return

            targets: List[Tuple[str, Dict[str, Any]]] = [
                (seg_id, segments_by_id[seg_id])
                for seg_id in combined_ids
                if seg_id in segments_by_id
            ]
            if not targets:
                raise ValueError(
                    f"reading_notes.json 中有 {len(combined_ids)} 个待重读段落,"
                    f"但 smart_segments.json 中找不到对应片段"
                )

            detail_label = (
                f"含 {len(failed_ids)} 段已知失败 / {len(unprocessed_ids)} 段未处理"
                if unprocessed_ids and failed_ids
                else f"共 {len(targets)} 个段落"
            )
            self.progress.enter_stage(
                "sequential_reading",
                f"正在重读 {len(targets)} 个段落（{detail_label}）",
                15,
                "断点续传:重新分析失败段落及因中断未处理的段落",
            )

            recovered, remaining = self._retry_reread_segments(targets, manager)

            manager.save(notes_path)
            ProjectManager.save_project_artifact(project_id, "reading_notes.json", manager.assemble_for_save())
            ProjectManager.save_project_artifact(
                project_id, "segment_summaries.json",
                {"summaries": manager.all_segment_summaries},
            )
            self.progress.set_sequential_reading_retry(manager.failed_segment_ids())

            if remaining > 0:
                self.progress.complete(
                    f"已恢复 {recovered} 段,另有 {remaining} 段仍待重读。",
                    {
                        "project_id": project_id,
                        "recovered": recovered,
                        "remaining": remaining,
                        "pending_segments": manager.failed_segment_ids(),
                    },
                )
                if self.task_logger:
                    self.task_logger.info(
                        "retry_pipeline",
                        f"部分恢复:recovered={recovered}, remaining={remaining}",
                    )
                return

            # 全部恢复 → 重跑下游阶段 (stage 3 + stage 4)
            project = ProjectManager.get_project(project_id)
            if project is None:
                raise ValueError(f"项目不存在: {project_id}")
            project_name = project_name or project.name
            analysis_goal = analysis_goal or (project.analysis_goal or "")

            all_text = ProjectManager.get_extracted_text(project_id) or ""
            documents = [{"source_name": project.name, "text": all_text}]
            story_memory = ProjectManager.load_project_json(
                project_id, "story_memory.json",
            ) or {}
            block_analyses = ProjectManager.load_project_json(
                project_id, "block_analyses.json",
            ) or {}
            compatibility_artifacts = {
                "story_memory": story_memory,
                "block_analyses": block_analyses,
            }
            chapter_segments = ProjectManager.load_project_json(
                project_id, "chapter_segments.json",
            ) or {}
            chapter_count = chapter_segments.get("chapter_count", 0)

            seed_analysis, ontology = self._global_integration_and_ontology(
                project_id, project_name, analysis_goal, additional_context,
                documents, manager, compatibility_artifacts,
            )

            agent_profiles = self._generate_agent_profiles(project_id, manager)

            self.service._finalize_project(
                project_id, analysis_goal, ontology, seed_analysis,
            )
            self._record_unified_db_ready()

            # Persist narrative data after a resume rerun too — the resume path
            # rebuilds arcs/volumes from scratch so the DB state should refresh.
            self._persist_narrative_data(project_id, manager)

            # 重读重跑完整 finalize 后同样打通下游数据
            self._link_global_data(project_id)

            payload = self._result_payload(
                project_id,
                {
                    "smart_segments": smart_segments,
                    "chapter_count": chapter_count,
                },
                manager, seed_analysis, agent_profiles,
            )
            payload.update({"recovered": recovered, "remaining": 0})
            self.progress.complete(
                f"已恢复 {recovered} 段并刷新下游产物。",
                payload,
            )
            if self.task_logger:
                total_s = time.time() - pipeline_start
                self.task_logger.info(
                    "retry_pipeline",
                    f"重读与重建完成,总耗时 {total_s:.1f}s",
                )

        except TaskCancelledException as exc:
            self._log(
                "retry_pipeline",
                f"重读任务被用户取消 (stage={exc.stage})",
                "warning",
            )
            self.progress.fail("用户取消了重读任务")
        except PermanentLLMError as exc:
            self._log("retry_pipeline", f"永久 LLM 错误中止重读: {exc.detail}", "error")
            self.progress.fail(exc.detail)
        finally:
            if self.task_logger:
                self.task_logger.close()

    def _retry_reread_segments(
        self,
        targets: List[Tuple[str, Dict[str, Any]]],
        manager: ReadingNotesManager,
    ) -> Tuple[int, int]:
        """对每一个失败段落执行一次扩大预算的重读。返回 (recovered, remaining)。"""
        reader = self.service.sequential_reader
        client = reader.llm_router.build_client(SEQUENTIAL_READING_MODULE_KEY)
        base_policy = reader.retry_policy
        policy = RetryPolicy(
            max_attempts=max(base_policy.max_attempts * 2, 2),
            base_delay_seconds=base_policy.base_delay_seconds,
            max_delay_seconds=base_policy.max_delay_seconds,
        )

        total = len(targets)
        recovered = 0
        for idx, (segment_id, segment) in enumerate(targets):
            self._check_cancelled()
            step_id = self.progress.begin_step(
                "sequential_reading",
                "segment_retry",
                f"重读段落 {segment_id} ({idx + 1}/{total})",
                group_key="deep_reading",
                group_label="深度阅读",
            )

            context = manager.assemble_context()
            segment_text = reader._extract_segment_text(segment)

            def call(attempt: int):
                if attempt == 0:
                    temperature, max_tokens = 0.3, 8192
                else:
                    temperature, max_tokens = 0.2, 4096
                messages = build_segment_reading_prompt(context, segment_text)
                raw = client.chat_json_value(
                    messages, temperature=temperature, max_tokens=max_tokens,
                )
                return normalize_json_object(raw, f"segment {segment_id} (manual retry)")

            def on_retry(attempt, max_attempts, wait, error_class, exc):
                self.progress.update_active_step_detail(
                    f"段落 {segment_id} 正在重试 {attempt}/{max(max_attempts - 1, 1)}"
                    f"（{int(wait)}s 后,原因 {error_class}）"
                )

            try:
                result = retry_with_policy(call, policy=policy, on_retry=on_retry)
            except PermanentLLMError:
                self.progress.end_step(step_id)
                raise
            except ExhaustedLLMRetries as exc:
                logger.warning(
                    "Manual retry exhausted for %s: %s", segment_id, exc.detail,
                )
                self.progress.emit_warning(
                    "sequential_reading",
                    f"段落 {segment_id} 仍未能完成",
                    (exc.detail or "")[:200],
                    {
                        "kind": "retry_still_failed",
                        "segment_id": segment_id,
                        "error_class": exc.error_class,
                    },
                )
                self.progress.end_step(step_id)
                continue

            summary = result.get("segment_summary", "") if isinstance(result, dict) else ""
            if not summary:
                logger.warning("Manual retry of %s returned empty summary", segment_id)
                self.progress.end_step(step_id)
                continue

            if manager.update_segment_summary(segment_id, summary):
                reader._merge_structured_fields(manager, result, segment_id)
                recovered += 1
            else:
                # 该段落从未被处理过（进程在第一次 checkpoint 前被杀）—
                # update_segment_summary 找不到旧条目就返回 False，这时直接
                # 追加新条目，再合并结构化字段，否则 LLM 的结果会被静默丢掉。
                manager.add_segment_summary(segment_id, summary)
                reader._merge_structured_fields(manager, result, segment_id)
                recovered += 1

            progress_pct = 15 + int(((idx + 1) / max(total, 1)) * 40)
            self.progress.enter_stage(
                "sequential_reading",
                f"已完成 {idx + 1}/{total} 段重读",
                progress_pct,
            )
            self.progress.end_step(step_id)

        # Backfill arc / volume summaries for segments recovered by this pass.
        # 模仿 SequentialReader.read():183-215 的末端处理：循环补齐尚未覆盖的弧，
        # 每补完一弧再按阈值触发一次卷摘要；最后还有一次"兜底弧"把尾段收编。
        # PermanentLLMError 会抛回 retry_failed_segments 的 except 分支；
        # ExhaustedLLMRetries 被 _generate_arc_summary 内部转成 retry_needed 条目。
        self._backfill_arc_volume_summaries(client, manager, reader)

        remaining = len(manager.failed_segment_ids())
        return recovered, remaining

    def _backfill_arc_volume_summaries(
        self,
        client: Any,
        manager: ReadingNotesManager,
        reader: "SequentialReader",
    ) -> None:
        """Drive arc / volume summary generation to completion for ``manager``.

        Slices ``pending_arc_segments`` into ``arc_interval``-sized chunks so
        the produced弧 count matches a clean single-pass run (first-pass
        flushes one arc every ``arc_interval`` segments; backfill may face a
        large pending queue and should preserve that granularity).
        """

        def _run_arc(pending: List[Dict]) -> None:
            arc_index = len(manager.notes["plot_state"]["arc_summaries"]) + 1
            step_id = self.progress.begin_step(
                "arc_summary",
                "arc_summary",
                f"补齐弧线摘要 arc_{arc_index:03d}",
                group_key="deep_reading",
                group_label="深度阅读",
            )
            try:
                reader._generate_arc_summary(
                    client, manager, progress_callback=None, pending=pending,
                )
            finally:
                self.progress.end_step(step_id)

        def _run_volume() -> None:
            vol_index = len(manager.notes["plot_state"]["volume_summaries"]) + 1
            step_id = self.progress.begin_step(
                "arc_summary",
                "volume_summary",
                f"补齐卷摘要 vol_{vol_index:03d}",
                group_key="deep_reading",
                group_label="深度阅读",
            )
            try:
                reader._generate_volume_summary(client, manager, progress_callback=None)
            finally:
                self.progress.end_step(step_id)

        interval = max(1, int(manager.arc_interval))
        while manager.needs_arc_summary():
            pending = manager.pending_arc_segments()[:interval]
            _run_arc(pending)
            if manager.needs_volume_summary():
                _run_volume()

        # 尾段兜底弧（模仿 sequential_reader.read():213-215）：不足 arc_interval
        # 的残段单独成弧，保证每一段都被某条弧摘要覆盖。
        if manager.pending_arc_segments():
            _run_arc(manager.pending_arc_segments())
            if manager.needs_volume_summary():
                _run_volume()

    def _validate_llm_modules(self) -> None:
        if not self.use_llm:
            return
        missing = []
        router = LlmRouter()
        for module_key in (
            "sequential_reading",
            "story_ontology",
            "character_agent_profile",
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
