import io
import json
import time

from app import create_app
from app.config import Config
from app.models.project import ProjectManager

from .seed_test_helpers import install_fake_seed_llm


def build_long_novel(chapter_count: int = 120) -> str:
    sections = []
    for order in range(1, chapter_count + 1):
        sections.append(
            (
                f"第{order}章 镜湖回声\n"
                f"沈夜在第{order}章继续追查镜湖旧案。"
                f"角色{order:03d}带来了新的线索，组织{order:03d}宗也在暗中推进布局。"
                f"章末的异响提醒众人，旧案还远未结束。"
            )
        )
    return "\n\n".join(sections)


def wait_for_task(client, task_id: str, timeout: float = 20.0):
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


def test_long_novel_pipeline_builds_anchors_and_adaptive_snapshots(tmp_path, monkeypatch):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    Config.ZEP_API_KEY = None
    install_fake_seed_llm(monkeypatch)

    app = create_app()
    client = app.test_client()
    upload = io.BytesIO(build_long_novel().encode("utf-8"))

    response = client.post(
        "/api/project/seed/extract",
        data={
            "analysis_goal": "提取长篇小说中的角色、组织、关系与持续线索",
            "project_name": "超长篇回归测试",
            "files": (upload, "long_novel.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202, response.get_json()

    payload = response.get_json()["data"]
    task = wait_for_task(client, payload["task_id"])
    assert task["status"] == "completed", task

    project_dir = ProjectManager._get_project_dir(payload["project_id"])
    with open(f"{project_dir}/anchor_points.json", "r", encoding="utf-8") as file_obj:
        anchors = json.load(file_obj)
    with open(f"{project_dir}/story_memory.json", "r", encoding="utf-8") as file_obj:
        story_memory = json.load(file_obj)
    with open(f"{project_dir}/story_memory_snapshots.json", "r", encoding="utf-8") as file_obj:
        snapshots = json.load(file_obj)["snapshots"]

    final_snapshot = next(item for item in snapshots if item["block_id"] == "block_0012")

    assert anchors["anchor_count"] == 3
    assert final_snapshot["nearest_anchor"]["anchor_id"] == "anchor_0002"
    # Service now scopes relevant_entities to entities actually referenced in
    # the block's evidence windows (previously cumulative across the full
    # entity registry). Enforce a floor rather than an exact count so future
    # fixture tweaks don't have to edit the test in lockstep.
    assert len(final_snapshot["relevant_entities"]) >= 5
    assert final_snapshot["block_fingerprints"]
    assert "夜哥" not in story_memory["entity_registry"]
    assert "沈夜" in story_memory["entity_registry"]
