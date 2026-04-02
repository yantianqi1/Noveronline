import io
import json
import time

from app import create_app
from app.config import Config
from app.models.project import ProjectManager
from app.services.local_block_fact_extractor import LocalBlockFactExtractor
from .seed_test_helpers import install_fake_seed_llm


def build_chaptered_novel() -> str:
    sections = [
        "第1章 山门雪夜\n沈夜在玄霄宗山门前跪了一夜，只为等一封来自白泽司的密信。秦昭在风雪里出现，提醒他宗门里有人提前知道试炼名单。",
        "第2章 密信开封\n苏半夏在药庐里替沈夜拆开密信，信中提到镜湖引擎能够读取修士识海残痕。三人意识到沈临川旧案并未结束。",
        "第3章 谷口对峙\n顾行舟、林雁回与霍承安同时逼近镜湖谷，沈夜必须决定公开真相还是继续潜伏。秦昭提醒他，每一个选择都会生成新的世界线。",
    ]
    return "\n\n".join(sections)


def build_uneven_block_novel() -> str:
    def section(order: int, body_size: int) -> str:
        return f"第{order}章 分段测试\n" + ("甲" * body_size)

    return "\n\n".join(
        [
            section(1, 1600),
            section(2, 1600),
            section(3, 1800),
            section(4, 5200),
            section(5, 1000),
            section(6, 1100),
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


def test_seed_extract_returns_task_immediately(tmp_path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    Config.ZEP_API_KEY = None

    app = create_app()
    client = app.test_client()
    upload = io.BytesIO(build_chaptered_novel().encode("utf-8"))

    started_at = time.time()
    response = client.post(
        "/api/project/seed/extract",
        data={
            "analysis_goal": "提取角色、组织与关系并用于平行世界推演",
            "project_name": "异步上传测试",
            "use_llm": "false",
            "files": (upload, "chaptered_novel.txt"),
        },
        content_type="multipart/form-data",
    )
    elapsed = time.time() - started_at

    assert response.status_code == 400, response.get_json()
    assert "仅支持 LLM 模式" in response.get_json()["error"]
    assert elapsed < 3


def test_async_seed_pipeline_generates_chapter_outputs(tmp_path, monkeypatch):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    Config.ZEP_API_KEY = None
    install_fake_seed_llm(monkeypatch)

    app = create_app()
    client = app.test_client()
    upload = io.BytesIO(build_chaptered_novel().encode("utf-8"))

    response = client.post(
        "/api/project/seed/extract",
        data={
            "analysis_goal": "提取角色、组织与关系并用于平行世界推演",
            "project_name": "章节连续性测试",
            "files": (upload, "chaptered_novel.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202, response.get_json()
    payload = response.get_json()["data"]
    task = wait_for_task(client, payload["task_id"])
    assert task["status"] == "completed", task

    project_id = payload["project_id"]
    project_dir = ProjectManager._get_project_dir(project_id)
    segments_path = f"{project_dir}/chapter_segments.json"
    continuity_path = f"{project_dir}/chapter_continuity.json"
    chapter_cards_path = f"{project_dir}/chapter_cards.json"
    seed_analysis_path = f"{project_dir}/seed_analysis.json"

    with open(segments_path, "r", encoding="utf-8") as file_obj:
        segments = json.load(file_obj)
    with open(continuity_path, "r", encoding="utf-8") as file_obj:
        continuity = json.load(file_obj)
    with open(chapter_cards_path, "r", encoding="utf-8") as file_obj:
        chapter_cards = json.load(file_obj)
    with open(seed_analysis_path, "r", encoding="utf-8") as file_obj:
        seed_analysis = json.load(file_obj)

    assert len(segments["chapters"]) == 3
    assert chapter_cards["chapter_count"] == 3
    assert chapter_cards["chapters"][0]["summary_text"]
    assert segments["chapters"][0]["title"].startswith("第1章")
    assert continuity["chapters"][0]["continuity_summary"]
    assert "tail_hooks" in continuity["chapters"][1]
    assert seed_analysis["characters"]

    project_resp = client.get(f"/api/project/{project_id}")
    assert project_resp.status_code == 200, project_resp.get_json()
    project = project_resp.get_json()["data"]
    assert project["status"] in {"seed_completed", "ontology_generated"}
    assert project["ontology"]


def test_async_seed_pipeline_uses_dynamic_char_based_analysis_blocks(tmp_path, monkeypatch):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    Config.ZEP_API_KEY = None
    install_fake_seed_llm(monkeypatch)

    app = create_app()
    client = app.test_client()
    upload = io.BytesIO(build_uneven_block_novel().encode("utf-8"))

    response = client.post(
        "/api/project/seed/extract",
        data={
            "analysis_goal": "提取角色、组织与关系并用于平行世界推演",
            "project_name": "动态分块测试",
            "files": (upload, "uneven_chaptered_novel.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202, response.get_json()
    payload = response.get_json()["data"]
    task = wait_for_task(client, payload["task_id"])
    assert task["status"] == "completed", task

    project_dir = ProjectManager._get_project_dir(payload["project_id"])
    analysis_blocks_path = f"{project_dir}/analysis_blocks.json"

    with open(analysis_blocks_path, "r", encoding="utf-8") as file_obj:
        analysis_blocks = json.load(file_obj)

    assert analysis_blocks["target_owned_char_count"] == 5000
    assert analysis_blocks["block_count"] == 3
    assert analysis_blocks["blocks"][0]["owned_chapter_ids"] == ["chapter_0001", "chapter_0002", "chapter_0003"]
    assert analysis_blocks["blocks"][1]["owned_chapter_ids"] == ["chapter_0004"]
    assert analysis_blocks["blocks"][2]["owned_chapter_ids"] == ["chapter_0005", "chapter_0006"]


def test_seed_extract_returns_task_immediately_in_llm_mode(tmp_path, monkeypatch):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    Config.ZEP_API_KEY = None
    install_fake_seed_llm(monkeypatch)

    app = create_app()
    client = app.test_client()
    upload = io.BytesIO(build_chaptered_novel().encode("utf-8"))

    started_at = time.time()
    response = client.post(
        "/api/project/seed/extract",
        data={
            "analysis_goal": "提取角色、组织与关系并用于平行世界推演",
            "project_name": "异步上传测试-LMM",
            "files": (upload, "chaptered_novel.txt"),
        },
        content_type="multipart/form-data",
    )
    elapsed = time.time() - started_at

    assert response.status_code == 202, response.get_json()
    data = response.get_json()["data"]
    assert data["status"] == "processing"
    assert data["task_id"]
    assert data["project_id"]
    assert elapsed < 3


def test_task_progress_detail_exposes_structured_seed_logs(tmp_path, monkeypatch):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    Config.ZEP_API_KEY = None
    install_fake_seed_llm(monkeypatch)

    original_extract_blocks = LocalBlockFactExtractor.extract_blocks

    def slow_extract_blocks(self, blocks, chapters, use_llm, skeleton=None, anchors=None, progress_callback=None):
        time.sleep(0.25)
        return original_extract_blocks(self, blocks, chapters, use_llm, skeleton, anchors, progress_callback)

    monkeypatch.setattr(LocalBlockFactExtractor, "extract_blocks", slow_extract_blocks)

    app = create_app()
    client = app.test_client()
    upload = io.BytesIO(build_chaptered_novel().encode("utf-8"))

    response = client.post(
        "/api/project/seed/extract",
        data={
            "analysis_goal": "提取角色、组织与关系并用于平行世界推演",
            "project_name": "结构化日志测试",
            "files": (upload, "chaptered_novel.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202, response.get_json()
    payload = response.get_json()["data"]

    processing_task = None
    deadline = time.time() + 5
    while time.time() < deadline:
        poll_response = client.get(f"/api/project/task/{payload['task_id']}")
        assert poll_response.status_code == 200, poll_response.get_json()
        candidate = poll_response.get_json()["data"]
        detail = candidate.get("progress_detail") or {}
        if candidate["status"] == "processing" and detail.get("timeline"):
            processing_task = candidate
            break
        time.sleep(0.05)

    assert processing_task is not None
    detail = processing_task["progress_detail"]
    assert detail["active_stage"]["key"]
    assert detail["active_stage"]["label"]
    assert detail["task_metrics"]["chapter_count"] >= 0
    assert detail["task_metrics"]["active_workers"] >= 0
    assert detail["llm_activity"]["mode"] == "llm"
    assert detail["llm_activity"]["enabled"] is True
    assert detail["timeline"]

    completed_task = wait_for_task(client, payload["task_id"])
    completed_detail = completed_task["progress_detail"]
    assert completed_detail["active_stage"]["status"] == "completed"
    assert completed_detail["timeline"][-1]["status"] == "completed"
    assert completed_detail["timeline"][-1]["title"]
    assert completed_detail["timeline"][-1]["timestamp"]
    assert any(item["stage"] == "skeleton_timeline" for item in completed_detail["timeline"])
    assert any(item["stage"] == "anchor_generation" for item in completed_detail["timeline"])
    assert any(item["stage"] == "chapter_card_generation" for item in completed_detail["timeline"])
    assert completed_detail["task_metrics"]["chapter_count"] == 3
    assert completed_detail["task_metrics"]["block_count"] >= 1
