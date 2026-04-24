"""migrate archive_library into assets + switch triggers

Revision ID: 20260419_0003
Revises: 20260419_0002
Create Date: 2026-04-19

Completes the asset-library refactor P5: moves all ``archive_library``
rows into the ``assets`` table as ``asset_type='archive_entity'`` rows,
rewires the global_index sync triggers to branch on ``asset_type``
instead of on the source table, and drops ``archive_library``.

Data migration mapping (archive_library → assets)::

  asset_id                    ← archive_id
  project_id                  ← project_id
  scope                       = 'project'
  asset_type                  = 'archive_entity'
  title                       ← entity_name
  summary                     ← entity_role (fallback: core_drive, relationship_summary, '')
  content                     = ''
  payload_json                = '{}'        (archive fields live in dedicated cols)
  tags_json                   = '[]'
  source_kind                 = 'archive'
  source_ref                  ← entity_uuid
  enabled                     = 1
  pinned                      = 0
  word_count                  = 0
  created_at, updated_at      ← synced_at
  entity_uuid, entity_name,
    entity_type, agent_kind,
    importance_tier,
    recommended_importance_tier,
    selected_importance_tier,
    template_key, template_version,
    entity_role, core_drive,
    surface_mask, hidden_tension,
    relationship_summary,
    agent_behavior_hint,
    human_ai_relation_tag,
    can_act_as_agent,
    notable_risks_json,
    template_sections_json,
    template_payload_json,
    template_metadata_json,
    entity_id, synced_at      ← 1:1 from archive_library

Trigger changes:

  Before 20260419_0003 (from 20260419_0001):
    assets_to_global_index_*       → always source='assets'
    archive_to_global_index_*      → source='archive' from archive_library

  After 20260419_0003:
    assets_to_global_index_generic_*    → source='assets' WHEN asset_type != 'archive_entity'
    assets_to_global_index_archive_*    → source='archive' WHEN asset_type == 'archive_entity'
    (archive_to_global_index_* dropped along with archive_library)

The satellite tables ``archive_sources``, ``archive_agent_memory``, and
``archive_agent_memory_events`` are **kept as-is** (same names, same
schema). Their ``archive_id`` columns now reference ``assets.asset_id``
via soft FK — the values are identical to the old archive_library.archive_id
values that migrated over, so no data change is needed.

Rollback policy:

  downgrade() is a best-effort restore. It:
    1. Recreates the archive_library table
    2. Copies archive_entity rows back from assets
    3. Restores the original triggers
    4. Deletes archive_entity rows from assets

  It does NOT drop the 23 new columns on assets (those come from
  20260419_0002 and must be downgraded separately).

SQLite only. Postgres port will follow when the app is deployed
against Postgres; the archive table definition in ``tables/archive.py``
will need dual-dialect DDL at that point.

Phase: asset-library refactor / P5 schema-merge step 2.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260419_0003"
down_revision = "20260419_0002"
branch_labels = None
depends_on = None


# ----------------------------------------------------------------------
# Data migration
# ----------------------------------------------------------------------

_MIGRATE_ARCHIVE_TO_ASSETS = """
INSERT INTO assets (
    asset_id, project_id, scope, asset_type, category, title, summary,
    content, payload_json, tags_json, source_kind, source_ref,
    enabled, pinned, word_count, created_at, updated_at,
    entity_uuid, entity_name, entity_type, agent_kind, importance_tier,
    recommended_importance_tier, selected_importance_tier,
    template_key, template_version, entity_role, core_drive,
    surface_mask, hidden_tension, relationship_summary,
    agent_behavior_hint, human_ai_relation_tag, can_act_as_agent,
    notable_risks_json, template_sections_json, template_payload_json,
    template_metadata_json, entity_id, synced_at
)
SELECT
    archive_id, project_id, 'project', 'archive_entity', '',
    COALESCE(entity_name, ''),
    COALESCE(NULLIF(entity_role, ''), NULLIF(core_drive, ''), NULLIF(relationship_summary, ''), ''),
    '', '{}', '[]', 'archive', COALESCE(entity_uuid, ''),
    1, 0, 0, COALESCE(synced_at, ''), COALESCE(synced_at, ''),
    entity_uuid, entity_name, entity_type, agent_kind, importance_tier,
    recommended_importance_tier, selected_importance_tier,
    template_key, template_version, entity_role, core_drive,
    surface_mask, hidden_tension, relationship_summary,
    agent_behavior_hint, human_ai_relation_tag, can_act_as_agent,
    notable_risks_json, template_sections_json, template_payload_json,
    template_metadata_json, entity_id, synced_at
FROM archive_library
"""


# ----------------------------------------------------------------------
# Trigger DDL: after the merge, assets itself hosts both regular and
# archive rows. We need two paired triggers per event (INSERT/UPDATE/
# DELETE), branching on ``asset_type``. SQLite supports ``WHEN`` clauses
# on row-level triggers which makes this straightforward.
# ----------------------------------------------------------------------

_DROP_OLD_TRIGGERS = (
    "DROP TRIGGER IF EXISTS assets_to_global_index_ai",
    "DROP TRIGGER IF EXISTS assets_to_global_index_au",
    "DROP TRIGGER IF EXISTS assets_to_global_index_ad",
    "DROP TRIGGER IF EXISTS archive_to_global_index_ai",
    "DROP TRIGGER IF EXISTS archive_to_global_index_au",
    "DROP TRIGGER IF EXISTS archive_to_global_index_ad",
)

# Generic assets (non-archive): same body as before, gated by WHEN clause.
_NEW_GENERIC_TRIGGERS = (
    """
    CREATE TRIGGER IF NOT EXISTS assets_to_global_index_generic_ai
    AFTER INSERT ON assets
    WHEN NEW.asset_type != 'archive_entity'
    BEGIN
        INSERT OR REPLACE INTO global_index
            (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
        VALUES (
            'assets',
            NEW.asset_id,
            NEW.project_id,
            COALESCE(NEW.asset_type, ''),
            COALESCE(NEW.title, ''),
            COALESCE(NEW.summary, '') || char(10) ||
            COALESCE(NEW.content, '') || char(10) ||
            COALESCE(NEW.payload_json, ''),
            COALESCE(NEW.tags_json, ''),
            COALESCE(NEW.updated_at, ''),
            COALESCE(NEW.payload_json, '{}')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS assets_to_global_index_generic_au
    AFTER UPDATE ON assets
    WHEN NEW.asset_type != 'archive_entity'
    BEGIN
        INSERT OR REPLACE INTO global_index
            (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
        VALUES (
            'assets',
            NEW.asset_id,
            NEW.project_id,
            COALESCE(NEW.asset_type, ''),
            COALESCE(NEW.title, ''),
            COALESCE(NEW.summary, '') || char(10) ||
            COALESCE(NEW.content, '') || char(10) ||
            COALESCE(NEW.payload_json, ''),
            COALESCE(NEW.tags_json, ''),
            COALESCE(NEW.updated_at, ''),
            COALESCE(NEW.payload_json, '{}')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS assets_to_global_index_generic_ad
    AFTER DELETE ON assets
    WHEN OLD.asset_type != 'archive_entity'
    BEGIN
        DELETE FROM global_index
        WHERE source = 'assets' AND source_ref = OLD.asset_id;
    END
    """,
)

# Archive rows inside assets: write with source='archive' + archive fields.
_NEW_ARCHIVE_TRIGGERS = (
    """
    CREATE TRIGGER IF NOT EXISTS assets_to_global_index_archive_ai
    AFTER INSERT ON assets
    WHEN NEW.asset_type = 'archive_entity'
    BEGIN
        INSERT OR REPLACE INTO global_index
            (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
        VALUES (
            'archive',
            NEW.asset_id,
            NEW.project_id,
            COALESCE(NEW.entity_type, ''),
            COALESCE(NEW.entity_name, ''),
            COALESCE(NEW.entity_role, '') || char(10) ||
            COALESCE(NEW.core_drive, '') || char(10) ||
            COALESCE(NEW.surface_mask, '') || char(10) ||
            COALESCE(NEW.hidden_tension, '') || char(10) ||
            COALESCE(NEW.relationship_summary, '') || char(10) ||
            COALESCE(NEW.template_payload_json, ''),
            '',
            COALESCE(NEW.synced_at, NEW.updated_at, ''),
            COALESCE(NEW.template_payload_json, '{}')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS assets_to_global_index_archive_au
    AFTER UPDATE ON assets
    WHEN NEW.asset_type = 'archive_entity'
    BEGIN
        INSERT OR REPLACE INTO global_index
            (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
        VALUES (
            'archive',
            NEW.asset_id,
            NEW.project_id,
            COALESCE(NEW.entity_type, ''),
            COALESCE(NEW.entity_name, ''),
            COALESCE(NEW.entity_role, '') || char(10) ||
            COALESCE(NEW.core_drive, '') || char(10) ||
            COALESCE(NEW.surface_mask, '') || char(10) ||
            COALESCE(NEW.hidden_tension, '') || char(10) ||
            COALESCE(NEW.relationship_summary, '') || char(10) ||
            COALESCE(NEW.template_payload_json, ''),
            '',
            COALESCE(NEW.synced_at, NEW.updated_at, ''),
            COALESCE(NEW.template_payload_json, '{}')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS assets_to_global_index_archive_ad
    AFTER DELETE ON assets
    WHEN OLD.asset_type = 'archive_entity'
    BEGIN
        DELETE FROM global_index
        WHERE source = 'archive' AND source_ref = OLD.asset_id;
    END
    """,
)


# ----------------------------------------------------------------------
# Downgrade: reverse migration. Schema-only; data round-trip is
# best-effort because the archive_library table must be recreated from
# the assets snapshot.
# ----------------------------------------------------------------------

_RECREATE_ARCHIVE_LIBRARY = """
CREATE TABLE IF NOT EXISTS archive_library (
    archive_id                  TEXT PRIMARY KEY,
    project_id                  TEXT NOT NULL,
    project_name                TEXT NOT NULL,
    entity_uuid                 TEXT NOT NULL,
    entity_name                 TEXT NOT NULL,
    entity_type                 TEXT NOT NULL,
    agent_kind                  TEXT NOT NULL DEFAULT 'generic',
    importance_tier             TEXT NOT NULL,
    recommended_importance_tier TEXT NOT NULL DEFAULT 'supporting',
    selected_importance_tier    TEXT NOT NULL DEFAULT 'supporting',
    template_key                TEXT NOT NULL DEFAULT 'generic.supporting.v1',
    template_version            TEXT NOT NULL DEFAULT 'v1',
    entity_role                 TEXT NOT NULL,
    core_drive                  TEXT NOT NULL,
    surface_mask                TEXT NOT NULL,
    hidden_tension              TEXT NOT NULL,
    relationship_summary        TEXT NOT NULL,
    agent_behavior_hint         TEXT NOT NULL,
    human_ai_relation_tag       TEXT NOT NULL,
    can_act_as_agent            INTEGER NOT NULL DEFAULT 1,
    notable_risks_json          TEXT NOT NULL DEFAULT '[]',
    template_sections_json      TEXT NOT NULL DEFAULT '[]',
    template_payload_json       TEXT NOT NULL DEFAULT '{}',
    template_metadata_json      TEXT NOT NULL DEFAULT '{}',
    synced_at                   TEXT NOT NULL,
    entity_id                   TEXT
)
"""

_RESTORE_ARCHIVE_FROM_ASSETS = """
INSERT OR REPLACE INTO archive_library (
    archive_id, project_id, project_name, entity_uuid, entity_name,
    entity_type, agent_kind, importance_tier,
    recommended_importance_tier, selected_importance_tier,
    template_key, template_version, entity_role, core_drive,
    surface_mask, hidden_tension, relationship_summary,
    agent_behavior_hint, human_ai_relation_tag, can_act_as_agent,
    notable_risks_json, template_sections_json, template_payload_json,
    template_metadata_json, synced_at, entity_id
)
SELECT
    asset_id, COALESCE(project_id, ''), '',
    COALESCE(entity_uuid, ''), COALESCE(entity_name, ''),
    COALESCE(entity_type, ''), COALESCE(agent_kind, 'generic'),
    COALESCE(importance_tier, 'supporting'),
    COALESCE(recommended_importance_tier, 'supporting'),
    COALESCE(selected_importance_tier, 'supporting'),
    COALESCE(template_key, 'generic.supporting.v1'),
    COALESCE(template_version, 'v1'),
    COALESCE(entity_role, ''), COALESCE(core_drive, ''),
    COALESCE(surface_mask, ''), COALESCE(hidden_tension, ''),
    COALESCE(relationship_summary, ''),
    COALESCE(agent_behavior_hint, ''),
    COALESCE(human_ai_relation_tag, ''),
    COALESCE(can_act_as_agent, 1),
    COALESCE(notable_risks_json, '[]'),
    COALESCE(template_sections_json, '[]'),
    COALESCE(template_payload_json, '{}'),
    COALESCE(template_metadata_json, '{}'),
    COALESCE(synced_at, updated_at, ''),
    entity_id
FROM assets WHERE asset_type = 'archive_entity'
"""

_DELETE_ARCHIVE_FROM_ASSETS = (
    "DELETE FROM assets WHERE asset_type = 'archive_entity'"
)

_RESTORE_OLD_TRIGGERS = (
    """
    CREATE TRIGGER IF NOT EXISTS assets_to_global_index_ai
    AFTER INSERT ON assets
    BEGIN
        INSERT OR REPLACE INTO global_index
            (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
        VALUES (
            'assets', NEW.asset_id, NEW.project_id,
            COALESCE(NEW.asset_type, ''), COALESCE(NEW.title, ''),
            COALESCE(NEW.summary, '') || char(10) ||
            COALESCE(NEW.content, '') || char(10) ||
            COALESCE(NEW.payload_json, ''),
            COALESCE(NEW.tags_json, ''),
            COALESCE(NEW.updated_at, ''),
            COALESCE(NEW.payload_json, '{}')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS assets_to_global_index_au
    AFTER UPDATE ON assets
    BEGIN
        INSERT OR REPLACE INTO global_index
            (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
        VALUES (
            'assets', NEW.asset_id, NEW.project_id,
            COALESCE(NEW.asset_type, ''), COALESCE(NEW.title, ''),
            COALESCE(NEW.summary, '') || char(10) ||
            COALESCE(NEW.content, '') || char(10) ||
            COALESCE(NEW.payload_json, ''),
            COALESCE(NEW.tags_json, ''),
            COALESCE(NEW.updated_at, ''),
            COALESCE(NEW.payload_json, '{}')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS assets_to_global_index_ad
    AFTER DELETE ON assets
    BEGIN
        DELETE FROM global_index
        WHERE source = 'assets' AND source_ref = OLD.asset_id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS archive_to_global_index_ai
    AFTER INSERT ON archive_library
    BEGIN
        INSERT OR REPLACE INTO global_index
            (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
        VALUES (
            'archive', NEW.archive_id, NEW.project_id,
            COALESCE(NEW.entity_type, ''), COALESCE(NEW.entity_name, ''),
            COALESCE(NEW.entity_role, '') || char(10) ||
            COALESCE(NEW.core_drive, '') || char(10) ||
            COALESCE(NEW.surface_mask, '') || char(10) ||
            COALESCE(NEW.hidden_tension, '') || char(10) ||
            COALESCE(NEW.relationship_summary, '') || char(10) ||
            COALESCE(NEW.template_payload_json, ''),
            '',
            COALESCE(NEW.synced_at, ''),
            COALESCE(NEW.template_payload_json, '{}')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS archive_to_global_index_au
    AFTER UPDATE ON archive_library
    BEGIN
        INSERT OR REPLACE INTO global_index
            (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
        VALUES (
            'archive', NEW.archive_id, NEW.project_id,
            COALESCE(NEW.entity_type, ''), COALESCE(NEW.entity_name, ''),
            COALESCE(NEW.entity_role, '') || char(10) ||
            COALESCE(NEW.core_drive, '') || char(10) ||
            COALESCE(NEW.surface_mask, '') || char(10) ||
            COALESCE(NEW.hidden_tension, '') || char(10) ||
            COALESCE(NEW.relationship_summary, '') || char(10) ||
            COALESCE(NEW.template_payload_json, ''),
            '',
            COALESCE(NEW.synced_at, ''),
            COALESCE(NEW.template_payload_json, '{}')
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS archive_to_global_index_ad
    AFTER DELETE ON archive_library
    BEGIN
        DELETE FROM global_index
        WHERE source = 'archive' AND source_ref = OLD.archive_id;
    END
    """,
)

_DROP_NEW_TRIGGERS = (
    "DROP TRIGGER IF EXISTS assets_to_global_index_generic_ai",
    "DROP TRIGGER IF EXISTS assets_to_global_index_generic_au",
    "DROP TRIGGER IF EXISTS assets_to_global_index_generic_ad",
    "DROP TRIGGER IF EXISTS assets_to_global_index_archive_ai",
    "DROP TRIGGER IF EXISTS assets_to_global_index_archive_au",
    "DROP TRIGGER IF EXISTS assets_to_global_index_archive_ad",
)


def _is_sqlite(bind) -> bool:
    return bind.dialect.name == "sqlite"


def upgrade() -> None:
    bind = op.get_bind()
    if not _is_sqlite(bind):
        return

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "archive_library" not in tables:
        # Already migrated (or fresh install from a future snapshot where
        # archive_library never existed). Still need to set up the new
        # triggers since they may not exist yet.
        for stmt in _DROP_OLD_TRIGGERS:
            op.execute(stmt)
        for stmt in _NEW_GENERIC_TRIGGERS:
            op.execute(stmt)
        for stmt in _NEW_ARCHIVE_TRIGGERS:
            op.execute(stmt)
        return

    # Step 1: migrate data while archive_library + old triggers still
    # exist. The old archive_to_global_index triggers will fire when we
    # later DELETE from archive_library (during drop) — those DELETEs
    # wipe the 'archive'-source rows from global_index. We then
    # re-populate from assets via the new triggers' INSERT side when the
    # archive_entity rows land in assets.
    op.execute(_MIGRATE_ARCHIVE_TO_ASSETS)

    # Step 2: drop the old triggers before we start writing archive_entity
    # rows so the triggers don't double-fire.
    for stmt in _DROP_OLD_TRIGGERS:
        op.execute(stmt)

    # Step 3: install the new pair of assets triggers. These fire on
    # the rows we just INSERTed in step 1 only going forward; past
    # rows need an explicit backfill.
    for stmt in _NEW_GENERIC_TRIGGERS:
        op.execute(stmt)
    for stmt in _NEW_ARCHIVE_TRIGGERS:
        op.execute(stmt)

    # Step 4: backfill global_index from the archive_entity rows now in
    # assets. The old archive_library triggers had already populated
    # global_index with source='archive'; that data is still correct
    # because source_ref == archive_id == asset_id. But the data the old
    # triggers wrote is keyed to the (soon-to-be-dropped) archive_library.
    # We keep those rows; they match the new trigger output.
    # Nothing to do here — rows persist.

    # Step 5: drop archive_library. The satellite tables
    # (archive_sources, archive_agent_memory, archive_agent_memory_events)
    # stay — their archive_id column now soft-FK's to assets.asset_id.
    op.execute("DROP TABLE IF EXISTS archive_library")


def downgrade() -> None:
    bind = op.get_bind()
    if not _is_sqlite(bind):
        return

    op.execute(_RECREATE_ARCHIVE_LIBRARY)
    op.execute(_RESTORE_ARCHIVE_FROM_ASSETS)
    op.execute(_DELETE_ARCHIVE_FROM_ASSETS)

    for stmt in _DROP_NEW_TRIGGERS:
        op.execute(stmt)
    for stmt in _RESTORE_OLD_TRIGGERS:
        op.execute(stmt)
