from pathlib import Path


def _settings(tmp_path, **overrides):
    from app.config import Settings

    values = {
        "DATABASE_URL": f"sqlite:///{tmp_path / 'data' / 'mirofish.db'}",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "ADMIN_SECRET": "",
        "DEBUG": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_fastapi_health_endpoint_returns_service_status(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(settings=_settings(tmp_path))

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "MiroFish-Novel Backend"}


def test_settings_reads_environment_without_losing_legacy_fields(tmp_path, monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'custom.db'}")
    monkeypatch.setenv("ADMIN_SECRET", "secret-token")
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "9")

    settings = Settings()

    assert settings.DATABASE_URL.endswith("custom.db")
    assert settings.ADMIN_SECRET == "secret-token"
    assert settings.LLM_REQUEST_TIMEOUT_SECONDS == 9
    assert settings.ALLOWED_EXTENSIONS == {"pdf", "md", "txt", "markdown"}


def test_init_db_creates_sqlite_database_file(tmp_path):
    from app.config import Settings
    from app.database import create_engine_from_settings, init_db

    db_path = tmp_path / "nested" / "mirofish.db"
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    engine = create_engine_from_settings(settings)

    init_db(engine)

    assert db_path.exists()


def test_admin_secret_protects_llm_write_routes(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app(settings=_settings(tmp_path, ADMIN_SECRET="token")))

    response = client.post("/api/llm/channels", json={})
    health_response = client.get("/health")

    assert response.status_code == 401
    assert response.json()["error"] == "Unauthorized"
    assert health_response.status_code == 200


def test_fastapi_app_serves_legacy_api_contract(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app(settings=_settings(tmp_path)))

    response = client.get("/api/llm/settings")

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_unhandled_errors_use_legacy_error_payload(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(settings=_settings(tmp_path, DEBUG=True))

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaput")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    payload = response.json()

    assert response.status_code == 500
    assert payload["success"] is False
    assert payload["error"] == "kaput"
    assert "RuntimeError" in payload["traceback"]


def test_alembic_bootstrap_imports_unified_metadata():
    backend_root = Path(__file__).parents[1]
    env_py = backend_root / "alembic" / "env.py"

    assert (backend_root / "alembic.ini").exists()
    assert env_py.exists()
    assert (backend_root / "alembic" / "script.py.mako").exists()
    assert "from app.tables import metadata" in env_py.read_text(encoding="utf-8")


def test_unified_metadata_declares_all_regular_tables():
    from app.tables import metadata

    expected = {
        "agent_action_log", "agent_dialogue_log", "agent_episodic_memory",
        "agent_memory", "agent_registry", "agent_state_snapshots",
        "agent_states", "archive_agent_memory",
        "archive_agent_memory_events", "archive_library", "archive_sources",
        "asset_links", "assets", "book_plans", "chapter_content", "chapter_meta",
        "character_events", "classification_map", "consistency_notes",
        "dedup_index", "entities",
        "entity_aliases", "entity_evidence", "entity_labels",
        "global_index", "graph_aliases", "graph_edges", "graph_evidence",
        "graph_meta", "graph_node_labels", "graph_nodes", "llm_channels",
        "llm_models", "llm_module_bindings", "narrative_arcs",
        "outline_versions", "plot_threads", "prepare_event_log",
        "prepare_runs", "prepared_agent_dossiers", "project_artifacts",
        "project_meta",
        "relation_state_log", "relationship_events", "relationships",
        "rule_entity_links", "scenes", "segment_summaries", "sessions",
        "task_runs", "thread_entity_links", "thread_lifecycle",
        "volume_summaries", "world_events", "world_rule_evidence",
        "worldline_branches", "worldline_sessions", "writer_presets",
        "writer_presets_global",
    }

    assert set(metadata.tables) == expected


def test_project_scoped_tables_include_project_id_column():
    from app.tables import metadata

    project_scoped = {
        name
        for name in metadata.tables
        if name not in {
            "llm_channels", "llm_models", "llm_module_bindings",
            "writer_presets_global", "task_runs",
            "classification_map",
        }
    }

    missing = [name for name in sorted(project_scoped) if "project_id" not in metadata.tables[name].c]

    assert missing == []


def test_init_db_creates_sqlite_fts_virtual_tables(tmp_path):
    from sqlalchemy import inspect

    from app.config import Settings
    from app.database import create_engine_from_settings, init_db

    db_path = tmp_path / "fts.db"
    engine = create_engine_from_settings(Settings(DATABASE_URL=f"sqlite:///{db_path}"))

    init_db(engine)

    table_names = set(inspect(engine).get_table_names())
    expected_fts = {
        "agent_memory_fts", "assets_fts", "chapter_content_fts",
        "character_events_fts", "consistency_notes_fts", "entities_fts",
        "entity_evidence_fts", "global_index_fts", "narrative_arcs_fts",
        "plot_threads_fts", "relationship_events_fts", "relationships_fts",
        "scenes_fts", "segment_summaries_fts", "thread_lifecycle_fts",
        "volume_summaries_fts", "world_rule_evidence_fts",
    }

    assert expected_fts.issubset(table_names)


def test_repository_requires_project_id_for_project_scoped_reads(tmp_path):
    from app.config import Settings
    from app.database import create_engine_from_settings, init_db
    from app.repositories.base import ProjectScopedRepository
    from app.tables import metadata

    engine = create_engine_from_settings(Settings(DATABASE_URL=f"sqlite:///{tmp_path / 'repo.db'}"))
    init_db(engine)
    repo = ProjectScopedRepository(engine, metadata.tables["entities"])

    rows = repo.list_by_project("proj_a")

    assert rows == []
    assert "project_id" in repo.project_condition("proj_a").left.name


def test_entity_repository_upserts_and_scopes_by_project(tmp_path):
    from app.config import Settings
    from app.database import create_engine_from_settings, init_db
    from app.repositories.entity_repo import EntityRepository

    engine = create_engine_from_settings(Settings(DATABASE_URL=f"sqlite:///{tmp_path / 'entity.db'}"))
    init_db(engine)
    repo = EntityRepository(engine)
    base = {"entity_type": "Character", "created_at": "2026-04-12T00:00:00", "updated_at": "2026-04-12T00:00:00"}

    repo.upsert_entity("proj_a", {"entity_id": "char_1", "name": "沈夜", **base})
    repo.upsert_entity("proj_b", {"entity_id": "char_1", "name": "另一个沈夜", **base})
    repo.upsert_entity("proj_a", {"entity_id": "char_1", "name": "沈夜改", **base})

    assert repo.get_entity("proj_a", "char_1")["name"] == "沈夜改"
    assert repo.get_entity("proj_b", "char_1")["name"] == "另一个沈夜"
    assert [row["entity_id"] for row in repo.list_entities("proj_a")] == ["char_1"]
