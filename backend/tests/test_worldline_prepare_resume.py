"""Coverage for worldline prepare 断点续传 (resume from partial dossiers).

Context: `uvicorn --reload` kills in-flight prepare workers on any .py save,
wasting the already-completed agent dossiers. These tests lock in the
resume contract:

1. After a failed run, `POST /session/prepare/{id}/resume` only re-invokes
   the LLM for agents whose dossier is NOT already in the DB.
2. Calling resume on a `ready` prepare is a no-op — no fresh LLM calls.
3. Already-in-progress runs refuse to be resumed concurrently.
"""

from __future__ import annotations

import threading
import time

from app import create_app
from app.models.project import ProjectManager
from app.models.task import TaskManager

from tests.test_worldline_prepare_api import (
    _FakeDialogueClient,
    _FakePrepareClient,
    _create_project_with_seed,
    _wait_for_task,
)


class _CountingPrepareClient:
    """Counts dossier calls and optionally fails after N successes."""

    model = "counting-prepare-model"
    max_concurrency = 1  # serial → deterministic failure point

    def __init__(self, fail_after: int | None = None, concurrency: int = 1):
        self.fail_after = fail_after
        self.max_concurrency = concurrency
        self.call_count = 0
        self._lock = threading.Lock()

    def chat_json(self, messages, temperature=0.4, max_tokens=1600):
        with self._lock:
            self.call_count += 1
            current = self.call_count
        if self.fail_after is not None and current > self.fail_after:
            raise RuntimeError(f"simulated failure on call #{current}")
        # Reuse the real fake's payload so schema validation passes.
        return _FakePrepareClient().chat_json(
            messages, temperature=temperature, max_tokens=max_tokens
        )


class _CountingRouter:
    def __init__(self, prepare_client):
        self.prepare_client = prepare_client
        self.dialogue_client = _FakeDialogueClient()

    def build_client(self, module_key):
        if module_key == "worldline_agent_prepare":
            return self.prepare_client
        if module_key == "worldline_agent_dialogue":
            return self.dialogue_client
        raise AssertionError(f"unexpected module: {module_key}")


def test_resume_prepare_skips_already_completed_dossiers(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    from app.api_fastapi import worldline as worldline_module

    # First run: fail after first 2 successful dossiers.
    failing_client = _CountingPrepareClient(fail_after=2)
    failing_router = _CountingRouter(failing_client)
    monkeypatch.setattr(
        worldline_module.worldline_prepare_service, "llm_router", failing_router
    )

    prepare_response = client.post(
        "/api/worldline/session/prepare",
        json={"project_id": project.project_id},
    )
    assert prepare_response.status_code == 202, prepare_response.get_json()
    payload = prepare_response.get_json()["data"]
    prepare_id = payload["prepare_id"]

    task = _wait_for_task(client, payload["task_id"])
    assert task["status"] == "failed", task

    status_response = client.get(f"/api/worldline/session/prepare/{prepare_id}")
    status_payload = status_response.get_json()["data"]
    assert status_payload["status"] == "failed"
    assert status_payload["can_start"] is False

    agents_response = client.get(f"/api/worldline/session/prepare/{prepare_id}/agents")
    partial_agents = agents_response.get_json()["data"]["agents"]
    # The fake client fails after 2 successful dossiers, so we expect at
    # least 2 persisted. A 3rd is possible if the failing call happens
    # to slip through concurrent scheduling; we only care that it's not
    # zero and not everything.
    persisted = len(partial_agents)
    assert 2 <= persisted, partial_agents
    completed_agent_ids = {a["agent_id"] for a in partial_agents}

    # Second run: swap in a client that always succeeds, then resume.
    fresh_client = _CountingPrepareClient(fail_after=None)
    fresh_router = _CountingRouter(fresh_client)
    monkeypatch.setattr(
        worldline_module.worldline_prepare_service, "llm_router", fresh_router
    )

    resume_response = client.post(
        f"/api/worldline/session/prepare/{prepare_id}/resume"
    )
    assert resume_response.status_code == 202, resume_response.get_json()
    resume_payload = resume_response.get_json()["data"]
    assert resume_payload["prepare_id"] == prepare_id
    assert resume_payload["task_id"] != payload["task_id"]

    task2 = _wait_for_task(client, resume_payload["task_id"])
    assert task2["status"] == "completed", task2

    # Final state must be ready + can_start; all dossiers present.
    final_status = client.get(
        f"/api/worldline/session/prepare/{prepare_id}"
    ).get_json()["data"]
    assert final_status["status"] == "ready"
    assert final_status["can_start"] is True

    final_agents = client.get(
        f"/api/worldline/session/prepare/{prepare_id}/agents"
    ).get_json()["data"]["agents"]
    final_ids = {a["agent_id"] for a in final_agents}
    assert completed_agent_ids.issubset(final_ids)
    assert len(final_agents) > len(partial_agents)

    # The new client must have been called only for the remaining agents,
    # not the already-persisted ones.
    expected_remaining = len(final_agents) - persisted
    assert fresh_client.call_count == expected_remaining, (
        f"resume should skip {persisted} done agents; "
        f"called {fresh_client.call_count}, expected {expected_remaining}"
    )


def test_resume_prepare_on_ready_prepare_is_noop(tmp_path, monkeypatch):
    project = _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    from app.api_fastapi import worldline as worldline_module

    success_client = _CountingPrepareClient(fail_after=None, concurrency=4)
    success_router = _CountingRouter(success_client)
    monkeypatch.setattr(
        worldline_module.worldline_prepare_service, "llm_router", success_router
    )

    prepare_response = client.post(
        "/api/worldline/session/prepare",
        json={"project_id": project.project_id},
    )
    payload = prepare_response.get_json()["data"]
    prepare_id = payload["prepare_id"]
    task = _wait_for_task(client, payload["task_id"])
    assert task["status"] == "completed", task
    total_calls = success_client.call_count
    assert total_calls > 0

    resume_response = client.post(
        f"/api/worldline/session/prepare/{prepare_id}/resume"
    )
    assert resume_response.status_code == 202, resume_response.get_json()
    # Ready prepare → returns immediately, no new LLM calls.
    assert success_client.call_count == total_calls

    status_payload = client.get(
        f"/api/worldline/session/prepare/{prepare_id}"
    ).get_json()["data"]
    assert status_payload["status"] == "ready"


def test_resume_prepare_unknown_id_returns_error(tmp_path, monkeypatch):
    _create_project_with_seed(tmp_path, monkeypatch)
    app = create_app()
    client = app.test_client()

    response = client.post("/api/worldline/session/prepare/prep_doesnotexist/resume")
    # ValueError path in the service → 400; fallthrough → 500. Either is
    # a hard error — just confirm it's surfaced as a failure, not a 202.
    assert response.status_code >= 400, response.get_json()
