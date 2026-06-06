from dataclasses import dataclass

from settings import WorkerSettings
from task_queue import TaskQueueSpec, build_task_queue_spec


@dataclass(frozen=True, slots=True)
class WorkerBootstrap:
    settings: WorkerSettings
    task_queue: TaskQueueSpec

    def as_dict(self) -> dict[str, object]:
        return {
            "settings": {
                "temporal_target": self.settings.temporal_target,
                "temporal_namespace": self.settings.temporal_namespace,
                "task_queue": self.settings.task_queue,
                "worker_name": self.settings.worker_name,
            },
            "task_queue": self.task_queue.as_dict(),
        }


def build_worker_bootstrap(settings: WorkerSettings | None = None) -> WorkerBootstrap:
    effective_settings = settings or WorkerSettings()
    return WorkerBootstrap(
        settings=effective_settings,
        task_queue=build_task_queue_spec(effective_settings),
    )
