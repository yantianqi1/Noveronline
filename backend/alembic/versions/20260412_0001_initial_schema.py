"""initial unified schema

Revision ID: 20260412_0001
Revises:
Create Date: 2026-04-12
"""

from __future__ import annotations

from alembic import op

from app.tables import metadata

revision = "20260412_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    metadata.drop_all(op.get_bind())
