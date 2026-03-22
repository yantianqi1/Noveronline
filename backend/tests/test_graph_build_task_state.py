import time
import io

from app import create_app
from app.models.project import ProjectManager
from app.models.project_types import ProjectStatus
from app.models.task import TaskManager, TaskStatus


def build_small_novel() -> str:
    return "\n\n".join(
        [
            "第1章 山门雪夜\n沈夜在玄霄宗山门前跪了一夜，只为等一封来自白泽司的密信。秦昭提醒他镜湖谷试炼名单已经被动过。",
            "第2章 密信开封\n苏半夏替沈夜拆开密信，信里提到镜湖引擎能够读取修士识海残痕。玄霄宗和白泽司都在追查这件事。",
            "第3章 谷口对峙\n顾行舟、林雁回与霍承安同时逼近镜湖谷。沈夜决定在试炼开始前公开一部分真相。",
        ]
    )


def wait_for_task_runtime(task_id: str, timeout: float = 15.0):
    deadline = time.time() + timeout
    manager = TaskManager()
    latest = None
    while time.time() < deadline:
        latest = manager.get_task(task_id)
        if latest and latest.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"任务超时未完成: {task_id}, latest={latest.to_dict() if latest else None}")


def create_seed_project(client):
    upload = io.BytesIO(build_small_novel().encode("utf-8"))
    response = client.post(
        "/api/project/seed/extract",
        data={
            "analysis_goal": "提取角色、组织、地点、物件与关系，用于故事图谱和世界线推演",
            "project_name": "本地图谱测试",
            "use_llm": "false",
            "files": (upload, "local-graph-novel.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["task_id"]
    task = wait_for_task_runtime(task_id)
    assert task.status == TaskStatus.COMPLETED
    return response.get_json()["data"]["project_id"]


def test_graph_build_completion_updates_project_without_task_polling(tmp_path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")

    app = create_app()
    client = app.test_client()
    project_id = create_seed_project(client)

    response = client.post(
        "/api/project/build-graph",
        json={"project_id": project_id, "graph_name": "Novel Story Graph"},
    )
    assert response.status_code == 200, response.get_json()
    task_id = response.get_json()["data"]["task_id"]

    task = wait_for_task_runtime(task_id)
    assert task.status == TaskStatus.COMPLETED

    project = ProjectManager.get_project(project_id)
    assert project is not None
    assert project.status == ProjectStatus.GRAPH_COMPLETED
    assert project.graph_id == f"local_graph_{project_id}"
