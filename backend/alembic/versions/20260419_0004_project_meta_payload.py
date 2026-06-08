"""store canonical project metadata payload

Revision ID: 20260419_0004
Revises: 20260419_0003
Create Date: 2026-06-07

Moves runtime project metadata away from ``project.json`` by adding a
``project_json`` payload column to ``project_meta``. Existing narrative
metadata columns remain in place.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260419_0004"
down_revision = "20260419_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("project_meta")}
    if "project_json" not in existing:
        op.add_column("project_meta", sa.Column("project_json", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("project_meta")}
    if "project_json" in existing:
        op.drop_column("project_meta", "project_json")
