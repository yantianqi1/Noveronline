from app import create_app
from app.models.project import ProjectManager
from app.models.project_types import ProjectStatus
from app.models.task import TaskManager


def reset_task_manager() -> None:
    TaskManager._instance = None


def create_orphan_seed_project(tmp_path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    reset_task_manager()
    project = ProjectManager.create_project(name="任务恢复测试")
    project.status = ProjectStatus.SEED_PROCESSING
    project.seed_task_id = "missing-seed-task"
    ProjectManager.save_project(project)
    return project


def test_get_project_marks_orphan_seed_task_as_failed(tmp_path):
    project = create_orphan_seed_project(tmp_path)
    app = create_app()
    client = app.test_client()

    response = client.get(f"/api/project/{project.project_id}")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["status"] == "failed"
    assert payload["seed_task_id"] is None
    assert "服务可能已重启" in payload["error"]


def test_get_task_returns_failed_payload_for_orphan_seed_task(tmp_path):
    project = create_orphan_seed_project(tmp_path)
    app = create_app()
    client = app.test_client()

    response = client.get("/api/project/task/missing-seed-task")

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["task_id"] == "missing-seed-task"
    assert payload["status"] == "failed"
    assert "服务可能已重启" in payload["error"]

    project_response = client.get(f"/api/project/{project.project_id}")
    project_payload = project_response.get_json()["data"]
    assert project_payload["status"] == "failed"


def test_get_task_disables_http_caching_for_live_progress(tmp_path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    reset_task_manager()
    manager = TaskManager()
    task_id = manager.create_task(task_type="seed_extract")
    app = create_app()
    client = app.test_client()

    response = client.get(f"/api/project/task/{task_id}")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
