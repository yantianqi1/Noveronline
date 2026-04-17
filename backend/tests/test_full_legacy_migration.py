"""End-to-end smoke tests for the multi-domain legacy migration."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, text

from app.database import init_db


# ---------------------------------------------------------------------------
# Fixture builders — tiny legacy sqlite / JSON files covering every domain
# ---------------------------------------------------------------------------


def _seed_project_meta(project_dir: Path, project_id: str) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.json").write_text(
        json.dumps({"project_id": project_id, "name": "FullMigration Demo"}, ensure_ascii=False),
        encoding="utf-8",
    )


def _seed_legacy_novel(project_dir: Path) -> None:
    path = project_dir / "novel.sqlite3"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                summary TEXT,
                profile_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO entities (entity_id, name, entity_type, summary, profile_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "ent_hero",
                "Lin",
                "character",
                "Protagonist",
                "{}",
                "2026-04-17T00:00:00",
                "2026-04-17T00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_legacy_graph(project_dir: Path) -> None:
    path = project_dir / "story_graph.sqlite3"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE graph_nodes (
                uuid TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                summary TEXT NOT NULL,
                attributes_json TEXT NOT NULL,
                evidence_refs_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO graph_nodes (uuid, name, summary, attributes_json, evidence_refs_json) "
            "VALUES (?, ?, ?, ?, ?)",
            ("node_hero", "Lin", "Protagonist node", "{}", "[]"),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_legacy_project_assets(project_dir: Path, project_id: str) -> None:
    path = project_dir / "project_assets.sqlite3"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE assets (
                asset_id TEXT PRIMARY KEY,
                project_id TEXT,
                scope TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                tags_json TEXT NOT NULL DEFAULT '[]',
                source_kind TEXT NOT NULL DEFAULT '',
                source_ref TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                pinned INTEGER NOT NULL DEFAULT 0,
                word_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO assets (asset_id, project_id, scope, asset_type, category, title, summary, content, "
            "payload_json, tags_json, source_kind, source_ref, enabled, pinned, word_count, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "asset_proj",
                project_id,
                "project",
                "style",
                "",
                "Codex",
                "",
                "",
                "{}",
                "[]",
                "",
                "",
                1,
                0,
                0,
                "2026-04-17T00:00:00",
                "2026-04-17T00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_legacy_worldline_runtime(project_dir: Path, project_id: str) -> None:
    worldlines_dir = project_dir / "worldlines"
    worldlines_dir.mkdir(parents=True, exist_ok=True)
    path = worldlines_dir / "runtime.sqlite3"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE agent_registry (
                project_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                branch_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                agent_kind TEXT NOT NULL,
                display_name TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                role TEXT NOT NULL,
                drive TEXT NOT NULL,
                tension TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                can_chat INTEGER NOT NULL,
                can_act INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                state_source TEXT NOT NULL,
                state_version INTEGER NOT NULL,
                last_action_at TEXT,
                last_dialogue_at TEXT,
                source_archive_id TEXT,
                source_entity_uuid TEXT,
                importance_tier TEXT NOT NULL DEFAULT 'supporting',
                template_key TEXT NOT NULL DEFAULT 'generic.supporting.v1',
                template_version TEXT NOT NULL DEFAULT 'v1',
                template_sections_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (project_id, session_id, branch_id, agent_id)
            )
            """
        )
        conn.execute(
            "INSERT INTO agent_registry (project_id, session_id, branch_id, agent_id, agent_kind, display_name, "
            "source_ref, role, drive, tension, status, summary, can_chat, can_act, state_json, state_source, "
            "state_version, importance_tier, template_key, template_version, template_sections_json, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                "sess_main",
                "br_main",
                "agent_hero",
                "character",
                "Lin",
                "entity:ent_hero",
                "protagonist",
                "ambition",
                "regret",
                "active",
                "",
                1,
                1,
                "{}",
                "snapshot",
                1,
                "protagonist",
                "generic.protagonist.v1",
                "v1",
                "[]",
                "2026-04-17T00:00:00",
                "2026-04-17T00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_chapter_segments_json(project_dir: Path) -> None:
    payload = {
        "chapter_count": 2,
        "chapters": [
            {
                "chapter_id": "chapter_0001",
                "order": 1,
                "title": "Origin",
                "content": "Lin awakens.",
                "word_count": 12,
            },
            {
                "chapter_id": "chapter_0002",
                "order": 2,
                "title": "Departure",
                "content": "Lin sets out.",
                "word_count": 14,
            },
        ],
        "sentence_atlas": {},
    }
    (project_dir / "chapter_segments.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _seed_legacy_llm_facility(system_dir: Path) -> None:
    system_dir.mkdir(parents=True, exist_ok=True)
    path = system_dir / "llm_facility.sqlite3"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE llm_channels (
                channel_key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                base_url TEXT NOT NULL,
                api_key TEXT NOT NULL,
                max_concurrency INTEGER NOT NULL DEFAULT 4,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_sync_at TEXT,
                last_sync_status TEXT NOT NULL DEFAULT 'idle',
                last_sync_error TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO llm_channels (channel_key, name, base_url, api_key, max_concurrency, is_enabled, "
            "created_at, updated_at, last_sync_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ch_default",
                "Default",
                "https://api.example.com",
                "sk-xxx",
                4,
                1,
                "2026-04-17T00:00:00",
                "2026-04-17T00:00:00",
                "idle",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_legacy_archive_library(system_dir: Path) -> None:
    system_dir.mkdir(parents=True, exist_ok=True)
    path = system_dir / "archive_library.sqlite3"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE archive_library (
                archive_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                project_name TEXT NOT NULL,
                entity_uuid TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                agent_kind TEXT NOT NULL DEFAULT 'generic',
                importance_tier TEXT NOT NULL,
                recommended_importance_tier TEXT NOT NULL DEFAULT 'supporting',
                selected_importance_tier TEXT NOT NULL DEFAULT 'supporting',
                template_key TEXT NOT NULL DEFAULT 'generic.supporting.v1',
                template_version TEXT NOT NULL DEFAULT 'v1',
                entity_role TEXT NOT NULL,
                core_drive TEXT NOT NULL,
                surface_mask TEXT NOT NULL,
                hidden_tension TEXT NOT NULL,
                relationship_summary TEXT NOT NULL,
                agent_behavior_hint TEXT NOT NULL,
                human_ai_relation_tag TEXT NOT NULL,
                can_act_as_agent INTEGER NOT NULL DEFAULT 1,
                notable_risks_json TEXT NOT NULL DEFAULT '[]',
                template_sections_json TEXT NOT NULL DEFAULT '[]',
                template_payload_json TEXT NOT NULL DEFAULT '{}',
                template_metadata_json TEXT NOT NULL DEFAULT '{}',
                synced_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO archive_library (archive_id, project_id, project_name, entity_uuid, entity_name, "
            "entity_type, importance_tier, entity_role, core_drive, surface_mask, hidden_tension, "
            "relationship_summary, agent_behavior_hint, human_ai_relation_tag, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "arc_hero",
                "proj_fullmig",
                "FullMigration Demo",
                "ent_hero",
                "Lin",
                "character",
                "protagonist",
                "hero",
                "courage",
                "calm",
                "regret",
                "",
                "",
                "none",
                "2026-04-17T00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_legacy_assets_library(system_dir: Path) -> None:
    system_dir.mkdir(parents=True, exist_ok=True)
    path = system_dir / "assets_library.sqlite3"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE assets (
                asset_id TEXT PRIMARY KEY,
                project_id TEXT,
                scope TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                tags_json TEXT NOT NULL DEFAULT '[]',
                source_kind TEXT NOT NULL DEFAULT '',
                source_ref TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                pinned INTEGER NOT NULL DEFAULT 0,
                word_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO assets (asset_id, project_id, scope, asset_type, category, title, summary, content, "
            "payload_json, tags_json, source_kind, source_ref, enabled, pinned, word_count, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "asset_global",
                None,
                "global",
                "style",
                "",
                "Global Preset",
                "",
                "",
                "{}",
                "[]",
                "",
                "",
                1,
                0,
                0,
                "2026-04-17T00:00:00",
                "2026-04-17T00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_all_legacy(upload_root: Path, project_id: str) -> None:
    project_dir = upload_root / "projects" / project_id
    system_dir = upload_root / "system"
    _seed_project_meta(project_dir, project_id)
    _seed_legacy_novel(project_dir)
    _seed_legacy_graph(project_dir)
    _seed_legacy_project_assets(project_dir, project_id)
    _seed_legacy_worldline_runtime(project_dir, project_id)
    _seed_chapter_segments_json(project_dir)
    _seed_legacy_llm_facility(system_dir)
    _seed_legacy_archive_library(system_dir)
    _seed_legacy_assets_library(system_dir)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_migrate_legacy_data_covers_all_domains(tmp_path, monkeypatch):
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_fullmig"
    _seed_all_legacy(upload_root, project_id)

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    report = migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")

    scopes = set(report.keys())
    assert f"novel:{project_id}" in scopes
    assert f"story_graph:{project_id}" in scopes
    assert f"project_assets:{project_id}" in scopes
    assert f"worldline_runtime:{project_id}" in scopes
    assert f"seed_json:{project_id}" in scopes
    assert "llm_facility:__global__" in scopes
    assert "archive_library:__global__" in scopes
    assert "assets_library:__global__" in scopes

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM entities WHERE project_id = :pid"), {"pid": project_id}
        ).scalar() == 1
        assert connection.execute(
            text("SELECT COUNT(*) FROM graph_nodes WHERE project_id = :pid"), {"pid": project_id}
        ).scalar() == 1
        assert connection.execute(
            text("SELECT COUNT(*) FROM assets WHERE project_id = :pid"), {"pid": project_id}
        ).scalar() == 1
        assert connection.execute(
            text("SELECT COUNT(*) FROM agent_registry WHERE project_id = :pid"), {"pid": project_id}
        ).scalar() == 1
        assert connection.execute(
            text("SELECT COUNT(*) FROM chapter_content WHERE project_id = :pid"), {"pid": project_id}
        ).scalar() == 2
        assert connection.execute(
            text("SELECT COUNT(*) FROM chapter_meta WHERE project_id = :pid"), {"pid": project_id}
        ).scalar() == 2
        assert connection.execute(text("SELECT COUNT(*) FROM llm_channels")).scalar() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM archive_library")).scalar() == 1
        global_assets = connection.execute(
            text("SELECT COUNT(*) FROM assets WHERE asset_id = 'asset_global'")
        ).scalar()
        assert global_assets == 1


def test_migrate_legacy_data_is_idempotent(tmp_path, monkeypatch):
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_idem"
    _seed_all_legacy(upload_root, project_id)

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")
    migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM entities WHERE project_id = :pid"), {"pid": project_id}
        ).scalar() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM llm_channels")).scalar() == 1
        assert connection.execute(
            text("SELECT COUNT(*) FROM chapter_content WHERE project_id = :pid"), {"pid": project_id}
        ).scalar() == 2


def test_migrate_legacy_data_dry_run_counts_without_writing(tmp_path, monkeypatch):
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_dry"
    _seed_all_legacy(upload_root, project_id)

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    report = migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}", dry_run=True)

    assert report[f"novel:{project_id}"]["entities"] == 1
    assert report["llm_facility:__global__"]["llm_channels"] == 1
    assert report[f"seed_json:{project_id}"]["chapter_content"] == 2

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM entities")).scalar() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM llm_channels")).scalar() == 0


def test_migrate_legacy_data_report_passes_verifier(tmp_path, monkeypatch):
    from app.services.migration_verifier import MigrationVerifier
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_verify"
    _seed_all_legacy(upload_root, project_id)

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)
    verifier = MigrationVerifier(upload_root=upload_root, engine=engine)

    project_report = verifier.verify_project(project_id)
    assert project_report["overall_verdict"] == "pass"
    assert project_report["domains"]["novel"]["status"] == "pass"
    assert project_report["domains"]["story_graph"]["status"] == "pass"
    assert project_report["domains"]["project_assets"]["status"] == "pass"
    assert project_report["domains"]["worldline_runtime"]["status"] == "pass"

    global_report = verifier.verify_global()
    assert global_report["overall_verdict"] == "pass"
    assert global_report["domains"]["llm_facility"]["status"] == "pass"
    assert global_report["domains"]["archive_library"]["status"] == "pass"
    assert global_report["domains"]["assets_library"]["status"] == "pass"
