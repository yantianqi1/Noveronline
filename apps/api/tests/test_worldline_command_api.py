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


def seed_worldline_events(database_url: str) -> None:
    now = datetime(2026, 4, 12, tzinfo=timezone.utc)
    engine = create_engine(database_url)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            metadata.tables["worldline_sessions"].insert().values(
                session_id="ws_1",
                project_id=None,
                session_scope="project",
                simulation_goal="test",
                focus_question="test",
                status="running",
                created_from_prepare_run_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["world_states"].insert().values(
                world_state_id="state_1",
                session_id="ws_1",
                version_no=1,
                is_current=True,
                created_at=now,
            )
        )
        connection.execute(
            metadata.tables["timeline_events"].insert(),
            [
                {
                    "timeline_event_id": "evt_seed",
                    "session_id": "ws_1",
                    "world_state_id": "state_1",
                    "step_no": 0,
                    "event_type": "seed",
                    "title": "seed",
                    "summary": "seed event",
                    "status": "canon",
                    "created_at": now,
                },
                {
                    "timeline_event_id": "evt_c1",
                    "session_id": "ws_1",
                    "world_state_id": "state_1",
                    "step_no": 1,
                    "event_type": "evolution",
                    "title": "candidate 1",
                    "summary": "first candidate",
                    "status": "candidate",
                    "created_at": now,
                },
                {
                    "timeline_event_id": "evt_c2",
                    "session_id": "ws_1",
                    "world_state_id": "state_1",
                    "step_no": 1,
                    "event_type": "evolution",
                    "title": "candidate 2",
                    "summary": "second candidate",
                    "status": "candidate",
                    "created_at": now,
                },
                {
                    "timeline_event_id": "evt_c3",
                    "session_id": "ws_1",
                    "world_state_id": "state_1",
                    "step_no": 1,
                    "event_type": "evolution",
                    "title": "candidate 3",
                    "summary": "third candidate",
                    "status": "candidate",
                    "created_at": now,
                },
            ],
        )


def test_worldline_event_commands_adopt_reject_and_edit_candidates(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'worldline_commands.db'}"
    seed_worldline_events(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    adopt_response = client.post(
        "/api/v2/worldlines/sessions/ws_1/event-adoptions",
        json={"event_ids": ["evt_c1", "evt_c2"], "action": "canon"},
    )
    assert adopt_response.status_code == 200, adopt_response.json()
    assert adopt_response.json()["data"]["changed_count"] == 2

    reject_response = client.post(
        "/api/v2/worldlines/sessions/ws_1/event-adoptions",
        json={"event_ids": ["evt_c3"], "action": "rejected"},
    )
    assert reject_response.status_code == 200, reject_response.json()
    assert reject_response.json()["data"]["action"] == "rejected"

    edit_response = client.patch(
        "/api/v2/worldlines/sessions/ws_1/events/evt_c1",
        json={"summary": "modified consequence text"},
    )
    assert edit_response.status_code == 400, edit_response.json()

    engine = create_engine(database_url)
    with engine.connect() as connection:
        rows = connection.execute(select(metadata.tables["timeline_events"])).all()
    statuses = {row.timeline_event_id: row.status for row in rows}
    assert statuses["evt_c1"] == "canon"
    assert statuses["evt_c2"] == "canon"
    assert statuses["evt_c3"] == "rejected"


def test_worldline_event_edit_marks_candidate_as_canon(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'worldline_edit.db'}"
    seed_worldline_events(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    edit_response = client.patch(
        "/api/v2/worldlines/sessions/ws_1/events/evt_c1",
        json={"summary": "modified consequence text"},
    )
    assert edit_response.status_code == 200, edit_response.json()
    payload = edit_response.json()["data"]
    assert payload["event_id"] == "evt_c1"
    assert payload["status"] == "canon"
    assert payload["summary"] == "modified consequence text"

    invalid_response = client.patch(
        "/api/v2/worldlines/sessions/ws_1/events/evt_seed",
        json={"summary": "new text"},
    )
    assert invalid_response.status_code == 400, invalid_response.json()
