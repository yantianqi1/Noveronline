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


def seed_workspace_database(database_url: str) -> None:
    engine = create_engine(database_url)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            metadata.tables["workspaces"].insert().values(
                workspace_id="legacy-workspace",
                name="Legacy Imported Workspace",
                created_at=datetime(2026, 4, 11, tzinfo=timezone.utc),
                updated_at=datetime(2026, 4, 11, tzinfo=timezone.utc),
            )
        )


def test_list_workspaces_returns_seeded_rows(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'workspace.db'}"
    seed_workspace_database(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    response = client.get("/api/v2/workspaces")

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["data"][0]["workspace_id"] == "legacy-workspace"
    assert payload["meta"]["version"] == "v2"


def test_get_workspace_returns_not_found_for_unknown_id(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'workspace.db'}"
    seed_workspace_database(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    response = client.get("/api/v2/workspaces/missing-workspace")

    assert response.status_code == 404, response.json()
    assert response.json()["error"]["code"] == "workspace_not_found"
