from app import create_app

from tests.test_worldline_prepare_api import (
    _FakeRouter,
    _create_project_with_seed,
    _wait_for_task,
)


def test_v2_worldline_prepare_routes_materialize_agents_and_start_session(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    from app.api_fastapi import worldline as worldline_prepare

    monkeypatch.setattr(worldline_prepare.worldline_prepare_service, "llm_router", _FakeRouter())

    prepare_response = client.post(
        "/api/v2/worldlines/preparations",
        json={"project_id": project.project_id, "variables": ["密信提前泄露"]},
    )
    assert prepare_response.status_code == 202, prepare_response.get_json()
    prepare_payload = prepare_response.get_json()["data"]
    prepare_id = prepare_payload["prepare_id"]
    assert prepare_id
    assert prepare_payload["task_id"]

    task = _wait_for_task(client, prepare_payload["task_id"])
    assert task["status"] == "completed", task

    status_response = client.get(f"/api/v2/worldlines/preparations/{prepare_id}")
    assert status_response.status_code == 200, status_response.get_json()
    status_payload = status_response.get_json()["data"]
    assert status_payload["status"] == "ready"
    assert status_payload["can_start"] is True
    assert status_payload["events"]

    agents_response = client.get(f"/api/v2/worldlines/preparations/{prepare_id}/agents")
    assert agents_response.status_code == 200, agents_response.get_json()
    agents_payload = agents_response.get_json()["data"]
    assert agents_payload["status"] == "ready"
    protagonist = next(item for item in agents_payload["agents"] if item["display_name"] == "沈夜")
    assert protagonist["model_name"] == "fake-prepare-model"
    assert protagonist["private_profile"]["hidden_goal"]

    start_response = client.post(
        f"/api/v2/worldlines/preparations/{prepare_id}/start",
        json={"project_id": project.project_id},
    )
    assert start_response.status_code == 200, start_response.get_json()
    start_payload = start_response.get_json()["data"]
    assert start_payload["prepare_id"] == prepare_id
    assert start_payload["session_id"]
    assert start_payload["prepare_status"] == "ready"

    session_response = client.get(
        f"/api/v2/worldlines/sessions/{start_payload['session_id']}",
        query_string={"project_id": project.project_id},
    )
    assert session_response.status_code == 200, session_response.get_json()
    session_payload = session_response.get_json()["data"]
    assert session_payload["prepare_id"] == prepare_id
    assert session_payload["current_world"]["branch_id"] == "main"
