"""Phase F / Task 7 — confirm archive / assets / llm services are
entirely DB-backed.

These services were re-pointed at the unified database during Phase A
(the large FastAPI + SQLAlchemy refactor). Phase F's purpose is to
add explicit regression gates: each service's CRUD must succeed while
the legacy silo files (``uploads/system/{archive_library,
assets_library,llm_facility}.sqlite3``) are absent, and crucially must
not re-create them.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

from app.database import init_db
from app.repositories.archive_repo import ArchiveRepository
from app.repositories.llm_repo import LlmRepository
from app.services.archive_library_service import ArchiveLibraryService
from app.services.assets.assets_service import GLOBAL_SCOPE, PROJECT_SCOPE, AssetsService


def _legacy_paths(tmp_path: Path) -> list[Path]:
    system = tmp_path / "uploads" / "system"
    return [
        system / "archive_library.sqlite3",
        system / "assets_library.sqlite3",
        system / "llm_facility.sqlite3",
    ]


def _assert_no_legacy_silos(tmp_path: Path) -> None:
    for path in _legacy_paths(tmp_path):
        assert not path.exists(), f"legacy silo resurrected at {path}"


def test_archive_service_crud_uses_unified_db_only(tmp_path, monkeypatch):
    _assert_no_legacy_silos(tmp_path)
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)

    repo = ArchiveRepository(engine)
    repo.upsert_archive(
        {
            "archive_id": "arc_hero",
            "project_id": "proj_demo",
            "project_name": "Demo",
            "entity_uuid": "ent_hero",
            "entity_name": "Lin",
            "entity_type": "character",
            "agent_kind": "generic",
            "importance_tier": "protagonist",
            "recommended_importance_tier": "protagonist",
            "selected_importance_tier": "protagonist",
            "template_key": "generic.protagonist.v1",
            "template_version": "v1",
            "entity_role": "hero",
            "core_drive": "courage",
            "surface_mask": "calm",
            "hidden_tension": "regret",
            "relationship_summary": "",
            "agent_behavior_hint": "",
            "human_ai_relation_tag": "none",
            "can_act_as_agent": 1,
            "notable_risks_json": "[]",
            "template_sections_json": "[]",
            "template_payload_json": "{}",
            "template_metadata_json": "{}",
            "synced_at": "2026-04-17T00:00:00",
        }
    )

    service = ArchiveLibraryService(repo=repo)
    # sync_incremental walks ProjectManager.PROJECTS_DIR; point it at an
    # empty temp dir so the JSON-source path is a no-op.
    from app.models.project import ProjectManager

    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    (tmp_path / "projects").mkdir(parents=True, exist_ok=True)

    archive = service.get_archive("arc_hero")
    assert archive["entity_name"] == "Lin"

    # Post-P5: archive rows live in ``assets`` with
    # ``asset_type='archive_entity'``; the ``archive_library`` table
    # was dropped by migration 20260419_0003.
    with engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM assets "
                "WHERE asset_id = :id AND asset_type = 'archive_entity'"
            ),
            {"id": "arc_hero"},
        ).scalar()
    assert count == 1
    _assert_no_legacy_silos(tmp_path)


def test_assets_service_crud_uses_unified_db_only(tmp_path, monkeypatch):
    _assert_no_legacy_silos(tmp_path)
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)

    from app.repositories.asset_repo import AssetRepository

    service = AssetsService(repo=AssetRepository(engine))

    created = service.create(
        scope=GLOBAL_SCOPE,
        asset_type="style",
        title="Global Style Preset",
        content="Example body",
        tags=["demo"],
    )
    assert created["asset_id"]
    asset_id = created["asset_id"]

    service.update(asset_id, scope=GLOBAL_SCOPE, summary="Updated summary")
    listed = service.list(scope=GLOBAL_SCOPE)
    titles = [item["title"] for item in listed]
    assert "Global Style Preset" in titles

    service.create(
        scope=PROJECT_SCOPE,
        asset_type="codex",
        title="Project Codex",
        project_id="proj_f",
        tags=["codex"],
    )
    project_list = service.list(scope=PROJECT_SCOPE, project_id="proj_f")
    assert [item["title"] for item in project_list] == ["Project Codex"]

    with engine.connect() as conn:
        global_count = conn.execute(
            text("SELECT COUNT(*) FROM assets WHERE scope = 'global'")
        ).scalar()
        project_count = conn.execute(
            text("SELECT COUNT(*) FROM assets WHERE scope = 'project' AND project_id = 'proj_f'")
        ).scalar()
    assert global_count == 1
    assert project_count == 1

    removed = service.delete(asset_id, scope=GLOBAL_SCOPE)
    assert removed is True

    _assert_no_legacy_silos(tmp_path)


def test_llm_facility_repo_crud_uses_unified_db_only(tmp_path, monkeypatch):
    _assert_no_legacy_silos(tmp_path)
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)

    repo = LlmRepository(engine)
    repo.upsert_channel(
        {
            "channel_key": "ch_test",
            "name": "TestChannel",
            "base_url": "https://api.example.com",
            "api_key": "sk-local",
            "max_concurrency": 4,
            "is_enabled": 1,
            "created_at": "2026-04-17T00:00:00",
            "updated_at": "2026-04-17T00:00:00",
            "last_sync_status": "idle",
        }
    )
    repo.upsert_binding(
        {
            "module_key": "writer_composer",
            "channel_key": "ch_test",
            "model_id": "sonnet-test",
            "updated_at": "2026-04-17T00:00:00",
        }
    )

    channels = repo.list_channels()
    assert [ch["channel_key"] for ch in channels] == ["ch_test"]

    bindings = repo.list_bindings()
    assert {b["module_key"]: b["channel_key"] for b in bindings} == {"writer_composer": "ch_test"}

    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM llm_channels")).scalar() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM llm_module_bindings")).scalar() == 1

    _assert_no_legacy_silos(tmp_path)
