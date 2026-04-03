"""步骤级 trace 上下文，基于 contextvars 实现线程安全隐式传播。"""

from __future__ import annotations

import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class StepTraceContext:
    """当前活动步骤的 trace 收集容器。"""

    step_id: str
    step_kind: str
    group_key: str
    group_label: str
    stage: str
    title: str
    started_at_mono: float = field(default_factory=time.monotonic)
    started_at_wall: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    calls: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_call(self, call_data: Dict[str, Any]) -> None:
        """线程安全地追加一条 LLM 调用记录。"""
        with self._lock:
            self.calls.append(call_data)

    def record_artifact(self, label: str, content: str, kind: str = "text") -> None:
        """追加一条非 LLM 产物记录（输入文本、处理结果、统计等）。"""
        with self._lock:
            self.artifacts.append({"label": label, "content": content, "kind": kind})

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def has_content(self) -> bool:
        return len(self.calls) > 0 or len(self.artifacts) > 0

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started_at_mono) * 1000)


_current_step: ContextVar[Optional[StepTraceContext]] = ContextVar("_current_step", default=None)


@contextmanager
def enter_step(
    step_id: str,
    step_kind: str,
    group_key: str,
    group_label: str,
    stage: str,
    title: str,
):
    """进入步骤上下文。退出时自动清理。"""
    ctx = StepTraceContext(
        step_id=step_id,
        step_kind=step_kind,
        group_key=group_key,
        group_label=group_label,
        stage=stage,
        title=title,
    )
    token = _current_step.set(ctx)
    try:
        yield ctx
    finally:
        _current_step.reset(token)


def get_current_step() -> Optional[StepTraceContext]:
    """获取当前线程/协程的活动步骤上下文，无则返回 None。"""
    return _current_step.get(None)


def record_call(call_data: Dict[str, Any]) -> None:
    """向当前步骤追加调用记录。若无活动步骤则静默跳过。"""
    ctx = _current_step.get(None)
    if ctx is not None:
        ctx.record_call(call_data)


def record_artifact(label: str, content: str, kind: str = "text") -> None:
    """向当前步骤追加产物记录。若无活动步骤则静默跳过。"""
    ctx = _current_step.get(None)
    if ctx is not None:
        ctx.record_artifact(label, content, kind)


def new_step_id() -> str:
    """生成唯一步骤 ID。"""
    return f"step_{uuid.uuid4().hex[:12]}"
