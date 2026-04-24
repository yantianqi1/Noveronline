"""extend assets table with archive-specific columns

Revision ID: 20260419_0002
Revises: 20260419_0001
Create Date: 2026-04-19

Adds archive-library columns to the ``assets`` table so archive rows can
be merged into ``assets`` in the next revision (``20260419_0003``). All
added columns are nullable — existing assets rows (writing_style,
manuscript_block, etc.) simply carry NULL in the new columns.

Columns added (mirror of ``archive_library`` schema):

  entity_uuid, entity_name, entity_type, agent_kind, importance_tier,
  recommended_importance_tier, selected_importance_tier, template_key,
  template_version, entity_role, core_drive, surface_mask, hidden_tension,
  relationship_summary, agent_behavior_hint, human_ai_relation_tag,
  can_act_as_agent, notable_risks_json, template_sections_json,
  template_payload_json, template_metadata_json, entity_id, synced_at

After this revision runs:

  - ``archive_library`` table still holds the authoritative archive rows.
  - ``assets`` table has all columns ready to receive the migrated data.
  - No data has been moved yet (that happens in 20260419_0003).

Rollback drops the added columns (SQLite 3.35+ and Postgres both support
DROP COLUMN). If any assets row already uses these columns as an
archive_entity (i.e. 20260419_0003 has run), downgrade will fail safely
because the caller must first downgrade 20260419_0003.

Phase: asset-library refactor / P5 schema-merge step 1.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260419_0002"
down_revision = "20260419_0001"
branch_labels = None
depends_on = None


_NEW_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("entity_uuid", sa.String()),
    ("entity_name", sa.String()),
    ("entity_type", sa.String()),
    ("agent_kind", sa.String()),
    ("importance_tier", sa.String()),
    ("recommended_importance_tier", sa.String()),
    ("selected_importance_tier", sa.String()),
    ("template_key", sa.String()),
    ("template_version", sa.String()),
    ("entity_role", sa.String()),
    ("core_drive", sa.String()),
    ("surface_mask", sa.String()),
    ("hidden_tension", sa.String()),
    ("relationship_summary", sa.String()),
    ("agent_behavior_hint", sa.String()),
    ("human_ai_relation_tag", sa.String()),
    ("can_act_as_agent", sa.Integer()),
    ("notable_risks_json", sa.String()),
    ("template_sections_json", sa.String()),
    ("template_payload_json", sa.String()),
    ("template_metadata_json", sa.String()),
    ("entity_id", sa.String()),
    ("synced_at", sa.String()),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("assets")}
    for name, type_ in _NEW_COLUMNS:
        if name in existing:
            continue
        op.add_column("assets", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("assets")}
    for name, _ in _NEW_COLUMNS:
        if name in existing:
            op.drop_column("assets", name)
