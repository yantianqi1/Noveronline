import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bootstrap.app_factory import create_app
from src.bootstrap.settings import AppSettings
from src.shared.db.base import metadata


def make_settings(database_url: str) -> AppSettings:
    return AppSettings.model_construct(
        app_name="MiroFish-Novel API v2",
        api_prefix="/api/v2",
        env="test",
        host="127.0.0.1",
        port=5102,
        redis_url="redis://127.0.0.1:6379/0",
        temporal_target="127.0.0.1:7233",
        database_url_override=database_url,
    )


def seed_llm_command_database(database_url: str) -> None:
    now = datetime(2026, 4, 12, tzinfo=timezone.utc)
    engine = create_engine(database_url)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            metadata.tables["llm_providers"].insert().values(
                llm_provider_id="provider_1",
                provider_key="openai_main",
                provider_type="openai-compatible",
                name="OpenAI Main",
                base_url="https://api.openai.com/v1",
                auth_secret_ref="inline-secret:sk-test-123456",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["llm_channels"].insert().values(
                llm_channel_id="channel_1",
                llm_provider_id="provider_1",
                channel_key="openai_main",
                name="OpenAI Main",
                max_concurrency=4,
                timeout_ms=60000,
                is_enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["llm_models"].insert().values(
                llm_model_id="model_1",
                llm_channel_id="channel_1",
                provider_model_id="gpt-4.1",
                display_name="GPT-4.1",
                synced_at=now,
            )
        )


def test_llm_commands_create_update_channel_and_bind_module(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'llm_commands.db'}"
    seed_llm_command_database(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    create_response = client.post(
        "/api/v2/llm/channels",
        json={
            "name": "OpenAI Backup",
            "base_url": "https://backup.example.com/v1",
            "api_key": "sk-backup-123456",
            "is_enabled": True,
            "max_concurrency": 5,
            "timeout_ms": 45000,
        },
    )
    assert create_response.status_code == 201, create_response.json()
    created = create_response.json()["data"]
    assert created["channel_key"].startswith("channel_")
    assert created["api_key_masked"].startswith("sk-")
    assert created["max_concurrency"] == 5

    update_response = client.patch(
        "/api/v2/llm/channels/openai_main",
        json={"max_concurrency": 9, "is_enabled": False},
    )
    assert update_response.status_code == 200, update_response.json()
    updated = update_response.json()["data"]
    assert updated["max_concurrency"] == 9
    assert updated["is_enabled"] is False

    failed_binding = client.put(
        "/api/v2/llm/module-bindings/story_ontology",
        json={"llm_channel_id": "channel_1", "llm_model_id": "model_1"},
    )
    assert failed_binding.status_code == 400, failed_binding.json()

    client.patch(
        "/api/v2/llm/channels/openai_main",
        json={"is_enabled": True},
    )
    bind_response = client.put(
        "/api/v2/llm/module-bindings/story_ontology",
        json={"llm_channel_id": "channel_1", "llm_model_id": "model_1"},
    )
    assert bind_response.status_code == 200, bind_response.json()
    binding = bind_response.json()["data"]
    assert binding["module_key"] == "story_ontology"
    assert binding["llm_channel_id"] == "channel_1"
    assert binding["llm_model_id"] == "model_1"

    delete_binding = client.delete("/api/v2/llm/module-bindings/story_ontology")
    assert delete_binding.status_code == 200, delete_binding.json()
    assert delete_binding.json()["data"] == {"module_key": "story_ontology", "deleted": True}

    missing_binding = client.delete("/api/v2/llm/module-bindings/story_ontology")
    assert missing_binding.status_code == 404, missing_binding.json()

    delete_channel = client.delete("/api/v2/llm/channels/openai_main")
    assert delete_channel.status_code == 200, delete_channel.json()
    assert delete_channel.json()["data"] == {"channel_key": "openai_main", "deleted": True}

    engine = create_engine(database_url)
    with engine.connect() as connection:
        channels = connection.execute(select(metadata.tables["llm_channels"])).all()
        bindings = connection.execute(select(metadata.tables["llm_module_bindings"])).all()

    assert len(channels) == 1
    assert len(bindings) == 0
