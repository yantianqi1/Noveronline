"""DB-only contracts for project metadata.

The unified database is the runtime source of truth. New projects may still
need filesystem directories for uploaded files, but ``project.json`` must not
be required for ``ProjectManager.get_project`` / ``list_projects`` / updates.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.project import ProjectManager
from app.models.project_types import ProjectStatus


def _projects_dir(tmp_path, monkeypatch) -> Path:
    projects_dir = tmp_path / "uploads" / "projects"
    projects_dir.mkdir(parents=True)
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    return projects_dir


def test_project_manager_gets_project_from_db_without_project_json(tmp_path, monkeypatch):
    projects_dir = _projects_dir(tmp_path, monkeypatch)
    project = ProjectManager.create_project("DB 元数据")
    project_json = projects_dir / project.project_id / "project.json"
    if project_json.exists():
        project_json.unlink()

    loaded = ProjectManager.get_project(project.project_id)

    assert loaded is not None
    assert loaded.project_id == project.project_id
    assert loaded.name == "DB 元数据"
    assert loaded.status == ProjectStatus.CREATED


def test_project_manager_lists_db_projects_without_project_json(tmp_path, monkeypatch):
    projects_dir = _projects_dir(tmp_path, monkeypatch)
    first = ProjectManager.create_project("Alpha")
    second = ProjectManager.create_project("Beta")
    for project in (first, second):
        project_json = projects_dir / project.project_id / "project.json"
        if project_json.exists():
            project_json.unlink()

    projects = ProjectManager.list_projects(limit=10)

    names = {project.name for project in projects}
    assert {"Alpha", "Beta"}.issubset(names)


def test_project_manager_save_project_updates_db_before_filesystem(tmp_path, monkeypatch):
    projects_dir = _projects_dir(tmp_path, monkeypatch)
    project = ProjectManager.create_project("Before")
    project.status = ProjectStatus.GRAPH_COMPLETED
    project.graph_id = "graph_db_only"
    ProjectManager.save_project(project)

    project_json = projects_dir / project.project_id / "project.json"
    if project_json.exists():
        project_json.write_text(
            json.dumps(
                {
                    **project.to_dict(),
                    "name": "Stale Filesystem",
                    "status": ProjectStatus.FAILED.value,
                    "graph_id": "graph_stale",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    loaded = ProjectManager.get_project(project.project_id)

    assert loaded is not None
    assert loaded.name == "Before"
    assert loaded.status == ProjectStatus.GRAPH_COMPLETED
    assert loaded.graph_id == "graph_db_only"


def test_extracted_text_reads_from_db_without_text_file(tmp_path, monkeypatch):
    projects_dir = _projects_dir(tmp_path, monkeypatch)
    project = ProjectManager.create_project("文本项目")
    ProjectManager.save_extracted_text(project.project_id, "第一章\n正文")
    text_path = projects_dir / project.project_id / "extracted_text.txt"
    if text_path.exists():
        text_path.unlink()

    assert ProjectManager.get_extracted_text(project.project_id) == "第一章\n正文"


def test_extracted_text_prefers_db_over_stale_text_file(tmp_path, monkeypatch):
    projects_dir = _projects_dir(tmp_path, monkeypatch)
    project = ProjectManager.create_project("文本漂移")
    ProjectManager.save_extracted_text(project.project_id, "DB 正文")
    text_path = projects_dir / project.project_id / "extracted_text.txt"
    text_path.write_text("旧文件正文", encoding="utf-8")

    assert ProjectManager.get_extracted_text(project.project_id) == "DB 正文"
