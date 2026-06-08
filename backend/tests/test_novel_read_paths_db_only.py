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

import json
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


def _forbid_project_artifact_reads(monkeypatch, on_read=None) -> None:
    def fail(self, project_id: str, artifact_key: str):
        if on_read is not None:
            return on_read(project_id, artifact_key)
        raise AssertionError(f"unexpected artifact read: {artifact_key}")

    monkeypatch.setattr(ProjectArtifactRepository, "load", fail)


def test_chapter_context_options_do_not_read_chapter_artifact_fallbacks(
    tmp_path, monkeypatch
):
    from app.repositories.project_artifact_repo import ProjectArtifactRepository
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

    original_load = ProjectArtifactRepository.load

    def fail_on_chapter_artifacts(self, project_id: str, artifact_key: str):
        if artifact_key in {"chapter_segments", "chapter_continuity"}:
            raise AssertionError("chapter context options must not read chapter artifacts")
        return original_load(self, project_id, artifact_key)

    monkeypatch.setattr(ProjectArtifactRepository, "load", fail_on_chapter_artifacts)
    options = ChapterContextPackBuilder().build_options(project.project_id)
    assert options["project_id"] == project.project_id
    assert options["chapters"] == []
    assert options["pov_characters"] == ["沈夜", "秦昭"]
    assert options["continuity_summary"] == ""

    project_dir = Path(projects_dir) / project.project_id
    _assert_no_legacy_json(project_dir, [
        "chapter_segments.json", "chapter_continuity.json", "seed_analysis.json",
    ])


def test_chapter_context_options_read_chapter_tables_without_artifacts(
    tmp_path, monkeypatch
):
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from app.services.chapter_meta_service import ChapterMetaService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "开局",
                "summary_text": "沈夜接到密信。",
                "start_anchor": "风雪夜，密信落入沈夜手中。",
                "open_threads": [],
            },
            {
                "chapter_id": "chapter_0002",
                "chapter_order": 2,
                "title": "追查",
                "summary_text": "沈夜追查镜湖旧案。",
                "start_anchor": "沈夜进入地下档案。",
                "open_threads": [],
            },
        ],
    )
    _save_artifact(project.project_id, "seed_analysis", {
        "characters": [{"name": "沈夜"}, {"name": "秦昭"}, {}],
    })

    options = ChapterContextPackBuilder().build_options(project.project_id)

    assert [c["chapter_id"] for c in options["chapters"]] == [
        "chapter_0001",
        "chapter_0002",
    ]
    assert options["chapters"][0]["head_context"] == "风雪夜，密信落入沈夜手中。"
    assert options["pov_characters"] == ["沈夜", "秦昭"]
    assert "沈夜接到密信" in options["continuity_summary"]
    assert "沈夜追查镜湖旧案" in options["continuity_summary"]
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "chapter_segments.json", "chapter_continuity.json",
    ])


def test_chapter_context_options_do_not_probe_artifacts_when_chapter_tables_exist(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.services import chapter_context_pack_builder as builder_module
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from app.services.chapter_meta_service import ChapterMetaService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "开局",
                "summary_text": "沈夜收到密信。",
                "start_anchor": "风雪夜，密信落入沈夜手中。",
                "open_threads": [],
            },
            {
                "chapter_id": "chapter_0002",
                "chapter_order": 2,
                "title": "追查",
                "summary_text": "沈夜进入地下档案。",
                "start_anchor": "沈夜进入地下档案。",
                "open_threads": [],
            },
        ],
    )
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        },
    )

    def fail_artifact_probe(project_id: str, artifact_key: str):
        raise AssertionError(f"unexpected artifact read: {artifact_key}")

    _forbid_project_artifact_reads(monkeypatch, fail_artifact_probe)

    options = ChapterContextPackBuilder().build_options(project.project_id)

    assert [item["chapter_id"] for item in options["chapters"]] == [
        "chapter_0001",
        "chapter_0002",
    ]
    assert options["pov_characters"] == ["沈夜"]
    assert "沈夜收到密信" in options["continuity_summary"]
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "chapter_segments.json", "chapter_continuity.json", "seed_analysis.json",
    ])


def test_chapter_context_options_read_pov_characters_from_entities_without_seed_artifact(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from app.services.chapter_meta_service import ChapterMetaService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "开局",
                "summary_text": "沈夜收到密信。",
                "start_anchor": "风雪夜，密信落入沈夜手中。",
                "open_threads": [],
            }
        ],
    )
    entities = EntityRepository(get_engine())
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_qinzhao",
            "name": "秦昭",
            "entity_type": "character",
            "importance_tier": "major",
            "summary": "掌握地下档案密钥的盟友。",
            "created_at": now,
            "updated_at": now,
        },
    )
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "org_mirror_lake",
            "name": "镜湖盟",
            "entity_type": "organization",
            "importance_tier": "major",
            "summary": "保存镜湖旧案档案的组织。",
            "created_at": now,
            "updated_at": now,
        },
    )

    options = ChapterContextPackBuilder().build_options(project.project_id)

    assert options["pov_characters"] == ["沈夜", "秦昭"]
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "chapter_segments.json",
        "chapter_continuity.json",
        "seed_analysis.json",
    ])


def test_chapter_context_options_read_pov_characters_from_canonical_entity_type(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from app.services.chapter_meta_service import ChapterMetaService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "开局",
                "summary_text": "沈夜收到密信。",
                "start_anchor": "风雪夜，密信落入沈夜手中。",
                "open_threads": [],
            }
        ],
    )
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "Character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )

    options = ChapterContextPackBuilder().build_options(project.project_id)

    assert options["pov_characters"] == ["沈夜"]
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "seed_analysis.json",
    ])


def test_chapter_context_build_reads_project_pack_from_chapter_tables_without_artifacts(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from sqlalchemy import insert

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.event_repo import EventRepository
    from app.repositories.relationship_repo import RelationshipRepository
    from app.repositories.thread_repo import ThreadRepository
    from app.repositories.world_rule_repo import WorldRuleRepository
    from app.services import chapter_context_pack_builder as builder_module
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from app.services.chapter_meta_service import ChapterMetaService
    from app.tables.novel import consistency_notes, entity_evidence, world_events

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "core_drive": "查清镜湖真相",
            "current_objective": "打开地下档案密钥",
            "hidden_tension": "担心秦昭隐瞒关键证据",
            "created_at": now,
            "updated_at": now,
        },
    )
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_qinzhao",
            "name": "秦昭",
            "entity_type": "character",
            "importance_tier": "major",
            "summary": "掌握地下档案密钥的盟友。",
            "created_at": now,
            "updated_at": now,
        },
    )
    RelationshipRepository(get_engine()).upsert_relationship(
        project.project_id,
        {
            "relation_id": "rel_shenye_qinzhao",
            "source_id": "char_shenye",
            "target_id": "char_qinzhao",
            "relation_type": "ally",
            "description": "秦昭知道地下档案密钥，但尚未完全信任沈夜。",
            "updated_at": now,
        },
    )
    ThreadRepository(get_engine()).upsert_thread(
        project.project_id,
        {
            "thread_id": "thread_archive_key",
            "thread_key": "地下档案密钥",
            "status": "open",
            "detail": "地下档案密钥仍在秦昭手里。",
            "source_chapter": "1",
            "created_at": now,
            "updated_at": now,
        },
    )
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "密信初现",
                "summary_text": "沈夜收到密信，镜湖旧案重新浮出水面。",
                "start_anchor": "风雪夜，密信落入沈夜手中。",
                "end_anchor": "密信线索指向地下档案。",
                "key_events": [{"summary": "沈夜决定追查镜湖旧案。"}],
                "open_threads": [{"thread_key": "镜湖真相", "summary": "镜湖真相仍未查清。"}],
            },
            {
                "chapter_id": "chapter_0002",
                "chapter_order": 2,
                "title": "地下档案",
                "summary_text": "沈夜进入地下档案，发现镜湖引擎的旧记录。",
                "start_anchor": "沈夜进入地下档案。",
                "end_anchor": "镜湖引擎残响提到顾行舟。",
                "key_events": [{"summary": "地下档案暴露镜湖引擎残响。"}],
                "open_threads": [{"thread_key": "顾行舟布局", "summary": "顾行舟的真正意图仍未明朗。"}],
            },
        ],
    )
    WorldRuleRepository(get_engine()).upsert_world_rule(
        project.project_id,
        {
            "evidence_id": "rule_mirror_lake",
            "fact_text": "镜湖引擎可以读取修士识海残痕。",
            "segment_id": "seg_rule_001",
            "chapter_order": 1,
            "evidence_snippet": "镜湖引擎留下了残响。",
            "created_at": datetime.now().isoformat(),
        },
    )
    EventRepository(get_engine()).log_character_event(
        project.project_id,
        {
            "event_id": "ev_engine_trace_current",
            "entity_id": "char_shenye",
            "segment_id": "seg_event_002",
            "chapter_order": 2,
            "event_type": "discovery",
            "summary": "沈夜触发镜湖引擎残响，听见顾行舟的名字。",
            "detail_json": "{}",
            "created_at": now,
        },
    )
    with get_engine().connect() as conn:
        conn.execute(
            insert(consistency_notes).values(
                note_id="note_engine_timeline",
                project_id=project.project_id,
                segment_id="seg_note_002",
                chapter_order=2,
                note_text="镜湖引擎残响时间线需要保持在第二章之后。",
                created_at=now,
            )
        )
        conn.execute(
            insert(entity_evidence).values(
                evidence_id="evidence_shenye_key",
                project_id=project.project_id,
                owner_id="char_shenye",
                owner_type="entity",
                chapter_id="chapter_0002",
                snippet="沈夜握紧地下档案密钥，意识到秦昭仍有隐瞒。",
                created_at=now,
            )
        )
        conn.execute(
            insert(world_events).values(
                event_id="world_event_mirror_echo",
                project_id=project.project_id,
                session_id="session_canon",
                branch_id="main",
                step=3,
                title="镜湖谷回声",
                summary="镜湖谷的世界线回声确认地下档案仍会改变审判走向。",
                event_type="canon_echo",
                driving_entities_json='["沈夜"]',
                state_changes_json="[]",
                status="canon",
                created_at=now,
            )
        )
        conn.commit()

    def fail_artifact_probe(project_id: str, artifact_key: str):
        raise AssertionError(f"unexpected artifact read: {artifact_key}")

    _forbid_project_artifact_reads(monkeypatch, fail_artifact_probe)

    pack = ChapterContextPackBuilder().build(
        {
            "scope_type": "project_chapter",
            "project_id": project.project_id,
            "chapter_order": 2,
            "pov_character": "沈夜",
            "writing_goal": "续写地下档案中的发现",
            "scene_focus": "镜湖引擎",
        }
    )

    assert pack["context_scope"]["chapter_id"] == "chapter_0002"
    assert any(item["category"] == "world_rule" for item in pack["must_know"])
    assert any("镜湖引擎" in item["summary"] for item in pack["must_know"])
    assert any(
        item["category"] == "event" and "触发镜湖引擎残响" in item["summary"]
        for item in pack["must_know"]
    )
    assert any(
        item["category"] == "event" and "世界线回声确认地下档案" in item["summary"]
        for item in pack["must_know"]
    )
    assert any("地下档案密钥" in item["summary"] for item in pack["should_know"])
    assert any("秦昭知道地下档案密钥" in item["summary"] for item in pack["should_know"])
    assert any(
        item["category"] == "pov_state"
        and "查清镜湖真相" in item["summary"]
        and "沈夜握紧地下档案密钥" in item["summary"]
        for item in pack["should_know"]
    )
    assert any("镜湖引擎残响时间线" in item["summary"] for item in pack["warnings"])
    assert pack["history_recall"]["recent_anchors"]
    assert "写作目标" in pack["writer_prompt_block"]
    assert "必须延续的事实" in pack["writer_prompt_block"]
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "story_memory.json", "chapter_continuity.json", "consistency_report.json",
    ])


def test_chapter_context_does_not_fill_world_rules_from_story_memory_artifact(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from sqlalchemy import insert

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.event_repo import EventRepository
    from app.repositories.relationship_repo import RelationshipRepository
    from app.services import chapter_context_pack_builder as builder_module
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from app.services.chapter_meta_service import ChapterMetaService
    from app.tables.novel import consistency_notes

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_qinzhao",
            "name": "秦昭",
            "entity_type": "character",
            "summary": "掌握地下档案密钥的盟友。",
            "created_at": now,
            "updated_at": now,
        },
    )
    RelationshipRepository(get_engine()).upsert_relationship(
        project.project_id,
        {
            "relation_id": "rel_shenye_qinzhao",
            "source_id": "char_shenye",
            "target_id": "char_qinzhao",
            "relation_type": "ally",
            "description": "秦昭知道地下档案密钥。",
            "updated_at": now,
        },
    )
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "密信初现",
                "summary_text": "沈夜收到密信。",
                "open_threads": [{"thread_key": "镜湖真相", "summary": "镜湖真相仍未查清。"}],
            }
        ],
    )
    EventRepository(get_engine()).log_character_event(
        project.project_id,
        {
            "event_id": "ev_archive_key",
            "entity_id": "char_shenye",
            "segment_id": "seg_event_001",
            "chapter_order": 1,
            "event_type": "discovery",
            "summary": "沈夜发现地下档案密钥。",
            "detail_json": "{}",
            "created_at": now,
        },
    )
    with get_engine().connect() as conn:
        conn.execute(
            insert(consistency_notes).values(
                note_id="note_no_artifact",
                project_id=project.project_id,
                segment_id="seg_note_001",
                chapter_order=1,
                note_text="地下档案密钥应在第一章后保持一致。",
                created_at=now,
            )
        )
        conn.commit()
    _save_artifact(
        project.project_id,
        "story_memory",
        {"world_rules": ["artifact 中的旧世界规则不应进入上下文。"]},
    )

    def fail_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"chapter context should not load artifact {artifact_name}")

    _forbid_project_artifact_reads(monkeypatch, fail_artifact_probe)

    story_memory, _continuity, _consistency = ChapterContextPackBuilder()._load_project_sources(
        project.project_id
    )

    assert story_memory["world_rules"] == []
    assert story_memory["open_threads"]
    assert story_memory["relationship_ledger"]
    assert story_memory["event_timeline"]
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "story_memory.json",
        "chapter_continuity.json",
        "consistency_report.json",
    ])


def test_chapter_context_does_not_fill_warnings_from_consistency_report_artifact(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.event_repo import EventRepository
    from app.repositories.relationship_repo import RelationshipRepository
    from app.services import chapter_context_pack_builder as builder_module
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from app.services.chapter_meta_service import ChapterMetaService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_qinzhao",
            "name": "秦昭",
            "entity_type": "character",
            "summary": "掌握地下档案密钥的盟友。",
            "created_at": now,
            "updated_at": now,
        },
    )
    RelationshipRepository(get_engine()).upsert_relationship(
        project.project_id,
        {
            "relation_id": "rel_shenye_qinzhao",
            "source_id": "char_shenye",
            "target_id": "char_qinzhao",
            "relation_type": "ally",
            "description": "秦昭知道地下档案密钥。",
            "updated_at": now,
        },
    )
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "密信初现",
                "summary_text": "沈夜收到密信。",
                "open_threads": [{"thread_key": "镜湖真相", "summary": "镜湖真相仍未查清。"}],
            }
        ],
    )
    EventRepository(get_engine()).log_character_event(
        project.project_id,
        {
            "event_id": "ev_archive_key",
            "entity_id": "char_shenye",
            "segment_id": "seg_event_001",
            "chapter_order": 1,
            "event_type": "discovery",
            "summary": "沈夜发现地下档案密钥。",
            "detail_json": "{}",
            "created_at": now,
        },
    )
    _save_artifact(
        project.project_id,
        "consistency_report",
        {
            "conflicts": [
                {
                    "kind": "post_death_activity",
                    "name": "沈临川",
                    "evidence": ["artifact 中的旧一致性风险不应进入上下文。"],
                }
            ],
            "ambiguities": [],
        },
    )

    def fail_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"chapter context should not load artifact {artifact_name}")

    _forbid_project_artifact_reads(monkeypatch, fail_artifact_probe)

    _story_memory, _continuity, consistency = ChapterContextPackBuilder()._load_project_sources(
        project.project_id
    )

    assert consistency["conflicts"] == []
    assert consistency["ambiguities"] == []
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "story_memory.json",
        "chapter_continuity.json",
        "consistency_report.json",
    ])


def test_chapter_context_does_not_fill_open_threads_from_story_memory_artifact(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.event_repo import EventRepository
    from app.repositories.relationship_repo import RelationshipRepository
    from app.services import chapter_context_pack_builder as builder_module
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from app.services.chapter_meta_service import ChapterMetaService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_qinzhao",
            "name": "秦昭",
            "entity_type": "character",
            "summary": "掌握地下档案密钥的盟友。",
            "created_at": now,
            "updated_at": now,
        },
    )
    RelationshipRepository(get_engine()).upsert_relationship(
        project.project_id,
        {
            "relation_id": "rel_shenye_qinzhao",
            "source_id": "char_shenye",
            "target_id": "char_qinzhao",
            "relation_type": "ally",
            "description": "秦昭知道地下档案密钥。",
            "updated_at": now,
        },
    )
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "密信初现",
                "summary_text": "沈夜收到密信。",
                "open_threads": [],
            }
        ],
    )
    EventRepository(get_engine()).log_character_event(
        project.project_id,
        {
            "event_id": "ev_archive_key",
            "entity_id": "char_shenye",
            "segment_id": "seg_event_001",
            "chapter_order": 1,
            "event_type": "discovery",
            "summary": "沈夜发现地下档案密钥。",
            "detail_json": "{}",
            "created_at": now,
        },
    )
    _save_artifact(
        project.project_id,
        "story_memory",
        {
            "open_threads": [
                {
                    "thread_key": "镜湖真相",
                    "summary": "artifact 中的旧开放线索不应进入上下文。",
                }
            ]
        },
    )

    def fail_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"chapter context should not load artifact {artifact_name}")

    _forbid_project_artifact_reads(monkeypatch, fail_artifact_probe)

    story_memory, _continuity, _consistency = ChapterContextPackBuilder()._load_project_sources(
        project.project_id
    )

    assert story_memory["open_threads"] == []
    assert story_memory["relationship_ledger"]
    assert story_memory["event_timeline"]
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "story_memory.json",
        "chapter_continuity.json",
    ])


def test_chapter_context_does_not_fill_relationships_from_story_memory_artifact(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.event_repo import EventRepository
    from app.repositories.thread_repo import ThreadRepository
    from app.services import chapter_context_pack_builder as builder_module
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from app.services.chapter_meta_service import ChapterMetaService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "密信初现",
                "summary_text": "沈夜收到密信。",
                "open_threads": [],
            }
        ],
    )
    ThreadRepository(get_engine()).create_thread(
        project.project_id,
        thread_key="镜湖真相",
        detail="镜湖真相仍未查清。",
        chapter_order=1,
    )
    EventRepository(get_engine()).log_character_event(
        project.project_id,
        {
            "event_id": "ev_archive_key",
            "entity_id": "char_shenye",
            "segment_id": "seg_event_001",
            "chapter_order": 1,
            "event_type": "discovery",
            "summary": "沈夜发现地下档案密钥。",
            "detail_json": "{}",
            "created_at": now,
        },
    )
    _save_artifact(
        project.project_id,
        "story_memory",
        {
            "relationship_ledger": [
                {
                    "source": "沈夜",
                    "target": "秦昭",
                    "description": "artifact 中的旧关系不应进入上下文。",
                }
            ]
        },
    )

    def fail_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"chapter context should not load artifact {artifact_name}")

    _forbid_project_artifact_reads(monkeypatch, fail_artifact_probe)

    story_memory, _continuity, _consistency = ChapterContextPackBuilder()._load_project_sources(
        project.project_id
    )

    assert story_memory["relationship_ledger"] == []
    assert story_memory["open_threads"]
    assert story_memory["event_timeline"]
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "story_memory.json",
        "chapter_continuity.json",
    ])


def test_chapter_context_does_not_fill_events_from_story_memory_artifact(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.relationship_repo import RelationshipRepository
    from app.repositories.thread_repo import ThreadRepository
    from app.services import chapter_context_pack_builder as builder_module
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from app.services.chapter_meta_service import ChapterMetaService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_qinzhao",
            "name": "秦昭",
            "entity_type": "character",
            "summary": "掌握地下档案密钥的盟友。",
            "created_at": now,
            "updated_at": now,
        },
    )
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "密信初现",
                "summary_text": "沈夜收到密信。",
                "open_threads": [],
            }
        ],
    )
    ThreadRepository(get_engine()).create_thread(
        project.project_id,
        thread_key="镜湖真相",
        detail="镜湖真相仍未查清。",
        chapter_order=1,
    )
    RelationshipRepository(get_engine()).upsert_relationship(
        project.project_id,
        {
            "relation_id": "rel_shenye_qinzhao",
            "source_id": "char_shenye",
            "target_id": "char_qinzhao",
            "relation_type": "ally",
            "description": "秦昭知道地下档案密钥。",
            "updated_at": now,
        },
    )
    _save_artifact(
        project.project_id,
        "story_memory",
        {
            "event_timeline": [
                {
                    "event_id": "event_legacy",
                    "summary": "artifact 中的旧事件不应进入上下文。",
                    "characters": ["沈夜"],
                }
            ]
        },
    )

    def fail_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"chapter context should not load artifact {artifact_name}")

    _forbid_project_artifact_reads(monkeypatch, fail_artifact_probe)

    story_memory, _continuity, _consistency = ChapterContextPackBuilder()._load_project_sources(
        project.project_id
    )

    assert story_memory["event_timeline"] == []
    assert story_memory["open_threads"]
    assert story_memory["relationship_ledger"]
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "story_memory.json",
        "chapter_continuity.json",
    ])


def test_chapter_context_build_uses_structured_scene_candidates_without_artifacts(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from sqlalchemy import insert

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.event_repo import EventRepository
    from app.repositories.relationship_repo import RelationshipRepository
    from app.repositories.scene_repo import SceneRepository
    from app.repositories.world_rule_repo import WorldRuleRepository
    from app.services import chapter_context_pack_builder as builder_module
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from app.services.chapter_meta_service import ChapterMetaService
    from app.tables.novel import consistency_notes

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    entities = EntityRepository(get_engine())
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_qinzhao",
            "name": "秦昭",
            "entity_type": "character",
            "importance_tier": "major",
            "summary": "掌握地下档案密钥的盟友。",
            "created_at": now,
            "updated_at": now,
        },
    )
    RelationshipRepository(get_engine()).upsert_relationship(
        project.project_id,
        {
            "relation_id": "rel_scene_seed",
            "source_id": "char_shenye",
            "target_id": "char_qinzhao",
            "relation_type": "ally",
            "description": "两人围绕地下档案暂时合作。",
            "updated_at": now,
        },
    )
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "密信初现",
                "summary_text": "沈夜收到密信。",
                "start_anchor": "风雪夜，密信落入沈夜手中。",
                "end_anchor": "密信指向地下档案。",
                "open_threads": [{"thread_key": "地下档案", "summary": "地下档案仍未打开。"}],
            },
            {
                "chapter_id": "chapter_0002",
                "chapter_order": 2,
                "title": "档案门前",
                "summary_text": "沈夜与秦昭抵达地下档案门前。",
                "start_anchor": "两人来到地下档案门前。",
                "end_anchor": "档案门后的残响即将苏醒。",
                "open_threads": [{"thread_key": "镜湖残响", "summary": "镜湖残响仍未解释。"}],
            },
        ],
    )
    WorldRuleRepository(get_engine()).upsert_world_rule(
        project.project_id,
        {
            "evidence_id": "rule_scene_candidate",
            "fact_text": "地下档案只能由双人同时开启。",
            "segment_id": "seg_rule_002",
            "chapter_order": 2,
            "evidence_snippet": "两枚钥匙需要同时入锁。",
            "created_at": now,
        },
    )
    EventRepository(get_engine()).log_character_event(
        project.project_id,
        {
            "event_id": "ev_scene_candidate",
            "entity_id": "char_shenye",
            "segment_id": "seg_event_002",
            "chapter_order": 2,
            "event_type": "arrival",
            "summary": "沈夜抵达地下档案门前。",
            "detail_json": "{}",
            "created_at": now,
        },
    )
    with get_engine().begin() as conn:
        conn.execute(
            insert(consistency_notes).values(
                note_id="note_scene_candidate",
                project_id=project.project_id,
                segment_id="seg_note_002",
                chapter_order=2,
                note_text="地下档案双钥匙规则需要延续。",
                created_at=now,
            )
        )
    SceneRepository(get_engine()).upsert_scene(
        project.project_id,
        {
            "scene_id": "scene_archive_door",
            "chapter_id": "chapter_0002",
            "scene_order": 1,
            "title": "双钥匙入锁",
            "content": "沈夜和秦昭在地下档案门前同时转动钥匙。",
            "location": "地下档案门前",
            "involved_entities_json": json.dumps(["沈夜", "秦昭"], ensure_ascii=False),
            "writing_brief_json": json.dumps(
                {
                    "scene_focus": "双钥匙同时入锁",
                    "tension": "秦昭仍未解释第二枚钥匙的来源。",
                    "why_now": "这是进入地下档案前必须兑现的场景。",
                },
                ensure_ascii=False,
            ),
        },
    )

    def fail_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"chapter context should not load artifact {artifact_name}")

    _forbid_project_artifact_reads(monkeypatch, fail_artifact_probe)

    pack = ChapterContextPackBuilder().build(
        {
            "scope_type": "project_chapter",
            "project_id": project.project_id,
            "chapter_order": 2,
            "pov_character": "沈夜",
            "writing_goal": "写地下档案门前的开场",
            "scene_focus": "双钥匙",
        }
    )

    assert pack["scene_candidates"][0]["title"] == "双钥匙入锁"
    assert pack["scene_candidates"][0]["setup"] == "双钥匙同时入锁"
    assert pack["scene_candidates"][0]["tension"] == "秦昭仍未解释第二枚钥匙的来源。"
    assert pack["scene_candidates"][0]["why_now"] == "这是进入地下档案前必须兑现的场景。"
    assert "scene_archive_door" in pack["scene_candidates"][0]["depends_on"]
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "story_memory.json",
        "chapter_continuity.json",
        "consistency_report.json",
    ])


def test_chapter_context_build_uses_relationship_events_without_story_memory_artifact(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from sqlalchemy import insert

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.event_repo import EventRepository
    from app.repositories.world_rule_repo import WorldRuleRepository
    from app.services import chapter_context_pack_builder as builder_module
    from app.services.chapter_context_pack_builder import ChapterContextPackBuilder
    from app.services.chapter_meta_service import ChapterMetaService
    from app.tables.novel import consistency_notes

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    entities = EntityRepository(get_engine())
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_qinzhao",
            "name": "秦昭",
            "entity_type": "character",
            "importance_tier": "major",
            "summary": "掌握地下档案密钥的盟友。",
            "created_at": now,
            "updated_at": now,
        },
    )
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "档案门前",
                "summary_text": "沈夜与秦昭抵达地下档案门前。",
                "start_anchor": "两人来到地下档案门前。",
                "end_anchor": "秦昭取出第二枚钥匙。",
                "open_threads": [{"thread_key": "第二枚钥匙", "summary": "第二枚钥匙来源仍未解释。"}],
            }
        ],
    )
    EventRepository(get_engine()).log_character_event(
        project.project_id,
        {
            "event_id": "ev_archive_door",
            "entity_id": "char_shenye",
            "segment_id": "seg_event_001",
            "chapter_order": 1,
            "event_type": "arrival",
            "summary": "沈夜抵达地下档案门前。",
            "detail_json": "{}",
            "created_at": now,
        },
    )
    EventRepository(get_engine()).log_relationship_event(
        project.project_id,
        {
            "event_id": "rel_ev_second_key",
            "source_entity_id": "char_shenye",
            "target_entity_id": "char_qinzhao",
            "segment_id": "seg_rel_001",
            "chapter_order": 1,
            "relation_type": "ally",
            "previous_state": "互相试探",
            "new_state": "暂时结盟",
            "trigger_event": "秦昭交出第二枚钥匙。",
            "emotional_shift": "沈夜对秦昭的信任上升。",
            "power_shift": "",
            "evidence": "两人同时转动钥匙，档案门开启。",
            "created_at": now,
        },
    )
    WorldRuleRepository(get_engine()).upsert_world_rule(
        project.project_id,
        {
            "evidence_id": "rule_relationship_event",
            "fact_text": "地下档案只能由双人同时开启。",
            "segment_id": "seg_rule_001",
            "chapter_order": 1,
            "evidence_snippet": "两枚钥匙需要同时入锁。",
            "created_at": now,
        },
    )
    with get_engine().begin() as conn:
        conn.execute(
            insert(consistency_notes).values(
                note_id="note_relationship_event",
                project_id=project.project_id,
                segment_id="seg_note_001",
                chapter_order=1,
                note_text="秦昭交出第二枚钥匙后，两人的信任状态需要延续。",
                created_at=now,
            )
        )

    def fail_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"chapter context should not load artifact {artifact_name}")

    _forbid_project_artifact_reads(monkeypatch, fail_artifact_probe)

    pack = ChapterContextPackBuilder().build(
        {
            "scope_type": "project_chapter",
            "project_id": project.project_id,
            "chapter_order": 1,
            "pov_character": "沈夜",
            "writing_goal": "写两人打开地下档案门",
            "scene_focus": "第二枚钥匙",
        }
    )

    assert any(
        item["category"] == "relationship"
        and item["source_kind"] == "relationship_events"
        and "秦昭交出第二枚钥匙" in item["summary"]
        and "信任上升" in item["summary"]
        for item in pack["should_know"]
    )
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "story_memory.json",
        "chapter_continuity.json",
        "consistency_report.json",
    ])


def test_chapter_meta_world_rules_and_prev_ending_read_from_structured_db(
    tmp_path, monkeypatch
):
    from app.services.chapter_meta_service import ChapterMetaService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    _save_artifact(project.project_id, "story_memory", {
        "world_rules": ["artifact 中的旧规则不应进入运行时"],
    })
    _save_artifact(project.project_id, "chapter_segments", {
        "chapters": [
            {"chapter_id": "chapter_0001", "order": 1, "content": "artifact 中的旧章节结尾。"},
            {"chapter_id": "chapter_0002", "order": 2, "content": "秦昭潜入地下档案。"},
        ],
    })

    service = ChapterMetaService()
    service.upsert_chapter_card(
        project.project_id,
        {
            "chapter_id": "chapter_0001",
            "chapter_order": 1,
            "title": "密信初现",
            "summary_text": "沈夜收到密信。",
            "start_anchor": "风雪夜，密信落入沈夜手中。",
            "end_anchor": "结构化章节锚点指向镜湖。",
        },
        world_rules=["重力正常", "", "魔法存在但需要代价"],
    )

    rules = service.get_world_rules(project.project_id)
    assert rules == ["重力正常", "魔法存在但需要代价"]

    prev_ending = service._get_prev_chapter_ending(project.project_id, 2)
    assert prev_ending == "结构化章节锚点指向镜湖。"

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
        "profiles": {"沈夜": {"basic_info": {"name": "沈夜", "identity": "主角"}}},
        "profile_count": 1,
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
    assert any(
        asset.entity_type == "seed_agent_profile"
        and asset.title == "沈夜"
        and asset.summary == "主角"
        for asset in assets
    )

    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "narrative_archives.json", "reading_notes.json", "ontology.json", "agent_profiles.json",
    ])


def test_unified_asset_view_read_seed_from_structured_tables_without_artifacts(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.narrative_repo import NarrativeRepository
    from app.repositories import project_artifact_repo
    from app.repositories.thread_repo import ThreadRepository
    from app.repositories.world_rule_repo import WorldRuleRepository
    from app.services.assets.unified_asset_view import Readers
    from app.services.chapter_meta_service import ChapterMetaService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    project.ontology = {
        "entity_types": [
            {"name": "Character", "description": "人物与角色"},
            {"name": "RuleSystem", "description": "世界规则"},
        ],
        "edge_types": [],
    }
    ProjectManager.save_project(project)
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "profile_json": json.dumps(
                {
                    "basic_info": {"name": "沈夜", "identity": "调查者"},
                    "speech": {"style": "简练"},
                    "motivation": {"current_objective": "追查镜湖旧案"},
                },
                ensure_ascii=False,
            ),
            "created_at": now,
            "updated_at": now,
        },
    )
    ThreadRepository(get_engine()).upsert_thread(
        project.project_id,
        {
            "thread_id": "thread_mirror_lake",
            "thread_key": "镜湖真相",
            "status": "open",
            "detail": "镜湖旧案仍未查清。",
            "source_chapter": "1",
            "created_at": now,
            "updated_at": now,
        },
    )
    WorldRuleRepository(get_engine()).upsert_world_rule(
        project.project_id,
        {
            "evidence_id": "rule_engine_trace",
            "fact_text": "镜湖引擎可以读取修士识海残痕。",
            "segment_id": "seg_001",
            "chapter_order": 1,
            "evidence_snippet": "镜湖引擎残响回应沈夜。",
            "created_at": now,
        },
    )
    narrative_repo = NarrativeRepository(get_engine())
    narrative_repo.upsert_narrative_arc(
        project.project_id,
        {
            "arc_id": "arc_mirror_lake",
            "summary": "镜湖旧案从密信线索推进到地下档案。",
            "covered_segments_json": json.dumps(["seg_001", "seg_002"], ensure_ascii=False),
            "created_at": now,
        },
    )
    narrative_repo.upsert_volume_summary(
        project.project_id,
        {
            "volume_id": "vol_001",
            "volume_order": 1,
            "summary": "第一卷围绕镜湖旧案与地下档案展开。",
            "covered_arcs_json": json.dumps(["arc_mirror_lake"], ensure_ascii=False),
            "created_at": now,
        },
    )
    narrative_repo.upsert_segment_summary(
        project.project_id,
        {
            "segment_id": "seg_001",
            "segment_order": 1,
            "summary": "沈夜收到密信，镜湖旧案重新浮出水面。",
            "created_at": now,
        },
    )
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "地下档案",
                "summary_text": "沈夜追查镜湖旧案。",
                "key_events": [
                    {
                        "event_id": "ev_engine_trace",
                        "title": "镜湖引擎残响",
                        "summary": "沈夜在地下档案中启动镜湖引擎残响。",
                    }
                ],
                "open_threads": [],
            }
        ],
    )

    def fail_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"read_seed should not load artifact {artifact_name}")

    monkeypatch.setattr(project_artifact_repo, "load_project_artifact", fail_artifact_probe)

    assets = Readers().read_seed(project.project_id)
    entity_types = {asset.entity_type for asset in assets}

    assert "seed_character" in entity_types
    assert "seed_world_rule" in entity_types
    assert "seed_plot_thread" in entity_types
    assert "seed_arc_summary" in entity_types
    assert "seed_volume_summary" in entity_types
    assert "seed_segment_summary" in entity_types
    assert "seed_key_event" in entity_types
    assert "seed_ontology_entity" in entity_types
    assert "seed_agent_profile" in entity_types
    assert any(asset.title == "沈夜" for asset in assets)
    assert any(
        asset.entity_type == "seed_agent_profile"
        and asset.title == "沈夜"
        and asset.payload.get("basic_info", {}).get("identity") == "调查者"
        for asset in assets
    )
    assert any(asset.title == "镜湖真相" for asset in assets)
    assert any(
        asset.entity_type == "seed_arc_summary"
        and asset.title == "arc_mirror_lake"
        and asset.summary == "镜湖旧案从密信线索推进到地下档案。"
        for asset in assets
    )
    assert any(
        asset.entity_type == "seed_volume_summary"
        and asset.title == "vol_001"
        and asset.summary == "第一卷围绕镜湖旧案与地下档案展开。"
        for asset in assets
    )
    assert any(
        asset.entity_type == "seed_segment_summary"
        and asset.title == "seg_001"
        and asset.summary == "沈夜收到密信，镜湖旧案重新浮出水面。"
        for asset in assets
    )
    assert any(
        asset.entity_type == "seed_ontology_entity"
        and asset.title == "Character"
        and asset.summary == "人物与角色"
        for asset in assets
    )
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "narrative_archives.json",
        "reading_notes.json",
        "ontology.json",
        "agent_profiles.json",
    ])


def test_unified_asset_view_does_not_gap_fill_archive_seed_types_from_artifact_when_db_has_seed_rows(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories import project_artifact_repo
    from app.repositories.entity_repo import EntityRepository
    from app.services.assets.unified_asset_view import Readers

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        },
    )

    def fail_on_narrative_archives(_project_id: str, artifact_name: str):
        if artifact_name == "narrative_archives":
            raise AssertionError("read_seed should not gap-fill narrative_archives after DB seed rows exist")
        return {}

    monkeypatch.setattr(project_artifact_repo, "load_project_artifact", fail_on_narrative_archives)

    assets = Readers().read_seed(project.project_id)

    assert any(
        asset.entity_type == "seed_character" and asset.title == "沈夜"
        for asset in assets
    )
    assert not any(asset.entity_type == "seed_world_rule" for asset in assets)
    assert not any(asset.entity_type == "seed_plot_thread" for asset in assets)
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "narrative_archives.json",
    ])


def test_unified_asset_view_does_not_gap_fill_reading_notes_from_artifact_when_db_has_narrative_seed_rows(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories import project_artifact_repo
    from app.repositories.narrative_repo import NarrativeRepository
    from app.services.assets.unified_asset_view import Readers

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    NarrativeRepository(get_engine()).upsert_narrative_arc(
        project.project_id,
        {
            "arc_id": "arc_mirror_lake",
            "summary": "镜湖旧案从密信线索推进到地下档案。",
            "covered_segments_json": json.dumps(["seg_001"], ensure_ascii=False),
            "created_at": datetime.now().isoformat(),
        },
    )

    def fail_on_reading_notes(_project_id: str, artifact_name: str):
        if artifact_name == "reading_notes":
            raise AssertionError("read_seed should not gap-fill reading_notes after DB narrative seed rows exist")
        return {}

    monkeypatch.setattr(project_artifact_repo, "load_project_artifact", fail_on_reading_notes)

    assets = Readers().read_seed(project.project_id)

    assert any(
        asset.entity_type == "seed_arc_summary"
        and asset.title == "arc_mirror_lake"
        for asset in assets
    )
    assert not any(asset.entity_type == "seed_key_event" for asset in assets)
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "reading_notes.json",
    ])


def test_unified_asset_view_reads_seed_key_events_from_runtime_event_tables(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories import project_artifact_repo
    from app.repositories.entity_repo import EntityRepository
    from app.repositories.event_repo import EventRepository
    from app.repositories.narrative_repo import NarrativeRepository
    from app.repositories.thread_repo import ThreadRepository
    from app.repositories.world_rule_repo import WorldRuleRepository
    from app.services.assets.unified_asset_view import Readers

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    project.ontology = {"entity_types": [{"name": "Character", "description": "人物"}]}
    ProjectManager.save_project(project)
    entities = EntityRepository(get_engine())
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "profile_json": json.dumps(
                {"basic_info": {"name": "沈夜", "identity": "调查者"}},
                ensure_ascii=False,
            ),
            "created_at": now,
            "updated_at": now,
        },
    )
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_qinzhao",
            "name": "秦昭",
            "entity_type": "character",
            "importance_tier": "major",
            "summary": "掌握地下档案密钥的盟友。",
            "created_at": now,
            "updated_at": now,
        },
    )
    ThreadRepository(get_engine()).upsert_thread(
        project.project_id,
        {
            "thread_id": "thread_archive_key",
            "thread_key": "地下档案密钥",
            "status": "open",
            "detail": "地下档案密钥来源尚未揭开。",
            "source_chapter": "1",
            "created_at": now,
            "updated_at": now,
        },
    )
    WorldRuleRepository(get_engine()).upsert_world_rule(
        project.project_id,
        {
            "evidence_id": "rule_dual_key",
            "fact_text": "地下档案只能由双人同时开启。",
            "segment_id": "seg_rule_001",
            "chapter_order": 1,
            "evidence_snippet": "两枚钥匙需要同时入锁。",
            "created_at": now,
        },
    )
    NarrativeRepository(get_engine()).upsert_narrative_arc(
        project.project_id,
        {
            "arc_id": "arc_archive_door",
            "summary": "地下档案门前的双钥匙线索开始推进。",
            "covered_segments_json": json.dumps(["seg_event_001"], ensure_ascii=False),
            "created_at": now,
        },
    )
    events = EventRepository(get_engine())
    events.log_character_event(
        project.project_id,
        {
            "event_id": "ev_archive_arrival",
            "entity_id": "char_shenye",
            "segment_id": "seg_event_001",
            "chapter_order": 1,
            "event_type": "arrival",
            "summary": "沈夜抵达地下档案门前。",
            "detail_json": "{}",
            "created_at": now,
        },
    )
    events.log_relationship_event(
        project.project_id,
        {
            "event_id": "rel_ev_second_key",
            "source_entity_id": "char_shenye",
            "target_entity_id": "char_qinzhao",
            "segment_id": "seg_rel_001",
            "chapter_order": 1,
            "relation_type": "ally",
            "previous_state": "互相试探",
            "new_state": "暂时结盟",
            "trigger_event": "秦昭交出第二枚钥匙。",
            "emotional_shift": "沈夜对秦昭的信任上升。",
            "power_shift": "",
            "evidence": "两人同时转动钥匙，档案门开启。",
            "created_at": now,
        },
    )

    def fail_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"read_seed should not load artifact {artifact_name}")

    monkeypatch.setattr(project_artifact_repo, "load_project_artifact", fail_artifact_probe)

    assets = Readers().read_seed(project.project_id)

    assert any(
        asset.entity_type == "seed_key_event"
        and asset.source_ref == "event:ev_archive_arrival"
        and asset.summary == "沈夜抵达地下档案门前。"
        for asset in assets
    )
    assert any(
        asset.entity_type == "seed_key_event"
        and asset.source_ref == "event:rel_ev_second_key"
        and "秦昭交出第二枚钥匙" in asset.summary
        and "信任上升" in asset.summary
        for asset in assets
    )
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "reading_notes.json",
        "narrative_archives.json",
        "ontology.json",
        "agent_profiles.json",
    ])


def test_unified_asset_view_ignores_empty_default_profile_json(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.services.assets.unified_asset_view import Readers

    project, _projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "entity_xuanxiao",
            "name": "玄霄宗",
            "entity_type": "unknown",
            "importance_tier": "minor",
            "summary": "被关系解析补齐的占位实体。",
            "created_at": now,
            "updated_at": now,
        },
    )

    assets = Readers().read_seed(project.project_id)

    assert any(
        asset.entity_type == "seed_character" and asset.title == "玄霄宗"
        for asset in assets
    )
    assert not any(
        asset.entity_type == "seed_agent_profile"
        and asset.source_ref == "profile:entity_xuanxiao"
        for asset in assets
    )


def test_unified_asset_view_does_not_gap_fill_agent_profiles_from_artifact_when_entities_exist(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories import project_artifact_repo
    from app.repositories.entity_repo import EntityRepository
    from app.services.assets.unified_asset_view import Readers

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        },
    )

    def fail_on_agent_profiles(_project_id: str, artifact_name: str):
        if artifact_name == "agent_profiles":
            raise AssertionError("read_seed should not gap-fill agent_profiles after entity rows exist")
        return {}

    monkeypatch.setattr(project_artifact_repo, "load_project_artifact", fail_on_agent_profiles)

    assets = Readers().read_seed(project.project_id)

    assert any(
        asset.entity_type == "seed_character" and asset.title == "沈夜"
        for asset in assets
    )
    assert not any(asset.entity_type == "seed_agent_profile" for asset in assets)
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "agent_profiles.json",
    ])


def test_unified_asset_view_does_not_gap_fill_ontology_from_artifact_when_seed_rows_exist(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories import project_artifact_repo
    from app.repositories.entity_repo import EntityRepository
    from app.services.assets.unified_asset_view import Readers

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        },
    )

    def fail_on_ontology(_project_id: str, artifact_name: str):
        if artifact_name == "ontology":
            raise AssertionError("read_seed should not gap-fill ontology after structured seed rows exist")
        return {}

    monkeypatch.setattr(project_artifact_repo, "load_project_artifact", fail_on_ontology)

    assets = Readers().read_seed(project.project_id)

    assert any(
        asset.entity_type == "seed_character" and asset.title == "沈夜"
        for asset in assets
    )
    assert not any(asset.entity_type == "seed_ontology_entity" for asset in assets)
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "ontology.json",
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


def test_worldline_source_loader_reads_archives_from_db_artifact(tmp_path, monkeypatch):
    from app.services.world_state_store import WorldStateStore
    from app.services.worldline_source_loader import WorldlineSourceLoader

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    _save_artifact(project.project_id, "narrative_archives", {
        "archives": [
            {
                "entity_uuid": "char_shenye",
                "entity_name": "沈夜",
                "entity_type": "Character",
                "agent_kind": "character",
                "importance_tier": "protagonist",
                "entity_role": "追查旧案的主角",
                "core_drive": "查清镜湖真相",
                "hidden_tension": "担心证人被提前灭口",
                "template_key": "character.protagonist.v1",
                "template_version": "v1",
                "template_sections": ["identity", "state"],
                "template_payload": {"state": {"status": "alert"}},
            }
        ],
    })

    fake_container = str(tmp_path / "no_such_container")
    loader = WorldlineSourceLoader(store=WorldStateStore())
    bundle = loader.load(project=project, graph_id="", container_dir=fake_container)

    assert bundle["source_summary"]["archives"] == 1
    assert bundle["actors"]["沈夜"]["state_source"] == "narrative_archives"
    assert bundle["actors"]["沈夜"]["drive"] == "查清镜湖真相"

    _assert_no_legacy_json(
        Path(projects_dir) / project.project_id,
        ["narrative_archives.json"],
    )


def test_worldline_source_loader_reads_entities_and_relationships_from_db_tables(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.relationship_repo import RelationshipRepository
    from app.services import worldline_source_loader as loader_module
    from app.services.world_state_store import WorldStateStore
    from app.services.worldline_source_loader import WorldlineSourceLoader

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    entities = EntityRepository(get_engine())
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "core_drive": "查清镜湖真相",
            "hidden_tension": "担心证人被提前灭口",
            "created_at": now,
            "updated_at": now,
        },
    )
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "org_mirror_lake",
            "name": "镜湖盟",
            "entity_type": "organization",
            "importance_tier": "major",
            "summary": "暗中操控镜湖旧案的组织。",
            "core_drive": "隐藏镜湖引擎真相",
            "hidden_tension": "内部成员开始动摇",
            "created_at": now,
            "updated_at": now,
        },
    )
    RelationshipRepository(get_engine()).upsert_relationship(
        project.project_id,
        {
            "relation_id": "rel_shenye_mirror_lake",
            "source_id": "char_shenye",
            "target_id": "org_mirror_lake",
            "relation_type": "conflict",
            "description": "沈夜正在逼近镜湖盟掩盖的真相。",
            "updated_at": now,
        },
    )

    def fail_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"worldline source should not load artifact {artifact_name}")

    monkeypatch.setattr(loader_module, "load_project_artifact", fail_artifact_probe)

    loader = WorldlineSourceLoader(store=WorldStateStore())
    bundle = loader.load(
        project=project,
        graph_id="",
        container_dir=str(tmp_path / "no_such_container"),
        config_override={},
    )

    assert bundle["actors"]["沈夜"]["state_source"] == "novel_db"
    assert bundle["actors"]["沈夜"]["drive"] == "查清镜湖真相"
    assert bundle["organizations"]["镜湖盟"]["state_source"] == "novel_db"
    assert bundle["relationships"][0]["source"] == "沈夜"
    assert bundle["relationships"][0]["target"] == "镜湖盟"
    assert bundle["relationships"][0]["state_source"] == "novel_db"
    assert bundle["source_summary"]["novel_entities"] == 2
    assert bundle["source_summary"]["seed_analysis"] is False
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "seed_analysis.json",
        "narrative_archives.json",
        "parallel_world_config.json",
    ])


def test_worldline_source_loader_reads_parallel_config_from_project_settings(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.meta_repo import MetaRepository
    from app.repositories.relationship_repo import RelationshipRepository
    from app.services import worldline_source_loader as loader_module
    from app.services.world_state_store import WorldStateStore
    from app.services.worldline_source_loader import WorldlineSourceLoader

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    config = {
        "simulation_goal": "观察密信提前泄露后的单世界演化",
        "world_variables": [
            {
                "name": "密信提前泄露",
                "description": "反派提前获知主角计划",
                "impact_axis": "信息差",
            }
        ],
        "branch_hypotheses": [],
        "timeline_focus": ["起因暴露", "联盟重组"],
        "agent_behavior_axes": ["信息差", "组织利益"],
    }
    payload = project.to_dict()
    payload["settings"] = {"parallel_world_config": config}
    MetaRepository(get_engine()).save_project_payload(project.project_id, payload)

    now = datetime.now().isoformat()
    entities = EntityRepository(get_engine())
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "org_mirror_lake",
            "name": "镜湖盟",
            "entity_type": "organization",
            "importance_tier": "major",
            "summary": "暗中操控镜湖旧案的组织。",
            "created_at": now,
            "updated_at": now,
        },
    )
    RelationshipRepository(get_engine()).upsert_relationship(
        project.project_id,
        {
            "relation_id": "rel_shenye_mirror_lake",
            "source_id": "char_shenye",
            "target_id": "org_mirror_lake",
            "relation_type": "conflict",
            "description": "沈夜正在逼近镜湖盟掩盖的真相。",
            "updated_at": now,
        },
    )

    def fail_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"worldline source should not load artifact {artifact_name}")

    monkeypatch.setattr(loader_module, "load_project_artifact", fail_artifact_probe)

    bundle = WorldlineSourceLoader(store=WorldStateStore()).load(
        project=project,
        graph_id="",
        container_dir=str(tmp_path / "no_such_container"),
    )

    assert bundle["config"] == config
    assert bundle["timeline_focus"] == ["起因暴露", "联盟重组"]
    assert bundle["agent_behavior_axes"] == ["信息差", "组织利益"]
    assert bundle["source_summary"]["parallel_world_config"] is True
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "parallel_world_config.json",
        "seed_analysis.json",
        "narrative_archives.json",
    ])


def test_worldline_source_loader_does_not_read_parallel_config_artifact_fallback(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.project_artifact_repo import ProjectArtifactRepository
    from app.repositories.relationship_repo import RelationshipRepository
    from app.services.world_state_store import WorldStateStore
    from app.services.worldline_source_loader import WorldlineSourceLoader

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    ProjectArtifactRepository(get_engine()).save(
        project.project_id,
        "parallel_world_config",
        {
            "timeline_focus": ["旧 artifact 变量"],
            "agent_behavior_axes": ["旧 artifact 轴"],
        },
    )
    now = datetime.now().isoformat()
    entities = EntityRepository(get_engine())
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "org_mirror_lake",
            "name": "镜湖盟",
            "entity_type": "organization",
            "importance_tier": "major",
            "summary": "暗中操控镜湖旧案的组织。",
            "created_at": now,
            "updated_at": now,
        },
    )
    RelationshipRepository(get_engine()).upsert_relationship(
        project.project_id,
        {
            "relation_id": "rel_shenye_mirror_lake",
            "source_id": "char_shenye",
            "target_id": "org_mirror_lake",
            "relation_type": "conflict",
            "description": "沈夜正在逼近镜湖盟掩盖的真相。",
            "updated_at": now,
        },
    )

    bundle = WorldlineSourceLoader(store=WorldStateStore()).load(
        project=project,
        graph_id="",
        container_dir=str(tmp_path / "no_such_container"),
    )

    assert bundle["config"] == {}
    assert bundle["timeline_focus"] == []
    assert bundle["agent_behavior_axes"] == []
    assert bundle["source_summary"]["parallel_world_config"] is False
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "parallel_world_config.json",
        "seed_analysis.json",
        "narrative_archives.json",
    ])


def test_worldline_source_loader_seed_gap_fill_uses_db_first_read_model(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.services import worldline_source_loader as loader_module
    from app.services.world_state_store import WorldStateStore
    from app.services.worldline_source_loader import WorldlineSourceLoader

    project, _projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "core_drive": "查清镜湖真相",
            "created_at": now,
            "updated_at": now,
        },
    )
    _save_artifact(
        project.project_id,
        "seed_analysis",
        {
            "characters": [{"name": "旧角色", "profile_summary": "旧 artifact 中的过时角色。"}],
            "chapter_beats": [{"title": "密信"}],
        },
    )

    def fail_direct_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"worldline loader should use read model, not {artifact_name}")

    monkeypatch.setattr(loader_module, "load_project_artifact", fail_direct_artifact_probe)

    seed = WorldlineSourceLoader(store=WorldStateStore())._load_seed_analysis(
        project.project_id,
    )

    assert [item["name"] for item in seed["characters"]] == ["沈夜"]
    assert seed["characters"][0]["core_drive"] == "查清镜湖真相"
    assert seed["chapter_beats"] == [{"title": "密信"}]


def test_graph_builder_reads_required_and_optional_artifacts_from_db(tmp_path, monkeypatch):
    from app.services.graph_builder import GraphBuilderService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
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

    project_dir = Path(projects_dir) / project.project_id
    (project_dir / "filesystem_only.json").write_text(
        '{"source":"filesystem"}',
        encoding="utf-8",
    )
    (project_dir / "optional_only.json").write_text(
        '{"source":"filesystem"}',
        encoding="utf-8",
    )
    ProjectArtifactRepository(get_engine()).delete(project.project_id, "reading_notes")
    (project_dir / "reading_notes.json").write_text(
        '{"source":"filesystem"}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="缺少构建本地图谱所需工件"):
        service._required_json(project.project_id, "filesystem_only.json")
    with pytest.raises(ValueError, match="缺少构建本地图谱所需工件"):
        service._required_json(project.project_id, "reading_notes.json")
    assert service._optional_json(project.project_id, "optional_only.json") is None


def test_graph_builder_builds_from_structured_tables_without_seed_artifacts(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.event_repo import EventRepository
    from app.repositories.relationship_repo import RelationshipRepository
    from app.repositories.world_rule_repo import WorldRuleRepository
    from app.repositories import project_artifact_repo
    from app.services.chapter_meta_service import ChapterMetaService
    from app.services.graph_builder import GraphBuilderService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    entities = EntityRepository(get_engine())
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    entities.upsert_alias(
        project.project_id,
        {"entity_id": "char_shenye", "alias": "夜哥"},
    )
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_qinzhao",
            "name": "秦昭",
            "entity_type": "character",
            "importance_tier": "major",
            "summary": "熟悉地下档案的盟友。",
            "created_at": now,
            "updated_at": now,
        },
    )
    RelationshipRepository(get_engine()).upsert_relationship(
        project.project_id,
        {
            "relation_id": "rel_shenye_qinzhao",
            "source_id": "char_shenye",
            "target_id": "char_qinzhao",
            "relation_type": "ally",
            "description": "两人暂时联手追查镜湖引擎。",
            "updated_at": now,
        },
    )
    EventRepository(get_engine()).log_character_event(
        project.project_id,
        {
            "event_id": "ev_engine_trace",
            "entity_id": "char_shenye",
            "segment_id": "seg_001",
            "chapter_order": 1,
            "event_type": "discovery",
            "summary": "沈夜在地下档案中启动镜湖引擎残响。",
            "detail_json": "{}",
            "created_at": now,
        },
    )
    WorldRuleRepository(get_engine()).upsert_world_rule(
        project.project_id,
        {
            "evidence_id": "rule_engine_trace",
            "fact_text": "镜湖引擎可以读取修士识海残痕。",
            "segment_id": "seg_001",
            "chapter_order": 1,
            "evidence_snippet": "镜湖引擎残响回应沈夜。",
            "created_at": now,
        },
    )
    ChapterMetaService().replace_project_chapter_cards(
        project.project_id,
        [
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "地下档案",
                "summary_text": "沈夜和秦昭追查镜湖引擎。",
                "start_anchor": "沈夜进入地下档案。",
                "end_anchor": "镜湖引擎残响被启动。",
                "open_threads": [],
            }
        ],
    )

    def fail_artifact_probe(project_id: str, artifact_key: str):
        raise AssertionError(f"unexpected artifact read: {artifact_key}")

    monkeypatch.setattr(project_artifact_repo, "load_project_artifact", fail_artifact_probe)

    graph = GraphBuilderService().build_graph(
        project.project_id,
        text="沈夜与秦昭在地下档案中启动镜湖引擎残响。",
        ontology={
            "entity_types": [
                {"name": "Character"},
                {"name": "PlotEvent"},
                {"name": "RuleSystem"},
            ],
            "edge_types": [
                {"name": "ALLY_WITH"},
                {"name": "PARTICIPATES_IN"},
                {"name": "OBEYS_RULE"},
            ],
        },
        graph_name="DB-only graph",
    )

    node_names = {node.name for node in graph.nodes}
    edge_names = {edge.name for edge in graph.edges}
    assert {"沈夜", "秦昭"}.issubset(node_names)
    assert "镜湖引擎可以读取修士识海残痕。" in node_names
    assert any("镜湖引擎" in node.name for node in graph.nodes)
    assert "ALLY_WITH" in edge_names
    assert "PARTICIPATES_IN" in edge_names
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "reading_notes.json",
        "seed_analysis.json",
        "story_memory.json",
        "chapter_continuity.json",
        "local_block_facts.json",
        "block_analyses.json",
    ])


def test_graph_builder_reads_open_threads_from_plot_threads_without_artifacts(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.thread_repo import ThreadRepository
    from app.services.graph_builder import GraphBuilderService

    class _SpyGraphBuilder:
        def __init__(self):
            self.kwargs = {}

        def build_for_project(self, **kwargs):
            self.kwargs = kwargs
            return {"graph_id": "spy"}

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    threads = ThreadRepository(get_engine())
    open_thread = threads.create_thread(
        project.project_id,
        thread_key="地下档案密钥",
        detail="地下档案密钥来源尚未揭开。",
        chapter_order=2,
    )
    threads.create_thread(
        project.project_id,
        thread_key="已结伏笔",
        detail="这条伏笔不应进入开放情节线。",
        status="resolved",
        chapter_order=1,
    )

    spy = _SpyGraphBuilder()
    result = GraphBuilderService(builder=spy).build_graph(
        project.project_id,
        text="沈夜进入地下档案。",
        ontology={"entity_types": [{"name": "Character"}], "edge_types": []},
        graph_name="DB-only open-thread graph",
    )

    assert result == {"graph_id": "spy"}
    open_threads = spy.kwargs["story_memory"]["open_threads"]
    assert {
        "thread_id": open_thread["thread_id"],
        "thread_key": "地下档案密钥",
        "summary": "地下档案密钥来源尚未揭开。",
        "status": "open",
        "source_chapter": "2",
    } in open_threads
    assert all(thread["thread_key"] != "已结伏笔" for thread in open_threads)
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "reading_notes.json",
        "seed_analysis.json",
        "story_memory.json",
        "chapter_continuity.json",
        "local_block_facts.json",
        "block_analyses.json",
    ])


def test_graph_builder_treats_plot_threads_as_structured_input_without_entities(
    tmp_path, monkeypatch
):
    from app.repositories import project_artifact_repo
    from app.repositories.thread_repo import ThreadRepository
    from app.services.graph_builder import GraphBuilderService

    class _SpyGraphBuilder:
        def __init__(self):
            self.kwargs = {}

        def build_for_project(self, **kwargs):
            self.kwargs = kwargs
            return {"graph_id": "spy"}

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    open_thread = ThreadRepository(get_engine()).create_thread(
        project.project_id,
        thread_key="地下档案密钥",
        detail="地下档案密钥来源尚未揭开。",
        chapter_order=2,
    )

    def fail_artifact_probe(_project_id: str, artifact_name: str):
        raise AssertionError(f"graph build should not load artifact {artifact_name}")

    monkeypatch.setattr(project_artifact_repo, "load_project_artifact", fail_artifact_probe)

    spy = _SpyGraphBuilder()
    result = GraphBuilderService(builder=spy).build_graph(
        project.project_id,
        text="沈夜进入地下档案。",
        ontology={"entity_types": [{"name": "Character"}], "edge_types": []},
        graph_name="DB-only plot-thread graph",
    )

    assert result == {"graph_id": "spy"}
    assert spy.kwargs["story_memory"]["open_threads"] == [
        {
            "thread_id": open_thread["thread_id"],
            "thread_key": "地下档案密钥",
            "summary": "地下档案密钥来源尚未揭开。",
            "status": "open",
            "source_chapter": "2",
        }
    ]
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "reading_notes.json",
        "seed_analysis.json",
        "story_memory.json",
        "chapter_continuity.json",
        "local_block_facts.json",
        "block_analyses.json",
    ])


def test_graph_builder_reads_relationship_events_without_artifacts(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from app.repositories.entity_repo import EntityRepository
    from app.repositories.event_repo import EventRepository
    from app.services.graph_builder import GraphBuilderService

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    entities = EntityRepository(get_engine())
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    entities.upsert_entity(
        project.project_id,
        {
            "entity_id": "char_qinzhao",
            "name": "秦昭",
            "entity_type": "character",
            "importance_tier": "major",
            "summary": "掌握地下档案密钥的盟友。",
            "created_at": now,
            "updated_at": now,
        },
    )
    EventRepository(get_engine()).log_relationship_event(
        project.project_id,
        {
            "event_id": "rel_event_archive_key",
            "source_entity_id": "char_shenye",
            "target_entity_id": "char_qinzhao",
            "segment_id": "seg_001",
            "chapter_order": 1,
            "relation_type": "ally",
            "previous_state": "互相试探",
            "new_state": "ally",
            "trigger_event": "秦昭交出地下档案密钥。",
            "emotional_shift": "信任上升",
            "power_shift": "",
            "evidence": "沈夜接过密钥，两人决定共同追查镜湖旧案。",
            "created_at": now,
        },
    )

    graph = GraphBuilderService().build_graph(
        project.project_id,
        text="沈夜接过秦昭递来的地下档案密钥。",
        ontology={
            "entity_types": [
                {"name": "Character"},
                {"name": "PlotEvent"},
            ],
            "edge_types": [
                {"name": "ALLY_WITH"},
                {"name": "PARTICIPATES_IN"},
            ],
        },
        graph_name="DB-only relationship-event graph",
    )

    node_names = {node.name for node in graph.nodes}
    edge_names = {edge.name for edge in graph.edges}
    assert "秦昭交出地下档案密钥。" in node_names
    assert "ALLY_WITH" in edge_names
    assert "PARTICIPATES_IN" in edge_names
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "reading_notes.json",
        "seed_analysis.json",
        "story_memory.json",
        "chapter_continuity.json",
        "local_block_facts.json",
        "block_analyses.json",
    ])


def test_graph_builder_reads_entity_evidence_without_artifacts(
    tmp_path, monkeypatch
):
    from datetime import datetime

    from sqlalchemy import insert

    from app.repositories.entity_repo import EntityRepository
    from app.services.graph_builder import GraphBuilderService
    from app.tables.novel import entity_evidence

    project, projects_dir = _setup_project(tmp_path, monkeypatch)
    now = datetime.now().isoformat()
    EntityRepository(get_engine()).upsert_entity(
        project.project_id,
        {
            "entity_id": "char_shenye",
            "name": "沈夜",
            "entity_type": "character",
            "importance_tier": "protagonist",
            "summary": "追查镜湖旧案的主角。",
            "created_at": now,
            "updated_at": now,
        },
    )
    with get_engine().begin() as conn:
        conn.execute(
            insert(entity_evidence).values(
                evidence_id="evd_shenye_archive_key",
                project_id=project.project_id,
                owner_id="char_shenye",
                owner_type="entity",
                chapter_id="chapter_0001",
                snippet="沈夜在地下档案里辨认出镜湖旧案密钥。",
                created_at=now,
            )
        )

    graph = GraphBuilderService().build_graph(
        project.project_id,
        text="沈夜进入地下档案。",
        ontology={"entity_types": [{"name": "Character"}], "edge_types": []},
        graph_name="DB-only entity-evidence graph",
    )

    shenye = next(node for node in graph.nodes if node.name == "沈夜")
    assert any(
        ref.chapter_id == "chapter_0001"
        and ref.snippet == "沈夜在地下档案里辨认出镜湖旧案密钥。"
        for ref in shenye.evidence_refs
    )
    _assert_no_legacy_json(Path(projects_dir) / project.project_id, [
        "reading_notes.json",
        "seed_analysis.json",
        "story_memory.json",
        "chapter_continuity.json",
        "local_block_facts.json",
        "block_analyses.json",
    ])


def test_load_project_artifact_accepts_both_filename_and_key(tmp_path, monkeypatch):
    """Regression guard: callers that still pass ``.json`` suffixes keep working."""
    from app.repositories.project_artifact_repo import load_project_artifact

    project, _ = _setup_project(tmp_path, monkeypatch)
    _save_artifact(project.project_id, "ontology", {"v": 1})

    assert load_project_artifact(project.project_id, "ontology.json") == {"v": 1}
    assert load_project_artifact(project.project_id, "ontology") == {"v": 1}
