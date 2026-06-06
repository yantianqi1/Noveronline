import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, select

from migrations.import_only import run_import_only


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_llm_facility_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        """
        create table llm_channels (
          channel_key text primary key,
          name text not null,
          base_url text not null,
          api_key text not null,
          max_concurrency integer not null,
          is_enabled integer not null,
          created_at text not null,
          updated_at text not null,
          last_sync_at text,
          last_sync_status text not null,
          last_sync_error text
        )
        """
    )
    connection.execute(
        """
        create table llm_models (
          channel_key text not null,
          model_id text not null,
          owned_by text,
          fetched_at text not null,
          raw_payload text not null
        )
        """
    )
    connection.execute(
        """
        create table llm_module_bindings (
          module_key text primary key,
          channel_key text not null,
          model_id text not null,
          updated_at text not null
        )
        """
    )
    connection.execute(
        """
        insert into llm_channels
        (channel_key, name, base_url, api_key, max_concurrency, is_enabled, created_at, updated_at, last_sync_at, last_sync_status, last_sync_error)
        values
        ('openai_main', 'OpenAI Main', 'https://api.openai.com/v1', 'sk-test-123', 4, 1, '2026-04-11T00:00:00', '2026-04-11T00:00:00', '2026-04-11T00:01:00', 'success', null)
        """
    )
    connection.execute(
        """
        insert into llm_models (channel_key, model_id, owned_by, fetched_at, raw_payload)
        values ('openai_main', 'gpt-4.1', 'openai', '2026-04-11T00:01:00', '{"id":"gpt-4.1"}')
        """
    )
    connection.execute(
        """
        insert into llm_module_bindings (module_key, channel_key, model_id, updated_at)
        values ('story_ontology', 'openai_main', 'gpt-4.1', '2026-04-11T00:02:00')
        """
    )
    connection.commit()
    connection.close()


def test_import_only_imports_llm_facility_sqlite(tmp_path):
    uploads = tmp_path / "uploads"
    db_path = tmp_path / "import.db"
    write_text(
        uploads / "projects" / "proj_demo" / "project.json",
        '{"project_id":"proj_demo","name":"LLM导入项目","status":"created","created_at":"2026-04-11T00:00:00","updated_at":"2026-04-11T00:00:00"}',
    )
    create_llm_facility_db(uploads / "system" / "llm_facility.sqlite3")

    report = run_import_only(uploads, f"sqlite:///{db_path}")

    assert "system/llm_facility.sqlite3 -> llm_channels+llm_models+llm_module_bindings" not in report.blocked_targets

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        providers = connection.execute(select(report.metadata.tables["llm_providers"])).all()
        channels = connection.execute(select(report.metadata.tables["llm_channels"])).all()
        models = connection.execute(select(report.metadata.tables["llm_models"])).all()
        bindings = connection.execute(select(report.metadata.tables["llm_module_bindings"])).all()

    assert len(providers) == 1
    assert providers[0].auth_secret_ref.startswith("secret://legacy-llm/")
    assert len(channels) == 1
    assert channels[0].channel_key == "openai_main"
    assert len(models) == 1
    assert models[0].provider_model_id == "gpt-4.1"
    assert len(bindings) == 1
    assert bindings[0].module_key == "story_ontology"
