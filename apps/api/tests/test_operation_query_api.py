import sys
from datetime import datetime, timedelta, timezone
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


def seed_operation_database(database_url: str) -> None:
    now = datetime(2026, 4, 12, tzinfo=timezone.utc)
    engine = create_engine(database_url)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            metadata.tables["workflow_runs"].insert().values(
                workflow_run_id="wfr_demo",
                project_id=None,
                legacy_task_id="legacy_task_1",
                workflow_type="seed_extract",
                status="completed",
                progress_percent=100,
                last_message="完成导入",
                input_snapshot='{"project_id":"proj_demo"}',
                last_error=None,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            metadata.tables["workflow_steps"].insert(),
            [
                {
                    "workflow_step_id": "step_extract",
                    "workflow_run_id": "wfr_demo",
                    "step_key": "extract_text",
                    "stage": "extract_text",
                    "status": "completed",
                    "progress_percent": 100,
                    "message": "文本提取完成",
                    "started_at": now,
                    "finished_at": now,
                    "elapsed_ms": 10,
                },
                {
                    "workflow_step_id": "step_segment",
                    "workflow_run_id": "wfr_demo",
                    "step_key": "segment_chapters",
                    "stage": "segment_chapters",
                    "status": "completed",
                    "progress_percent": 100,
                    "message": "章节切分完成",
                    "started_at": now,
                    "finished_at": now,
                    "elapsed_ms": 20,
                },
            ],
        )
        connection.execute(
            metadata.tables["workflow_events"].insert(),
            [
                {
                    "workflow_event_id": "evt_start",
                    "workflow_run_id": "wfr_demo",
                    "event_type": "operation.started",
                    "stage": "extract_text",
                    "level": "info",
                    "status": "completed",
                    "title": "开始处理",
                    "detail": "任务启动",
                    "payload_json": '{"title":"开始处理"}',
                    "emitted_at": now,
                },
                {
                    "workflow_event_id": "evt_done",
                    "workflow_run_id": "wfr_demo",
                    "event_type": "operation.completed",
                    "stage": "segment_chapters",
                    "level": "info",
                    "status": "completed",
                    "title": "处理完成",
                    "detail": "任务完成",
                    "payload_json": '{"title":"处理完成"}',
                    "emitted_at": now + timedelta(seconds=1),
                },
            ],
        )


def test_operation_queries_return_run_and_step_trace(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'operations.db'}"
    seed_operation_database(database_url)
    client = TestClient(create_app(make_settings(database_url)))

    operation_response = client.get("/api/v2/operations/wfr_demo")
    assert operation_response.status_code == 200, operation_response.json()
    payload = operation_response.json()
    assert payload["operation_id"] == "wfr_demo"
    assert payload["status"] == "succeeded"
    assert payload["steps"][0]["step_id"] == "step_extract"
    assert payload["steps"][0]["status"] == "succeeded"

    legacy_response = client.get("/api/v2/operations/legacy_task_1")
    assert legacy_response.status_code == 200, legacy_response.json()
    assert legacy_response.json()["operation_id"] == "wfr_demo"

    step_response = client.get("/api/v2/operations/wfr_demo/steps/segment_chapters")
    assert step_response.status_code == 200, step_response.json()
    step_payload = step_response.json()
    assert step_payload["steps"][0]["stage"] == "segment_chapters"
    assert step_payload["steps"][0]["message"] == "章节切分完成"

    events_response = client.get("/api/v2/operations/wfr_demo/events")
    assert events_response.status_code == 200, events_response.json()
    events_payload = events_response.json()
    assert events_payload[0]["type"] == "operation.started"
    assert events_payload[-1]["type"] == "operation.completed"

    stream_response = client.get("/api/v2/operations/wfr_demo/stream")
    assert stream_response.status_code == 200, stream_response.text
    assert "event: operation.started" in stream_response.text
    assert "id: evt_start" in stream_response.text

    replay_response = client.get("/api/v2/operations/wfr_demo/stream", headers={"Last-Event-ID": "evt_start"})
    assert replay_response.status_code == 200, replay_response.text
    assert "id: evt_start" not in replay_response.text
    assert "id: evt_done" in replay_response.text
