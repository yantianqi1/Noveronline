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


def seed_writer_database(database_url: str) -> None:
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
            metadata.tables["workspace_settings"].insert().values(
                workspace_id="legacy-workspace",
                reviewer_rules_text="自定义审校规则",
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["projects"].insert().values(
                project_id="proj_demo",
                workspace_id="legacy-workspace",
                name="写作项目",
                legacy_status="created",
                analysis_summary="writer ready",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["chapters"].insert(),
            [
                {
                    "chapter_id": "chapter_0001",
                    "project_id": "proj_demo",
                    "chapter_order": 1,
                    "title": "起疑",
                    "summary_text": "沈夜得到密信。",
                    "timeline_note": "夜间",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "chapter_id": "chapter_0002",
                    "project_id": "proj_demo",
                    "chapter_order": 2,
                    "title": "废塔",
                    "summary_text": "秦昭带沈夜潜入废塔。",
                    "timeline_note": "深夜",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        connection.execute(
            metadata.tables["entities"].insert(),
            [
                {
                    "entity_id": "ent_1",
                    "project_id": "proj_demo",
                    "entity_uuid": "uuid_1",
                    "entity_kind": "Character",
                    "canonical_name": "沈夜",
                    "display_name": "沈夜",
                    "summary": "主角",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "entity_id": "ent_2",
                    "project_id": "proj_demo",
                    "entity_uuid": "uuid_2",
                    "entity_kind": "Character",
                    "canonical_name": "秦昭",
                    "display_name": "秦昭",
                    "summary": "盟友",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )


def test_writer_queries_return_options_and_reviewer_rules(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'writer.db'}"
    seed_writer_database(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    options_response = client.get("/api/v2/chapter-context/options", params={"project_id": "proj_demo"})
    assert options_response.status_code == 200, options_response.json()
    options_payload = options_response.json()
    assert options_payload["data"]["project_id"] == "proj_demo"
    assert len(options_payload["data"]["chapters"]) == 2
    assert "沈夜" in options_payload["data"]["pov_characters"]

    reviewer_response = client.get("/api/v2/workspaces/legacy-workspace/reviewer-rules")
    assert reviewer_response.status_code == 200, reviewer_response.json()
    reviewer_payload = reviewer_response.json()
    assert reviewer_payload["data"]["custom_prompt"] == "自定义审校规则"
    assert reviewer_payload["data"]["is_custom"] is True
    assert reviewer_payload["data"]["default_prompt"]

    update_response = client.put(
        "/api/v2/workspaces/legacy-workspace/reviewer-rules",
        json={"custom_prompt": "新的审校规则"},
    )
    assert update_response.status_code == 200, update_response.json()
    assert update_response.json()["data"]["custom_prompt"] == "新的审校规则"
    assert update_response.json()["data"]["is_custom"] is True

    reset_response = client.put(
        "/api/v2/workspaces/legacy-workspace/reviewer-rules",
        json={"custom_prompt": ""},
    )
    assert reset_response.status_code == 200, reset_response.json()
    assert reset_response.json()["data"]["custom_prompt"] == ""
    assert reset_response.json()["data"]["is_custom"] is False
