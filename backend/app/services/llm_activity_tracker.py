"""全局 LLM 调用活动追踪器。

记录每次 LLM 调用的运行状态，供 API 端点轮询以实现全局监控面板。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ActivityRecord:
    call_id: str          # uuid4 hex
    module_key: str       # e.g. "narrative_archives"
    module_label: str     # e.g. "角色势力档案生成"
    model: str            # e.g. "gpt-4o"
    channel_key: str      # e.g. "openai_main"
    status: str           # "waiting" | "running" | "streaming"
    started_at: float     # time.monotonic()
    call_type: str        # "chat" | "chat_json" | "chat_stream"


class LlmActivityTracker:
    """线程安全的 LLM 活动追踪单例。"""

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
            module_label=module_label,
            model=model,
            channel_key=channel_key,
            status=status,
            started_at=time.monotonic(),
            call_type=call_type,
        )
        with self._lock:
            self._calls[call_id] = record
        return call_id

    def update_status(self, call_id: str, status: str) -> None:
        """更新调用状态（waiting → running / streaming）。"""
        with self._lock:
            record = self._calls.get(call_id)
            if record:
                record.status = status

    def unregister(self, call_id: str) -> None:
        """调用结束，移除记录。"""
        with self._lock:
            self._calls.pop(call_id, None)

    def snapshot(self) -> List[dict]:
        """返回当前所有活跃调用的快照列表。"""
        now = time.monotonic()
        with self._lock:
            return [
                {
                    "call_id": r.call_id,
                    "module_key": r.module_key,
                    "module_label": r.module_label,
                    "model": r.model,
                    "channel_key": r.channel_key,
                    "status": r.status,
                    "elapsed_ms": int((now - r.started_at) * 1000),
                    "call_type": r.call_type,
                }
                for r in self._calls.values()
            ]


# 进程级单例
llm_activity_tracker = LlmActivityTracker()
