"""渠道级 LLM 并发控制（asyncio 原生）。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Dict


DEFAULT_CHANNEL_CONCURRENCY = 4


@dataclass
class _ChannelRuntime:
    limit: int
    inflight: int = 0
    waiting: int = 0
    condition: asyncio.Condition = field(
        default_factory=lambda: asyncio.Condition(asyncio.Lock())
    )


class LlmConcurrencyService:
    """按渠道维护请求并发上限与运行态（asyncio 原生）。"""

    def __init__(self, default_limit: int = DEFAULT_CHANNEL_CONCURRENCY):
        self.default_limit = default_limit
        self._channels: Dict[str, _ChannelRuntime] = {}
        self._lock = asyncio.Lock()

    async def set_limit(self, channel_key: str, limit: int) -> None:
        runtime = await self._runtime(channel_key, limit)
        async with runtime.condition:
            if runtime.limit == limit:
                return
            runtime.limit = limit
            runtime.condition.notify_all()

    async def acquire_slot(self, channel_key: str) -> None:
        runtime = await self._runtime(channel_key)
        async with runtime.condition:
            runtime.waiting += 1
            try:
                while runtime.inflight >= runtime.limit:
                    await runtime.condition.wait()
                runtime.waiting -= 1
                runtime.inflight += 1
            except Exception:
                runtime.waiting -= 1
                runtime.condition.notify_all()
                raise

    async def release_slot(self, channel_key: str) -> None:
        runtime = await self._runtime(channel_key)
        async with runtime.condition:
            if runtime.inflight > 0:
                runtime.inflight -= 1
            runtime.condition.notify_all()

    async def snapshot(self, channel_key: str) -> Dict[str, int]:
        runtime = await self._runtime(channel_key)
        async with runtime.condition:
            return {
                "limit": runtime.limit,
                "inflight": runtime.inflight,
                "waiting": runtime.waiting,
            }

    @asynccontextmanager
    async def async_slot(self, channel_key: str):
        await self.acquire_slot(channel_key)
        try:
            yield
        finally:
            await self.release_slot(channel_key)

    async def reset(self) -> None:
        async with self._lock:
            self._channels = {}

    async def channel_keys(self) -> list:
        """返回所有已注册的渠道 key 列表。"""
        async with self._lock:
            return list(self._channels.keys())

    async def _runtime(
        self,
        channel_key: str,
        limit: int | None = None,
    ) -> _ChannelRuntime:
        if not channel_key:
            raise ValueError("channel_key 不能为空")
        async with self._lock:
            runtime = self._channels.get(channel_key)
            if runtime is None:
                runtime = _ChannelRuntime(limit=limit or self.default_limit)
                self._channels[channel_key] = runtime
            return runtime


llm_concurrency_service = LlmConcurrencyService()
