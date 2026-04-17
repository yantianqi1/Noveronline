"""项目删除的级联清理服务。

当用户删除一个项目时，除了文件系统 (``backend/uploads/projects/<pid>/``)
之外，所有以 ``project_id`` 列标注的 SQL 行都必须随之清除，否则：

- 档案库、资产库、统一资产视图仍会展示已删项目的遗留条目；
- 图谱、实体、场景、大纲版本等都会变成孤儿；
- 后续同名/同 ID 的项目创建时可能冲突或串扰。

本服务把所有级联删除逻辑集中在一处，便于审阅与演进。对已经有
``delete_by_project``-类方法的 repo（archive / graph / search）直接复用；
其余表在服务自己的事务里按 ``project_id`` 批删。
"""

from __future__ import annotations

from sqlalchemy import Table, delete

from ..database import get_engine
from ..repositories.archive_repo import ArchiveRepository
from ..repositories.graph_repo import GraphRepository
from ..repositories.search_repo import SearchRepository
from ..tables import archive as archive_tables
from ..tables import assets as assets_tables
from ..tables import llm as llm_tables
from ..tables import novel as novel_tables
from ..tables import worldline as worldline_tables
from ..tables.base import metadata


# ---------------------------------------------------------------------------
# 表覆盖清单
# ---------------------------------------------------------------------------
# 这两份清单加起来必须覆盖 metadata 里所有含 project_id 列的表，
# 否则 `test_project_deletion_cascade_covers_all_tables` 会红。

# 已由 repo 方法覆盖的表（不需要在本服务里手动删除）。
COVERED_BY_REPO_METHODS: tuple[Table, ...] = (
    archive_tables.archive_library,
    archive_tables.archive_sources,
    # graph_repo.delete_graph 覆盖全部 6 张图谱表
    *(
        table
        for table in metadata.tables.values()
        if table.name.startswith("graph_")
    ),
    # search_repo.delete_project 覆盖 global_index
    *(
        table
        for table in metadata.tables.values()
        if table.name == "global_index"
    ),
)

# 需要本服务主动删除的表（所有带 project_id 但不在上面清单里的）。
# 显式列出便于审阅；有新表时必须主动追加。
ALL_PROJECT_SCOPED_TABLES: tuple[Table, ...] = (
    # archive.py 剩余
    archive_tables.archive_agent_memory,
    archive_tables.archive_agent_memory_events,
    # assets.py
    assets_tables.assets,
    assets_tables.asset_links,
    # novel.py
    novel_tables.entities,
    novel_tables.entity_aliases,
    novel_tables.entity_labels,
    novel_tables.relationships,
    novel_tables.entity_evidence,
    novel_tables.chapter_content,
    novel_tables.chapter_meta,
    novel_tables.scenes,
    novel_tables.sessions,
    novel_tables.worldline_branches,
    novel_tables.agent_states,
    novel_tables.agent_memory,
    novel_tables.world_events,
    novel_tables.plot_threads,
    novel_tables.narrative_arcs,
    novel_tables.project_meta,
    novel_tables.project_artifacts,
    novel_tables.writer_presets,
    novel_tables.character_events,
    novel_tables.relationship_events,
    novel_tables.thread_lifecycle,
    novel_tables.world_rule_evidence,
    novel_tables.consistency_notes,
    novel_tables.volume_summaries,
    novel_tables.segment_summaries,
    novel_tables.outline_versions,
    novel_tables.thread_entity_links,
    novel_tables.rule_entity_links,
    novel_tables.book_plans,
    # worldline.py
    worldline_tables.agent_registry,
    worldline_tables.agent_state_snapshots,
    worldline_tables.agent_action_log,
    worldline_tables.agent_dialogue_log,
    worldline_tables.relation_state_log,
    worldline_tables.agent_episodic_memory,
    worldline_tables.prepare_runs,
    worldline_tables.prepared_agent_dossiers,
    worldline_tables.prepare_event_log,
    worldline_tables.worldline_sessions,
    # llm.py
    llm_tables.writer_presets_global,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def cascade_delete_project(project_id: str) -> dict[str, int]:
    """级联删除给定项目的全部数据库行。

    调用方负责单独处理文件系统 (`ProjectManager.delete_project`)。
    建议顺序：先 DB 后文件系统——DB 失败时文件系统还在，用户可重试。

    返回各表删除的行数统计，便于调试/审计。
    """
    if not project_id:
        raise ValueError("project_id 不能为空")

    engine = get_engine()
    stats: dict[str, int] = {}

    # 1) 已有 repo 方法（每个自带独立连接/事务）
    archive_repo = ArchiveRepository(engine)
    stats["archive_library"] = archive_repo.delete_archives_by_project(project_id)
    stats["archive_sources"] = archive_repo.delete_source(project_id)

    stats["global_index"] = SearchRepository(engine).delete_project(project_id)

    GraphRepository(engine).delete_graph(project_id)
    stats["graph_tables"] = 1  # 无 rowcount，只标记已执行

    # 2) 剩余表：单个事务批删
    with engine.begin() as conn:
        for table in ALL_PROJECT_SCOPED_TABLES:
            result = conn.execute(
                delete(table).where(table.c.project_id == project_id),
            )
            stats[table.name] = result.rowcount or 0

    return stats


__all__ = [
    "ALL_PROJECT_SCOPED_TABLES",
    "COVERED_BY_REPO_METHODS",
    "cascade_delete_project",
]
