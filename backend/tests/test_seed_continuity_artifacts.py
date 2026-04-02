import io
import json
import time

from app import create_app
from app.config import Config
from app.models.project import ProjectManager
from .seed_test_helpers import install_fake_seed_llm


def build_twelve_chapter_novel() -> str:
    sections = []
    for order in range(1, 13):
        chapter_body = (
            f"沈夜在第{order}章继续追查镜湖旧案，秦昭陪他潜入玄霄宗外库。"
            f"白泽司与回声会都想抢先控制线索，苏半夏负责稳住局势。"
            f"众人提到沈夜又叫夜哥，但正式身份仍是沈夜。"
        ) * 12
        sections.append(
            (
                f"第{order}章 镜湖余波\n"
                f"{chapter_body}"
            )
        )
    return "\n\n".join(sections)


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


def test_async_seed_pipeline_generates_story_memory_artifacts(tmp_path, monkeypatch):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    Config.ZEP_API_KEY = None
    install_fake_seed_llm(monkeypatch)

    app = create_app()
    client = app.test_client()
    upload = io.BytesIO(build_twelve_chapter_novel().encode("utf-8"))

    response = client.post(
        "/api/project/seed/extract",
        data={
            "analysis_goal": "提取角色、组织、关系与持续剧情线索",
            "project_name": "连续性产物测试",
            "files": (upload, "twelve_chapters.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202, response.get_json()

    payload = response.get_json()["data"]
    task = wait_for_task(client, payload["task_id"])
    assert task["status"] == "completed", task

    project_dir = ProjectManager._get_project_dir(payload["project_id"])
    artifact_names = [
        "analysis_blocks.json",
        "skeleton_timeline.json",
        "anchor_points.json",
        "local_block_facts.json",
        "story_memory.json",
        "story_memory_snapshots.json",
        "block_analyses.json",
        "consistency_report.json",
        "chapter_continuity.json",
        "seed_analysis.json",
    ]

    loaded = {}
    for name in artifact_names:
        with open(f"{project_dir}/{name}", "r", encoding="utf-8") as file_obj:
            loaded[name] = json.load(file_obj)

    blocks = loaded["analysis_blocks.json"]["blocks"]
    skeleton = loaded["skeleton_timeline.json"]
    anchors = loaded["anchor_points.json"]
    snapshots = loaded["story_memory_snapshots.json"]["snapshots"]
    continuity = loaded["chapter_continuity.json"]
    seed_analysis = loaded["seed_analysis.json"]

    assert len(blocks) == 2
    assert skeleton["global_characters"]
    assert skeleton["chapter_sketches"][0]["chapter_id"] == "chapter_0001"
    assert skeleton["chapter_sketches"][0]["fingerprint"]
    assert skeleton["chapter_sketches"][0]["tail_hook"]
    assert anchors["anchor_count"] == 1
    assert blocks[0]["owned_chapter_ids"][0] == "chapter_0001"
    assert blocks[1]["owned_chapter_ids"][0] == f"chapter_{len(blocks[0]['owned_chapter_ids']) + 1:04d}"
    assert blocks[1]["context_chapter_ids"] == blocks[0]["owned_chapter_ids"][-2:]
    assert snapshots[1]["block_id"] == "block_0002"
    assert snapshots[1]["story_so_far"]
    assert "nearest_anchor" in snapshots[1]
    assert snapshots[1]["block_fingerprints"][0]["block_id"] == "block_0001"
    assert continuity["chapter_count"] == 12
    assert continuity["chapters"][10]["head_context"]
    assert seed_analysis["source_stats"]["block_count"] == 2
    assert seed_analysis["story_memory"]["block_count"] == 2
