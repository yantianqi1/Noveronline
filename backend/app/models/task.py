"""
任务状态管理
用于跟踪长时间运行的任务（如图谱构建）
"""

import asyncio
import logging
import uuid
import json
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Any, Optional
from dataclasses import dataclass, field

from ..database import get_engine
from ..repositories.task_repo import TaskRepository

logger = logging.getLogger(__name__)


def _log_if_failed(task: asyncio.Task) -> None:
    """Done-callback for fire-and-forget coroutines scheduled via sync_bridge
    on the event loop thread. Surfaces failures that would otherwise be
    silently swallowed."""
    try:
        exc = task.exception()
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        return
    if exc is not None:
        logger.exception("sync_bridge fire-and-forget task failed: %s", exc)


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"          # 等待中
    PROCESSING = "processing"    # 处理中
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"            # 失败
    CANCELLED = "cancelled"      # 已取消


@dataclass
class Task:
    """任务数据类"""
    task_id: str
    task_type: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    progress: int = 0              # 总进度百分比 0-100
    message: str = ""              # 状态消息
    result: Optional[Dict] = None  # 任务结果
    error: Optional[str] = None    # 错误信息
    metadata: Dict = field(default_factory=dict)  # 额外元数据
    progress_detail: Dict = field(default_factory=dict)  # 详细进度信息
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "progress": self.progress,
            "message": self.message,
            "progress_detail": self.progress_detail,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class TaskManager:
    """
    任务管理器
    协程安全的任务状态管理（asyncio.Lock）
    """

    _instance = None
    _init_lock = asyncio.Lock()
    _instance_ready = False

    def __new__(cls):
        """单例模式 — 同步部分只创建对象壳。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._task_lock = asyncio.Lock()
            cls._instance._storage = TaskRepository(get_engine())
            cls._instance._loop: Optional[asyncio.AbstractEventLoop] = None
            cls._instance_ready = True
        return cls._instance

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Cache the running event loop for sync bridge calls."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        return self._loop

    def sync_bridge(self, coro):
        """Run an async TaskManager coroutine from a sync context (e.g. a
        background thread started via ``asyncio.to_thread``).  Falls back to
        ``asyncio.run`` when no loop is cached.

        If invoked while already running on the cached event loop thread
        (e.g. an async coroutine's ``except`` block calling ``progress.fail``
        which internally dispatches through ``sync_bridge``), blocking on
        ``future.result()`` would deadlock: the current thread IS the
        event loop, so scheduling the coroutine on that loop and then
        blocking prevents the loop from ever running it. In that case we
        schedule it as a fire-and-forget task instead; progress updates
        complete asynchronously as soon as the current coroutine yields.
        """
        loop = self._ensure_loop()
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is not None and current_loop is loop:
            task = asyncio.ensure_future(coro, loop=loop)
            task.add_done_callback(_log_if_failed)
            return None
        if loop is not None and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result()
        # No cached loop — last resort
        return asyncio.run(coro)

    def _serialize(self, task: Task) -> Dict[str, Any]:
        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status.value,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
            "progress": task.progress,
            "message": task.message,
            "result_json": json.dumps(task.result, ensure_ascii=False) if task.result is not None else None,
            "error": task.error,
            "metadata_json": json.dumps(task.metadata, ensure_ascii=False),
            "progress_detail_json": json.dumps(task.progress_detail, ensure_ascii=False),
        }

    def _deserialize(self, row) -> Task:
        return Task(
            task_id=row["task_id"],
            task_type=row["task_type"],
            status=TaskStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            progress=row["progress"],
            message=row["message"],
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            error=row["error"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            progress_detail=json.loads(row["progress_detail_json"] or "{}"),
        )

    def _save_task(self, task: Task) -> None:
        payload = self._serialize(task)
        self._storage.update_task(payload)

    def _load_task(self, task_id: str) -> Optional[Task]:
        row = self._storage.get_task(task_id)
        return self._deserialize(row) if row else None
    
    async def create_task(self, task_type: str, metadata: Optional[Dict] = None) -> str:
        """
        创建新任务

        Args:
            task_type: 任务类型
            metadata: 额外元数据

        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())
        now = datetime.now()

        task = Task(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )

        async with self._task_lock:
            self._save_task(task)

        return task_id

    async def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        async with self._task_lock:
            return self._load_task(task_id)

    async def mutate_task(self, task_id: str, mutator: Callable[[Task], None]) -> None:
        """在锁内原子更新任务。"""
        async with self._task_lock:
            task = self._load_task(task_id)
            if not task:
                return
            mutator(task)
            task.updated_at = datetime.now()
            self._save_task(task)

    async def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
        progress_detail: Optional[Dict] = None
    ):
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态
            progress: 进度
            message: 消息
            result: 结果
            error: 错误信息
            progress_detail: 详细进度信息
        """
        async with self._task_lock:
            task = self._load_task(task_id)
            if task:
                task.updated_at = datetime.now()
                if status is not None:
                    task.status = status
                if progress is not None:
                    task.progress = progress
                if message is not None:
                    task.message = message
                if result is not None:
                    task.result = result
                if error is not None:
                    task.error = error
                if progress_detail is not None:
                    task.progress_detail = progress_detail
                self._save_task(task)

    async def complete_task(self, task_id: str, result: Dict):
        """标记任务完成"""
        await self.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="任务完成",
            result=result
        )

    async def fail_task(self, task_id: str, error: str):
        """标记任务失败"""
        await self.update_task(
            task_id,
            status=TaskStatus.FAILED,
            message="任务失败",
            error=error
        )

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a task. Only PROCESSING tasks can be cancelled."""
        async with self._task_lock:
            task = self._load_task(task_id)
            if not task or task.status != TaskStatus.PROCESSING:
                return False
            task.status = TaskStatus.CANCELLED
            task.message = "用户取消了分析任务"
            task.updated_at = datetime.now()
            self._save_task(task)
            return True

    async def is_cancelled(self, task_id: str) -> bool:
        """Check if a task has been cancelled."""
        async with self._task_lock:
            task = self._load_task(task_id)
            return task is not None and task.status == TaskStatus.CANCELLED

    async def list_tasks(self, task_type: Optional[str] = None) -> list:
        """列出任务"""
        async with self._task_lock:
            with self._storage.connect() as connection:
                if task_type:
                    rows = connection.execute(
                        "SELECT * FROM task_runs WHERE task_type = ? ORDER BY created_at DESC",
                        (task_type,),
                    ).fetchall()
                else:
                    rows = connection.execute("SELECT * FROM task_runs ORDER BY created_at DESC").fetchall()
            tasks = [self._deserialize(row) for row in rows]
            return [t.to_dict() for t in sorted(tasks, key=lambda x: x.created_at, reverse=True)]

    async def cleanup_old_tasks(self, max_age_hours: int = 24):
        """清理旧任务"""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(hours=max_age_hours)

        async with self._task_lock:
            with self._storage.connect() as connection:
                connection.execute(
                    """
                    DELETE FROM task_runs
                    WHERE created_at < ? AND status IN (?, ?)
                    """,
                    (
                        cutoff.isoformat(),
                        TaskStatus.COMPLETED.value,
                        TaskStatus.FAILED.value,
                    ),
                )
                connection.commit()
