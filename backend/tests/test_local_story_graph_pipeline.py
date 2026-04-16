import asyncio
import io
import os
import sqlite3
import time

from app import create_app
from app.config import Config
from app.models.project import ProjectManager
from app.models.task import TaskManager, TaskStatus
from app.services.seed_extract_task_service import SeedExtractTaskService
from app.services.zep_entity_reader import ZepEntityReader


def build_small_novel() -> str:
    return "\n\n".join(
        [
            "第1章 山门雪夜\n沈夜在玄霄宗山门前跪了一夜，只为等一封来自白泽司的密信。秦昭提醒他镜湖谷试炼名单已经被动过。",
            "第2章 密信开封\n苏半夏替沈夜拆开密信，信里提到镜湖引擎能够读取修士识海残痕。玄霄宗和白泽司都在追查这件事。",
            "第3章 谷口对峙\n顾行舟、林雁回与霍承安同时逼近镜湖谷。沈夜决定在试炼开始前公开一部分真相。",
        ]
    )


def wait_for_task(client, task_id: str, timeout: float = 15.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        response = client.get(f"/api/project/task/{task_id}")
        assert response.status_code == 200, response.get_json()
        latest = response.get_json()["data"]
        if latest["status"] in {"completed", "failed"}:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"任务超时未完成: {task_id}, latest={latest}")


def create_seed_project(client):
    Config.UPLOAD_FOLDER = os.path.dirname(ProjectManager.PROJECTS_DIR)
    project = ProjectManager.create_project("本地图谱测试")
    project.analysis_goal = "提取角色、组织、地点、物件与关系，用于故事图谱和世界线推演"
    files_dir = os.path.join(ProjectManager._get_project_dir(project.project_id), "files")
    os.makedirs(files_dir, exist_ok=True)
    with open(os.path.join(files_dir, "local-graph-novel.txt"), "w", encoding="utf-8") as file_obj:
        file_obj.write(build_small_novel())
    project.files = [{
        "filename": "local-graph-novel.txt",
        "saved_filename": "local-graph-novel.txt",
        "size": len(build_small_novel()),
    }]
    ProjectManager.save_project(project)

    # Run create_task + wait for worker completion in a single asyncio loop —
    # asyncio.run would kill the create_task()-scheduled background worker on
    # loop close, leaving the task permanently PENDING.
    async def _create_and_wait() -> str:
        service = SeedExtractTaskService()
        task_id = await service.create_task(
            project.project_id,
            project.name,
            project.analysis_goal,
            "",
            False,
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            task = await service.task_manager.get_task(task_id)
            if task and task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
                assert task.status == TaskStatus.COMPLETED, task.to_dict()
                return task_id
            await asyncio.sleep(0.05)
        raise AssertionError(f"seed task did not complete: {task_id}")

    asyncio.run(_create_and_wait())
    return project.project_id


def test_build_graph_creates_local_story_graph_and_query_api(tmp_path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    TaskManager._instance = None

    app = create_app()
    client = app.test_client()
    project_id = create_seed_project(client)

    response = client.post(
        "/api/project/build-graph",
        json={"project_id": project_id, "graph_name": "Novel Story Graph"},
    )
    assert response.status_code == 200, response.get_json()
    task = wait_for_task(client, response.get_json()["data"]["task_id"])
    assert task["status"] == "completed", task
    assert task["result"]["graph_id"] == f"local_graph_{project_id}"

    graph_response = client.get(f"/api/project/{project_id}/graph")
    assert graph_response.status_code == 200, graph_response.get_json()
    payload = graph_response.get_json()["data"]
    assert payload["graph_id"] == f"local_graph_{project_id}"
    assert payload["nodes"]
    assert payload["edges"]
    assert payload["built_at"]
    assert all("evidence_refs" in item for item in payload["nodes"])
    assert all("evidence_refs" in item for item in payload["edges"])

    # Graph data now persists to the unified DB (graph_nodes / graph_edges)
    # instead of legacy per-project story_graph.json / story_graph.sqlite3.
    from app.database import get_engine
    from sqlalchemy import text
    with get_engine().connect() as conn:
        node_count = conn.execute(
            text("SELECT COUNT(*) FROM graph_nodes WHERE project_id = :pid"),
            {"pid": project_id},
        ).scalar()
        edge_count = conn.execute(
            text("SELECT COUNT(*) FROM graph_edges WHERE project_id = :pid"),
            {"pid": project_id},
        ).scalar()
    assert node_count >= 4
    assert edge_count >= 3


def test_local_graph_reader_exposes_entities_for_archives_and_worldbuilding(tmp_path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    TaskManager._instance = None

    app = create_app()
    client = app.test_client()
    project_id = create_seed_project(client)

    build_response = client.post(
        "/api/project/build-graph",
        json={"project_id": project_id, "graph_name": "Novel Story Graph"},
    )
    assert build_response.status_code == 200, build_response.get_json()
    build_task = wait_for_task(client, build_response.get_json()["data"]["task_id"])
    assert build_task["status"] == "completed", build_task
    graph_id = build_task["result"]["graph_id"]

    reader = ZepEntityReader()
    filtered = reader.filter_defined_entities(graph_id=graph_id, enrich_with_edges=True)
    entity_names = {item.name for item in filtered.entities}
    entity_types = {item.get_entity_type() for item in filtered.entities}

    assert "沈夜" in entity_names
    assert "玄霄宗" in entity_names
    assert "Character" in entity_types
    assert "Organization" in entity_types

    archives_response = client.post(
        "/api/novel/archives/generate",
        json={"project_id": project_id, "graph_id": graph_id, "use_llm": False},
    )
    assert archives_response.status_code == 200, archives_response.get_json()
    assert archives_response.get_json()["data"]["count"] >= 2
