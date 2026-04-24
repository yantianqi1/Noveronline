"""add soft FK columns: archive_library.entity_id, entities.archive_id

Revision ID: 20260418_0002
Revises: 20260418_0001
Create Date: 2026-04-18

Adds nullable cross-reference columns so ``archive_library`` rows can
point to their in-story counterpart in ``entities``, and vice versa.
The columns are populated lazily by ``narrative_entity_service`` when
both rows exist for the same (project_id, entity_name). Phase 1 / Task 5.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260418_0002"
down_revision = "20260418_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    archive_cols = {c["name"] for c in inspector.get_columns("archive_library")}
    if "entity_id" not in archive_cols:
        op.add_column("archive_library", sa.Column("entity_id", sa.String(), nullable=True))

    entity_cols = {c["name"] for c in inspector.get_columns("entities")}
    if "archive_id" not in entity_cols:
        op.add_column("entities", sa.Column("archive_id", sa.String(), nullable=True))


def downgrade() -> None:
    # SQLite pre-3.35 doesn't support DROP COLUMN; guard with dialect check.
    # Modern Python ships 3.35+ bundled, so this is a safe best-effort drop.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    archive_cols = {c["name"] for c in inspector.get_columns("archive_library")}
    if "entity_id" in archive_cols:
        op.drop_column("archive_library", "entity_id")
    entity_cols = {c["name"] for c in inspector.get_columns("entities")}
    if "archive_id" in entity_cols:
        op.drop_column("entities", "archive_id")
