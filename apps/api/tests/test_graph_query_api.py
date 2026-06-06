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


def seed_graph_database(database_url: str) -> None:
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
                name="图谱项目",
                legacy_status="created",
                analysis_summary="graph ready",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["graph_nodes"].insert(),
            [
                {
                    "graph_node_id": "node_1",
                    "project_id": "proj_demo",
                    "canonical_name": "沈夜",
                    "display_name": "沈夜",
                    "node_type": "Character",
                    "summary": "主角",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "graph_node_id": "node_2",
                    "project_id": "proj_demo",
                    "canonical_name": "玄霄宗",
                    "display_name": "玄霄宗",
                    "node_type": "Organization",
                    "summary": "宗门",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        connection.execute(
            metadata.tables["graph_edges"].insert().values(
                graph_edge_id="edge_1",
                project_id="proj_demo",
                source_node_id="node_1",
                target_node_id="node_2",
                edge_type="tension",
                summary="沈夜与玄霄宗关系紧张",
                created_at=now,
                updated_at=now,
            )
        )


def test_graph_queries_return_projection_and_node_detail(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'graph.db'}"
    seed_graph_database(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    graph_response = client.get("/api/v2/workspaces/legacy-workspace/graph")
    assert graph_response.status_code == 200, graph_response.json()
    graph_payload = graph_response.json()
    assert graph_payload["data"]["node_count"] == 2
    assert graph_payload["data"]["edge_count"] == 1
    assert graph_payload["data"]["nodes"][0]["graph_node_id"] == "node_1"

    node_response = client.get("/api/v2/workspaces/legacy-workspace/graph/nodes/node_1")
    assert node_response.status_code == 200, node_response.json()
    node_payload = node_response.json()
    assert node_payload["data"]["node"]["graph_node_id"] == "node_1"
    assert node_payload["data"]["edges"][0]["graph_edge_id"] == "edge_1"


def test_graph_template_config_patch_upserts_and_updates(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'graph_template.db'}"
    seed_graph_database(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    create_response = client.patch(
        "/api/v2/workspaces/legacy-workspace/graph-template-configs/character.protagonist.v1",
        json={"status": "active"},
    )
    assert create_response.status_code == 200, create_response.json()
    created = create_response.json()["data"]
    assert created["template_key"] == "character.protagonist.v1"
    assert created["status"] == "active"

    update_response = client.patch(
        "/api/v2/workspaces/legacy-workspace/graph-template-configs/character.protagonist.v1",
        json={"status": "disabled"},
    )
    assert update_response.status_code == 200, update_response.json()
    updated = update_response.json()["data"]
    assert updated["status"] == "disabled"
