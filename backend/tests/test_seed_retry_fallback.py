"""断点续传在 reading_notes.json 缺失时的降级路径契约测试。

场景：第一遍 seed_extract 在写出 reading_notes.json 之前就被杀（比如用户
提前关后端 / 外置盘掉线 / 进程被 reload），只剩 smart_segments.json。之前
retry_failed_segments 会直接抛 "项目尚未生成 reading_notes.json"，用户看不
到任何恢复路径。修复后应当用空 ReadingNotesManager 把所有段落当未处理重跑；
只有连 smart_segments.json 都没有时才真正放弃。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import pytest

from app.config import Config
from app.models.project import Project, ProjectManager, ProjectStatus
from app.models.task import TaskManager
from app.services.reading_notes_manager import ReadingNotesManager
from app.services.seed_extract_runner import SeedExtractRunner
from app.services.seed_extract_task_service import SeedExtractTaskService


class _StubSequentialReader:
    """Capture what segments retry iteration wants to re-read."""

    def __init__(self) -> None:
        self.retry_policy = None  # filled in before use
        self.llm_router = None

    def read(self, *a, **kw):  # pragma: no cover - retry path doesn't call .read
        raise AssertionError("retry_failed_segments 不应该调用 read()")


class _StubService(SeedExtractTaskService):
    """Wrap SeedExtractTaskService with a stubbed sequential_reader so the
    test doesn't need a live LLM. The runner's retry path calls into
    ``service.sequential_reader._retry_reread_segments`` indirectly, so we
    patch ``_retry_reread_segments`` at the runner level further down.
    """

    def __init__(self) -> None:
        # Skip parent __init__ — it tries to build real LLM clients.
        self.task_manager = TaskManager()


@pytest.fixture
def project_setup(tmp_path, monkeypatch):
    """Create a project dir + DB task, with smart_segments.json present and
    reading_notes.json absent — the exact scenario that used to break."""
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_dir))
    # PROJECTS_DIR 在类定义时基于 Config.UPLOAD_FOLDER 计算了一次，需单独覆盖
    monkeypatch.setattr(
        ProjectManager, "PROJECTS_DIR",
        str(upload_dir / "projects"),
    )
    TaskManager._instance = None

    project_id = "proj_test_retry"
    project_dir = upload_dir / "projects" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    # Minimal project.json so ProjectManager.get_project works.
    from datetime import datetime
    now = datetime.now().isoformat()
    project = Project(
        project_id=project_id,
        name="测试项目",
        status=ProjectStatus.SEED_PROCESSING,
        created_at=now,
        updated_at=now,
        analysis_goal="",
    )
    ProjectManager.save_project(project)

    # Write smart_segments.json with 3 segments directly to disk — 不走
    # ProjectManager.save_project_json，避免 DB 镜像把删掉的文件"复活"。
    segments = [
        {"segment_id": f"seg_{i:03d}", "text": f"段落 {i} 正文"} for i in (1, 2, 3)
    ]
    smart_path = project_dir / "smart_segments.json"
    smart_path.write_text(
        json.dumps({"segments": segments}, ensure_ascii=False),
        encoding="utf-8",
    )

    yield project_id, project_dir

    TaskManager._instance = None


def test_retry_missing_reading_notes_falls_back_to_empty_manager(
    project_setup, monkeypatch
):
    """reading_notes.json 不存在时，retry 应该用空 manager 把所有段落当未处理
    来重跑，而不是抛 "项目尚未生成 reading_notes.json"。"""
    project_id, project_dir = project_setup
    assert not (project_dir / "reading_notes.json").exists()

    import asyncio

    service = _StubService()
    task_id = asyncio.run(
        service.task_manager.create_task(
            task_type="seed_retry_segments",
            metadata={"project_id": project_id},
        )
    )

    runner = SeedExtractRunner(service, task_id, use_llm=True, project_id=project_id)
    # 绕开真实 LLM 模块校验（否则没有配置会报 LLM 未绑定）
    monkeypatch.setattr(runner, "_validate_llm_modules", lambda: None)

    # 捕获 _retry_reread_segments 拿到的 target 列表
    captured: Dict[str, Any] = {}

    def fake_retry(targets, manager):
        captured["targets"] = list(targets)
        captured["manager_fresh"] = not manager.all_segment_summaries
        # 留一个没恢复，让 retry 走 "部分恢复" 分支直接 return，
        # 避免走到下游 finalize 路径（那段会调真实 LLM 客户端）。
        for seg_id, _seg in targets[:-1]:
            manager.all_segment_summaries.append({"segment_id": seg_id, "summary": "ok"})
        return len(targets) - 1, 1

    monkeypatch.setattr(runner, "_retry_reread_segments", fake_retry)

    runner.retry_failed_segments(project_id)

    # 应该把 3 个段落都当成未处理来重跑
    assert captured.get("manager_fresh") is True, (
        "reading_notes.json 缺失时应该用空 manager 而不是 load 老文件"
    )
    assert [sid for sid, _ in captured["targets"]] == ["seg_001", "seg_002", "seg_003"]

    # retry 成功后应当把 reading_notes.json 落盘，下次 断点续传 就能接上
    assert (project_dir / "reading_notes.json").exists()


def test_retry_missing_smart_segments_raises_value_error(project_setup, monkeypatch):
    """连 smart_segments.json 都没有的话，retry 确实没法恢复。应该抛
    ValueError，由上层 ``_run_retry_worker`` 的 except 转为用户可见的
    "请点击重新开始" 提示——而不是像以前那样只说 reading_notes.json
    不存在，让用户误以为继续点 断点续传 就能解决。"""
    project_id, project_dir = project_setup
    (project_dir / "smart_segments.json").unlink()

    import asyncio

    service = _StubService()
    task_id = asyncio.run(
        service.task_manager.create_task(
            task_type="seed_retry_segments",
            metadata={"project_id": project_id},
        )
    )
    runner = SeedExtractRunner(service, task_id, use_llm=True, project_id=project_id)
    monkeypatch.setattr(runner, "_validate_llm_modules", lambda: None)

    with pytest.raises(ValueError, match="smart_segments.json"):
        runner.retry_failed_segments(project_id)
