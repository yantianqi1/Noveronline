"""渠道级 LLM 并发控制。"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator


DEFAULT_CHANNEL_CONCURRENCY = 4


@dataclass
class _ChannelRuntime:
    limit: int
    inflight: int = 0
    waiting: int = 0
    condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.Lock())
    )


class LlmConcurrencyService:
    """按渠道维护请求并发上限与运行态。"""

    def __init__(self, default_limit: int = DEFAULT_CHANNEL_CONCURRENCY):
        self.default_limit = default_limit
        self._channels: Dict[str, _ChannelRuntime] = {}
        self._lock = threading.Lock()

    def set_limit(self, channel_key: str, limit: int) -> None:
        runtime = self._runtime(channel_key, limit)
        with runtime.condition:
            if runtime.limit == limit:
                return
            runtime.limit = limit
            runtime.condition.notify_all()

    def wait_for_turn(self, channel_key: str) -> None:
        runtime = self._runtime(channel_key)
        with runtime.condition:
            runtime.waiting += 1
            try:
                while runtime.inflight >= runtime.limit:
                    runtime.condition.wait()
                runtime.waiting -= 1
                runtime.inflight += 1
            except Exception:
                runtime.waiting -= 1
                runtime.condition.notify_all()
                raise

    def release(self, channel_key: str) -> None:
        runtime = self._runtime(channel_key)
        with runtime.condition:
            if runtime.inflight > 0:
                runtime.inflight -= 1
            runtime.condition.notify_all()

    def snapshot(self, channel_key: str) -> Dict[str, int]:
        runtime = self._runtime(channel_key)
        with runtime.condition:
            return {
                "limit": runtime.limit,
                "inflight": runtime.inflight,
                "waiting": runtime.waiting,
            }

    @contextmanager
    def slot(self, channel_key: str) -> Iterator[None]:
        self.wait_for_turn(channel_key)
        try:
            yield
        finally:
            self.release(channel_key)

    def reset(self) -> None:
        with self._lock:
            self._channels = {}

    def channel_keys(self) -> list:
        """返回所有已注册的渠道 key 列表。"""
        with self._lock:
            return list(self._channels.keys())

    def _runtime(
        self,
        channel_key: str,
        limit: int | None = None,
    ) -> _ChannelRuntime:
        if not channel_key:
            raise ValueError("channel_key 不能为空")
        with self._lock:
            runtime = self._channels.get(channel_key)
            if runtime is None:
                runtime = _ChannelRuntime(limit=limit or self.default_limit)
                self._channels[channel_key] = runtime
            return runtime


llm_concurrency_service = LlmConcurrencyService()
