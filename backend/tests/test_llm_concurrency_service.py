import threading
import time

import pytest

from app.services.llm_concurrency_service import LlmConcurrencyService


WAIT_TIMEOUT_SECONDS = 1.0
POLL_INTERVAL_SECONDS = 0.01


def _wait_for(predicate, timeout_seconds: float = WAIT_TIMEOUT_SECONDS) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(POLL_INTERVAL_SECONDS)
    return predicate()


def test_concurrency_service_tracks_waiting_requests():
    service = LlmConcurrencyService()
    service.set_limit("channel_alpha", 1)
    service.wait_for_turn("channel_alpha")

    acquired = threading.Event()

    def worker():
        service.wait_for_turn("channel_alpha")
        acquired.set()
        service.release("channel_alpha")

    thread = threading.Thread(target=worker)
    thread.start()

    assert _wait_for(lambda: service.snapshot("channel_alpha")["waiting"] == 1)
    assert service.snapshot("channel_alpha") == {
        "limit": 1,
        "inflight": 1,
        "waiting": 1,
    }

    service.release("channel_alpha")

    assert acquired.wait(WAIT_TIMEOUT_SECONDS)
    thread.join()
    assert service.snapshot("channel_alpha") == {
        "limit": 1,
        "inflight": 0,
        "waiting": 0,
    }


def test_concurrency_service_wakes_waiters_when_limit_increases():
    service = LlmConcurrencyService()
    service.set_limit("channel_beta", 1)
    service.wait_for_turn("channel_beta")

    acquired = threading.Event()
    release_worker = threading.Event()

    def worker():
        service.wait_for_turn("channel_beta")
        acquired.set()
        release_worker.wait(WAIT_TIMEOUT_SECONDS)
        service.release("channel_beta")

    thread = threading.Thread(target=worker)
    thread.start()

    assert _wait_for(lambda: service.snapshot("channel_beta")["waiting"] == 1)
    service.set_limit("channel_beta", 2)

    assert acquired.wait(WAIT_TIMEOUT_SECONDS)
    assert service.snapshot("channel_beta") == {
        "limit": 2,
        "inflight": 2,
        "waiting": 0,
    }

    release_worker.set()
    service.release("channel_beta")
    thread.join()
    assert service.snapshot("channel_beta") == {
        "limit": 2,
        "inflight": 0,
        "waiting": 0,
    }


def test_concurrency_service_does_not_interrupt_inflight_requests_when_limit_shrinks():
    service = LlmConcurrencyService()
    service.set_limit("channel_gamma", 2)
    service.wait_for_turn("channel_gamma")
    service.wait_for_turn("channel_gamma")
    service.set_limit("channel_gamma", 1)

    acquired = threading.Event()
    release_worker = threading.Event()

    def worker():
        service.wait_for_turn("channel_gamma")
        acquired.set()
        release_worker.wait(WAIT_TIMEOUT_SECONDS)
        service.release("channel_gamma")

    thread = threading.Thread(target=worker)
    thread.start()

    assert _wait_for(lambda: service.snapshot("channel_gamma")["waiting"] == 1)
    service.release("channel_gamma")
    assert not acquired.wait(0.1)

    service.release("channel_gamma")
    assert acquired.wait(WAIT_TIMEOUT_SECONDS)
    assert service.snapshot("channel_gamma") == {
        "limit": 1,
        "inflight": 1,
        "waiting": 0,
    }

    release_worker.set()
    thread.join()
    assert service.snapshot("channel_gamma") == {
        "limit": 1,
        "inflight": 0,
        "waiting": 0,
    }


@pytest.mark.asyncio
async def test_concurrency_service_supports_async_slot():
    service = LlmConcurrencyService()
    service.set_limit("channel_async", 1)

    async with service.async_slot("channel_async"):
        assert service.snapshot("channel_async") == {
            "limit": 1,
            "inflight": 1,
            "waiting": 0,
        }

    assert service.snapshot("channel_async") == {
        "limit": 1,
        "inflight": 0,
        "waiting": 0,
    }
