"""sync global_index via triggers on assets and archive_library

Revision ID: 20260419_0001
Revises: 20260418_0003
Create Date: 2026-04-19

Makes ``global_index`` self-maintaining for the two tabular silos
(``assets``, ``archive_library``) by adding SQLite AFTER INSERT/UPDATE/
DELETE triggers that mirror changes into ``global_index``. Previously
``global_index`` only refreshed when someone called
``GlobalSearchIndexer.reindex_project()`` — a manual entry point that
was easy to forget and, worse, was invoked by a dead-code path in
``api_fastapi/unified_assets.py:search_unified`` (calling a
nonexistent ``indexer._connect()`` method). With triggers in place:

- ``assets`` INSERT/UPDATE/DELETE → ``global_index`` row with source='assets'
- ``archive_library`` INSERT/UPDATE/DELETE → ``global_index`` row with source='archive'
- Triggers fire inside the writing transaction, so search is consistent
  with the source table within a single statement.

Other silos (story_graph / novel_db / worldline / seed) are NOT covered
by triggers — they live in multiple normalized tables and are still
materialized by ``reindex_project()``. That entry point stays.

The upgrade also runs a one-time backfill so existing rows land in
``global_index`` immediately instead of waiting for the next UPDATE.

SQLite only. Postgres port will land alongside the P5 merge migration
(the archive_library table is slated for deletion in Phase 5, so the
archive half of this trigger is a transitional stepping stone).

Phase: asset-library refactor / P1 Spike (search path unification).
"""

from __future__ import annotations

from alembic import op


revision = "20260419_0001"
down_revision = "20260418_0003"
branch_labels = None
depends_on = None


# ----------------------------------------------------------------------
# Trigger bodies — defined once so upgrade/downgrade stay in sync.
# ----------------------------------------------------------------------

# ``body`` concatenates title-relevant fields + payload_json so the FTS
# trigram tokenizer on ``global_index_fts`` can match substrings across
# any textual column. The exact format does not need to match
# ``SearchRepository.upsert`` byte-for-byte; both produce
# "reasonably searchable text" that the FTS layer then indexes.

_ASSETS_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS assets_to_global_index_ai
AFTER INSERT ON assets
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
"""

_ASSETS_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS assets_to_global_index_au
AFTER UPDATE ON assets
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
"""

_ASSETS_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS assets_to_global_index_ad
AFTER DELETE ON assets
BEGIN
    DELETE FROM global_index
    WHERE source = 'assets' AND source_ref = OLD.asset_id;
END
"""

_ARCHIVE_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS archive_to_global_index_ai
AFTER INSERT ON archive_library
BEGIN
    INSERT OR REPLACE INTO global_index
        (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
    VALUES (
        'archive',
        NEW.archive_id,
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
        COALESCE(NEW.synced_at, ''),
        COALESCE(NEW.template_payload_json, '{}')
    );
END
"""

_ARCHIVE_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS archive_to_global_index_au
AFTER UPDATE ON archive_library
BEGIN
    INSERT OR REPLACE INTO global_index
        (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
    VALUES (
        'archive',
        NEW.archive_id,
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
        COALESCE(NEW.synced_at, ''),
        COALESCE(NEW.template_payload_json, '{}')
    );
END
"""

_ARCHIVE_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS archive_to_global_index_ad
AFTER DELETE ON archive_library
BEGIN
    DELETE FROM global_index
    WHERE source = 'archive' AND source_ref = OLD.archive_id;
END
"""

_ALL_TRIGGERS = (
    _ASSETS_INSERT_TRIGGER,
    _ASSETS_UPDATE_TRIGGER,
    _ASSETS_DELETE_TRIGGER,
    _ARCHIVE_INSERT_TRIGGER,
    _ARCHIVE_UPDATE_TRIGGER,
    _ARCHIVE_DELETE_TRIGGER,
)

_TRIGGER_NAMES = (
    "assets_to_global_index_ai",
    "assets_to_global_index_au",
    "assets_to_global_index_ad",
    "archive_to_global_index_ai",
    "archive_to_global_index_au",
    "archive_to_global_index_ad",
)


# One-time backfill: wipe existing assets/archive rows from global_index
# and rematerialize them. We don't touch the other four sources' rows
# (story_graph / novel_db / worldline / seed) — they stay until the next
# reindex_project() runs.

_BACKFILL_DELETE = """
DELETE FROM global_index WHERE source IN ('assets', 'archive')
"""

_BACKFILL_ASSETS = """
INSERT OR REPLACE INTO global_index
    (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
SELECT
    'assets',
    asset_id,
    project_id,
    COALESCE(asset_type, ''),
    COALESCE(title, ''),
    COALESCE(summary, '') || char(10) ||
    COALESCE(content, '') || char(10) ||
    COALESCE(payload_json, ''),
    COALESCE(tags_json, ''),
    COALESCE(updated_at, ''),
    COALESCE(payload_json, '{}')
FROM assets
"""

_BACKFILL_ARCHIVE = """
INSERT OR REPLACE INTO global_index
    (source, source_ref, project_id, entity_type, title, body, tags, updated_at, payload_json)
SELECT
    'archive',
    archive_id,
    project_id,
    COALESCE(entity_type, ''),
    COALESCE(entity_name, ''),
    COALESCE(entity_role, '') || char(10) ||
    COALESCE(core_drive, '') || char(10) ||
    COALESCE(surface_mask, '') || char(10) ||
    COALESCE(hidden_tension, '') || char(10) ||
    COALESCE(relationship_summary, '') || char(10) ||
    COALESCE(template_payload_json, ''),
    '',
    COALESCE(synced_at, ''),
    COALESCE(template_payload_json, '{}')
FROM archive_library
"""


def _is_sqlite(bind) -> bool:
    return bind.dialect.name == "sqlite"


def upgrade() -> None:
    bind = op.get_bind()
    if not _is_sqlite(bind):
        # Postgres support deferred; see module docstring.
        return

    for statement in _ALL_TRIGGERS:
        op.execute(statement)

    # Backfill existing rows. INSERT OR REPLACE handles duplicates that
    # might already be in global_index from prior manual reindex runs.
    op.execute(_BACKFILL_DELETE)
    op.execute(_BACKFILL_ASSETS)
    op.execute(_BACKFILL_ARCHIVE)


def downgrade() -> None:
    bind = op.get_bind()
    if not _is_sqlite(bind):
        return

    for name in _TRIGGER_NAMES:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")

    # Intentionally do NOT clear global_index — the mirror rows are
    # still valid data. Re-running upgrade just re-creates the triggers
    # and the backfill is idempotent via INSERT OR REPLACE.
