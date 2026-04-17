"""Fileless worldline smoke test (Phase E / Task 6-3).

Asserts that every worldline session I/O path — ``save_session`` /
``load_session`` / ``list_sessions`` via ``WorldStateStore`` AND
``read_worldline`` via ``unified_asset_view`` — is satisfied by the
``worldline_sessions`` table alone, without ever writing the legacy
``uploads/projects/<pid>/worldlines/**`` filesystem layout.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import text

from app.config import Config
from app.database import get_engine
from app.models.project import ProjectManager
from app.models.worldline import WorldlineBranch, WorldlineSession
from app.services.assets.unified_asset_view import Readers
from app.services.world_state_store import WorldStateStore


def _make_project(tmp_path: Path):
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    project = ProjectManager.create_project("无文件世界线")
    project.graph_id = "graph_fileless"
    ProjectManager.save_project(project)
    return project


def _fresh_session(project_id: str, session_id: str = "sess_fileless") -> WorldlineSession:
    return WorldlineSession(
        session_id=session_id,
        project_id=project_id,
        graph_id="graph_fileless",
        simulation_goal="验证无文件持久化",
        focus_question="DB 是否足以承载 session 元数据？",
        branch_count=1,
        label="Fileless Session",
        branches=[
            WorldlineBranch(
                branch_id="main",
                title="主干",
                core_change="主角踏出家门",
            )
        ],
    )


def _worldlines_dir(project_id: str) -> Path:
    return Path(Config.UPLOAD_FOLDER) / "projects" / project_id / "worldlines"


def test_save_and_load_session_without_creating_worldlines_directory(tmp_path):
    project = _make_project(tmp_path)
    store = WorldStateStore()
    session = _fresh_session(project.project_id)

    # ``container_dir`` is accepted for signature compatibility but must
    # not influence where session data ends up.
    store.save_session(str(tmp_path / "ignored_container_dir"), session)

    assert not _worldlines_dir(project.project_id).exists(), (
        "worldlines/ directory should never be created during save_session"
    )

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT session_id, project_id, label, status FROM worldline_sessions WHERE session_id = :sid"),
            {"sid": session.session_id},
        ).fetchone()
    assert row is not None
    assert row[0] == "sess_fileless"
    assert row[1] == project.project_id
    assert row[2] == "Fileless Session"

    loaded = store.load_session(session.session_id)
    assert loaded is not None
    assert loaded.session_id == "sess_fileless"
    assert loaded.branches[0].branch_id == "main"


def test_list_sessions_reads_from_db_without_index_file(tmp_path):
    project = _make_project(tmp_path)
    store = WorldStateStore()
    store.save_session("", _fresh_session(project.project_id, "sess_a"))
    store.save_session("", _fresh_session(project.project_id, "sess_b"))

    items = store.list_sessions(project_id=project.project_id)
    ids = sorted(item["session_id"] for item in items)
    assert ids == ["sess_a", "sess_b"]
    assert not _worldlines_dir(project.project_id).exists(), (
        "list_sessions must not touch the filesystem layout"
    )


def test_reload_after_save_recovers_nested_branch_state(tmp_path):
    project = _make_project(tmp_path)
    store = WorldStateStore()
    session = _fresh_session(project.project_id, "sess_reload")
    session.branches[0].actor_states = {
        "沈夜": {"status": "active", "drive": "查真相", "role": "主角"}
    }
    session.world_variables_raw = None  # ensure serialization survives missing optional fields

    store.save_session("", session)
    reloaded = store.load_session("sess_reload")

    assert reloaded is not None
    assert reloaded.branches[0].actor_states["沈夜"]["drive"] == "查真相"


def test_unified_asset_view_read_worldline_uses_db(tmp_path):
    project = _make_project(tmp_path)
    store = WorldStateStore()
    store.save_session("", _fresh_session(project.project_id, "sess_view"))

    assets = Readers().read_worldline(project.project_id)
    assert len(assets) == 1
    asset = assets[0]
    assert asset.source == "worldline"
    assert asset.source_ref == "session:sess_view"
    assert asset.title == "Fileless Session"
    assert asset.project_id == project.project_id


def test_no_session_files_written_anywhere_under_uploads(tmp_path):
    project = _make_project(tmp_path)
    store = WorldStateStore()
    store.save_session("", _fresh_session(project.project_id, "sess_audit"))

    uploads_root = Path(Config.UPLOAD_FOLDER)
    offenders: list[str] = []
    if uploads_root.exists():
        for path in uploads_root.rglob("*"):
            if not path.is_file():
                continue
            name = path.name
            if name == "session.json" or (name.endswith(".json") and path.parent.name == "sessions"):
                offenders.append(str(path))
            if name == "index.json" and path.parent.name == "worldlines":
                offenders.append(str(path))
    assert offenders == [], f"Unexpected filesystem session artefacts: {offenders}"


def test_save_session_does_not_require_container_dir_to_exist(tmp_path):
    project = _make_project(tmp_path)
    store = WorldStateStore()
    # Path that definitely doesn't exist on disk — save_session must NOT
    # try to create it, since container_dir is deprecated.
    imaginary = str(tmp_path / "does" / "not" / "exist")
    store.save_session(imaginary, _fresh_session(project.project_id, "sess_imag"))

    assert not os.path.exists(imaginary)
    assert store.load_session("sess_imag") is not None
