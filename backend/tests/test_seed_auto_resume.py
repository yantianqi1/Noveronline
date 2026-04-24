"""Auto-resume on server startup contract test (F4).

Flow: _recover_stale_tasks flags zombie tasks as failed; _auto_resume_seed_tasks
then schedules a fresh retry task for every project whose smart_segments.json
is already on disk. Projects that never made it past stage 1 stay FAILED.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

import pytest

from app.config import Config
from app.database import get_engine
from app.main import _auto_resume_seed_tasks, _recover_stale_tasks
from app.models.project import Project, ProjectManager, ProjectStatus
from app.models.task import TaskManager, TaskStatus
from app.repositories.task_repo import TaskRepository


def _reset_task_manager() -> None:
    TaskManager._instance = None


def _seed_stale_task(task_id: str, task_type: str = "seed_extract") -> None:
    """Insert a task_runs row in processing state to simulate a zombie."""
    now = datetime.now().isoformat()
    repo = TaskRepository(get_engine())
    repo.update_task({
        "task_id": task_id,
        "task_type": task_type,
        "status": TaskStatus.PROCESSING.value,
        "created_at": now,
        "updated_at": now,
        "progress": 20,
        "message": "mid-flight kill",
        "result_json": None,
        "error": None,
        "metadata_json": "{}",
        "progress_detail_json": "{}",
    })


def _make_project_with_segments(tmp_path, monkeypatch, project_id: str) -> str:
    """Make a project in SEED_PROCESSING + smart_segments.json on disk."""
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_dir))
    monkeypatch.setattr(
        ProjectManager, "PROJECTS_DIR", str(upload_dir / "projects"),
    )
    project_dir = upload_dir / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat()
    project = Project(
        project_id=project_id,
        name="auto resume test",
        status=ProjectStatus.SEED_PROCESSING,
        created_at=now,
        updated_at=now,
        analysis_goal="",
        seed_task_id="stale-seed-1",
    )
    ProjectManager.save_project(project)
    (project_dir / "smart_segments.json").write_text(
        json.dumps({"segments": [
            {"segment_id": "seg_001", "chapters": []},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(project_dir)


def test_auto_resume_enqueues_retry_for_resumable_project(tmp_path, monkeypatch):
    _reset_task_manager()
    project_id = "proj_auto_resume_ok"
    _make_project_with_segments(tmp_path, monkeypatch, project_id)
    _seed_stale_task("stale-seed-1")

    # _recover_stale_tasks 会把 stale task 标为 failed + 项目复位成 FAILED
    # （seed_task_id 保留为僵尸 id，让 _auto_resume_seed_tasks 知道这个槽位
    # 是"等待恢复"而不是"别人在跑"）。
    stale_ids = _recover_stale_tasks(get_engine())
    assert stale_ids == ["stale-seed-1"]
    project = ProjectManager.get_project(project_id)
    assert project.status == ProjectStatus.FAILED
    assert project.seed_task_id == "stale-seed-1"

    # 防止 create_retry_task 的后台 worker 去打真实 LLM。
    from app.services import seed_extract_task_service as sets_mod

    async def _noop_worker(self, task_id, project_id, additional_context):
        return None

    monkeypatch.setattr(sets_mod.SeedExtractTaskService, "_run_retry_worker", _noop_worker)

    asyncio.run(_auto_resume_seed_tasks(stale_ids))

    project = ProjectManager.get_project(project_id)
    # 新 retry task 应该被挂到 project 上；id 不再是老僵尸
    assert project.seed_task_id is not None
    assert project.seed_task_id != "stale-seed-1"

    manager = TaskManager()
    new_task = asyncio.run(manager.get_task(project.seed_task_id))
    assert new_task is not None
    assert new_task.task_type == "seed_retry_segments"


def test_auto_resume_skips_project_without_smart_segments(tmp_path, monkeypatch):
    """Stage 1 还没完成（smart_segments.json 不存在）的项目没法断点续传，
    应当保持在 FAILED 让用户去点"重新开始"，不能给它挂一条 retry task。"""
    _reset_task_manager()
    project_id = "proj_auto_resume_stage1_only"
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_dir))
    monkeypatch.setattr(
        ProjectManager, "PROJECTS_DIR", str(upload_dir / "projects"),
    )
    (upload_dir / "projects" / project_id).mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat()
    ProjectManager.save_project(Project(
        project_id=project_id,
        name="stage1-only",
        status=ProjectStatus.SEED_PROCESSING,
        created_at=now,
        updated_at=now,
        seed_task_id="stale-seed-2",
    ))
    _seed_stale_task("stale-seed-2")

    stale_ids = _recover_stale_tasks(get_engine())
    assert "stale-seed-2" in stale_ids

    from app.services import seed_extract_task_service as sets_mod

    async def _noop_worker(self, task_id, project_id, additional_context):
        return None

    monkeypatch.setattr(sets_mod.SeedExtractTaskService, "_run_retry_worker", _noop_worker)

    asyncio.run(_auto_resume_seed_tasks(stale_ids))

    project = ProjectManager.get_project(project_id)
    assert project.status == ProjectStatus.FAILED
    # seed_task_id 仍然指向老僵尸（还没被替换），说明 auto-resume 没给它挂新 task
    assert project.seed_task_id == "stale-seed-2"
