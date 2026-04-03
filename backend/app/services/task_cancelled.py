"""Exception raised when a running task detects it has been cancelled."""


class TaskCancelledException(Exception):
    """Raised when a worker detects its task has been cancelled."""

    def __init__(self, task_id: str, stage: str = ""):
        self.task_id = task_id
        self.stage = stage
        super().__init__(f"任务已取消: {task_id} (stage={stage})")
