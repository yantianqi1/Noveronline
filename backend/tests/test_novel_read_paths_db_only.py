"""DB-only contract tests for Phase G / Task 8.

Each test writes the artefact payload **only** to ``project_artifacts``
(via ``ProjectArtifactRepository.save``). No legacy JSON files are
created on disk. The test then exercises the real runtime read path
and asserts the service behaves identically to the pre-migration
filesystem contract.

This guards against regressions: any future service that re-adds a
``ProjectManager.load_project_json(...)`` call will fail these tests
the moment the filesystem copy is missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database import get_engine
from app.models.project import ProjectManager
from app.repositories.project_artifact_repo import ProjectArtifactRepository


def _setup_project(tmp_path, monkeypatch):
    projects_dir = tmp_path / "uploads" / "projects"
    projects_dir.mkdir(parents=True)
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(projects_dir))
    project = ProjectManager.create_project("DB-only 门禁")
    return project, projects_dir


def _save_artifact(project_id: str, key: str, payload: dict) -> None:
    ProjectArtifactRepository(get_engine()).save(project_id, key, payload)


def _assert_no_legacy_json(project_dir: Path, filenames: list[str]) -> None:
    """Fail loudly if any caller accidentally created a fallback JSON file."""
    for name in filenames:
        assert not (project_dir / name).exists(), f"{name} should not exist on disk"


def test_chapter_context_builder_runs_without_any_filesystem_json(tmp_path, monkeypatch):
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder

    project, projects_dir = _setup_project(tmp_path, monkeypatch)

    _save_artifact(project.project_id, "chapter_segments", {
        "chapter_count": 2,
        "chapters": [
            {"chapter_id": "chapter_0001", "order": 1, "title": "开局"},
            {"chapter_id": "chapter_0002", "order": 2, "title": "追查"},
        ],
    })
    _save_artifact(project.project_id, "chapter_continuity", {
        "global_summary": "围绕镜湖旧案展开的悬疑推理。",
        "chapters": [
            {"chapter_id": "chapter_0001", "order": 1, "head_context": "风雪夜"},
            {"chapter_id": "chapter_0002", "order": 2, "head_context": "地下档案"},
        ],
    })
    _save_artifact(project.project_id, "seed_analysis", {
        "characters": [{"name": "沈夜"}, {"name": "秦昭"}, {}],
    })

    options = ChapterContextPackBuilder().build_options(project.project_id)
    assert options["project_id"] == project.project_id
    assert [c["chapter_id"] for c in options["chapters"]] == ["chapter_0001", "chapter_0002"]
    assert options["pov_characters"] == ["沈夜", "秦昭"]
    assert options["continuity_summary"] == "围绕镜湖旧案展开的悬疑推理。"

    project_dir = Path(projects_dir) / project.project_id
    _assert_no_legacy_json(project_dir, [
        "chapter_segments.json", "chapter_continuity.json", "seed_analysis.json",
    ])


def test_chapter_meta_world_rules_and_prev_ending_read_from_db(tmp_path, monkeypatch):
    from app.services.chapter_meta_service import ChapterMetaService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    _save_artifact(project.project_id, "story_memory", {
        "world_rules": ["重力正常", "", "魔法存在但需要代价"],
    })
    _save_artifact(project.project_id, "chapter_segments", {
        "chapters": [
            {"chapter_id": "chapter_0001", "order": 1, "content": "沈夜接到神秘密信。线索指向镜湖。"},
            {"chapter_id": "chapter_0002", "order": 2, "content": "秦昭潜入地下档案。"},
        ],
    })

    service = ChapterMetaService()
    rules = service.get_world_rules(project.project_id)
    assert rules == ["重力正常", "魔法存在但需要代价"]

    prev_ending = service._get_prev_chapter_ending(project.project_id, 2)
    assert prev_ending.endswith("线索指向镜湖。")

    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "story_memory.json", "chapter_segments.json",
    ])


def test_unified_asset_view_read_seed_from_db_only(tmp_path, monkeypatch):
    from app.services.assets.unified_asset_view import Readers

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    _save_artifact(project.project_id, "narrative_archives", {
        "characters": {
            "c1": {"uuid": "e1", "name": "沈夜", "role": "protagonist"},
        },
        "world_rules": [
            {"name": "重力", "statement": "遵循牛顿定律"},
        ],
        "plot_threads": [
            {"name": "镜湖真相", "summary": "藏在谷底的旧案"},
        ],
    })
    _save_artifact(project.project_id, "reading_notes", {
        "notes": {
            "plot_state": {"arc_summaries": [{"arc_id": "arc_1", "summary": "开篇"}]},
            "key_events": [{"event_id": "ev_1", "title": "密信出现", "description": "夜晚"}],
        },
    })
    _save_artifact(project.project_id, "ontology", {
        "entity_types": [{"name": "Character", "description": "人物"}],
    })
    _save_artifact(project.project_id, "agent_profiles", {
        "沈夜": {"name": "沈夜", "summary": "主角"},
    })

    assets = Readers().read_seed(project.project_id)
    entity_types = {a.entity_type for a in assets}
    assert "seed_character" in entity_types
    assert "seed_world_rule" in entity_types
    assert "seed_plot_thread" in entity_types
    assert "seed_arc_summary" in entity_types
    assert "seed_key_event" in entity_types
    assert "seed_ontology_entity" in entity_types
    assert "seed_agent_profile" in entity_types

    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "narrative_archives.json", "reading_notes.json", "ontology.json", "agent_profiles.json",
    ])


def test_worldline_source_loader_falls_back_to_artifact(tmp_path, monkeypatch):
    from app.services.world_state_store import WorldStateStore
    from app.services.worldline_source_loader import WorldlineSourceLoader

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    _save_artifact(project.project_id, "seed_analysis", {
        "characters": [{"name": "沈夜", "profile_summary": "追查真相"}],
        "organizations": [{"name": "镜湖盟", "summary": "暗中活动"}],
        "relations": [{"source": "沈夜", "target": "镜湖盟", "relation_type": "oppose"}],
        "chapter_beats": [{"title": "密信"}],
    })

    # container_dir is unused by the artifact fallback path — pass a path
    # that doesn't exist so ``store.load_json_if_exists`` short-circuits.
    fake_container = str(tmp_path / "no_such_container")
    loader = WorldlineSourceLoader(store=WorldStateStore())
    bundle = loader.load(project=project, graph_id="", container_dir=fake_container)

    assert "沈夜" in bundle["actors"]
    assert "镜湖盟" in bundle["organizations"]
    assert bundle["source_summary"]["seed_analysis"] is True


def test_graph_builder_reads_required_and_optional_artifacts_from_db(tmp_path, monkeypatch):
    from app.services.graph_builder import GraphBuilderService

    project, _ = _setup_project(tmp_path, monkeypatch)
    _save_artifact(project.project_id, "seed_analysis", {"characters": [{"name": "沈夜"}]})
    _save_artifact(project.project_id, "reading_notes", {"core_facts": {"characters": {}}})

    service = GraphBuilderService()
    # _required_json raises cleanly when the artefact is missing.
    with pytest.raises(ValueError, match="缺少构建本地图谱所需工件"):
        service._required_json(project.project_id, "missing_artifact.json")

    # _required_json returns the DB row when present.
    seed = service._required_json(project.project_id, "seed_analysis.json")
    assert seed["characters"][0]["name"] == "沈夜"

    # _optional_json returns None for missing keys and the payload otherwise.
    assert service._optional_json(project.project_id, "never_saved.json") is None
    assert service._optional_json(project.project_id, "reading_notes.json") == {
        "core_facts": {"characters": {}},
    }


def test_load_project_artifact_accepts_both_filename_and_key(tmp_path, monkeypatch):
    """Regression guard: callers that still pass ``.json`` suffixes keep working."""
    from app.repositories.project_artifact_repo import load_project_artifact

    project, _ = _setup_project(tmp_path, monkeypatch)
    _save_artifact(project.project_id, "ontology", {"v": 1})

    assert load_project_artifact(project.project_id, "ontology.json") == {"v": 1}
    assert load_project_artifact(project.project_id, "ontology") == {"v": 1}
