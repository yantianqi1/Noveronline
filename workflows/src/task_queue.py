from dataclasses import dataclass

from settings import WorkerSettings


@dataclass(frozen=True, slots=True)
class TaskQueueSpec:
    name: str
    namespace: str
    worker_name: str

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "worker_name": self.worker_name,
        }


def build_task_queue_spec(settings: WorkerSettings) -> TaskQueueSpec:
    return TaskQueueSpec(
        name=settings.task_queue,
        namespace=settings.temporal_namespace,
        worker_name=settings.worker_name,
    )
