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


def seed_archive_database(database_url: str) -> None:
    now = datetime(2026, 4, 11, tzinfo=timezone.utc)
    engine = create_engine(database_url)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            metadata.tables["workspaces"].insert().values(
                workspace_id="legacy-workspace",
                name="Legacy Imported Workspace",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["projects"].insert().values(
                project_id="proj_demo",
                workspace_id="legacy-workspace",
                name="档案项目",
                legacy_status="created",
                analysis_summary="archive ready",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["entities"].insert().values(
                entity_id="ent_1",
                project_id="proj_demo",
                entity_uuid="uuid_1",
                entity_kind="Character",
                canonical_name="沈夜",
                display_name="沈夜",
                summary="主角",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["archives"].insert().values(
                archive_id="arc_1",
                project_id="proj_demo",
                entity_id="ent_1",
                archive_type="Character",
                agent_kind="character",
                importance_tier="protagonist",
                selected_importance_tier="protagonist",
                template_key="character.protagonist.v1",
                template_version="v1",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["memories"].insert().values(
                memory_id="mem_1",
                project_id="proj_demo",
                archive_id="arc_1",
                memory_type="event",
                memory_layer="canon",
                status="active",
                normalized_subject="密信",
                summary="沈夜得到密信",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["memory_events"].insert().values(
                memory_event_id="evt_1",
                memory_id="mem_1",
                archive_id="arc_1",
                event_type="bootstrap_legacy",
                actor_type="migration",
                actor_ref="legacy-archive-library",
                created_at=now,
            )
        )


def test_archive_queries_return_list_detail_memories_and_events(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'archive.db'}"
    seed_archive_database(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    list_response = client.get("/api/v2/archives")
    assert list_response.status_code == 200, list_response.json()
    list_payload = list_response.json()
    assert list_payload["data"]["count"] == 1
    assert list_payload["data"]["items"][0]["entity_name"] == "沈夜"

    detail_response = client.get("/api/v2/archives/arc_1")
    assert detail_response.status_code == 200, detail_response.json()
    assert detail_response.json()["data"]["archive_id"] == "arc_1"

    memories_response = client.get("/api/v2/archives/arc_1/memories")
    assert memories_response.status_code == 200, memories_response.json()
    assert memories_response.json()["data"]["items"][0]["memory_id"] == "mem_1"

    events_response = client.get("/api/v2/archives/arc_1/memory-events")
    assert events_response.status_code == 200, events_response.json()
    assert events_response.json()["data"]["items"][0]["memory_event_id"] == "evt_1"
