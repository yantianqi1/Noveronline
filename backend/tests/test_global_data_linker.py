"""Tests for ``GlobalDataLinker`` and the ``/project/{id}/relink-data`` API."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app import create_app
from app.config import Config
from app.database import get_engine
from app.models.project import ProjectManager, ProjectStatus
from app.repositories.archive_repo import ArchiveRepository
from app.services.global_data_linker import GlobalDataLinker
from app.services.local_story_graph_models import GraphSnapshot


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _configure_storage(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    ProjectManager.PROJECTS_DIR = str(upload_root / "projects")
    return upload_root


def _seed_project(name: str = "赘婿测试", status: ProjectStatus = ProjectStatus.ONTOLOGY_GENERATED):
    project = ProjectManager.create_project(name)
    project.analysis_goal = "观察主角命运与宗门博弈"
    project.status = status
    project.ontology = {
        "entity_types": ["Character", "Organization"],
        "edge_types": ["tension"],
    }
    ProjectManager.save_project(project)
    ProjectManager.save_extracted_text(project.project_id, "第一章：宁毅抵达江南……\n" * 40)
    ProjectManager.save_project_json(
        project.project_id,
        "seed_analysis.json",
        {
            "characters": [
                {
                    "name": "宁毅",
                    "importance_tier": "protagonist",
                    "identity_hint": "主角",
                    "profile_summary": "在江宁三方势力间寻找立足点",
                },
            ],
            "organizations": [
                {
                    "name": "苏家",
                    "importance_tier": "major",
                    "organization_type": "family",
                    "summary": "掌控江宁商贸脉络",
                },
            ],
            "relations": [
                {"source": "宁毅", "target": "苏家", "relation_type": "tension"},
            ],
        },
    )
    ProjectManager.save_project_json(
        project.project_id, "agent_profiles.json", {"profiles": {}}
    )
    return project


def _mock_graph_service():
    """Return a ``GraphBuilderService`` double whose ``build_graph`` yields a snapshot."""
    service = MagicMock()

    def _build(**kwargs):
        return GraphSnapshot(
            graph_id=f"local://{kwargs['project_id']}",
            project_id=kwargs["project_id"],
            graph_name=kwargs.get("graph_name", "test"),
            built_at="2026-04-17T00:00:00",
            build_version="test",
            ontology=kwargs["ontology"],
            nodes=[],
            edges=[],
        )

    service.build_graph.side_effect = _build
    return service


def _mock_indexer(return_count: int = 0):
    indexer = MagicMock()
    indexer.reindex_project.return_value = return_count
    return indexer


# ---------------------------------------------------------------------------
# Linker unit tests
# ---------------------------------------------------------------------------


def test_link_project_populates_archive_library(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    create_app()  # trigger init_db
    project = _seed_project()

    linker = GlobalDataLinker(
        graph_service=_mock_graph_service(),
        indexer=_mock_indexer(return_count=3),
    )
    summary = linker.link_project(project.project_id, use_llm=False)

    # Stage A wrote archive_library rows
    repo = ArchiveRepository(get_engine())
    assert repo.count_archives(project_id=project.project_id) > 0

    # Stage B called build_graph exactly once with our fixture text+ontology
    assert linker._graph_service.build_graph.call_count == 1

    # Stage C delegated to indexer
    assert linker._indexer.reindex_project.called

    # Project was promoted to GRAPH_COMPLETED
    refreshed = ProjectManager.get_project(project.project_id)
    assert refreshed.status == ProjectStatus.GRAPH_COMPLETED
    assert summary["final_status"] == ProjectStatus.GRAPH_COMPLETED.value
    assert summary["stages"]["archive_sync"]["archive_count"] > 0
    assert summary["stages"]["index_rebuild"]["indexed"] == 3


def test_link_project_fails_without_seed_analysis(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    create_app()
    project = ProjectManager.create_project("no-seed")
    project.status = ProjectStatus.ONTOLOGY_GENERATED
    ProjectManager.save_project(project)

    linker = GlobalDataLinker(
        graph_service=_mock_graph_service(), indexer=_mock_indexer(),
    )
    with pytest.raises(ValueError, match="seed_analysis"):
        linker.link_project(project.project_id, use_llm=False)

    # Graph build was never reached
    assert not linker._graph_service.build_graph.called


def test_find_missing_projects_skips_already_linked(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    create_app()
    linked = _seed_project("已打通")
    missing = _seed_project("待打通")

    # Pre-populate archive_library for `linked`
    GlobalDataLinker(
        graph_service=_mock_graph_service(), indexer=_mock_indexer(),
    ).link_project(linked.project_id, use_llm=False)

    found = GlobalDataLinker().find_missing_projects()
    assert missing.project_id in found
    assert linked.project_id not in found


def test_find_missing_projects_skips_projects_with_active_task(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    create_app()
    project = _seed_project("正在跑")
    project.seed_task_id = "dummy-task-id"
    ProjectManager.save_project(project)

    found = GlobalDataLinker().find_missing_projects()
    assert project.project_id not in found


def test_backfill_missing_continues_after_failure(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    create_app()
    ok_project = _seed_project("ok")
    # Second project without seed_analysis should be filtered out by find_missing.
    broken = ProjectManager.create_project("broken")
    broken.status = ProjectStatus.ONTOLOGY_GENERATED
    ProjectManager.save_project(broken)

    linker = GlobalDataLinker(
        graph_service=_mock_graph_service(), indexer=_mock_indexer(),
    )
    # Force an error for the ok_project by making build_graph raise
    calls = {"n": 0}

    def _raise_once(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated graph failure")
        return _mock_graph_service().build_graph(**kwargs)

    linker._graph_service.build_graph.side_effect = _raise_once

    # Add a second linkable project so we prove the loop continues
    second = _seed_project("second")
    results = linker.backfill_missing(use_llm=False)

    assert {r["project_id"] for r in results} >= {ok_project.project_id, second.project_id}
    # list_projects sorts by created_at desc, so order is non-deterministic
    # across runs; assert that *one* project succeeded and *one* failed.
    oks = [r for r in results if r["ok"] is True]
    fails = [r for r in results if r["ok"] is False]
    assert len(fails) == 1 and "simulated graph failure" in fails[0]["error"]
    assert len(oks) >= 1


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------


def test_relink_data_api_returns_task_id(tmp_path, monkeypatch):
    _configure_storage(tmp_path, monkeypatch)
    # Patch GraphBuilderService + GlobalSearchIndexer in-place so the async
    # worker doesn't try to run the real pipelines.
    import app.services.global_data_linker as linker_mod

    monkeypatch.setattr(
        linker_mod, "GraphBuilderService", lambda: _mock_graph_service(),
    )
    monkeypatch.setattr(
        linker_mod, "GlobalSearchIndexer", lambda: _mock_indexer(),
    )

    app = create_app()
    client = app.test_client()
    project = _seed_project("API 项目")

    response = client.post(f"/api/project/{project.project_id}/relink-data")

    assert response.status_code == 202, response.get_json()
    payload = response.get_json()["data"]
    assert payload["project_id"] == project.project_id
    assert payload["task_id"]
    # Project's seed_task_id should now reference the task (sanity check that
    # the background worker was registered; its completion is covered by the
    # unit tests above).
    refreshed = ProjectManager.get_project(project.project_id)
    assert refreshed.seed_task_id == payload["task_id"]
