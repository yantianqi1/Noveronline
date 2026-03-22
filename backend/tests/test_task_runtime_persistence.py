from app.config import Config
from app.models.task import TaskManager, TaskStatus


def reset_task_manager() -> None:
    TaskManager._instance = None


def test_task_manager_persists_tasks_across_singleton_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    reset_task_manager()

    manager = TaskManager()
    task_id = manager.create_task("seed_extract", {"project_id": "proj_demo"})
    manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=42,
        message="正在处理",
        progress_detail={"stage": "extract"},
    )

    reset_task_manager()
    recovered_manager = TaskManager()
    recovered_task = recovered_manager.get_task(task_id)

    assert recovered_task is not None
    assert recovered_task.status == TaskStatus.PROCESSING
    assert recovered_task.progress == 42
    assert recovered_task.message == "正在处理"
    assert recovered_task.progress_detail["stage"] == "extract"

