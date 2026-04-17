from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, text

from app.database import init_db


def _project_dir(upload_root: Path, project_id: str) -> Path:
    project_dir = upload_root / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def _write_project_meta(project_dir: Path, project_id: str) -> None:
    (project_dir / "project.json").write_text(
        json.dumps({"project_id": project_id, "name": "Verifier Demo"}, ensure_ascii=False),
        encoding="utf-8",
    )


def _create_legacy_novel_db(path: Path, *, entity_name: str = "Lin", entity_summary: str = "Hero") -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                summary TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO entities (entity_id, name, entity_type, summary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("ent_1", entity_name, "character", entity_summary, "2026-04-14T00:00:00", "2026-04-14T00:00:00"),
        )
        conn.commit()
    finally:
        conn.close()


def _create_legacy_graph_db(path: Path, *, summary: str = "Lead node") -> None:
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
            """
            INSERT INTO graph_nodes (uuid, name, summary, attributes_json, evidence_refs_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("node_1", "Lin", summary, "{}", "[]"),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_matching_unified_rows(engine, project_id: str, *, entity_summary: str = "Hero", graph_summary: str = "Lead node") -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO entities (
                    entity_id, project_id, name, entity_type, summary, created_at, updated_at
                ) VALUES (
                    :entity_id, :project_id, :name, :entity_type, :summary, :created_at, :updated_at
                )
                """
            ),
            {
                "entity_id": "ent_1",
                "project_id": project_id,
                "name": "Lin",
                "entity_type": "character",
                "summary": entity_summary,
                "created_at": "2026-04-14T00:00:00",
                "updated_at": "2026-04-14T00:00:00",
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO graph_nodes (
                    project_id, uuid, name, summary, attributes_json, evidence_refs_json
                ) VALUES (
                    :project_id, :uuid, :name, :summary, :attributes_json, :evidence_refs_json
                )
                """
            ),
            {
                "project_id": project_id,
                "uuid": "node_1",
                "name": "Lin",
                "summary": graph_summary,
                "attributes_json": "{}",
                "evidence_refs_json": "[]",
            },
        )


def test_verify_project_returns_pass_report_for_matching_data(tmp_path):
    from app.services.migration_verifier import MigrationVerifier

    upload_root = tmp_path / "uploads"
    project_id = "proj_demo"
    project_dir = _project_dir(upload_root, project_id)
    _write_project_meta(project_dir, project_id)
    _create_legacy_novel_db(project_dir / "novel.sqlite3")
    _create_legacy_graph_db(project_dir / "story_graph.sqlite3")

    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    _insert_matching_unified_rows(engine, project_id)

    report = MigrationVerifier(upload_root=upload_root, engine=engine).verify_project(project_id)

    assert report["project_id"] == project_id
    assert report["overall_verdict"] == "pass"
    assert report["legacy_sources"]["project_meta"]["exists"] is True
    assert report["legacy_sources"]["novel_db"]["exists"] is True
    assert report["legacy_sources"]["story_graph_db"]["exists"] is True
    assert report["domains"]["novel"]["status"] == "pass"
    assert report["domains"]["story_graph"]["status"] == "pass"
    assert report["domains"]["novel"]["legacy_row_count"] == 1
    assert report["domains"]["novel"]["unified_row_count"] == 1
    assert report["domains"]["novel"]["mismatch_count"] == 0
    assert report["domains"]["story_graph"]["tables"][0]["table"] == "graph_nodes"


def test_verify_project_reports_missing_rows_and_field_mismatches(tmp_path):
    from app.services.migration_verifier import MigrationVerifier

    upload_root = tmp_path / "uploads"
    project_id = "proj_problem"
    project_dir = _project_dir(upload_root, project_id)
    _write_project_meta(project_dir, project_id)
    _create_legacy_novel_db(project_dir / "novel.sqlite3", entity_summary="Legacy Hero")
    _create_legacy_graph_db(project_dir / "story_graph.sqlite3", summary="Legacy Node")

    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    _insert_matching_unified_rows(engine, project_id, entity_summary="Unified Hero", graph_summary="Changed Node")
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM graph_nodes WHERE project_id = :project_id"), {"project_id": project_id})

    report = MigrationVerifier(upload_root=upload_root, engine=engine).verify_project(project_id)

    assert report["overall_verdict"] == "fail"
    assert report["risk_level"] == "high"

    novel_domain = report["domains"]["novel"]
    assert novel_domain["status"] == "fail"
    assert novel_domain["mismatch_count"] == 1
    assert novel_domain["tables"][0]["field_mismatches"][0]["primary_key"] == {"entity_id": "ent_1"}
    assert novel_domain["tables"][0]["field_mismatches"][0]["differing_fields"] == ["summary"]

    graph_domain = report["domains"]["story_graph"]
    assert graph_domain["status"] == "fail"
    assert graph_domain["missing_in_unified_count"] == 1
    assert graph_domain["tables"][0]["missing_in_unified"][0] == {"uuid": "node_1"}


def test_verify_project_migration_cli_prints_json(tmp_path, capsys):
    from scripts.verify_project_migration import main

    upload_root = tmp_path / "uploads"
    project_id = "proj_cli"
    project_dir = _project_dir(upload_root, project_id)
    _write_project_meta(project_dir, project_id)
    _create_legacy_novel_db(project_dir / "novel.sqlite3")
    _create_legacy_graph_db(project_dir / "story_graph.sqlite3")

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)
    _insert_matching_unified_rows(engine, project_id)

    exit_code = main(
        [
            "--project-id",
            project_id,
            "--upload-root",
            str(upload_root),
            "--database-url",
            f"sqlite:///{db_path}",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["project_id"] == project_id
    assert payload["overall_verdict"] == "pass"


def _create_legacy_project_assets_db(path: Path, *, project_id: str = "proj_demo", asset_title: str = "Codex") -> None:
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
            """
            INSERT INTO assets (
                asset_id, project_id, scope, asset_type, category, title,
                summary, content, payload_json, tags_json, source_kind,
                source_ref, enabled, pinned, word_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "asset_1", project_id, "project", "style", "", asset_title,
                "", "", "{}", "[]", "", "", 1, 0, 0,
                "2026-04-17T00:00:00", "2026-04-17T00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _create_legacy_worldline_runtime_db(path: Path, *, project_id: str = "proj_demo") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            """
            INSERT INTO agent_registry (
                project_id, session_id, branch_id, agent_id, agent_kind, display_name,
                source_ref, role, drive, tension, status, summary, can_chat, can_act,
                state_json, state_source, state_version, importance_tier, template_key,
                template_version, template_sections_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id, "sess_1", "br_1", "agent_1", "character", "Lin",
                "entity:ent_1", "protagonist", "ambition", "burden", "active", "",
                1, 1, "{}", "snapshot", 1, "protagonist", "generic.protagonist.v1",
                "v1", "[]", "2026-04-17T00:00:00", "2026-04-17T00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _create_legacy_llm_facility_db(path: Path, *, channel_key: str = "ch_1") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            """
            INSERT INTO llm_channels (
                channel_key, name, base_url, api_key, max_concurrency, is_enabled,
                created_at, updated_at, last_sync_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                channel_key, "Default", "https://api.example.com", "sk-x", 4, 1,
                "2026-04-17T00:00:00", "2026-04-17T00:00:00", "idle",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _create_legacy_archive_library_db(path: Path, *, project_id: str = "proj_demo") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            """
            INSERT INTO archive_library (
                archive_id, project_id, project_name, entity_uuid, entity_name,
                entity_type, importance_tier, entity_role, core_drive, surface_mask,
                hidden_tension, relationship_summary, agent_behavior_hint,
                human_ai_relation_tag, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "arc_1", project_id, "Demo", "ent_1", "Lin", "character",
                "protagonist", "hero", "courage", "calm", "regret", "", "", "none",
                "2026-04-17T00:00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_matching_project_assets_row(engine, project_id: str, *, asset_title: str = "Codex") -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO assets (
                    asset_id, project_id, scope, asset_type, category, title,
                    summary, content, payload_json, tags_json, source_kind,
                    source_ref, enabled, pinned, word_count, created_at, updated_at
                ) VALUES (
                    :asset_id, :project_id, :scope, :asset_type, :category, :title,
                    :summary, :content, :payload_json, :tags_json, :source_kind,
                    :source_ref, :enabled, :pinned, :word_count, :created_at, :updated_at
                )
                """
            ),
            {
                "asset_id": "asset_1", "project_id": project_id, "scope": "project",
                "asset_type": "style", "category": "", "title": asset_title,
                "summary": "", "content": "", "payload_json": "{}",
                "tags_json": "[]", "source_kind": "", "source_ref": "",
                "enabled": 1, "pinned": 0, "word_count": 0,
                "created_at": "2026-04-17T00:00:00", "updated_at": "2026-04-17T00:00:00",
            },
        )


def _insert_matching_worldline_runtime_row(engine, project_id: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO agent_registry (
                    project_id, session_id, branch_id, agent_id, agent_kind, display_name,
                    source_ref, role, drive, tension, status, summary, can_chat, can_act,
                    state_json, state_source, state_version, importance_tier, template_key,
                    template_version, template_sections_json, created_at, updated_at
                ) VALUES (
                    :project_id, :session_id, :branch_id, :agent_id, :agent_kind, :display_name,
                    :source_ref, :role, :drive, :tension, :status, :summary, :can_chat, :can_act,
                    :state_json, :state_source, :state_version, :importance_tier, :template_key,
                    :template_version, :template_sections_json, :created_at, :updated_at
                )
                """
            ),
            {
                "project_id": project_id, "session_id": "sess_1", "branch_id": "br_1",
                "agent_id": "agent_1", "agent_kind": "character", "display_name": "Lin",
                "source_ref": "entity:ent_1", "role": "protagonist", "drive": "ambition",
                "tension": "burden", "status": "active", "summary": "",
                "can_chat": 1, "can_act": 1, "state_json": "{}", "state_source": "snapshot",
                "state_version": 1, "importance_tier": "protagonist",
                "template_key": "generic.protagonist.v1", "template_version": "v1",
                "template_sections_json": "[]",
                "created_at": "2026-04-17T00:00:00", "updated_at": "2026-04-17T00:00:00",
            },
        )


def _insert_matching_llm_channel_row(engine, *, channel_key: str = "ch_1") -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO llm_channels (
                    channel_key, name, base_url, api_key, max_concurrency, is_enabled,
                    created_at, updated_at, last_sync_status
                ) VALUES (
                    :channel_key, :name, :base_url, :api_key, :max_concurrency, :is_enabled,
                    :created_at, :updated_at, :last_sync_status
                )
                """
            ),
            {
                "channel_key": channel_key, "name": "Default", "base_url": "https://api.example.com",
                "api_key": "sk-x", "max_concurrency": 4, "is_enabled": 1,
                "created_at": "2026-04-17T00:00:00", "updated_at": "2026-04-17T00:00:00",
                "last_sync_status": "idle",
            },
        )


def _insert_matching_archive_row(engine, project_id: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO archive_library (
                    archive_id, project_id, project_name, entity_uuid, entity_name,
                    entity_type, importance_tier, entity_role, core_drive, surface_mask,
                    hidden_tension, relationship_summary, agent_behavior_hint,
                    human_ai_relation_tag, synced_at
                ) VALUES (
                    :archive_id, :project_id, :project_name, :entity_uuid, :entity_name,
                    :entity_type, :importance_tier, :entity_role, :core_drive, :surface_mask,
                    :hidden_tension, :relationship_summary, :agent_behavior_hint,
                    :human_ai_relation_tag, :synced_at
                )
                """
            ),
            {
                "archive_id": "arc_1", "project_id": project_id, "project_name": "Demo",
                "entity_uuid": "ent_1", "entity_name": "Lin", "entity_type": "character",
                "importance_tier": "protagonist", "entity_role": "hero",
                "core_drive": "courage", "surface_mask": "calm", "hidden_tension": "regret",
                "relationship_summary": "", "agent_behavior_hint": "",
                "human_ai_relation_tag": "none", "synced_at": "2026-04-17T00:00:00",
            },
        )


def test_verify_project_assets_domain(tmp_path):
    from app.services.migration_verifier import MigrationVerifier

    upload_root = tmp_path / "uploads"
    project_id = "proj_pa"
    project_dir = _project_dir(upload_root, project_id)
    _write_project_meta(project_dir, project_id)
    _create_legacy_project_assets_db(project_dir / "project_assets.sqlite3", project_id=project_id)

    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    _insert_matching_project_assets_row(engine, project_id)

    report = MigrationVerifier(upload_root=upload_root, engine=engine).verify_project(project_id)

    assert report["legacy_sources"]["project_assets_db"]["exists"] is True
    pa_domain = report["domains"]["project_assets"]
    assert pa_domain["source_available"] is True
    assert pa_domain["status"] == "pass"
    assert pa_domain["legacy_row_count"] == 1
    assert pa_domain["unified_row_count"] == 1
    assert pa_domain["mismatch_count"] == 0


def test_verify_worldline_runtime_domain(tmp_path):
    from app.services.migration_verifier import MigrationVerifier

    upload_root = tmp_path / "uploads"
    project_id = "proj_wl"
    project_dir = _project_dir(upload_root, project_id)
    _write_project_meta(project_dir, project_id)
    _create_legacy_worldline_runtime_db(project_dir / "worldlines" / "runtime.sqlite3", project_id=project_id)

    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    _insert_matching_worldline_runtime_row(engine, project_id)

    report = MigrationVerifier(upload_root=upload_root, engine=engine).verify_project(project_id)

    assert report["legacy_sources"]["worldline_runtime_db"]["exists"] is True
    wl_domain = report["domains"]["worldline_runtime"]
    assert wl_domain["source_available"] is True
    assert wl_domain["status"] == "pass"
    assert wl_domain["legacy_row_count"] == 1
    assert wl_domain["unified_row_count"] == 1


def test_verify_global_llm_facility_pass(tmp_path):
    from app.services.migration_verifier import MigrationVerifier

    upload_root = tmp_path / "uploads"
    system_dir = upload_root / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    _create_legacy_llm_facility_db(system_dir / "llm_facility.sqlite3")

    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    _insert_matching_llm_channel_row(engine)

    report = MigrationVerifier(upload_root=upload_root, engine=engine).verify_global()

    assert report["scope"] == "global"
    assert report["legacy_sources"]["llm_facility_db"]["exists"] is True
    llm_domain = report["domains"]["llm_facility"]
    assert llm_domain["source_available"] is True
    assert llm_domain["status"] == "pass"
    assert llm_domain["legacy_row_count"] == 1
    assert llm_domain["unified_row_count"] == 1


def test_verify_global_archive_library_detects_mismatch(tmp_path):
    from app.services.migration_verifier import MigrationVerifier

    upload_root = tmp_path / "uploads"
    system_dir = upload_root / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    _create_legacy_archive_library_db(system_dir / "archive_library.sqlite3", project_id="proj_arc")

    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)

    report = MigrationVerifier(upload_root=upload_root, engine=engine).verify_global()

    archive_domain = report["domains"]["archive_library"]
    assert archive_domain["source_available"] is True
    assert archive_domain["status"] == "fail"
    assert archive_domain["missing_in_unified_count"] == 1
    assert report["overall_verdict"] == "fail"


def test_verify_project_migration_cli_include_global(tmp_path, capsys):
    from scripts.verify_project_migration import main

    upload_root = tmp_path / "uploads"
    project_id = "proj_cli_global"
    project_dir = _project_dir(upload_root, project_id)
    _write_project_meta(project_dir, project_id)
    _create_legacy_novel_db(project_dir / "novel.sqlite3")
    _create_legacy_graph_db(project_dir / "story_graph.sqlite3")

    system_dir = upload_root / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    _create_legacy_llm_facility_db(system_dir / "llm_facility.sqlite3")

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)
    _insert_matching_unified_rows(engine, project_id)
    _insert_matching_llm_channel_row(engine)

    exit_code = main(
        [
            "--project-id", project_id,
            "--upload-root", str(upload_root),
            "--database-url", f"sqlite:///{db_path}",
            "--include-global",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["overall_verdict"] == "pass"
    assert payload["global"]["overall_verdict"] == "pass"
    assert payload["global"]["domains"]["llm_facility"]["status"] == "pass"
