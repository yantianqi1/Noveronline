from __future__ import annotations

import asyncio

import pytest

import mirofish_agents.temporal.worker as worker_module
from mirofish_agents.temporal.seed import SEED_TASK_QUEUE


def test_run_worker_provides_activity_executor_for_sync_activities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    fake_client = object()

    async def connect(address: str) -> object:
        captured["address"] = address
        return fake_client

    class FakeWorker:
        def __init__(self, client: object, **kwargs: object) -> None:
            captured["client"] = client
            captured.update(kwargs)

        async def run(self) -> None:
            captured["ran"] = True
            executor = captured.get("activity_executor")
            assert executor is not None
            future = executor.submit(lambda: "ok")
            assert future.result(timeout=1) == "ok"

    monkeypatch.setenv("TEMPORAL_ADDRESS", "temporal:7233")
    monkeypatch.setenv("AGENT_RUNTIME_TASK_QUEUE", SEED_TASK_QUEUE)
    monkeypatch.setattr(worker_module.Client, "connect", staticmethod(connect))
    monkeypatch.setattr(worker_module, "Worker", FakeWorker)

    asyncio.run(worker_module.run_worker())

    assert captured["address"] == "temporal:7233"
    assert captured["client"] is fake_client
    assert captured["task_queue"] == SEED_TASK_QUEUE
    assert captured["ran"] is True
