"""End-to-end integration tests for the new 4-stage seed pipeline."""

import io
import json
import os
import time

import pytest

from app import create_app
from app.config import Config
from app.models.project import ProjectManager, ProjectStatus

from tests.seed_test_helpers import install_fake_seed_llm

NOVEL_TEXT = """
第1章 镜湖夜

沈夜站在镜湖边，月光洒在湖面上。
"真相不会自己浮出水面。"沈夜低声道。
秦昭从暗处走出，手中握着一份密函。"夜哥，玄霄宗的人已经到了山脚。"
苏半夏冷静地安排着防线。她是队伍中最沉稳的人。
玄霄宗与白泽司的暗中博弈已经持续了数月。回声会在两方之间暗中活动。

第2章 宗门之变

清晨，玄霄宗的使者到达了。
沈夜与使者对峙，气氛紧张。秦昭始终站在沈夜身后。
"你们要的东西，我们没有。"沈夜的声音很平静。
白泽司的探子带来了新的情报——镜湖下方藏着一条密道。
苏半夏已经提前勘察了周围的地形。

第3章 暗流涌动

夜幕降临，沈夜独自进入密道。
密道深处，他发现了回声会留下的标记。这说明回声会比所有人都早一步到达了这里。
秦昭在入口处守护，不让任何人靠近。
"镜湖旧案的真相，或许就在这密道尽头。"沈夜心想。
""".strip()


def wait_for_task(client, task_id, timeout_s=15.0, poll_interval_s=0.05):
    """Poll task status until completed/failed or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/api/project/task/{task_id}")
        assert resp.status_code == 200, f"Task poll failed: {resp.status_code} {resp.data}"
        data = resp.get_json()
        task_data = data.get("data") or data
        status = task_data.get("status", "")
        if status in ("completed", "failed"):
            return task_data
        time.sleep(poll_interval_s)
    raise TimeoutError(f"Task {task_id} did not complete within {timeout_s}s")


def test_new_pipeline_end_to_end(tmp_path, monkeypatch):
    """Full pipeline with fake LLM: upload -> extract -> segment -> read -> integrate -> profiles."""
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    Config.ZEP_API_KEY = None
    install_fake_seed_llm(monkeypatch)

    app = create_app()
    client = app.test_client()

    file_data = (io.BytesIO(NOVEL_TEXT.encode("utf-8")), "test_novel.txt")
    resp = client.post(
        "/api/project/seed/extract",
        data={
            "files": file_data,
            "analysis_goal": "分析镜湖旧案的人物关系与剧情线",
            "project_name": "镜湖测试",
            "use_llm": "true",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 202, f"Upload failed: {resp.status_code} {resp.data}"
    upload_data = resp.get_json()["data"]
    project_id = upload_data["project_id"]
    task_id = upload_data["task_id"]

    task_result = wait_for_task(client, task_id)
    assert task_result["status"] == "completed", f"Task failed: {task_result.get('error', task_result)}"

    # Verify project status
    project = ProjectManager.get_project(project_id)
    assert project is not None
    assert project.status == ProjectStatus.ONTOLOGY_GENERATED

    # Verify seed_analysis.json
    project_dir = ProjectManager._get_project_dir(project_id)
    seed_path = os.path.join(project_dir, "seed_analysis.json")
    assert os.path.exists(seed_path), "seed_analysis.json not found"
    with open(seed_path, "r", encoding="utf-8") as f:
        seed_analysis = json.load(f)
    character_names = [c["name"] for c in seed_analysis.get("characters", [])]
    assert len(character_names) >= 3, f"Expected >= 3 characters, got {character_names}"
    assert "沈夜" in character_names

    # Verify reading_notes.json
    notes_path = os.path.join(project_dir, "reading_notes.json")
    assert os.path.exists(notes_path), "reading_notes.json not found"
    with open(notes_path, "r", encoding="utf-8") as f:
        reading_notes = json.load(f)
    notes_characters = reading_notes.get("notes", {}).get("core_facts", {}).get("characters", {})
    assert "沈夜" in notes_characters, f"沈夜 not found in reading notes characters: {list(notes_characters.keys())}"

    # Verify agent_profiles.json
    profiles_path = os.path.join(project_dir, "agent_profiles.json")
    assert os.path.exists(profiles_path), "agent_profiles.json not found"
    with open(profiles_path, "r", encoding="utf-8") as f:
        agent_profiles = json.load(f)
    # Short test novel has only 1 segment, so characters may not meet the
    # importance threshold (default=2). Profile generation is tested separately
    # in test_character_agent_profile_generator.py. Here we just verify the
    # artifact is produced.
    assert "profile_count" in agent_profiles


def test_new_pipeline_offline(tmp_path, monkeypatch):
    """Offline mode: invoke service directly (endpoint rejects use_llm=false)."""
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    Config.ZEP_API_KEY = None
    install_fake_seed_llm(monkeypatch)

    app = create_app()

    with app.app_context():
        # Create project manually
        project = ProjectManager.create_project(name="离线测试")
        project.analysis_goal = "离线分析"
        project_id = project.project_id

        # Save file manually
        project_dir = ProjectManager._get_project_dir(project_id)
        files_dir = os.path.join(project_dir, "files")
        os.makedirs(files_dir, exist_ok=True)
        file_path = os.path.join(files_dir, "test_novel.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(NOVEL_TEXT)
        project.files = [{"filename": "test_novel.txt", "saved_filename": "test_novel.txt", "size": len(NOVEL_TEXT)}]
        ProjectManager.save_project(project)

        from app.services.seed_extract_task_service import SeedExtractTaskService
        service = SeedExtractTaskService()
        task_id = service.create_task(
            project_id=project_id,
            project_name="离线测试",
            analysis_goal="离线分析",
            additional_context="",
            use_llm=False,
        )

        # Wait for task completion
        deadline = time.time() + 15.0
        while time.time() < deadline:
            task = service.task_manager.get_task(task_id)
            if task and task.status in ("completed", "failed"):
                break
            time.sleep(0.05)

        task = service.task_manager.get_task(task_id)
        assert task is not None
        assert task.status == "completed", f"Task failed: {task.error}"

        # Verify seed_analysis.json exists
        seed_path = os.path.join(project_dir, "seed_analysis.json")
        assert os.path.exists(seed_path), "seed_analysis.json not found"
        with open(seed_path, "r", encoding="utf-8") as f:
            seed_analysis = json.load(f)
        # Offline mode produces minimal data but should still complete
        assert "characters" in seed_analysis

        # Verify reading_notes.json exists
        notes_path = os.path.join(project_dir, "reading_notes.json")
        assert os.path.exists(notes_path), "reading_notes.json not found"

        # Verify agent_profiles.json exists
        profiles_path = os.path.join(project_dir, "agent_profiles.json")
        assert os.path.exists(profiles_path), "agent_profiles.json not found"
