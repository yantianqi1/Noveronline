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
    (project_dir / "extracted_text.txt").write_text("第一章\n旧项目正文", encoding="utf-8")


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


def test_migrate_seed_json_mirrors_project_artifacts(tmp_path, monkeypatch):
    """Phase G / Task 8: legacy project metadata/text move into DB.

    ``project.json`` lands in ``project_meta.project_json``. Other parseable
    ``*.json`` files plus ``extracted_text.txt`` land in ``project_artifacts``.
    """
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_artifacts"
    project_dir = upload_root / "projects" / project_id
    system_dir = upload_root / "system"
    _seed_project_meta(project_dir, project_id)
    _seed_chapter_segments_json(project_dir)
    # Add several JSONs that have no structured unified-table mapping yet.
    (project_dir / "seed_analysis.json").write_text(
        json.dumps({"characters": [{"name": "Aria"}], "world_rules": ["gravity"]}),
        encoding="utf-8",
    )
    (project_dir / "ontology.json").write_text(
        json.dumps({"entity_types": [{"name": "Character"}]}),
        encoding="utf-8",
    )
    (project_dir / "reviewer_rules.json").write_text(
        json.dumps({"custom_prompt": "be kind"}),
        encoding="utf-8",
    )
    # Malformed JSON is skipped silently (keeps the migration resilient).
    (project_dir / "broken.json").write_text("{ this is not json", encoding="utf-8")
    _seed_legacy_llm_facility(system_dir)
    _seed_legacy_archive_library(system_dir)
    _seed_legacy_assets_library(system_dir)

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    report = migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")

    seed_scope = report[f"seed_json:{project_id}"]
    assert seed_scope["project_meta"] == 1
    # chapter_segments counts as chapter_content + chapter_meta; artifact count
    # covers every successfully-parsed JSON (chapter_segments + seed_analysis
    # + ontology + reviewer_rules = 4; broken.json is excluded) plus
    # extracted_text.
    assert seed_scope["project_artifacts"] == 5

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as connection:
        project_row = connection.execute(
            text("SELECT project_json FROM project_meta WHERE project_id = :pid"),
            {"pid": project_id},
        ).fetchone()
        rows = connection.execute(
            text(
                "SELECT artifact_key, payload_json FROM project_artifacts "
                "WHERE project_id = :pid ORDER BY artifact_key"
            ),
            {"pid": project_id},
        ).fetchall()
    assert project_row is not None
    assert json.loads(project_row[0])["name"] == "FullMigration Demo"
    keys = [row[0] for row in rows]
    assert keys == ["chapter_segments", "extracted_text", "ontology", "reviewer_rules", "seed_analysis"]
    loaded = {row[0]: json.loads(row[1]) for row in rows}
    assert loaded["extracted_text"] == "第一章\n旧项目正文"
    assert loaded["seed_analysis"]["characters"][0]["name"] == "Aria"
    assert loaded["reviewer_rules"] == {"custom_prompt": "be kind"}
    project_payload = json.loads(project_row[0])
    assert project_payload["settings"]["reviewer_rules"]["custom_prompt"] == "be kind"


def test_migrate_seed_json_imports_parallel_world_config_to_project_settings(
    tmp_path, monkeypatch
):
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_parallel_config"
    project_dir = upload_root / "projects" / project_id
    _seed_project_meta(project_dir, project_id)
    (project_dir / "parallel_world_config.json").write_text(
        json.dumps(
            {
                "simulation_goal": "观察密信提前泄露后的单世界演化",
                "timeline_focus": ["起因暴露", "联盟重组"],
                "agent_behavior_axes": ["信息差", "组织利益"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as connection:
        project_row = connection.execute(
            text("SELECT project_json FROM project_meta WHERE project_id = :pid"),
            {"pid": project_id},
        ).fetchone()
    assert project_row is not None
    project_payload = json.loads(project_row[0])
    config = project_payload["settings"]["parallel_world_config"]
    assert config["simulation_goal"] == "观察密信提前泄露后的单世界演化"
    assert config["timeline_focus"] == ["起因暴露", "联盟重组"]


def test_migrate_seed_json_imports_agent_profiles_to_structured_entities(
    tmp_path, monkeypatch
):
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_agent_profiles"
    project_dir = upload_root / "projects" / project_id
    _seed_project_meta(project_dir, project_id)
    (project_dir / "agent_profiles.json").write_text(
        json.dumps(
            {
                "profiles": {
                    "沈夜": {
                        "basic_info": {
                            "name": "沈夜",
                            "identity": "镜湖调查者",
                            "aliases": ["夜行人", "沈先生"],
                        },
                        "speech": {
                            "style": "冷静简短",
                            "verbal_habits": ["先查证。"],
                        },
                        "motivation": {
                            "ultimate_goal": "查清镜湖旧案",
                            "current_objective": "打开地下档案",
                        },
                        "capabilities": {"skills": ["追踪线索", "解读旧档案"]},
                    },
                    "秦昭": {
                        "basic_info": {"name": "秦昭", "identity": "旧盟友"},
                        "motivation": {"current_objective": "隐藏证据"},
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    report = migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")

    assert report[f"seed_json:{project_id}"]["agent_profiles"] == 2

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT name, profile_json, speech_style, current_objective, skills_json "
                "FROM entities WHERE project_id = :pid ORDER BY name"
            ),
            {"pid": project_id},
        ).fetchall()
        aliases = connection.execute(
            text(
                "SELECT alias FROM entity_aliases "
                "WHERE project_id = :pid ORDER BY alias"
            ),
            {"pid": project_id},
        ).fetchall()

    assert [row[0] for row in rows] == ["沈夜", "秦昭"]
    shenye = next(row for row in rows if row[0] == "沈夜")
    profile = json.loads(shenye[1])
    assert profile["basic_info"]["identity"] == "镜湖调查者"
    assert shenye[2] == "冷静简短"
    assert shenye[3] == "打开地下档案"
    assert json.loads(shenye[4]) == ["追踪线索", "解读旧档案"]
    assert [row[0] for row in aliases] == ["夜行人", "沈先生"]


def test_migrated_chapter_context_options_preserve_legacy_continuity_without_artifact_reads(
    tmp_path, monkeypatch
):
    from app.repositories.project_artifact_repo import ProjectArtifactRepository
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_chapter_continuity"
    project_dir = upload_root / "projects" / project_id
    _seed_project_meta(project_dir, project_id)
    _seed_chapter_segments_json(project_dir)
    (project_dir / "chapter_continuity.json").write_text(
        json.dumps(
            {
                "global_summary": "Lin follows the mirror clue into open danger.",
                "chapters": [
                    {
                        "chapter_id": "chapter_0001",
                        "head_context": "Lin wakes with a broken signal.",
                        "continuity_summary": "Lin wakes and chooses to investigate.",
                        "tail_hooks": ["A stranger leaves a mirror clue."],
                    },
                    {
                        "chapter_id": "chapter_0002",
                        "head_context": "Lin follows the mirror clue.",
                        "continuity_summary": "Lin leaves home and enters the old road.",
                        "tail_hooks": ["The old road answers with a name."],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")

    original_load = ProjectArtifactRepository.load

    def fail_on_chapter_artifacts(self, project_id: str, artifact_key: str):
        if artifact_key in {"chapter_segments", "chapter_continuity"}:
            raise AssertionError("migrated chapter context options must not read artifacts")
        return original_load(self, project_id, artifact_key)

    monkeypatch.setattr(ProjectArtifactRepository, "load", fail_on_chapter_artifacts)
    options = ChapterContextPackBuilder().build_options(project_id)

    assert options["continuity_summary"] == "Lin follows the mirror clue into open danger."
    assert [chapter["chapter_id"] for chapter in options["chapters"]] == [
        "chapter_0001",
        "chapter_0002",
    ]
    assert options["chapters"][0]["head_context"] == "Lin wakes with a broken signal."


def test_migrate_seed_json_imports_story_memory_world_rules(tmp_path, monkeypatch):
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_story_memory_rules"
    project_dir = upload_root / "projects" / project_id
    _seed_project_meta(project_dir, project_id)
    (project_dir / "story_memory.json").write_text(
        json.dumps(
            {
                "world_rules": [
                    "镜湖城内夜间禁用传讯符。",
                    "",
                    "沈家血脉能感知旧案残响。",
                    "镜湖城内夜间禁用传讯符。",
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    report = migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")

    assert report[f"seed_json:{project_id}"]["world_rule_evidence"] == 2

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT fact_text, segment_id, evidence_snippet "
                "FROM world_rule_evidence "
                "WHERE project_id = :pid ORDER BY evidence_id"
            ),
            {"pid": project_id},
        ).fetchall()

    assert [row[0] for row in rows] == [
        "镜湖城内夜间禁用传讯符。",
        "沈家血脉能感知旧案残响。",
    ]
    assert {row[1] for row in rows} == {"story_memory"}
    assert [row[2] for row in rows] == [
        "镜湖城内夜间禁用传讯符。",
        "沈家血脉能感知旧案残响。",
    ]


def test_migrate_seed_json_imports_story_memory_open_threads(tmp_path, monkeypatch):
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_story_memory_threads"
    project_dir = upload_root / "projects" / project_id
    _seed_project_meta(project_dir, project_id)
    (project_dir / "story_memory.json").write_text(
        json.dumps(
            {
                "open_threads": [
                    {
                        "thread_key": "镜湖真相",
                        "summary": "镜湖真相仍未查清。",
                        "chapter_id": "chapter_0002",
                    },
                    {
                        "thread_key": "地下档案密钥",
                        "detail": "地下档案密钥来源尚未揭开。",
                        "source_chapter": "3",
                    },
                    {"thread_key": "", "summary": ""},
                    {"thread_key": "镜湖真相", "summary": "重复线索不应重复导入。"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    report = migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")

    assert report[f"seed_json:{project_id}"]["plot_threads"] == 2

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT thread_key, detail, status, source_chapter "
                "FROM plot_threads "
                "WHERE project_id = :pid ORDER BY thread_key"
            ),
            {"pid": project_id},
        ).fetchall()

    assert [tuple(row) for row in rows] == [
        ("地下档案密钥", "地下档案密钥来源尚未揭开。", "open", "3"),
        ("镜湖真相", "镜湖真相仍未查清。", "open", "chapter_0002"),
    ]


def test_migrate_seed_json_imports_story_memory_relationship_ledger(
    tmp_path, monkeypatch
):
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_story_memory_relationships"
    project_dir = upload_root / "projects" / project_id
    _seed_project_meta(project_dir, project_id)
    (project_dir / "story_memory.json").write_text(
        json.dumps(
            {
                "relationship_ledger": [
                    {
                        "source": "沈夜",
                        "target": "秦昭",
                        "relation_type": "ally",
                        "description": "秦昭知道地下档案密钥，但尚未完全信任沈夜。",
                    },
                    {
                        "source": "沈夜",
                        "target": "顾行舟",
                        "changes": [
                            {
                                "change": "rival",
                                "evidence": ["顾行舟提前封锁镜湖谷。"],
                            }
                        ],
                    },
                    {"source": "", "target": "无效", "description": "缺 source 不导入"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    report = migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")

    assert report[f"seed_json:{project_id}"]["relationships"] == 2

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT source_id, target_id, relation_type, description "
                "FROM relationships "
                "WHERE project_id = :pid ORDER BY target_id"
            ),
            {"pid": project_id},
        ).fetchall()

    assert [tuple(row) for row in rows] == [
        ("沈夜", "秦昭", "ally", "秦昭知道地下档案密钥，但尚未完全信任沈夜。"),
        ("沈夜", "顾行舟", "rival", "顾行舟提前封锁镜湖谷。"),
    ]


def test_migrate_seed_json_imports_story_memory_event_timeline(tmp_path, monkeypatch):
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_story_memory_events"
    project_dir = upload_root / "projects" / project_id
    _seed_project_meta(project_dir, project_id)
    (project_dir / "story_memory.json").write_text(
        json.dumps(
            {
                "event_timeline": [
                    {
                        "event_id": "event_001",
                        "summary": "沈夜发现地下档案密钥。",
                        "characters": ["沈夜", "秦昭"],
                        "chapter_order": 2,
                    },
                    {
                        "summary": "顾行舟提前封锁镜湖谷。",
                        "characters": ["顾行舟"],
                        "chapter_id": "chapter_0003",
                    },
                    {"summary": ""},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    report = migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")

    assert report[f"seed_json:{project_id}"]["world_events"] == 2

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT event_id, session_id, branch_id, step, summary, driving_entities_json "
                "FROM world_events "
                "WHERE project_id = :pid ORDER BY event_id"
            ),
            {"pid": project_id},
        ).fetchall()

    assert rows[0][0].endswith("0001")
    assert rows[0][1] == "seed_story_memory"
    assert rows[0][2] == "main"
    assert rows[0][3] == 2
    assert rows[0][4] == "沈夜发现地下档案密钥。"
    assert json.loads(rows[0][5]) == ["沈夜", "秦昭"]
    assert rows[1][3] == 3
    assert rows[1][4] == "顾行舟提前封锁镜湖谷。"


def test_migrate_seed_json_imports_consistency_report_notes(tmp_path, monkeypatch):
    from scripts.migrate_legacy_data import migrate_legacy_data

    upload_root = tmp_path / "uploads"
    project_id = "proj_consistency_report"
    project_dir = upload_root / "projects" / project_id
    _seed_project_meta(project_dir, project_id)
    (project_dir / "consistency_report.json").write_text(
        json.dumps(
            {
                "conflicts": [
                    {
                        "kind": "post_death_activity",
                        "name": "沈临川",
                        "evidence": ["残响中再次出现沈临川的声音。"],
                    }
                ],
                "ambiguities": [
                    {
                        "alias": "夜哥",
                        "candidate_names": ["沈夜", "沈临川"],
                        "reason": "称呼可能混淆两代人。",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "data" / "mirofish.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    report = migrate_legacy_data(upload_root, database_url=f"sqlite:///{db_path}")

    assert report[f"seed_json:{project_id}"]["consistency_notes"] == 2

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT note_text, segment_id "
                "FROM consistency_notes "
                "WHERE project_id = :pid ORDER BY note_id"
            ),
            {"pid": project_id},
        ).fetchall()

    note_texts = [row[0] for row in rows]
    assert any("沈临川" in text and "残响中再次出现沈临川的声音" in text for text in note_texts)
    assert any("夜哥" in text and "沈夜" in text and "沈临川" in text for text in note_texts)
    assert {row[1] for row in rows} == {"consistency_report"}


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
