import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine


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


def seed_llm_database(database_url: str) -> None:
    now = datetime(2026, 4, 11, tzinfo=timezone.utc)
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
                auth_secret_ref="secret://legacy-llm/key_1",
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
        connection.execute(
            metadata.tables["llm_module_bindings"].insert().values(
                llm_module_binding_id="binding_1",
                module_key="story_ontology",
                llm_channel_id="channel_1",
                llm_model_id="model_1",
                updated_at=now,
            )
        )


def test_get_llm_settings_returns_channels_models_and_bindings(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'llm.db'}"
    seed_llm_database(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    response = client.get("/api/v2/llm/settings")

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["meta"]["version"] == "v2"
    assert payload["data"]["providers"][0]["provider_key"] == "openai_main"
    assert payload["data"]["channels"][0]["channel_key"] == "openai_main"
    assert payload["data"]["channels"][0]["models"][0]["provider_model_id"] == "gpt-4.1"
    assert payload["data"]["modules"][0]["module_key"] == "story_ontology"
