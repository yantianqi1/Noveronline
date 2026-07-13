from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
SQL = (ROOT / "infra/postgres/migrations/0004_writer_workspace.sql").read_text(encoding="utf-8")
NORMALIZED = re.sub(r"\s+", " ", SQL.lower())


TABLES = {
    "chapters",
    "chapter_versions",
    "scenes",
    "scene_versions",
    "outline_versions",
    "book_plans",
    "book_run_events",
    "writer_presets",
    "forbidden_lexicon_entries",
}


def test_writer_workspace_migration_is_transactional_and_complete():
    assert NORMALIZED.startswith("begin;")
    assert NORMALIZED.strip().endswith("commit;")
    for table in TABLES:
        assert f"create table {table}" in NORMALIZED


def test_every_table_has_tenant_project_context_and_project_fk():
    for table in TABLES:
        body = re.search(rf"create table {table} \((.*?)\n\);", SQL, re.I | re.S).group(1).lower()
        assert "tenant_id uuid not null" in body
        assert "project_id uuid" in body
        assert "references projects(tenant_id, project_id)" in body


def test_versions_are_immutable_snapshots_with_lineage():
    assert "unique (tenant_id, project_id, chapter_id, version_number)" in NORMALIZED
    assert "unique (tenant_id, project_id, scene_id, version_number)" in NORMALIZED
    assert "references outline_versions(tenant_id, project_id, outline_version_id)" in NORMALIZED
    assert "where lifecycle = 'active'" in NORMALIZED
    assert "revoke update, delete on chapter_versions, scene_versions, book_run_events" in NORMALIZED
    assert "revoke delete on outline_versions" in NORMALIZED
    assert "create trigger trg_outline_versions_immutable" in NORMALIZED
    assert "outline version snapshots are immutable" in NORMALIZED


def test_active_order_constraints_are_scoped_and_ignore_archived_rows():
    assert "create unique index chapters_project_active_order_key on chapters (tenant_id, project_id, chapter_order) where status <> 'archived'" in NORMALIZED
    assert "create unique index scenes_chapter_active_order_key on scenes (tenant_id, project_id, chapter_id, scene_order) where status <> 'archived'" in NORMALIZED


def test_clean_migration_does_not_keep_legacy_deferrable_order_constraints():
    assert "chapters_project_order_key" not in NORMALIZED
    assert "scenes_chapter_order_key" not in NORMALIZED


def test_book_events_are_count_only():
    event_body = re.search(r"create table book_run_events \((.*?)\n\);", SQL, re.I | re.S).group(1).lower()
    assert "item_count integer" in event_body
    assert "warning_count integer" in event_body
    for private_name in ("payload", "content", "body", "prompt", "response"):
        assert private_name not in event_body


def test_presets_cannot_store_provider_or_credential_columns():
    preset_body = re.search(r"create table writer_presets \((.*?)\n\);", SQL, re.I | re.S).group(1).lower()
    for forbidden in ("provider", "credential", "api_key", "prompt"):
        assert forbidden not in preset_body


def test_rls_force_grants_and_indexes_cover_every_table():
    assert "enable row level security" in NORMALIZED
    assert "force row level security" in NORMALIZED
    assert "grant select, insert, update, delete" in NORMALIZED
    assert "to mirofish_app" in NORMALIZED
    for table in TABLES:
        assert table in NORMALIZED
    for index in (
        "idx_chapters_project",
        "idx_chapter_versions_history",
        "idx_scenes_chapter",
        "idx_scene_versions_history",
        "idx_outline_versions_scope",
        "idx_book_plans_project",
        "idx_book_run_events_replay",
        "idx_writer_presets_scope",
        "idx_forbidden_lexicon_project",
    ):
        assert f"create index {index}" in NORMALIZED
