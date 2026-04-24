"""Unified global search table and source-silo sync triggers."""

from __future__ import annotations

from sqlalchemy import DDL, event

from .base import metadata
from .helpers import composite_pk, project_id, table, text_col

global_index = table("global_index", text_col("source", nullable=False), text_col("source_ref", nullable=False), project_id(nullable=True), text_col("entity_type", nullable=False, default="''"), text_col("title", nullable=False, default="''"), text_col("body", nullable=False, default="''"), text_col("tags", nullable=False, default="''"), text_col("updated_at", nullable=False, default="''"), text_col("payload_json", nullable=False, default="'{}'"), composite_pk("source", "source_ref"))


# SQLite triggers that mirror writes on ``assets`` into ``global_index``
# so the FTS search path stays in sync without a manual ``reindex_project``
# step. Migration ``20260419_0003`` owns the same DDL for production
# upgrades; registering here lets test harnesses (which bypass alembic)
# pick up the triggers via ``init_db`` + ``metadata.create_all``.
#
# The triggers branch on ``asset_type`` because as of P5 of the
# asset-library refactor, the ``assets`` table hosts both regular
# assets (writing_style / manuscript_block / etc.) and archive entities
# (``asset_type='archive_entity'``). The former write global_index rows
# with source='assets'; the latter write source='archive' and pull from
# the archive-specific columns (entity_name, entity_role, core_drive, …).
#
# All statements use ``CREATE TRIGGER IF NOT EXISTS`` so double
# registration (alembic + metadata listener) is safe.

_GLOBAL_INDEX_SYNC_TRIGGERS = (
    # Generic (non-archive) assets: source='assets'.
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
    # Archive entities stored in assets: source='archive'.
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


def _register_sync_triggers() -> None:
    for statement in _GLOBAL_INDEX_SYNC_TRIGGERS:
        event.listen(metadata, "after_create", DDL(statement).execute_if(dialect="sqlite"))


_register_sync_triggers()
