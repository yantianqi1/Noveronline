"""全局 LLM 调用活动追踪器。

记录每次 LLM 调用的运行状态，供 API 端点轮询以实现全局监控面板。

Implementation note:
  The tracker is shared by both sync and async LLM client paths. The sync
  ``LLMClient`` runs inside ``asyncio.to_thread`` worker threads during
  seed/graph pipelines, so we cannot rely on ``asyncio.Lock`` (which is
  tied to a single event loop). Instead we use ``threading.Lock`` — the
  in-memory dict mutation is trivial and doesn't await anything, so a
  sync lock is sufficient and works equally well from async callers.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class ActivityRecord:
    call_id: str          # uuid4 hex
    module_key: str       # e.g. "narrative_archives"
    module_label: str     # e.g. "角色势力档案生成"
    model: str            # e.g. "gpt-4o"
    channel_key: str      # e.g. "openai_main"
    status: str           # "waiting" | "running" | "streaming"
    started_at_mono: float  # time.monotonic() — for elapsed calculation
    started_at_wall: str    # ISO 8601 string — for display
    call_type: str        # "chat" | "chat_json" | "chat_stream" | ...


class LlmActivityTracker:
    """线程安全的 LLM 活动追踪单例（threading.Lock）。"""

    def __init__(self) -> None:
        self._calls: Dict[str, ActivityRecord] = {}
        self._lock = threading.Lock()

    def register(
        self,
        module_key: str,
        module_label: str,
        model: str,
        channel_key: str,
        call_type: str = "chat",
        status: str = "waiting",
    ) -> str:
        """注册一次调用，返回 call_id。"""
        call_id = uuid.uuid4().hex
        record = ActivityRecord(
            call_id=call_id,
            module_key=module_key,
            module_label=module_label or module_key,
            model=model,
            channel_key=channel_key,
            status=status,
            started_at_mono=time.monotonic(),
            started_at_wall=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            call_type=call_type,
        )
        with self._lock:
            self._calls[call_id] = record
            active = len(self._calls)
        logger.debug(
            "LLM activity register: module=%s model=%s channel=%s total_active=%d",
            module_key, model, channel_key, active,
        )
        return call_id

    def update_status(self, call_id: str, status: str) -> None:
        """更新调用状态（waiting -> running / streaming）。"""
        if not call_id:
            return
        with self._lock:
            record = self._calls.get(call_id)
            if record:
                record.status = status

    def unregister(self, call_id: str) -> None:
        """调用结束，移除记录。"""
        if not call_id:
            return
        with self._lock:
            self._calls.pop(call_id, None)
            active = len(self._calls)
        logger.debug("LLM activity unregister: %s total_active=%d", call_id, active)

    def snapshot(self) -> List[dict]:
        """返回当前所有活跃调用的快照列表。

        Return shape matches the frontend ``LlmActiveCall`` contract
        (see ``frontend/src/types/llm.ts``): module / model_id /
        elapsed_seconds / started_at / channel_key.
        """
        now = time.monotonic()
        with self._lock:
            return [
                {
                    "call_id": r.call_id,
                    "module": r.module_label or r.module_key,
                    "module_key": r.module_key,
                    "model_id": r.model,
                    "channel_key": r.channel_key,
                    "status": r.status,
                    "started_at": r.started_at_wall,
                    "elapsed_seconds": round(now - r.started_at_mono, 2),
                    "call_type": r.call_type,
                }
                for r in self._calls.values()
            ]


# 进程级单例
llm_activity_tracker = LlmActivityTracker()
