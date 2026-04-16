"""种子提取流水线执行器（四阶段管线）。"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Tuple

from ..models.project import ProjectManager, ProjectStatus
from .chapter_continuity_service import ChapterContinuityService
from .llm_router import LlmRouter
from .reading_notes_manager import ReadingNotesManager
from .seed_task_callbacks import build_ontology_progress_callback
from .seed_task_progress import SeedTaskProgressTracker
from .step_trace_context import record_artifact
from .task_cancelled import TaskCancelledException
from ..utils.task_file_logger import TaskFileLogger

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
        ProjectManager.save_project_json(project_id, "chapter_segments.json", chapter_segments)
        self.progress.set_counts(chapter_count=chapter_segments["chapter_count"])

        # Generate initial chapter_continuity.json from chapter segments
        # so the writer workbench can list chapters before any finalization
        continuity = ChapterContinuityService().build_from_chapter_cards(chapter_segments["chapters"])
        ProjectManager.save_project_json(project_id, "chapter_continuity.json", continuity)

        # smart_segmentation
        self.progress.enter_stage("smart_segmentation", "正在智能分段", 8, "将章节分组为阅读段")
        step_id = self.progress.begin_step("smart_segmentation", "segment", "智能分段")
        segment_result = self.service.smart_segmenter.segment(chapter_segments["chapters"])
        ProjectManager.save_project_json(project_id, "smart_segments.json", segment_result)
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

        # 跟踪每个 segment 的 step_id，用于在 segment_end 时关闭
        _active_segment_step: Dict[str, str] = {}

        def reading_progress_callback(event_type: str, data: Dict[str, Any]) -> None:
            seg_idx = data.get("segment_index", 0)
            seg_id = data.get("segment_id", "")
            total = data.get("total_segments", total_segments)
            if total < 1:
                total = 1

            if event_type == "segment_start":
                progress_pct = 10 + int((seg_idx / total) * 65)
                # 开启 step trace 上下文，让 LLM 调用被记录
                step_id = self.progress.begin_step(
                    "sequential_reading",
                    "segment_reading",
                    f"阅读段落 {seg_id} ({seg_idx + 1}/{total})",
                    group_key="deep_reading",
                    group_label="深度阅读",
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
        ProjectManager.save_project_json(project_id, "analysis_blocks.json", analysis_blocks)
        self.progress.set_counts(block_count=analysis_blocks["block_count"])
        self.progress.note("analysis_blocks", "分析块已生成", f"{analysis_blocks['block_count']} 个剧情块")

        skeleton = SkeletonTimelineBuilder(NovelSeedAnalyzer()).build(chapters)
        ProjectManager.save_project_json(project_id, "skeleton_timeline.json", skeleton)
        self.progress.note("skeleton_timeline", "骨架时间线已生成", f"{skeleton['chapter_count']} 章")

        if use_llm:
            anchors = AnchorPointBuilder().build(analysis_blocks["blocks"], chapters, skeleton)
        else:
            anchors = self._offline_anchor_points(analysis_blocks["blocks"], skeleton)
        ProjectManager.save_project_json(project_id, "anchor_points.json", anchors)
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
        ProjectManager.save_project_json(project_id, "local_block_facts.json", local_facts)

        story_payload = StoryMemoryBuilder().build(
            local_facts["packets"], analysis_blocks["blocks"], anchors["anchors"], skeleton,
        )
        story_memory = story_payload["story_memory"]
        ProjectManager.save_project_json(project_id, "story_memory.json", story_memory)
        ProjectManager.save_project_json(project_id, "story_memory_snapshots.json", {"snapshots": story_payload["snapshots"]})

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
        ProjectManager.save_project_json(project_id, "block_analyses.json", block_analyses)
        consistency = ContinuityConsistencyAuditor().audit(story_memory, block_analyses["blocks"], local_facts["packets"])
        ProjectManager.save_project_json(project_id, "consistency_report.json", consistency)

        if use_llm:
            cards = ChapterCardGenerator().generate_cards(chapters, story_memory, block_analyses)
        else:
            cards = self._offline_chapter_cards(chapters, story_memory, block_analyses)
        ProjectManager.save_project_json(project_id, "chapter_cards.json", cards)
        self.progress.note("chapter_card_generation", "章节卡已生成", f"{cards['chapter_count']} 张章节卡")
        continuity = ChapterContinuityService().build_from_chapter_cards(cards["chapters"])
        ProjectManager.save_project_json(project_id, "chapter_continuity.json", continuity)
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
        ProjectManager.save_project_json(project_id, "seed_analysis.json", seed_analysis)
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
