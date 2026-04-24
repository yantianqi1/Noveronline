"""全局数据打通服务。

种子管线跑完后把三类下游数据一次性灌满，避免用户手动串联档案库、故事图谱、
全局索引三次按钮：

- Stage A 档案同步：把 seed_analysis + agent_profiles 生成叙事档案，写入
  ``narrative_archives.json`` 并同步到 ``archive_library`` DB 表。
- Stage B 图谱构建：基于 ontology + 阅读笔记构建本地故事图谱，写入
  ``graph_meta`` / ``graph_nodes`` / ``graph_edges``。
- Stage C 索引重建：把所有 silo 资产重新灌入 ``global_index`` FTS 表。

所有 Stage 都**幂等**：可重复调用不会产生重复记录。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..database import get_engine
from ..models.project import ProjectManager, ProjectStatus
from ..repositories.archive_repo import ArchiveRepository
from ..repositories.project_artifact_repo import load_project_artifact
from .archive_candidate_builder import ArchiveCandidateBuilder
from .archive_library_service import ArchiveLibraryService
from .assets.global_search_indexer import GlobalSearchIndexer
from .graph_builder import GraphBuilderService
from .narrative_entity_archivist import NarrativeEntityArchivist
from .seed_task_progress import SeedTaskProgressTracker

logger = logging.getLogger(__name__)


STAGE_ARCHIVE_SYNC = "archive_sync"
STAGE_GRAPH_BUILD = "graph_build"
STAGE_INDEX_REBUILD = "index_rebuild"

PROGRESS_ARCHIVE_SYNC = 93
PROGRESS_GRAPH_BUILD = 96
PROGRESS_INDEX_REBUILD = 99


class GlobalDataLinker:
    """编排档案同步 / 图谱构建 / FTS 重建三步。

    用法：

    >>> linker = GlobalDataLinker()
    >>> summary = linker.link_project(project_id)            # 同步跑
    >>> linker.backfill_missing()                            # 扫描存量项目

    设计约束：
    - 所有方法都是同步的，便于从 ``asyncio.to_thread`` 调用。
    - ``progress`` 可选，传入 ``SeedTaskProgressTracker`` 时把三个新阶段
      打进种子任务时间轴；未传时静默跑完。
    - 任一 stage 抛异常则中断并向上传，由调用方决定如何标记 project 状态。
    """

    def __init__(
        self,
        archive_service: Optional[ArchiveLibraryService] = None,
        graph_service: Optional[GraphBuilderService] = None,
        indexer: Optional[GlobalSearchIndexer] = None,
        candidate_builder: Optional[ArchiveCandidateBuilder] = None,
        archivist: Optional[NarrativeEntityArchivist] = None,
    ):
        self._archive_service = archive_service or ArchiveLibraryService()
        self._graph_service = graph_service or GraphBuilderService()
        self._indexer = indexer or GlobalSearchIndexer()
        self._candidate_builder = candidate_builder or ArchiveCandidateBuilder()
        self._archivist = archivist or NarrativeEntityArchivist(
            candidate_builder=self._candidate_builder,
        )

    # ==================================================================
    # 主入口
    # ==================================================================

    def link_project(
        self,
        project_id: str,
        *,
        progress: Optional[SeedTaskProgressTracker] = None,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        """串行跑三步打通，返回 summary。"""
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")

        summary: Dict[str, Any] = {"project_id": project_id, "stages": {}}

        summary["stages"]["archive_sync"] = self._run_archive_sync(
            project_id, progress=progress, use_llm=use_llm,
        )
        summary["stages"]["graph_build"] = self._run_graph_build(
            project_id, progress=progress,
        )
        summary["stages"]["index_rebuild"] = self._run_index_rebuild(
            project_id, progress=progress,
        )

        # 打通完成后促状态到 GRAPH_COMPLETED，前端据此隐藏重试按钮。
        refreshed = ProjectManager.get_project(project_id)
        if refreshed and refreshed.status != ProjectStatus.GRAPH_COMPLETED:
            refreshed.status = ProjectStatus.GRAPH_COMPLETED
            refreshed.error = None
            ProjectManager.save_project(refreshed)
        summary["final_status"] = ProjectStatus.GRAPH_COMPLETED.value
        return summary

    # ==================================================================
    # Stage A — 档案同步
    # ==================================================================

    def _run_archive_sync(
        self,
        project_id: str,
        *,
        progress: Optional[SeedTaskProgressTracker],
        use_llm: bool,
    ) -> Dict[str, Any]:
        if progress:
            progress.enter_stage(
                STAGE_ARCHIVE_SYNC,
                "正在同步档案库",
                PROGRESS_ARCHIVE_SYNC,
                "从种子分析与角色档案生成全局档案并写入档案库",
            )

        seed_analysis = load_project_artifact(project_id, "seed_analysis")
        if not seed_analysis:
            raise ValueError(f"项目缺少 seed_analysis，无法生成档案: {project_id}")
        raw_profiles = load_project_artifact(project_id, "agent_profiles") or {}
        agent_profiles = (
            raw_profiles.get("profiles", {}) if isinstance(raw_profiles, dict) else {}
        )

        step_id = None
        if progress:
            step_id = progress.begin_step(
                STAGE_ARCHIVE_SYNC, "archive_generate", "生成叙事档案",
            )
        try:
            candidates = self._candidate_builder.build_from_seed_analysis(seed_analysis)
            archives = self._archivist.generate_archives_from_candidates(
                candidates,
                use_llm=use_llm,
                entity_lookup={},
                agent_profiles=agent_profiles,
            )
            data = {
                "graph_id": None,
                "project_id": project_id,
                "count": len(archives),
                "entity_types": ["Character", "Organization", "Relationship"],
                "archives": [item.to_dict() for item in archives],
            }
            # Phase 2 · DB is the sole source of truth. The former
            # ``narrative_archives.json`` write has been removed — DB-native
            # write happens in the next step via write_archives_for_project.
        finally:
            if progress and step_id:
                progress.end_step(step_id)

        step_id = None
        if progress:
            step_id = progress.begin_step(
                STAGE_ARCHIVE_SYNC, "archive_sync_db", "同步到档案库",
            )
        try:
            # Phase 2 · DB-native write. No longer goes through
            # sync_project_archives → JSON → _replace_project_archives;
            # the in-memory ``data`` payload is written to the DB directly.
            synced = self._archive_service.write_archives_for_project(
                project_id, data,
            )
        finally:
            if progress and step_id:
                progress.end_step(step_id)

        if progress:
            progress.note(
                STAGE_ARCHIVE_SYNC,
                "档案库同步完成",
                f"写入 {len(synced)} 条档案",
                meta={"kind": "artifact", "artifact": "archive_library"},
            )
        return {"archive_count": len(synced)}

    # ==================================================================
    # Stage B — 图谱构建
    # ==================================================================

    def _run_graph_build(
        self,
        project_id: str,
        *,
        progress: Optional[SeedTaskProgressTracker],
    ) -> Dict[str, Any]:
        if progress:
            progress.enter_stage(
                STAGE_GRAPH_BUILD,
                "正在构建故事图谱",
                PROGRESS_GRAPH_BUILD,
                "把阅读笔记沉淀为节点与连边",
            )

        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        if not project.ontology:
            raise ValueError(f"项目尚未生成 ontology: {project_id}")

        extracted_text = ProjectManager.get_extracted_text(project_id)
        if not extracted_text:
            raise ValueError(f"项目缺少提取文本: {project_id}")

        step_id = None
        if progress:
            step_id = progress.begin_step(
                STAGE_GRAPH_BUILD, "graph_build", "构建本地图谱",
            )

        # 刻意不把 builder 的 emit 转发为 progress.note:
        # builder 内部会 emit 6-8 次,每次都 sync_bridge 一次,在测试环境里会放大
        # TaskManager._task_lock 跨 loop 的噪声。生产也没必要把图谱内部阶段
        # 暴露在种子 timeline 上 -- 档案同步 / 图谱构建 / 索引三级就够粒度了。
        try:
            snapshot = self._graph_service.build_graph(
                project_id=project_id,
                text=extracted_text,
                ontology=project.ontology,
                graph_name="Novel Story Graph",
                progress_callback=None,
            )
        finally:
            if progress and step_id:
                progress.end_step(step_id)

        refreshed = ProjectManager.get_project(project_id)
        if refreshed:
            refreshed.graph_id = snapshot.graph_id
            refreshed.status = ProjectStatus.GRAPH_COMPLETED
            refreshed.graph_build_task_id = None
            refreshed.error = None
            ProjectManager.save_project(refreshed)

        if progress:
            progress.note(
                STAGE_GRAPH_BUILD,
                "图谱构建完成",
                f"节点 {snapshot.node_count} / 连边 {snapshot.edge_count}",
                meta={"kind": "artifact", "artifact": "story_graph"},
            )
        return {
            "graph_id": snapshot.graph_id,
            "node_count": snapshot.node_count,
            "edge_count": snapshot.edge_count,
        }

    # ==================================================================
    # Stage C — 全局索引重建
    # ==================================================================

    def _run_index_rebuild(
        self,
        project_id: str,
        *,
        progress: Optional[SeedTaskProgressTracker],
    ) -> Dict[str, Any]:
        if progress:
            progress.enter_stage(
                STAGE_INDEX_REBUILD,
                "正在重建全局索引",
                PROGRESS_INDEX_REBUILD,
                "把所有 silo 资产灌入 FTS 索引",
            )
        step_id = None
        if progress:
            step_id = progress.begin_step(
                STAGE_INDEX_REBUILD, "reindex", "重建 global_index",
            )
        try:
            count = self._indexer.reindex_project(project_id)
        finally:
            if progress and step_id:
                progress.end_step(step_id)
        if progress:
            progress.note(
                STAGE_INDEX_REBUILD,
                "全局索引重建完成",
                f"共索引 {count} 条目",
                meta={"kind": "artifact", "artifact": "global_index"},
            )
        return {"indexed": count}

    # ==================================================================
    # 回填老项目
    # ==================================================================

    def find_missing_projects(self) -> List[str]:
        """返回「种子已完成但档案库仍为空」的 project_id 列表。"""
        engine = get_engine()
        archive_repo = ArchiveRepository(engine)
        eligible_statuses = {
            ProjectStatus.ONTOLOGY_GENERATED,
            ProjectStatus.GRAPH_BUILDING,
            ProjectStatus.GRAPH_COMPLETED,
            ProjectStatus.FAILED,
        }
        missing: List[str] = []
        for project in ProjectManager.list_projects(limit=500):
            if project.status not in eligible_statuses:
                continue
            if project.seed_task_id:
                continue
            if not load_project_artifact(project.project_id, "seed_analysis"):
                continue
            if archive_repo.count_archives(project_id=project.project_id) > 0:
                continue
            missing.append(project.project_id)
        return missing

    def backfill_missing(self, *, use_llm: bool = True) -> List[Dict[str, Any]]:
        """串行跑 ``find_missing_projects()`` 列出的所有项目。

        每个项目的失败被吞掉并记录，不影响后续项目。返回每个项目的结果。
        """
        results: List[Dict[str, Any]] = []
        for pid in self.find_missing_projects():
            logger.info("GlobalDataLinker.backfill_missing: project=%s", pid)
            try:
                summary = self.link_project(pid, use_llm=use_llm)
                results.append({"project_id": pid, "ok": True, "summary": summary})
            except Exception as exc:  # noqa: BLE001 — 明示吞异常便于继续跑下一个
                logger.exception(
                    "GlobalDataLinker.backfill_missing 失败 project=%s", pid,
                )
                results.append({"project_id": pid, "ok": False, "error": str(exc)})
        return results
