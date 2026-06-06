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


def seed_archive_review_database(database_url: str) -> None:
    now = datetime(2026, 4, 12, tzinfo=timezone.utc)
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
                name="记忆审核项目",
                legacy_status="created",
                analysis_summary="review ready",
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
            metadata.tables["memories"].insert(),
            [
                {
                    "memory_id": "mem_canon_1",
                    "project_id": "proj_demo",
                    "archive_id": "arc_1",
                    "memory_type": "strategy",
                    "memory_layer": "canon",
                    "status": "active",
                    "normalized_subject": "公开密信",
                    "summary": "沈夜决定先公开一页密信试探众人反应。",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "memory_id": "mem_candidate_1",
                    "project_id": "proj_demo",
                    "archive_id": "arc_1",
                    "memory_type": "strategy",
                    "memory_layer": "candidate",
                    "status": "active",
                    "normalized_subject": "公开密信",
                    "summary": "沈夜决定改为在众目睽睽下公开密信残页。",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "memory_id": "mem_candidate_2",
                    "project_id": "proj_demo",
                    "archive_id": "arc_1",
                    "memory_type": "strategy",
                    "memory_layer": "candidate",
                    "status": "active",
                    "normalized_subject": "隐瞒密信来源",
                    "summary": "沈夜决定继续隐瞒密信来源。",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )


def test_archive_memory_review_commands_adopt_and_reject_candidates(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'archive_review.db'}"
    seed_archive_review_database(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    adopt_response = client.post("/api/v2/archives/arc_1/memory-adoptions", json={"memory_id": "mem_candidate_1"})
    assert adopt_response.status_code == 200, adopt_response.json()
    adopted = adopt_response.json()["data"]["memory"]
    assert adopted["memory_id"] == "mem_candidate_1"
    assert adopted["memory_layer"] == "canon"
    assert adopted["status"] == "active"

    reject_response = client.post("/api/v2/archives/arc_1/memory-rejections", json={"memory_id": "mem_candidate_2"})
    assert reject_response.status_code == 200, reject_response.json()
    rejected = reject_response.json()["data"]["memory"]
    assert rejected["memory_id"] == "mem_candidate_2"
    assert rejected["status"] == "rejected"

    engine = create_engine(database_url)
    with engine.connect() as connection:
        memories = connection.execute(
            select(metadata.tables["memories"]).where(metadata.tables["memories"].c.archive_id == "arc_1")
        ).all()
        events = connection.execute(
            select(metadata.tables["memory_events"]).where(metadata.tables["memory_events"].c.archive_id == "arc_1")
        ).all()

    memory_map = {row.memory_id: row for row in memories}
    assert memory_map["mem_canon_1"].status == "superseded"
    assert memory_map["mem_candidate_1"].memory_layer == "canon"
    assert memory_map["mem_candidate_2"].status == "rejected"
    assert {row.event_type for row in events} >= {"promote_to_canon", "reject_candidate", "supersede_canon"}

    repeated_adopt_response = client.post("/api/v2/archives/arc_1/memory-adoptions", json={"memory_id": "mem_candidate_1"})
    assert repeated_adopt_response.status_code == 400, repeated_adopt_response.json()

    repeated_reject_response = client.post("/api/v2/archives/arc_1/memory-rejections", json={"memory_id": "mem_candidate_2"})
    assert repeated_reject_response.status_code == 400, repeated_reject_response.json()
