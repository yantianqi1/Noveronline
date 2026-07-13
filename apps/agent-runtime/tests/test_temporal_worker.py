from __future__ import annotations

import asyncio

import pytest

import mirofish_agents.temporal.worker as worker_module
from mirofish_agents.temporal.seed import SEED_TASK_QUEUE
from mirofish_agents.temporal.character import CHARACTER_TASK_QUEUE
from mirofish_agents.temporal.worldline import WORLDLINE_TASK_QUEUE


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


def test_custom_seed_task_queue_registers_seed_workflows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEED_TASK_QUEUE", "seed-heavy-custom")

    components = worker_module.worker_components_for_task_queue("seed-heavy-custom")

    assert [workflow.__name__ for workflow in components["workflows"]] == [
        "SeedPipelineWorkflow",
        "SeedSegmentRetryWorkflow",
    ]
    assert "seed_segment_retry_activity" in [
        activity.__name__ for activity in components["activities"]
    ]


def test_character_task_queue_registers_dialogue_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHARACTER_TASK_QUEUE", "character-custom")

    for task_queue in (CHARACTER_TASK_QUEUE, "character-custom"):
        components = worker_module.worker_components_for_task_queue(task_queue)
        assert [workflow.__name__ for workflow in components["workflows"]] == [
            "CharacterDialogueWorkflow"
        ]
        assert [activity.__name__ for activity in components["activities"]] == [
            "character_dialogue_activity"
        ]


def test_worldline_task_queue_registers_step_prepare_and_auto_evolution_runtime() -> None:
    components = worker_module.worker_components_for_task_queue(WORLDLINE_TASK_QUEUE)

    assert [workflow.__name__ for workflow in components["workflows"]] == [
        "WorldlineStepWorkflow",
        "WorldlinePrepareWorkflow",
        "WorldlineAutoEvolutionWorkflow",
    ]
    assert [activity.__name__ for activity in components["activities"]] == [
        "worldline_step_activity",
        "worldline_prepare_activity",
        "worldline_auto_evolution_step_activity",
        "worldline_auto_evolution_finalize_activity",
    ]
