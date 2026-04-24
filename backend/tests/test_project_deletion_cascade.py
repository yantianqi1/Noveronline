"""项目删除级联清理集成测试。

核心断言：调用 ``cascade_delete_project`` 后，所有以 project_id 列
标注的表中属于该项目的行必须清零；同时存在一个"防漏表"看门测试，
确保 metadata 里任何新增的 project-scoped 表都必须显式加入
``ALL_PROJECT_SCOPED_TABLES`` 或被已覆盖 repo 方法处理。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, func, insert, select

from app.database import init_db
from app.services.project_deletion_service import (
    ALL_PROJECT_SCOPED_TABLES,
    COVERED_BY_REPO_METHODS,
    cascade_delete_project,
)
from app.tables import archive as archive_tables
from app.tables import assets as assets_tables
from app.tables import novel as novel_tables
from app.tables import search as search_tables
from app.tables import worldline as worldline_tables
from app.tables.base import metadata


@pytest.fixture()
def isolated_engine(monkeypatch, tmp_path):
    """In-memory SQLite engine wired as the app's shared engine."""
    upload_root = tmp_path / "uploads"
    (upload_root / "system").mkdir(parents=True)
    (upload_root / "projects").mkdir(parents=True)

    from app.config import Config
    from app.models.project import ProjectManager

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_root / "projects"))

    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)

    # project_deletion_service 通过 get_engine() 拿 engine，这里把它替换掉。
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", engine)

    yield engine


def _insert_sample_rows(engine, pid: str, now: str = "2026-04-16T10:00:00") -> None:
    """给测试项目 pid 在各 silo 里各插入 1-2 行。所有 PK 都以 pid 为后缀
    以便在同一 DB 里为多个项目并行插入不冲突。"""
    sfx = pid[-6:]  # 短后缀，保证跨项目 PK 不冲突
    with engine.begin() as conn:
        # archive entity (P5: merged into assets with asset_type='archive_entity')
        conn.execute(insert(assets_tables.assets).values(
            asset_id=f"arch_{sfx}", project_id=pid, scope="project",
            asset_type="archive_entity", category="", title="张三",
            summary="", content="", payload_json="{}", tags_json="[]",
            source_kind="archive", source_ref=f"u_{sfx}",
            enabled=1, pinned=0, word_count=0,
            created_at=now, updated_at=now,
            entity_uuid=f"u_{sfx}", entity_name="张三", entity_type="character",
            agent_kind="generic", importance_tier="major",
            recommended_importance_tier="major", selected_importance_tier="major",
            template_key="generic.major.v1", template_version="v1",
            entity_role="", core_drive="", surface_mask="",
            hidden_tension="", relationship_summary="",
            agent_behavior_hint="", human_ai_relation_tag="",
            can_act_as_agent=1, notable_risks_json="[]",
            template_sections_json="[]", template_payload_json="{}",
            template_metadata_json="{}", synced_at=now,
        ))
        conn.execute(insert(archive_tables.archive_sources).values(
            project_id=pid, project_name="T", file_path="/tmp/x.json",
            file_mtime=0.0, synced_at=now,
        ))
        conn.execute(insert(archive_tables.archive_agent_memory).values(
            memory_id=f"mem_{sfx}", project_id=pid, archive_id=f"arch_{sfx}",
            agent_id="a1", memory_type="goal",
            normalized_subject="", summary="", detail_json="{}",
            source_kind="", source_ref_id="",
            salience=0.0, memory_layer="canon", status="active",
            version=1, parent_memory_id="",
            source_session_id="", source_branch_id="",
            evidence_json="[]", created_at=now, updated_at=now,
        ))
        conn.execute(insert(archive_tables.archive_agent_memory_events).values(
            event_id=f"ev_{sfx}", project_id=pid, memory_id=f"mem_{sfx}",
            archive_id=f"arch_{sfx}", normalized_subject="",
            memory_type="goal", event_type="adopt",
            memory_layer="canon", status="active", version=1,
            parent_memory_id="", source_session_id="",
            source_branch_id="", summary="", evidence_json="[]",
            created_at=now,
        ))

        # assets
        conn.execute(insert(assets_tables.assets).values(
            asset_id=f"ast_{sfx}", project_id=pid, scope="project",
            asset_type="note", category="", title="笔记",
            summary="", content="", payload_json="{}", tags_json="[]",
            source_kind="manual", source_ref="",
            enabled=1, pinned=0, word_count=0,
            created_at=now, updated_at=now,
        ))
        conn.execute(insert(assets_tables.assets).values(
            asset_id=f"ast_other_{sfx}", project_id=pid, scope="project",
            asset_type="note", category="", title="另一条笔记",
            summary="", content="", payload_json="{}", tags_json="[]",
            source_kind="manual", source_ref="",
            enabled=1, pinned=0, word_count=0,
            created_at=now, updated_at=now,
        ))
        # asset_links — 项目范围的链接必须带 project_id，才会被级联删除命中
        conn.execute(insert(assets_tables.asset_links).values(
            project_id=pid,
            src_asset_id=f"ast_{sfx}", dst_asset_id=f"ast_other_{sfx}",
            relation="references", created_at=now,
        ))

        # novel
        conn.execute(insert(novel_tables.entities).values(
            entity_id=f"e_{sfx}", project_id=pid, name="张三",
            entity_type="character", importance_tier="major",
            profile_json="{}", created_at=now, updated_at=now,
        ))
        conn.execute(insert(novel_tables.scenes).values(
            scene_id=f"sc_{sfx}", project_id=pid, chapter_id=f"ch_{sfx}",
            scene_order=1, title="", content="",
            created_at=now, updated_at=now,
        ))
        conn.execute(insert(novel_tables.plot_threads).values(
            thread_id=f"th_{sfx}", project_id=pid, thread_key="main",
            status="open", detail="",
            created_at=now, updated_at=now,
        ))
        conn.execute(insert(novel_tables.chapter_content).values(
            chapter_id=f"ch_{sfx}", project_id=pid, chapter_order=1,
            title="", content="", word_count=0, status="draft",
            created_at=now, updated_at=now,
        ))
        conn.execute(insert(novel_tables.outline_versions).values(
            version_id=f"v_{sfx}", project_id=pid, chapter_id=f"ch_{sfx}",
            outline_json="[]", label="", created_at=now,
        ))

        # global_index 的 'assets' / 'archive' 行由触发器
        # (migration 20260419_0001) 在上面 assets / archive_library 写入时
        # 自动物化，无需再手动插入。cascade_delete_project 覆盖
        # global_index 的断言依赖这些触发器产出的行。

        # worldline runtime — agent_registry 的 PK 是 (project_id, session_id, branch_id, agent_id)
        conn.execute(insert(worldline_tables.agent_registry).values(
            project_id=pid, session_id="s1", branch_id="main",
            agent_id="a1", agent_kind="character", display_name="张三",
            source_ref="", role="", drive="", tension="",
            status="active", summary="",
            can_chat=1, can_act=1,
            state_json="{}", state_source="", state_version=1,
            last_action_at=None, last_dialogue_at=None,
            source_archive_id=None, source_entity_uuid=None,
            importance_tier="major", template_key="generic.major.v1",
            template_version="v1", template_sections_json="[]",
            created_at=now, updated_at=now,
        ))

        # worldline prepare
        conn.execute(insert(worldline_tables.prepare_runs).values(
            prepare_id=f"p_{sfx}", task_id=f"t_{sfx}", project_id=pid,
            graph_id="", session_scope="new", status="ready", stage="done",
            can_start=1, focus_question="", branch_count=1,
            source_summary_json="{}", source_json="{}",
            world_variables_json="{}", input_payload_json="{}",
            source_archive_ids_json="[]", source_project_ids_json="[]",
            source_archive_count=0, started_session_id="",
            error=None, created_at=now, updated_at=now,
        ))


def _insert_global_asset(engine, now: str = "2026-04-16T10:00:00") -> None:
    """独立插一条 scope=global 的资产，确认级联删除不会碰它。"""
    with engine.begin() as conn:
        conn.execute(insert(assets_tables.assets).values(
            asset_id="ast_global", project_id=None, scope="global",
            asset_type="note", category="", title="全局笔记",
            summary="", content="", payload_json="{}", tags_json="[]",
            source_kind="manual", source_ref="",
            enabled=1, pinned=0, word_count=0,
            created_at=now, updated_at=now,
        ))


def _count(engine, table, project_id: str) -> int:
    with engine.connect() as conn:
        return conn.execute(
            select(func.count()).select_from(table).where(
                table.c.project_id == project_id,
            ),
        ).scalar_one()


def test_cascade_delete_project_clears_all_tables(isolated_engine):
    """插入测试数据 → 调 cascade → 所有项目范围表零行。"""
    engine = isolated_engine
    pid = f"proj_{uuid.uuid4().hex[:12]}"
    other_pid = f"proj_{uuid.uuid4().hex[:12]}"

    _insert_sample_rows(engine, pid)
    _insert_sample_rows(engine, other_pid)  # 同时插另一项目，验证不会误删
    _insert_global_asset(engine)

    stats = cascade_delete_project(pid)

    # 至少这些表应 >0
    # stats["archive_library"] holds the count of archive_entity rows
    # deleted via archive_repo.delete_archives_by_project (P5 compat).
    assert stats.get("archive_library", 0) >= 1
    assert stats.get("entities", 0) >= 1
    assert stats.get("scenes", 0) >= 1
    assert stats.get("assets", 0) >= 1
    assert stats.get("asset_links", 0) >= 1
    assert stats.get("global_index", 0) >= 1
    assert stats.get("agent_registry", 0) >= 1
    assert stats.get("prepare_runs", 0) >= 1

    # 全部项目范围表对 pid 零行
    all_project_tables = [
        t for t in metadata.tables.values() if "project_id" in t.c
    ]
    for table in all_project_tables:
        remaining = _count(engine, table, pid)
        assert remaining == 0, (
            f"table {table.name} 仍残留 {remaining} 条 project_id={pid} 的行"
        )

    # other_pid 的数据未被误删
    assert _count(engine, novel_tables.entities, other_pid) == 1
    # archive_entity now lives in assets; count it via asset_type filter
    with engine.connect() as conn:
        other_archive_count = conn.execute(
            select(func.count()).select_from(assets_tables.assets).where(
                (assets_tables.assets.c.asset_type == "archive_entity")
                & (assets_tables.assets.c.project_id == other_pid),
            ),
        ).scalar_one()
    assert other_archive_count == 1

    # 全局资产（scope=global, project_id=NULL）未被误删
    with engine.connect() as conn:
        global_asset_count = conn.execute(
            select(func.count()).select_from(assets_tables.assets).where(
                assets_tables.assets.c.scope == "global",
            ),
        ).scalar_one()
    assert global_asset_count >= 1


def test_cascade_delete_tables_cover_all_project_scoped(isolated_engine):
    """防漏表看门：metadata 里所有带 project_id 列的表必须被覆盖。"""
    covered = {t.name for t in COVERED_BY_REPO_METHODS}
    covered |= {t.name for t in ALL_PROJECT_SCOPED_TABLES}

    project_scoped_names = {
        t.name for t in metadata.tables.values() if "project_id" in t.c
    }

    missing = project_scoped_names - covered
    assert not missing, (
        f"以下带 project_id 的表未被 cascade_delete_project 覆盖："
        f"{sorted(missing)}。请加入 ALL_PROJECT_SCOPED_TABLES 或相应 repo 方法。"
    )


def test_cascade_delete_project_rejects_empty_id(isolated_engine):
    with pytest.raises(ValueError):
        cascade_delete_project("")
