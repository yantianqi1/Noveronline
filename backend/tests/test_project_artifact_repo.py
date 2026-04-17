"""Tests for ``ProjectArtifactRepository`` (Phase G / Task 8).

Validates the read/write contract that Phase G service layers rely on:
   - round-trip save/load returns the original payload
   - load returns None when no row exists
   - save upserts (second save overwrites the first, both timestamps move
     forward on the row)
   - list_keys / delete work as documented
   - ``ProjectManager.save_project_json`` mirrors every written JSON into
     ``project_artifacts`` keyed by the filename stem
   - ``ProjectManager.load_project_json`` prefers the DB when present and
     falls back to the filesystem for legacy data
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

from app.database import init_db
from app.models.project import ProjectManager
from app.repositories.project_artifact_repo import (
    ProjectArtifactRepository,
    artifact_key_from_filename,
)
from app.tables.novel import project_artifacts


@pytest.fixture
def engine(tmp_path):
    db_path = tmp_path / "artifacts.db"
    eng = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(eng)
    return eng


def test_artifact_key_from_filename_strips_json_suffix():
    assert artifact_key_from_filename("seed_analysis.json") == "seed_analysis"
    assert artifact_key_from_filename("seed_analysis") == "seed_analysis"
    assert artifact_key_from_filename(" reviewer_rules.json ") == "reviewer_rules"


def test_save_and_load_round_trip(engine):
    repo = ProjectArtifactRepository(engine)
    payload = {"characters": [{"name": "沈夜"}], "world_rules": ["重力正常"]}
    repo.save("proj_a", "seed_analysis", payload)
    assert repo.load("proj_a", "seed_analysis") == payload


def test_load_returns_none_for_missing_entry(engine):
    repo = ProjectArtifactRepository(engine)
    assert repo.load("proj_missing", "seed_analysis") is None
    repo.save("proj_a", "seed_analysis", {"x": 1})
    assert repo.load("proj_a", "other_key") is None
    assert repo.load("proj_b", "seed_analysis") is None


def test_save_upserts_existing_row(engine):
    repo = ProjectArtifactRepository(engine)
    repo.save("proj_a", "ontology", {"v": 1})
    repo.save("proj_a", "ontology", {"v": 2, "added": True})

    assert repo.load("proj_a", "ontology") == {"v": 2, "added": True}

    with engine.connect() as conn:
        rows = conn.execute(
            select(project_artifacts).where(project_artifacts.c.project_id == "proj_a")
        ).fetchall()
    assert len(rows) == 1
    created_at = rows[0]._mapping["created_at"]
    updated_at = rows[0]._mapping["updated_at"]
    assert updated_at >= created_at


def test_list_keys_returns_sorted_artifact_keys(engine):
    repo = ProjectArtifactRepository(engine)
    repo.save("proj_a", "ontology", {})
    repo.save("proj_a", "seed_analysis", {})
    repo.save("proj_a", "agent_profiles", {})
    repo.save("proj_b", "other", {})
    assert repo.list_keys("proj_a") == ["agent_profiles", "ontology", "seed_analysis"]
    assert repo.list_keys("proj_b") == ["other"]
    assert repo.list_keys("proj_missing") == []


def test_delete_removes_row(engine):
    repo = ProjectArtifactRepository(engine)
    repo.save("proj_a", "seed_analysis", {"x": 1})
    assert repo.delete("proj_a", "seed_analysis") == 1
    assert repo.load("proj_a", "seed_analysis") is None
    assert repo.delete("proj_a", "seed_analysis") == 0


def test_save_project_json_mirrors_to_project_artifacts(tmp_path, monkeypatch):
    """Every ``ProjectManager.save_project_json`` write hits ``project_artifacts``."""
    projects_dir = tmp_path / "uploads" / "projects"
    projects_dir.mkdir(parents=True)
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    project = ProjectManager.create_project("镜像测试")

    payload = {"characters": [{"name": "秦昭"}], "meta": {"schema": 1}}
    ProjectManager.save_project_json(project.project_id, "seed_analysis.json", payload)

    # Filesystem JSON is still written (authoritative for import/export).
    json_path = Path(projects_dir) / project.project_id / "seed_analysis.json"
    assert json_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8")) == payload

    # DB mirror is populated.
    from app.database import get_engine
    repo = ProjectArtifactRepository(get_engine())
    assert repo.load(project.project_id, "seed_analysis") == payload


def test_load_project_json_prefers_db_over_filesystem(tmp_path, monkeypatch):
    """When the DB has a row, ``load_project_json`` returns the DB value even if
    the filesystem JSON has drifted to a stale value."""
    projects_dir = tmp_path / "uploads" / "projects"
    projects_dir.mkdir(parents=True)
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    project = ProjectManager.create_project("双源测试")

    ProjectManager.save_project_json(project.project_id, "ontology.json", {"version": "db"})

    # Corrupt the filesystem copy. Read path must still prefer the DB.
    json_path = Path(projects_dir) / project.project_id / "ontology.json"
    json_path.write_text(json.dumps({"version": "stale"}), encoding="utf-8")

    loaded = ProjectManager.load_project_json(project.project_id, "ontology.json")
    assert loaded == {"version": "db"}


def test_load_project_json_falls_back_to_filesystem(tmp_path, monkeypatch):
    """Legacy projects with no DB row still work through the filesystem fallback."""
    projects_dir = tmp_path / "uploads" / "projects"
    projects_dir.mkdir(parents=True)
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    project = ProjectManager.create_project("只有文件")

    project_dir = Path(projects_dir) / project.project_id
    (project_dir / "reviewer_rules.json").write_text(
        json.dumps({"custom_prompt": "legacy"}), encoding="utf-8"
    )

    loaded = ProjectManager.load_project_json(project.project_id, "reviewer_rules.json")
    assert loaded == {"custom_prompt": "legacy"}


def test_load_project_json_returns_none_when_absent(tmp_path, monkeypatch):
    projects_dir = tmp_path / "uploads" / "projects"
    projects_dir.mkdir(parents=True)
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    project = ProjectManager.create_project("空项目")
    assert ProjectManager.load_project_json(project.project_id, "missing.json") is None
