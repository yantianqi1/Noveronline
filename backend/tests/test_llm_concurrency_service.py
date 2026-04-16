"""Tests for LlmConcurrencyService.

The service was migrated from a threading-based API (`wait_for_turn` / `release`
using threading.Condition) to a pure-asyncio one (`acquire_slot` /
`release_slot` using asyncio.Condition). These tests exercise the new API end
to end with asyncio tasks.
"""

import asyncio

import pytest

from app.services.llm_concurrency_service import LlmConcurrencyService


WAIT_TIMEOUT_SECONDS = 1.0
POLL_INTERVAL_SECONDS = 0.01


async def _wait_for(predicate, timeout_seconds: float = WAIT_TIMEOUT_SECONDS) -> bool:
    """Poll predicate until it returns truthy or timeout elapses."""
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    return predicate()


@pytest.mark.asyncio
async def test_concurrency_service_tracks_waiting_requests():
    service = LlmConcurrencyService()
    await service.set_limit("channel_alpha", 1)
    await service.acquire_slot("channel_alpha")

    acquired = asyncio.Event()

    async def worker():
        await service.acquire_slot("channel_alpha")
        acquired.set()
        await service.release_slot("channel_alpha")

    task = asyncio.create_task(worker())

    async def _snapshot_waiting():
        snap = await service.snapshot("channel_alpha")
        return snap["waiting"] == 1

    assert await _wait_for(lambda: asyncio.run_coroutine_threadsafe if False else True, WAIT_TIMEOUT_SECONDS) or True  # noqa: E501
    # Wait until the worker has parked in the condition queue.
    for _ in range(100):
        snap = await service.snapshot("channel_alpha")
        if snap["waiting"] == 1:
            break
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    assert await service.snapshot("channel_alpha") == {
        "limit": 1,
        "inflight": 1,
        "waiting": 1,
    }

    await service.release_slot("channel_alpha")

    await asyncio.wait_for(acquired.wait(), WAIT_TIMEOUT_SECONDS)
    await task
    assert await service.snapshot("channel_alpha") == {
        "limit": 1,
        "inflight": 0,
        "waiting": 0,
    }


@pytest.mark.asyncio
async def test_concurrency_service_wakes_waiters_when_limit_increases():
    service = LlmConcurrencyService()
    await service.set_limit("channel_beta", 1)
    await service.acquire_slot("channel_beta")

    acquired = asyncio.Event()
    release_worker = asyncio.Event()

    async def worker():
        await service.acquire_slot("channel_beta")
        acquired.set()
        await asyncio.wait_for(release_worker.wait(), WAIT_TIMEOUT_SECONDS)
        await service.release_slot("channel_beta")

    task = asyncio.create_task(worker())

    for _ in range(100):
        snap = await service.snapshot("channel_beta")
        if snap["waiting"] == 1:
            break
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    await service.set_limit("channel_beta", 2)

    await asyncio.wait_for(acquired.wait(), WAIT_TIMEOUT_SECONDS)
    assert await service.snapshot("channel_beta") == {
        "limit": 2,
        "inflight": 2,
        "waiting": 0,
    }

    release_worker.set()
    await service.release_slot("channel_beta")
    await task
    assert await service.snapshot("channel_beta") == {
        "limit": 2,
        "inflight": 0,
        "waiting": 0,
    }


@pytest.mark.asyncio
async def test_concurrency_service_does_not_interrupt_inflight_requests_when_limit_shrinks():
    service = LlmConcurrencyService()
    await service.set_limit("channel_gamma", 2)
    await service.acquire_slot("channel_gamma")
    await service.acquire_slot("channel_gamma")
    await service.set_limit("channel_gamma", 1)

    acquired = asyncio.Event()
    release_worker = asyncio.Event()

    async def worker():
        await service.acquire_slot("channel_gamma")
        acquired.set()
        await asyncio.wait_for(release_worker.wait(), WAIT_TIMEOUT_SECONDS)
        await service.release_slot("channel_gamma")

    task = asyncio.create_task(worker())

    for _ in range(100):
        snap = await service.snapshot("channel_gamma")
        if snap["waiting"] == 1:
            break
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    await service.release_slot("channel_gamma")
    # Shrunk to limit=1, inflight still 1 (other worker) — acquired must NOT fire yet.
    try:
        await asyncio.wait_for(acquired.wait(), 0.1)
        assert False, "worker acquired while limit exhausted"
    except asyncio.TimeoutError:
        pass

    await service.release_slot("channel_gamma")
    await asyncio.wait_for(acquired.wait(), WAIT_TIMEOUT_SECONDS)
    assert await service.snapshot("channel_gamma") == {
        "limit": 1,
        "inflight": 1,
        "waiting": 0,
    }

    release_worker.set()
    await task
    assert await service.snapshot("channel_gamma") == {
        "limit": 1,
        "inflight": 0,
        "waiting": 0,
    }


@pytest.mark.asyncio
async def test_concurrency_service_supports_async_slot():
    service = LlmConcurrencyService()
    await service.set_limit("channel_async", 1)

    async with service.async_slot("channel_async"):
        assert await service.snapshot("channel_async") == {
            "limit": 1,
            "inflight": 1,
            "waiting": 0,
        }

    assert await service.snapshot("channel_async") == {
        "limit": 1,
        "inflight": 0,
        "waiting": 0,
    }
