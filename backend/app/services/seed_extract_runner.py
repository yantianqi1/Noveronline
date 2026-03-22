"""种子提取流水线执行器。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..models.project import ProjectManager, ProjectStatus
from .llm_router import LlmRouter
from .seed_task_callbacks import (
    build_anchor_progress_callback,
    build_block_progress_callback,
    build_ontology_progress_callback,
)
from .seed_task_progress import SeedTaskProgressTracker


class SeedExtractRunner:
    """执行第一阶段种子提取流水线。"""

    def __init__(self, service: Any, task_id: str, use_llm: bool):
        self.service = service
        self.use_llm = use_llm
        self.progress = SeedTaskProgressTracker(service.task_manager, task_id, use_llm)

    def run(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
    ) -> None:
        self._validate_llm_modules()
        documents, chapter_segments = self._extract_and_segment(project_id)
        skeleton = self._build_skeleton(project_id, chapter_segments)
        analysis_blocks = self._build_blocks(project_id, chapter_segments)
        anchors = self._build_anchors(project_id, analysis_blocks, chapter_segments, skeleton)
        local_block_facts, story_memory_payload, story_memory = self._extract_story_memory(
            project_id,
            chapter_segments,
            analysis_blocks,
            skeleton,
            anchors,
        )
        block_analyses, continuity, seed_analysis = self._analyze_story(
            project_id,
            project_name,
            analysis_goal,
            chapter_segments,
            analysis_blocks,
            local_block_facts,
            story_memory_payload,
            story_memory,
        )
        ontology = self._generate_ontology(
            documents,
            analysis_goal,
            additional_context,
            continuity,
            story_memory,
            block_analyses,
        )
        self.service._finalize_project(project_id, analysis_goal, ontology, seed_analysis)
        self.progress.complete(
            "上传完成，项目与种子分析已生成。",
            self._result_payload(project_id, chapter_segments, analysis_blocks, seed_analysis),
        )

    def _extract_and_segment(self, project_id: str) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        self.progress.enter_stage("extract_text", "正在提取上传文件文本", 5, "读取并清洗上传的原始文稿")
        documents, all_text = self.service._extract_documents(project_id)
        self.service._save_text(project_id, documents, all_text)
        self.progress.note("extract_text", "文本提取完成", f"已提取 {len(documents)} 份文稿，共 {len(all_text)} 字")

        self.progress.enter_stage("segment_chapters", "正在切分章节与叙事段", 15)
        chapter_segments = self.service.chapter_segmenter.segment_documents(documents)
        ProjectManager.save_project_json(project_id, "chapter_segments.json", chapter_segments)
        self.progress.set_counts(chapter_count=chapter_segments["chapter_count"])
        self.progress.note(
            "segment_chapters",
            "章节切分完成",
            f"已识别 {chapter_segments['chapter_count']} 个章节",
            meta={"kind": "artifact", "artifact": "chapter_segments.json"},
        )
        return documents, chapter_segments

    def _build_skeleton(self, project_id: str, chapter_segments: Dict[str, Any]) -> Dict[str, Any]:
        self.progress.enter_stage("skeleton_timeline", "正在顺序扫描骨架时间线", 22)
        skeleton = self.service.skeleton_timeline_builder.build(chapter_segments["chapters"])
        ProjectManager.save_project_json(project_id, "skeleton_timeline.json", skeleton)
        self.progress.note(
            "skeleton_timeline",
            "骨架时间线扫描完成",
            f"已记录 {len(skeleton['global_characters'])} 名角色、{len(skeleton['global_organizations'])} 个组织",
            meta={"kind": "artifact", "artifact": "skeleton_timeline.json"},
        )
        return skeleton

    def _build_blocks(self, project_id: str, chapter_segments: Dict[str, Any]) -> Dict[str, Any]:
        self.progress.enter_stage("build_blocks", "正在组装分析块与重叠上下文", 28)
        analysis_blocks = self.service.block_builder.build(chapter_segments["chapters"])
        ProjectManager.save_project_json(project_id, "analysis_blocks.json", analysis_blocks)
        self.progress.set_counts(block_count=analysis_blocks["block_count"])
        self.progress.note(
            "build_blocks",
            "分析块组装完成",
            f"共生成 {analysis_blocks['block_count']} 个块",
            meta={"kind": "artifact", "artifact": "analysis_blocks.json"},
        )
        return analysis_blocks

    def _build_anchors(
        self,
        project_id: str,
        analysis_blocks: Dict[str, Any],
        chapter_segments: Dict[str, Any],
        skeleton: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.progress.enter_stage("anchor_generation", "正在生成剧情锚点摘要", 38)
        anchors = self.service.anchor_point_builder.build(
            blocks=analysis_blocks["blocks"],
            chapters=chapter_segments["chapters"],
            skeleton=skeleton,
            progress_callback=build_anchor_progress_callback(self.progress),
        )
        ProjectManager.save_project_json(project_id, "anchor_points.json", anchors)
        self.progress.note(
            "anchor_generation",
            "剧情锚点生成完成",
            f"共生成 {anchors['anchor_count']} 个锚点",
            meta={"kind": "artifact", "artifact": "anchor_points.json"},
        )
        return anchors

    def _extract_story_memory(
        self,
        project_id: str,
        chapter_segments: Dict[str, Any],
        analysis_blocks: Dict[str, Any],
        skeleton: Dict[str, Any],
        anchors: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        self.progress.enter_stage("extract_local_facts", "正在并发提取块内局部事实", 50)
        self.progress.reset_block_progress()
        local_block_facts = self.service.local_block_fact_extractor.extract_blocks(
            blocks=analysis_blocks["blocks"],
            chapters=chapter_segments["chapters"],
            use_llm=self.use_llm,
            skeleton=skeleton,
            anchors=anchors,
            progress_callback=build_block_progress_callback(self.progress, "extract_local_facts", "块内事实"),
        )
        ProjectManager.save_project_json(project_id, "local_block_facts.json", local_block_facts)
        self.progress.note(
            "extract_local_facts",
            "局部事实提取完成",
            f"已完成 {local_block_facts['block_count']} 个块",
            meta={"kind": "artifact", "artifact": "local_block_facts.json"},
        )

        self.progress.enter_stage("merge_story_memory", "正在顺序汇总故事记忆", 58)
        story_memory_payload = self.service.story_memory_builder.build(
            local_block_facts["packets"],
            blocks=analysis_blocks["blocks"],
            anchors=anchors.get("anchors", []),
            skeleton=skeleton,
        )
        story_memory = story_memory_payload["story_memory"]
        snapshots = {"snapshots": story_memory_payload["snapshots"]}
        ProjectManager.save_project_json(project_id, "story_memory.json", story_memory)
        ProjectManager.save_project_json(project_id, "story_memory_snapshots.json", snapshots)
        self.progress.note(
            "merge_story_memory",
            "故事记忆已汇总",
            f"生成 {len(story_memory_payload['snapshots'])} 份前情快照",
            meta={"kind": "artifact", "artifact": "story_memory.json"},
        )
        self.progress.enter_stage("entity_resolution", "正在执行全局实体消歧", 62)
        story_memory = self.service.entity_resolution_service.resolve(story_memory)
        ProjectManager.save_project_json(project_id, "story_memory.json", story_memory)
        self.progress.note(
            "entity_resolution",
            "全局实体消歧完成",
            f"当前实体数 {len(story_memory.get('entity_registry', {}))}",
            meta={"kind": "artifact", "artifact": "story_memory.json"},
        )
        return local_block_facts, story_memory_payload, story_memory

    def _analyze_story(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        chapter_segments: Dict[str, Any],
        analysis_blocks: Dict[str, Any],
        local_block_facts: Dict[str, Any],
        story_memory_payload: Dict[str, Any],
        story_memory: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        self.progress.enter_stage("contextual_block_analysis", "正在带前情快照分析剧情块", 72)
        self.progress.reset_block_progress()
        block_analyses = self.service.contextual_block_analyzer.analyze_blocks(
            blocks=analysis_blocks["blocks"],
            local_block_facts=local_block_facts["packets"],
            snapshots=story_memory_payload["snapshots"],
            chapters=chapter_segments["chapters"],
            use_llm=self.use_llm,
            progress_callback=build_block_progress_callback(self.progress, "contextual_block_analysis", "剧情块分析"),
        )
        ProjectManager.save_project_json(project_id, "block_analyses.json", block_analyses)
        self.progress.note(
            "contextual_block_analysis",
            "剧情块分析完成",
            f"已分析 {block_analyses['block_count']} 个块",
            meta={"kind": "artifact", "artifact": "block_analyses.json"},
        )

        self._build_continuity_artifacts(project_id, chapter_segments, analysis_blocks, local_block_facts, story_memory, block_analyses)
        continuity = ProjectManager.load_project_json(project_id, "chapter_continuity.json") or {"chapter_count": 0, "chapters": []}
        seed_analysis = self._build_seed_analysis(project_id, project_name, analysis_goal, story_memory, block_analyses)
        return block_analyses, continuity, seed_analysis

    def _build_continuity_artifacts(
        self,
        project_id: str,
        chapter_segments: Dict[str, Any],
        analysis_blocks: Dict[str, Any],
        local_block_facts: Dict[str, Any],
        story_memory: Dict[str, Any],
        block_analyses: Dict[str, Any],
    ) -> None:
        self.progress.enter_stage("consistency_audit", "正在审计连续性冲突与歧义", 78)
        consistency_report = self.service.consistency_auditor.audit(
            story_memory=story_memory,
            block_analyses=block_analyses["blocks"],
            local_block_facts=local_block_facts["packets"],
        )
        ProjectManager.save_project_json(project_id, "consistency_report.json", consistency_report)
        self.progress.note(
            "consistency_audit",
            "连续性审计完成",
            f"识别 {len(consistency_report.get('issues', []))} 个关注点",
            meta={"kind": "artifact", "artifact": "consistency_report.json"},
        )

        self.progress.enter_stage("build_continuity", "正在生成兼容章节连续性摘要", 82)
        continuity = self.service.continuity_service.build_from_block_analyses(
            chapter_segments["chapters"],
            analysis_blocks["blocks"],
            block_analyses["blocks"],
        )
        ProjectManager.save_project_json(project_id, "chapter_continuity.json", continuity)
        self.progress.note(
            "build_continuity",
            "章节连续性摘要完成",
            f"已生成 {continuity['chapter_count']} 条章节连续性记录",
            meta={"kind": "artifact", "artifact": "chapter_continuity.json"},
        )

    def _build_seed_analysis(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        story_memory: Dict[str, Any],
        block_analyses: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.progress.enter_stage("seed_analysis", "正在聚合角色、组织与关系种子分析", 88)
        seed_analysis = self.service.seed_analysis_aggregator.aggregate(
            story_memory=story_memory,
            block_analyses=block_analyses["blocks"],
            analysis_goal=analysis_goal,
            project_name=project_name,
        )
        ProjectManager.save_project_json(project_id, "seed_analysis.json", seed_analysis)
        self.progress.note(
            "seed_analysis",
            "种子分析聚合完成",
            self._seed_counts_text(seed_analysis),
            meta={"kind": "artifact", "artifact": "seed_analysis.json"},
        )
        return seed_analysis

    def _generate_ontology(
        self,
        documents: List[Dict[str, str]],
        analysis_goal: str,
        additional_context: str,
        continuity: Dict[str, Any],
        story_memory: Dict[str, Any],
        block_analyses: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.progress.enter_stage("ontology", "正在生成小说本体与故事主轴", 94)
        return self.service.ontology_generator.generate(
            document_texts=[item["text"] for item in documents],
            analysis_goal=analysis_goal,
            additional_context=additional_context or None,
            use_llm=self.use_llm,
            chapter_continuity=continuity,
            story_memory=story_memory,
            block_analyses=block_analyses["blocks"],
            progress_callback=build_ontology_progress_callback(self.progress),
        )

    def _result_payload(
        self,
        project_id: str,
        chapter_segments: Dict[str, Any],
        analysis_blocks: Dict[str, Any],
        seed_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "project_id": project_id,
            "project_status": ProjectStatus.ONTOLOGY_GENERATED.value,
            "chapter_count": chapter_segments["chapter_count"],
            "block_count": analysis_blocks["block_count"],
            "seed_analysis": {
                "character_count": len(seed_analysis.get("characters", [])),
                "organization_count": len(seed_analysis.get("organizations", [])),
                "relation_count": len(seed_analysis.get("relations", [])),
            },
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
            "local_block_facts",
            "contextual_block_analysis",
            "anchor_point_summary",
            "entity_resolution",
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
